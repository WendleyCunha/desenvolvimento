"""
hub/cliente_app.py — APP DO CLIENTE (Central do Cliente) · página pública em /cliente/
─────────────────────────────────────────────────────────────────────────────
Link geral para os clientes:  https://<seu-hub>/cliente/   (instalável como app)

  • Entrada: CPF (ou CNPJ) + e-mail. Confere no cadastro de clientes do ERP
    (erp_parceiros: tipo=cliente, doc, email). Se o cliente ainda não tem
    código, o código (6 caracteres) é criado na hora — o mesmo dos Tickets.
  • URA: menu de autoatendimento (pedidos, prazo de entrega, chamados) e
    "falar com a central", que abre um chamado com motivo/setor já definidos.
  • Pedidos: status em linguagem de cliente, data e janela da entrega,
    tentativas, itens. Rascunhos e dados internos (custo, histórico com login
    de funcionário, observações) NÃO saem daqui.
  • Chamados: os do cliente (abertos pelo app OU pela central). O cliente vê
    só o que é público: a abertura feita por ele e as mensagens com
    interno=False (as dele e as "Responder no app" da central). Notas internas,
    pendências entre setores e registros do sistema ficam escondidos.
  • Chat: a mensagem do cliente vira um comentário do próprio ticket
    (tipo "cliente", interno=False) — a central responde no mesmo lugar.

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
from datetime import datetime
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

# Menu da URA (Ajustes do Atendimento podem trocar em config/tickets_hub → app_cliente.ura)
URA_PADRAO = [
    {"id": "entrega", "rotulo": "Entrega e agendamento", "descricao": "Data, reagendar, endereço", "motivo_pai": "Logística", "departamento": "Logística"},
    {"id": "troca", "rotulo": "Troca, defeito ou avaria", "descricao": "Produto com problema ou diferente", "motivo_pai": "Pedido", "departamento": "CX"},
    {"id": "cancelar", "rotulo": "Cancelamento", "descricao": "Desistir do pedido", "motivo_pai": "Pedido", "departamento": "CX"},
    {"id": "cadastro", "rotulo": "Atualizar meus dados", "descricao": "Telefone, endereço, documentos", "motivo_pai": "Cliente", "departamento": "CX"},
    {"id": "outro", "rotulo": "Outro assunto", "descricao": "Fale com a central", "motivo_pai": "", "departamento": "CX"},
]
APP_PADRAO = {"ativo": True, "empresa": "Central do Cliente",
              "saudacao": "Olá! Sou o atendimento automático. Escolha uma opção:", "ura": URA_PADRAO,
              "max_chamados_dia": 5}

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
        raise HTTPException(401, "Entre com seu CPF e e-mail.")
    e = _erp()
    e.ST.carregar()
    cli = e.ST.dados["parceiros"].get(d.get("c") or "")
    if not cli or cli.get("tipo") != "cliente" or cli.get("ativo") is False or _impressao(cli) != d.get("i"):
        raise HTTPException(401, "Sua sessão expirou. Entre de novo.")
    return d["c"], cli


def _https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"


# ── freio contra tentativa de adivinhar CPF/e-mail ───────────────────────────
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
    return {"ativo": bool(c.get("ativo")), "empresa": c.get("empresa")}


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
    achado = achar_cliente(doc, email)
    if not achado:
        _falhou(ip, "doc:" + doc)
        raise HTTPException(401, "Não encontramos um cadastro com esse CPF e e-mail. Use o e-mail informado na compra "
                                 "ou fale com a loja para atualizar seu cadastro.")
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


def mensagens_publicas(t: dict) -> list[dict]:
    """Só o que o cliente pode ver. Comentário sem 'interno' explícito = interno (seguro)."""
    msgs = []
    if t.get("origem") == "app" and t.get("descricao"):
        msgs.append({"de": "cliente", "texto": t["descricao"], "data": t.get("criado_em")})
    for c in t.get("comentarios") or []:
        if c.get("interno") is not False:
            continue
        de = "cliente" if c.get("tipo") == "cliente" else "central"
        msgs.append({"de": de, "autor": "" if de == "cliente" else _primeiro_nome(c.get("autor")), "texto": c.get("texto", ""), "data": c.get("data")})
    return msgs


def resumo_cliente(t: dict) -> dict:
    msgs = mensagens_publicas(t)
    ult = msgs[-1] if msgs else None
    st = t.get("status")
    return {"id": t["id"].split("#")[-1], "assunto": t.get("assunto") or "Atendimento", "status": st, "rotulo": TK_ST.get(st, st),
            "aberto": st in T.ABERTOS, "pode_escrever": st in T.ABERTOS or st == "resolvido",
            "criado_em": t.get("criado_em"), "atualizado_em": t.get("atualizado_em"), "pedido": t.get("erp_pedido_numero"),
            "n_msgs": len(msgs), "ultima": ({"de": ult["de"], "texto": ult["texto"][:140], "data": ult["data"]} if ult else None),
            "resposta_nova_em": next((m["data"] for m in reversed(msgs) if m["de"] == "central"), None)}


def _ticket_do_cliente(cid: str, cli: dict, sid: str) -> dict:
    sid = str(sid or "")
    t = next((x for x in tickets_do_cliente(cid, cli) if x["id"].split("#")[-1] == sid), None)
    if not t:
        raise HTTPException(404, "Chamado não encontrado.")
    return t


@router.get("/api/cliente/eu")
def eu(request: Request):
    cid, cli = _cliente_da_sessao(request)
    c = cfg_app()
    todos = sorted(tickets_do_cliente(cid, cli), key=lambda t: str(t.get("atualizado_em") or ""), reverse=True)
    ts = [x for x in todos if x.get("status") in T.ABERTOS] + [x for x in todos if x.get("status") not in T.ABERTOS][:20]
    return {"nome": _primeiro_nome(cli.get("nome")), "nome_completo": cli.get("nome"), "codigo": cli.get("codigo"),
            "empresa": c.get("empresa"), "saudacao": c.get("saudacao"),
            "ura": [{k: u.get(k) for k in ("id", "rotulo", "descricao")} for u in c["ura"]],
            "pedidos": pedidos_do_cliente(cid), "chamados": [resumo_cliente(t) for t in ts], "versao": T.BASE.ver}


@router.get("/api/cliente/novidades")
def novidades(request: Request):
    """Barato: o app chama a cada ~15 s com a tela aberta. Só diz se algo mudou."""
    _cliente_da_sessao(request)
    T.BASE.atualizar()
    return {"versao": T.BASE.ver}


@router.get("/api/cliente/chamado/{sid}")
def chamado(sid: str, request: Request):
    cid, cli = _cliente_da_sessao(request)
    t = _ticket_do_cliente(cid, cli, sid)
    return {**resumo_cliente(t), "mensagens": mensagens_publicas(t)}


def _me(cli: dict) -> dict:
    return {"usuario": "cliente:" + str(cli.get("codigo") or ""), "nome": cli.get("nome") or "Cliente", "depto": "", "hub": ""}


def _msg_cliente(s: dict, me: dict, texto: str):
    s.setdefault("comentarios", []).append({"autor": me["nome"], "usuario": me["usuario"], "texto": texto, "data": T.agora(),
                                            "interno": False, "tipo": "cliente", "via": "app"})
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


@router.post("/api/cliente/chamado/{sid}/mensagem")
async def mensagem(sid: str, request: Request):
    cid, cli = _cliente_da_sessao(request)
    t = _ticket_do_cliente(cid, cli, sid)
    d = await request.json()
    texto = _texto(d)
    if not (t.get("status") in T.ABERTOS or t.get("status") == "resolvido"):
        raise HTTPException(409, "Este chamado foi encerrado. Abra um novo pelo menu.")
    _freio_msg("cli:" + cid)
    me = _me(cli)
    T._mutar_sol(t["id"], lambda s: _msg_cliente(s, me, texto), me)
    return {"ok": True}


@router.post("/api/cliente/chamados")
async def abrir_chamado(request: Request):
    """Opção da URA + texto (+ pedido). Se já houver um chamado aberto do mesmo assunto,
    a mensagem entra nele (o cliente não espalha o mesmo problema em vários tickets)."""
    cid, cli = _cliente_da_sessao(request)
    c = cfg_app()
    d = await request.json()
    texto = _texto(d)
    op = next((u for u in c["ura"] if u.get("id") == d.get("opcao")), None)
    if not op:
        raise HTTPException(422, "Escolha um assunto.")
    e = _erp()
    ped_id = str(d.get("pedido_id") or "")
    ped = e.ST.dados["pedidos"].get(ped_id) if ped_id else None
    if ped_id and (not ped or ped.get("cliente_id") != cid):
        raise HTTPException(404, "Pedido não encontrado.")
    me = _me(cli)
    abertos = [t for t in tickets_do_cliente(cid, cli) if t.get("status") in T.ABERTOS and t.get("origem") == "app"
               and t.get("app_opcao") == op["id"] and (t.get("erp_pedido_id") or "") == ped_id]
    if abertos:
        alvo = abertos[0]
        _freio_msg("cli:" + cid)
        T._mutar_sol(alvo["id"], lambda s: _msg_cliente(s, me, texto), me)
        return {"ok": True, "id": alvo["id"].split("#")[-1], "existente": True}
    hoje = T.agora()[:10]
    n_hoje = sum(1 for t in tickets_do_cliente(cid, cli) if t.get("origem") == "app" and str(t.get("criado_em") or "")[:10] == hoje)
    if n_hoje >= int(c.get("max_chamados_dia") or 5):
        raise HTTPException(429, "Você já abriu vários chamados hoje. Continue a conversa em um deles.")
    _freio_msg("cli:" + cid)
    pai = op.get("motivo_pai") if op.get("motivo_pai") in T.motivos() else ""
    deps = T.departamentos()
    depto = op.get("departamento") if op.get("departamento") in deps else (T.hub_cfg().get("depto_erp") or (deps[0] if deps else ""))
    dados = {"assunto": op["rotulo"] + (f" · pedido #{ped.get('numero')}" if ped else ""), "descricao": texto,
             "departamento": depto, "categoria": depto, "motivo_pai": pai, "motivo_pai_id": pai, "motivo_filho": "",
             "sla1_prazo_dias": T._sla_motivo(pai, "") if pai else (T.hub_cfg().get("sla_erp_dias") or 1),
             "prioridade": "normal", "cliente_nome": cli.get("nome", ""), "cliente_telefone": cli.get("telefone", ""),
             "solicitante_nome": cli.get("nome", ""), "aberto_por": me["usuario"], "origem": "app", "app_opcao": op["id"],
             "erp_cliente_id": cid, "app_pendente": True, "app_pendente_desde": T.agora(),
             "ultima_interacao_autor": me["usuario"], "cliente_codigo": cli.get("codigo")}
    if ped:
        dados.update(erp_pedido_id=ped_id, erp_pedido_numero=ped.get("numero"))
    tid = T.criar_solicitacao({k: v for k, v in dados.items() if v not in (None, "")}, me)
    return {"ok": True, "id": tid.split("#")[-1], "existente": False}
