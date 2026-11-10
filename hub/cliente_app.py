"""
hub/cliente_app.py — APP DO CLIENTE (Central do Cliente) · página pública em /cliente/
─────────────────────────────────────────────────────────────────────────────
Link geral para os clientes:  https://<seu-hub>/cliente/   (instalável como app)

  • Entrada: CPF (ou CNPJ) + e-mail, conferidos no cadastro de clientes do ERP
    (erp_parceiros: tipo=cliente, doc, email). Com "Exigir palavra-chave" ligado
    em Ajustes do Atendimento, pede também a PALAVRA-CHAVE de um pedido do
    cliente (gerada pelo ERP quando o pedido nasce; só atendentes veem).
    Se o cliente ainda não tem código, o código (6 caracteres) é criado na
    hora — o mesmo dos Tickets.
  • ATENDIMENTO = CHAT: a URA pergunta o assunto UMA vez e vira conversa com a
    central. Só existe UM chat ativo por cliente; quem encerra é o atendente
    (Concluir/Finalizar/Cancelar na central). Escrever "outro assunto" com um
    chat ativo entra no mesmo chat.
  • CHAMADO ÚNICO: o cliente tem UM chamado (o número é o código dele); cada
    problema é uma solicitação dentro dele. Pela aba Chamados ele abre com
    Motivo › Submotivo (árvore de Ajustes) — se já houver chamado, a nova
    solicitação é AGRUPADA nele (o app avisa). Em atendimento (chat ativo), não
    abre: o atendente registra a solicitação pelo chat.
  • Pedidos: status em linguagem de cliente, data e janela da entrega,
    tentativas, itens. Rascunhos e dados internos (custo, histórico com login
    de funcionário, observações, palavra-chave) NÃO saem daqui.
  • O cliente só vê o que é público: a abertura feita por ele e as mensagens
    com interno=False (as dele e as "Responder no app" da central).
  • Sem internet: o app guarda chats/chamados/mensagens numa fila e reenvia
    sozinho. Cada envio leva um "req" (id gerado no aparelho) — reenviar a
    mesma coisa nunca duplica.

Sessão do cliente: cookie próprio "cli_sessao" (HMAC com o HUB_SEGREDO, mas
com outra "etiqueta" — um token de cliente nunca vale como login do hub e
vice-versa). Se o CPF/e-mail mudar no ERP ou o cliente ficar inativo, a
sessão cai sozinha.

Cota grátis: nada de leitura extra — usa o cache dos Tickets (tickets.BASE,
atualização incremental a cada 20 s) e o cache do ERP (erp.ST).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

import acesso
import tickets as T

router = APIRouter()
PASTA = Path(__file__).parent / "static" / "cliente"
COOKIE = "cli_sessao"
DIAS_SESSAO = 30
ETIQUETA = "cliente-app:"          # entra na assinatura — separa do token do hub

# Assuntos da URA (Ajustes do Atendimento podem trocar em config/tickets_hub → app_cliente.ura)
URA_PADRAO = [
    {"id": "entrega", "rotulo": "Entrega e agendamento", "descricao": "Data, reagendar, endereço", "motivo_pai": "Logística", "departamento": "Logística"},
    {"id": "troca", "rotulo": "Troca, defeito ou avaria", "descricao": "Produto com problema ou diferente", "motivo_pai": "Pedido", "departamento": "CX"},
    {"id": "cancelar", "rotulo": "Cancelamento", "descricao": "Desistir do pedido", "motivo_pai": "Pedido", "departamento": "CX"},
    {"id": "cadastro", "rotulo": "Atualizar meus dados", "descricao": "Telefone, endereço, documentos", "motivo_pai": "Cliente", "departamento": "CX"},
    {"id": "outro", "rotulo": "Outro assunto", "descricao": "Fale com a central", "motivo_pai": "", "departamento": "CX"},
]
APP_PADRAO = {"ativo": True, "empresa": "Central do Cliente",
              "saudacao": "Olá! Sou o atendimento automático. Sobre o que você quer falar?", "ura": URA_PADRAO,
              "max_chamados_dia": 5, "exigir_palavra": False}

# Status do ERP → texto para o cliente
PED_ST = {
    "confirmado": ("Pedido confirmado", "Estamos preparando seu pedido."),
    "agendado": ("Entrega agendada", "Sua entrega já tem data marcada."),
    "em_carga": ("Separado para entrega", "Seu pedido está sendo carregado no caminhão."),
    "em_rota": ("Saiu para entrega", "O caminhão está a caminho."),
    "reagendar": ("Aguardando nova data", "Vamos combinar uma nova data de entrega com você."),
    "entregue": ("Entregue", "Pedido entregue."),
    "cancelado": ("Cancelado", "Este pedido foi cancelado."),
    "recusado": ("Entrega recusada", "A entrega foi recusada — a central vai falar com você."),
}
TRILHA = ["confirmado", "agendado", "em_rota", "entregue"]
RES_TENT = {"entregue": "Entregue", "ausente": "Ninguém em casa", "avaria": "Entregue com avaria", "recusado": "Recusada"}
TK_ST = {"aberto": "Recebido", "em_andamento": "Em atendimento", "aguardando": "Aguardando sua resposta",
         "resolvido": "Resolvido", "finalizado": "Encerrado", "cancelado": "Cancelado"}


def _erp():
    import erp
    return erp


def cfg_app() -> dict:
    """Ajustes do app (dentro de config/tickets_hub → app_cliente)."""
    try:
        bruto = T.hub_cfg().get("app_cliente") or {}
    except Exception:  # noqa: BLE001
        bruto = {}
    c = {**APP_PADRAO, **{k: v for k, v in bruto.items() if v not in (None, "")}}
    ura = [u for u in (c.get("ura") or []) if isinstance(u, dict) and u.get("id") and u.get("rotulo")]
    c["ura"] = ura or URA_PADRAO
    c["exigir_palavra"] = bool(c.get("exigir_palavra"))
    return c


# ══════════════════════════════════════════════════════════════════════════════
# SESSÃO DO CLIENTE
# ══════════════════════════════════════════════════════════════════════════════
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _assinar(corpo: str) -> str:
    return hmac.new(acesso.SEGREDO.encode(), (ETIQUETA + corpo).encode(), hashlib.sha256).hexdigest()


def _impressao(cli: dict) -> str:
    """Muda se o CPF ou o e-mail do cadastro mudarem → a sessão antiga cai."""
    return hashlib.sha256((T.digitos(cli.get("doc")) + "|" + str(cli.get("email") or "").strip().lower()).encode()).hexdigest()[:16]


def gerar_token(cliente_id: str, cli: dict) -> str:
    corpo = _b64(json.dumps({"c": cliente_id, "i": _impressao(cli), "e": int(time.time() + DIAS_SESSAO * 86400)}).encode())
    return corpo + "." + _assinar(corpo)


def ler_token(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    corpo, ass = token.rsplit(".", 1)
    if not hmac.compare_digest(_assinar(corpo), ass):
        return None
    try:
        d = json.loads(_unb64(corpo))
    except Exception:  # noqa: BLE001
        return None
    return d if d.get("e", 0) >= time.time() else None


def _cliente_da_sessao(request: Request) -> tuple[str, dict]:
    d = ler_token(request.cookies.get(COOKIE))
    if not d:
        raise HTTPException(401, "Entre com seus dados.")
    e = _erp()
    e.ST.carregar()
    cli = e.ST.dados["parceiros"].get(d.get("c") or "")
    if not cli or cli.get("tipo") != "cliente" or cli.get("ativo") is False or _impressao(cli) != d.get("i"):
        raise HTTPException(401, "Sua sessão expirou. Entre de novo.")
    return d["c"], cli


def _https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"


# ── freio contra tentativa de adivinhar CPF/e-mail/palavra ───────────────────
_falhas: dict[str, list[float]] = {}
_trava_falhas = threading.Lock()
LIMITE_IP, LIMITE_DOC, JANELA = 8, 5, 900


def _ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "?")


def _bloqueado(chave: str, limite: int) -> bool:
    agora = time.time()
    with _trava_falhas:
        l = [t for t in _falhas.get(chave, []) if agora - t < JANELA]
        _falhas[chave] = l
        return len(l) >= limite


def _falhou(*chaves: str):
    with _trava_falhas:
        for k in chaves:
            _falhas.setdefault(k, []).append(time.time())
        if len(_falhas) > 20000:
            _falhas.clear()


def doc_valido(d: str) -> bool:
    """CPF (dígitos verificadores) ou CNPJ com 14 dígitos."""
    if len(d) == 14:
        return len(set(d)) > 1
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (s * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def achar_cliente(doc: str, email: str) -> tuple[str, dict] | None:
    e = _erp()
    e.ST.carregar()
    for pid, c in e.ST.dados["parceiros"].items():
        if c.get("tipo") != "cliente" or c.get("ativo") is False:
            continue
        if T.digitos(c.get("doc")) == doc and str(c.get("email") or "").strip().lower() == email:
            return pid, c
    return None


def palavra_confere(cliente_id: str, palavra: str) -> bool:
    """A palavra-chave de QUALQUER pedido do cliente (que não esteja cancelado) serve."""
    e = _erp()
    alvo = e.normalizar_palavra(palavra)
    if not alvo:
        return False
    return any(p.get("cliente_id") == cliente_id and p.get("status") != "cancelado"
               and hmac.compare_digest(e.normalizar_palavra(p.get("palavra_chave")), alvo)
               for p in e.ST.dados["pedidos"].values() if p.get("palavra_chave"))


# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA (app instalável — escopo próprio /cliente/)
# ══════════════════════════════════════════════════════════════════════════════
SEM_CACHE = {"Cache-Control": "no-cache"}


@router.get("/cliente", include_in_schema=False)
def _sem_barra():
    return RedirectResponse("/cliente/", status_code=307)


@router.get("/cliente/", include_in_schema=False)
def pagina():
    return FileResponse(PASTA / "index.html", media_type="text/html; charset=utf-8", headers=SEM_CACHE)


@router.get("/cliente/manifest.webmanifest", include_in_schema=False)
def manifesto():
    return FileResponse(PASTA / "manifest.webmanifest", media_type="application/manifest+json", headers=SEM_CACHE)


@router.get("/cliente/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(PASTA / "sw.js", media_type="application/javascript",
                        headers={**SEM_CACHE, "Service-Worker-Allowed": "/cliente/"})


# ══════════════════════════════════════════════════════════════════════════════
# ENTRAR / SAIR
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/api/cliente/info")
def info():
    c = cfg_app()
    return {"ativo": bool(c.get("ativo")), "empresa": c.get("empresa"), "exigir_palavra": c["exigir_palavra"]}


@router.post("/api/cliente/entrar")
async def entrar(request: Request):
    c = cfg_app()
    if not c.get("ativo"):
        raise HTTPException(503, "O atendimento pelo app está pausado. Tente mais tarde.")
    if not T.configurado():
        raise HTTPException(503, "Sistema em manutenção. Tente mais tarde.")
    try:
        d = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Envio inválido.") from None
    doc = T.digitos(d.get("cpf"))
    email = str(d.get("email") or "").strip().lower()
    ip = "ip:" + _ip(request)
    if _bloqueado(ip, LIMITE_IP) or (doc and _bloqueado("doc:" + doc, LIMITE_DOC)):
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    if not doc_valido(doc):
        raise HTTPException(422, "Confira o CPF — ele parece incompleto ou errado.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(422, "Confira o e-mail.")
    if c["exigir_palavra"] and not str(d.get("palavra") or "").strip():
        raise HTTPException(422, "Informe a palavra-chave do seu pedido.")
    achado = achar_cliente(doc, email)
    if not achado or (c["exigir_palavra"] and not palavra_confere(achado[0], d.get("palavra"))):
        _falhou(ip, "doc:" + doc)
        raise HTTPException(401, ("Não encontramos um cadastro com esse CPF, e-mail e palavra-chave. A palavra-chave é informada "
                                  "pela nossa central quando o pedido é feito." if c["exigir_palavra"] else
                                  "Não encontramos um cadastro com esse CPF e e-mail. Use o e-mail informado na compra "
                                  "ou fale com a loja para atualizar seu cadastro."))
    pid, cli = achado
    e = _erp()
    if not str(cli.get("codigo") or "").strip():   # gera o código do cliente (o mesmo dos Tickets)
        with e.ST.trava:
            tx = e.Tx({"login": "app-cliente"})
            e.garantir_codigo(tx, pid)
            tx.commit()
        cli = e.ST.dados["parceiros"][pid]
    resp = JSONResponse({"ok": True, "nome": _primeiro_nome(cli.get("nome"))})
    resp.set_cookie(COOKIE, gerar_token(pid, cli), httponly=True, samesite="lax", secure=_https(request),
                    max_age=DIAS_SESSAO * 86400, path="/")
    return resp


@router.post("/api/cliente/sair")
def sair():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


def _primeiro_nome(n) -> str:
    return (str(n or "").strip().split(" ") or [""])[0].title()


# ══════════════════════════════════════════════════════════════════════════════
# O QUE O CLIENTE VÊ
# ══════════════════════════════════════════════════════════════════════════════
def pedidos_do_cliente(cid: str) -> list[dict]:
    e = _erp()
    saida = []
    for pid, p in e.ST.dados["pedidos"].items():
        if p.get("cliente_id") != cid or p.get("status") in (None, "rascunho"):
            continue
        st = p.get("status")
        rot, texto = PED_ST.get(st, (st, ""))
        if p.get("pendencia") == "ausente":
            texto = "Não encontramos ninguém na última tentativa. Vamos combinar uma nova data."
        elif p.get("pendencia") == "reposicao":
            texto = "Parte do pedido será reenviada (reposição de avaria)."
        elif p.get("sem_estoque") and st in ("confirmado", "reagendar"):
            texto = "Aguardando chegada do produto para agendar a entrega."
        passo = TRILHA.index(st) if st in TRILHA else (1 if st == "em_carga" else (0 if st == "reagendar" else -1))
        ag = p.get("agendamento") or {}
        end = p.get("endereco") or {}
        saida.append({
            "id": pid, "numero": p.get("numero"), "tipo": p.get("tipo") or "venda", "status": st, "rotulo": rot, "texto": texto,
            "passo": passo, "trilha": ["Confirmado", "Agendado", "Saiu p/ entrega", "Entregue"],
            "entrega": {"data": ag.get("data"), "janela": ag.get("janela")} if ag.get("data") else None,
            "criado_em": str(p.get("criado_em") or "")[:10], "valor_total": p.get("valor_total"),
            "itens": [{"nome": (e.ST.dados["produtos"].get(i.get("produto_id")) or {}).get("nome", "Produto"), "qtd": i.get("qtd")}
                      for i in p.get("itens", [])],
            "tentativas": [{"n": x.get("n"), "data": str(x.get("data") or "")[:10], "resultado": RES_TENT.get(x.get("resultado"), x.get("resultado"))}
                           for x in p.get("tentativas", [])],
            "endereco": ", ".join(x for x in (f"{end.get('logradouro', '')} {end.get('numero', '')}".strip(), end.get("bairro"),
                                                f"{end.get('cidade', '')}/{end.get('uf', '')}".strip("/")) if x),
        })
    saida.sort(key=lambda x: (x["status"] in ("entregue", "cancelado", "recusado"), -(x["numero"] or 0)))
    return saida


def tickets_do_cliente(cid: str, cli: dict) -> list[dict]:
    T.BASE.atualizar()
    cont = T._id_doc(cli.get("codigo") or "") if cli.get("codigo") else None
    return [t for t in T.BASE.tickets() if (cont and T.decompor(t["id"])[0] == cont) or t.get("erp_cliente_id") == cid]


def tipo_app(t: dict) -> str:
    """'chat' (Atendimento), 'chamado' (aberto pelo cliente na aba Chamados) ou 'central' (aberto pela equipe)."""
    if T.eh_chat(t):
        return "chat"
    return "chamado" if t.get("origem") == "app" else "central"


def chat_ativo(ts: list[dict]) -> dict | None:
    """O único chat em andamento (o mais recente, se por acaso houver mais de um antigo)."""
    ativos = [t for t in ts if tipo_app(t) == "chat" and t.get("status") in T.ABERTOS]
    return max(ativos, key=lambda t: str(t.get("criado_em") or "")) if ativos else None


def mensagens_publicas(t: dict) -> list[dict]:
    """Só o que o cliente pode ver. Comentário sem 'interno' explícito = interno (seguro)."""
    msgs = []
    if t.get("origem") == "app" and t.get("descricao"):
        msgs.append({"de": "cliente", "texto": t["descricao"], "data": t.get("criado_em"), "req": t.get("app_req")})
    for c in t.get("comentarios") or []:
        if c.get("interno") is not False:
            continue
        de = "cliente" if c.get("tipo") == "cliente" else "central"
        msgs.append({"de": de, "autor": "" if de == "cliente" else _primeiro_nome(c.get("autor")), "texto": c.get("texto", ""),
                     "data": c.get("data"), "req": c.get("req")})
    return msgs


def _pode_escrever(t: dict) -> bool:
    st = t.get("status")
    return st in T.ABERTOS if tipo_app(t) == "chat" else (st in T.ABERTOS or st == "resolvido")


def chamado_unico(cli: dict, ts: list[dict]) -> dict | None:
    """O chamado do cliente (número = código): solicitações + linha do tempo pública de tudo que não é o chat ativo."""
    ativo = chat_ativo(ts)
    sols = [t for t in ts if t is not ativo]
    if not sols:
        return None
    probs = [t for t in sols if not T.eh_chat(t)]
    linha = []
    for t in sols:
        cor, rot = T.cor_de(t), ("Chat" if T.eh_chat(t) else (t.get("assunto") or "Solicitação"))
        for m in mensagens_publicas(t):
            linha.append({**m, "sol": t["id"].split("#")[-1], "cor": cor, "rotulo": rot})
    linha.sort(key=lambda m: str(m.get("data") or ""))
    abertas = [t for t in probs if t.get("status") in T.ABERTOS]
    return {"numero": cli.get("codigo"), "aberto": bool(abertas),
            "rotulo": ("Em andamento" if abertas else "Sem pendências"),
            "solicitacoes": sorted(({**resumo_cliente(t), "cor": T.cor_de(t)} for t in probs),
                                   key=lambda x: (not x["aberto"], str(x["criado_em"] or ""))),
            "mensagens": linha, "pode_escrever": any(_pode_escrever(t) for t in probs),
            "resposta_nova_em": max((m["data"] for m in linha if m["de"] == "central"), default=None)}


def destino_da_mensagem(ts: list[dict]) -> dict | None:
    """Mensagem do cliente no chamado vai para a solicitação aberta que a central respondeu por último
    (ou a mais recente aberta; sem aberta, a última resolvida — que reabre)."""
    probs = [t for t in ts if not T.eh_chat(t) and _pode_escrever(t)]
    if not probs:
        return None
    def ult_central(t):
        return max((m["data"] or "" for m in mensagens_publicas(t) if m["de"] == "central"), default="")
    abertas = [t for t in probs if t.get("status") in T.ABERTOS] or probs
    return max(abertas, key=lambda t: (ult_central(t), str(t.get("atualizado_em") or "")))


def resumo_cliente(t: dict) -> dict:
    msgs = mensagens_publicas(t)
    ult = msgs[-1] if msgs else None
    st = t.get("status")
    return {"id": t["id"].split("#")[-1], "tipo": tipo_app(t), "assunto": t.get("assunto") or "Atendimento", "status": st,
            "rotulo": TK_ST.get(st, st), "aberto": st in T.ABERTOS, "pode_escrever": _pode_escrever(t),
            "criado_em": t.get("criado_em"), "atualizado_em": t.get("atualizado_em"), "pedido": t.get("erp_pedido_numero"),
            "motivo": " › ".join(x for x in (t.get("motivo_pai"), t.get("motivo_filho")) if x) if tipo_app(t) == "chamado" else "",
            "n_msgs": len(msgs), "ultima": ({"de": ult["de"], "texto": ult["texto"][:140], "data": ult["data"]} if ult else None),
            "resposta_nova_em": next((m["data"] for m in reversed(msgs) if m["de"] == "central"), None)}


def _completo(t: dict) -> dict:
    return {**resumo_cliente(t), "mensagens": mensagens_publicas(t)}


def _ticket_do_cliente(cid: str, cli: dict, sid: str) -> dict:
    sid = str(sid or "")
    t = next((x for x in tickets_do_cliente(cid, cli) if x["id"].split("#")[-1] == sid), None)
    if not t:
        raise HTTPException(404, "Atendimento não encontrado.")
    return t


def motivos_para_cliente() -> dict:
    """Motivo › Submotivos ativos (a mesma árvore de Ajustes do Atendimento)."""
    saida = {}
    for pai, filhos in T.motivos().items():
        ativos = [f for f, i in (filhos or {}).items() if (i or {}).get("ativo", True)]
        if ativos:
            saida[pai] = ativos
    return saida


@router.get("/api/cliente/eu")
def eu(request: Request):
    cid, cli = _cliente_da_sessao(request)
    c = cfg_app()
    todos = sorted(tickets_do_cliente(cid, cli), key=lambda t: str(t.get("atualizado_em") or ""), reverse=True)
    ts = [x for x in todos if x.get("status") in T.ABERTOS] + [x for x in todos if x.get("status") not in T.ABERTOS][:20]
    ativo = chat_ativo(todos)
    return {"nome": _primeiro_nome(cli.get("nome")), "nome_completo": cli.get("nome"), "codigo": cli.get("codigo"),
            "empresa": c.get("empresa"), "saudacao": c.get("saudacao"),
            "ura": [{k: u.get(k) for k in ("id", "rotulo", "descricao")} for u in c["ura"]],
            "motivos": motivos_para_cliente(),
            "pedidos": pedidos_do_cliente(cid), "chamados": [resumo_cliente(t) for t in ts],
            "chamado": chamado_unico(cli, todos),
            "chat": _completo(ativo) if ativo else None, "versao": T.BASE.ver}


@router.get("/api/cliente/novidades")
def novidades(request: Request):
    """Barato: o app chama a cada ~15 s com a tela aberta. Só diz se algo mudou."""
    _cliente_da_sessao(request)
    T.BASE.atualizar()
    return {"versao": T.BASE.ver}


@router.get("/api/cliente/chamado/{sid}")
def chamado(sid: str, request: Request):
    cid, cli = _cliente_da_sessao(request)
    return _completo(_ticket_do_cliente(cid, cli, sid))


# ══════════════════════════════════════════════════════════════════════════════
# ESCREVER (chat, chamado, mensagem) — idempotente pelo "req" do aparelho
# ══════════════════════════════════════════════════════════════════════════════
def _me(cli: dict) -> dict:
    return {"usuario": "cliente:" + str(cli.get("codigo") or ""), "nome": cli.get("nome") or "Cliente", "depto": "", "hub": ""}


def _req(d: dict) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(d.get("req") or ""))[:40]


def _ja_recebido(ts: list[dict], req: str) -> dict | None:
    """Ticket onde esse envio (req) já entrou — como abertura ou como mensagem."""
    if not req:
        return None
    for t in ts:
        if t.get("app_req") == req or any(c.get("req") == req for c in t.get("comentarios") or []):
            return t
    return None


def _msg_cliente(s: dict, me: dict, texto: str, req: str = "", offline_em: str = ""):
    c = {"autor": me["nome"], "usuario": me["usuario"], "texto": texto, "data": T.agora(), "interno": False, "tipo": "cliente", "via": "app"}
    if req:
        c["req"] = req
    if offline_em:
        c["escrito_em"] = offline_em
    s.setdefault("comentarios", []).append(c)
    s["app_pendente"] = True
    s["app_pendente_desde"] = s.get("app_pendente_desde") or T.agora()
    if s.get("status") in ("aguardando", "resolvido"):   # cliente respondeu → volta para a fila
        s["status"] = "em_andamento" if (s.get("atendentes") or s.get("atribuido_para")) else "aberto"


def _texto(d: dict) -> str:
    texto = re.sub(r"[ \t]+", " ", str(d.get("texto") or "")).strip()
    if not texto:
        raise HTTPException(422, "Escreva sua mensagem.")
    if len(texto) > 2000:
        raise HTTPException(422, "Mensagem muito longa (máx. 2000 caracteres).")
    return texto


def _offline_em(d: dict) -> str:
    """Hora em que o cliente escreveu sem internet (vai junto na mensagem para a central saber)."""
    v = str(d.get("escrito_em") or "")
    return v[:19] if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", v) else ""


_envios: dict[str, list[float]] = {}


def _freio_msg(chave: str, maximo=12, janela=300):
    agora = time.time()
    with _trava_falhas:
        l = [x for x in _envios.get(chave, []) if agora - x < janela]
        if len(l) >= maximo:
            raise HTTPException(429, "Muitas mensagens seguidas. Aguarde alguns minutos.")
        l.append(agora)
        _envios[chave] = l
        if len(_envios) > 20000:
            _envios.clear()


def _limite_dia(cid: str, cli: dict, c: dict):
    hoje = T.agora()[:10]
    n = sum(1 for t in tickets_do_cliente(cid, cli) if t.get("origem") == "app" and str(t.get("criado_em") or "")[:10] == hoje)
    if n >= int(c.get("max_chamados_dia") or 5):
        raise HTTPException(429, "Você já abriu vários atendimentos hoje. Continue a conversa em um deles.")


def _criar(cid: str, cli: dict, me: dict, dados: dict) -> str:
    base = {"prioridade": "normal", "cliente_nome": cli.get("nome", ""), "cliente_telefone": cli.get("telefone", ""),
            "solicitante_nome": cli.get("nome", ""), "aberto_por": me["usuario"], "origem": "app", "erp_cliente_id": cid,
            "app_pendente": True, "app_pendente_desde": T.agora(), "ultima_interacao_autor": me["usuario"],
            "cliente_codigo": cli.get("codigo")}
    tid = T.criar_solicitacao({k: v for k, v in {**base, **dados}.items() if v not in (None, "")}, me)
    return tid.split("#")[-1]


def _depto_do_motivo(pai: str, preferido: str = "") -> str:
    deps = T.departamentos()
    if preferido in deps:
        return preferido
    for u in cfg_app()["ura"]:   # o setor que Ajustes ligou a esse motivo no menu da URA
        if pai and u.get("motivo_pai") == pai and u.get("departamento") in deps:
            return u["departamento"]
    return T.hub_cfg().get("depto_erp") or (deps[0] if deps else "")


@router.post("/api/cliente/chat")
async def chat(request: Request):
    """Atendimento: a URA perguntou o assunto UMA vez → vira chat. Um chat ativo por cliente:
    se já houver, a mensagem entra nele (só o atendente encerra)."""
    cid, cli = _cliente_da_sessao(request)
    d = await request.json()
    texto, req, off = _texto(d), _req(d), _offline_em(d)
    ts = tickets_do_cliente(cid, cli)
    feito = _ja_recebido(ts, req)
    if feito:
        return {"ok": True, "id": feito["id"].split("#")[-1], "repetido": True}
    me = _me(cli)
    ativo = chat_ativo(ts)
    if ativo:
        _freio_msg("cli:" + cid)
        T._mutar_sol(ativo["id"], lambda s: _msg_cliente(s, me, texto, req, off), me)
        return {"ok": True, "id": ativo["id"].split("#")[-1], "existente": True}
    c = cfg_app()
    op = next((u for u in c["ura"] if u.get("id") == d.get("opcao")), None) or next((u for u in c["ura"] if u.get("id") == "outro"), c["ura"][-1])
    _limite_dia(cid, cli, c)
    _freio_msg("cli:" + cid)
    pai = op.get("motivo_pai") if op.get("motivo_pai") in T.motivos() else ""
    depto = _depto_do_motivo(pai, op.get("departamento") or "")
    sid = _criar(cid, cli, me, {
        "assunto": op["rotulo"], "descricao": texto + (f"\n\n(escrito sem internet em {off[8:10]}/{off[5:7]} {off[11:16]})" if off else ""),
        "departamento": depto, "categoria": depto, "motivo_pai": pai, "motivo_pai_id": pai, "motivo_filho": "",
        "sla1_prazo_dias": T._sla_motivo(pai, "") if pai else (T.hub_cfg().get("sla_erp_dias") or 1),
        "app_tipo": "chat", "app_opcao": op["id"], "app_req": req})
    return {"ok": True, "id": sid, "existente": False}


@router.post("/api/cliente/chamados")
async def abrir_chamado(request: Request):
    """Aba Chamados: o cliente abre com Motivo › Submotivo (árvore de Ajustes) + pedido opcional.
    Vira uma SOLICITAÇÃO no chamado único do cliente (agrupada, se ele já tinha).
    Em atendimento (chat ativo) não abre: o atendente registra pelo chat."""
    cid, cli = _cliente_da_sessao(request)
    d = await request.json()
    texto, req, off = _texto(d), _req(d), _offline_em(d)
    ts = tickets_do_cliente(cid, cli)
    feito = _ja_recebido(ts, req)
    if feito:
        return {"ok": True, "id": feito["id"].split("#")[-1], "repetido": True, "chamado": cli.get("codigo")}
    if chat_ativo(ts):
        raise HTTPException(409, "Você está em atendimento agora. Conte no chat da aba Atendimento — o atendente abre a solicitação para você.")
    pai, filho = str(d.get("motivo_pai") or ""), str(d.get("motivo_filho") or "")
    arv = motivos_para_cliente()
    if pai not in arv or filho not in arv[pai]:
        raise HTTPException(422, "Escolha o motivo e o submotivo do chamado.")
    e = _erp()
    ped_id = str(d.get("pedido_id") or "")
    ped = e.ST.dados["pedidos"].get(ped_id) if ped_id else None
    if ped_id and (not ped or ped.get("cliente_id") != cid):
        raise HTTPException(404, "Pedido não encontrado.")
    for t in ts:
        if (not T.eh_chat(t) and t.get("status") not in ("finalizado", "cancelado") and T.norm(t.get("motivo_pai")) == T.norm(pai)
                and str(t.get("erp_pedido_id") or "") == ped_id):
            raise HTTPException(409, f"Seu chamado nº {cli.get('codigo')} já tem uma solicitação de \"{pai}\""
                                     + (f" do pedido #{ped.get('numero')}" if ped else "") + ". Escreva nela pela aba Chamados.")
    havia = sum(1 for t in ts if not T.eh_chat(t) and t.get("status") in T.ABERTOS)
    c = cfg_app()
    _limite_dia(cid, cli, c)
    _freio_msg("cli:" + cid)
    depto = _depto_do_motivo(pai)
    me = _me(cli)
    dados = {"assunto": f"{filho}" + (f" · pedido #{ped.get('numero')}" if ped else ""),
             "descricao": texto + (f"\n\n(escrito sem internet em {off[8:10]}/{off[5:7]} {off[11:16]})" if off else ""),
             "departamento": depto, "categoria": depto, "motivo_pai": pai, "motivo_pai_id": pai, "motivo_filho": filho,
             "sla1_prazo_dias": T._sla_motivo(pai, filho), "app_tipo": "chamado", "app_req": req}
    if ped:
        dados.update(erp_pedido_id=ped_id, erp_pedido_numero=ped.get("numero"))
    sid = _criar(cid, cli, me, dados)
    return {"ok": True, "id": sid, "existente": False, "agrupado": bool(havia), "chamado": cli.get("codigo"), "solicitacoes": havia + 1}


@router.post("/api/cliente/chamado/mensagem")
async def mensagem_no_chamado(request: Request):
    """O cliente escreve no chamado (sem escolher solicitação): vai para a que a central respondeu por último."""
    cid, cli = _cliente_da_sessao(request)
    d = await request.json()
    texto, req, off = _texto(d), _req(d), _offline_em(d)
    ts = tickets_do_cliente(cid, cli)
    if req and _ja_recebido(ts, req):
        return {"ok": True, "repetido": True}
    alvo = destino_da_mensagem(ts)
    if not alvo:
        raise HTTPException(409, "Seu chamado não tem solicitações abertas. Para um assunto novo, abra pela aba Chamados ou fale no Atendimento.")
    _freio_msg("cli:" + cid)
    me = _me(cli)
    T._mutar_sol(alvo["id"], lambda s: _msg_cliente(s, me, texto, req, off), me)
    return {"ok": True, "sol": alvo["id"].split("#")[-1]}


@router.post("/api/cliente/chamado/{sid}/mensagem")
async def mensagem(sid: str, request: Request):
    cid, cli = _cliente_da_sessao(request)
    t = _ticket_do_cliente(cid, cli, sid)
    d = await request.json()
    texto, req, off = _texto(d), _req(d), _offline_em(d)
    if req and _ja_recebido([t], req):
        return {"ok": True, "repetido": True}
    if not _pode_escrever(t):
        raise HTTPException(409, "Este atendimento foi encerrado pela central." + (" Fale com a gente de novo pela aba Atendimento."
                                                                                  if tipo_app(t) == "chat" else " Abra um novo chamado se precisar."))
    _freio_msg("cli:" + cid)
    me = _me(cli)
    T._mutar_sol(t["id"], lambda s: _msg_cliente(s, me, texto, req, off), me)
    return {"ok": True}
