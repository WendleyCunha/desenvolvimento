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
    tentativas, itens e a PALAVRA-CHAVE do pedido (login e, no futuro, entrega).
    Rascunhos e dados internos (custo, histórico com login de funcionário,
    observações) NÃO saem daqui.
  • Chamados no app = as SOLICITAÇÕES (os tickets do atendente): o que ficou
    definido (motivo, etapa, prazo combinado, situação) e as ATUALIZAÇÕES que
    a central registrou ("Registrar contato"). A conversa fica só no Atendimento.
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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

import acesso
import banco
import tickets as T

router = APIRouter()
PASTA = Path(__file__).parent / "static" / "cliente"
COOKIE = "cli_sessao"


def _ck() -> str:
    """Nome do cookie de sessão — um por empresa (o mesmo celular pode usar o app de duas empresas sem misturar)."""
    return COOKIE if banco.empresa_atual() == banco.PRINCIPAL else f"{COOKIE}_{banco.empresa_atual()}"
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
    d = ler_token(request.cookies.get(_ck()))
    if not d:
        raise HTTPException(401, "Entre com seus dados.")
    e = _erp()
    e.ST.carregar()
    cli = e.ST.dados["parceiros"].get(d.get("c") or "")
    if not cli or cli.get("tipo") != "cliente" or cli.get("ativo") is False:
        raise HTTPException(401, "Sua sessão expirou. Entre de novo.")
    if d.get("d"):   # aparelho conectado pelo link + senha (cliente_acesso.py)
        import cliente_acesso
        cliente_acesso.checar_aparelho(d, d["c"], cli)
    elif _impressao(cli) != d.get("i"):   # login antigo (CPF + e-mail)
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
    return RedirectResponse(banco.prefixo_publico() + "/cliente/", status_code=307)


@router.get("/cliente/", include_in_schema=False)
def pagina():
    return FileResponse(PASTA / "index.html", media_type="text/html; charset=utf-8", headers=SEM_CACHE)


@router.get("/cliente/manifest.webmanifest", include_in_schema=False)
def manifesto():
    return acesso.manifesto_publico(PASTA / "manifest.webmanifest", "/cliente/")


@router.get("/cliente/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(PASTA / "sw.js", media_type="application/javascript",
                        headers={**SEM_CACHE, "Service-Worker-Allowed": banco.prefixo_publico() + "/cliente/"})


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
    resp.set_cookie(_ck(), gerar_token(pid, cli), httponly=True, samesite="lax", secure=_https(request),
                    max_age=DIAS_SESSAO * 86400, path="/")
    return resp


@router.post("/api/cliente/sair")
def sair():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(_ck(), path="/")
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
            "palavra_chave": p.get("palavra_chave") if st not in ("cancelado", "recusado") else "",
            "recebido": {k: (p.get("entrega") or {}).get(k) for k in ("em", "recebedor", "parentesco", "resultado")} if p.get("entrega") else None,
            "rota": _rota_do_pedido(pid) if st in ("agendado", "em_carga", "em_rota", "entregue", "reagendar") else None,
            "endereco": ", ".join(x for x in (f"{end.get('logradouro', '')} {end.get('numero', '')}".strip(), end.get("bairro"),
                                                f"{end.get('cidade', '')}/{end.get('uf', '')}".strip("/")) if x),
        })
    saida.sort(key=lambda x: (x["status"] in ("entregue", "cancelado", "recusado"), -(x["numero"] or 0)))
    return saida


def _rota_do_pedido(pid: str) -> dict | None:
    """[WROUTER] Acompanhamento da entrega: situação na rua, km até o endereço e o link (vizinho, palavra)."""
    try:
        import wrouter
        a = wrouter.acompanhamento_do_pedido(pid)
    except Exception:  # noqa: BLE001
        return None
    if not a:
        return None
    me = next((x for x in a["pedidos"] if x["pid"] == pid), {})
    return {"fase": a["fase"], "km": me.get("km"), "km_cor": me.get("km_cor"), "km_aprox": me.get("km_aprox"), "pos_ha_seg": a.get("pos_ha_seg"),
            "chegou": me.get("chegou"), "desfecho": me.get("desfecho"), "vizinho": me.get("vizinho"), "pode_vizinho": a.get("pode_vizinho"),
            "mapa": bool(a.get("mapa")), "link": f"{banco.prefixo_publico()}/entrega/{a['token']}" if a.get("token") else ""}


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
                     "data": c.get("data"), "req": c.get("req"), **({"anexos": c["anexos"]} if c.get("anexos") else {})})
    return msgs


def _pode_escrever(t: dict) -> bool:
    st = t.get("status")
    return st in T.ABERTOS if tipo_app(t) == "chat" else (st in T.ABERTOS or st == "resolvido")


def atualizacoes(t: dict) -> list[dict]:
    """O que a central registrou para o cliente nesta solicitação (Registrar contato / respostas),
    a partir de quando ela virou solicitação — a conversa do chat que a originou NÃO entra."""
    desde = str(t.get("criado_em") or "")
    out = []
    if t.get("origem") == "app" and t.get("descricao") and not t.get("convertido_de_chat"):
        out.append({"de": "cliente", "texto": t["descricao"], "data": t.get("criado_em")})
    for c in t.get("comentarios") or []:
        if c.get("interno") is not False or c.get("tipo") not in ("contato", "resposta", "atualizacao"):
            continue
        if str(c.get("data") or "") < desde:
            continue
        out.append({"de": "central", "autor": _primeiro_nome(c.get("autor")), "texto": c.get("texto", ""), "data": c.get("data")})
    return out


def definido(t: dict) -> dict:
    """O que ficou combinado nesta solicitação (sem detalhe interno)."""
    etapa = str(t.get("etapa_atual") or "").split(" › ")
    return {"motivo": " › ".join(x for x in (t.get("motivo_pai"), t.get("motivo_filho")) if x),
            "etapa": etapa[1] if len(etapa) > 1 else "",
            "prazo": str(t.get("etapa_data_prevista") or "")[:10] if t.get("etapa_vermelha") else "",
            "resolvido_em": t.get("resolvido_em") if t.get("status") in ("resolvido", "finalizado") else ""}


def chamado_unico(cli: dict, ts: list[dict]) -> dict | None:
    """O chamado do cliente (número = código): as solicitações, cada uma com o definido e as atualizações.
    Chats NÃO entram aqui — conversa é a aba Atendimento."""
    probs = [t for t in ts if not T.eh_chat(t)]
    if not probs:
        return None
    sols = []
    for t in probs:
        at = atualizacoes(t)
        sols.append({**resumo_cliente(t), "cor": T.cor_de(t), "definido": definido(t), "atualizacoes": at,
                     "atualizada_em": max((a["data"] or "" for a in at if a["de"] == "central"), default=None)})
    sols.sort(key=lambda x: (not x["aberto"], str(x["criado_em"] or "")))
    abertas = [x for x in sols if x["aberto"]]
    return {"numero": cli.get("codigo"), "aberto": bool(abertas), "rotulo": "Em andamento" if abertas else "Sem pendências",
            "solicitacoes": sols, "resposta_nova_em": max((x["atualizada_em"] or "" for x in sols), default=None) or None}


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
        ativos = [f for f, i in (filhos or {}).items() if (i or {}).get("ativo", True) and (i or {}).get("exige_codigo", True)]   # interno não aparece pro cliente
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
    import cliente_acesso
    pedidos = pedidos_do_cliente(cid)
    protegida = cliente_acesso.palavra_protegida(request, cid)
    if protegida:   # com senha criada: a palavra-chave da entrega só aparece depois de digitar a senha
        for p in pedidos:
            p["palavra_protegida"] = bool(p.get("palavra_chave"))
            p["palavra_chave"] = ""
    return {"palavra_protegida": protegida, "tem_senha": cliente_acesso.tem_senha(cid),
            "nome": _primeiro_nome(cli.get("nome")), "nome_completo": cli.get("nome"), "codigo": cli.get("codigo"),
            "empresa": c.get("empresa"), "saudacao": c.get("saudacao"),
            "ura": [{k: u.get(k) for k in ("id", "rotulo", "descricao")} for u in c["ura"]],
            "motivos": motivos_para_cliente(),
            "pedidos": pedidos, "chamados": [resumo_cliente(t) for t in ts],
            "chamado": chamado_unico(cli, todos),
            "chat": _completo(ativo) if ativo else None, "versao": T.BASE.ver}


@router.get("/api/cliente/pedido/{pid}/pdf")
def pdf_pedido_cliente(pid: str, request: Request):
    """O cliente baixa o PDF do próprio pedido (com a palavra-chave da entrega)."""
    cid, _cli = _cliente_da_sessao(request)
    e = _erp()
    ped = e.ST.dados["pedidos"].get(pid)
    if not ped or ped.get("cliente_id") != cid or ped.get("status") in (None, "rascunho"):
        raise HTTPException(404, "Pedido não encontrado.")
    import cliente_acesso
    if cliente_acesso.palavra_protegida(request, cid):   # o PDF traz a palavra-chave da entrega
        raise HTTPException(403, "Digite sua senha no app para baixar o PDF do pedido.")
    pdf = e.pdf_do_pedido(ped, palavra=(ped.get("palavra_chave") or "") if ped.get("status") not in ("cancelado", "recusado", "entregue") else "")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="pedido_{ped.get("numero")}.pdf"'})


@router.get("/api/cliente/pedido/{pid}/comprovante")
def comprovante_cliente(pid: str, request: Request):
    """O cliente baixa o comprovante de entrega do próprio pedido (quem recebeu, assinatura, foto, código de integridade)."""
    cid, _cli = _cliente_da_sessao(request)
    e = _erp()
    ped = e.ST.dados["pedidos"].get(pid)
    if not ped or ped.get("cliente_id") != cid:
        raise HTTPException(404, "Pedido não encontrado.")
    import wrouter
    return wrouter.comprovante_pdf_resposta(pid)


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
    s.pop("chamei_em", None)   # a central tinha chamado: o cliente respondeu → sai de "Chamei" e volta para Atendimentos
    s.pop("chamei_por", None)
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


_envios = banco.por_empresa(dict)


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
    return _chat_do_cliente(cid, cli, d)


def _chat_do_cliente(cid: str, cli: dict, d: dict, via: str = "") -> dict:
    """Escreve no chat ativo do cliente ou abre um novo (URA do app, ou o link de atendimento quando via="link")."""
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
    if via in ("link", "link_sem_id"):   # link de atendimento (Ajustes › Wwhat): sem URA, cai no setor escolhido lá
        w = cfg_wwhat()
        op = {"id": via, "rotulo": "Atendimento pelo link" if via == "link" else "Atendimento pelo link · sem identificação",
              "motivo_pai": w.get("motivo_pai") or "", "departamento": w.get("departamento") or "CX"}
    else:
        op = next((u for u in c["ura"] if u.get("id") == d.get("opcao")), None) or next((u for u in c["ura"] if u.get("id") == "outro"), c["ura"][-1])
    _limite_dia(cid, cli, c)
    _freio_msg("cli:" + cid)
    pai = op.get("motivo_pai") if op.get("motivo_pai") in T.motivos() else ""
    depto = _depto_do_motivo(pai, op.get("departamento") or "")
    dados = {
        "assunto": op["rotulo"], "descricao": texto + (f"\n\n(escrito sem internet em {off[8:10]}/{off[5:7]} {off[11:16]})" if off else ""),
        "departamento": depto, "categoria": depto, "motivo_pai": pai, "motivo_pai_id": pai, "motivo_filho": "",
        "sla1_prazo_dias": T._sla_motivo(pai, "") if pai else (T.hub_cfg().get("sla_erp_dias") or 1),
        "app_tipo": "chat", "app_opcao": op["id"], "app_req": req}
    if via:
        dados["app_via"] = via
    sid = _criar(cid, cli, me, dados)
    try:
        T.distribuir(forcar=True)   # chat novo: já vai para um atendente online do setor
    except Exception as ex:  # noqa: BLE001
        print(f"[cliente] distribuição: {ex}")
    return {"ok": True, "id": sid, "existente": False}


def central_chama(cid: str, texto: str, me: dict, pedido: dict | None = None, anexos: list | None = None, cli: dict | None = None) -> dict:
    """A CENTRAL chama o cliente: a mensagem entra no chat ativo dele (ou abre um chat novo já com o atendente)
    e o celular dele recebe notificação — no app (/cliente/) e/ou no link de atendimento (/atendimento/), onde
    ele tiver ativado os avisos. `cli` permite chamar o visitante do link (sem cadastro no ERP)."""
    e = _erp()
    cli = cli if cli is not None else (e.ST.dados["parceiros"].get(cid) or {})
    if not cli.get("codigo"):
        raise HTTPException(409, "Este cliente ainda não tem código do app (é gerado no primeiro pedido/cadastro). Use o WhatsApp.")
    texto = re.sub(r"[ \t]+", " ", str(texto or "")).strip()[:2000]
    if not texto and not anexos:
        raise HTTPException(422, "Escreva a mensagem para o cliente.")
    eu = {"usuario": me.get("login") or me.get("usuario") or "", "nome": me.get("nome") or me.get("login") or "Central"}
    anx = []
    if anexos:
        import anexos as A
        anx = A.salvar_lista(anexos, {"cont": T._id_doc(cli["codigo"])})

    def msg(s):
        T._coment(s, eu, texto, interno=False, tipo="resposta", anexos=anx)
        s["app_pendente"] = False
        s.pop("app_pendente_desde", None)
        s["app_respondido_em"] = T.agora()
        s["chamei_em"], s["chamei_por"] = T.agora(), eu["usuario"]   # fila "Chamei" na Caixa até o cliente responder
        if s.get("status") in ("aberto", "aguardando"):
            s["status"] = "em_andamento"
        if eu["usuario"] and eu["usuario"] not in (s.get("atendentes") or []):
            s.setdefault("atendentes", []).append(eu["usuario"])
            s.setdefault("atribuido_para", eu["usuario"])

    ativo = chat_ativo(tickets_do_cliente(cid, cli))
    if ativo:
        T._mutar_sol(ativo["id"], msg, eu)
        tid = ativo["id"].split("#")[-1]
    else:
        ped = pedido or {}
        dados = {"assunto": f"Entrega do pedido #{ped.get('numero')}" if ped else "Contato da central", "descricao": "",
                 "departamento": T.hub_cfg().get("depto_erp") or "", "app_tipo": "chat", "app_opcao": "central",
                 "app_pendente": False, "aberto_pela_central": True, "atendentes": [eu["usuario"]] if eu["usuario"] else [],
                 "atribuido_para": eu["usuario"], "status": "em_andamento", "erp_pedido_id": ped.get("id"), "erp_pedido_numero": ped.get("numero")}
        dados["categoria"] = dados["departamento"]
        tid = _criar(cid, cli, eu, dados)
        T._mutar_sol(T.compor(T._id_doc(cli["codigo"]), tid), msg, eu)
    aviso = {"total": 0, "enviados": 0}
    try:   # manda o aviso e espera até 8 s pelo resultado (a central vê se chegou); demorou → segue em segundo plano
        import promocoes
        cod = str(cli["codigo"]).upper()
        box = {}
        th = threading.Thread(target=lambda: box.update(promocoes.avisar_cliente_detalhe(
            cod, "💬 A central está te chamando", texto[:140] or "📎 Anexo", f"{banco.prefixo_publico()}/cliente/", f"central-{cod}-{int(time.time())}")), daemon=True)
        th.start()
        th.join(8)
        aviso = box or {"total": len((promocoes.inscricoes().get(cod) or {}).get("subs") or []), "enviados": None}
    except Exception as ex:  # noqa: BLE001
        print(f"[cliente] sem notificação: {ex}")
    return {"ok": True, "id": tid, "existente": bool(ativo), "chamado": cli["codigo"], "aparelhos": aviso.get("total", 0),
            "avisados": aviso.get("enviados"), "aviso": aviso}


def chamar_por_codigo(codigo: str, texto: str, me: dict) -> dict:
    """Botão "Chamar cliente" do CX: pelo código do chamado — cliente do ERP ou visitante do link (V…)."""
    cod = str(codigo or "").strip().upper()
    e = _erp()
    e.ST.carregar()
    achado = next(((k, c) for k, c in e.ST.dados["parceiros"].items() if c.get("tipo") == "cliente" and str(c.get("codigo") or "").upper() == cod), None)
    if achado:
        return central_chama(achado[0], texto, me)
    cont = T.BASE.cont.get(T._id_doc(cod)) if cod else None
    if not cont:
        raise HTTPException(404, "Cliente não encontrado.")
    return central_chama("", texto, me, cli={"codigo": cod, "nome": cont.get("cliente_nome") or "Cliente", "tipo": "visitante"})


def chat_com_cliente(cid: str, tid: str = "") -> dict:
    """Situação do chat do app com o cliente (tela dividida do WROUTER). Sem chat aberto, devolve o último
    chat chamado pela entrega (`tid`), já finalizado — assim o PDF do caso traz a conversa inteira."""
    cli = _erp().ST.dados["parceiros"].get(cid) or {}
    if not cli.get("codigo"):
        return {"ativo": False, "sem_app": True, "mensagens": []}
    ts = tickets_do_cliente(cid, cli)
    ativo = chat_ativo(ts)
    if not ativo:
        ant = next((t for t in ts if tid and t["id"].split("#")[-1] == str(tid).split("#")[-1]), None)
        if ant:
            return {"ativo": False, "id": ant["id"], "chamado": cli["codigo"], "status": ant.get("status"), "nova": False,
                    "mensagens": mensagens_publicas(ant)[-80:]}
        return {"ativo": False, "mensagens": []}
    return {"ativo": True, "id": ativo["id"], "chamado": cli["codigo"], "status": ativo.get("status"),
            "nova": bool(ativo.get("app_pendente")), "mensagens": mensagens_publicas(ativo)[-80:]}


def central_finaliza_chat(cid: str, me: dict) -> bool:
    """Finaliza SÓ a conversa com o cliente (o chat com o motorista é outro e continua)."""
    cli = _erp().ST.dados["parceiros"].get(cid) or {}
    ativo = chat_ativo(tickets_do_cliente(cid, cli)) if cli.get("codigo") else None
    if not ativo:
        return False
    eu = {"usuario": me.get("login") or me.get("usuario") or "", "nome": me.get("nome") or me.get("login") or "Central"}

    def fn(s):
        s.update(status="resolvido", resolvido_em=T.agora(), resolvido_por=eu["usuario"], app_pendente=False)
        s.pop("app_pendente_desde", None)
        T._coment(s, eu, "💬 Conversa com o cliente finalizada pela central de entregas (WROUTER).", tipo="sistema")
    T._mutar_sol(ativo["id"], fn, eu)
    return True


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


@router.get("/api/cliente/anexo/{aid}")
def ver_anexo(aid: str, request: Request):
    """Anexo que a central mandou no chat/chamado — só o próprio cliente abre."""
    cid, cli = _cliente_da_sessao(request)
    import anexos as A
    doc = A.ler(aid)
    if not cli.get("codigo") or doc.get("cont") != T._id_doc(cli["codigo"]):
        raise HTTPException(404, "Anexo não encontrado.")
    return A.resposta(doc)


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


# ══════════════════════════════════════════════════════════════════════════════
# LINK DE ATENDIMENTO (/atendimento/) — bot de boas-vindas que valida o cliente
# ──────────────────────────────────────────────────────────────────────────────
#  O bot pede o CPF e faz DUAS perguntas com o que está no ERP (número da casa,
#  4 últimos do telefone, sobrenome, começo do CEP e uma de múltipla escolha
#  — produto comprado ou bairro). Acertou as duas → sessão SÓ de atendimento
#  (cookie próprio "cli_atend", outra etiqueta na assinatura): conversa com a
#  central e nada mais — não vê pedidos, não abre chamado. O app (/cliente/)
#  continua com tudo. Textos do bot: Ajustes do Atendimento › Wwhat.
#  As respostas certas ficam só no servidor (nunca vão para a página).
# ══════════════════════════════════════════════════════════════════════════════
WWHAT_PADRAO = {
    "ativo": True,
    "saudacao": "Olá! 👋 Sou o assistente virtual da {empresa}. Para te atender com segurança, vou confirmar alguns dados do seu cadastro.",
    "pedir_cpf": "Digite o seu CPF (só os números).",
    "direcionando": "Pronto, {nome}! ✅ Dados confirmados. Estou te direcionando ao atendimento — escreva sua mensagem que um atendente já te responde.",
    "departamento": "CX", "motivo_pai": "",
}
COOKIE_AT = "cli_atend"
ETIQUETA_AT = "cliente-atend:"
HORAS_AT = 12
ERROS_AT = 2                    # erros na mesma conversa → o bot encerra (e o freio de CPF/IP continua contando)
_conversas = banco.por_empresa(dict)


def cfg_wwhat() -> dict:
    try:
        bruto = T.hub_cfg().get("wwhat") or {}
    except Exception:  # noqa: BLE001
        bruto = {}
    c = {**WWHAT_PADRAO, **{k: v for k, v in bruto.items() if v not in (None, "")}}
    c["ativo"] = bool(c.get("ativo"))
    return c


def _ck_at() -> str:
    return COOKIE_AT if banco.empresa_atual() == banco.PRINCIPAL else f"{COOKIE_AT}_{banco.empresa_atual()}"


def _assinar_at(corpo: str) -> str:
    return hmac.new(acesso.SEGREDO.encode(), (ETIQUETA_AT + corpo).encode(), hashlib.sha256).hexdigest()


def token_atendimento(cliente_id: str, cli: dict) -> str:
    corpo = _b64(json.dumps({"c": cliente_id, "i": _impressao(cli), "e": int(time.time() + HORAS_AT * 3600)}).encode())
    return corpo + "." + _assinar_at(corpo)


def token_visitante(codigo: str, nome: str) -> str:
    """Sem identificação (CPF não achado): só conversa, num chamado próprio com código de visitante (V…)."""
    corpo = _b64(json.dumps({"v": codigo, "n": nome, "e": int(time.time() + HORAS_AT * 3600)}).encode())
    return corpo + "." + _assinar_at(corpo)


LETRAS_V = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def codigo_visitante() -> str:
    import secrets
    T.BASE.atualizar()
    while True:
        cod = "V" + "".join(secrets.choice(LETRAS_V) for _ in range(5))
        if T._id_doc(cod) not in T.BASE.cont:
            return cod


def _cliente_do_link(request: Request) -> tuple[str, dict]:
    # cookie (normal) ou o mesmo token guardado no aparelho (alguns navegadores de app apagam o cookie ao fechar a aba)
    tk = request.cookies.get(_ck_at()) or request.headers.get("x-atend-token") or ""
    if "." not in tk:
        raise HTTPException(401, "Confirme seus dados para falar com a gente.")
    corpo, ass = tk.rsplit(".", 1)
    try:
        d = json.loads(_unb64(corpo)) if hmac.compare_digest(_assinar_at(corpo), ass) else {}
    except Exception:  # noqa: BLE001
        d = {}
    if not d or d.get("e", 0) < time.time():
        raise HTTPException(401, "Seu atendimento expirou. Confirme seus dados de novo.")
    if d.get("v"):   # visitante (sem identificação)
        return "", {"tipo": "visitante", "codigo": d["v"], "nome": f"{d.get('n') or 'Visitante'} · sem cadastro", "_primeiro": d.get("n") or ""}
    e = _erp()
    e.ST.carregar()
    cli = e.ST.dados["parceiros"].get(d.get("c") or "")
    if not cli or cli.get("tipo") != "cliente" or cli.get("ativo") is False or _impressao(cli) != d.get("i"):
        raise HTTPException(401, "Seu atendimento expirou. Confirme seus dados de novo.")
    return d["c"], cli


def _tpl(txt: str, **kw) -> str:
    for k, v in kw.items():
        txt = txt.replace("{" + k + "}", str(v or ""))
    return txt


def achar_por_cpf(doc: str) -> tuple[str, dict] | None:
    e = _erp()
    e.ST.carregar()
    for pid, c in e.ST.dados["parceiros"].items():
        if c.get("tipo") == "cliente" and c.get("ativo") is not False and T.digitos(c.get("doc")) == doc:
            return pid, c
    return None


_LIGACAO = {"de", "da", "do", "das", "dos", "e"}


def _endereco(cid: str, cli: dict) -> dict:
    end = cli.get("endereco") or {}
    if T.digitos(end.get("numero")) or end.get("bairro") or end.get("cep"):
        return end
    peds = sorted((p for p in _erp().ST.dados["pedidos"].values() if p.get("cliente_id") == cid and p.get("endereco")),
                  key=lambda p: str(p.get("criado_em") or ""), reverse=True)
    return (peds[0].get("endereco") if peds else {}) or {}


SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Pereira", "Costa", "Rodrigues", "Almeida", "Lima", "Gomes", "Ribeiro", "Carvalho",
              "Ferreira", "Martins", "Araújo", "Barbosa", "Rocha", "Dias", "Moreira", "Cardoso"]
BAIRROS = ["Centro", "Jardim América", "Vila Nova", "Boa Vista", "Santa Cruz", "Parque das Flores", "Jardim Paulista", "Vila Mariana",
           "São José", "Bela Vista"]
COMPLEMENTOS = ["Sem complemento", "Apto 12", "Casa 2", "Bloco B, apto 31", "Fundos", "Casa 1", "Apto 104", "Sala 3"]
DOMINIOS = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com.br", "icloud.com", "uol.com.br"]
_ultimas = banco.por_empresa(dict)   # CPF → perguntas da última validação (a próxima tenta outras)


def _mascara_email(e: str) -> str:
    u, _, d = str(e or "").strip().lower().partition("@")
    if not u or "." not in d:
        return ""
    nome, _, fim = d.partition(".")
    return f"{u[:2]}•••@{nome[:2]}•••.{fim}"


def _escolhas(rnd, certo: str, candidatos, genericos, proibidos=()) -> list[str] | None:
    """4 opções (1 certa + 3 de outros cadastros/lista padrão), nenhuma parecida com a certa."""
    fora = {T.norm(certo)} | {T.norm(x) for x in proibidos}
    vistos, outros = set(fora), []
    for x in list(dict.fromkeys(c for c in candidatos if c)) + [g for g in genericos if g]:
        if T.norm(x) not in vistos:
            vistos.add(T.norm(x))
            outros.append(x)
    reais = [x for x in outros if x not in genericos]
    pool = reais if len(reais) >= 3 else outros
    if len(pool) < 3:
        return None
    ops = rnd.sample(pool, 3) + [certo]
    rnd.shuffle(ops)
    return ops


def _datas_vizinhas(rnd, d: str) -> list[str]:
    import datetime as dt
    base = dt.date.fromisoformat(d)
    ops = set()
    while len(ops) < 3:
        try:
            x = base.replace(year=base.year + rnd.choice([-3, -2, -1, 0, 0, 1, 2, 3]), month=rnd.randint(1, 12), day=rnd.randint(1, 28))
        except ValueError:
            continue
        if x != base:
            ops.add(x.strftime("%d/%m/%Y"))
    return list(ops)


def perguntas_do_cliente(cid: str, cli: dict, sorteio=None, evitar=()) -> list[dict]:
    """Banco de perguntas com o que o ERP tem do cliente — TODAS respondidas com números:
    digitadas (nº da casa, 4 últimos do telefone, começo do CEP, dia/mês/ano de nascimento) e de múltipla escolha 1-4
    (produto comprado, bairro, sobrenome, e-mail mascarado, data de nascimento, complemento).
    Sorteia a ordem, uma pergunta por assunto (nunca duas de nascimento, por exemplo), e empurra para o fim as que o
    mesmo CPF respondeu na última validação."""
    import random
    rnd = sorteio or random.SystemRandom()
    e = _erp()
    outros_cli = [c for k, c in e.ST.dados["parceiros"].items() if k != cid and c.get("tipo") == "cliente"]
    end = _endereco(cid, cli)
    qs = []

    def dig(id_, grupo, texto, certo, zeros=False):
        qs.append({"id": id_, "grupo": grupo, "texto": texto, "modo": "digitos", "certo": certo.lstrip("0") if zeros else certo, "zeros": zeros})

    def esc_(id_, grupo, texto, certo, candidatos, genericos=(), proibidos=()):
        ops = _escolhas(rnd, certo, candidatos, list(genericos), proibidos)
        if ops:
            qs.append({"id": id_, "grupo": grupo, "texto": texto, "modo": "opcao", "opcoes": ops, "certo": str(ops.index(certo) + 1)})

    if T.digitos(end.get("numero")):
        dig("numero", "numero", "Qual é o número da sua casa no endereço de entrega?", T.digitos(end.get("numero")), zeros=True)
    tel = T.digitos(cli.get("telefone"))
    if len(tel) >= 8:
        dig("telefone", "telefone", "Quais são os 4 últimos números do seu telefone cadastrado?", tel[-4:])
    cep = T.digitos(end.get("cep"))
    if len(cep) == 8:
        dig("cep", "cep", "Quais são os 5 primeiros números do CEP de entrega?", cep[:5])
    nasc = str(cli.get("nascimento") or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", nasc):
        a, m, d = nasc.split("-")
        dig("nasc_dia", "nascimento", "Qual é o DIA do seu nascimento? (só o número)", d, zeros=True)
        dig("nasc_mes", "nascimento", "Qual é o MÊS do seu nascimento? (número de 1 a 12)", m, zeros=True)
        dig("nasc_ano", "nascimento", "Qual é o ANO do seu nascimento? (os 4 números)", a)
        certo = f"{d}/{m}/{a}"
        ops = _datas_vizinhas(rnd, nasc) + [certo]
        rnd.shuffle(ops)
        qs.append({"id": "nasc_data", "grupo": "nascimento", "texto": "Qual é a sua data de nascimento?", "modo": "opcao", "opcoes": ops,
                   "certo": str(ops.index(certo) + 1)})
    prods = e.ST.dados.get("produtos") or {}
    comprados = sorted({str((prods.get(i.get("produto_id")) or {}).get("nome") or "").strip()
                        for p in e.ST.dados["pedidos"].values() if p.get("cliente_id") == cid and p.get("status") not in (None, "rascunho", "cancelado")
                        for i in (p.get("itens") or [])} - {""})
    if comprados:
        esc_("produto", "produto", "Dos itens abaixo, qual produto você comprou?", rnd.choice(comprados),
             [str(v.get("nome") or "").strip() for v in prods.values()], proibidos=comprados)
    if str(end.get("bairro") or "").strip():
        esc_("bairro", "bairro", "Qual é o seu bairro?", str(end["bairro"]).strip(),
             [str((c.get("endereco") or {}).get("bairro") or "").strip() for c in outros_cli], BAIRROS)
    sobrenomes = [x for x in str(cli.get("nome") or "").split()[1:] if len(x) >= 3 and T.norm(x) not in _LIGACAO]
    if sobrenomes:
        esc_("sobrenome", "nome", "Qual é o seu sobrenome?", sobrenomes[-1].capitalize(),
             [str(c.get("nome") or "").split()[-1].capitalize() for c in outros_cli if len(str(c.get("nome") or "").split()) > 1], SOBRENOMES,
             proibidos=sobrenomes)
    if _mascara_email(cli.get("email")):
        # e-mails falsos inventados (nunca o e-mail de outro cliente), no mesmo formato da máscara
        falsos = [_mascara_email("".join(rnd.choice("abcdefghijlmnoprstuv") for _ in range(6)) + "@" + rnd.choice(DOMINIOS)) for _ in range(8)]
        esc_("email", "email", "Qual destes é o seu e-mail?", _mascara_email(cli.get("email")), [f for f in falsos if f])
    compl = str(end.get("complemento") or "").strip() or "Sem complemento"
    if T.digitos(end.get("numero")) or end.get("bairro"):   # com endereço, pergunta mesmo sem complemento ("Sem complemento" é a certa)
        esc_("complemento", "complemento", "Qual é o complemento do seu endereço?", compl,
             [str((c.get("endereco") or {}).get("complemento") or "").strip() for c in outros_cli], COMPLEMENTOS)
    rnd.shuffle(qs)
    qs.sort(key=lambda q: q["id"] in evitar)   # as da última vez ficam para o fim
    fila, grupos = [], set()
    for q in qs:
        if q["grupo"] not in grupos:
            grupos.add(q["grupo"])
            fila.append(q)
    return fila


def resposta_confere(q: dict, resposta: str) -> bool:
    r = T.digitos(resposta)
    if q["modo"] == "digitos":
        r = r.lstrip("0") if q.get("zeros") else r
        return bool(r) and hmac.compare_digest(r, q["certo"])
    if q["modo"] == "opcao":
        if not r:   # tocou/escreveu o texto da opção
            r = next((str(i + 1) for i, o in enumerate(q["opcoes"]) if T.norm(o) == T.norm(resposta)), "")
        return r == q["certo"]
    return False


def em_atendimento(cid: str, cli: dict) -> dict | None:
    """Chat já aberto com a central (do link OU do app): quem validar de novo — no mesmo aparelho ou em outro —
    continua NESSA conversa. Um chat por cliente."""
    ativo = chat_ativo(tickets_do_cliente(cid, cli))
    if not ativo:
        return None
    dono = ativo.get("atribuido_para") or (ativo.get("atendentes") or [""])[0]
    nome = ((T.usuarios().get(dono) or {}).get("nome") or "") if dono else ""
    return {"id": ativo["id"].split("#")[-1], "atendente": _primeiro_nome(nome), "_tid": ativo["id"]}


def _avisar_entrada(info: dict, cli: dict):
    """Nota só para a central: alguém validou de novo e entrou na conversa que já estava aberta."""
    me = {"usuario": "bot-link", "nome": "Assistente do link"}
    T._mutar_sol(info["_tid"], lambda s: T._coment(s, me, "🔗 Entrou de novo pelo link de atendimento (CPF validado — pode ser outro aparelho "
                                                        "ou outra pessoa da casa). A conversa continua aqui.", interno=True, tipo="sistema"), me)


def _publica(q: dict) -> dict:
    return {"texto": q["texto"], **({"opcoes": q["opcoes"]} if q.get("modo") == "opcao" else {})}


def _limpar_conversas():
    agora = time.time()
    for k in [k for k, v in _conversas.items() if v["exp"] < agora]:
        _conversas.pop(k, None)


@router.get("/atendimento", include_in_schema=False)
def _at_sem_barra():
    return RedirectResponse(banco.prefixo_publico() + "/atendimento/", status_code=307)


@router.get("/atendimento/", include_in_schema=False)
def pagina_atendimento():
    return FileResponse(Path(__file__).parent / "static" / "atendimento" / "index.html", media_type="text/html; charset=utf-8", headers=SEM_CACHE)


@router.get("/atendimento/manifest.webmanifest", include_in_schema=False)
def manifesto_atendimento():
    return acesso.manifesto_publico(Path(__file__).parent / "static" / "atendimento" / "manifest.webmanifest", "/atendimento/")


@router.get("/atendimento/sw.js", include_in_schema=False)
def sw_atendimento():
    """Só para as notificações do link (a central chamando). Escopo: /atendimento/."""
    return FileResponse(Path(__file__).parent / "static" / "atendimento" / "sw.js", media_type="application/javascript",
                        headers={**SEM_CACHE, "Service-Worker-Allowed": banco.prefixo_publico() + "/atendimento/"})


@router.post("/api/cliente/atendimento/push")
async def at_push(request: Request):
    """O celular aceitou ser avisado: a central chamando (botão Chamar do CX/ERP) abre o link de atendimento."""
    _cid, cli = _cliente_do_link(request)
    d = await request.json()
    import promocoes
    promocoes.guardar_inscricao(str(cli.get("codigo") or "").upper(), cli.get("_primeiro") or cli.get("nome") or "", d.get("inscricao") or {},
                                url=banco.prefixo_publico() + "/atendimento/")
    return {"ok": True}


@router.get("/api/cliente/atendimento/info")
def at_info(request: Request):
    w, c = cfg_wwhat(), cfg_app()
    nome, visitante, cont = "", False, None
    try:
        cid, cli = _cliente_do_link(request)
        visitante = cli.get("tipo") == "visitante"
        nome = _primeiro_nome(cli["_primeiro"] if visitante else cli.get("nome")) or "Visitante"
        cont = em_atendimento(cid, cli)
    except HTTPException:
        pass
    emp = c.get("empresa") or "Central do Cliente"
    return {"ativo": w["ativo"] and bool(c.get("ativo")), "empresa": emp, "saudacao": _tpl(w["saudacao"], empresa=emp, nome=""),
            "pedir_cpf": w["pedir_cpf"], "validado": bool(nome), "nome": nome, "visitante": visitante,
            "continua": {k: v for k, v in cont.items() if not k.startswith("_")} if cont else None,
            "direcionando": _tpl(w["direcionando"], nome=nome, empresa=emp) if nome else ""}


@router.post("/api/cliente/atendimento/cpf")
async def at_cpf(request: Request):
    w, c = cfg_wwhat(), cfg_app()
    if not (w["ativo"] and c.get("ativo")):
        raise HTTPException(503, "O atendimento por aqui está pausado. Tente mais tarde.")
    if not T.configurado():
        raise HTTPException(503, "Sistema em manutenção. Tente mais tarde.")
    d = await request.json()
    doc = T.digitos(d.get("cpf"))
    ip = "ip:" + _ip(request)
    if _bloqueado(ip, LIMITE_IP) or (doc and _bloqueado("doc:" + doc, LIMITE_DOC)):
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    if not doc_valido(doc):
        raise HTTPException(422, "Esse CPF parece incompleto ou errado. Confira e digite de novo (só os números).")
    achado = achar_por_cpf(doc)
    if not achado:
        _falhou(ip, "doc:" + doc)
        raise HTTPException(404, "Não encontrei um cadastro com esse CPF. Confira os números ou fale com a loja onde você comprou.")
    cid, cli = achado
    import cliente_acesso
    if cliente_acesso.validacao_travada(cid):
        raise HTTPException(429, "Por segurança, a validação deste CPF está travada por 24 horas (3 tentativas erradas). "
                                 "Se precisar antes, fale com a loja onde você comprou.")
    fila = perguntas_do_cliente(cid, cli, evitar=_ultimas.get(doc) or ())
    if len(fila) < 2:
        raise HTTPException(409, "Não consigo confirmar seus dados por aqui — o cadastro está incompleto. Fale com a loja onde você comprou.")
    _limpar_conversas()
    conv = hashlib.sha256(f"{time.time_ns()}|{doc}|{acesso.SEGREDO}".encode()).hexdigest()[:32]
    _conversas[conv] = {"cid": cid, "doc": doc, "fila": fila[1:], "atual": fila[0], "acertos": 0, "erros": 0, "exp": time.time() + 900}
    return {"conversa": conv, "pergunta": _publica(fila[0]), "passo": 1, "total": 2}


@router.post("/api/cliente/atendimento/resposta")
async def at_resposta(request: Request):
    d = await request.json()
    _limpar_conversas()
    cv = _conversas.get(str(d.get("conversa") or ""))
    if not cv:
        raise HTTPException(410, "Essa conversa expirou. Vamos começar de novo — digite o seu CPF.")
    ip = "ip:" + _ip(request)
    if _bloqueado(ip, LIMITE_IP) or _bloqueado("doc:" + cv["doc"], LIMITE_DOC):
        _conversas.pop(str(d.get("conversa")), None)
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    cv.setdefault("feitas", []).append(cv["atual"]["id"])
    _ultimas[cv["doc"]] = cv["feitas"][-4:]
    if len(_ultimas) > 20000:
        _ultimas.clear()
    if resposta_confere(cv["atual"], d.get("resposta")):
        cv["acertos"] += 1
        if cv["acertos"] >= 2:
            _conversas.pop(str(d.get("conversa")), None)
            e = _erp()
            cli = e.ST.dados["parceiros"].get(cv["cid"]) or {}
            if not str(cli.get("codigo") or "").strip():   # o código do cliente liga o chat aos Tickets
                with e.ST.trava:
                    tx = e.Tx({"login": "atendimento-link"})
                    e.garantir_codigo(tx, cv["cid"])
                    tx.commit()
                cli = e.ST.dados["parceiros"][cv["cid"]]
            nome = _primeiro_nome(cli.get("nome"))
            import cliente_acesso
            cliente_acesso.validou(cv["cid"], cli)
            cont = em_atendimento(cv["cid"], cli)
            if cont:
                _avisar_entrada(cont, cli)
            tk = token_atendimento(cv["cid"], cli)
            resp = JSONResponse({"ok": True, "validado": True, "nome": nome, "tk": tk,
                                 "continua": {k: v for k, v in cont.items() if not k.startswith("_")} if cont else None,
                                 "direcionando": _tpl(cfg_wwhat()["direcionando"], nome=nome, empresa=cfg_app().get("empresa"))})
            resp.set_cookie(_ck_at(), tk, httponly=True, samesite="lax", secure=_https(request), max_age=HORAS_AT * 3600, path="/")
            return resp
        if not cv["fila"]:
            _conversas.pop(str(d.get("conversa")), None)
            return {"ok": False, "fim": True, "msg": "Não consegui confirmar seus dados por aqui. Fale com a loja onde você comprou."}
        cv["atual"] = cv["fila"].pop(0)
        return {"ok": True, "pergunta": _publica(cv["atual"]), "passo": 2, "total": 2}
    cv["erros"] += 1
    _falhou(ip, "doc:" + cv["doc"])
    if cv["erros"] >= ERROS_AT or not cv["fila"]:
        _conversas.pop(str(d.get("conversa")), None)
        import cliente_acesso
        cliente_acesso.falhou_validacao(cv["cid"])
        return {"ok": False, "fim": True, "msg": "Não consegui confirmar seus dados. Por segurança, encerrei a validação. "
                                                 "Tente de novo mais tarde ou fale com a loja onde você comprou."}
    cv["atual"] = cv["fila"].pop(0)
    return {"ok": False, "msg": "Hmm, essa resposta não confere com o cadastro. Vamos tentar outra:", "pergunta": _publica(cv["atual"]),
            "passo": cv["acertos"] + 1, "total": 2}


@router.post("/api/cliente/atendimento/visitante")
async def at_visitante(request: Request):
    """CPF não achado depois das tentativas: segue para o atendimento SEM identificação (só pede o nome).
    Não vê nada do ERP — é só uma conversa com a central, num chamado de visitante."""
    w, c = cfg_wwhat(), cfg_app()
    if not (w["ativo"] and c.get("ativo")):
        raise HTTPException(503, "O atendimento por aqui está pausado. Tente mais tarde.")
    d = await request.json()
    nome = re.sub(r"[^\wÀ-ÿ' .-]", "", str(d.get("nome") or "")).strip()[:40]
    if len(nome) < 2:
        raise HTTPException(422, "Me diga seu nome para eu te apresentar ao atendente.")
    _freio_msg("visitante:" + _ip(request), maximo=5, janela=3600)
    nome = " ".join(x.capitalize() for x in nome.split())
    tk = token_visitante(codigo_visitante(), nome)
    resp = JSONResponse({"ok": True, "nome": nome.split(" ")[0], "tk": tk,
                         "direcionando": f"Prazer, {nome.split(' ')[0]}! 😊 Estou te direcionando ao atendimento — escreva sua mensagem que um atendente já te responde."})
    resp.set_cookie(_ck_at(), tk, httponly=True, samesite="lax", secure=_https(request), max_age=HORAS_AT * 3600, path="/")
    return resp


@router.get("/api/cliente/atendimento/chat")
def at_chat(request: Request):
    cid, cli = _cliente_do_link(request)
    T.BASE.atualizar()
    ativo = chat_ativo(tickets_do_cliente(cid, cli))
    return {"nome": _primeiro_nome(cli.get("_primeiro") or cli.get("nome")), "ativo": bool(ativo), "id": ativo["id"].split("#")[-1] if ativo else "",
            "mensagens": mensagens_publicas(ativo)[-80:] if ativo else [], "versao": T.BASE.ver}


@router.post("/api/cliente/atendimento/mensagem")
async def at_mensagem(request: Request):
    cid, cli = _cliente_do_link(request)
    if not (cfg_wwhat()["ativo"] and cfg_app().get("ativo")):
        raise HTTPException(503, "O atendimento por aqui está pausado. Tente mais tarde.")
    return _chat_do_cliente(cid, cli, await request.json(), via="link_sem_id" if cli.get("tipo") == "visitante" else "link")


@router.get("/api/cliente/atendimento/anexo/{aid}")
def at_anexo(aid: str, request: Request):
    cid, cli = _cliente_do_link(request)
    import anexos as A
    doc = A.ler(aid)
    if not cli.get("codigo") or doc.get("cont") != T._id_doc(cli["codigo"]):
        raise HTTPException(404, "Anexo não encontrado.")
    return A.resposta(doc)


@router.post("/api/cliente/atendimento/sair")
def at_sair():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(_ck_at(), path="/")
    return resp


import cliente_acesso  # noqa: E402,F401  — registra as rotas do acesso seguro (senha, aparelhos) neste router
