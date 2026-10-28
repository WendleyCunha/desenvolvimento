"""
hub/secretaria.py — API da SECRETARIA (Parque Aliança) no hub.
─────────────────────────────────────────────────────────────────────────────
Lê e grava AS MESMAS coleções do Streamlit (admin-parquealianca) e do
formulário público (relatoriosparquealianca) — os três continuam em sincronia:

    membros_v2/{nome}                       cadastro (id = nome, igual ao Streamlit)
    relatorios_parque_alianca/{id}          relatórios (formulário + baixas)
    congregacoes/parque_alianca/assistencia/{tipo}_{AAAA-AAAA}   S-88 mensal (Streamlit)

E acrescenta (só o hub usa; o Streamlit ignora):
    congregacoes/parque_alianca/assistencia_reunioes/{AAAA-MM-DD}_{meio|fim}
    congregacoes/parque_alianca/fechamentos/{AAAA-MM}     S-1 "fotografado" ao fechar o mês
    congregacoes/parque_alianca/config/secretaria         grupos, pastas, regras, IT

Campos novos que o hub grava nos relatórios (o Streamlit ignora, não quebra nada):
    mes_chave "AAAA-MM", membro_id, origem, atualizado_por/_em
Excluir = status_validacao "EXCLUIDO" (os dois sistemas já escondem esse valor).

COTA GRÁTIS DO FIRESTORE — leitura econômica:
  • tudo fica em memória; o que o hub grava atualiza a memória na hora;
  • a cada 60 s (só quando alguém abre a tela) busca apenas os relatórios NOVOS
    (data_envio/timestamp maior que o último visto);
  • a cada 10 min relê o mês atual e o anterior (pega edições feitas no Streamlit);
  • leitura completa: na 1ª abertura, a cada 6 h ou pelo botão "Recarregar tudo".
"""
from __future__ import annotations

import base64
import re
import threading
import time
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

import acesso
import banco
import secretaria_pdf as PDF
import secretaria_regras as R

router = APIRouter(prefix="/api/secretaria")
MOD = "secretaria"
COL_MEMBROS = "membros_v2"
COL_REL = "relatorios_parque_alianca"
CONG = "parque_alianca"
TIPOS_REUNIAO = {"meio": "Reunião do Meio de Semana", "fim": "Reunião do Fim de Semana"}
CAMPOS_SENSIVEIS = ["data_nascimento", "data_batismo", "telefone_emergencia"]
CAMPOS_MEMBRO = ["nome_oficial", "categoria", "genero", "classe", "cargo", "status", "grupo", "data_nascimento",
                 "data_batismo", "telefone_emergencia", "surdo", "cego", "preso", "saiu_em", "saiu_motivo",
                 "inicio_chave", "mes_inicio", "observacao"]
GENEROS = ["", "Masculino", "Feminino"]
CLASSES = ["", "Outras ovelhas", "Ungido"]
CARGOS = ["Ancião", "Servo ministerial", "Pioneiro regular", "Pioneiro especial", "Missionário em campo"]

ITS_PADRAO = [
    {"titulo": "Secretário", "ref": "1:13"},
    {"titulo": "Mudança do irmão que serve como secretário", "ref": "1:26"},
    {"titulo": "Responsabilidades do secretário", "ref": "1:14"},
    {"titulo": "Análise das atividades dos pioneiros regulares", "ref": "14:5-7"},
    {"titulo": "Cartas de apresentação", "ref": "17:11"},
    {"titulo": "Correspondência e arquivo da congregação", "ref": "17:2, 6"},
    {"titulo": "Correspondências enviadas para o corpo de anciãos", "ref": "17:9"},
    {"titulo": "Preparativos para enfrentar desastres", "ref": "11:3.1; 11:11"},
    {"titulo": "Publicadores recém-batizados", "ref": "10:2.1"},
    {"titulo": "Recomendações para designação de anciãos e servos ministeriais", "ref": "5:7, 11"},
    {"titulo": "Registros de assistência às reuniões", "ref": "4:32.4; 16:12; 17:13"},
    {"titulo": "Registros de serviço de campo", "ref": "1:19.6; 3:15; 17:13-15"},
]
CONFIG_PADRAO = {"limite_aux": R.LIMITE_AUX_PADRAO, "corte_dia": R.CORTE_DIA_PADRAO, "grupos": [], "pastas": [],
                 "dia_meio": -1, "dia_fim": -1,
                 "its": ITS_PADRAO, "territorios_total": 0, "territorios_nao_trabalhados": 0, "visita_ultima": ""}


# ══════════════════════════════════════════════════════════════════════════════
# util
# ══════════════════════════════════════════════════════════════════════════════
def _db():
    return banco.db()


def _cong():
    return _db().collection("congregacoes").document(CONG)


def _agora() -> str:
    return datetime.now(R.FUSO).strftime("%Y-%m-%dT%H:%M:%S")


def _json(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, dict):
        return {str(k): _json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_json(x) for x in v]
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _int(v, minimo=0, maximo=100000) -> int:
    try:
        n = int(round(float(v)))
    except (TypeError, ValueError):
        raise HTTPException(400, f"Número inválido: {v!r}") from None
    if not minimo <= n <= maximo:
        raise HTTPException(400, f"Valor fora do limite ({minimo}–{maximo}): {n}")
    return n


def _chave(v) -> str:
    if not R.chave_valida(v):
        raise HTTPException(400, "Mês inválido (use AAAA-MM).")
    return v


def _contexto(request: Request):
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(MOD)
    if esq is None:
        raise HTTPException(404, "Módulo secretaria não encontrado (falta modulos/secretaria.html).")
    p = acesso.permissoes(u, MOD, esq)
    if not p["acoes"].get("acessar"):
        raise HTTPException(403, "Sem acesso à Secretaria.")
    if not banco.configurado():
        raise HTTPException(503, "Banco não configurado: falta FIRESTORE_CREDS no Render.")
    return u, p


def _exigir(p: dict, acao: str, texto: str):
    if not p["acoes"].get(acao):
        raise HTTPException(403, f"Sem permissão para {texto}.")


def _nivel(p: dict, campo: str) -> str:
    return p["campos"].get(campo, "editar")


# ══════════════════════════════════════════════════════════════════════════════
# MEMÓRIA (cache econômico)
# ══════════════════════════════════════════════════════════════════════════════
class _Base:
    INCREMENTAL, RECENTE, COMPLETA = 60, 600, 6 * 3600

    def __init__(self) -> None:
        self.trava = threading.RLock()
        self.membros: dict[str, dict] | None = None
        self.rels: dict[str, dict] = {}
        self.t_completa = self.t_recente = self.t_incremental = 0.0
        self.ultimo_visto: datetime | None = None
        self.cfg: dict | None = None
        self.assist_mes: dict[str, dict] = {}      # doc_id → meses (Streamlit)
        self.t_assist: dict[str, float] = {}
        self.reunioes: dict[str, dict] | None = None
        self.fechamentos: dict[str, dict] | None = None
        self.leituras = 0
        self._linhas = None

    # ── relatórios ──
    def _marcar(self, d: dict):
        for campo in ("data_envio", "timestamp"):
            v = d.get(campo)
            if isinstance(v, datetime):
                v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
                if not self.ultimo_visto or v > self.ultimo_visto:
                    self.ultimo_visto = v

    def _guardar(self, docs):
        n = 0
        for doc in docs:
            d = doc.to_dict() or {}
            self.rels[doc.id] = {**d, "id": doc.id}
            self._marcar(d)
            n += 1
        self.leituras += n
        self._linhas = None
        return n

    def completa(self):
        with self.trava:
            self.membros = {d.id: (d.to_dict() or {}) for d in _db().collection(COL_MEMBROS).stream(timeout=banco.TIMEOUT)}
            self.leituras += len(self.membros)
            self.rels = {}
            self.ultimo_visto = None
            self._guardar(_db().collection(COL_REL).stream(timeout=banco.TIMEOUT))
            self.t_completa = self.t_recente = self.t_incremental = time.time()
            self._linhas = None

    def atualizar(self, forcar: bool = False):
        with self.trava:
            agora = time.time()
            if forcar or self.membros is None or agora - self.t_completa > self.COMPLETA:
                return self.completa()
            from google.cloud.firestore_v1.base_query import FieldFilter
            if agora - self.t_recente > self.RECENTE:
                atual = R.chave_por_data(datetime.now(R.FUSO), self.config().get("corte_dia", R.CORTE_DIA_PADRAO))
                rotulos = sorted(set(R.rotulos_possiveis(atual) + R.rotulos_possiveis(R.somar(atual, -1))))
                q = _db().collection(COL_REL).where(filter=FieldFilter("mes_referencia", "in", rotulos))
                docs = list(q.stream(timeout=banco.TIMEOUT))
                self._guardar(docs)
                vistos = {doc.id for doc in docs}
                # some do cache o que foi apagado direto no banco (só nesses meses)
                for rid, r in list(self.rels.items()):
                    if r.get("mes_referencia") in rotulos and rid not in vistos:
                        self.rels.pop(rid, None)
                self.membros = {d.id: (d.to_dict() or {}) for d in _db().collection(COL_MEMBROS).stream(timeout=banco.TIMEOUT)}
                self.leituras += len(self.membros)
                self.t_recente = self.t_incremental = agora
                self._linhas = None
            elif agora - self.t_incremental > self.INCREMENTAL and self.ultimo_visto:
                for campo in ("data_envio", "timestamp"):
                    q = _db().collection(COL_REL).where(filter=FieldFilter(campo, ">", self.ultimo_visto))
                    self._guardar(q.stream(timeout=banco.TIMEOUT))
                self.t_incremental = agora

    def linhas(self) -> list[dict]:
        with self.trava:
            if self._linhas is None:
                self._linhas = R.preparar(list(self.rels.values()), self.membros or {}, self.config().get("limite_aux", 15))
            return self._linhas

    def gravar_rel(self, rid: str, dados: dict, merge=True):
        ref = _db().collection(COL_REL).document(rid)
        ref.set(dados, merge=merge, timeout=banco.TIMEOUT)
        with self.trava:
            atual = self.rels.get(rid, {}) if merge else {}
            self.rels[rid] = {**atual, **dados, "id": rid}
            self._linhas = None

    def gravar_membro(self, mid: str, dados: dict, merge=True):
        _db().collection(COL_MEMBROS).document(mid).set(dados, merge=merge, timeout=banco.TIMEOUT)
        with self.trava:
            atual = (self.membros or {}).get(mid, {}) if merge else {}
            self.membros[mid] = {**atual, **dados}
            self._linhas = None

    # ── config ──
    def config(self) -> dict:
        if self.cfg is None:
            snap = _cong().collection("config").document("secretaria").get(timeout=banco.TIMEOUT)
            self.leituras += 1
            self.cfg = {**CONFIG_PADRAO, **((snap.to_dict() or {}) if snap.exists else {})}
        return self.cfg

    def salvar_config(self, novo: dict):
        self.cfg = {**self.config(), **novo}
        _cong().collection("config").document("secretaria").set(self.cfg, timeout=banco.TIMEOUT)
        self._linhas = None

    # ── assistência ──
    def doc_assist(self, tipo: str, as_: int) -> str:
        slug = TIPOS_REUNIAO[tipo].lower().replace(" ", "_").replace("ã", "a").replace("é", "e")
        return f"{slug}_{as_ - 1}-{as_}"

    def meses_streamlit(self, tipo: str, as_: int) -> dict:
        did = self.doc_assist(tipo, as_)
        if did not in self.assist_mes or time.time() - self.t_assist.get(did, 0) > 300:
            snap = _cong().collection("assistencia").document(did).get(timeout=banco.TIMEOUT)
            self.leituras += 1
            self.assist_mes[did] = ((snap.to_dict() or {}).get("meses") or {}) if snap.exists else {}
            self.t_assist[did] = time.time()
        return self.assist_mes[did]

    def todas_reunioes(self) -> dict[str, dict]:
        if self.reunioes is None:
            self.reunioes = {d.id: (d.to_dict() or {}) for d in
                             _cong().collection("assistencia_reunioes").stream(timeout=banco.TIMEOUT)}
            self.leituras += len(self.reunioes)
        return self.reunioes

    def todos_fechamentos(self) -> dict[str, dict]:
        if self.fechamentos is None:
            self.fechamentos = {d.id: (d.to_dict() or {}) for d in
                                _cong().collection("fechamentos").stream(timeout=banco.TIMEOUT)}
            self.leituras += len(self.fechamentos)
        return self.fechamentos


BASE = _Base()


def _mes_atual() -> str:
    return R.chave_por_data(datetime.now(R.FUSO), BASE.config().get("corte_dia", R.CORTE_DIA_PADRAO))


# ══════════════════════════════════════════════════════════════════════════════
# ASSISTÊNCIA — junta reuniões (hub) + meses (Streamlit)
# ══════════════════════════════════════════════════════════════════════════════
def _assist_ano(as_: int) -> dict:
    reun = BASE.todas_reunioes()
    saida = {"meio": {}, "fim": {}, "fonte": {"meio": {}, "fim": {}}, "reunioes": {"meio": {}, "fim": {}}}
    for tipo in ("meio", "fim"):
        ms = BASE.meses_streamlit(tipo, as_)
        for ch in R.meses_do_as(as_):
            lista = sorted([{"id": rid, **r} for rid, r in reun.items()
                            if r.get("tipo") == tipo and str(r.get("data", ""))[:7] == ch], key=lambda x: x["data"])
            saida["reunioes"][tipo][ch] = lista
            nome_mes = R.MESES_TITULO[R.partes(ch)[1] - 1]
            if lista:
                saida[tipo][ch] = R.resumo_reunioes(lista)
                saida["fonte"][tipo][ch] = "reunioes"
            elif nome_mes in ms and (ms[nome_mes].get("qtd") or ms[nome_mes].get("total")):
                saida[tipo][ch] = R.resumo_mes(ms[nome_mes].get("qtd"), ms[nome_mes].get("total"))
                saida["fonte"][tipo][ch] = "mensal"
    saida["suspeitos"] = {t: R.suspeitos_assistencia(saida[t]) for t in ("meio", "fim")}
    saida["media_anual"] = {t: R.media_anual([saida[t].get(c, {}).get("media", 0) for c in R.meses_do_as(as_)])
                            for t in ("meio", "fim")}
    return saida


def _gravar_mes_streamlit(tipo: str, ch: str, qtd: int, total: int):
    """Mantém o S-88 do Streamlit igual ao do hub (só o mês mexido)."""
    as_ = R.ano_servico(ch)
    did = BASE.doc_assist(tipo, as_)
    nome_mes = R.MESES_TITULO[R.partes(ch)[1] - 1]
    ref = _cong().collection("assistencia").document(did)
    ref.set({"tipo_reuniao": TIPOS_REUNIAO[tipo], "ano_referencia": f"{as_ - 1}/{as_}",
             "meses": {nome_mes: {"qtd": qtd, "total": total}}, "atualizado_em": _agora()}, merge=True, timeout=banco.TIMEOUT)
    BASE.meses_streamlit(tipo, as_)[nome_mes] = {"qtd": qtd, "total": total}


def _media_fim(ch: str) -> float:
    return _assist_ano(R.ano_servico(ch))["fim"].get(ch, {}).get("media", 0)


# ══════════════════════════════════════════════════════════════════════════════
# SAÍDA PARA A TELA (respeitando campos ocultos)
# ══════════════════════════════════════════════════════════════════════════════
def _membro_saida(mid: str, m: dict, p: dict, part: set[str], atual: str) -> dict:
    out = {k: m.get(k) for k in CAMPOS_MEMBRO if k in m}
    for c in CAMPOS_SENSIVEIS:
        if _nivel(p, c) == "oculto":
            out.pop(c, None)
    out.update(id=mid, nome_oficial=m.get("nome_oficial") or mid, regular=R.eh_regular(m), cargo=R.cargos(m),
               situacao=R.situacao(m, part, atual), situacao_anterior=R.situacao(m, part, R.somar(atual, -1)),
               ultimo=R.ultimo_mes_com_participacao(part, atual), inicio=R.inicio_do_membro(m))
    return _json(out)


def _linha_saida(ln: dict, p: dict) -> dict:
    out = dict(ln)
    if _nivel(p, "observacoes") == "oculto":
        out["observacoes"] = ""
    return out


@router.get("/base")
def base(request: Request, mes: str = "", recarregar: int = 0):
    u, p = _contexto(request)
    if recarregar:
        _exigir(p, "ajustes", "recarregar tudo do banco")
    BASE.atualizar(forcar=bool(recarregar))
    cfg = BASE.config()
    atual = _mes_atual()
    ch = mes if R.chave_valida(mes) else atual
    linhas = BASE.linhas()
    membros = BASE.membros or {}
    part = R.participacoes(linhas)
    meses = sorted({ln["chave"] for ln in linhas if ln["chave"]} | {atual, ch}, reverse=True)
    do_mes = [ln for ln in linhas if ln["chave"] == ch]
    fech = BASE.todos_fechamentos().get(ch)
    return _json({
        "perm": p, "usuario": acesso.publico(u), "mes": ch, "mes_atual": atual, "meses": meses,
        "config": {k: v for k, v in cfg.items()},
        "opcoes": {"generos": GENEROS, "classes": CLASSES, "cargos": CARGOS, "categorias": R.CATEGORIAS},
        "membros": [_membro_saida(mid, m, p, part.get(mid, set()), ch) for mid, m in membros.items()],
        "relatorios": [_linha_saida(ln, p) for ln in do_mes if ln["situacao"] == "IDENTIFICADO"],
        "triagem": [_linha_saida(ln, p) for ln in linhas if ln["situacao"] in ("TRIAGEM", "SEM_MES")],
        "pendencias": R.pendencias(ch, linhas, membros, part),
        "s1": R.s1(ch, linhas, membros, _media_fim(ch), part),
        "fechamento": fech,
        "fechados": sorted(BASE.todos_fechamentos().keys()),
        "rotulos_errados": sum(1 for ln in linhas if ln["rotulo_errado"] and ln["situacao"] != "SEM_MES"),
        "duplicados": sum(1 for ln in do_mes if ln["duplicado"]),
        "sync": {"completa": BASE.t_completa, "recente": BASE.t_recente, "leituras": BASE.leituras,
                 "total_relatorios": len(BASE.rels)},
    })


@router.get("/membro/{mid}")
def historico_membro(mid: str, request: Request):
    _, p = _contexto(request)
    BASE.atualizar()
    membros = BASE.membros or {}
    if mid not in membros:
        raise HTTPException(404, "Membro não encontrado.")
    linhas = BASE.linhas()
    part = R.participacoes(linhas).get(mid, set())
    meus = sorted([_linha_saida(ln, p) for ln in linhas if ln["membro_id"] == mid], key=lambda x: x["chave"] or "", reverse=True)
    atual = _mes_atual()
    anos = sorted({R.ano_servico(ln["chave"]) for ln in meus if ln["chave"]} | {R.ano_servico(atual)}, reverse=True)
    ev = R.eventos(membros[mid], part, [R.somar(atual, -i) for i in range(36, -1, -1)])
    return _json({"membro": _membro_saida(mid, membros[mid], p, part, atual), "relatorios": meus, "anos": anos, "eventos": ev})


# ══════════════════════════════════════════════════════════════════════════════
# RELATÓRIOS
# ══════════════════════════════════════════════════════════════════════════════
def _id_novo(mid: str, ch: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", R.normalizar(mid)).strip("-")[:60] or "membro"
    return f"hub_{slug}_{ch}_{int(time.time() * 1000) % 100000:05d}"


def _dados_rel(mid: str, ch: str, participou: bool, horas: int, estudos: int, obs: str, u: dict, origem: str) -> dict:
    return {"nome": (BASE.membros or {}).get(mid, {}).get("nome_oficial") or mid, "membro_id": mid,
            "mes_referencia": R.rotulo_banco(ch), "mes_chave": ch, "participou_ministerio": bool(participou),
            "horas": horas, "estudos_biblicos": estudos, "observacoes": obs, "timestamp": datetime.now(timezone.utc),
            "status_validacao": "IDENTIFICADO", "origem": origem, "atualizado_por": u["login"], "atualizado_em": _agora()}


def _ja_tem(mid: str, ch: str) -> dict | None:
    return next((ln for ln in BASE.linhas() if ln["membro_id"] == mid and ln["chave"] == ch and ln["principal"]
                 and ln["situacao"] == "IDENTIFICADO"), None)


@router.post("/relatorios")
async def lancar(request: Request):
    u, p = _contexto(request)
    _exigir(p, "lancar", "lançar relatórios")
    c = await request.json()
    BASE.atualizar()
    mid, ch = str(c.get("membro_id", "")), _chave(c.get("chave"))
    if mid not in (BASE.membros or {}):
        raise HTTPException(404, "Membro não encontrado.")
    existente = _ja_tem(mid, ch)
    if existente:
        raise HTTPException(409, f"Já existe relatório de {R.rotulo(ch)} para essa pessoa — edite o que está lá.")
    obs = str(c.get("observacoes") or "")[:300] if _nivel(p, "observacoes") == "editar" else ""
    dados = _dados_rel(mid, ch, c.get("participou", True), _int(c.get("horas", 0), 0, 400),
                       _int(c.get("estudos", 0), 0, 200), obs, u, "hub")
    if c.get("categoria_mes") in R.CATEGORIAS:
        dados["categoria_mes"] = c["categoria_mes"]
    rid = _id_novo(mid, ch)
    BASE.gravar_rel(rid, dados, merge=False)
    return {"ok": True, "id": rid}


@router.post("/relatorios/baixa-lote")
async def baixa_lote(request: Request):
    """'Dar baixa' em vários de uma vez — sem horas; diz se participaram ou não."""
    u, p = _contexto(request)
    _exigir(p, "lancar", "lançar relatórios")
    c = await request.json()
    BASE.atualizar()
    ch = _chave(c.get("chave"))
    ids = [str(x) for x in (c.get("membros") or [])][:300]
    feitos, pulados = 0, []
    lote = _db().batch()
    novos = {}
    for mid in ids:
        if mid not in (BASE.membros or {}) or _ja_tem(mid, ch):
            pulados.append(mid)
            continue
        rid = _id_novo(mid, ch) + f"{feitos:03d}"
        dados = _dados_rel(mid, ch, bool(c.get("participou", True)), 0, 0, "", u, "baixa-hub")
        lote.set(_db().collection(COL_REL).document(rid), dados)
        novos[rid] = dados
        feitos += 1
    if feitos:
        lote.commit(timeout=banco.TIMEOUT)
        with BASE.trava:
            for rid, d in novos.items():
                BASE.rels[rid] = {**d, "id": rid}
            BASE._linhas = None
    return {"ok": True, "feitos": feitos, "pulados": pulados}


@router.put("/relatorios/{rid}")
async def editar_relatorio(rid: str, request: Request):
    u, p = _contexto(request)
    c = await request.json()
    BASE.atualizar()
    atual = BASE.rels.get(rid)
    if not atual:
        raise HTTPException(404, "Relatório não encontrado (pode ter sido excluído).")
    vincular = "membro_id" in c and c["membro_id"] != atual.get("membro_id")
    _exigir(p, "triagem" if vincular and set(c) <= {"membro_id", "chave"} else "lancar", "alterar relatórios")
    novo: dict = {"atualizado_por": u["login"], "atualizado_em": _agora()}
    if "membro_id" in c:
        mid = str(c["membro_id"])
        if mid not in (BASE.membros or {}):
            raise HTTPException(404, "Membro não encontrado.")
        novo.update(membro_id=mid, nome=BASE.membros[mid].get("nome_oficial") or mid)
    ch = c.get("chave") or R.resolver_chave(atual)
    if ch:
        ch = _chave(ch)
        novo.update(mes_chave=ch, mes_referencia=R.rotulo_banco(ch))
    if "horas" in c:
        novo["horas"] = _int(c["horas"], 0, 400)
    if "estudos" in c:
        novo["estudos_biblicos"] = _int(c["estudos"], 0, 200)
    if "participou" in c:
        novo["participou_ministerio"] = bool(c["participou"])
    if "observacoes" in c:
        if _nivel(p, "observacoes") != "editar":
            raise HTTPException(403, "Sem permissão para alterar observações.")
        novo["observacoes"] = str(c["observacoes"] or "")[:300]
    if "categoria_mes" in c:
        from google.cloud import firestore
        novo["categoria_mes"] = c["categoria_mes"] if c["categoria_mes"] in R.CATEGORIAS else firestore.DELETE_FIELD
    BASE.gravar_rel(rid, novo)
    if "categoria_mes" in novo and novo["categoria_mes"] not in R.CATEGORIAS:
        with BASE.trava:
            BASE.rels[rid].pop("categoria_mes", None)
            BASE._linhas = None
    return {"ok": True}


@router.delete("/relatorios/{rid}")
def excluir_relatorio(rid: str, request: Request):
    u, p = _contexto(request)
    _exigir(p, "excluir", "excluir relatórios")
    if rid not in BASE.rels:
        return {"ok": True}
    BASE.gravar_rel(rid, {"status_validacao": "EXCLUIDO", "excluido_por": u["login"], "excluido_em": _agora()})
    return {"ok": True}


@router.post("/relatorios/corrigir-rotulos")
async def corrigir_rotulos(request: Request):
    """Lista (ou corrige) relatórios cujo mes_referencia está na convenção errada."""
    u, p = _contexto(request)
    c = await request.json()
    BASE.atualizar(forcar=bool(c.get("aplicar")))
    alvos = [ln for ln in BASE.linhas() if ln["rotulo_errado"] and ln["chave"]]
    lista = [{"id": ln["id"], "nome": ln["nome_enviado"], "de": ln["rotulo_banco"], "para": R.rotulo_banco(ln["chave"]),
              "mes": R.rotulo(ln["chave"]), "data": ln["data"]} for ln in alvos]
    if not c.get("aplicar"):
        return {"ok": True, "lista": lista}
    _exigir(p, "ajustes", "corrigir rótulos no banco")
    for i in range(0, len(alvos), 400):
        lote = _db().batch()
        for ln in alvos[i:i + 400]:
            lote.set(_db().collection(COL_REL).document(ln["id"]),
                     {"mes_referencia": R.rotulo_banco(ln["chave"]), "mes_chave": ln["chave"],
                      "rotulo_corrigido_de": ln["rotulo_banco"], "atualizado_por": u["login"]}, merge=True)
        lote.commit(timeout=banco.TIMEOUT)
    for ln in alvos:
        BASE.rels[ln["id"]].update(mes_referencia=R.rotulo_banco(ln["chave"]), mes_chave=ln["chave"])
    BASE._linhas = None
    return {"ok": True, "corrigidos": len(alvos), "lista": lista}


# ══════════════════════════════════════════════════════════════════════════════
# MEMBROS
# ══════════════════════════════════════════════════════════════════════════════
def _limpar_membro(c: dict, p: dict) -> dict:
    d = {}
    if "categoria" in c:
        d["categoria"] = c["categoria"] if c["categoria"] in (R.PUB, R.REG) else R.PUB
    for campo, opcoes in (("genero", GENEROS), ("classe", CLASSES)):
        if campo in c:
            d[campo] = c[campo] if c[campo] in opcoes else ""
    if "cargo" in c:
        d["cargo"] = [x for x in (c["cargo"] or []) if x in CARGOS]
    for campo in ("grupo", "observacao", "saiu_motivo"):
        if campo in c:
            d[campo] = str(c[campo] or "")[:200]
    for campo in ("surdo", "cego", "preso"):
        if campo in c:
            d[campo] = bool(c[campo])
    for campo in ("saiu_em", "inicio_chave"):
        if campo in c:
            d[campo] = c[campo] if R.chave_valida(c[campo]) else ""
    for campo in CAMPOS_SENSIVEIS:
        if campo in c:
            if _nivel(p, campo) != "editar":
                raise HTTPException(403, "Sem permissão para alterar dados pessoais.")
            d[campo] = str(c[campo] or "")[:40]
    if d.get("categoria") == R.REG and "Pioneiro regular" not in d.get("cargo", ["Pioneiro regular"]):
        d.setdefault("cargo", []).append("Pioneiro regular")
    if "saiu_em" in d:
        d["status"] = "Inativo" if d["saiu_em"] else "Ativo"
    return d


@router.post("/membros")
async def novo_membro(request: Request):
    u, p = _contexto(request)
    _exigir(p, "membros", "cadastrar membros")
    c = await request.json()
    BASE.atualizar()
    nome = " ".join(str(c.get("nome_oficial", "")).split())
    if len(nome) < 3 or "/" in nome:
        raise HTTPException(400, "Informe o nome completo (sem barra '/').")
    if nome in (BASE.membros or {}):
        raise HTTPException(409, "Já existe um membro com esse nome.")
    d = {"nome_oficial": nome, "categoria": R.PUB, "status": "Ativo", "cargo": [], "genero": "", "classe": "",
         "inicio_chave": _mes_atual(), "mes_inicio": R.rotulo_banco(_mes_atual()),
         "criado_por": u["login"], "criado_em": _agora(), **_limpar_membro(c, p)}
    if R.chave_valida(d.get("inicio_chave")):
        d["mes_inicio"] = R.rotulo_banco(d["inicio_chave"])
    BASE.gravar_membro(nome, d, merge=False)
    return {"ok": True, "id": nome}


@router.put("/membros/{mid}")
async def editar_membro(mid: str, request: Request):
    u, p = _contexto(request)
    _exigir(p, "membros", "editar membros")
    c = await request.json()
    BASE.atualizar()
    if mid not in (BASE.membros or {}):
        raise HTTPException(404, "Membro não encontrado.")
    d = _limpar_membro(c, p)
    if R.chave_valida(d.get("inicio_chave")):
        d["mes_inicio"] = R.rotulo_banco(d["inicio_chave"])
    novo_nome = " ".join(str(c.get("nome_oficial", mid)).split())
    if novo_nome and novo_nome != mid:
        return _renomear(mid, novo_nome, d, u)
    d.update(atualizado_por=u["login"], atualizado_em=_agora())
    BASE.gravar_membro(mid, d)
    return {"ok": True, "id": mid}


def _renomear(antigo: str, novo: str, mudancas: dict, u: dict):
    """O id do membro é o nome (padrão do Streamlit): renomear = copiar + religar relatórios."""
    if len(novo) < 3 or "/" in novo:
        raise HTTPException(400, "Nome inválido.")
    if novo in BASE.membros:
        raise HTTPException(409, "Já existe um membro com esse nome.")
    dados = {**BASE.membros[antigo], **mudancas, "nome_oficial": novo, "nome_anterior": antigo,
             "atualizado_por": u["login"], "atualizado_em": _agora()}
    meus = [ln["id"] for ln in BASE.linhas() if ln["membro_id"] == antigo]
    lote = _db().batch()
    lote.set(_db().collection(COL_MEMBROS).document(novo), dados)
    for rid in meus:
        lote.set(_db().collection(COL_REL).document(rid), {"membro_id": novo, "nome": novo}, merge=True)
    lote.delete(_db().collection(COL_MEMBROS).document(antigo))
    lote.commit(timeout=banco.TIMEOUT)
    with BASE.trava:
        BASE.membros.pop(antigo, None)
        BASE.membros[novo] = dados
        for rid in meus:
            BASE.rels[rid].update(membro_id=novo, nome=novo)
        BASE._linhas = None
    return {"ok": True, "id": novo}


# ══════════════════════════════════════════════════════════════════════════════
# ASSISTÊNCIA
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/assistencia")
def assistencia(request: Request, ano: int = 0):
    _contexto(request)
    as_ = ano or R.ano_servico(_mes_atual())
    return _json({"ano": as_, **_assist_ano(as_)})


@router.put("/assistencia/reuniao")
async def salvar_reuniao(request: Request):
    u, p = _contexto(request)
    _exigir(p, "assistencia", "lançar assistência")
    c = await request.json()
    tipo = c.get("tipo")
    if tipo not in TIPOS_REUNIAO:
        raise HTTPException(400, "Tipo de reunião inválido.")
    try:
        dia = date.fromisoformat(str(c.get("data")))
    except ValueError:
        raise HTTPException(400, "Data inválida.") from None
    rid = f"{dia.isoformat()}_{tipo}"
    reun = BASE.todas_reunioes()
    col = _cong().collection("assistencia_reunioes")
    if c.get("assistencia") in (None, ""):
        col.document(rid).delete(timeout=banco.TIMEOUT)
        reun.pop(rid, None)
    else:
        d = {"data": dia.isoformat(), "tipo": tipo, "assistencia": _int(c["assistencia"], 0, 5000),
             "obs": str(c.get("obs") or "")[:200], "atualizado_por": u["login"], "atualizado_em": _agora()}
        col.document(rid).set(d, timeout=banco.TIMEOUT)
        reun[rid] = d
    ch = R.chave(dia.year, dia.month)
    lista = [r for r in reun.values() if r.get("tipo") == tipo and str(r.get("data", ""))[:7] == ch]
    res = R.resumo_reunioes(lista)
    _gravar_mes_streamlit(tipo, ch, res["qtd"], res["total"])
    return {"ok": True, "mes": res}


@router.put("/assistencia/mes")
async def salvar_mes(request: Request):
    """Lançar o mês fechado direto (meses antigos, sem as reuniões uma a uma)."""
    u, p = _contexto(request)
    _exigir(p, "assistencia", "lançar assistência")
    c = await request.json()
    tipo, ch = c.get("tipo"), _chave(c.get("chave"))
    if tipo not in TIPOS_REUNIAO:
        raise HTTPException(400, "Tipo de reunião inválido.")
    if any(r.get("tipo") == tipo and str(r.get("data", ""))[:7] == ch for r in BASE.todas_reunioes().values()):
        raise HTTPException(409, "Esse mês já tem reuniões lançadas uma a uma — ajuste por lá.")
    _gravar_mes_streamlit(tipo, ch, _int(c.get("qtd", 0), 0, 31), _int(c.get("total", 0), 0, 100000))
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# FECHAMENTOS
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/fechamentos/{ch}")
def fechar_mes(ch: str, request: Request):
    u, p = _contexto(request)
    _exigir(p, "fechar", "fechar o mês")
    ch = _chave(ch)
    BASE.atualizar()
    linhas = BASE.linhas()
    s = R.s1(ch, linhas, BASE.membros or {}, _media_fim(ch))
    cats = {ln["membro_id"]: ln["categoria"] for ln in R.validas(linhas) if ln["chave"] == ch}
    d = {"s1": s, "categorias": cats, "fechado_em": _agora(), "fechado_por": u["login"],
         "triagem_pendente": sum(1 for ln in linhas if ln["chave"] == ch and ln["situacao"] == "TRIAGEM")}
    _cong().collection("fechamentos").document(ch).set(d, timeout=banco.TIMEOUT)
    BASE.todos_fechamentos()[ch] = d
    return _json({"ok": True, "fechamento": d})


@router.delete("/fechamentos/{ch}")
def reabrir_mes(ch: str, request: Request):
    _, p = _contexto(request)
    _exigir(p, "fechar", "reabrir o mês")
    _cong().collection("fechamentos").document(_chave(ch)).delete(timeout=banco.TIMEOUT)
    BASE.todos_fechamentos().pop(ch, None)
    return {"ok": True}


@router.get("/anual")
def anual(request: Request, ano: int = 0):
    _contexto(request)
    BASE.atualizar()
    atual = _mes_atual()
    as_ = ano or R.ano_servico(R.somar(atual, -1))
    ate = min(R.meses_do_as(as_)[-1], atual)
    s = R.s10(as_, BASE.linhas(), BASE.membros or {}, _assist_ano(as_), BASE.config(), ate=ate)
    return _json(s)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
@router.put("/config")
async def salvar_config(request: Request):
    _, p = _contexto(request)
    _exigir(p, "ajustes", "alterar os ajustes")
    c = await request.json()
    novo = {}
    if "limite_aux" in c:
        novo["limite_aux"] = _int(c["limite_aux"], 1, 100)
    if "corte_dia" in c:
        novo["corte_dia"] = _int(c["corte_dia"], 1, 28)
    if "grupos" in c:
        novo["grupos"] = [{"id": re.sub(r"[^a-z0-9-]", "", str(g.get("id") or R.normalizar(g.get("nome", "")).replace(" ", "-")))[:40] or f"g{i}",
                           "nome": str(g.get("nome", ""))[:60], "dirigente": str(g.get("dirigente", ""))[:80]}
                          for i, g in enumerate(c["grupos"] or []) if str(g.get("nome", "")).strip()][:40]
    if "pastas" in c:
        novo["pastas"] = [{"caminho": str(x.get("caminho", ""))[:150], "membros": [str(m) for m in (x.get("membros") or [])][:400]}
                          for x in (c["pastas"] or []) if str(x.get("caminho", "")).strip()][:60]
    if "its" in c:
        novo["its"] = [{"titulo": str(x.get("titulo", ""))[:150], "ref": str(x.get("ref", ""))[:60], "nota": str(x.get("nota", ""))[:600]}
                       for x in (c["its"] or []) if str(x.get("titulo", "")).strip()][:120]
    for campo in ("dia_meio", "dia_fim"):   # 0 = segunda … 6 = domingo; -1 = não definido
        if campo in c:
            novo[campo] = _int(c[campo], -1, 6)
    for campo in ("territorios_total", "territorios_nao_trabalhados"):
        if campo in c:
            novo[campo] = _int(c[campo], 0, 10000)
    if "visita_ultima" in c:
        novo["visita_ultima"] = str(c["visita_ultima"] or "")[:10]
    BASE.salvar_config(novo)
    return {"ok": True, "config": BASE.config()}


# ══════════════════════════════════════════════════════════════════════════════
# PDFs e ZIP
# ══════════════════════════════════════════════════════════════════════════════
def _pdf(dados: bytes, nome: str) -> Response:
    return Response(dados, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{PDF.nome_arquivo(nome)}.pdf"', "Cache-Control": "no-store"})


def _membro_para_pdf(m: dict, p: dict) -> dict:
    return {k: v for k, v in m.items() if not (k in CAMPOS_SENSIVEIS and _nivel(p, k) == "oculto")}


@router.get("/pdf/s21/{mid}")
def pdf_s21(mid: str, request: Request, ano: int = 0):
    _, p = _contexto(request)
    _exigir(p, "exportar", "baixar cartões")
    BASE.atualizar()
    if mid not in (BASE.membros or {}):
        raise HTTPException(404, "Membro não encontrado.")
    as_ = ano or R.ano_servico(_mes_atual())
    m = BASE.membros[mid]
    return _pdf(PDF.s21_membro(_membro_para_pdf(m, p), R.cartao(mid, as_, BASE.linhas()), as_), f"S-21 {m.get('nome_oficial', mid)} {as_}")


@router.get("/pdf/total/{cat}")
def pdf_total(cat: str, request: Request, ano: int = 0):
    _, p = _contexto(request)
    _exigir(p, "exportar", "baixar cartões")
    mapa = {"publicadores": (R.PUB, "PUBLICADORES"), "auxiliares": (R.AUX, "PIONEIROS AUXILIARES"),
            "regulares": (R.REG, "PIONEIROS REGULARES")}
    if cat not in mapa:
        raise HTTPException(404)
    BASE.atualizar()
    as_ = ano or R.ano_servico(_mes_atual())
    categoria, titulo = mapa[cat]
    return _pdf(PDF.s21_total(f"{titulo} {as_}", R.cartao_total(categoria, as_, BASE.linhas()), as_), f"{titulo} {as_}")


@router.get("/pdf/s88")
def pdf_s88(request: Request, ano: int = 0):
    _, p = _contexto(request)
    _exigir(p, "exportar", "baixar o S-88")
    as_ = ano or R.ano_servico(_mes_atual())
    a = _assist_ano(as_)
    return _pdf(PDF.s88(as_, a["meio"], a["fim"]), f"S-88 Assistência {as_}")


@router.post("/visita/zip")
async def zip_visita(request: Request):
    u, p = _contexto(request)
    _exigir(p, "exportar", "gerar o ZIP da visita")
    c = await request.json()
    BASE.atualizar()
    de, ate = _chave(c.get("de")), _chave(c.get("ate"))
    if R.distancia(de, ate) < 0 or R.distancia(de, ate) > 24:
        raise HTTPException(400, "Período inválido (até 24 meses).")
    meses = [R.somar(de, i) for i in range(R.distancia(de, ate) + 1)]
    anos = sorted({R.ano_servico(x) for x in meses})
    linhas = BASE.linhas()
    membros = {mid: _membro_para_pdf(m, p) for mid, m in (BASE.membros or {}).items()}
    part = R.participacoes(linhas)
    situacoes = {mid: R.situacao(m, part.get(mid, set()), ate) for mid, m in membros.items()}
    assist = {"meio": {}, "fim": {}}
    for as_ in anos:
        a = _assist_ano(as_)
        assist["meio"].update(a["meio"])
        assist["fim"].update(a["fim"])
    s1s = [R.s1(x, linhas, membros, assist["fim"].get(x, {}).get("media", 0), part) for x in meses]
    s10_ = R.s10(anos[-1], linhas, membros, assist, BASE.config(), ate=ate) if R.partes(ate)[1] == 8 else None
    anexos, tamanho = [], 0
    for a in (c.get("anexos") or [])[:200]:
        try:
            dados = base64.b64decode(str(a.get("base64", "")), validate=False)
        except (ValueError, TypeError):
            continue
        tamanho += len(dados)
        if tamanho > 60 * 1024 * 1024:
            raise HTTPException(413, "Anexos grandes demais (máx. 60 MB no total).")
        anexos.append((str(a.get("caminho") or a.get("nome") or "anexo"), dados))
    cfg = BASE.config()
    grupos = {g["id"]: g["nome"] for g in cfg.get("grupos", [])}
    raiz = str(c.get("titulo") or f"VISITA {datetime.now(R.FUSO).strftime('%d %m %Y')}")
    dados = PDF.zip_visita(raiz=raiz, anos=anos, membros=membros, linhas=linhas, ate=ate, situacoes=situacoes,
                           assist=assist, s1s=s1s, s10_=s10_, pastas=cfg.get("pastas", []),
                           por_grupo=bool(c.get("por_grupo")), grupos=grupos, anexos=anexos)
    if c.get("marcar_visita"):
        BASE.salvar_config({"visita_ultima": datetime.now(R.FUSO).date().isoformat()})
    return Response(dados, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{PDF.nome_arquivo(raiz)}.zip"', "Cache-Control": "no-store"})
