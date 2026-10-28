"""
═══════════════════════════════════════════════════════════════════════════════
 atelier.py — LILA CLOSET ATELIER dentro do hub  ·  /api/atelier
───────────────────────────────────────────────────────────────────────────────
 O sistema do atelier (antes só no Streamlit) agora é um módulo do hub.
 Lê e grava as MESMAS coleções do Firestore (projeto wendleydesenvolvimento),
 então o app antigo continua funcionando com os mesmos dados enquanto existir:

   lila_clientes · lila_encomendas · lila_cronograma · lila_prospects
   lila_gastos · lila_recebimentos · lila_fechamentos_mensais
   lila_campo_horas · lila_peso_registro · lila_config

 Regras: atelier_regras.py (puras, testadas)  ·  PDFs: atelier_pdf.py
 Economia de cota: tudo fica na memória; relê o banco ao abrir o módulo
 (no máx. a cada 2 min) ou no botão "Recarregar". Gravações do hub já
 atualizam a memória na hora.
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

import acesso
import atelier_pdf as PDF
import atelier_regras as R
import banco

router = APIRouter(prefix="/api/atelier")
MOD = "lila-closet"
FUSO = ZoneInfo("America/Sao_Paulo")
COLS = {"clientes": "lila_clientes", "encomendas": "lila_encomendas", "cronograma": "lila_cronograma",
        "prospects": "lila_prospects", "gastos": "lila_gastos", "recebimentos": "lila_recebimentos",
        "fechamentos": "lila_fechamentos_mensais", "campo": "lila_campo_horas", "peso": "lila_peso_registro"}


def _limpo(v):
    """O app antigo (pandas) gravou NaN/Infinity em alguns campos — viram vazio aqui."""
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None
    if isinstance(v, dict):
        return {k: _limpo(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_limpo(x) for x in v]
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def hoje() -> date:
    return datetime.now(FUSO).date()


def agora() -> str:
    return datetime.now(FUSO).isoformat()


def _now_iso() -> str:          # o Streamlit grava _criado_em sem fuso
    return datetime.now(FUSO).replace(tzinfo=None).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXTO / PERMISSÕES
# ══════════════════════════════════════════════════════════════════════════════
def _ctx(request: Request, acao: str | None = None, texto: str = ""):
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(MOD)
    if esq is None:
        raise HTTPException(404, "Módulo do atelier não encontrado (falta modulos/lila-closet.html).")
    p = acesso.permissoes(u, MOD, esq)
    if not p["acoes"].get("acessar"):
        raise HTTPException(403, "Sem acesso ao Lila Closet.")
    if acao and not p["acoes"].get(acao):
        raise HTTPException(403, f"Sem permissão para {texto or acao}.")
    if not banco.configurado():
        raise HTTPException(503, "Banco não configurado: falta FIRESTORE_CREDS no Render.")
    BASE.garantir()
    return u, p


# ══════════════════════════════════════════════════════════════════════════════
# MEMÓRIA
# ══════════════════════════════════════════════════════════════════════════════
class _Base:
    IDADE_MAX = 120

    def __init__(self):
        self.trava = threading.RLock()
        self.d: dict[str, dict[str, dict]] = {}
        self.cfg: dict = {}
        self.em = 0.0
        self.leituras = 0
        self.versao = 0

    def carregar(self):
        db = banco.db()
        novo = {}
        n = 0
        for k, col in COLS.items():
            novo[k] = {doc.id: {**_limpo(doc.to_dict() or {}), "id": doc.id} for doc in db.collection(col).stream(timeout=60)}
            n += len(novo[k])
        cfg = dict(R.CONFIG_PADRAO)
        for doc in db.collection("lila_config").stream(timeout=30):
            cfg[doc.id] = str((doc.to_dict() or {}).get("valor", cfg.get(doc.id, "")))
            n += 1
        with self.trava:
            self.d, self.cfg, self.em = novo, cfg, time.time()
            self.leituras += n
            self.versao += 1

    def garantir(self, forcar=False):
        if forcar or not self.d or time.time() - self.em > self.IDADE_MAX:
            self.carregar()

    def lista(self, k: str) -> list[dict]:
        with self.trava:
            return [dict(v) for v in self.d.get(k, {}).values()]

    def get(self, k: str, i: str) -> dict | None:
        with self.trava:
            v = self.d.get(k, {}).get(i)
            return dict(v) if v else None

    # ── gravações (banco + memória) ──
    def add(self, k: str, dados: dict) -> str:
        _, ref = banco.db().collection(COLS[k]).add(dados, timeout=banco.TIMEOUT)
        with self.trava:
            self.d.setdefault(k, {})[ref.id] = {**dados, "id": ref.id}
            self.versao += 1
        return ref.id

    def upd(self, k: str, i: str, dados: dict):
        banco.db().collection(COLS[k]).document(i).update(dados, timeout=banco.TIMEOUT)
        with self.trava:
            atual = self.d.setdefault(k, {}).get(i) or {"id": i}
            self.d[k][i] = {**atual, **dados}
            self.versao += 1

    def dele(self, k: str, i: str):
        banco.db().collection(COLS[k]).document(i).delete(timeout=banco.TIMEOUT)
        with self.trava:
            self.d.get(k, {}).pop(i, None)
            self.versao += 1

    def cfg_set(self, chave: str, valor: str):
        banco.db().collection("lila_config").document(chave).set({"valor": valor}, timeout=banco.TIMEOUT)
        with self.trava:
            self.cfg[chave] = valor
            self.versao += 1


BASE = _Base()


def _enc(eid: str) -> dict:
    e = BASE.get("encomendas", eid)
    if not e:
        raise HTTPException(404, "Pedido não encontrado (pode ter sido apagado — clique em Recarregar).")
    return e


def _iso(v, obrig=False) -> str:
    dd = R.d(v)
    if obrig and not dd:
        raise HTTPException(400, "Data inválida.")
    return dd.isoformat() if dd else ""


def _txt(v, n=500) -> str:
    return str(v or "").strip()[:n]


def _money(v) -> float:
    try:
        return round(max(float(str(v).replace(",", ".")), 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _mes_fechado(mes: str) -> bool:
    return any(x.get("mes") == mes and R.i(x.get("fechado")) for x in BASE.lista("fechamentos"))


def _checar_confeccao(dia, excluir_id, confirmar):
    status, msg = R.validar_data_confeccao(BASE.lista("encomendas"), R.d(dia), excluir_id, confirmar)
    if status != "ok":
        raise HTTPException(409, {"agenda": status, "mensagem": msg})


def _tarefas_do_pedido(eid: str) -> list[dict]:
    return [t for t in BASE.lista("cronograma") if str(t.get("encomenda_id") or "") == eid and t.get("tipo_agenda", "Trabalho") == "Trabalho"]


def _sincronizar_lembretes(eid: str, e: dict):
    """Mesma lógica do Streamlit: só mexe nas tarefas PENDENTES do pedido."""
    desc = f"{e.get('peca')} ({e.get('cliente')})"
    pend = [t for t in _tarefas_do_pedido(eid) if not R.i(t.get("concluida"))]
    tem_p2 = bool(R.i(e.get("tem_prova2"))) and bool(str(e.get("data_prova2") or "").strip())
    espec = R.tarefas_do_pedido(eid, e.get("cliente"), e.get("peca"), R.i(e.get("precisa_tecido")), R.d(e.get("data_tecido")),
                                R.d(e.get("data_confeccao")), R.d(e.get("data_prova")), tem_p2, R.d(e.get("data_prova2")),
                                R.d(e.get("data_entrega")))
    for prefixo, cat, horas, data_v, deve in espec:
        linha = next((t for t in pend if str(t.get("tarefa") or "").startswith(prefixo)), None)
        if not deve:
            if linha:
                BASE.dele("cronograma", linha["id"])
            continue
        if data_v is None:
            continue
        texto = f"{prefixo} {desc}"
        if linha:
            BASE.upd("cronograma", linha["id"], {"tarefa": texto, "data": data_v.isoformat()})
        else:
            BASE.add("cronograma", {"tarefa": texto, "categoria": cat, "horas": horas, "data": data_v.isoformat(),
                                    "frequencia": "Pontual", "concluida": 0, "encomenda_id": eid, "tipo_agenda": "Trabalho",
                                    "_criado_em": _now_iso()})


def _reverter_lembretes(eid: str, etapa: int):
    for prefixo, gerada in ((R.PREF_CONF, 1), (R.PREF_PROVA, 2), (R.PREF_ENTREGA, 3)):
        linha = next((t for t in _tarefas_do_pedido(eid) if str(t.get("tarefa") or "").startswith(prefixo)), None)
        if linha:
            deve = gerada <= etapa
            if bool(R.i(linha.get("concluida"))) != deve:
                BASE.upd("cronograma", linha["id"], {"concluida": 1 if deve else 0})


def _publica_enc(e: dict, p: dict) -> dict:
    if not p["acoes"].get("contratos"):
        e = {k: v for k, v in e.items() if k not in ("cpf_cliente", "rg_cliente")}
        e["_tem_contrato"] = None
    return e


# ══════════════════════════════════════════════════════════════════════════════
# ESTADO
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/estado")
def estado(request: Request, fresco: int = 0):
    u, p = _ctx(request)
    if fresco:
        BASE.garantir(forcar=time.time() - BASE.em > 20)
    a = p["acoes"]
    encs = [_publica_enc(e, p) for e in BASE.lista("encomendas")]
    out = {"perm": p, "eu": {"login": u.get("login"), "nome": u.get("nome") or u.get("login"), "admin": bool(u.get("admin"))},
           "hoje": hoje().isoformat(), "versao": BASE.versao, "leituras": BASE.leituras, "lido_em": BASE.em,
           "cfg": BASE.cfg, "clientes": BASE.lista("clientes"), "encomendas": encs, "prospects": BASE.lista("prospects"),
           "cronograma": [t for t in BASE.lista("cronograma") if t.get("tipo_agenda", "Trabalho") != "Pessoal" or a.get("pessoal")],
           "const": {"etapas": R.ETAPAS, "medidas": R.DIC_MEDIDAS, "cat_gastos": R.CAT_GASTOS, "cat_receitas": R.CAT_RECEITAS,
                     "formas": R.FORMAS_PAGAMENTO, "formas_pedido": R.FORMAS_PEDIDO, "cat_pessoal": R.CAT_PESSOAL,
                     "limite_provas": R.LIMITE_PROVAS_PARA_CONFECCAO, "meta_campo": R.META_HORAS_CAMPO,
                     "meta_peso": R.META_PESO_KG, "peso_inicial": R.PESO_INICIAL_KG}}
    if a.get("financeiro"):
        out.update(gastos=BASE.lista("gastos"), recebimentos=BASE.lista("recebimentos"), fechamentos=BASE.lista("fechamentos"))
    if a.get("pessoal"):
        out.update(campo=BASE.lista("campo"), peso=BASE.lista("peso"))
    return out


@router.get("/ocupacao")
def ocupacao(request: Request, mes: str, excluir: str = ""):
    _ctx(request)
    try:
        a, m = int(mes[:4]), int(mes[5:7])
    except ValueError:
        raise HTTPException(400, "Mês inválido.")
    return {"mes": mes, "dias": R.ocupacao_mes(BASE.lista("encomendas"), a, m, excluir or None), "limite": R.LIMITE_PROVAS_PARA_CONFECCAO}


@router.post("/recarregar")
def recarregar(request: Request):
    _ctx(request)
    BASE.garantir(forcar=True)
    return {"ok": True, "versao": BASE.versao}


# ══════════════════════════════════════════════════════════════════════════════
# PEDIDOS (encomendas)
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/encomendas")
async def criar_encomenda(request: Request):
    u, p = _ctx(request, "pedidos", "criar pedidos")
    c = await request.json()
    cliente, peca = _txt(c.get("cliente"), 120), _txt(c.get("peca"), 200)
    if not cliente:
        raise HTTPException(400, "Informe o nome da cliente.")
    if not peca:
        raise HTTPException(400, "Informe a peça / serviço.")
    d_conf, d_prova, d_ent = _iso(c.get("data_confeccao"), True), _iso(c.get("data_prova"), True), _iso(c.get("data_entrega"), True)
    tem_p2 = bool(c.get("tem_prova2"))
    d_p2 = _iso(c.get("data_prova2")) if tem_p2 else ""
    precisa_tecido = bool(c.get("precisa_tecido"))
    d_tec = _iso(c.get("data_tecido")) or (hoje() + timedelta(days=3)).isoformat()
    _checar_confeccao(d_conf, None, bool(c.get("confirmar")))
    if not any(R.d(x) for x in [d_conf]):
        raise HTTPException(400, "Data da confecção inválida.")
    if not any(str(x.get("nome") or "").strip().lower() == cliente.lower() for x in BASE.lista("clientes")):
        BASE.add("clientes", {"nome": cliente, "telefone": _txt(c.get("telefone"), 40), "criado_em": agora()})
    total, sinal = _money(c.get("valor_total")), _money(c.get("sinal"))
    pode_contrato = p["acoes"].get("contratos")
    dados = {"cliente": cliente, "peca": peca, "descricao": _txt(c.get("descricao"), 2000), "valor_total": total, "sinal": sinal,
             "valor_recebido": sinal, "etapa": 1, "precisa_tecido": 1 if precisa_tecido else 0, "data_tecido": d_tec,
             "data_confeccao": d_conf, "data_prova": d_prova, "tem_prova2": 1 if tem_p2 else 0, "data_prova2": d_p2,
             "data_entrega": d_ent, "cpf_cliente": _txt(c.get("cpf"), 20) if pode_contrato else "",
             "rg_cliente": _txt(c.get("rg"), 20) if pode_contrato else "", "forma_pagamento": _txt(c.get("forma_pagamento"), 30) or "A combinar",
             "observacoes": _txt(c.get("observacoes"), 2000), "cancelado": 0, "criado_em": agora(), "_criado_em": _now_iso(),
             "criado_por": u.get("login")}
    eid = BASE.add("encomendas", dados)
    _sincronizar_lembretes(eid, dados)
    # Melhoria do hub: o sinal vira uma ENTRADA de verdade no caixa (no Streamlit ele só ficava no pedido)
    if sinal > 0 and c.get("lancar_sinal", True) and p["acoes"].get("financeiro"):
        BASE.add("recebimentos", {"encomenda_id": eid, "descricao": f"Sinal – {cliente}: {peca}", "valor": sinal, "categoria": "Sinal/Entrada",
                                  "data": hoje().isoformat(), "forma_pagamento": dados["forma_pagamento"], "conciliado": 0,
                                  "criado_em": agora(), "_criado_em": _now_iso()})
    if c.get("prospect_id") and BASE.get("prospects", str(c["prospect_id"])):
        BASE.dele("prospects", str(c["prospect_id"]))
    return {"ok": True, "id": eid, "contrato": bool(dados["cpf_cliente"] and dados["rg_cliente"])}


@router.put("/encomendas/{eid}")
async def editar_encomenda(eid: str, request: Request):
    u, p = _ctx(request, "pedidos", "editar pedidos")
    e = _enc(eid)
    c = await request.json()
    cancelado = bool(R.i(e.get("cancelado")))
    mud: dict = {}
    for k, n in (("cliente", 120), ("peca", 200), ("descricao", 2000), ("observacoes", 2000), ("forma_pagamento", 30)):
        if k in c:
            mud[k] = _txt(c[k], n)
    if "cliente" in mud and not mud["cliente"]:
        raise HTTPException(400, "Informe o nome da cliente.")
    if "valor_total" in c:
        mud["valor_total"] = _money(c["valor_total"])
    if p["acoes"].get("contratos"):
        for k, ck in (("cpf_cliente", "cpf"), ("rg_cliente", "rg")):
            if ck in c:
                mud[k] = _txt(c[ck], 20)
    datas = any(k in c for k in ("data_confeccao", "data_prova", "data_entrega", "data_tecido", "data_prova2", "tem_prova2", "precisa_tecido"))
    if datas:
        for k in ("data_confeccao", "data_prova", "data_entrega"):
            if k in c:
                mud[k] = _iso(c[k], True)
        if "data_tecido" in c:
            mud["data_tecido"] = _iso(c["data_tecido"])
        if "precisa_tecido" in c:
            mud["precisa_tecido"] = 1 if c["precisa_tecido"] else 0
        if "tem_prova2" in c:
            mud["tem_prova2"] = 1 if c["tem_prova2"] else 0
            mud["data_prova2"] = _iso(c.get("data_prova2")) if c["tem_prova2"] else ""
        nova_conf = mud.get("data_confeccao", e.get("data_confeccao"))
        if nova_conf != e.get("data_confeccao") and not R.eh_conserto(e):
            _checar_confeccao(nova_conf, eid, bool(c.get("confirmar")))
    novo = {**e, **mud}
    ajustada = None
    if datas and not cancelado:
        etapa_max = R.etapa_maxima_por_datas(hoje(), R.d(novo.get("data_confeccao")), R.d(novo.get("data_prova")))
        if etapa_max < R.i(e.get("etapa"), 1):
            mud["etapa"] = ajustada = etapa_max
    if not mud:
        return {"ok": True}
    mud["atualizado_em"] = agora()
    BASE.upd("encomendas", eid, mud)
    novo = {**e, **mud}
    if ajustada:
        _reverter_lembretes(eid, ajustada)
    if datas or "cliente" in mud or "peca" in mud:
        if not cancelado:
            _sincronizar_lembretes(eid, novo)
    return {"ok": True, "etapa_ajustada": ajustada, "etapa_nome": R.ETAPAS[ajustada][1] if ajustada else None}


@router.post("/encomendas/{eid}/concluir")
def concluir(eid: str, request: Request):
    _ctx(request, "pedidos", "concluir pedidos")
    e = _enc(eid)
    if R.i(e.get("cancelado")):
        raise HTTPException(409, "Pedido cancelado.")
    BASE.upd("encomendas", eid, {"etapa": 4, "atualizado_em": agora()})
    return {"ok": True}


@router.post("/encomendas/{eid}/reabrir")
def reabrir(eid: str, request: Request):
    _ctx(request, "pedidos", "reabrir pedidos")
    e = _enc(eid)
    etapa = R.etapa_maxima_por_datas(hoje(), R.d(e.get("data_confeccao")), R.d(e.get("data_prova")))
    BASE.upd("encomendas", eid, {"etapa": etapa, "atualizado_em": agora()})
    return {"ok": True, "etapa": etapa}


@router.post("/encomendas/{eid}/cancelar")
def cancelar(eid: str, request: Request):
    """Igual ao Streamlit: zera o andamento, apaga as tarefas e os gastos NÃO pagos do pedido.
    O dinheiro já recebido (lila_recebimentos) continua — é fato do caixa."""
    _ctx(request, "pedidos", "cancelar pedidos")
    _enc(eid)
    BASE.upd("encomendas", eid, {"cancelado": 1, "etapa": 1, "sinal": 0, "valor_recebido": 0, "data_tecido": None,
                                 "data_confeccao": None, "data_prova": None, "data_entrega": None, "atualizado_em": agora()})
    for t in [t for t in BASE.lista("cronograma") if str(t.get("encomenda_id") or "") == eid]:
        BASE.dele("cronograma", t["id"])
    for g in [g for g in BASE.lista("gastos") if str(g.get("encomenda_id") or "") == eid and not R.i(g.get("pago"))]:
        BASE.dele("gastos", g["id"])
    return {"ok": True}


@router.delete("/encomendas/{eid}")
async def apagar_encomenda(eid: str, request: Request):
    _ctx(request, "excluir", "excluir pedidos para sempre")
    c = await request.json()
    if str(c.get("confirmar") or "").strip().upper() != "EXCLUIR":
        raise HTTPException(400, "Digite EXCLUIR para confirmar.")
    _enc(eid)
    BASE.dele("encomendas", eid)
    for t in [t for t in BASE.lista("cronograma") if str(t.get("encomenda_id") or "") == eid]:
        BASE.dele("cronograma", t["id"])
    for g in [g for g in BASE.lista("gastos") if str(g.get("encomenda_id") or "") == eid]:
        BASE.dele("gastos", g["id"])
    return {"ok": True}


@router.get("/encomendas/{eid}/contrato.pdf")
def contrato(eid: str, request: Request):
    _ctx(request, "contratos", "gerar contratos")
    e = _enc(eid)
    cpf, rg = _txt(e.get("cpf_cliente"), 20), _txt(e.get("rg_cliente"), 20)
    if not cpf or not rg:
        raise HTTPException(400, "Preencha CPF e RG do contrato primeiro.")
    pdf = PDF.gerar_pdf_contrato(e, cpf, rg, BASE.cfg)
    nome = "Contrato_" + "".join(ch if ch.isalnum() else "_" for ch in str(e.get("cliente") or "cliente")) + ".pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'})


@router.post("/consertos")
async def criar_conserto(request: Request):
    _ctx(request, "pedidos", "registrar consertos")
    c = await request.json()
    cliente, tipo = _txt(c.get("cliente"), 120), _txt(c.get("tipo"), 60) or "Ajuste"
    if not cliente:
        raise HTTPException(400, "Informe a cliente.")
    dia = _iso(c.get("data"), True)
    peca = f"{R.PREFIXO_CONSERTO} {tipo}"
    eid = BASE.add("encomendas", {"cliente": cliente, "peca": peca, "descricao": _txt(c.get("descricao"), 500), "valor_total": _money(c.get("valor")),
                                  "valor_recebido": 0.0, "sinal": 0.0, "etapa": 1, "precisa_tecido": 0, "data_tecido": dia,
                                  "data_confeccao": dia, "data_prova": dia, "tem_prova2": 0, "data_prova2": "", "data_entrega": dia,
                                  "cpf_cliente": "", "rg_cliente": "", "forma_pagamento": "A combinar", "observacoes": f"Conserto — {tipo}",
                                  "cancelado": 0, "criado_em": agora(), "_criado_em": _now_iso()})
    BASE.add("cronograma", {"tarefa": f"{R.PREF_CONF} {peca} ({cliente})", "categoria": "Costura", "horas": 1.0, "data": dia,
                            "frequencia": "Pontual", "concluida": 0, "encomenda_id": eid, "tipo_agenda": "Trabalho", "_criado_em": _now_iso()})
    if c.get("prospect_id") and BASE.get("prospects", str(c["prospect_id"])):
        BASE.dele("prospects", str(c["prospect_id"]))
    if not any(str(x.get("nome") or "").strip().lower() == cliente.lower() for x in BASE.lista("clientes")):
        BASE.add("clientes", {"nome": cliente, "telefone": _txt(c.get("telefone"), 40), "criado_em": agora()})
    return {"ok": True, "id": eid}


# ══════════════════════════════════════════════════════════════════════════════
# CLIENTES · PROSPECTS
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/clientes")
async def criar_cliente(request: Request):
    _ctx(request, "pedidos", "cadastrar clientes")
    c = await request.json()
    nome = _txt(c.get("nome"), 120)
    if not nome:
        raise HTTPException(400, "Informe o nome.")
    return {"ok": True, "id": BASE.add("clientes", {"nome": nome, "telefone": _txt(c.get("telefone"), 40), "criado_em": agora()})}


@router.put("/clientes/{cid}")
async def editar_cliente(cid: str, request: Request):
    _ctx(request, "pedidos", "editar clientes")
    if not BASE.get("clientes", cid):
        raise HTTPException(404, "Cliente não encontrada.")
    c = await request.json()
    mud = {campo: _txt(c[campo], 20) for campo in R.DIC_MEDIDAS.values() if campo in c}
    if "outro" in c:
        mud["outro"] = _txt(c["outro"], 2000)
    for k in ("nome", "telefone"):
        if k in c:
            mud[k] = _txt(c[k], 120)
    if "nome" in mud and not mud["nome"]:
        raise HTTPException(400, "O nome não pode ficar vazio.")
    if mud:
        BASE.upd("clientes", cid, mud)
    return {"ok": True}


@router.delete("/clientes/{cid}")
async def apagar_cliente(cid: str, request: Request):
    _ctx(request, "excluir", "excluir cadastros")
    c = await request.json()
    if str(c.get("confirmar") or "").strip().upper() != "EXCLUIR":
        raise HTTPException(400, "Digite EXCLUIR para confirmar.")
    BASE.dele("clientes", cid)
    return {"ok": True}


@router.post("/prospects")
async def criar_prospect(request: Request):
    _ctx(request, "pedidos", "cadastrar prospects")
    c = await request.json()
    nome = _txt(c.get("nome"), 120)
    if not nome:
        raise HTTPException(400, "Informe o nome.")
    return {"ok": True, "id": BASE.add("prospects", {"nome": nome, "telefone": _txt(c.get("telefone"), 40), "obs": _txt(c.get("obs"), 500),
                                                     "criado_em": agora(), "_criado_em": _now_iso()})}


@router.delete("/prospects/{pid}")
def apagar_prospect(pid: str, request: Request):
    _ctx(request, "pedidos", "remover prospects")
    BASE.dele("prospects", pid)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# AGENDA (cronograma) · VIDA PESSOAL
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/tarefas")
async def criar_tarefa(request: Request):
    u, p = _ctx(request)
    c = await request.json()
    tipo = "Pessoal" if c.get("tipo_agenda") == "Pessoal" else "Trabalho"
    if tipo == "Pessoal" and not p["acoes"].get("pessoal"):
        raise HTTPException(403, "Sem permissão para a vida pessoal.")
    if tipo == "Trabalho" and not p["acoes"].get("pedidos"):
        raise HTTPException(403, "Sem permissão para criar tarefas.")
    tarefa = _txt(c.get("tarefa"), 200)
    if not tarefa:
        raise HTTPException(400, "Descreva a tarefa.")
    return {"ok": True, "id": BASE.add("cronograma", {"tarefa": tarefa, "categoria": _txt(c.get("categoria"), 60) or "Outros",
                                                      "horas": float(c.get("horas") or 1), "data": _iso(c.get("data"), True),
                                                      "frequencia": "Pontual", "concluida": 0, "tipo_agenda": tipo, "_criado_em": _now_iso()})}


@router.put("/tarefas/{tid}")
async def editar_tarefa(tid: str, request: Request):
    """Popup 'Data': muda a data (e o campo de data do pedido) e/ou marca 'já foi feito'."""
    u, p = _ctx(request)
    t = BASE.get("cronograma", tid)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    pessoal = t.get("tipo_agenda") == "Pessoal"
    if not p["acoes"].get("pessoal" if pessoal else "pedidos"):
        raise HTTPException(403, "Sem permissão.")
    c = await request.json()
    mud = {}
    if "concluida" in c:
        mud["concluida"] = 1 if c["concluida"] else 0
    nova = _iso(c.get("data")) if c.get("data") else ""
    eid = str(t.get("encomenda_id") or "")
    texto = str(t.get("tarefa") or "")
    if nova and nova != t.get("data"):
        if texto.startswith(R.PREF_CONF) and eid and not R.eh_conserto(BASE.get("encomendas", eid) or {}):
            _checar_confeccao(nova, eid, bool(c.get("confirmar")))
        mud["data"] = nova
        if eid and BASE.get("encomendas", eid):
            for pref, campo in R.PREFIXO_CAMPO.items():
                if texto.startswith(pref):
                    BASE.upd("encomendas", eid, {campo: nova})
                    break
    if mud:
        BASE.upd("cronograma", tid, mud)
    return {"ok": True}


@router.post("/tarefas/{tid}/feito")
def tarefa_feita(tid: str, request: Request):
    """'✅ Feito' da agenda: conclui a tarefa e avança a régua no MÁXIMO até Entrega (3)."""
    u, p = _ctx(request)
    t = BASE.get("cronograma", tid)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    if not p["acoes"].get("pessoal" if t.get("tipo_agenda") == "Pessoal" else "pedidos"):
        raise HTTPException(403, "Sem permissão.")
    eid = str(t.get("encomenda_id") or "")
    e = BASE.get("encomendas", eid) if eid else None
    if e:
        atual = R.i(e.get("etapa"), 1)
        prox = min(atual + 1, R.ETAPA_CONCLUIDO - 1)
        if prox > atual:
            BASE.upd("encomendas", eid, {"etapa": prox})
    BASE.upd("cronograma", tid, {"concluida": 1})
    return {"ok": True}


@router.delete("/tarefas/{tid}")
def apagar_tarefa(tid: str, request: Request):
    u, p = _ctx(request)
    t = BASE.get("cronograma", tid)
    if not t:
        return {"ok": True}
    if t.get("encomenda_id"):
        raise HTTPException(409, "Tarefas de pedido saem sozinhas — edite as datas do pedido.")
    if not p["acoes"].get("pessoal" if t.get("tipo_agenda") == "Pessoal" else "pedidos"):
        raise HTTPException(403, "Sem permissão.")
    BASE.dele("cronograma", tid)
    return {"ok": True}


@router.post("/campo")
async def lancar_campo(request: Request):
    _ctx(request, "pessoal", "lançar horas")
    c = await request.json()
    dia = R.d(c.get("data")) or hoje()
    horas = float(c.get("horas") or 0)
    if not 0 < horas <= 24:
        raise HTTPException(400, "Horas inválidas.")
    return {"ok": True, "id": BASE.add("campo", {"data": dia.isoformat(), "horas": horas, "descricao": _txt(c.get("descricao"), 200),
                                                 "mes_ano": dia.strftime("%Y-%m"), "criado_em": agora()})}


@router.delete("/campo/{cid}")
def apagar_campo(cid: str, request: Request):
    _ctx(request, "pessoal", "apagar horas")
    BASE.dele("campo", cid)
    return {"ok": True}


@router.post("/peso")
async def registrar_peso(request: Request):
    _ctx(request, "pessoal", "registrar peso")
    c = await request.json()
    dia = R.d(c.get("data")) or hoje()
    kg = float(c.get("peso_kg") or 0)
    if not 30 <= kg <= 200:
        raise HTTPException(400, "Peso inválido.")
    mes = dia.strftime("%Y-%m")
    ja = next((x for x in BASE.lista("peso") if x.get("mes_ano") == mes), None)
    if ja:
        BASE.upd("peso", ja["id"], {"data": dia.isoformat(), "peso_kg": kg})
    else:
        BASE.add("peso", {"mes_ano": mes, "data": dia.isoformat(), "peso_kg": kg})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# FINANCEIRO
# ══════════════════════════════════════════════════════════════════════════════
def _fin():
    return BASE.lista("encomendas"), BASE.lista("recebimentos"), BASE.lista("gastos"), BASE.lista("fechamentos")


@router.get("/financeiro")
def financeiro(request: Request, mes: str = ""):
    _ctx(request, "financeiro", "ver o financeiro")
    encs, rec, gas, fec = _fin()
    h = hoje()
    mes = mes if len(mes) == 7 else h.strftime("%Y-%m")
    m0 = h.strftime("%Y-%m")
    meses_proj = [m0, R.mes_seguinte(m0), R.mes_seguinte(R.mes_seguinte(m0))]
    r_mes = [r for r in rec if R.mes_de(r.get("data")) == mes]
    g_mes = [g for g in gas if R.mes_de(g.get("data")) == mes]
    rec_m = sum(R.f(r.get("valor")) for r in r_mes)
    gas_m = sum(R.f(g.get("valor")) for g in g_mes if R.i(g.get("pago")))
    margem_min = R.f(BASE.cfg.get("margem_minima_pct") or 30)
    pedidos = []
    for e in R.ativos(encs):
        rc = R.f(e.get("valor_recebido"))
        custo = sum(R.f(g.get("valor")) for g in gas if str(g.get("encomenda_id") or "") == e["id"])
        lucro = rc - custo
        pedidos.append({"id": e["id"], "cliente": e.get("cliente"), "peca": e.get("peca"), "total": R.f(e.get("valor_total")),
                        "recebido": rc, "saldo": R.saldo_pendente(e), "custo": custo, "margem": (lucro / rc * 100) if rc > 0 else 0,
                        "entrega": e.get("data_entrega"), "etapa": R.i(e.get("etapa"), 1)})
    return {"visao": R.visao_geral(encs, rec, gas, fec, BASE.cfg, h),
            "projecoes": [R.projecao(encs, gas, fec, rec, h, m) for m in meses_proj],
            "atrasados_receber": [{"id": e["id"], "cliente": e.get("cliente"), "peca": e.get("peca"), "saldo": e["_saldo"], "entrega": e.get("data_entrega")}
                                  for e in sorted(R.a_receber_atrasado(encs, h), key=lambda x: str(x.get("data_entrega")))],
            "atrasados_pagar": sorted(R.despesas_atrasadas(gas, h), key=lambda x: str(x.get("data"))),
            "relatorio": {"mes": mes, "receita": rec_m, "gastos": gas_m, "lucro": rec_m - gas_m,
                          "margem": ((rec_m - gas_m) / rec_m * 100) if rec_m > 0 else 0, "entradas": r_mes, "saidas": g_mes},
            "pedidos": sorted(pedidos, key=lambda x: str(x["cliente"] or "").lower()), "margem_min": margem_min,
            "grandes": R.grandes_previstas(gas)}


def _ajustar_recebido(eid: str, delta: float):
    e = BASE.get("encomendas", eid) if eid else None
    if e:
        novo = round(max(R.f(e.get("valor_recebido")) + delta, 0.0), 2)
        BASE.upd("encomendas", eid, {"valor_recebido": novo})


@router.post("/recebimentos")
async def lancar_recebimento(request: Request):
    _ctx(request, "financeiro", "lançar entradas")
    c = await request.json()
    valor = _money(c.get("valor"))
    if valor <= 0:
        raise HTTPException(400, "Informe o valor.")
    dia = _iso(c.get("data")) or hoje().isoformat()
    if _mes_fechado(dia[:7]):
        raise HTTPException(409, f"O mês {dia[:7]} está fechado — reabra para lançar nele.")
    eid = str(c.get("encomenda_id") or "") or None
    if eid:
        e = _enc(eid)
        saldo = R.saldo_pendente(e)
        if valor > saldo + 0.01:
            raise HTTPException(400, f"O saldo deste pedido é {PDF.brl(saldo)}.")
    rid = BASE.add("recebimentos", {"encomenda_id": eid, "descricao": _txt(c.get("descricao"), 200) or "Entrada", "valor": valor,
                                    "categoria": _txt(c.get("categoria"), 60) or ("Venda de peça" if eid else "Outro"), "data": dia,
                                    "forma_pagamento": _txt(c.get("forma_pagamento"), 30), "conciliado": 0, "criado_em": agora(),
                                    "_criado_em": _now_iso()})
    if eid:
        _ajustar_recebido(eid, valor)
    return {"ok": True, "id": rid}


@router.put("/recebimentos/{rid}")
async def editar_recebimento(rid: str, request: Request):
    _ctx(request, "financeiro", "editar entradas")
    r = BASE.get("recebimentos", rid)
    if not r:
        raise HTTPException(404, "Lançamento não encontrado.")
    c = await request.json()
    if _mes_fechado(R.mes_de(r.get("data"))) or ("data" in c and _mes_fechado(str(c["data"])[:7])):
        raise HTTPException(409, "Mês fechado — reabra para editar.")
    mud = {}
    if "valor" in c:
        mud["valor"] = _money(c["valor"])
    if "descricao" in c:
        mud["descricao"] = _txt(c["descricao"], 200)
    if "conciliado" in c:
        mud["conciliado"] = 1 if c["conciliado"] else 0
    if "data" in c:
        mud["data"] = _iso(c["data"], True)
    if mud:
        BASE.upd("recebimentos", rid, mud)
        if "valor" in mud and r.get("encomenda_id"):
            _ajustar_recebido(str(r["encomenda_id"]), mud["valor"] - R.f(r.get("valor")))
    return {"ok": True}


@router.delete("/recebimentos/{rid}")
def apagar_recebimento(rid: str, request: Request):
    _ctx(request, "financeiro", "excluir entradas")
    r = BASE.get("recebimentos", rid)
    if not r:
        return {"ok": True}
    if _mes_fechado(R.mes_de(r.get("data"))):
        raise HTTPException(409, "Mês fechado — reabra para excluir.")
    BASE.dele("recebimentos", rid)
    if r.get("encomenda_id"):
        _ajustar_recebido(str(r["encomenda_id"]), -R.f(r.get("valor")))
    return {"ok": True}


@router.post("/gastos")
async def lancar_gasto(request: Request):
    _ctx(request, "financeiro", "lançar saídas")
    c = await request.json()
    valor = _money(c.get("valor"))
    desc = _txt(c.get("descricao"), 200)
    if valor <= 0 or not desc:
        raise HTTPException(400, "Preencha descrição e valor.")
    dia = _iso(c.get("data")) or hoje().isoformat()
    pago = 1 if c.get("pago", True) else 0
    if pago and _mes_fechado(dia[:7]):
        raise HTTPException(409, f"O mês {dia[:7]} está fechado — reabra para lançar nele.")
    grande = 1 if c.get("grande_despesa_prevista") else 0
    return {"ok": True, "id": BASE.add("gastos", {"encomenda_id": str(c.get("encomenda_id") or "") or None, "descricao": desc, "valor": valor,
                                                  "data": dia, "categoria": _txt(c.get("categoria"), 60) or ("Grande despesa prevista" if grande else "Outros"),
                                                  "pago": 0 if grande else pago, "recorrente": 1 if c.get("recorrente") else 0,
                                                  "grande_despesa_prevista": grande, "conciliado": 0, "criado_em": agora(), "_criado_em": _now_iso()})}


@router.put("/gastos/{gid}")
async def editar_gasto(gid: str, request: Request):
    _ctx(request, "financeiro", "editar saídas")
    g = BASE.get("gastos", gid)
    if not g:
        raise HTTPException(404, "Lançamento não encontrado.")
    c = await request.json()
    if (R.i(g.get("pago")) and _mes_fechado(R.mes_de(g.get("data")))) or ("data" in c and _mes_fechado(str(c["data"])[:7]) and (R.i(g.get("pago")) or c.get("pago"))):
        raise HTTPException(409, "Mês fechado — reabra para editar.")
    mud = {}
    for k, fn in (("valor", _money), ("descricao", lambda v: _txt(v, 200)), ("categoria", lambda v: _txt(v, 60)), ("data", lambda v: _iso(v, True))):
        if k in c:
            mud[k] = fn(c[k])
    for k in ("conciliado", "pago"):
        if k in c:
            mud[k] = 1 if c[k] else 0
    if mud:
        BASE.upd("gastos", gid, mud)
    return {"ok": True}


@router.delete("/gastos/{gid}")
def apagar_gasto(gid: str, request: Request):
    _ctx(request, "financeiro", "excluir saídas")
    g = BASE.get("gastos", gid)
    if not g:
        return {"ok": True}
    if R.i(g.get("pago")) and _mes_fechado(R.mes_de(g.get("data"))):
        raise HTTPException(409, "Mês fechado — reabra para excluir.")
    BASE.dele("gastos", gid)
    return {"ok": True}


@router.get("/fechamento/{mes}")
def fechamento(mes: str, request: Request, saldo_inicial: str = ""):
    _ctx(request, "financeiro", "ver o fechamento")
    _, rec, gas, fec = _fin()
    si = float(saldo_inicial.replace(",", ".")) if saldo_inicial.strip() else None
    return R.resumo_mes(mes, rec, gas, fec, si)


@router.post("/fechamento/{mes}/fechar")
async def fechar_mes(mes: str, request: Request):
    u, p = _ctx(request, "fechar", "fechar o mês")
    c = await request.json()
    _, rec, gas, fec = _fin()
    res = R.resumo_mes(mes, rec, gas, fec, c.get("saldo_inicial"))
    if res["ja_fechado"]:
        raise HTTPException(409, "Este mês já está fechado.")
    extrato = c.get("saldo_extrato")
    extrato = res["saldo_teorico"] if extrato in (None, "") else float(str(extrato).replace(",", "."))
    dif = res["saldo_teorico"] - extrato
    saldo_final = extrato if abs(dif) >= 0.01 else res["saldo_teorico"]
    dados = {"mes": mes, "saldo_inicial": res["saldo_inicial"], "receitas_mes": res["entradas"], "despesas_mes": res["despesas"],
             "lucro_real_mes": res["resultado"], "saldo_final": saldo_final, "grandes_despesas_previstas": res["total_grandes"],
             "fundos_disponiveis": saldo_final - res["total_grandes"], "saldo_extrato_informado": extrato, "diferenca": dif,
             "fechado": 1, "observacoes": _txt(c.get("observacoes"), 2000), "data_fechamento": agora(), "atualizado_em": agora(),
             "_atualizado_em": _now_iso(), "fechado_por": u.get("login")}
    ja = next((x for x in BASE.lista("fechamentos") if x.get("mes") == mes), None)
    if ja:
        BASE.upd("fechamentos", ja["id"], dados)
    else:
        BASE.add("fechamentos", dados)
    return {"ok": True, "saldo_final": saldo_final, "proximo": R.mes_seguinte(mes)}


@router.post("/fechamento/{mes}/reabrir")
def reabrir_mes(mes: str, request: Request):
    _ctx(request, "fechar", "reabrir o mês")
    ja = next((x for x in BASE.lista("fechamentos") if x.get("mes") == mes), None)
    if not ja:
        raise HTTPException(404, "Mês sem fechamento.")
    BASE.upd("fechamentos", ja["id"], {"fechado": 0, "_atualizado_em": _now_iso()})
    return {"ok": True}


@router.get("/fechamento/{mes}/pdf")
def fechamento_pdf(mes: str, request: Request, saldo_inicial: str = "", saldo_extrato: str = "", observacoes: str = ""):
    _ctx(request, "financeiro", "baixar o fechamento")
    _, rec, gas, fec = _fin()
    res = R.resumo_mes(mes, rec, gas, fec, float(saldo_inicial.replace(",", ".")) if saldo_inicial.strip() else None)
    fe = res["fechamento"] or {}
    if res["ja_fechado"]:
        saldo_final, fundos = R.f(fe.get("saldo_final")), R.f(fe.get("fundos_disponiveis", fe.get("saldo_final")))
        extrato, dif, obs = fe.get("saldo_extrato_informado"), fe.get("diferenca"), fe.get("observacoes") or ""
    else:
        saldo_final, fundos = res["saldo_teorico"], res["fundos_disponiveis"]
        extrato = float(saldo_extrato.replace(",", ".")) if saldo_extrato.strip() else None
        dif = (saldo_final - extrato) if extrato is not None else None
        obs = observacoes
    pdf = PDF.gerar_pdf_fechamento(mes, res["saldo_inicial"], res["recebimentos"], res["gastos"], res["entradas"], res["despesas"],
                                   res["resultado"], saldo_final, res["grandes"], res["total_grandes"], fundos, extrato, dif, obs,
                                   res["ja_fechado"], fe.get("data_fechamento"), BASE.cfg)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="Lila_Fechamento_{mes}.pdf"'})


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════════════════════════
@router.put("/config")
async def salvar_config(request: Request):
    _ctx(request, "configurar", "mudar as configurações")
    c = await request.json()
    for k in R.CONFIG_PADRAO:
        if k in c:
            BASE.cfg_set(k, _txt(c[k], 200))
    return {"ok": True, "cfg": BASE.cfg}
