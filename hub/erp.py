"""
hub/erp.py — ERP · núcleo de Estoque, Pedidos, Logística e Retornos.
─────────────────────────────────────────────────────────────────────────────
Tudo gira em torno de um RAZÃO DE ESTOQUE: cada peça está sempre em um LOCAL,
e qualquer mudança de local vira um MOVIMENTO (kardex). Nada "some": a soma
de todos os locais de um produto fecha com tudo o que entrou.

  LOCAIS (saldo por produto)
    disponivel   pronto para vender
    reservado    separado para um pedido confirmado (ainda no depósito)
    transito     no caminhão (carga saiu)
    triagem      voltou (ausente não, esse volta p/ reservado) e aguarda inspeção
    assistencia  em recuperação interna
    at           na assistência técnica externa
    fornecedor   devolvido ao fornecedor (troca autorizada) aguardando reposição
    outlet       mercado / ponta de estoque (vendável com desconto)
    entregue     saiu definitivamente para o cliente      (acumulado)
    perdas       baixado como perda                       (acumulado)

  FLUXO DO PEDIDO
    rascunho → confirmado (reserva) → agendado → em_carga → em_rota
       → entregue
       → ausente   (volta ao depósito ainda reservado; reagendar = nova tentativa)
       → avaria    (o que chegou bom é entregue; o avariado vai p/ TRIAGEM e o
                    pedido fica com a reposição pendente para reenvio)
       → recusado  (tudo volta para TRIAGEM)
    cancelado em qualquer ponto antes da rota (libera a reserva).
    TROCA = pedido que leva itens novos e RECOLHE itens do cliente (→ triagem).

  TRIAGEM / RETORNOS — decide o destino de cada peça que voltou:
    estoque (novo) · mercado/outlet · assistência · AT · fornecedor · perdas
    e de assistência/AT/fornecedor ela pode voltar para estoque/outlet/perdas.

Firestore (projeto do FIRESTORE_CREDS), coleções próprias:
    erp_produtos  erp_parceiros  erp_saldos  erp_pedidos  erp_cargas
    erp_movimentos  erp_config/geral
Cota grátis: o hub é o único que escreve aqui, então mantém cache em memória;
ao acordar lê produtos/parceiros/saldos + pedidos/cargas dos últimos 120 dias
(e os abertos) + movimentos dos últimos 60 dias. Kardex antigo: sob demanda.
"""
from __future__ import annotations

import random
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

import acesso
import banco

router = APIRouter(prefix="/api/erp")
MOD = "erp"

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # noqa: BLE001
    FUSO = timezone(timedelta(hours=-3))

LOCAIS = ["disponivel", "reservado", "transito", "triagem", "assistencia", "at", "fornecedor", "outlet", "entregue", "perdas"]
EXTERNO = "externo"
DESTINOS = ["disponivel", "outlet", "assistencia", "at", "fornecedor", "perdas"]   # saídas da triagem
ORIGENS_DESTINO = ["triagem", "assistencia", "at", "fornecedor", "outlet"]
ABERTOS = ["rascunho", "confirmado", "agendado", "em_carga", "em_rota", "reagendar"]
CONFIG_PADRAO = {
    "empresa": "Minha Empresa",
    "rotulos": {"disponivel": "Estoque disponível", "reservado": "Reservado", "transito": "Em trânsito", "triagem": "Triagem",
                "assistencia": "Assistência (recuperação)", "at": "Assistência técnica (AT)", "fornecedor": "Fornecedor (troca autorizada)",
                "outlet": "Mercado / Outlet", "entregue": "Entregue", "perdas": "Perdas"},
    "janelas": ["Manhã", "Tarde", "Comercial"],
    "motivos_avaria": ["Transporte", "Embalagem", "Fabricação", "Manuseio", "Outro"],
    "motivos_ausencia": ["Cliente ausente", "Endereço não localizado", "Sem acesso", "Reagendado pelo cliente", "Outro"],
    "motivos_troca": ["Defeito", "Tamanho/modelo errado", "Arrependimento", "Avaria", "Outro"],
    "categorias": ["Geral"],
    "seq": {"pedido": 0, "carga": 0},
}


def agora() -> str:
    return datetime.now(FUSO).strftime("%Y-%m-%dT%H:%M:%S")


def hoje() -> str:
    return datetime.now(FUSO).strftime("%Y-%m-%d")


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _num(v, padrao=0.0) -> float:
    try:
        f = float(v)
        return f if f == f else padrao
    except (TypeError, ValueError):
        return padrao


def _int(v, padrao=0) -> int:
    return int(round(_num(v, padrao)))


# ══════════════════════════════════════════════════════════════════════════════
# ARMAZÉM EM MEMÓRIA + TRANSAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
COLS = {"produtos": "erp_produtos", "parceiros": "erp_parceiros", "saldos": "erp_saldos",
        "pedidos": "erp_pedidos", "cargas": "erp_cargas", "movimentos": "erp_movimentos"}


class _Store:
    def __init__(self):
        self.trava = threading.RLock()
        self.pronto = False
        self.dados: dict[str, dict[str, dict]] = {k: {} for k in COLS}
        self.config: dict = {}
        self.carregado_em = 0.0

    def carregar(self):
        with self.trava:
            if self.pronto:
                return
            db = banco.db()
            T = banco.TIMEOUT
            for k in ("produtos", "parceiros", "saldos"):
                self.dados[k] = {d.id: d.to_dict() or {} for d in db.collection(COLS[k]).stream(timeout=T)}
            corte = (datetime.now(FUSO) - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%S")
            ped = {d.id: d.to_dict() or {} for d in db.collection(COLS["pedidos"]).where("atualizado_em", ">=", corte).stream(timeout=T)}
            ped.update({d.id: d.to_dict() or {} for d in db.collection(COLS["pedidos"]).where("status", "in", ABERTOS).stream(timeout=T)})
            self.dados["pedidos"] = ped
            car = {d.id: d.to_dict() or {} for d in db.collection(COLS["cargas"]).where("atualizado_em", ">=", corte).stream(timeout=T)}
            car.update({d.id: d.to_dict() or {} for d in db.collection(COLS["cargas"]).where("status", "in", ["montando", "em_rota"]).stream(timeout=T)})
            self.dados["cargas"] = car
            corte_mov = (datetime.now(FUSO) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S")
            self.dados["movimentos"] = {d.id: d.to_dict() or {} for d in db.collection(COLS["movimentos"]).where("em", ">=", corte_mov).stream(timeout=T)}
            snap = db.collection("erp_config").document("geral").get(timeout=T)
            cfg = snap.to_dict() if snap.exists else {}
            self.config = {**CONFIG_PADRAO, **(cfg or {})}
            self.config["rotulos"] = {**CONFIG_PADRAO["rotulos"], **(cfg or {}).get("rotulos", {})}
            self.config["seq"] = {**CONFIG_PADRAO["seq"], **(cfg or {}).get("seq", {})}
            self.pronto = True
            self.carregado_em = time.time()


ST = _Store()


class Tx:
    """Acumula mudanças, grava tudo num batch e só então aplica no cache.
    Se o Firestore falhar, o cache continua como estava (nada pela metade)."""

    def __init__(self, usuario: dict):
        self.u = usuario
        self.mud: dict[tuple[str, str], dict | None] = {}
        self.cfg: dict | None = None
        self.movs: list[dict] = []

    # leitura com sobreposição
    def get(self, col: str, i: str) -> dict | None:
        if (col, i) in self.mud:
            return self.mud[(col, i)]
        d = ST.dados[col].get(i)
        return None if d is None else _copia(d)

    def put(self, col: str, i: str, d: dict):
        self.mud[(col, i)] = d

    def config(self) -> dict:
        if self.cfg is None:
            self.cfg = _copia(ST.config)
        return self.cfg

    def saldo(self, pid: str) -> dict:
        s = self.get("saldos", pid) or {}
        for l in LOCAIS:
            s.setdefault(l, 0)
        return s

    def mover(self, pid: str, qtd, de: str, para: str, tipo: str, ref: str = "", obs: str = "", em: str | None = None, extra: dict | None = None):
        qtd = _int(qtd)
        if qtd <= 0:
            raise HTTPException(400, "Quantidade precisa ser maior que zero.")
        prod = self.get("produtos", pid)
        if not prod:
            raise HTTPException(400, "Produto não encontrado.")
        s = self.saldo(pid)
        if de != EXTERNO:
            if s.get(de, 0) < qtd:
                rot = ST.config.get("rotulos", {}).get(de, de)
                raise HTTPException(409, f"Saldo insuficiente de {prod.get('nome')} em {rot}: tem {s.get(de, 0)}, precisa {qtd}.")
            s[de] -= qtd
        if para != EXTERNO:
            s[para] = s.get(para, 0) + qtd
        self.put("saldos", pid, s)
        mov = {"id": _id(), "em": em or agora(), "por": self.u.get("login", ""), "tipo": tipo, "produto_id": pid,
               "qtd": qtd, "de": de, "para": para, "ref": ref, "obs": obs, "custo_unit": _num(prod.get("custo"))}
        if extra:
            mov.update(extra)
        self.movs.append(mov)
        return mov

    def commit(self):
        if not self.mud and not self.movs and self.cfg is None:
            return
        db = banco.db()
        ops = []
        for (col, i), d in self.mud.items():
            ref = db.collection(COLS[col]).document(i)
            ops.append((ref, d))
        for m in self.movs:
            ops.append((db.collection(COLS["movimentos"]).document(m["id"]), m))
        if self.cfg is not None:
            ops.append((db.collection("erp_config").document("geral"), self.cfg))
        for k in range(0, len(ops), 450):
            lote = db.batch()
            for ref, d in ops[k:k + 450]:
                if d is None:
                    lote.delete(ref)
                else:
                    lote.set(ref, d)
            lote.commit(timeout=banco.TIMEOUT)
        for (col, i), d in self.mud.items():
            if d is None:
                ST.dados[col].pop(i, None)
            else:
                ST.dados[col][i] = d
        for m in self.movs:
            ST.dados["movimentos"][m["id"]] = m
        if self.cfg is not None:
            ST.config = self.cfg


def _copia(d):
    if isinstance(d, dict):
        return {k: _copia(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_copia(v) for v in d]
    return d


# ══════════════════════════════════════════════════════════════════════════════
# PERMISSÕES
# ══════════════════════════════════════════════════════════════════════════════
def _ctx(request: Request, acao: str | None = None, texto: str = ""):
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(MOD)
    if esq is None:
        raise HTTPException(404, "Módulo ERP não encontrado (falta modulos/erp.html).")
    p = acesso.permissoes(u, MOD, esq)
    if not p["acoes"].get("acessar"):
        raise HTTPException(403, "Sem acesso ao ERP.")
    if acao and not p["acoes"].get(acao):
        raise HTTPException(403, f"Sem permissão para {texto or acao}.")
    if not banco.configurado():
        raise HTTPException(503, "Banco não configurado: falta FIRESTORE_CREDS no Render.")
    ST.carregar()
    return u, p


def _filtrar(p: dict, col: str, d: dict) -> dict:
    """Esconde custos/preços/contatos conforme o nível do campo."""
    oculto = lambda c: p["campos"].get(c, "editar") == "oculto"
    d = dict(d)
    if col == "produtos":
        if oculto("custo"):
            d.pop("custo", None)
        if oculto("preco"):
            d.pop("preco", None)
    elif col == "parceiros":
        if oculto("contato"):
            for k in ("doc", "telefone", "email"):
                d.pop(k, None)
    elif col == "pedidos":
        if oculto("preco"):
            d.pop("valor_total", None)
            d["itens"] = [{k: v for k, v in i.items() if k != "preco"} for i in d.get("itens", [])]
        if oculto("contato"):
            d.pop("telefone", None)
    elif col == "movimentos":
        if oculto("custo"):
            d.pop("custo_unit", None)
    return d


def _pode_editar_campo(p: dict, c: str) -> bool:
    return p["campos"].get(c, "editar") == "editar"


# ══════════════════════════════════════════════════════════════════════════════
# ESTADO
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/estado")
def estado(request: Request):
    _, p = _ctx(request)
    with ST.trava:
        out = {k: [_filtrar(p, k, {**v, "id": i}) for i, v in ST.dados[k].items()] for k in COLS}
        cfg = {k: v for k, v in ST.config.items() if k != "seq"}
    return {**out, "config": cfg, "perm": p, "locais": LOCAIS, "destinos": DESTINOS, "origens_destino": ORIGENS_DESTINO,
            "hoje": hoje(), "agora": agora()}


@router.get("/kardex/{pid}")
def kardex(pid: str, request: Request):
    _, p = _ctx(request)
    docs = banco.db().collection(COLS["movimentos"]).where("produto_id", "==", pid).stream(timeout=banco.TIMEOUT)
    movs = [_filtrar(p, "movimentos", {**(d.to_dict() or {}), "id": d.id}) for d in docs]
    movs.sort(key=lambda m: m.get("em", ""))
    return {"movimentos": movs}


# ══════════════════════════════════════════════════════════════════════════════
# CADASTROS
# ══════════════════════════════════════════════════════════════════════════════
CAMPOS_PRODUTO = ["sku", "nome", "categoria", "unidade", "custo", "preco", "fornecedor_id", "minimo", "volumes", "ean", "ativo", "obs"]
CAMPOS_PARCEIRO = ["tipo", "nome", "codigo", "doc", "telefone", "email", "endereco", "capacidade", "placa", "ativo", "obs"]   # codigo = código do cliente (liga com os Tickets)
TIPOS_PARCEIRO = ["cliente", "fornecedor", "motorista", "veiculo"]


def _limpar_produto(c: dict, p: dict, atual: dict | None) -> dict:
    d = dict(atual or {"ativo": True, "unidade": "un", "categoria": "Geral", "minimo": 0, "volumes": 1})
    for k in CAMPOS_PRODUTO:
        if k not in c:
            continue
        if k in ("custo", "preco") and not _pode_editar_campo(p, k):
            continue
        v = c[k]
        if k in ("custo", "preco"):
            v = round(max(_num(v), 0), 2)
        elif k in ("minimo", "volumes"):
            v = max(_int(v), 0)
        elif k == "ativo":
            v = bool(v)
        else:
            v = str(v or "").strip()
        d[k] = v
    if not d.get("nome"):
        raise HTTPException(400, "Informe o nome do produto.")
    d["sku"] = (d.get("sku") or "").upper()
    return d


@router.post("/produtos")
async def criar_produto(request: Request):
    u, p = _ctx(request, "produtos", "cadastrar produtos")
    c = await request.json()
    with ST.trava:
        d = _limpar_produto(c, p, None)
        if not d["sku"]:
            d["sku"] = f"P{len(ST.dados['produtos']) + 1:05d}"
        if any(x.get("sku") == d["sku"] for x in ST.dados["produtos"].values()):
            raise HTTPException(409, f"Já existe um produto com o código {d['sku']}.")
        pid = _id()
        d.update(criado_em=agora(), atualizado_em=agora())
        tx = Tx(u)
        tx.put("produtos", pid, d)
        tx.put("saldos", pid, {l: 0 for l in LOCAIS})
        tx.commit()
        return {"ok": True, "produto": _filtrar(p, "produtos", {**d, "id": pid}), "saldo": {**ST.dados["saldos"][pid], "id": pid}}


@router.put("/produtos/{pid}")
async def editar_produto(pid: str, request: Request):
    u, p = _ctx(request, "produtos", "editar produtos")
    c = await request.json()
    with ST.trava:
        atual = ST.dados["produtos"].get(pid)
        if not atual:
            raise HTTPException(404, "Produto não encontrado.")
        d = _limpar_produto(c, p, _copia(atual))
        if any(x.get("sku") == d["sku"] and i != pid for i, x in ST.dados["produtos"].items()):
            raise HTTPException(409, f"Já existe um produto com o código {d['sku']}.")
        d["atualizado_em"] = agora()
        tx = Tx(u)
        tx.put("produtos", pid, d)
        tx.commit()
        return {"ok": True, "produto": _filtrar(p, "produtos", {**d, "id": pid})}


@router.post("/parceiros")
async def criar_parceiro(request: Request):
    return await _salvar_parceiro(request, None)


@router.put("/parceiros/{pid}")
async def editar_parceiro(pid: str, request: Request):
    return await _salvar_parceiro(request, pid)


async def _salvar_parceiro(request: Request, pid: str | None):
    u, p = _ctx(request, "cadastros", "editar cadastros")
    c = await request.json()
    with ST.trava:
        atual = _copia(ST.dados["parceiros"].get(pid)) if pid else {"ativo": True}
        if pid and atual is None:
            raise HTTPException(404, "Cadastro não encontrado.")
        for k in CAMPOS_PARCEIRO:
            if k not in c:
                continue
            if k in ("doc", "telefone", "email") and not _pode_editar_campo(p, "contato"):
                continue
            v = c[k]
            if k == "endereco":
                v = {kk: str((v or {}).get(kk) or "").strip() for kk in ("logradouro", "numero", "complemento", "bairro", "cidade", "uf", "cep", "referencia")}
            elif k == "capacidade":
                v = max(_int(v), 0)
            elif k == "ativo":
                v = bool(v)
            else:
                v = str(v or "").strip()
            atual[k] = v
        if atual.get("tipo") not in TIPOS_PARCEIRO:
            raise HTTPException(400, "Tipo de cadastro inválido.")
        if not atual.get("nome"):
            raise HTTPException(400, "Informe o nome.")
        pid = pid or _id()
        atual.setdefault("criado_em", agora())
        atual["atualizado_em"] = agora()
        tx = Tx(u)
        tx.put("parceiros", pid, atual)
        tx.commit()
        return {"ok": True, "parceiro": _filtrar(p, "parceiros", {**atual, "id": pid})}


# ══════════════════════════════════════════════════════════════════════════════
# ESTOQUE — entrada, ajuste, transferência
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/estoque/entrada")
async def entrada(request: Request):
    u, p = _ctx(request, "estoque", "lançar entradas")
    c = await request.json()
    itens = c.get("itens") or []
    if not itens:
        raise HTTPException(400, "Inclua ao menos um item.")
    doc = str(c.get("documento") or "").strip()
    forn = str(c.get("fornecedor_id") or "")
    with ST.trava:
        tx = Tx(u)
        for it in itens:
            pid = str(it.get("produto_id") or "")
            prod = tx.get("produtos", pid)
            if prod and "custo" in it and _pode_editar_campo(p, "custo") and _num(it.get("custo")) > 0:
                prod["custo"] = round(_num(it["custo"]), 2)   # última compra vira custo
                tx.put("produtos", pid, prod)
            tx.mover(pid, it.get("qtd"), EXTERNO, "disponivel", "entrada", ref=doc, obs=str(c.get("obs") or ""),
                     extra={"fornecedor_id": forn})
        tx.commit()
        return {"ok": True, **_parcial(p, tx)}


@router.post("/estoque/ajuste")
async def ajuste(request: Request):
    """Inventário: informa a contagem real de um local; o sistema lança a diferença."""
    u, p = _ctx(request, "ajuste", "ajustar estoque")
    c = await request.json()
    pid, local = str(c.get("produto_id") or ""), str(c.get("local") or "disponivel")
    if local not in LOCAIS or local in ("entregue", "reservado", "transito"):
        raise HTTPException(400, "Esse local não pode ser ajustado por inventário.")
    contado = _int(c.get("contado"))
    if contado < 0:
        raise HTTPException(400, "Contagem não pode ser negativa.")
    with ST.trava:
        tx = Tx(u)
        s = tx.saldo(pid)
        dif = contado - s.get(local, 0)
        motivo = str(c.get("motivo") or "Inventário")
        if dif > 0:
            tx.mover(pid, dif, EXTERNO, local, "ajuste", obs=motivo)
        elif dif < 0:
            tx.mover(pid, -dif, local, "perdas" if c.get("como_perda") else EXTERNO, "ajuste", obs=motivo)
        tx.commit()
        return {"ok": True, "diferenca": dif, **_parcial(p, tx)}


@router.post("/estoque/transferir")
async def transferir(request: Request):
    """Destinação de retornos (triagem → estoque/outlet/assistência/AT/fornecedor/perdas)
    e volta de assistência/AT/fornecedor/outlet."""
    u, p = _ctx(request, "triagem", "destinar retornos")
    c = await request.json()
    de, para = str(c.get("de") or ""), str(c.get("para") or "")
    if de not in ORIGENS_DESTINO or para not in DESTINOS or de == para:
        raise HTTPException(400, "Origem ou destino inválido.")
    with ST.trava:
        tx = Tx(u)
        for it in (c.get("itens") or [{"produto_id": c.get("produto_id"), "qtd": c.get("qtd")}]):
            tx.mover(str(it.get("produto_id") or ""), it.get("qtd"), de, para, "destinacao", ref=str(c.get("ref") or ""),
                     obs=str(c.get("obs") or ""), extra={"condicao": str(c.get("condicao") or ""), "motivo": str(c.get("motivo") or "")})
        tx.commit()
        return {"ok": True, **_parcial(p, tx)}


def _parcial(p: dict, tx: Tx) -> dict:
    """Devolve só o que mudou (o navegador atualiza o próprio estado)."""
    out: dict[str, list] = {k: [] for k in COLS}
    for (col, i), d in tx.mud.items():
        if d is not None:
            out[col].append(_filtrar(p, col, {**d, "id": i}))
    out["movimentos"] = [_filtrar(p, "movimentos", m) for m in tx.movs]
    out["removidos"] = [{"col": col, "id": i} for (col, i), d in tx.mud.items() if d is None]
    return {"mudou": out}


# ══════════════════════════════════════════════════════════════════════════════
# PEDIDOS
# ══════════════════════════════════════════════════════════════════════════════
def _hist(ped: dict, u: dict, evento: str, em: str | None = None):
    ped.setdefault("historico", []).append({"em": em or agora(), "por": u.get("login", ""), "evento": evento})


def _itens_validos(tx: Tx, itens, com_preco=True) -> list[dict]:
    out = {}
    for it in itens or []:
        pid = str(it.get("produto_id") or "")
        q = _int(it.get("qtd"))
        if q <= 0:
            continue
        prod = tx.get("produtos", pid)
        if not prod:
            raise HTTPException(400, "Produto inválido no pedido.")
        if pid in out:
            out[pid]["qtd"] += q
        else:
            out[pid] = {"produto_id": pid, "qtd": q}
            if com_preco:
                out[pid]["preco"] = round(_num(it.get("preco"), _num(prod.get("preco"))), 2)
    return list(out.values())


def _reservar(tx: Tx, ped: dict, em=None):
    falta = []
    for it in ped.get("pendentes", []):           # confere tudo antes de mexer em qualquer saldo
        tem = tx.saldo(it["produto_id"]).get("disponivel", 0)
        if tem < it["qtd"]:
            falta.append(f"{(tx.get('produtos', it['produto_id']) or {}).get('nome', '?')} (tem {tem}, precisa {it['qtd']})")
    if falta:
        raise HTTPException(409, "Estoque disponível insuficiente: " + "; ".join(falta) + ".")
    for it in ped.get("pendentes", []):
        tx.mover(it["produto_id"], it["qtd"], "disponivel", "reservado", "reserva", ref=f"PED {ped['numero']}", em=em)
    ped["reservado"] = True


def _liberar(tx: Tx, ped: dict, motivo="liberação"):
    if ped.get("reservado"):
        for it in ped.get("pendentes", []):
            tx.mover(it["produto_id"], it["qtd"], "reservado", "disponivel", "liberacao", ref=f"PED {ped['numero']}", obs=motivo)
    ped["reservado"] = False


def _num_seq(tx: Tx, chave: str) -> int:
    cfg = tx.config()
    cfg["seq"][chave] = int(cfg["seq"].get(chave, 0)) + 1
    return cfg["seq"][chave]


def _total(ped: dict) -> float:
    return round(sum(_num(i.get("preco")) * _int(i.get("qtd")) for i in ped.get("itens", [])) + _num(ped.get("frete")) - _num(ped.get("desconto")), 2)


def _dados_cliente(tx: Tx, ped: dict, c: dict):
    cli = tx.get("parceiros", str(c.get("cliente_id") or ped.get("cliente_id") or ""))
    if not cli or cli.get("tipo") != "cliente":
        raise HTTPException(400, "Selecione um cliente cadastrado.")
    ped["cliente_id"] = c.get("cliente_id") or ped.get("cliente_id")
    ped["cliente_nome"] = cli.get("nome", "")
    ped["telefone"] = cli.get("telefone", "")
    end = c.get("endereco") or ped.get("endereco") or cli.get("endereco") or {}
    ped["endereco"] = {k: str(end.get(k) or "").strip() for k in ("logradouro", "numero", "complemento", "bairro", "cidade", "uf", "cep", "referencia")}


@router.post("/pedidos")
async def criar_pedido(request: Request):
    u, p = _ctx(request, "pedidos", "criar pedidos")
    c = await request.json()
    with ST.trava:
        tx = Tx(u)
        ped = _novo_pedido(tx, u, p, c)
        tx.commit()
        return {"ok": True, **_parcial(p, tx)}


def _novo_pedido(tx: Tx, u: dict, p: dict, c: dict, em: str | None = None) -> dict:
    tipo = c.get("tipo") if c.get("tipo") in ("venda", "troca") else "venda"
    ped = {"tipo": tipo, "status": "rascunho", "reservado": False, "tentativas": [], "historico": [],
           "obs": str(c.get("obs") or ""), "criado_em": em or agora(), "criado_por": u.get("login", ""),
           "vendedor": str(c.get("vendedor") or ""), "origem_id": str(c.get("origem_id") or ""),
           "motivo_troca": str(c.get("motivo_troca") or ""), "frete": 0.0, "desconto": 0.0}
    _dados_cliente(tx, ped, c)
    ped["itens"] = _itens_validos(tx, c.get("itens"), com_preco=True)
    ped["recolher"] = _itens_validos(tx, c.get("recolher"), com_preco=False) if tipo == "troca" else []
    if not _pode_editar_campo(p, "preco"):
        for i in ped["itens"]:
            i["preco"] = round(_num((tx.get("produtos", i["produto_id"]) or {}).get("preco")), 2)
    else:
        ped["frete"] = round(max(_num(c.get("frete")), 0), 2)
        ped["desconto"] = round(max(_num(c.get("desconto")), 0), 2)
    if not ped["itens"] and not ped["recolher"]:
        raise HTTPException(400, "Inclua ao menos um item.")
    ped["pendentes"] = [{"produto_id": i["produto_id"], "qtd": i["qtd"]} for i in ped["itens"]]
    ped["valor_total"] = _total(ped)
    ped["numero"] = _num_seq(tx, "pedido")
    pid = _id()
    _hist(ped, u, "Pedido criado" + (" (troca)" if tipo == "troca" else ""), em)
    if c.get("confirmar"):
        _reservar(tx, ped, em)
        ped["status"] = "confirmado"
        _hist(ped, u, "Confirmado — estoque reservado", em)
    ped["atualizado_em"] = em or agora()
    tx.put("pedidos", pid, ped)
    ped["id"] = pid
    return ped


@router.put("/pedidos/{pid}")
async def alterar_pedido(pid: str, request: Request):
    """Altera itens/cliente/endereço/obs. Antes da rota a reserva é refeita
    automaticamente (libera o que saiu, reserva o que entrou)."""
    u, p = _ctx(request, "alterar", "alterar pedidos")
    c = await request.json()
    with ST.trava:
        tx = Tx(u)
        ped = tx.get("pedidos", pid)
        if not ped:
            raise HTTPException(404, "Pedido não encontrado.")
        if ped["status"] in ("em_rota", "entregue", "cancelado", "recusado"):
            raise HTTPException(409, "Pedido em rota ou finalizado não pode ser alterado.")
        if ped.get("tentativas") and "itens" in c:
            raise HTTPException(409, "Este pedido já teve tentativa de entrega: altere só dados de entrega. Para itens, faça uma troca.")
        mudou = []
        if "cliente_id" in c or "endereco" in c:
            _dados_cliente(tx, ped, c)
            mudou.append("cliente/endereço")
        if "obs" in c:
            ped["obs"] = str(c.get("obs") or "")
            mudou.append("observação")
        if "itens" in c or "recolher" in c:
            estava = ped.get("reservado")
            _liberar(tx, ped, "alteração do pedido")
            if "itens" in c:
                novos = _itens_validos(tx, c.get("itens"))
                if not _pode_editar_campo(p, "preco"):
                    antigos = {i["produto_id"]: i.get("preco") for i in ped["itens"]}
                    for i in novos:
                        i["preco"] = antigos.get(i["produto_id"], round(_num((tx.get("produtos", i["produto_id"]) or {}).get("preco")), 2))
                ped["itens"] = novos
                ped["pendentes"] = [{"produto_id": i["produto_id"], "qtd": i["qtd"]} for i in novos]
            if "recolher" in c and ped["tipo"] == "troca":
                ped["recolher"] = _itens_validos(tx, c.get("recolher"), com_preco=False)
            if not ped["itens"] and not ped.get("recolher"):
                raise HTTPException(400, "O pedido ficaria sem itens. Cancele em vez disso.")
            if estava:
                _reservar(tx, ped)
            mudou.append("itens")
        if _pode_editar_campo(p, "preco"):
            for k in ("frete", "desconto"):
                if k in c:
                    ped[k] = round(max(_num(c[k]), 0), 2)
                    mudou.append(k)
        ped["valor_total"] = _total(ped)
        if mudou:
            _hist(ped, u, "Alterado: " + ", ".join(dict.fromkeys(mudou)))
        ped["atualizado_em"] = agora()
        tx.put("pedidos", pid, ped)
        # mantém a carga coerente
        if ped.get("carga_id"):
            car = tx.get("cargas", ped["carga_id"])
            if car:
                car["atualizado_em"] = agora()
                tx.put("cargas", ped["carga_id"], car)
        tx.commit()
        return {"ok": True, **_parcial(p, tx)}


@router.post("/pedidos/{pid}/acao")
async def acao_pedido(pid: str, request: Request):
    u, p = _ctx(request)
    c = await request.json()
    a = c.get("acao")
    req = {"confirmar": "pedidos", "cancelar": "cancelar", "agendar": "agendar", "desagendar": "agendar", "reservar": "pedidos"}
    if a not in req:
        raise HTTPException(400, "Ação inválida.")
    if not p["acoes"].get(req[a]):
        raise HTTPException(403, "Sem permissão para essa ação.")
    with ST.trava:
        tx = Tx(u)
        ped = tx.get("pedidos", pid)
        if not ped:
            raise HTTPException(404, "Pedido não encontrado.")
        st = ped["status"]
        if a == "confirmar":
            if st != "rascunho":
                raise HTTPException(409, "Só pedidos em rascunho podem ser confirmados.")
            _reservar(tx, ped)
            ped["status"] = "confirmado"
            _hist(ped, u, "Confirmado — estoque reservado")
        elif a == "reservar":
            if ped.get("reservado") or st not in ("reagendar", "confirmado"):
                raise HTTPException(409, "Nada a reservar.")
            _reservar(tx, ped)
            ped["sem_estoque"] = False
            _hist(ped, u, "Reserva refeita")
        elif a == "cancelar":
            if st in ("em_rota", "entregue", "cancelado", "recusado"):
                raise HTTPException(409, "Esse pedido não pode mais ser cancelado.")
            _liberar(tx, ped, "cancelamento")
            if ped.get("carga_id"):
                _tirar_da_carga(tx, ped, pid)
            ped["status"] = "cancelado"
            ped["motivo_cancelamento"] = str(c.get("motivo") or "")
            _hist(ped, u, "Cancelado" + (f": {ped['motivo_cancelamento']}" if ped["motivo_cancelamento"] else ""))
        elif a == "agendar":
            if st not in ("confirmado", "agendado", "reagendar"):
                raise HTTPException(409, "Confirme o pedido antes de agendar.")
            if not ped.get("reservado") and ped.get("pendentes"):
                raise HTTPException(409, "Sem estoque reservado para a reposição. Use 'Reservar' quando houver saldo.")
            data = str(c.get("data") or "")
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", data):
                raise HTTPException(400, "Data inválida.")
            ped["agendamento"] = {"data": data, "janela": str(c.get("janela") or ""), "obs": str(c.get("obs") or "")}
            ped["status"] = "agendado"
            _hist(ped, u, f"Agendado para {data[8:10]}/{data[5:7]}" + (f" ({ped['agendamento']['janela']})" if ped["agendamento"]["janela"] else ""))
        elif a == "desagendar":
            if st != "agendado":
                raise HTTPException(409, "Pedido não está agendado.")
            ped["agendamento"] = None
            ped["status"] = "confirmado"
            _hist(ped, u, "Agendamento removido")
        ped["atualizado_em"] = agora()
        tx.put("pedidos", pid, ped)
        tx.commit()
        return {"ok": True, **_parcial(p, tx)}


# ══════════════════════════════════════════════════════════════════════════════
# CARGAS — montagem, saída (baixa automática), baixa de entrega
# ══════════════════════════════════════════════════════════════════════════════
def _tirar_da_carga(tx: Tx, ped: dict, pid: str):
    car = tx.get("cargas", ped["carga_id"])
    if car:
        if car["status"] != "montando":
            raise HTTPException(409, "A carga já saiu.")
        car["pedidos"] = [x for x in car["pedidos"] if x != pid]
        car["atualizado_em"] = agora()
        tx.put("cargas", ped["carga_id"], car)
    ped["carga_id"] = ""
    if ped["status"] == "em_carga":
        ped["status"] = "agendado"


@router.post("/cargas")
async def criar_carga(request: Request):
    u, p = _ctx(request, "cargas", "montar cargas")
    c = await request.json()
    with ST.trava:
        tx = Tx(u)
        car = _nova_carga(tx, u, c)
        tx.commit()
        return {"ok": True, **_parcial(p, tx), "carga_id": car["id"]}


def _nova_carga(tx: Tx, u: dict, c: dict, em: str | None = None) -> dict:
    data = str(c.get("data") or hoje())
    car = {"numero": _num_seq(tx, "carga"), "data": data, "veiculo_id": str(c.get("veiculo_id") or ""),
           "motorista_id": str(c.get("motorista_id") or ""), "ajudante": str(c.get("ajudante") or ""),
           "pedidos": [], "status": "montando", "baixas": {}, "obs": str(c.get("obs") or ""),
           "criado_em": em or agora(), "criado_por": u.get("login", ""), "atualizado_em": em or agora()}
    cid = _id()
    tx.put("cargas", cid, car)
    car["id"] = cid
    _definir_pedidos_carga(tx, u, cid, car, c.get("pedidos") or [], em)
    return car


def _definir_pedidos_carga(tx: Tx, u: dict, cid: str, car: dict, ids: list, em=None):
    if car["status"] != "montando":
        raise HTTPException(409, "A carga já saiu; não dá para mexer nos pedidos.")
    ids = list(dict.fromkeys(str(x) for x in ids))
    for pid in [x for x in car["pedidos"] if x not in ids]:       # saem
        ped = tx.get("pedidos", pid)
        if ped and ped.get("carga_id") == cid:
            ped["carga_id"] = ""
            ped["status"] = "agendado"
            _hist(ped, u, f"Retirado da carga {car['numero']}", em)
            ped["atualizado_em"] = em or agora()
            tx.put("pedidos", pid, ped)
    for pid in ids:                                                  # entram
        ped = tx.get("pedidos", pid)
        if not ped:
            raise HTTPException(400, "Pedido inexistente na carga.")
        if ped.get("carga_id") == cid:
            continue
        if ped["status"] != "agendado":
            raise HTTPException(409, f"Pedido {ped['numero']} precisa estar agendado (está {ped['status']}).")
        if ped.get("carga_id"):
            raise HTTPException(409, f"Pedido {ped['numero']} já está em outra carga.")
        ped["carga_id"] = cid
        ped["status"] = "em_carga"
        _hist(ped, u, f"Incluído na carga {car['numero']}", em)
        ped["atualizado_em"] = em or agora()
        tx.put("pedidos", pid, ped)
    car["pedidos"] = ids
    car["atualizado_em"] = em or agora()
    tx.put("cargas", cid, car)


@router.put("/cargas/{cid}")
async def editar_carga(cid: str, request: Request):
    u, p = _ctx(request, "cargas", "montar cargas")
    c = await request.json()
    with ST.trava:
        tx = Tx(u)
        car = tx.get("cargas", cid)
        if not car:
            raise HTTPException(404, "Carga não encontrada.")
        for k in ("veiculo_id", "motorista_id", "ajudante", "obs", "data"):
            if k in c:
                if car["status"] != "montando" and k == "data":
                    continue
                car[k] = str(c[k] or "")
        car["id"] = cid
        if "pedidos" in c:
            _definir_pedidos_carga(tx, u, cid, car, c["pedidos"])
        else:
            car["atualizado_em"] = agora()
            tx.put("cargas", cid, {k: v for k, v in car.items() if k != "id"})
        if "pedidos" in c:
            tx.put("cargas", cid, {k: v for k, v in tx.get("cargas", cid).items() if k != "id"})
        tx.commit()
        return {"ok": True, **_parcial(p, tx)}


@router.delete("/cargas/{cid}")
def excluir_carga(cid: str, request: Request):
    """Desfaz uma carga que ainda não saiu: os pedidos voltam para 'agendado'."""
    u, p = _ctx(request, "cargas", "montar cargas")
    with ST.trava:
        tx = Tx(u)
        car = tx.get("cargas", cid)
        if not car:
            raise HTTPException(404, "Carga não encontrada.")
        if car["status"] != "montando":
            raise HTTPException(409, "Só cargas que ainda não saíram podem ser desfeitas.")
        car["id"] = cid
        _definir_pedidos_carga(tx, u, cid, car, [])
        tx.put("cargas", cid, None)
        tx.commit()
        return {"ok": True, **_parcial(p, tx)}


@router.post("/cargas/{cid}/sair")
async def sair_carga(cid: str, request: Request):
    u, p = _ctx(request, "cargas", "liberar cargas")
    with ST.trava:
        tx = Tx(u)
        _sair(tx, u, cid)
        tx.commit()
        return {"ok": True, **_parcial(p, tx)}


def _sair(tx: Tx, u: dict, cid: str, em=None):
    car = tx.get("cargas", cid)
    if not car:
        raise HTTPException(404, "Carga não encontrada.")
    if car["status"] != "montando":
        raise HTTPException(409, "Essa carga já saiu.")
    if not car["pedidos"]:
        raise HTTPException(400, "Carga vazia.")
    for pid in car["pedidos"]:
        ped = tx.get("pedidos", pid)
        for it in ped.get("pendentes", []):
            tx.mover(it["produto_id"], it["qtd"], "reservado", "transito", "saida_rota", ref=f"CARGA {car['numero']} · PED {ped['numero']}", em=em)
        ped["reservado"] = False
        ped["status"] = "em_rota"
        _hist(ped, u, f"Saiu para entrega (carga {car['numero']})", em)
        ped["atualizado_em"] = em or agora()
        tx.put("pedidos", pid, ped)
    car["status"] = "em_rota"
    car["saiu_em"] = em or agora()
    car["atualizado_em"] = em or agora()
    tx.put("cargas", cid, {k: v for k, v in car.items() if k != "id"})


@router.post("/cargas/{cid}/baixa")
async def baixa_entrega(cid: str, request: Request):
    u, p = _ctx(request, "baixa", "dar baixa de entregas")
    c = await request.json()
    with ST.trava:
        tx = Tx(u)
        _baixa(tx, u, cid, c)
        tx.commit()
        resposta = {"ok": True, **_parcial(p, tx)}
    # Avaria / recusa / ausência → ticket automático no módulo Tickets (se ligado em Ajustes).
    # Em segundo plano: a baixa nunca espera nem falha por causa disso.
    if c.get("resultado") in ("avaria", "recusado", "ausente"):
        try:
            import tickets
            threading.Thread(target=tickets.auto_de_baixa, args=(str(c.get("pedido_id") or ""), c.get("resultado"), str(c.get("motivo") or ""), u),
                             daemon=True).start()
        except Exception as ex:  # noqa: BLE001
            print(f"[erp] não abriu ticket automático: {ex}")
    return resposta


def _baixa(tx: Tx, u: dict, cid: str, c: dict, em=None):
    car = tx.get("cargas", cid)
    if not car:
        raise HTTPException(404, "Carga não encontrada.")
    if car["status"] != "em_rota":
        raise HTTPException(409, "A carga precisa estar em rota para dar baixa.")
    pid = str(c.get("pedido_id") or "")
    if pid not in car["pedidos"]:
        raise HTTPException(400, "Pedido não pertence a essa carga.")
    if pid in car.get("baixas", {}):
        raise HTTPException(409, "Esse pedido já teve baixa nessa carga.")
    ped = tx.get("pedidos", pid)
    res = c.get("resultado")
    if res not in ("entregue", "ausente", "avaria", "recusado"):
        raise HTTPException(400, "Resultado inválido.")
    ref = f"CARGA {car['numero']} · PED {ped['numero']}"
    pend = {i["produto_id"]: i["qtd"] for i in ped.get("pendentes", [])}
    avariados = {}
    if res == "avaria":
        for it in c.get("avariados") or []:
            q = _int(it.get("qtd"))
            pr = str(it.get("produto_id") or "")
            if q > 0:
                if q > pend.get(pr, 0):
                    raise HTTPException(400, "Quantidade avariada maior que a enviada.")
                avariados[pr] = avariados.get(pr, 0) + q
        if not avariados:
            raise HTTPException(400, "Informe quais itens chegaram avariados.")
    motivo = str(c.get("motivo") or "")
    if res == "entregue" or res == "avaria":
        for pr, q in pend.items():
            bom = q - avariados.get(pr, 0)
            if bom > 0:
                tx.mover(pr, bom, "transito", "entregue", "entrega", ref=ref, em=em)
            if avariados.get(pr):
                tx.mover(pr, avariados[pr], "transito", "triagem", "retorno_avaria", ref=ref, obs=motivo, em=em,
                         extra={"motivo": motivo, "pedido_id": pid})
        for it in ped.get("recolher", []):                     # troca: o que foi recolhido do cliente
            tx.mover(it["produto_id"], it["qtd"], EXTERNO, "triagem", "recolha_troca", ref=ref, obs=ped.get("motivo_troca", ""), em=em,
                     extra={"motivo": ped.get("motivo_troca", ""), "pedido_id": pid})
        ped["recolher_feito"] = bool(ped.get("recolher"))
        if avariados:
            ped["pendentes"] = [{"produto_id": k, "qtd": v} for k, v in avariados.items()]
            ped["status"] = "reagendar"
            ped["pendencia"] = "reposicao"
            try:
                _reservar(tx, ped, em)
                ped["sem_estoque"] = False
            except HTTPException:
                ped["reservado"] = False
                ped["sem_estoque"] = True
        else:
            ped["pendentes"] = []
            ped["status"] = "entregue"
            ped["pendencia"] = ""
            ped["entregue_em"] = em or agora()
    elif res == "ausente":
        for pr, q in pend.items():
            tx.mover(pr, q, "transito", "reservado", "retorno_ausente", ref=ref, obs=motivo, em=em)
        ped["reservado"] = True
        ped["status"] = "reagendar"
        ped["pendencia"] = "ausente"
    elif res == "recusado":
        for pr, q in pend.items():
            tx.mover(pr, q, "transito", "triagem", "recusa", ref=ref, obs=motivo, em=em, extra={"motivo": motivo, "pedido_id": pid})
        ped["status"] = "recusado"
        ped["pendentes"] = []
        ped["pendencia"] = ""
    tent = {"n": len(ped.get("tentativas", [])) + 1, "data": car["data"], "carga_id": cid, "carga": car["numero"],
            "motorista_id": car.get("motorista_id", ""), "resultado": res, "motivo": motivo,
            "avariados": [{"produto_id": k, "qtd": v} for k, v in avariados.items()],
            "obs": str(c.get("obs") or ""), "recebedor": str(c.get("recebedor") or ""), "em": em or agora(), "por": u.get("login", "")}
    ped.setdefault("tentativas", []).append(tent)
    ped["carga_id"] = ""
    ped["agendamento"] = None if ped["status"] == "reagendar" else ped.get("agendamento")
    rot = {"entregue": "Entregue", "ausente": "Ausente", "avaria": "Entregue com avaria — reposição pendente", "recusado": "Recusado pelo cliente"}[res]
    _hist(ped, u, f"Tentativa {tent['n']}: {rot}" + (f" ({motivo})" if motivo else ""), em)
    ped["atualizado_em"] = em or agora()
    tx.put("pedidos", pid, ped)
    car.setdefault("baixas", {})[pid] = res
    if len(car["baixas"]) == len(car["pedidos"]):
        car["status"] = "finalizada"
        car["fechada_em"] = em or agora()
    car["atualizado_em"] = em or agora()
    tx.put("cargas", cid, {k: v for k, v in car.items() if k != "id"})


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
@router.put("/config")
async def salvar_config(request: Request):
    u, p = _ctx(request, "configurar", "configurar o ERP")
    c = await request.json()
    with ST.trava:
        tx = Tx(u)
        cfg = tx.config()
        if "empresa" in c:
            cfg["empresa"] = str(c["empresa"] or "").strip() or "Minha Empresa"
        if isinstance(c.get("rotulos"), dict):
            for k, v in c["rotulos"].items():
                if k in LOCAIS and str(v).strip():
                    cfg["rotulos"][k] = str(v).strip()[:40]
        for k in ("janelas", "motivos_avaria", "motivos_ausencia", "motivos_troca", "categorias"):
            if isinstance(c.get(k), list):
                cfg[k] = [str(x).strip()[:40] for x in c[k] if str(x).strip()][:30]
        tx.commit()
        return {"ok": True, "config": {k: v for k, v in ST.config.items() if k != "seq"}}


# ══════════════════════════════════════════════════════════════════════════════
# DADOS DE EXEMPLO — roda o motor de verdade (mesmas regras), datas no passado
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/exemplo")
def exemplo(request: Request):
    u, p = _ctx(request, "configurar", "carregar exemplos")
    with ST.trava:
        if ST.dados["produtos"] or ST.dados["pedidos"]:
            raise HTTPException(409, "O ERP já tem dados. Exemplo só em base vazia.")
        rnd = random.Random(7)
        base = datetime.now(FUSO)
        quando = lambda d, h=8: (base - timedelta(days=d)).replace(hour=h, minute=rnd.randint(0, 59), second=0).strftime("%Y-%m-%dT%H:%M:%S")
        dia = lambda d: (base - timedelta(days=d)).strftime("%Y-%m-%d")

        tx = Tx(u)
        cfg = tx.config()
        cfg["empresa"] = "Empresa Exemplo"
        cfg["categorias"] = ["Colchões", "Bases", "Travesseiros", "Acessórios"]
        prods = [("COL-138-D33", "Colchão Casal D33 138x188", "Colchões", 620, 1290, 6), ("COL-158-MOL", "Colchão Queen Molas 158x198", "Colchões", 1180, 2490, 4),
                 ("COL-088-D28", "Colchão Solteiro D28 88x188", "Colchões", 310, 690, 8), ("BAS-138", "Base Box Casal 138x188", "Bases", 380, 790, 5),
                 ("BAS-158", "Base Box Queen 158x198", "Bases", 460, 990, 4), ("TRA-VIS", "Travesseiro Viscoelástico", "Travesseiros", 45, 129, 30),
                 ("TRA-FIB", "Travesseiro Fibra", "Travesseiros", 18, 49, 40), ("PRO-138", "Protetor Impermeável Casal", "Acessórios", 35, 99, 15)]
        pids = []
        forn_id = _id()
        tx.put("parceiros", forn_id, {"tipo": "fornecedor", "nome": "Fábrica Sono Bom Ltda", "doc": "12.345.678/0001-90", "telefone": "(11) 4000-1000",
                                       "email": "vendas@sonobom.exemplo", "ativo": True, "criado_em": quando(60), "atualizado_em": quando(60)})
        for sku, nome, cat, custo, preco, minimo in prods:
            pid = _id()
            tx.put("produtos", pid, {"sku": sku, "nome": nome, "categoria": cat, "unidade": "un", "custo": custo, "preco": preco,
                                     "fornecedor_id": forn_id, "minimo": minimo, "volumes": 2 if cat == "Bases" else 1, "ativo": True,
                                     "criado_em": quando(60), "atualizado_em": quando(60)})
            tx.put("saldos", pid, {l: 0 for l in LOCAIS})
            pids.append(pid)
        nomes = ["Ana Paula Ribeiro", "Bruno Carvalho", "Camila Fernandes", "Diego Martins", "Eduarda Lopes", "Felipe Araújo", "Gabriela Nunes",
                 "Henrique Barros", "Isabela Moura", "João Vitor Sales", "Larissa Castro", "Marcos Teixeira", "Natália Freitas", "Otávio Rezende",
                 "Patrícia Gomes", "Rafael Duarte", "Sabrina Pires", "Thiago Monteiro"]
        bairros = ["Centro", "Jardim América", "Vila Nova", "Parque das Flores", "Boa Vista", "Santa Cruz"]
        clis = []
        for i, n in enumerate(nomes):
            cid = _id()
            tx.put("parceiros", cid, {"tipo": "cliente", "nome": n, "telefone": f"(11) 9{rnd.randint(1000, 9999)}-{rnd.randint(1000, 9999)}",
                                      "doc": f"{rnd.randint(100, 999)}.{rnd.randint(100, 999)}.{rnd.randint(100, 999)}-{rnd.randint(10, 99)}",
                                      "endereco": {"logradouro": f"Rua {['das Acácias', 'Sete de Setembro', 'XV de Novembro', 'Bela Vista', 'dos Ipês'][i % 5]}",
                                                   "numero": str(rnd.randint(10, 999)), "complemento": "", "bairro": bairros[i % 6], "cidade": "São Paulo",
                                                   "uf": "SP", "cep": f"0{rnd.randint(1000, 9999)}-{rnd.randint(100, 999)}", "referencia": ""},
                                      "ativo": True, "criado_em": quando(50), "atualizado_em": quando(50)})
            clis.append(cid)
        mots, veis = [], []
        for n in ["Carlos Motorista", "Rogério Silva", "Wagner Souza"]:
            i = _id(); mots.append(i)
            tx.put("parceiros", i, {"tipo": "motorista", "nome": n, "telefone": "(11) 98888-0000", "ativo": True, "criado_em": quando(50), "atualizado_em": quando(50)})
        for placa, cap in [("ABC-1D23 · Baú 3/4", 24), ("XYZ-9F87 · VUC", 16)]:
            i = _id(); veis.append(i)
            tx.put("parceiros", i, {"tipo": "veiculo", "nome": placa, "placa": placa[:8], "capacidade": cap, "ativo": True, "criado_em": quando(50), "atualizado_em": quando(50)})
        for pid, (_, _, _, custo, _, minimo) in zip(pids, prods):
            tx.mover(pid, minimo * 5, EXTERNO, "disponivel", "entrada", ref="NF 10234", em=quando(40), extra={"fornecedor_id": forn_id})
        # pedidos ao longo de 5 semanas, em cargas reais
        resultados = ["entregue"] * 15 + ["ausente"] * 3 + ["avaria"] * 3 + ["recusado"]
        for semana in range(5, 0, -1):
            d0 = semana * 7
            peds = []
            # quem ficou ausente / com reposição na semana anterior volta na carga desta semana
            for pid, pd in list(ST.dados["pedidos"].items()) + [(k[1], v) for k, v in tx.mud.items() if k[0] == "pedidos" and v]:
                pd = tx.get("pedidos", pid)
                if pd and pd["status"] == "reagendar" and pd.get("reservado") and pid not in peds and len(peds) < 3:
                    pd["status"] = "agendado"
                    pd["agendamento"] = {"data": dia(d0), "janela": "Tarde", "obs": "Reagendado"}
                    _hist(pd, u, "Reagendado", quando(d0 + 1))
                    tx.put("pedidos", pid, pd)
                    peds.append(pid)
            for k in range(8 - len(peds) // 2):
                itens = [{"produto_id": pids[rnd.choice([0, 1, 2])], "qtd": 1}]
                if rnd.random() < .5:
                    itens.append({"produto_id": pids[3 if itens[0]["produto_id"] == pids[0] else 4], "qtd": 1})
                if rnd.random() < .6:
                    itens.append({"produto_id": pids[rnd.choice([5, 6])], "qtd": rnd.choice([1, 2])})
                ped = _novo_pedido(tx, u, p, {"cliente_id": rnd.choice(clis), "itens": itens, "confirmar": True}, em=quando(d0 + 3, 10))
                ped_db = tx.get("pedidos", ped["id"])
                ped_db["status"] = "agendado"
                ped_db["agendamento"] = {"data": dia(d0), "janela": rnd.choice(["Manhã", "Tarde"]), "obs": ""}
                _hist(ped_db, u, "Agendado", quando(d0 + 2))
                tx.put("pedidos", ped["id"], ped_db)
                peds.append(ped["id"])
            meio = (len(peds) + 1) // 2
            for lote_i, lote in enumerate([peds[:meio], peds[meio:]]):
                car = _nova_carga(tx, u, {"data": dia(d0), "veiculo_id": veis[lote_i], "motorista_id": mots[(semana + lote_i) % 3], "pedidos": lote}, em=quando(d0, 6))
                _sair(tx, u, car["id"], em=quando(d0, 7))
                for pid in lote:
                    res = rnd.choice(resultados)
                    c = {"pedido_id": pid, "resultado": res, "recebedor": "Cliente"}
                    if res == "avaria":
                        pend = tx.get("pedidos", pid)["pendentes"]
                        c["avariados"] = [{"produto_id": pend[0]["produto_id"], "qtd": 1}]
                        c["motivo"] = rnd.choice(["Transporte", "Embalagem", "Manuseio"])
                    if res == "ausente":
                        c["motivo"] = rnd.choice(["Cliente ausente", "Endereço não localizado"])
                    if res == "recusado":
                        c["motivo"] = "Desistência"
                    _baixa(tx, u, car["id"], c, em=quando(d0, rnd.randint(9, 17)))
        # alguns retornos já destinados
        tri = [(pid, s["triagem"]) for pid in pids for s in [tx.saldo(pid)] if s["triagem"] > 0]
        for j, (pid, q) in enumerate(tri[:2]):
            destino = ["assistencia", "disponivel", "fornecedor"][j % 3]
            tx.mover(pid, 1, "triagem", destino, "destinacao", obs="Inspeção", em=quando(3, 15), extra={"condicao": "avariado" if destino != "disponivel" else "novo"})
        # pedidos de hoje/amanhã para operar
        for k in range(5):
            ped = _novo_pedido(tx, u, p, {"cliente_id": clis[k], "itens": [{"produto_id": pids[k % 3], "qtd": 1}, {"produto_id": pids[5], "qtd": 2}], "confirmar": k < 4}, em=quando(1, 11))
            if k < 3:
                pd = tx.get("pedidos", ped["id"])
                pd["status"] = "agendado"
                pd["agendamento"] = {"data": (base + timedelta(days=1)).strftime("%Y-%m-%d"), "janela": "Manhã", "obs": ""}
                _hist(pd, u, "Agendado")
                tx.put("pedidos", ped["id"], pd)
        tx.commit()
        return {"ok": True}
