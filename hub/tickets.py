"""
hub/tickets.py — API do módulo TICKETS (atendimento) no hub.
─────────────────────────────────────────────────────────────────────────────
Lê e grava OS MESMOS tickets do wendleysite (Streamlit · mod_tickets.py), que
ficam no Firestore do projeto **bancowendley** — por isso usa uma credencial
própria (env var FIRESTORE_CREDS_TICKETS no Render), separada da do hub.

Modelo (igual ao tickets/common.py do Streamlit — os dois sistemas convivem):
    tickets/{cliente_codigo}      um "container" por cliente
        cliente_codigo, cliente_nome, criado_em, atualizado_em ("AAAA-MM-DD HH:MM:SS" BRT)
        solicitacoes: [ {sid, status, prioridade, assunto, descricao, departamento,
                         motivo_pai, motivo_filho, etapa_atual, sla1_prazo_dias,
                         horas_sla, etapa_vermelha, etapa_data_prevista, etapa_travada,
                         atendentes[], atribuido_para, aberto_por, comentarios[],
                         historico_etapas[], solicitacoes_setor[], ...} ]
    id do ticket na tela = "{container}#{sid}"
    config/motivos_central  {"ticket": {Pai: {Filho: {sla, etapas[], ativo}}}}
    config/departamentos    {"lista": [...]}
    usuarios/{login}        {nome, depto, ...}   (só nome e depto saem daqui)
    config/tickets_hub      ajustes do hub: mapa de usuários, ticket automático do ERP

PONTE COM O ERP (hub/erp.py — banco do hub):
  • no ticket: pedidos do cliente no ERP (código do cliente, telefone ou nome),
    agendar/reagendar (API do ERP), gerar troca;
  • no ERP: tickets do pedido, "Abrir ticket", e ticket AUTOMÁTICO quando a
    baixa da entrega é avaria / recusa / ausência (ligável em Ajustes).

Cota grátis: todos os containers em memória; a cada 20 s (só com a tela aberta)
busca apenas os que mudaram (atualizado_em > último visto); leitura completa a
cada 30 min. Toda escrita é transação no container (igual ao Streamlit).
"""
from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

import acesso
import banco

router = APIRouter(prefix="/api/tickets")
MOD = "tickets"
BRT = timezone(timedelta(hours=-3))
COL_STREAMLIT, COL_HUB = "tickets", "hub_tickets"


def col() -> str:
    return COL_STREAMLIT if banco_proprio() else COL_HUB


def doc_cfg(nome: str):
    """config/{nome} no bancowendley · hub_tickets_config/{nome} no banco do hub."""
    return db().collection("config" if banco_proprio() else "hub_tickets_config").document(nome)
ABERTOS = ("aberto", "em_andamento", "aguardando")
STATUS = ["aberto", "em_andamento", "aguardando", "resolvido", "finalizado", "cancelado"]
PRIORIDADES = ["urgente", "alta", "normal", "baixa"]
# Motivos e setores de partida (os mesmos do Concierge) — só quando roda no banco do hub
MOTIVOS_PADRAO = {
    "Pedido": {f: {"sla": 2, "ativo": True, "etapas": ["Apurar", "Aguardando cliente", "Aguardando liberação", "Resolvido com o cliente"]}
               for f in ["Cancelamento", "Arrependimento", "Produto Incorreto", "Alterar Pedido", "Troca Adaptação", "Devolução Adaptação"]},
    "Compras": {f: {"sla": 3, "ativo": True, "etapas": ["Apurar", "Aguardando fornecedor", "Aguardando estoque"]}
                for f in ["Bloqueio de estoque", "Falta de Peças", "Assistência Técnica"]},
    "Logística": {f: {"sla": 2, "ativo": True, "etapas": ["Apurar", "Agendamento", "Reenvio", "Aguardando transportadora"]}
                  for f in ["Descumprimento Entrega", "Rastreio Cotação", "Danos à Residência", "Montagem", "Avaria na entrega",
                            "Entrega recusada", "Cliente ausente"]},
    "Cliente": {f: {"sla": 1, "ativo": True, "etapas": ["Apurar", "Aguardando cliente"]} for f in ["Reenvio", "Atualizar Cadastro", "Envio de Documentos"]},
}
DEPARTAMENTOS_PADRAO = ["CX", "Logística", "Compras", "Financeiro", "TI", "Jurídico", "Manutenção"]
CONFIG_PADRAO = {"mapa_usuarios": {}, "auto_erp": {"avaria": True, "recusado": True, "ausente": False},
                 "depto_erp": "CX", "motivo_pai_erp": "Pedido", "sla_erp_dias": 2}


# ══════════════════════════════════════════════════════════════════════════════
# util
# ══════════════════════════════════════════════════════════════════════════════
def agora() -> str:
    return datetime.now(BRT).strftime("%Y-%m-%d %H:%M:%S")


def _dt(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace(" ", "T")[:19]).replace(tzinfo=BRT)
    except (ValueError, TypeError):
        return None


def norm(t) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(c) != "Mn").lower().split())


def digitos(t) -> str:
    return re.sub(r"\D", "", str(t or ""))


def _sid() -> str:
    return uuid.uuid4().hex[:10]


def _id_doc(cod: str) -> str:
    cod = (cod or "").strip().replace("/", "_").replace("#", "_")
    return cod[:200] or ("cliente_" + _sid())


def compor(cid: str, sid: str) -> str:
    return f"{cid}#{sid}"


def decompor(tid: str) -> tuple[str, str]:
    tid = str(tid or "")
    if "#" not in tid:
        return tid, "legacy"
    cid, sid = tid.rsplit("#", 1)
    return cid, sid


def normalizar_container(raw: dict | None) -> dict:
    if not raw:
        return {"cliente_codigo": "", "cliente_nome": "", "solicitacoes": []}
    if isinstance(raw.get("solicitacoes"), list):
        return raw
    leg = dict(raw)
    leg.setdefault("sid", "legacy")
    return {"cliente_codigo": raw.get("cliente_codigo", ""), "cliente_nome": raw.get("cliente_nome", ""),
            "criado_em": raw.get("criado_em", ""), "atualizado_em": raw.get("atualizado_em", ""), "solicitacoes": [leg]}


# ── SLA (mesma regra do tickets/common.py) ──────────────────────────────────
def deadline(t: dict) -> tuple[datetime | None, str]:
    if t.get("etapa_vermelha") and t.get("etapa_data_prevista"):
        try:
            d = datetime.fromisoformat(str(t["etapa_data_prevista"])[:10])
            return d.replace(hour=23, minute=59, second=59, tzinfo=BRT), "etapa"
        except ValueError:
            pass
    ini = _dt(t.get("criado_em"))
    if not ini:
        return None, "pai"
    if t.get("sla1_prazo_dias") not in (None, ""):
        try:
            return ini + timedelta(days=float(t["sla1_prazo_dias"])), "pai"
        except (TypeError, ValueError):
            pass
    try:
        horas = float(t.get("horas_sla", 24) or 24)
    except (TypeError, ValueError):
        horas = 24
    return ini + timedelta(hours=horas), "pai"


def sla_info(t: dict, agora_dt: datetime | None = None) -> dict:
    agora_dt = agora_dt or datetime.now(BRT)
    lim, origem = deadline(t)
    if not lim:
        return {"estado": "ok", "limite": "", "origem": origem, "min": None}
    resta = (lim - agora_dt).total_seconds() / 60
    if t.get("status") not in ABERTOS:
        fim = _dt(t.get("atualizado_em"))
        return {"estado": "perdido" if fim and fim > lim else "cumprido", "limite": lim.strftime("%Y-%m-%d %H:%M"), "origem": origem, "min": None}
    estado = "venc" if resta <= 0 else ("hoje" if lim.date() == agora_dt.date() else ("warn" if resta <= 30 else "ok"))
    return {"estado": estado, "limite": lim.strftime("%Y-%m-%d %H:%M"), "origem": origem, "min": round(resta)}


# ══════════════════════════════════════════════════════════════════════════════
# BANCO (bancowendley) — credencial própria
# ══════════════════════════════════════════════════════════════════════════════
_db = None
_trava_db = threading.Lock()


def banco_proprio() -> bool:
    """True = usa o bancowendley (tickets do Streamlit). False = usa o banco do próprio hub."""
    return bool(os.environ.get("FIRESTORE_CREDS_TICKETS", "").strip())


def configurado() -> bool:
    return banco_proprio() or banco.configurado()


def db():
    """Com FIRESTORE_CREDS_TICKETS → bancowendley (mesmos tickets do Streamlit).
    Sem ela → banco do próprio hub (o módulo já funciona; dá para trocar depois)."""
    global _db
    if not banco_proprio():
        return banco.db()
    if _db is None:
        with _trava_db:
            if _db is None:
                bruto = os.environ.get("FIRESTORE_CREDS_TICKETS", "").strip()
                from google.cloud import firestore
                from google.oauth2 import service_account
                info = banco.ler_credenciais(bruto)
                cred = service_account.Credentials.from_service_account_info(info)
                _db = firestore.Client(credentials=cred, project=info["project_id"])
    return _db


def _transacao(cid: str, mutar):
    """Lê o container, aplica `mutar(container)` e grava — numa transação do
    Firestore (o Streamlit pode estar escrevendo no mesmo cliente)."""
    ref = db().collection(col()).document(cid)
    if hasattr(db(), "transaction"):
        from google.cloud import firestore as fs
        tr = db().transaction()

        @fs.transactional
        def _tx(tr):
            snap = ref.get(transaction=tr)
            cont = normalizar_container(snap.to_dict() if snap.exists else None)
            res = mutar(cont)
            tr.set(ref, cont)
            return cont, res
        cont, res = _tx(tr)
    else:   # banco simulado nos testes
        snap = ref.get(timeout=banco.TIMEOUT)
        cont = normalizar_container(snap.to_dict() if snap.exists else None)
        res = mutar(cont)
        ref.set(cont, timeout=banco.TIMEOUT)
    with BASE.trava:
        BASE.cont[cid] = cont
        BASE.ver = time.time()
    return cont, res


# ══════════════════════════════════════════════════════════════════════════════
# MEMÓRIA
# ══════════════════════════════════════════════════════════════════════════════
class _Base:
    INCREMENTAL, COMPLETA = 20, 1800

    def __init__(self):
        self.trava = threading.RLock()
        self.cont: dict[str, dict] | None = None
        self.t_completa = self.t_inc = 0.0
        self.ultimo = ""
        self.cfg_cache: dict = {}
        self.t_cfg = 0.0
        self.ver = 0.0
        self.leituras = 0

    def atualizar(self, forcar=False):
        with self.trava:
            agora_s = time.time()
            if forcar or self.cont is None or agora_s - self.t_completa > self.COMPLETA:
                docs = list(db().collection(col()).stream(timeout=banco.TIMEOUT))
                self.cont = {d.id: normalizar_container(d.to_dict()) for d in docs}
                self.leituras += len(docs)
                self.ultimo = max((c.get("atualizado_em", "") for c in self.cont.values()), default="")
                self.t_completa = self.t_inc = agora_s
                self.ver = agora_s
            elif agora_s - self.t_inc > self.INCREMENTAL:
                from google.cloud.firestore_v1.base_query import FieldFilter
                q = db().collection(col()).where(filter=FieldFilter("atualizado_em", ">", self.ultimo or ""))
                docs = list(q.stream(timeout=banco.TIMEOUT))
                for d in docs:
                    self.cont[d.id] = normalizar_container(d.to_dict())
                    self.ultimo = max(self.ultimo, self.cont[d.id].get("atualizado_em", ""))
                self.leituras += len(docs)
                self.t_inc = agora_s
                if docs:
                    self.ver = agora_s

    def config(self, nome: str, padrao):
        """config/{nome} do bancowendley (motivos, departamentos, tickets_hub) — cache de 2 min."""
        with self.trava:
            if nome not in self.cfg_cache or time.time() - self.t_cfg > 120:
                for n in ("motivos_central", "departamentos", "tickets_hub"):
                    snap = doc_cfg(n).get(timeout=banco.TIMEOUT)
                    self.cfg_cache[n] = (snap.to_dict() or {}) if snap.exists else {}
                    self.leituras += 1
                if banco_proprio():
                    usu = {d.id: (d.to_dict() or {}) for d in db().collection("usuarios").stream(timeout=banco.TIMEOUT)}
                    self.leituras += len(usu)
                else:   # banco do hub: os usuários são os do próprio hub (setor definido em Ajustes)
                    setores = (self.cfg_cache.get("tickets_hub") or {}).get("setor_usuarios") or {}
                    usu = {k: {"nome": v.get("nome") or k, "depto": setores.get(k, "")} for k, v in acesso.USUARIOS.todos().items()
                           if v.get("ativo", True)}
                    if acesso.ADMIN_FAB_LOGIN and acesso.ADMIN_FAB_LOGIN not in usu:
                        usu[acesso.ADMIN_FAB_LOGIN] = {"nome": "Administrador", "depto": setores.get(acesso.ADMIN_FAB_LOGIN, "")}
                self.cfg_cache["usuarios"] = {k: {"nome": v.get("nome") or k, "depto": v.get("depto") or v.get("departamento") or ""}
                                              for k, v in usu.items()}
                self.t_cfg = time.time()
            return self.cfg_cache.get(nome) or padrao

    def tickets(self) -> list[dict]:
        saida = []
        for cid, c in (self.cont or {}).items():
            for s in c.get("solicitacoes", []):
                t = dict(s)
                t["id"] = compor(cid, s.get("sid", "legacy"))
                t.setdefault("cliente_codigo", c.get("cliente_codigo", ""))
                t.setdefault("cliente_nome", c.get("cliente_nome", ""))
                saida.append(t)
        return saida


BASE = _Base()


def hub_cfg() -> dict:
    return {**CONFIG_PADRAO, **BASE.config("tickets_hub", {})}


def motivos() -> dict:
    m = BASE.config("motivos_central", {}).get("ticket", {})
    return m or ({} if banco_proprio() else MOTIVOS_PADRAO)


def departamentos() -> list[str]:
    return BASE.config("departamentos", {}).get("lista") or (["GERAL", "TI", "RH", "OPERAÇÃO"] if banco_proprio() else DEPARTAMENTOS_PADRAO)


def usuarios() -> dict:
    BASE.config("departamentos", {})
    return BASE.cfg_cache.get("usuarios", {})


# ══════════════════════════════════════════════════════════════════════════════
# QUEM É QUEM — usuário do hub ↔ usuário dos tickets
# ══════════════════════════════════════════════════════════════════════════════
def eu(u: dict) -> dict:
    mapa = hub_cfg().get("mapa_usuarios") or {}
    usu = usuarios()
    login = u.get("login", "")
    alvo = mapa.get(login) or (login if login in usu else None)
    if not alvo:
        alvo = next((k for k, v in usu.items() if norm(v.get("nome")) == norm(u.get("nome"))), None) or login
    info = usu.get(alvo, {})
    return {"usuario": alvo, "nome": info.get("nome") or u.get("nome") or login, "depto": info.get("depto", ""), "hub": login}


def _contexto(request: Request):
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(MOD)
    if esq is None:
        raise HTTPException(404, "Módulo tickets não encontrado (falta modulos/tickets.html).")
    p = acesso.permissoes(u, MOD, esq)
    if not p["acoes"].get("acessar"):
        raise HTTPException(403, "Sem acesso aos Tickets.")
    if not configurado():
        raise HTTPException(503, "sem_banco_tickets")
    BASE.atualizar()
    return u, p, eu(u)


def _exigir(p, acao, texto):
    if not p["acoes"].get(acao):
        raise HTTPException(403, f"Sem permissão para {texto}.")


def atribuido(t: dict, me: dict) -> bool:
    return me["usuario"] in (t.get("atendentes") or []) or t.get("atribuido_para") in (me["usuario"], me["nome"])


def pend_abertas(t: dict) -> list[dict]:
    sols = t.get("solicitacoes_setor") or []
    resp = {s.get("pedido_id") for s in sols if s.get("tipo") == "resposta"}
    return [s for s in sols if s.get("tipo") == "pedido" and s.get("id") not in resp]


def visivel(t: dict, p: dict, me: dict) -> bool:
    if p["acoes"].get("equipe"):
        return True
    if atribuido(t, me) or t.get("aberto_por") == me["usuario"]:
        return True
    if me["depto"]:
        if p["acoes"].get("setor") and norm(t.get("departamento")) == norm(me["depto"]):
            return True
        if any(norm(me["depto"]) in (norm(s.get("setor_destino")), norm(s.get("setor_origem"))) for s in pend_abertas(t)):
            return True
    return False


def nao_visto(t: dict, me: dict) -> bool:
    """Alerta azul: alguém (que não sou eu) interagiu num ticket meu depois da minha última interação."""
    if not atribuido(t, me):
        return False
    ult = t.get("ultima_interacao_autor")
    return bool(ult) and ult != me["usuario"]


def resumo(t: dict, me: dict, agora_dt: datetime) -> dict:
    sla = sla_info(t, agora_dt)
    pend = pend_abertas(t)
    return {k: t.get(k) for k in ("id", "status", "prioridade", "assunto", "departamento", "motivo_pai", "motivo_filho", "etapa_atual",
                                   "cliente_codigo", "cliente_nome", "cliente_telefone", "atribuido_para", "aberto_por", "solicitante_nome",
                                   "criado_em", "atualizado_em", "origem", "erp_pedido_id", "erp_pedido_numero", "etapa_travada")} | {
        "atendentes": t.get("atendentes") or [], "sla": sla, "pendencias": [s.get("setor_destino") for s in pend],
        "n_comentarios": len(t.get("comentarios") or []), "nao_visto": nao_visto(t, me), "meu": atribuido(t, me),
        "sem_dono": not (t.get("atendentes") or t.get("atribuido_para")),
    }


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS — leitura
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/estado")
def estado(request: Request, dias_concluidos: int = 30):
    u, p, me = _contexto(request)
    agora_dt = datetime.now(BRT)
    corte = (agora_dt - timedelta(days=max(1, min(dias_concluidos, 400)))).strftime("%Y-%m-%d")
    lista = []
    for t in BASE.tickets():
        if not visivel(t, p, me):
            continue
        if t.get("status") not in ABERTOS and str(t.get("atualizado_em", ""))[:10] < corte:
            continue
        lista.append(resumo(t, me, agora_dt))
    usu = usuarios()
    return {"perm": p, "eu": me, "tickets": lista, "versao": BASE.ver,
            "departamentos": departamentos(), "motivos": motivos(), "status": STATUS, "prioridades": PRIORIDADES,
            "usuarios": [{"usuario": k, "nome": v["nome"], "depto": v["depto"]} for k, v in sorted(usu.items(), key=lambda kv: norm(kv[1]["nome"]))],
            "config": {k: v for k, v in hub_cfg().items() if k != "mapa_usuarios"} | ({"mapa_usuarios": hub_cfg().get("mapa_usuarios")} if p["acoes"].get("configurar") else {}),
            "sync": {"leituras": BASE.leituras, "completa": BASE.t_completa}, "erp": _erp_ligado(),
            "banco": "bancowendley" if banco_proprio() else "hub"}


def _ticket(tid: str, p: dict, me: dict) -> dict:
    cid, sid = decompor(tid)
    c = (BASE.cont or {}).get(cid)
    s = next((x for x in (c or {}).get("solicitacoes", []) if x.get("sid") == sid), None) if c else None
    if not s:
        raise HTTPException(404, "Ticket não encontrado.")
    t = {**s, "id": tid, "cliente_codigo": s.get("cliente_codigo") or c.get("cliente_codigo", ""),
         "cliente_nome": s.get("cliente_nome") or c.get("cliente_nome", "")}
    if not visivel(t, p, me):
        raise HTTPException(403, "Você não tem acesso a esse ticket.")
    return t


@router.get("/ticket/{tid:path}")
def detalhe(tid: str, request: Request):
    u, p, me = _contexto(request)
    t = _ticket(tid, p, me)
    cid, _ = decompor(tid)
    outros = [resumo(x, me, datetime.now(BRT)) for x in BASE.tickets()
              if x["id"] != tid and decompor(x["id"])[0] == cid]
    return {"ticket": {**t, "sla": sla_info(t), "pend_abertas": [s.get("id") for s in pend_abertas(t)]},
            "outros": outros, "erp": erp_do_ticket(t, u) if _erp_ligado() else None}


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS — escrita
# ══════════════════════════════════════════════════════════════════════════════
def _mutar_sol(tid: str, fn, me: dict, interacao=True):
    cid, sid = decompor(tid)

    def m(cont):
        sols = cont.get("solicitacoes", [])
        i = next((k for k, s in enumerate(sols) if s.get("sid") == sid), None)
        if i is None:
            raise HTTPException(404, "Ticket não encontrado (pode ter sido apagado no outro sistema).")
        s = dict(sols[i])
        res = fn(s)
        ag = agora()
        s["atualizado_em"] = ag
        if interacao:
            s["ultima_interacao_em"] = ag
            s["ultima_interacao_autor"] = me["usuario"]
        sols[i] = s
        cont["solicitacoes"] = sols
        cont["atualizado_em"] = ag
        return res
    return _transacao(cid, m)


def _coment(s: dict, me: dict, texto: str, interno=True, tipo="nota"):
    s.setdefault("comentarios", []).append({"autor": me["nome"], "usuario": me["usuario"], "texto": texto, "data": agora(),
                                            "interno": interno, "tipo": tipo, "via": "hub"})


def criar_solicitacao(dados: dict, me: dict, bloquear_duplicado=False) -> str:
    cod = str(dados.get("cliente_codigo") or "").strip()
    if not cod:
        raise HTTPException(400, "Informe o código do cliente.")
    cid = _id_doc(cod)
    sid = _sid()

    def m(cont):
        if bloquear_duplicado and dados.get("motivo_pai"):
            for s in cont.get("solicitacoes", []):
                if norm(s.get("motivo_pai")) == norm(dados["motivo_pai"]) and s.get("status") not in ("finalizado", "cancelado"):
                    raise HTTPException(409, f"Este cliente já tem um chamado aberto de \"{s.get('motivo_pai')}\" — trate esse antes de abrir outro.")
        ag = agora()
        nova = {"sid": sid, "criado_em": ag, "atualizado_em": ag, "origem": "hub", "comentarios": [], "historico_etapas": [],
                "solicitacoes_setor": [], "sla1_definido": False, "sla1_cumprido": None, "etapa_vermelha": False,
                "etapa_travada": False, "status": "aberto", "horas_sla": 24, "atendentes": [], **dados, "cliente_codigo": cod}
        nova["sid"] = sid
        cont.setdefault("solicitacoes", []).append(nova)
        cont["cliente_codigo"] = cod
        if dados.get("cliente_nome"):
            cont["cliente_nome"] = dados["cliente_nome"]
        cont.setdefault("criado_em", ag)
        cont["atualizado_em"] = ag
    _transacao(cid, m)
    return compor(cid, sid)


def _sla_motivo(pai: str, filho: str):
    info = (motivos().get(pai) or {}).get(filho) if filho else None
    if info and info.get("sla") not in (None, ""):
        return info.get("sla")
    filhos = motivos().get(pai) or {}
    slas = [f.get("sla") for f in filhos.values() if f.get("ativo", True) and f.get("sla") not in (None, "")]
    return min(slas) if slas else None


@router.post("/tickets")
async def abrir(request: Request):
    u, p, me = _contexto(request)
    _exigir(p, "abrir", "abrir chamados")
    c = await request.json()
    assunto, desc = str(c.get("assunto") or "").strip(), str(c.get("descricao") or "").strip()
    if not assunto or not desc:
        raise HTTPException(400, "Preencha assunto e descrição.")
    pai, filho = str(c.get("motivo_pai") or ""), str(c.get("motivo_filho") or "")
    dados = {"assunto": assunto[:200], "descricao": desc[:5000], "departamento": str(c.get("departamento") or ""),
             "categoria": str(c.get("departamento") or ""), "motivo_pai": pai, "motivo_pai_id": pai, "motivo_filho": filho,
             "sla1_prazo_dias": _sla_motivo(pai, filho), "prioridade": c.get("prioridade") if c.get("prioridade") in PRIORIDADES else "normal",
             "cliente_nome": str(c.get("cliente_nome") or "").strip(), "cliente_telefone": str(c.get("cliente_telefone") or "").strip(),
             "solicitante_nome": me["nome"], "aberto_por": me["usuario"], "cliente_codigo": str(c.get("cliente_codigo") or "").strip()}
    for k in ("erp_pedido_id", "erp_pedido_numero", "erp_cliente_id"):
        if c.get(k):
            dados[k] = c[k]
    if c.get("atribuir_a_mim"):
        dados.update(atendentes=[me["usuario"]], atribuido_para=me["usuario"], status="em_andamento")
    tid = criar_solicitacao({k: v for k, v in dados.items() if v is not None}, me, bloquear_duplicado=bool(c.get("bloquear_duplicado", True)))
    return {"ok": True, "id": tid}


@router.post("/ticket/{tid:path}/comentar")
async def comentar(tid: str, request: Request):
    u, p, me = _contexto(request)
    _exigir(p, "atender", "registrar no ticket")
    _ticket(tid, p, me)
    c = await request.json()
    texto = str(c.get("texto") or "").strip()
    if not texto:
        raise HTTPException(400, "Escreva alguma coisa.")
    tipo = c.get("tipo") if c.get("tipo") in ("nota", "contato", "resposta") else "nota"

    def fn(s):
        _coment(s, me, texto[:5000], interno=tipo != "resposta", tipo=tipo)
        if c.get("status") in STATUS:
            s["status"] = c["status"]
        elif s.get("status") == "aberto" and atribuido(s, me):
            s["status"] = "em_andamento"
    _mutar_sol(tid, fn, me)
    return {"ok": True}


@router.post("/ticket/{tid:path}/alterar")
async def alterar(tid: str, request: Request):
    """status, prioridade, atribuir (assumir/transferir)."""
    u, p, me = _contexto(request)
    t = _ticket(tid, p, me)
    c = await request.json()
    log = []

    def fn(s):
        if "status" in c:
            novo = c["status"]
            if novo not in STATUS:
                raise HTTPException(400, "Status inválido.")
            if novo in ("resolvido", "finalizado", "cancelado"):
                _exigir(p, "encerrar", "encerrar atendimentos")
            else:
                _exigir(p, "atender", "alterar atendimentos")
            if s.get("status") != novo:
                log.append(f"Status: {s.get('status')} → {novo}")
                s["status"] = novo
                if novo in ("resolvido", "finalizado"):
                    s["resolvido_em"] = agora()
                    s["resolvido_por"] = me["usuario"]
        if "prioridade" in c:
            _exigir(p, "atender", "alterar atendimentos")
            if c["prioridade"] not in PRIORIDADES:
                raise HTTPException(400, "Prioridade inválida.")
            if s.get("prioridade") != c["prioridade"]:
                log.append(f"Prioridade: {s.get('prioridade') or '—'} → {c['prioridade']}")
                s["prioridade"] = c["prioridade"]
        if "atribuir" in c:
            alvo = str(c["atribuir"] or "")
            if alvo == me["usuario"] and not (s.get("atendentes") or s.get("atribuido_para")):
                _exigir(p, "atender", "assumir atendimentos")
            else:
                _exigir(p, "transferir", "transferir atendimentos")
            nome = usuarios().get(alvo, {}).get("nome", alvo) if alvo else "ninguém"
            s["atendentes"] = [alvo] if alvo else []
            s["atribuido_para"] = alvo
            if alvo and s.get("status") == "aberto":
                s["status"] = "em_andamento"
            log.append(f"Atribuído a {nome}")
        if log:
            _coment(s, me, " · ".join(log), tipo="sistema")
    _mutar_sol(tid, fn, me)
    return {"ok": True}


@router.post("/lote")
async def lote(request: Request):
    """Transferir / assumir vários de uma vez."""
    u, p, me = _contexto(request)
    _exigir(p, "transferir", "transferir atendimentos")
    c = await request.json()
    alvo = str(c.get("atribuir") or "")
    nome = usuarios().get(alvo, {}).get("nome", alvo) if alvo else "ninguém"
    feitos = 0
    for tid in (c.get("ids") or [])[:300]:
        try:
            _ticket(tid, p, me)
        except HTTPException:
            continue

        def fn(s):
            s["atendentes"] = [alvo] if alvo else []
            s["atribuido_para"] = alvo
            if alvo and s.get("status") == "aberto":
                s["status"] = "em_andamento"
            _coment(s, me, f"Atribuído a {nome} (em lote)", tipo="sistema")
        _mutar_sol(tid, fn, me)
        feitos += 1
    return {"ok": True, "feitos": feitos}


@router.post("/ticket/{tid:path}/classificar")
async def classificar(tid: str, request: Request):
    """Motivo Filho + Etapa (mesma regra do Streamlit): 1ª classificação congela o SLA1;
    etapa com data → prazo passa a ser a data e a trilha TRAVA."""
    u, p, me = _contexto(request)
    _exigir(p, "atender", "classificar atendimentos")
    t = _ticket(tid, p, me)
    if t.get("etapa_travada"):
        raise HTTPException(409, "Esta trilha já foi travada com prazo — não pode mais ser alterada.")
    c = await request.json()
    pai = str(c.get("motivo_pai") or t.get("motivo_pai") or "")
    filho, etapa = str(c.get("motivo_filho") or ""), str(c.get("etapa") or "")
    arv = motivos()
    if pai not in arv or filho not in arv[pai]:
        raise HTTPException(400, "Escolha um Motivo e um Submotivo válidos.")
    etapas = arv[pai][filho].get("etapas") or []
    if etapas and etapa not in etapas:
        raise HTTPException(400, "Escolha uma etapa da lista.")
    data = str(c.get("data_prevista") or "")
    vermelha = bool(data)
    if vermelha:
        try:
            if datetime.fromisoformat(data).date() < datetime.now(BRT).date():
                raise HTTPException(400, "A data prevista precisa ser hoje ou depois.")
        except ValueError:
            raise HTTPException(400, "Data prevista inválida.") from None
    caminho = " › ".join(x for x in (filho, etapa) if x)

    def fn(s):
        ag = agora()
        if pai != s.get("motivo_pai"):
            s["motivo_pai"] = s["motivo_pai_id"] = pai
        s.update(motivo_filho=filho, etapa_atual=caminho, etapa_vermelha=vermelha)
        if not s.get("sla1_definido"):
            lim, _ = deadline({**s, "etapa_vermelha": False, "etapa_data_prevista": None})
            s.update(sla1_definido=True, sla1_cumprido=(datetime.now(BRT) <= lim) if lim else True, sla1_definido_em=ag)
        if vermelha:
            s.update(etapa_data_prevista=data, etapa_definida_em=ag, etapa_definida_por=me["nome"], etapa_travada=True)
        s.setdefault("historico_etapas", []).append({"etapa": caminho, "quando": ag, "por": me["nome"], "vermelha": vermelha,
                                                    "data_prevista": data or None})
        if s.get("status") == "aberto":
            s["status"] = "em_andamento"
        _coment(s, me, f"Classificado: {pai} › {caminho}" + (f" · prazo {data[8:10]}/{data[5:7]} (travado)" if vermelha else ""), tipo="sistema")
    _mutar_sol(tid, fn, me)
    return {"ok": True}


@router.post("/ticket/{tid:path}/pendencia")
async def pendencia(tid: str, request: Request):
    """Pedir algo a outro setor (fica no MESMO ticket) — ou responder uma pendência."""
    u, p, me = _contexto(request)
    _exigir(p, "atender", "registrar pendências")
    t = _ticket(tid, p, me)
    c = await request.json()
    msg = str(c.get("mensagem") or "").strip()
    if not msg:
        raise HTTPException(400, "Escreva a mensagem.")
    if c.get("responder"):
        ped = next((s for s in pend_abertas(t) if s.get("id") == c["responder"]), None)
        if not ped:
            raise HTTPException(404, "Pendência não encontrada (já respondida?).")

        def fn(s):
            s.setdefault("solicitacoes_setor", []).append({
                "id": _sid(), "tipo": "resposta", "pedido_id": ped["id"], "setor_origem": ped.get("setor_destino"),
                "setor_destino": ped.get("setor_origem"), "resposta": msg, "respondido_por": me["usuario"],
                "respondido_por_nome": me["nome"], "respondido_em": agora()})
            _coment(s, me, f"✅ Setor {ped.get('setor_destino')} respondeu a {ped.get('setor_origem')}: {msg}", tipo="pendencia")
    else:
        destino = str(c.get("setor") or "")
        if not destino:
            raise HTTPException(400, "Escolha o setor.")

        def fn(s):
            s.setdefault("solicitacoes_setor", []).append({
                "id": _sid(), "tipo": "pedido", "setor_origem": s.get("departamento") or s.get("categoria") or "—",
                "setor_destino": destino, "mensagem": msg, "solicitado_por": me["usuario"],
                "solicitado_por_nome": me["nome"], "solicitado_em": agora()})
            _coment(s, me, f"📨 Solicitação para o setor {destino}: {msg}", tipo="pendencia")
    _mutar_sol(tid, fn, me)
    return {"ok": True}


@router.put("/config")
async def salvar_config(request: Request):
    u, p, me = _contexto(request)
    _exigir(p, "configurar", "configurar o módulo")
    c = await request.json()
    novo = hub_cfg()
    if "mapa_usuarios" in c:
        novo["mapa_usuarios"] = {str(k): str(v) for k, v in (c["mapa_usuarios"] or {}).items() if k and v}
    if "auto_erp" in c:
        novo["auto_erp"] = {k: bool((c["auto_erp"] or {}).get(k)) for k in ("avaria", "recusado", "ausente")}
    for k in ("depto_erp", "motivo_pai_erp"):
        if k in c:
            novo[k] = str(c[k] or "")
    if "sla_erp_dias" in c:
        try:
            novo["sla_erp_dias"] = max(0.0, min(float(c["sla_erp_dias"]), 60.0))
        except (TypeError, ValueError):
            raise HTTPException(400, "SLA inválido.") from None
    if "setor_usuarios" in c:
        novo["setor_usuarios"] = {str(k): str(v) for k, v in (c["setor_usuarios"] or {}).items() if k}
    doc_cfg("tickets_hub").set(novo, timeout=banco.TIMEOUT)
    BASE.cfg_cache["tickets_hub"] = novo
    BASE.t_cfg = 0
    return {"ok": True}


@router.put("/config/motivos")
async def salvar_motivos(request: Request):
    """Árvore Motivo › Submotivo {sla dias, etapas[], ativo} — mesmo formato do motivos_central do Streamlit."""
    u, p, me = _contexto(request)
    _exigir(p, "configurar", "configurar motivos")
    c = await request.json()
    arv = {}
    for pai, filhos in (c.get("motivos") or {}).items():
        pai = str(pai).strip()[:80]
        if not pai:
            continue
        arv[pai] = {}
        for f, info in (filhos or {}).items():
            f = str(f).strip()[:80]
            if not f:
                continue
            try:
                sla = float(info.get("sla")) if info.get("sla") not in (None, "") else None
            except (TypeError, ValueError):
                sla = None
            arv[pai][f] = {"sla": sla, "ativo": bool(info.get("ativo", True)),
                           "etapas": [str(e).strip()[:80] for e in (info.get("etapas") or []) if str(e).strip()][:30]}
    atual = BASE.config("motivos_central", {})
    doc_cfg("motivos_central").set({**atual, "ticket": arv}, timeout=banco.TIMEOUT)
    deps = [str(d).strip()[:60] for d in (c.get("departamentos") or []) if str(d).strip()]
    if deps:
        doc_cfg("departamentos").set({"lista": deps}, timeout=banco.TIMEOUT)
    BASE.t_cfg = 0
    return {"ok": True}


@router.post("/recarregar")
def recarregar(request: Request):
    u, p, me = _contexto(request)
    _exigir(p, "configurar", "recarregar")
    BASE.atualizar(forcar=True)
    BASE.t_cfg = 0
    return {"ok": True, "leituras": BASE.leituras}


# ══════════════════════════════════════════════════════════════════════════════
# PONTE COM O ERP
# ══════════════════════════════════════════════════════════════════════════════
def _erp():
    try:
        import erp
        return erp
    except Exception:  # noqa: BLE001
        return None


def _erp_ligado() -> bool:
    e = _erp()
    return bool(e) and banco.configurado()


def clientes_erp_do_ticket(t: dict) -> list[str]:
    e = _erp()
    e.ST.carregar()
    parc = e.ST.dados["parceiros"]
    if t.get("erp_cliente_id") in parc:
        return [t["erp_cliente_id"]]
    cod, tel, nome = norm(t.get("cliente_codigo")), digitos(t.get("cliente_telefone"))[-8:], norm(t.get("cliente_nome"))
    achados = []
    for pid, c in parc.items():
        if c.get("tipo") != "cliente":
            continue
        if cod and norm(c.get("codigo")) == cod:
            return [pid]
        if (tel and len(tel) == 8 and digitos(c.get("telefone"))[-8:] == tel) or (nome and norm(c.get("nome")) == nome):
            achados.append(pid)
    return achados


def _ped_resumo(e, pid: str, d: dict) -> dict:
    car = e.ST.dados["cargas"].get(d.get("carga_id") or "")
    return {"id": pid, "numero": d.get("numero"), "tipo": d.get("tipo"), "status": d.get("status"), "pendencia": d.get("pendencia"),
            "agendamento": d.get("agendamento"), "valor_total": d.get("valor_total"), "criado_em": d.get("criado_em"),
            "carga": car.get("numero") if car else None, "cliente_id": d.get("cliente_id"), "cliente_nome": d.get("cliente_nome"),
            "itens": [{"nome": (e.ST.dados["produtos"].get(i["produto_id"]) or {}).get("nome", i["produto_id"]), "qtd": i.get("qtd")}
                      for i in d.get("itens", [])],
            "tentativas": [{"n": x.get("n"), "data": x.get("data"), "resultado": x.get("resultado"), "motivo": x.get("motivo")}
                           for x in d.get("tentativas", [])],
            "historico": (d.get("historico") or [])[-6:], "origem_id": d.get("origem_id"), "sem_estoque": d.get("sem_estoque")}


def erp_do_ticket(t: dict, u: dict) -> dict:
    e = _erp()
    try:
        perm = acesso.permissoes(u, "erp", acesso.obter_esquema("erp") or acesso.normalizar_esquema(None))
    except Exception:  # noqa: BLE001
        perm = {"acoes": {}}
    if not perm["acoes"].get("acessar"):
        return {"sem_acesso": True}
    ids = clientes_erp_do_ticket(t)
    peds = [_ped_resumo(e, pid, d) for pid, d in e.ST.dados["pedidos"].items() if d.get("cliente_id") in ids]
    for lig in [t.get("erp_pedido_id")] + [x.get("id") for x in t.get("erp_trocas") or []]:
        if lig and lig in e.ST.dados["pedidos"] and not any(x["id"] == lig for x in peds):
            peds.append(_ped_resumo(e, lig, e.ST.dados["pedidos"][lig]))
    peds.sort(key=lambda x: str(x.get("criado_em") or ""), reverse=True)
    ligados = {t.get("erp_pedido_id")} | {x.get("id") for x in t.get("erp_trocas") or []}
    peds.sort(key=lambda x: x["id"] not in ligados)   # os do atendimento primeiro
    clientes = [{"id": i, "nome": e.ST.dados["parceiros"][i].get("nome"), "codigo": e.ST.dados["parceiros"][i].get("codigo", "")} for i in ids]
    return {"clientes": clientes, "pedidos": peds[:20], "pode": {k: bool(perm["acoes"].get(k)) for k in ("agendar", "pedidos", "cancelar")},
            "janelas": e.ST.config.get("janelas", []), "hoje": e.hoje()}


@router.post("/ticket/{tid:path}/erp-cliente")
async def vincular_cliente_erp(tid: str, request: Request):
    u, p, me = _contexto(request)
    _exigir(p, "atender", "vincular cliente")
    _ticket(tid, p, me)
    c = await request.json()
    cli = str(c.get("cliente_id") or "")

    def fn(s):
        s["erp_cliente_id"] = cli
        _coment(s, me, "Cliente do ERP vinculado" if cli else "Cliente do ERP desvinculado", tipo="sistema")
    _mutar_sol(tid, fn, me, interacao=False)
    return {"ok": True}


@router.get("/erp/clientes")
def buscar_clientes_erp(request: Request, q: str = ""):
    _contexto(request)
    e = _erp()
    e.ST.carregar()
    qn, qd = norm(q), digitos(q)
    out = []
    for pid, c in e.ST.dados["parceiros"].items():
        if c.get("tipo") != "cliente":
            continue
        if (qn and qn in norm(c.get("nome"))) or (qd and len(qd) >= 4 and (qd in digitos(c.get("telefone")) or qd in digitos(c.get("doc")))) \
                or (qn and norm(c.get("codigo")).startswith(qn)):
            out.append({"id": pid, "nome": c.get("nome"), "codigo": c.get("codigo", ""), "telefone": c.get("telefone", ""),
                        "cidade": (c.get("endereco") or {}).get("cidade", "")})
        if len(out) >= 15:
            break
    exato = [x for x in out if norm(x["codigo"]) == qn]   # o código exato vem primeiro
    return {"clientes": exato + [x for x in out if x not in exato]}


@router.post("/erp/clientes/{cliente_id}/codigo")
def codigo_do_cliente(cliente_id: str, request: Request):
    """Atendimento escolheu um cliente do ERP sem código: cria o código (6 caracteres) e grava no cadastro."""
    _contexto(request)
    e = _erp()
    e.ST.carregar()
    with e.ST.trava:
        tx = e.Tx({"login": "atendimento"})
        cod = e.garantir_codigo(tx, cliente_id)
        if not cod:
            raise HTTPException(404, "Cliente não encontrado no ERP.")
        tx.commit()
    return {"codigo": cod}


@router.post("/ticket/{tid:path}/erp-troca")
async def gerar_troca(tid: str, request: Request):
    """Cria no ERP o pedido de TROCA do pedido escolhido (leva os mesmos itens e recolhe os do cliente)."""
    u, p, me = _contexto(request)
    _exigir(p, "atender", "gerar troca")
    t = _ticket(tid, p, me)
    e = _erp()
    up, pp = e._ctx(request, "pedidos", "criar pedidos no ERP")
    c = await request.json()
    with e.ST.trava:
        orig_id = str(c.get("pedido_id") or "")
        orig = e.ST.dados["pedidos"].get(orig_id)
        if not orig:
            raise HTTPException(404, "Pedido do ERP não encontrado.")
        if orig.get("status") != "entregue":
            raise HTTPException(409, "Troca só de pedido entregue.")
        tx = e.Tx(up)
        novo = e._novo_pedido(tx, up, pp, {"tipo": "troca", "cliente_id": orig.get("cliente_id"), "origem_id": c["pedido_id"],
                                           "motivo_troca": str(c.get("motivo") or t.get("motivo_filho") or ""),
                                           "obs": f"Aberta pelo ticket {tid.split('#')[-1]}",
                                           "itens": [{"produto_id": i["produto_id"], "qtd": i["qtd"], "preco": 0} for i in orig.get("itens", [])],
                                           "recolher": [{"produto_id": i["produto_id"], "qtd": i["qtd"]} for i in orig.get("itens", [])]})
        tx.commit()

    def fn(s):
        if not s.get("erp_pedido_id"):
            s["erp_pedido_id"], s["erp_pedido_numero"] = orig_id, orig.get("numero")
        s.setdefault("erp_trocas", []).append({"id": novo["id"], "numero": novo.get("numero")})
        _coment(s, me, f"🔁 Troca #{novo.get('numero')} criada no ERP (rascunho) a partir do pedido #{orig.get('numero')}.", tipo="sistema")
    _mutar_sol(tid, fn, me)
    return {"ok": True, "pedido": {"id": novo["id"], "numero": novo.get("numero")}}


def registrar_no_ticket(tid: str, texto: str, me: dict):
    try:
        _mutar_sol(tid, lambda s: _coment(s, me, texto, tipo="sistema"), me)
    except HTTPException:
        pass


@router.post("/ticket/{tid:path}/erp-registro")
async def registro_erp(tid: str, request: Request):
    """A tela chama depois de agendar/cancelar pelo ERP, para deixar a trilha no ticket."""
    u, p, me = _contexto(request)
    _ticket(tid, p, me)
    c = await request.json()
    registrar_no_ticket(tid, "📦 " + str(c.get("texto") or "")[:300], me)
    return {"ok": True}


# ── ERP → Tickets ────────────────────────────────────────────────────────────
@router.get("/erp/pedido/{pid}")
def tickets_do_pedido(pid: str, request: Request):
    """Usado pelo ERP: tickets ligados ao pedido ou ao cliente dele."""
    u = acesso.exigir_usuario(request)
    if not configurado():
        return {"configurado": False, "tickets": []}
    esq = acesso.obter_esquema(MOD)
    p = acesso.permissoes(u, MOD, esq) if esq else {"acoes": {}}
    if not p["acoes"].get("acessar"):
        return {"configurado": True, "sem_acesso": True, "tickets": []}
    BASE.atualizar()
    me = eu(u)
    e = _erp()
    ped = e.ST.dados["pedidos"].get(pid) or {}
    agora_dt = datetime.now(BRT)
    saida = []
    for t in BASE.tickets():
        ligado = t.get("erp_pedido_id") == pid
        if not ligado and ped.get("cliente_id"):
            ligado = ped["cliente_id"] in clientes_erp_do_ticket(t) if (t.get("erp_cliente_id") or t.get("cliente_codigo")) else False
        if ligado and visivel(t, p, me):
            saida.append(resumo(t, me, agora_dt))
    saida.sort(key=lambda x: x.get("criado_em") or "", reverse=True)
    return {"configurado": True, "tickets": saida[:20], "pode_abrir": bool(p["acoes"].get("abrir"))}


def _cliente_ticket_de_pedido(ped: dict, pid: str) -> tuple[str, str, str]:
    e = _erp()
    cli = e.ST.dados["parceiros"].get(ped.get("cliente_id") or "") or {}
    cod = cli.get("codigo") or ""
    if not cod and ped.get("cliente_id"):
        try:
            with e.ST.trava:
                tx = e.Tx({"login": "atendimento"})
                cod = e.garantir_codigo(tx, ped["cliente_id"])
                tx.commit()
        except Exception as ex:  # noqa: BLE001
            print(f"[tickets] não gerou código do cliente: {ex}")
    cod = cod or e.gerar_codigo_cliente()
    return cod, cli.get("nome") or ped.get("cliente_nome", ""), cli.get("telefone") or ped.get("telefone", "")


@router.post("/erp/pedido/{pid}/abrir")
async def abrir_de_pedido(pid: str, request: Request):
    u, p, me = _contexto(request)
    _exigir(p, "abrir", "abrir chamados")
    e = _erp()
    ped = e.ST.dados["pedidos"].get(pid)
    if not ped:
        raise HTTPException(404, "Pedido não encontrado no ERP.")
    c = await request.json()
    cod, nome, tel = _cliente_ticket_de_pedido(ped, pid)
    cfg = hub_cfg()
    pai = str(c.get("motivo_pai") or cfg.get("motivo_pai_erp") or "")
    dados = {"assunto": str(c.get("assunto") or f"Pedido #{ped.get('numero')}")[:200],
             "descricao": str(c.get("descricao") or "").strip() or f"Chamado aberto a partir do pedido #{ped.get('numero')} do ERP.",
             "departamento": str(c.get("departamento") or cfg.get("depto_erp") or ""), "motivo_pai": pai, "motivo_pai_id": pai,
             "motivo_filho": str(c.get("motivo_filho") or ""), "sla1_prazo_dias": _sla_motivo(pai, str(c.get("motivo_filho") or "")) or cfg.get("sla_erp_dias"),
             "prioridade": c.get("prioridade") if c.get("prioridade") in PRIORIDADES else "normal",
             "cliente_nome": nome, "cliente_telefone": tel, "solicitante_nome": me["nome"], "aberto_por": me["usuario"],
             "erp_pedido_id": pid, "erp_pedido_numero": ped.get("numero"), "erp_cliente_id": ped.get("cliente_id"), "origem": "erp"}
    if c.get("atribuir_a_mim"):
        dados.update(atendentes=[me["usuario"]], atribuido_para=me["usuario"], status="em_andamento")
    dados["cliente_codigo"] = cod
    tid = criar_solicitacao({k: v for k, v in dados.items() if v not in (None, "")}, me)
    return {"ok": True, "id": tid}


def eventos_do_erp(eventos: list, usuario_hub: dict):
    """Chamado pelo ERP depois de gravar QUALQUER ação num pedido (confirmar, bloqueio, liberação
    automática, agendar, alterar, cancelar, saída para entrega, baixa…). Cada evento vira um
    comentário nos tickets ABERTOS do pedido — ou do cliente, quando o ticket não é de outro pedido.
    Nunca derruba o ERP: qualquer erro só vai para o log."""
    try:
        if not configurado() or not eventos:
            return
        BASE.atualizar()
        quem = usuario_hub.get("login", "")
        me = {"usuario": "erp", "nome": "ERP" + (f" · {quem}" if quem and quem not in ("atendimento", "sistema") else ""), "depto": "", "hub": quem}
        abertos = [t for t in BASE.tickets() if t.get("status") in ABERTOS]
        for ev in eventos:
            pid = ev.get("pid")
            alvos = []
            for t in abertos:
                ligados = {t.get("erp_pedido_id")} | {x.get("id") for x in t.get("erp_trocas") or []}
                if pid in ligados:
                    alvos.append(t)
                elif not t.get("erp_pedido_id") and ev.get("cliente_id") and (t.get("erp_cliente_id") or t.get("cliente_codigo")) \
                        and ev["cliente_id"] in clientes_erp_do_ticket(t):
                    alvos.append(t)
            if not alvos:
                continue
            texto = "📦 Pedido #" + str(ev.get("numero")) + ": " + " · ".join(ev.get("eventos") or [])
            for t in alvos:
                try:
                    _mutar_sol(t["id"], lambda s, txt=texto: _coment(s, me, txt[:600], tipo="sistema"), me)
                except HTTPException:
                    pass
    except Exception as ex:  # noqa: BLE001
        print(f"[tickets] eventos do ERP não chegaram aos tickets: {type(ex).__name__}: {ex}")


ROTULO_RES = {"avaria": "Avaria na entrega", "recusado": "Entrega recusada", "ausente": "Cliente ausente na entrega"}


def auto_de_baixa(pid: str, resultado: str, motivo: str, usuario_hub: dict):
    """Chamado pelo ERP depois de gravar a baixa. Nunca derruba a baixa: qualquer erro só vai pro log."""
    try:
        if not configurado() or resultado not in ROTULO_RES:
            return
        cfg = hub_cfg()
        if not (cfg.get("auto_erp") or {}).get(resultado):
            return
        e = _erp()
        ped = e.ST.dados["pedidos"].get(pid)
        if not ped:
            return
        BASE.atualizar()
        if any(t.get("erp_pedido_id") == pid and t.get("status") in ABERTOS and t.get("origem") == "erp_auto"
               and t.get("erp_evento") == resultado for t in BASE.tickets()):
            return  # já existe um aberto para esse evento
        me = {"usuario": "erp", "nome": "ERP (automático)", "depto": "", "hub": usuario_hub.get("login", "")}
        cod, nome, tel = _cliente_ticket_de_pedido(ped, pid)
        pai = cfg.get("motivo_pai_erp") or ""
        criar_solicitacao({
            "assunto": f"{ROTULO_RES[resultado]} · pedido #{ped.get('numero')}",
            "descricao": f"Aberto automaticamente pela baixa da entrega no ERP ({ROTULO_RES[resultado].lower()})."
                         + (f" Motivo informado: {motivo}." if motivo else "") + f" Baixa feita por @{usuario_hub.get('login', '')}.",
            "departamento": cfg.get("depto_erp") or "", "categoria": cfg.get("depto_erp") or "", "motivo_pai": pai, "motivo_pai_id": pai,
            "sla1_prazo_dias": cfg.get("sla_erp_dias") or 2, "prioridade": "alta" if resultado != "ausente" else "normal",
            "cliente_nome": nome, "cliente_telefone": tel, "solicitante_nome": me["nome"], "aberto_por": "erp",
            "erp_pedido_id": pid, "erp_pedido_numero": ped.get("numero"), "erp_cliente_id": ped.get("cliente_id"),
            "origem": "erp_auto", "erp_evento": resultado, "cliente_codigo": cod}, me)
    except Exception as ex:  # noqa: BLE001
        print(f"[tickets] ticket automático da baixa falhou: {type(ex).__name__}: {ex}")
