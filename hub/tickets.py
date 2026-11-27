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

CHAMADO ÚNICO POR CÓDIGO (a central mostra assim):
    • 1 código de cliente = 1 CHAMADO (o container). Cada problema é uma
      SOLICITAÇÃO dentro dele (motivo/submotivo, pedido, SLA, etapa, pendências
      e situação próprios) e tem uma COR fixa (ordem de criação).
    • Abrir problema novo nunca cria outro chamado: vira solicitação no mesmo
      código. Trava: mesmo motivo + mesmo pedido já aberto.
    • O CHAT do app (origem=app, app_tipo=chat) é separado enquanto está ativo.
      "Concluir chat": anexa a conversa ao chamado OU vira solicitação.
    • Um DONO por cliente: assumir/transferir vale para todas as solicitações
      abertas, e as novas já nascem com ele.
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

import copy
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
    return banco.envolver(_db)   # separa por empresa (Configurações → Duplicar sistema)


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
                    usu = {k: {"nome": v.get("nome") or k, "depto": setores.get(k, "")} for k, v in acesso.usuarios_da_empresa().items()
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


BASE = banco.por_empresa(_Base)   # um cache por empresa


def hub_cfg() -> dict:
    return {**CONFIG_PADRAO, **BASE.config("tickets_hub", {})}


def motivos_por_setor() -> dict:
    """Árvores próprias de cada setor (Ajustes › escolher o setor). Setor sem árvore usa a geral."""
    return {k: v for k, v in (BASE.config("motivos_central", {}).get("por_setor") or {}).items() if v}


def motivos(setor: str = "") -> dict:
    if setor:
        ps = motivos_por_setor()
        for k, v in ps.items():
            if norm(k) == norm(setor):
                return v
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


# ══════════════════════════════════════════════════════════════════════════════
# PERFIL — o que cada um vê (Ajustes › Setor de cada pessoa)
#   atendente  → só os chats e tickets dele (pega o próximo da fila do setor com um clique)
#   supervisor → tudo do setor dele + painel da equipe do setor
#   gestor     → todos os setores + painel geral
# ══════════════════════════════════════════════════════════════════════════════
PERFIS = ("atendente", "supervisor", "gestor")
ONLINE = banco.por_empresa(dict)   # login → visto por último (por empresa)
ONLINE_SEG = 180


def perfil_padrao(p: dict) -> str:
    return "gestor" if p["acoes"].get("equipe") or p["acoes"].get("configurar") else "supervisor"


def perfil_de(me: dict, p: dict) -> str:
    if p["acoes"].get("configurar"):
        return "gestor"
    pf = (hub_cfg().get("perfis") or {}).get(me.get("usuario"))
    return pf if pf in PERFIS else perfil_padrao(p)


def online(usuario: str) -> bool:
    return time.time() - ONLINE.get(usuario, 0) < ONLINE_SEG


# ══════════════════════════════════════════════════════════════════════════════
# PRESENÇA (status na barra do hub): Online · pausas (Ajustes › Setor e perfil) · Offline
#   Ao abrir o hub, entra Online. Sem sinal do navegador por 5 min → Offline sozinho.
#   Diferente de Online = não recebe atendimento (a distribuição olha isto).
#   O tempo em cada status fica gravado por dia (cx_presenca/<usuario>_<AAAA-MM-DD>) para a Gestão.
# ══════════════════════════════════════════════════════════════════════════════
PAUSAS_PADRAO = [{"id": "pausa", "rotulo": "Pausa", "emoji": "☕"}, {"id": "almoco", "rotulo": "Almoço", "emoji": "🍽️"},
                 {"id": "banheiro", "rotulo": "Banheiro", "emoji": "🚻"}, {"id": "reuniao", "rotulo": "Reunião", "emoji": "👥"}]
SEM_SINAL_SEG = 300
PRESENCA = banco.por_empresa(dict)   # usuario → {"status", "desde", "ping"}
_trava_pres = threading.Lock()


def pausas() -> list[dict]:
    lst = [x for x in (hub_cfg().get("pausas") or []) if isinstance(x, dict) and x.get("id") and x.get("rotulo")]
    return lst or PAUSAS_PADRAO


def limite_de(usuario: str) -> int | None:
    """Atendimentos (chats) simultâneos: None = sem limite · 0 = só tickets."""
    v = (hub_cfg().get("limites") or {}).get(usuario)
    return None if v in (None, "") else max(0, int(v))


def _seg_doc(usuario: str, dia: str):
    return banco.db().collection("cx_presenca").document(f"{usuario}_{dia}")


_SEGS = banco.por_empresa(dict)   # (usuario, dia) → doc do dia (dias passados não mudam: lê uma vez só)


def segmentos(usuario: str, dia: str) -> list[dict]:
    k = (usuario, dia)
    if k not in _SEGS:
        try:
            snap = _seg_doc(usuario, dia).get(timeout=banco.TIMEOUT)
            _SEGS[k] = (snap.to_dict() if snap.exists else None) or {"segs": []}
        except Exception:  # noqa: BLE001
            return []
        if len(_SEGS) > 20000:
            _SEGS.clear()
    return _SEGS[k].get("segs") or []


def tempos(usuario: str, de: str, ate: str, por_hora: bool = False) -> dict:
    """Minutos em cada status no período [de, ate] (AAAA-MM-DD). Trecho aberto conta até agora (ou até o último sinal).
    por_hora=True: também os minutos ONLINE de cada hora (0-23), para a curva do dia."""
    total, horas = {}, [0.0] * 24
    agora_dt = datetime.now(BRT)
    p = PRESENCA.get(usuario) or {}
    vivo_ate = datetime.fromtimestamp(min(time.time(), (p.get("ping") or 0) + SEM_SINAL_SEG), BRT) if p.get("status") not in (None, "offline") else None
    d = datetime.fromisoformat(de).date()
    fim_d = datetime.fromisoformat(ate).date()
    while d <= fim_d:
        for sg in segmentos(usuario, d.isoformat()):
            ini = _dt(sg.get("i"))
            fim = _dt(sg.get("f")) if sg.get("f") else (vivo_ate if d == agora_dt.date() else None)
            if not ini or not fim or fim <= ini:
                continue
            total[sg.get("s")] = total.get(sg.get("s"), 0) + (fim - ini).total_seconds() / 60
            if por_hora and sg.get("s") == "online":
                c = ini
                while c < fim:
                    prox = min(fim, c.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                    horas[c.hour] += (prox - c).total_seconds() / 60
                    c = prox
        d += timedelta(days=1)
    return {"min": {k: round(v) for k, v in total.items()}, "horas": [round(x) for x in horas]}


def _registrar(usuario: str, status: str, ini: float, fim_anterior: float | None):
    """Fecha o trecho aberto (em fim_anterior) e abre um novo com `status` — no dia de cada um."""
    def hh(t):
        return datetime.fromtimestamp(t, BRT).strftime("%Y-%m-%d %H:%M:%S")
    try:
        if fim_anterior is not None:
            dia = hh(fim_anterior)[:10]
            ref = _seg_doc(usuario, dia)
            snap = ref.get(timeout=banco.TIMEOUT)
            d = (snap.to_dict() if snap.exists else None) or {"usuario": usuario, "dia": dia, "segs": []}
            if d["segs"] and not d["segs"][-1].get("f"):
                d["segs"][-1]["f"] = hh(fim_anterior)
                ref.set(d, timeout=banco.TIMEOUT)
            _SEGS[(usuario, dia)] = d
        if status != "offline":
            dia = hh(ini)[:10]
            ref = _seg_doc(usuario, dia)
            snap = ref.get(timeout=banco.TIMEOUT)
            d = (snap.to_dict() if snap.exists else None) or {"usuario": usuario, "dia": dia, "segs": []}
            d["segs"] = (d["segs"] + [{"s": status, "i": hh(ini), "f": None}])[-400:]
            ref.set(d, timeout=banco.TIMEOUT)
            _SEGS[(usuario, dia)] = d
    except Exception as ex:  # noqa: BLE001
        print(f"[presença] não gravou {usuario}: {ex}")


def _mudar(usuario: str, status: str, agora_s: float, fim_anterior: float | None = None, auto: bool = False):
    """auto=True: o SISTEMA deixou offline (ociosa ou sem sinal) — volta sozinho para Online quando a pessoa mexer.
    Offline escolhido no botão (auto=False) só muda no botão."""
    atual = PRESENCA.get(usuario)
    if atual and atual["status"] == status:
        atual["auto"] = auto if status == "offline" else False
        return
    PRESENCA[usuario] = {"status": status, "desde": agora_s, "ping": agora_s, "auto": auto and status == "offline"}
    if atual and atual["status"] != "offline":
        fim = fim_anterior if fim_anterior is not None else agora_s
    else:
        fim = None
    banco.thread(_registrar, usuario, status, agora_s, fim)


def presenca(usuario: str) -> dict:
    """Status atual (já tratando o "sem sinal": 5 min sem o navegador avisar → Offline desde o último sinal)."""
    with _trava_pres:
        p = PRESENCA.get(usuario)
        if p and p["status"] != "offline" and time.time() - p["ping"] > SEM_SINAL_SEG:
            _mudar(usuario, "offline", p["ping"] + 60, fim_anterior=p["ping"] + 60, auto=True)
            p = PRESENCA[usuario]
        return dict(p) if p else {"status": "offline", "desde": None, "ping": 0}


def disponivel(usuario: str) -> bool:
    return presenca(usuario)["status"] == "online"


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
    me = eu(u)
    me["perfil"] = perfil_de(me, p)
    ONLINE[me["usuario"]] = time.time()   # presença: quem está com o hub aberto (o hub consulta a cada 15–30 s)
    return u, p, me


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
    pf = me.get("perfil") or perfil_de(me, p)
    if pf == "gestor":
        return True
    if atribuido(t, me) or t.get("aberto_por") == me["usuario"]:
        return True
    if me["depto"]:
        if (pf == "supervisor" or t.get("interno")) and norm(t.get("departamento")) == norm(me["depto"]):   # supervisor vê o setor inteiro
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


def eh_chat(t: dict) -> bool:
    """Chat do app (aba Atendimento do cliente) — os primeiros do app não tinham app_tipo e eram chats."""
    return t.get("origem") == "app" and (t.get("app_tipo") or "chat") == "chat"


def cor_de(t: dict) -> int:
    """Cor fixa da solicitação = posição dela (por criação) entre as solicitações do chamado. Chat = -1."""
    if eh_chat(t):
        return -1
    cid, sid = decompor(t.get("id", ""))
    sols = [x for x in ((BASE.cont or {}).get(cid) or {}).get("solicitacoes", []) if not eh_chat(x)]
    sols.sort(key=lambda x: str(x.get("criado_em") or ""))
    return next((i for i, x in enumerate(sols) if x.get("sid") == sid), 0)


def dono_do_chamado(cont: dict) -> list[str]:
    """Quem cuida do cliente: o atendente das solicitações abertas (a mais recente que tiver dono)."""
    abertas = sorted((s for s in cont.get("solicitacoes", []) if s.get("status") in ABERTOS and (s.get("atendentes") or s.get("atribuido_para"))),
                     key=lambda s: str(s.get("atualizado_em") or ""), reverse=True)
    if not abertas:
        return []
    s = abertas[0]
    return list(s.get("atendentes") or ([s["atribuido_para"]] if s.get("atribuido_para") else []))


def resumo(t: dict, me: dict, agora_dt: datetime) -> dict:
    sla = sla_info(t, agora_dt)
    pend = pend_abertas(t)
    return {"cid": decompor(t.get("id", ""))[0], "chat": eh_chat(t), "cor": cor_de(t)} | {k: t.get(k) for k in ("id", "status", "prioridade", "assunto", "departamento", "motivo_pai", "motivo_filho", "etapa_atual",
                                   "cliente_codigo", "cliente_nome", "cliente_telefone", "atribuido_para", "aberto_por", "solicitante_nome",
                                   "criado_em", "atualizado_em", "origem", "erp_pedido_id", "erp_pedido_numero", "etapa_travada",
                                   "app_opcao", "app_pendente_desde", "app_tipo", "chamei_em", "chamei_por")} | {"interno": bool(t.get("interno"))} | {"app_pendente": bool(t.get("app_pendente")),
        "atendentes": t.get("atendentes") or [], "sla": sla, "pendencias": [s.get("setor_destino") for s in pend],
        "n_comentarios": len(t.get("comentarios") or []), "nao_visto": nao_visto(t, me), "meu": atribuido(t, me),
        "sem_dono": not (t.get("atendentes") or t.get("atribuido_para")),
    }


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS — leitura
# ══════════════════════════════════════════════════════════════════════════════
def clientes_em_rastreio() -> tuple[set, set]:
    """Clientes com pedido EM RASTREIO (frota na rua, sem desfecho): (ids do ERP, códigos do app).
    O chat do app desses clientes vai para a fila "Frota" da Caixa (e também aparece no WROUTER)."""
    ids, cods = set(), set()
    try:
        import wrouter
        e = _erp()
        for car in list((e.ST.dados.get("cargas") or {}).values()):
            for pid in car.get("pedidos") or []:
                if wrouter.em_rastreio(car, pid):
                    cid = (e.ST.dados["pedidos"].get(pid) or {}).get("cliente_id")
                    if cid:
                        ids.add(cid)
                        cod = (e.ST.dados["parceiros"].get(cid) or {}).get("codigo")
                        if cod:
                            cods.add(norm(cod))
    except Exception:  # noqa: BLE001
        pass
    return ids, cods


@router.get("/estado")
def estado(request: Request, dias_concluidos: int = 30):
    u, p, me = _contexto(request)
    distribuir()
    agora_dt = datetime.now(BRT)
    corte = (agora_dt - timedelta(days=max(1, min(dias_concluidos, 400)))).strftime("%Y-%m-%d")
    lista = []
    r_ids, r_cods = clientes_em_rastreio()
    for t in BASE.tickets():
        if not visivel(t, p, me):
            continue
        if t.get("status") not in ABERTOS and str(t.get("atualizado_em", ""))[:10] < corte:
            continue
        r = resumo(t, me, agora_dt)
        if r["chat"] and (t.get("erp_cliente_id") in r_ids or norm(t.get("cliente_codigo")) in r_cods):
            r["frota"] = True   # cliente com pedido em rastreio: fila "Frota"
        lista.append(r)
    usu = usuarios()
    return {"perm": p, "eu": me, "tickets": lista, "versao": BASE.ver, "fila": fila_sem_dono(me),
            "departamentos": departamentos(), "motivos": motivos(), "motivos_setor": motivos_por_setor(), "status": STATUS, "prioridades": PRIORIDADES,
            "usuarios": [{"usuario": k, "nome": v["nome"], "depto": v["depto"]} for k, v in sorted(usu.items(), key=lambda kv: norm(kv[1]["nome"]))],
            "config": {k: v for k, v in hub_cfg().items() if k != "mapa_usuarios"} | ({"mapa_usuarios": hub_cfg().get("mapa_usuarios")} if p["acoes"].get("configurar") else {}),
            "sync": {"leituras": BASE.leituras, "completa": BASE.t_completa}, "erp": _erp_ligado(),
            "banco": "bancowendley" if banco_proprio() else "hub", "app_cliente": _app_cliente(), "wwhat": _wwhat(), "pausas": pausas(), "regua": _regua()}


def _regua() -> dict:
    try:
        import regua
        return regua.publico()
    except Exception:  # noqa: BLE001
        return {}


def _wwhat() -> dict:
    """Ajustes do bot do link de atendimento (/atendimento/) com os padrões preenchidos."""
    try:
        import cliente_app
        return cliente_app.cfg_wwhat()
    except Exception:  # noqa: BLE001
        return {}


def _app_cliente() -> dict:
    """Ajustes do app do cliente (/cliente/) com os padrões preenchidos — import tardio (cliente_app importa este módulo)."""
    try:
        import cliente_app
        c = cliente_app.cfg_app()
    except Exception:  # noqa: BLE001
        return {}
    e = _erp()
    if e and banco.configurado():
        try:
            e.ST.carregar()
            c["pedidos_sem_palavra"] = sum(1 for d in e.ST.dados["pedidos"].values()
                                           if not d.get("palavra_chave") and d.get("status") not in ("cancelado", "rascunho"))
        except Exception:  # noqa: BLE001
            pass
    return c


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
        aberto_antes = s.get("status") in ABERTOS
        res = fn(s)
        if aberto_antes and eh_chat(s) and s.get("status") in ("resolvido", "finalizado"):   # chat concluído → pesquisa (régua)
            try:
                import regua
                regua.chat_concluido({**s, "id": tid}, cont.get("cliente_codigo") or s.get("cliente_codigo") or "",
                                     cont.get("cliente_nome") or s.get("cliente_nome") or "", s.get("atribuido_para") or s.get("resolvido_por") or "")
            except Exception as ex:  # noqa: BLE001
                print(f"[régua] pesquisa do chat: {ex}")
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


def _coment(s: dict, me: dict, texto: str, interno=True, tipo="nota", anexos: list | None = None):
    s.setdefault("comentarios", []).append({"autor": me["nome"], "usuario": me["usuario"], "texto": texto, "data": agora(),
                                            "interno": interno, "tipo": tipo, "via": "hub", **({"anexos": anexos} if anexos else {})})


def criar_solicitacao(dados: dict, me: dict, bloquear_duplicado=False) -> str:
    cod = str(dados.get("cliente_codigo") or "").strip()
    if not cod:
        raise HTTPException(400, "Informe o código do cliente.")
    cid = _id_doc(cod)
    sid = _sid()

    def m(cont):
        if bloquear_duplicado and dados.get("motivo_pai"):
            for s in cont.get("solicitacoes", []):
                if (not eh_chat(s) and norm(s.get("motivo_pai")) == norm(dados["motivo_pai"]) and s.get("status") not in ("finalizado", "cancelado")
                        and str(s.get("erp_pedido_id") or "") == str(dados.get("erp_pedido_id") or "")):
                    ped = f" do pedido #{s.get('erp_pedido_numero')}" if s.get("erp_pedido_numero") else ""
                    raise HTTPException(409, f"O chamado {cod} já tem uma solicitação aberta de \"{s.get('motivo_pai')}\"{ped} — "
                                             "registre nela em vez de abrir outra.")
        herda = {}
        if not (dados.get("atendentes") or dados.get("atribuido_para")) and not (dados.get("origem") == "app" and dados.get("app_tipo") == "chat"):
            dono = dono_do_chamado(cont)   # um dono por cliente: a solicitação nova já nasce com ele
            if dono:
                herda = {"atendentes": dono, "atribuido_para": dono[0], "status": "em_andamento"}
        ag = agora()
        nova = {"sid": sid, "criado_em": ag, "atualizado_em": ag, "origem": "hub", "comentarios": [], "historico_etapas": [],
                "solicitacoes_setor": [], "sla1_definido": False, "sla1_cumprido": None, "etapa_vermelha": False,
                "etapa_travada": False, "status": "aberto", "horas_sla": 24, "atendentes": [], **dados, **herda, "cliente_codigo": cod}
        nova["sid"] = sid
        cont.setdefault("solicitacoes", []).append(nova)
        cont["cliente_codigo"] = cod
        if dados.get("cliente_nome"):
            cont["cliente_nome"] = dados["cliente_nome"]
        cont.setdefault("criado_em", ag)
        cont["atualizado_em"] = ag
    _transacao(cid, m)
    return compor(cid, sid)


def exige_codigo(setor: str, pai: str, filho: str) -> bool:
    """Submotivo marcado em Ajustes como "não exige código" → solicitação INTERNA (ex.: Manutenção › torneira,
    TI › trocar mouse): não tem cliente, não entra na Caixa, cai só em Pedidos de ajuda do setor."""
    info = (motivos(setor).get(pai) or {}).get(filho) if pai and filho else None
    return bool(info.get("exige_codigo", True)) if info else True


def _sla_motivo(pai: str, filho: str, setor: str = ""):
    arv = motivos(setor)
    info = (arv.get(pai) or {}).get(filho) if filho else None
    if info and info.get("sla") not in (None, ""):
        return info.get("sla")
    filhos = arv.get(pai) or {}
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
             "sla1_prazo_dias": _sla_motivo(pai, filho, str(c.get("departamento") or "")), "prioridade": c.get("prioridade") if c.get("prioridade") in PRIORIDADES else "normal",
             "cliente_nome": str(c.get("cliente_nome") or "").strip(), "cliente_telefone": str(c.get("cliente_telefone") or "").strip(),
             "solicitante_nome": me["nome"], "aberto_por": me["usuario"], "cliente_codigo": str(c.get("cliente_codigo") or "").strip()}
    for k in ("erp_pedido_id", "erp_pedido_numero", "erp_cliente_id"):
        if c.get(k):
            dados[k] = c[k]
    if c.get("atribuir_a_mim"):
        dados.update(atendentes=[me["usuario"]], atribuido_para=me["usuario"], status="em_andamento")
    interno = bool(pai and filho and not exige_codigo(dados["departamento"], pai, filho))
    if interno:
        dados.update(interno=True, cliente_codigo=f"INTERNO-{me['usuario']}", cliente_nome=me["nome"], cliente_telefone="")
        for k in ("erp_pedido_id", "erp_pedido_numero", "erp_cliente_id"):
            dados.pop(k, None)
    havia = chamado_aberto(_id_doc(dados["cliente_codigo"])) if dados.get("cliente_codigo") else 0
    tid = criar_solicitacao({k: v for k, v in dados.items() if v is not None}, me, bloquear_duplicado=bool(c.get("bloquear_duplicado", True)) and not interno)
    return {"ok": True, "id": tid, "cid": decompor(tid)[0], "agrupado": bool(havia) and not interno, "chamado": dados["cliente_codigo"], "interno": interno}


def chamado_aberto(cid: str) -> int:
    """Quantas solicitações (não chat) abertas o chamado do cliente tem agora."""
    BASE.atualizar()
    cont = (BASE.cont or {}).get(cid) or {}
    return sum(1 for s in cont.get("solicitacoes", []) if not eh_chat(s) and s.get("status") in ABERTOS)


@router.get("/anexo/{aid}")
def ver_anexo(aid: str, request: Request, t: str = ""):
    """Anexo de uma conversa do CX (o atendente precisa enxergar o chamado: ?t=<id do ticket>)."""
    u, p, me = _contexto(request)
    import anexos as A
    doc = A.ler(aid)
    tk = _ticket(t, p, me)
    if doc.get("cont") != decompor(tk["id"])[0]:
        raise HTTPException(404, "Anexo não encontrado.")
    return A.resposta(doc)


@router.post("/ticket/{tid:path}/comentar")
async def comentar(tid: str, request: Request):
    u, p, me = _contexto(request)
    _exigir(p, "atender", "registrar no ticket")
    _ticket(tid, p, me)
    c = await request.json()
    texto = str(c.get("texto") or "").strip()
    if not texto and not c.get("anexos"):
        raise HTTPException(400, "Escreva alguma coisa.")
    tipo = c.get("tipo") if c.get("tipo") in ("nota", "contato", "resposta") else "nota"
    import anexos as A
    anx = A.salvar_lista(c.get("anexos"), {"cont": decompor(tid)[0], "tid": tid}) if c.get("anexos") else []

    def fn(s):
        # "resposta" (no chat) e "contato" (atualização da solicitação) o cliente VÊ no app; nota interna não
        _coment(s, me, texto[:5000], interno=tipo not in ("resposta", "contato"), tipo=tipo, anexos=anx)
        if tipo == "resposta":   # "Responder no app": o cliente vê no app e sai da fila "cliente aguardando"
            s["app_pendente"] = False
            s.pop("app_pendente_desde", None)
            s["app_respondido_em"] = agora()
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
                # solicitação interna (sem cliente): o setor de destino e quem pediu também finalizam
                if not (s.get("interno") and (norm(s.get("departamento")) == norm(me.get("depto")) or s.get("aberto_por") == me["usuario"])):
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
    c = await request.json()
    setor = str(c.get("departamento") or t.get("departamento") or "").strip()
    if setor and setor not in departamentos() and setor != t.get("departamento"):
        raise HTTPException(400, "Setor inválido.")
    pai = str(c.get("motivo_pai") or t.get("motivo_pai") or "")
    filho, etapa = str(c.get("motivo_filho") or ""), str(c.get("etapa") or "")
    travada = bool(t.get("etapa_travada"))
    arv = motivos(setor)
    if pai not in arv or filho not in arv[pai]:
        raise HTTPException(400, "Escolha um Motivo e um Submotivo válidos.")
    etapas = arv[pai][filho].get("etapas") or []
    if etapas and etapa not in etapas:
        raise HTTPException(400, "Escolha uma etapa da lista.")
    data = "" if travada else str(c.get("data_prevista") or "")   # trilha travada: o prazo combinado não muda
    vermelha = bool(data) or travada
    if data:
        try:
            if datetime.fromisoformat(data).date() < datetime.now(BRT).date():
                raise HTTPException(400, "A data prevista precisa ser hoje ou depois.")
        except ValueError:
            raise HTTPException(400, "Data prevista inválida.") from None
    caminho = " › ".join(x for x in (filho, etapa) if x)

    def fn(s):
        ag = agora()
        mudou = []
        if setor and setor != s.get("departamento"):
            mudou.append(f"setor {s.get('departamento') or '—'} → {setor}")
            s["departamento"] = s["categoria"] = setor
        if (pai, filho) != (s.get("motivo_pai"), s.get("motivo_filho")) and s.get("motivo_filho"):
            mudou.append(f"tabulação {s.get('motivo_pai') or '—'} › {s.get('motivo_filho') or '—'} → {pai} › {filho}")
        if pai != s.get("motivo_pai"):
            s["motivo_pai"] = s["motivo_pai_id"] = pai
        if filho != s.get("motivo_filho"):   # o SLA acompanha o submotivo novo
            novo_sla = _sla_motivo(pai, filho, setor)
            if novo_sla is not None:
                s["sla1_prazo_dias"] = novo_sla
        s.update(motivo_filho=filho, etapa_atual=caminho, etapa_vermelha=vermelha)
        if mudou:
            _coment(s, me, "Tabulação ajustada: " + " · ".join(mudou), tipo="sistema")
        if not s.get("sla1_definido"):
            lim, _ = deadline({**s, "etapa_vermelha": False, "etapa_data_prevista": None})
            s.update(sla1_definido=True, sla1_cumprido=(datetime.now(BRT) <= lim) if lim else True, sla1_definido_em=ag)
        if data:
            s.update(etapa_data_prevista=data, etapa_definida_em=ag, etapa_definida_por=me["nome"], etapa_travada=True)
        s.setdefault("historico_etapas", []).append({"etapa": caminho, "quando": ag, "por": me["nome"], "vermelha": vermelha,
                                                    "data_prevista": data or s.get("etapa_data_prevista") if vermelha else None})
        if s.get("status") == "aberto":
            s["status"] = "em_andamento"
        _coment(s, me, f"Classificado: {pai} › {caminho}" + (f" · prazo {data[8:10]}/{data[5:7]} (travado)" if data else ""), tipo="sistema")
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
                "id": _sid(), "tipo": "pedido",
                # [ajuda] quem pede é o SETOR DE QUEM PEDIU (antes era o setor do ticket — um CX pedindo num ticket de Compras saía como "Compras")
                "setor_origem": me.get("depto") or s.get("departamento") or s.get("categoria") or "—",
                "setor_destino": destino, "mensagem": msg, "solicitado_por": me["usuario"],
                "solicitado_por_nome": me["nome"], "solicitado_em": agora(), "mensagens": []})
            _coment(s, me, f"📨 Pedido de ajuda ao setor {destino}: {msg}", tipo="pendencia")
    _mutar_sol(tid, fn, me)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# PEDIDOS DE AJUDA — cada setor vê só o que pediram a ele e o que ele pediu
# (balão de chat em todo o hub: static/ajuda.js · aba "Pedidos de ajuda" no Atendimento)
# ══════════════════════════════════════════════════════════════════════════════
def _papel_ajuda(ped: dict, me: dict, setor: str = "") -> str:
    """'recebido' = pediram ao setor · 'enviado' = o setor (ou eu) pediu · '' = não é deste setor."""
    alvo = norm(setor or me.get("depto"))
    if alvo and norm(ped.get("setor_destino")) == alvo:
        return "recebido"
    if (not setor and ped.get("solicitado_por") == me["usuario"]) or (alvo and norm(ped.get("setor_origem")) == alvo):
        return "enviado"
    return ""


def _ajuda_view(cid: str, s: dict, ped: dict, resp: dict | None, papel: str) -> dict:
    conversa = [{"de": ped.get("solicitado_por"), "nome": ped.get("solicitado_por_nome"), "setor": ped.get("setor_origem"),
                 "texto": ped.get("mensagem", ""), "em": ped.get("solicitado_em")}] + list(ped.get("mensagens") or [])
    if resp:
        conversa.append({"de": resp.get("respondido_por"), "nome": resp.get("respondido_por_nome"), "setor": ped.get("setor_destino"),
                         "texto": resp.get("resposta", ""), "em": resp.get("respondido_em"), "encerrou": True})
    ult = conversa[-1]
    return {"id": ped.get("id"), "tid": compor(cid, s.get("sid", "legacy")), "cid": cid, "papel": papel,
            "cliente_codigo": s.get("cliente_codigo"), "cliente_nome": s.get("cliente_nome"),
            "assunto": s.get("motivo_filho") or s.get("assunto") or "", "setor_origem": ped.get("setor_origem"), "setor_destino": ped.get("setor_destino"),
            "solicitado_por": ped.get("solicitado_por"), "solicitado_por_nome": ped.get("solicitado_por_nome"), "solicitado_em": ped.get("solicitado_em"),
            "status": "resolvido" if resp else "aberto", "conversa": conversa, "ultima_em": ult.get("em"), "ultimo_de": ult.get("de")}


def pedidos_de_ajuda(me: dict, setor: str = "", dias: int = 30) -> list[dict]:
    corte = (datetime.now(BRT) - timedelta(days=max(1, min(dias, 400)))).strftime("%Y-%m-%d")
    saida = []
    for cid, c in (BASE.cont or {}).items():
        for s0 in c.get("solicitacoes", []):
            sols = s0.get("solicitacoes_setor") or []
            if not sols:
                continue
            s = {**s0, "cliente_codigo": s0.get("cliente_codigo") or c.get("cliente_codigo", ""), "cliente_nome": s0.get("cliente_nome") or c.get("cliente_nome", "")}
            resp = {x.get("pedido_id"): x for x in sols if x.get("tipo") == "resposta"}
            for ped in sols:
                if ped.get("tipo") != "pedido":
                    continue
                papel = _papel_ajuda(ped, me, setor)
                if not papel:
                    continue
                v = _ajuda_view(cid, s, ped, resp.get(ped.get("id")), papel)
                if v["status"] == "resolvido" and str(v["ultima_em"] or "")[:10] < corte:
                    continue
                saida.append(v)
    abertos = sorted([v for v in saida if v["status"] == "aberto"], key=lambda v: str(v["ultima_em"] or ""), reverse=True)
    fechados = sorted([v for v in saida if v["status"] != "aberto"], key=lambda v: str(v["ultima_em"] or ""), reverse=True)
    return abertos + fechados


@router.get("/ajuda")
def ajuda(request: Request, setor: str = "", dias: int = 30):
    """Pedidos de ajuda do MEU setor (recebidos e enviados). `setor=` só para quem configura o módulo (ver outro setor)."""
    u, p, me = _contexto(request)
    if setor and not p["acoes"].get("configurar"):
        setor = ""
    lista = pedidos_de_ajuda(me, setor, dias)
    return {"eu": me, "setor": setor or me.get("depto", ""), "pedidos": lista, "versao": BASE.ver,
            "departamentos": departamentos() if p["acoes"].get("configurar") else [],
            "abertos_recebidos": sum(1 for v in lista if v["status"] == "aberto" and v["papel"] == "recebido"),
            "conversas": conversas_de(me["usuario"]), "online": equipe_online(me["usuario"])}


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSA COM A EQUIPE — chat direto entre colegas, sem cliente (balão 🤝 › 💬)
#   Cada pessoa tem 1 documento (hub_conversas_equipe/{usuario}) com as conversas dela; a mensagem é gravada
#   nos dois lados. Cache em memória: o balão consulta a cada 15 s sem gastar leitura do banco.
# ══════════════════════════════════════════════════════════════════════════════
COL_DM, DM_MAX, DM_DIAS = "hub_conversas_equipe", 200, 60
_DM = banco.por_empresa(dict)   # cache das conversas da equipe (por empresa)
_DM_LOCK = threading.Lock()


def _dm(usuario: str) -> dict:
    if usuario not in _DM:
        try:
            snap = db().collection(COL_DM).document(usuario).get(timeout=banco.TIMEOUT)
            _DM[usuario] = (snap.to_dict() if snap.exists else None) or {"conversas": {}}
        except Exception:
            return {"conversas": {}}   # banco fora: não guarda em cache, tenta de novo depois
    return _DM[usuario]


def _dm_gravar(usuario: str, doc: dict):
    _DM[usuario] = doc
    db().collection(COL_DM).document(usuario).set(doc, timeout=banco.TIMEOUT)


def conversas_de(usuario: str) -> list:
    usu, saida = usuarios(), []
    for com, msgs in (_dm(usuario).get("conversas") or {}).items():
        if msgs:
            ult = msgs[-1]
            saida.append({"com": com, "nome": usu.get(com, {}).get("nome", com), "depto": usu.get(com, {}).get("depto", ""),
                          "online": online(com), "ultima_em": ult["em"], "ultimo_de": ult["de"], "texto": ult["texto"][:140],
                          "finalizada": bool(ult.get("fim"))})
    return sorted(saida, key=lambda x: x["ultima_em"], reverse=True)


def equipe_online(eu_usuario: str) -> list:
    usu = usuarios()
    return sorted(({"usuario": k, "nome": v.get("nome", k), "depto": v.get("depto", "")} for k, v in usu.items() if k != eu_usuario and online(k)),
                  key=lambda x: norm(x["nome"]))


@router.get("/conversa/{com}")
def conversa(com: str, request: Request):
    u, p, me = _contexto(request)
    usu = usuarios()
    return {"com": com, "nome": usu.get(com, {}).get("nome", com), "depto": usu.get(com, {}).get("depto", ""), "online": online(com),
            "mensagens": (_dm(me["usuario"]).get("conversas") or {}).get(com, [])}


@router.post("/conversa")
async def conversa_enviar(request: Request):
    u, p, me = _contexto(request)
    c = await request.json()
    para, texto = str(c.get("para") or "").strip(), str(c.get("texto") or "").strip()[:4000]
    if not texto:
        raise HTTPException(400, "Escreva a mensagem.")
    if not para or para == me["usuario"] or para not in usuarios():
        raise HTTPException(400, "Escolha um colega da equipe.")
    return {"ok": True, "mensagem": _dm_gravar_msg(me, para, {"de": me["usuario"], "nome": me["nome"], "texto": texto, "em": agora()})}


@router.post("/conversa/finalizar")
async def conversa_finalizar(request: Request):
    """Finaliza a conversa com o colega (some da lista de abertas dos dois; uma mensagem nova reabre)."""
    u, p, me = _contexto(request)
    para = str((await request.json()).get("para") or "").strip()
    if not para or para == me["usuario"] or para not in usuarios():
        raise HTTPException(400, "Escolha um colega da equipe.")
    if not (_dm(me["usuario"]).get("conversas") or {}).get(para):
        raise HTTPException(404, "Não há conversa com essa pessoa.")
    return {"ok": True, "mensagem": _dm_gravar_msg(me, para, {"de": me["usuario"], "nome": me["nome"], "texto": f"✅ Conversa finalizada por {me['nome']}.", "em": agora(), "fim": True})}


def _dm_gravar_msg(me: dict, para: str, msg: dict) -> dict:
    corte = (datetime.now(BRT) - timedelta(days=DM_DIAS)).strftime("%Y-%m-%d %H:%M:%S")
    with _DM_LOCK:
        for dono, com in ((me["usuario"], para), (para, me["usuario"])):
            doc = copy.deepcopy(_dm(dono))
            lista = [m for m in doc.setdefault("conversas", {}).get(com, []) if m["em"] >= corte] + [msg]
            doc["conversas"][com] = lista[-DM_MAX:]
            _dm_gravar(dono, doc)
    return msg


@router.post("/ajuda/mensagem")
async def ajuda_mensagem(request: Request):
    """Conversa do pedido de ajuda (chat). `encerrar=true` responde e fecha o pedido."""
    u, p, me = _contexto(request)
    c = await request.json()
    tid, pid, msg = str(c.get("tid") or ""), str(c.get("pid") or ""), str(c.get("texto") or "").strip()[:2000]
    if not msg and c.get("encerrar"):
        msg = "✅ Finalizado."   # finalizar sem mensagem final
    if not msg:
        raise HTTPException(400, "Escreva a mensagem.")
    cid, sid = decompor(tid)
    s0 = next((x for x in ((BASE.cont or {}).get(cid) or {}).get("solicitacoes", []) if x.get("sid") == sid), None)
    ped0 = next((x for x in (s0 or {}).get("solicitacoes_setor", []) if x.get("tipo") == "pedido" and x.get("id") == pid), None)
    if not ped0:
        raise HTTPException(404, "Pedido de ajuda não encontrado.")
    # quem atende o cliente também cobra/conversa (ícone Pendências da solicitação), mesmo sendo de outro setor
    if not (_papel_ajuda(ped0, me) or p["acoes"].get("configurar") or (p["acoes"].get("atender") and atribuido(s0, me))):
        raise HTTPException(403, "Este pedido de ajuda é de outro setor.")
    encerrar = bool(c.get("encerrar"))

    def fn(s):
        sols = s.setdefault("solicitacoes_setor", [])
        ped = next((x for x in sols if x.get("tipo") == "pedido" and x.get("id") == pid), None)
        if any(x.get("tipo") == "resposta" and x.get("pedido_id") == pid for x in sols):
            raise HTTPException(409, "Este pedido de ajuda já foi encerrado.")
        if encerrar:
            sols.append({"id": _sid(), "tipo": "resposta", "pedido_id": pid, "setor_origem": ped.get("setor_destino"),
                         "setor_destino": ped.get("setor_origem"), "resposta": msg, "respondido_por": me["usuario"],
                         "respondido_por_nome": me["nome"], "respondido_em": agora()})
            _coment(s, me, f"✅ Pedido de ajuda encerrado ({ped.get('setor_origem')} → {ped.get('setor_destino')}): {msg}", tipo="pendencia")
        else:
            ped.setdefault("mensagens", []).append({"de": me["usuario"], "nome": me["nome"], "setor": me.get("depto", ""), "texto": msg, "em": agora()})
            _coment(s, me, f"💬 Ajuda ({ped.get('setor_origem')} → {ped.get('setor_destino')}): {msg}", tipo="pendencia")
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
    if "perfis" in c:
        novo["perfis"] = {str(k): str(v) for k, v in (c["perfis"] or {}).items() if k and v in PERFIS}
    if "limites" in c:   # atendimentos simultâneos por pessoa (vazio = sem limite · 0 = só tickets)
        lim = {}
        for k, v in (c["limites"] or {}).items():
            if k and str(v).strip() != "":
                try:
                    lim[str(k)] = max(0, min(int(v), 50))
                except (TypeError, ValueError):
                    raise HTTPException(400, "Limite de atendimentos inválido.") from None
        novo["limites"] = lim
    if "regua" in c:   # régua do cliente (aviso por etapa do pedido) e pesquisas CSAT/NPS
        import regua
        novo["regua"] = regua.salvar(c["regua"])
    if "pausas" in c:   # motivos de pausa do botão de status (Online e Offline são fixos)
        lst = []
        for x in (c["pausas"] or [])[:12]:
            rot = str((x or {}).get("rotulo") or "").strip()[:30]
            if rot:
                pid = re.sub(r"[^a-z0-9]+", "-", norm(rot)).strip("-")[:20] or f"p{len(lst) + 1}"
                if pid in ("online", "offline"):
                    continue
                lst.append({"id": str(x.get("id") or pid)[:20] if x.get("id") not in ("online", "offline") else pid, "rotulo": rot,
                            "emoji": str(x.get("emoji") or "⏸").strip()[:4]})
        novo["pausas"] = lst
    if "setor_usuarios" in c:
        novo["setor_usuarios"] = {str(k): str(v) for k, v in (c["setor_usuarios"] or {}).items() if k}
    if "app_cliente" in c:   # app do cliente (/cliente/) — liga/desliga, nome, saudação, menu da URA, palavra-chave
        a = c["app_cliente"] or {}
        atual = dict(novo.get("app_cliente") or {})
        for k in ("ativo", "exigir_palavra"):
            if k in a:
                atual[k] = bool(a[k])
        for k, lim in (("empresa", 60), ("saudacao", 300)):
            if k in a:
                atual[k] = str(a[k] or "").strip()[:lim]
        if "ura" in a:
            ura = []
            for i, op in enumerate((a["ura"] or [])[:12]):
                rot = str((op or {}).get("rotulo") or "").strip()[:60]
                if rot:
                    ura.append({"id": re.sub(r"[^a-z0-9_-]", "", str(op.get("id") or "").lower())[:30] or f"op{i + 1}", "rotulo": rot,
                                "descricao": str(op.get("descricao") or "").strip()[:80],
                                "motivo_pai": str(op.get("motivo_pai") or "").strip()[:80], "departamento": str(op.get("departamento") or "").strip()[:60]})
            atual["ura"] = ura
        novo["app_cliente"] = atual
    if "wwhat" in c:   # bot do link de atendimento (/atendimento/) — liga/desliga, textos e para onde cai
        a = c["wwhat"] or {}
        atual = dict(novo.get("wwhat") or {})
        if "ativo" in a:
            atual["ativo"] = bool(a["ativo"])
        for k, lim in (("saudacao", 400), ("pedir_cpf", 200), ("direcionando", 400), ("departamento", 60), ("motivo_pai", 80), ("msg_fechado", 400)):
            if k in a:
                atual[k] = str(a[k] or "").strip()[:lim]
        if "horario_ativo" in a:
            atual["horario_ativo"] = bool(a["horario_ativo"])
        if "horario" in a:   # 0 = segunda … 6 = domingo
            hr = {}
            for i in range(7):
                d = (a["horario"] or {}).get(str(i)) or {}
                ini, fim = str(d.get("ini") or "08:00")[:5], str(d.get("fim") or "18:00")[:5]
                if not (re.match(r"^\d{2}:\d{2}$", ini) and re.match(r"^\d{2}:\d{2}$", fim)):
                    raise HTTPException(400, "Horário inválido (use HH:MM).")
                if d.get("aberto") and fim <= ini:
                    raise HTTPException(400, "O horário de fechar precisa ser depois do de abrir.")
                hr[str(i)] = {"aberto": bool(d.get("aberto")), "ini": ini, "fim": fim}
            atual["horario"] = hr
        if "feriados" in a:
            fer = []
            for f in (a["feriados"] or [])[:80]:
                dt = str((f or {}).get("data") or "")[:10]
                if re.match(r"^\d{4}-\d{2}-\d{2}$", dt):
                    fer.append({"data": dt, "nome": str(f.get("nome") or "Feriado").strip()[:60]})
            atual["feriados"] = sorted(fer, key=lambda x: x["data"])
        novo["wwhat"] = atual
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
            arv[pai][f] = {"sla": sla, "ativo": bool(info.get("ativo", True)), "exige_codigo": bool(info.get("exige_codigo", True)),
                           "etapas": [str(e).strip()[:80] for e in (info.get("etapas") or []) if str(e).strip()][:30]}
    atual = BASE.config("motivos_central", {})
    setor = str(c.get("setor") or "").strip()
    if setor:   # árvore própria do setor (vazia = volta a usar a geral)
        ps = {k: v for k, v in (atual.get("por_setor") or {}).items() if norm(k) != norm(setor)}
        if arv:
            ps[setor] = arv
        novo = {**atual, "por_setor": ps}
    else:
        novo = {**atual, "ticket": arv}
    doc_cfg("motivos_central").set(novo, timeout=banco.TIMEOUT)
    BASE.cfg_cache["motivos_central"] = novo
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


def _rastreio_link(car: dict | None, pid: str) -> str:
    """Pedido EM RASTREIO (frota na rua, sem desfecho) → o MESMO link de acompanhamento que o cliente usa."""
    if not car:
        return ""
    try:
        import wrouter
        if not wrouter.em_rastreio(car, pid):
            return ""
        tk = wrouter.link_do_pedido(car, pid)
    except Exception:  # noqa: BLE001
        return ""
    return f"{banco.prefixo_publico()}/entrega/{tk}" if tk else ""


def _ped_resumo(e, pid: str, d: dict, ver_palavra: bool = False) -> dict:
    car = e.ST.dados["cargas"].get(d.get("carga_id") or "")
    return ({"palavra_chave": d.get("palavra_chave") or ""} if ver_palavra else {}) | {"id": pid, "numero": d.get("numero"), "tipo": d.get("tipo"), "status": d.get("status"), "pendencia": d.get("pendencia"),
            "agendamento": d.get("agendamento"), "valor_total": d.get("valor_total"), "criado_em": d.get("criado_em"),
            "carga": car.get("numero") if car else None, "cliente_id": d.get("cliente_id"), "cliente_nome": d.get("cliente_nome"),
            "itens": [{"nome": (e.ST.dados["produtos"].get(i["produto_id"]) or {}).get("nome", i["produto_id"]), "qtd": i.get("qtd")}
                      for i in d.get("itens", [])],
            "tentativas": [{"n": x.get("n"), "data": x.get("data"), "resultado": x.get("resultado"), "motivo": x.get("motivo")}
                           for x in d.get("tentativas", [])],
            "historico": (d.get("historico") or [])[-6:], "origem_id": d.get("origem_id"), "sem_estoque": d.get("sem_estoque"),
            "nf": {"numero": (d.get("nf") or {}).get("numero"), "serie": (d.get("nf") or {}).get("serie"), "etiqueta": bool((d.get("nf") or {}).get("chave"))} if d.get("nf") else None,
            "entrega": {k: (d.get("entrega") or {}).get(k) for k in ("resultado", "em", "recebedor", "parentesco", "palavra", "dist_m", "motorista", "hash")} if d.get("entrega") else None,
            "rastreio": _rastreio_link(car, pid)}


def erp_do_ticket(t: dict, u: dict) -> dict:
    e = _erp()
    try:
        perm = acesso.permissoes(u, "erp", acesso.obter_esquema("erp") or acesso.normalizar_esquema(None))
    except Exception:  # noqa: BLE001
        perm = {"acoes": {}}
    if not perm["acoes"].get("acessar"):
        return {"sem_acesso": True}
    ver = ver_palavra(u)
    ids = clientes_erp_do_ticket(t)
    peds = [_ped_resumo(e, pid, d, ver) for pid, d in e.ST.dados["pedidos"].items() if d.get("cliente_id") in ids]
    for lig in [t.get("erp_pedido_id")] + [x.get("id") for x in t.get("erp_trocas") or []]:
        if lig and lig in e.ST.dados["pedidos"] and not any(x["id"] == lig for x in peds):
            peds.append(_ped_resumo(e, lig, e.ST.dados["pedidos"][lig], ver))
    peds.sort(key=lambda x: str(x.get("criado_em") or ""), reverse=True)
    ligados = {t.get("erp_pedido_id")} | {x.get("id") for x in t.get("erp_trocas") or []}
    peds.sort(key=lambda x: x["id"] not in ligados)   # os do atendimento primeiro
    clientes = [{"id": i, "nome": e.ST.dados["parceiros"][i].get("nome"), "codigo": e.ST.dados["parceiros"][i].get("codigo", "")} for i in ids]
    return {"clientes": clientes, "pedidos": peds[:20], "pode": {k: bool(perm["acoes"].get(k)) for k in ("agendar", "pedidos", "cancelar")} | {"palavra": ver},
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


def encerrar_auto_de_baixa(pid: str, evento: str, nota: str, usuario_hub: dict):
    """A baixa foi corrigida no CD: o ticket automático da baixa errada é encerrado com uma nota. Nunca derruba nada."""
    try:
        if not configurado():
            return
        BASE.atualizar()
        me = {"usuario": "erp", "nome": "ERP (automático)", "depto": "", "hub": usuario_hub.get("login", "")}
        for t in list(BASE.tickets()):
            if t.get("erp_pedido_id") == pid and t.get("origem") == "erp_auto" and t.get("erp_evento") == evento and t.get("status") in ABERTOS:
                def fn(s):
                    s.update(status="resolvido", resolvido_em=agora(), resolvido_por="erp")
                    _coment(s, me, f"🔁 {nota} — ticket encerrado automaticamente.", tipo="sistema")
                _mutar_sol(t["id"], fn, me)
    except Exception as ex:  # noqa: BLE001
        print(f"[tickets] não encerrou o ticket automático: {type(ex).__name__}: {ex}")


# ══════════════════════════════════════════════════════════════════════════════
# PALAVRA-CHAVE DO PEDIDO (login do app do cliente · futuro: confirmar entrega)
# Gerada pelo ERP quando o pedido nasce (erp._novo_pedido). Só quem tem a
# permissão "Ver a palavra-chave" no Atendimento enxerga — o módulo ERP não mostra.
# ══════════════════════════════════════════════════════════════════════════════
def ver_palavra(u: dict) -> bool:
    try:
        esq = acesso.obter_esquema(MOD)
        return bool(esq is not None and acesso.permissoes(u, MOD, esq)["acoes"].get("palavra_chave"))
    except Exception:  # noqa: BLE001
        return False


@router.get("/app/palavras")
def consultar_palavras(request: Request, q: str = ""):
    """Busca o cliente (nome, código, CPF ou telefone) e mostra a palavra-chave de cada pedido."""
    u, p, me = _contexto(request)
    _exigir(p, "palavra_chave", "ver a palavra-chave dos pedidos")
    e = _erp()
    e.ST.carregar()
    qn, qd = norm(q), digitos(q)
    if len(qn) < 2:
        return {"clientes": []}
    saida = []
    for cid, c in e.ST.dados["parceiros"].items():
        if c.get("tipo") != "cliente":
            continue
        if not ((qn in norm(c.get("nome"))) or norm(c.get("codigo")) == qn
                or (len(qd) >= 4 and (qd in digitos(c.get("doc")) or qd in digitos(c.get("telefone"))))):
            continue
        peds = sorted(((pid, d) for pid, d in e.ST.dados["pedidos"].items() if d.get("cliente_id") == cid and d.get("status") != "rascunho"),
                      key=lambda x: -(x[1].get("numero") or 0))
        saida.append({"id": cid, "nome": c.get("nome"), "codigo": c.get("codigo", ""),
                      "pedidos": [{"id": pid, "numero": d.get("numero"), "status": d.get("status"), "palavra_chave": d.get("palavra_chave") or ""}
                                  for pid, d in peds[:10]]})
        if len(saida) >= 10:
            break
    return {"clientes": saida}


@router.post("/app/palavra/{pid}/nova")
def nova_palavra(pid: str, request: Request):
    """Troca a palavra-chave de um pedido (ex.: o cliente perdeu ou ela vazou)."""
    u, p, me = _contexto(request)
    _exigir(p, "palavra_chave", "trocar a palavra-chave")
    e = _erp()
    e.ST.carregar()
    with e.ST.trava:
        tx = e.Tx(u)
        ped = tx.get("pedidos", pid)
        if not ped:
            raise HTTPException(404, "Pedido não encontrado.")
        ped["palavra_chave"] = e.gerar_palavra()
        ped["atualizado_em"] = e.agora()
        tx.put("pedidos", pid, ped)
        tx.commit()
    return {"ok": True, "palavra_chave": ped["palavra_chave"]}


@router.post("/app/palavras/gerar")
def gerar_palavras_antigas(request: Request):
    """Pedidos criados antes da palavra-chave existir ganham uma agora (rascunho e cancelado ficam de fora)."""
    u, p, me = _contexto(request)
    _exigir(p, "configurar", "gerar palavras-chave")
    e = _erp()
    e.ST.carregar()
    feitos = 0
    with e.ST.trava:
        tx = e.Tx(u)
        for pid, d in list(e.ST.dados["pedidos"].items()):
            if d.get("palavra_chave") or d.get("status") in ("cancelado", "rascunho"):
                continue
            ped = tx.get("pedidos", pid)
            ped["palavra_chave"] = e.gerar_palavra()
            tx.put("pedidos", pid, ped)
            feitos += 1
        tx.commit()
    return {"ok": True, "feitos": feitos}



# ══════════════════════════════════════════════════════════════════════════════
# CHAMADO ÚNICO POR CLIENTE (a tela de atendimento abre o cliente inteiro)
# ══════════════════════════════════════════════════════════════════════════════
def _sols_visiveis(cid: str, p: dict, me: dict) -> list[dict]:
    c = (BASE.cont or {}).get(cid)
    if not c:
        raise HTTPException(404, "Chamado não encontrado.")
    sols = []
    for s in c.get("solicitacoes", []):
        t = {**s, "id": compor(cid, s.get("sid", "legacy")), "cliente_codigo": s.get("cliente_codigo") or c.get("cliente_codigo", ""),
             "cliente_nome": s.get("cliente_nome") or c.get("cliente_nome", "")}
        sols.append(t)
    if not any(visivel(t, p, me) for t in sols):
        raise HTTPException(403, "Você não tem acesso a este chamado.")
    return sols


@router.get("/cliente/{cid}")
def chamado_do_cliente(cid: str, request: Request):
    """O chamado inteiro: chat ativo + todas as solicitações (cada uma com cor, SLA e pendências) + pedidos do ERP."""
    u, p, me = _contexto(request)
    sols = _sols_visiveis(cid, p, me)
    agora_dt = datetime.now(BRT)
    saida = [{**t, "sla": sla_info(t, agora_dt), "cor": cor_de(t), "chat": eh_chat(t), "pend_abertas": [x.get("id") for x in pend_abertas(t)],
              "nao_visto": nao_visto(t, me)} for t in sols]
    saida.sort(key=lambda t: (not (t["chat"] and t.get("status") in ABERTOS), t.get("status") not in ABERTOS, str(t.get("criado_em") or "")))
    ref = next((t for t in sols if t.get("erp_cliente_id")), sols[0])
    junto = {**ref, "erp_pedido_id": None,
             "erp_trocas": [x for t in sols for x in ([{"id": t["erp_pedido_id"]}] if t.get("erp_pedido_id") else []) + list(t.get("erp_trocas") or [])]}
    c = BASE.cont[cid]
    return {"cid": cid, "cliente": {"codigo": c.get("cliente_codigo") or ref.get("cliente_codigo"), "nome": c.get("cliente_nome") or ref.get("cliente_nome"),
                                    "telefone": next((t.get("cliente_telefone") for t in sols if t.get("cliente_telefone")), "")},
            "dono": dono_do_chamado(c), "solicitacoes": saida, "interno": all(t.get("interno") for t in sols),
            "erp": erp_do_ticket(junto, u) if _erp_ligado() and not all(t.get("interno") for t in sols) else None}


def _erp_do_container(cid: str) -> str:
    c = BASE.cont.get(cid)
    cod = str((c or {}).get("cliente_codigo") or "").upper()
    e = _erp()
    if not cod or not e:
        raise HTTPException(404, "Cliente não encontrado.")
    e.ST.carregar()
    pid = next((k for k, v in e.ST.dados["parceiros"].items() if v.get("tipo") == "cliente" and str(v.get("codigo") or "").upper() == cod), None)
    if not pid:
        raise HTTPException(404, "Este cliente não está no ERP (visitante sem cadastro).")
    return pid


@router.get("/cliente/{cid}/app-acesso")
def app_acesso(cid: str, request: Request):
    """Acesso do cliente ao app: senha criada, bloqueios e aparelhos conectados."""
    u, p, me = _contexto(request)
    import cliente_acesso
    return cliente_acesso.resumo_central(_erp_do_container(cid))


@router.post("/cliente/{cid}/app-acesso")
async def app_acesso_acao(cid: str, request: Request):
    """Central: desconectar um aparelho (ou todos) e destravar a validação/senha do cliente."""
    u, p, me = _contexto(request)
    _exigir(p, "atender", "mexer no acesso do cliente")
    d = await request.json()
    import cliente_acesso
    return cliente_acesso.acao_central(_erp_do_container(cid), str(d.get("acao") or ""), str(d.get("aparelho") or ""))


@router.post("/cliente/{cid}/chamar")
async def chamar_cliente(cid: str, request: Request):
    """Botão "Chamar cliente" (Conversa do cliente): manda a mensagem no chat dele (ou abre um) e avisa o celular
    — app e/ou link de atendimento. O chat fica na fila "Chamei" até o cliente responder."""
    u, p, me = _contexto(request)
    _exigir(p, "atender", "atender clientes")
    c = BASE.cont.get(cid)
    if not c or not c.get("cliente_codigo"):
        raise HTTPException(404, "Cliente não encontrado.")
    d = await request.json()
    import cliente_app
    return cliente_app.chamar_por_codigo(c["cliente_codigo"], d.get("texto"), {"login": me["usuario"], "nome": me["nome"]})


@router.post("/cliente/{cid}/dono")
async def dono_cliente(cid: str, request: Request):
    """Assumir/transferir o CLIENTE: vale para todas as solicitações abertas (e o chat)."""
    u, p, me = _contexto(request)
    sols = _sols_visiveis(cid, p, me)
    c = await request.json()
    alvo = str(c.get("atribuir") or "")
    sem_dono = not any((t.get("atendentes") or t.get("atribuido_para")) for t in sols if t.get("status") in ABERTOS)
    if alvo == me["usuario"] and sem_dono:
        _exigir(p, "atender", "assumir atendimentos")
    else:
        _exigir(p, "transferir", "transferir atendimentos")
    return {"ok": True, "feitas": _atribuir_cliente(cid, alvo, me)}


def _atribuir_cliente(cid: str, alvo: str, me: dict) -> int:
    nome = usuarios().get(alvo, {}).get("nome", alvo) if alvo else "ninguém"

    def mutar(cont):
        ag = agora()
        n = 0
        for i, s in enumerate(cont.get("solicitacoes", [])):
            if s.get("status") not in ABERTOS:
                continue
            s = dict(s)
            s["atendentes"] = [alvo] if alvo else []
            s["atribuido_para"] = alvo
            if alvo and s.get("status") == "aberto":
                s["status"] = "em_andamento"
            _coment(s, me, f"Cliente atribuído a {nome}", tipo="sistema")
            s["atualizado_em"] = ag
            cont["solicitacoes"][i] = s
            n += 1
        cont["atualizado_em"] = ag
        return n
    _, n = _transacao(cid, mutar)
    return n


def _candidatos(me: dict, setor: str | None = None) -> list[tuple]:
    """Clientes com chat/solicitação aberta SEM DONO no setor da pessoa (gestor: qualquer setor).
    Ordem: cliente esperando no app → chat → menor SLA."""
    BASE.atualizar()
    agora_dt, por = datetime.now(BRT), {}
    filtro = setor if setor is not None else ("" if me.get("perfil") == "gestor" else me.get("depto", ""))
    for t in BASE.tickets():
        if t.get("status") not in ABERTOS or t.get("atendentes") or t.get("atribuido_para") or t.get("interno"):
            continue
        if filtro and norm(t.get("departamento")) != norm(filtro):
            continue
        sla = sla_info(t, agora_dt).get("min")
        chave = (0 if t.get("app_pendente") else 1 if eh_chat(t) else 2, sla if sla is not None else 1e9)
        cid = decompor(t["id"])[0]
        if cid not in por or chave < por[cid][0]:
            por[cid] = (chave, eh_chat(t))
    return sorted(((v[0], cid, v[1]) for cid, v in por.items()), key=lambda x: x[0])


# ══════════════════════════════════════════════════════════════════════════════
# DISTRIBUIÇÃO AUTOMÁTICA dos atendimentos (chats do app/link)
#   O chat sem dono vai para alguém do SETOR do chat que esteja ONLINE (botão de status) e abaixo do limite
#   de atendimentos simultâneos (Ajustes › Setor e perfil; 0 = só tickets). Quem tem menos chats recebe
#   primeiro; empate → quem recebeu há mais tempo. Tickets continuam no "Pegar o próximo".
#   Roda quando o cliente abre um chat e a cada sinal/consulta do CX (no máximo a cada 5 s).
# ══════════════════════════════════════════════════════════════════════════════
_ult_dist = banco.por_empresa(lambda: {"t": 0.0})
_ULT_RECEBEU = banco.por_empresa(dict)
_trava_dist = threading.Lock()
SISTEMA = {"usuario": "distribuicao", "nome": "Distribuição automática", "depto": "", "hub": ""}


def chats_ativos_de(usuario: str) -> int:
    return sum(1 for t in BASE.tickets() if eh_chat(t) and t.get("status") in ABERTOS
               and (t.get("atribuido_para") == usuario or usuario in (t.get("atendentes") or [])))


def pode_receber(usuario: str) -> bool:
    lim = limite_de(usuario)
    return disponivel(usuario) and lim != 0 and (lim is None or chats_ativos_de(usuario) < lim)


def distribuir(forcar: bool = False) -> list[tuple[str, str]]:
    """Entrega os chats sem dono. Devolve [(cid, usuario)] do que entregou."""
    agora_s = time.time()
    st = _ult_dist
    if not forcar and agora_s - st["t"] < 5:
        return []
    if not _trava_dist.acquire(blocking=False):
        return []
    feitos = []
    try:
        st["t"] = agora_s
        if not any(p.get("status") == "online" for p in PRESENCA.values()):
            return []
        usu = usuarios()
        fila = {}
        for t in BASE.tickets():
            if not eh_chat(t) or t.get("status") not in ABERTOS or t.get("atendentes") or t.get("atribuido_para") or t.get("interno"):
                continue
            cid = decompor(t["id"])[0]
            chave = (0 if t.get("app_pendente") else 1, str(t.get("app_pendente_desde") or t.get("criado_em") or ""))
            if cid not in fila or chave < fila[cid][0]:
                fila[cid] = (chave, t.get("departamento") or "")
        for cid, (_, setor) in sorted(fila.items(), key=lambda kv: kv[1][0]):
            aptos = [k for k, v in usu.items() if norm(v.get("depto")) == norm(setor) and pode_receber(k)] if setor else []
            if not aptos:
                continue
            alvo = min(aptos, key=lambda k: (chats_ativos_de(k), _ULT_RECEBEU.get(k, 0)))
            if _atribuir_cliente(cid, alvo, {**SISTEMA, "nome": f"Distribuição automática → {usu.get(alvo, {}).get('nome', alvo)}"}):
                _ULT_RECEBEU[alvo] = time.time()
                feitos.append((cid, alvo))
    except Exception as ex:  # noqa: BLE001
        print(f"[distribuição] falhou: {ex}")
    finally:
        _trava_dist.release()
    return feitos


def fila_sem_dono(me: dict, setor: str | None = None) -> dict:
    c = _candidatos(me, setor) if setor or me.get("depto") or me.get("perfil") == "gestor" else []
    return {"clientes": len(c), "chats": sum(1 for x in c if x[2]), "aguardando_app": sum(1 for x in c if x[0][0] == 0)}


@router.get("/presenca")
def ver_presenca(request: Request, inicio: int = 0, ativo: int = 0, ocioso: int = 0):
    """O botão de status da barra do hub chama a cada 30 s (é o "sinal").
    inicio=1: abriu o hub · ativo=1: a pessoa mexeu (clique, tecla, trocou de aba) · ocioso=1: 5 min sem mexer.
    Ociosa ou sem sinal → Offline AUTOMÁTICO; mexeu de novo → volta Online. Offline escolhido no botão só sai no botão
    (ou no primeiro acesso de outro dia)."""
    u, p, me = _contexto(request)
    usu, agora_s = me["usuario"], time.time()
    hoje = datetime.now(BRT).strftime("%Y-%m-%d")
    with _trava_pres:
        atual = PRESENCA.get(usu)
        if atual and atual["status"] != "offline" and agora_s - atual["ping"] > SEM_SINAL_SEG:   # ficou sem sinal: fecha o trecho
            _mudar(usu, "offline", atual["ping"] + 60, fim_anterior=atual["ping"] + 60, auto=True)
            atual = PRESENCA[usu]
        manual_velho = bool(atual and atual["status"] == "offline" and not atual.get("auto")
                            and datetime.fromtimestamp(atual["desde"], BRT).strftime("%Y-%m-%d") != hoje)
        volta = not atual or (atual["status"] == "offline" and (atual.get("auto") or (inicio and manual_velho)))
        if (inicio or ativo) and volta:
            _mudar(usu, "online", agora_s)
        elif ocioso and atual and atual["status"] == "online":
            _mudar(usu, "offline", agora_s, auto=True)
        elif atual and atual["status"] != "offline":
            atual["ping"] = agora_s
    distribuir()
    st = presenca(usu)
    meus = [t for t in BASE.tickets() if eh_chat(t) and t.get("status") in ABERTOS and atribuido(t, me)]
    return {"status": st["status"], "desde": st["desde"], "auto": bool(st.get("auto")), "pausas": pausas(), "limite": limite_de(usu), "nome": me["nome"],
            "chats": len(meus), "aguardando": sum(1 for t in meus if t.get("app_pendente"))}


@router.post("/presenca")
async def mudar_presenca(request: Request):
    u, p, me = _contexto(request)
    d = await request.json()
    st = str(d.get("status") or "")
    if st not in ({"online", "offline"} | {x["id"] for x in pausas()}):
        raise HTTPException(400, "Status inválido.")
    with _trava_pres:
        _mudar(me["usuario"], st, time.time())
    if st == "online":
        distribuir(forcar=True)
    return {"ok": True, "status": st}


@router.post("/proximo")
def pegar_proximo(request: Request):
    """Pegar o próximo: o cliente mais urgente sem dono do meu setor vem para mim (sem precisar ver a fila inteira)."""
    u, p, me = _contexto(request)
    _exigir(p, "atender", "assumir atendimentos")
    if not me.get("depto") and me.get("perfil") != "gestor":
        raise HTTPException(400, "Seu usuário está sem setor — peça para definir em Ajustes.")
    lim = limite_de(me["usuario"])
    cheio = lim is not None and chats_ativos_de(me["usuario"]) >= lim   # no limite (ou 0 = só tickets): pega só ticket
    for _, cid, _chat in _candidatos(me):
        if cheio and _chat:
            continue
        if _atribuir_cliente(cid, me["usuario"], me):
            return {"ok": True, "cid": cid}
    raise HTTPException(404, "Ninguém esperando no seu setor agora. 🎉")


@router.get("/equipe")
def equipe(request: Request, dias: int = 1, setor: str = "", de: str = "", ate: str = ""):
    """Painel da equipe: quem está online e a produtividade no período (hoje / 7 / 30 dias).
    Atendente vê só a própria linha; supervisor, o setor dele; gestor, todos (ou um setor)."""
    u, p, me = _contexto(request)
    pf = me["perfil"]
    dias = max(1, min(int(dias or 1), 90))
    corte = (datetime.now(BRT) - timedelta(days=dias - 1)).strftime("%Y-%m-%d")
    hoje = datetime.now(BRT).strftime("%Y-%m-%d")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", de or ""):   # período personalizado (Gestão)
        corte, fim_p = de, ate if re.match(r"^\d{4}-\d{2}-\d{2}$", ate or "") and ate >= de else hoje
    else:
        fim_p = hoje
    alvo_setor = setor if pf == "gestor" else me.get("depto", "")
    usu = usuarios()
    if pf == "atendente":
        quem = {me["usuario"]}
    else:
        quem = {k for k, v in usu.items() if not alvo_setor or norm(v.get("depto")) == norm(alvo_setor)}
    linhas = {k: {"usuario": k, "nome": usu.get(k, {}).get("nome", k), "depto": usu.get(k, {}).get("depto", ""), "online": online(k),
                  "visto_em": ONLINE.get(k), "status": presenca(k)["status"], "limite": limite_de(k), "chats_atendidos": 0, "tickets_concluidos": 0, "respostas": 0,
                  "chats_ativos": 0, "cliente_aguardando": 0, "tickets_pendentes": 0, "vencidos": 0} for k in quem}
    agora_dt = datetime.now(BRT)
    for t in BASE.tickets():
        chat, aberto = eh_chat(t), t.get("status") in ABERTOS
        if aberto:
            for k in set(t.get("atendentes") or []) | ({t.get("atribuido_para")} if t.get("atribuido_para") else set()):
                if k in linhas:
                    L = linhas[k]
                    if chat:
                        L["chats_ativos"] += 1
                        L["cliente_aguardando"] += bool(t.get("app_pendente"))
                    else:
                        L["tickets_pendentes"] += 1
                        L["vencidos"] += sla_info(t, agora_dt).get("estado") == "venc"
        elif corte <= str(t.get("resolvido_em") or "")[:10] <= fim_p and t.get("resolvido_por") in linhas:
            linhas[t["resolvido_por"]]["chats_atendidos" if chat else "tickets_concluidos"] += 1
        for c in t.get("comentarios") or []:   # o que o cliente viu: resposta no chat + registro de contato
            if c.get("usuario") in linhas and c.get("tipo") in ("resposta", "contato") and corte <= str(c.get("data") or "")[:10] <= fim_p:
                linhas[c["usuario"]]["respostas"] += 1
    for k, L in linhas.items():   # tempo logado (Online) e em pausa no período — do botão de status
        tm = tempos(k, corte, fim_p)["min"]
        L["min_online"] = tm.get("online", 0)
        L["min_pausa"] = sum(v for s2, v in tm.items() if s2 not in ("online", "offline"))
        L["pausas"] = {s2: v for s2, v in tm.items() if s2 not in ("online", "offline")}
        L["desde"] = (PRESENCA.get(k) or {}).get("desde")
    pessoas = sorted(linhas.values(), key=lambda x: (not x["online"], -(x["chats_atendidos"] + x["tickets_concluidos"]), norm(x["nome"])))
    return {"perfil": pf, "dias": dias, "de": corte, "ate": fim_p, "setor": alvo_setor, "pessoas": pessoas, "pausas": pausas(), "fila": fila_sem_dono(me, alvo_setor if alvo_setor or pf == "gestor" else None),
            "departamentos": departamentos() if pf == "gestor" else []}


@router.get("/pesquisas")
def ver_pesquisas(request: Request, de: str = "", ate: str = ""):
    """Gestão › CSAT/NPS: notas das pesquisas (compra, atendimento, entrega) no período."""
    u, p, me = _contexto(request)
    import regua
    hoje = datetime.now(BRT).strftime("%Y-%m-%d")
    de = de if re.match(r"^\d{4}-\d{2}-\d{2}$", de or "") else (datetime.now(BRT) - timedelta(days=29)).strftime("%Y-%m-%d")
    ate = ate if re.match(r"^\d{4}-\d{2}-\d{2}$", ate or "") and ate >= de else hoje
    return regua.resumo(de, ate, usuarios())


@router.get("/equipe/curva")
def curva(request: Request, usuarios_: str = "", de: str = "", ate: str = ""):
    """Curva de produtividade (Gestão): um atendente, vários, ou todos (visão geral da operação).
    Um dia → por HORA; mais de um → por DIA. Chats atendidos, tickets concluídos, respostas e minutos Online."""
    u, p, me = _contexto(request)
    pf = me["perfil"]
    hoje = datetime.now(BRT).strftime("%Y-%m-%d")
    de = de if re.match(r"^\d{4}-\d{2}-\d{2}$", de or "") else hoje
    ate = ate if re.match(r"^\d{4}-\d{2}-\d{2}$", ate or "") and ate >= de else hoje
    if (datetime.fromisoformat(ate) - datetime.fromisoformat(de)).days > 92:
        raise HTTPException(400, "Escolha um período de até 3 meses.")
    usu = usuarios()
    pedidos = [x for x in str(usuarios_ or request.query_params.get("usuarios") or "").split(",") if x]
    if pf == "atendente":
        quem = {me["usuario"]}
    else:
        visiveis = {k for k, v in usu.items() if pf == "gestor" or norm(v.get("depto")) == norm(me.get("depto"))}
        quem = (set(pedidos) & visiveis) if pedidos else visiveis
    um_dia = de == ate
    rot = [f"{h:02d}h" for h in range(24)] if um_dia else []
    if not um_dia:
        d = datetime.fromisoformat(de).date()
        while d <= datetime.fromisoformat(ate).date():
            rot.append(d.isoformat())
            d += timedelta(days=1)
    idx = {r: i for i, r in enumerate(rot)}
    ser = {k: [0] * len(rot) for k in ("chats", "tickets", "respostas", "online")}

    def pos(data: str):
        data = str(data or "")
        if not (de <= data[:10] <= ate):
            return None
        return int(data[11:13]) if um_dia and len(data) >= 13 else idx.get(data[:10])

    for t in BASE.tickets():
        if t.get("resolvido_por") in quem and t.get("status") not in ABERTOS:
            i = pos(t.get("resolvido_em"))
            if i is not None:
                ser["chats" if eh_chat(t) else "tickets"][i] += 1
        for c in t.get("comentarios") or []:
            if c.get("usuario") in quem and c.get("tipo") in ("resposta", "contato"):
                i = pos(c.get("data"))
                if i is not None:
                    ser["respostas"][i] += 1
    status_min = {}
    for k in quem:
        if um_dia:
            tm = tempos(k, de, ate, por_hora=True)
            ser["online"] = [a + b for a, b in zip(ser["online"], tm["horas"])]
        else:
            tm = {"min": {}}
            for r in rot:
                m1 = tempos(k, r, r)["min"]
                ser["online"][idx[r]] += m1.get("online", 0)
                for s2, v in m1.items():
                    tm["min"][s2] = tm["min"].get(s2, 0) + v
        for s2, v in tm["min"].items():
            status_min[s2] = status_min.get(s2, 0) + v
    return {"de": de, "ate": ate, "por": "hora" if um_dia else "dia", "rotulos": rot, "series": ser, "usuarios": sorted(quem),
            "totais": {k: sum(v) for k, v in ser.items()}, "status_min": status_min, "pausas": pausas()}


@router.post("/ticket/{tid:path}/concluir-chat")
async def concluir_chat(tid: str, request: Request):
    """Fim do chat do app. modo 'anexar' → a conversa fica no histórico do chamado do cliente;
    modo 'solicitacao' → a própria conversa vira uma solicitação (motivo/submotivo/pedido) no chamado."""
    u, p, me = _contexto(request)
    _exigir(p, "encerrar", "encerrar atendimentos")
    t = _ticket(tid, p, me)
    if not eh_chat(t) or t.get("status") not in ABERTOS:
        raise HTTPException(409, "Este chat já foi concluído.")
    c = await request.json()
    modo = c.get("modo")
    if modo == "solicitacao":
        pai, filho = str(c.get("motivo_pai") or ""), str(c.get("motivo_filho") or "")
        setor_chat = str(c.get("departamento") or t.get("departamento") or "")
        arv = motivos(setor_chat)
        if pai not in arv or filho not in arv[pai]:
            raise HTTPException(400, "Escolha o motivo e o submotivo da solicitação.")
        ped = None
        if c.get("pedido_id"):
            e = _erp()
            ped = e.ST.dados["pedidos"].get(str(c["pedido_id"])) if e else None
            if not ped:
                raise HTTPException(404, "Pedido do ERP não encontrado.")
        cid = decompor(tid)[0]
        for s in ((BASE.cont or {}).get(cid) or {}).get("solicitacoes", []):
            if (not eh_chat(s) and s.get("status") in ABERTOS and norm(s.get("motivo_pai")) == norm(pai)
                    and str(s.get("erp_pedido_id") or "") == str(c.get("pedido_id") or "")):
                raise HTTPException(409, f"Já existe uma solicitação aberta de \"{pai}\"" + (f" do pedido #{ped.get('numero')}" if ped else "")
                                         + " neste chamado — anexe o chat e registre nela.")

        def fn(s):
            s["chat_iniciado_em"] = s.get("chat_iniciado_em") or s.get("criado_em")   # a conversa continua no lugar certo da linha do tempo
            s.update(app_tipo="chamado", convertido_de_chat=True, motivo_pai=pai, motivo_pai_id=pai, motivo_filho=filho,
                     assunto=filho + (f" · pedido #{ped.get('numero')}" if ped else ""), sla1_prazo_dias=_sla_motivo(pai, filho, setor_chat),
                     criado_em=agora())   # o prazo da solicitação conta a partir de agora
            if ped:
                s.update(erp_pedido_id=str(c["pedido_id"]), erp_pedido_numero=ped.get("numero"))
            if s.get("status") == "aberto":
                s["status"] = "em_andamento"
            _coment(s, me, f"💬→📋 Chat concluído e transformado em solicitação: {pai} › {filho}" + (f" (pedido #{ped.get('numero')})" if ped else ""), tipo="sistema")
    elif modo == "anexar":
        def fn(s):
            s.update(status="resolvido", resolvido_em=agora(), resolvido_por=me["usuario"], app_pendente=False)
            s.pop("app_pendente_desde", None)
            _coment(s, me, "💬 Chat concluído — a conversa fica no histórico do chamado do cliente.", tipo="sistema")
    else:
        raise HTTPException(400, "Escolha: anexar ao chamado ou virar solicitação.")
    _mutar_sol(tid, fn, me)
    return {"ok": True}
