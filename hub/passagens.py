"""
hub/passagens.py — API do módulo PASSAGENS (VGP) no hub.
─────────────────────────────────────────────────────────────────────────────
Lê e grava EXATAMENTE as mesmas coleções do Parque Aliança (Streamlit),
no mesmo projeto Firestore (wendleydesenvolvimento):

    eventos/{id_evento}                       nome, datas, valor, custo_onibus,
                                              status ("ativo"|"finalizado"),
                                              criado_em, frotas {dia: n}
    eventos/{id_evento}/passageiros/{pax_id}  nome, rg, cpf, grupo, dias_onibus
                                              [{dia, bus}], pago, embarcou,
                                              valor_total, valor_pago
    cadastro_geral/{nome_sem_espacos}         nome, rg, cpf, grupo, ultima_atualizacao

Os ids seguem a MESMA regra do mod_passagens.py — por isso o que é lançado
aqui aparece lá e vice-versa ("aqui e lá"):
    pax_id    = f"{nome}_{rg or 'reserva'}".lower().replace(" ", "")
    evento_id = f"{nome.lower().replace(' ', '_')}_{AAAAMMDD}"

Sem cache nas listas de passageiros/eventos: o Streamlit também escreve,
então cada leitura vem fresca do banco. (Só a busca no cadastro_geral tem
cache curto, porque varre a coleção inteira.)

Permissões (bloco "hub-permissoes" do modulos/passagens.html), conferidas
aqui no servidor: ação por ação e campo por campo.
"""
from __future__ import annotations

import ast
import json
import threading
import time
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

import acesso
import banco

router = APIRouter(prefix="/api/passagens")
MOD = "passagens"
GRUPOS = ["Rosas", "Engenho", "Cohab", "Geral"]
DIAS_VALIDOS = ["Sexta", "Sábado", "Domingo"]
CUSTO_ONIBUS_PADRAO = 1770.0
CAPACIDADE = 46

# campos de passageiro que o usuário pode receber/alterar
CAMPOS_PAX = ["nome", "rg", "cpf", "grupo", "dias_onibus", "pago", "valor_pago", "valor_total", "embarcou"]
# ações que liberam campos específicos mesmo sem "editar"
REGRAS = {"receber": {"pago", "valor_pago"}, "embarque": {"embarcou"}}


# ══════════════════════════════════════════════════════════════════════════════
# util
# ══════════════════════════════════════════════════════════════════════════════
def _db():
    return banco.db()


def _json_seguro(v):
    """Firestore devolve datetime (DatetimeWithNanoseconds) — vira texto ISO.
    NaN/infinito (que o JSON não aceita) viram vazio."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return None  # NaN gravado pelo pandas (importação de planilha no Streamlit)
    if isinstance(v, dict):
        return {k: _json_seguro(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_seguro(x) for x in v]
    return v


def pax_id(nome: str, rg: str) -> str:
    sufixo = rg if rg else "reserva"
    return f"{nome}_{sufixo}".lower().replace(" ", "")


def _num(v, padrao=0.0) -> float:
    try:
        f = float(v)
        return f if f == f else padrao  # NaN
    except (TypeError, ValueError):
        return padrao


def _igual(a, b) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _contexto(request: Request):
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(MOD)
    if esq is None:
        raise HTTPException(404, "Módulo passagens não encontrado (falta modulos/passagens.html).")
    p = acesso.permissoes(u, MOD, esq)
    if not p["acoes"].get("acessar"):
        raise HTTPException(403, "Sem acesso ao módulo Passagens.")
    if not banco.configurado():
        raise HTTPException(503, "Banco não configurado: falta FIRESTORE_CREDS no Render.")
    return u, esq, p


def _exigir(p: dict, acao: str, texto: str):
    if not p["acoes"].get(acao):
        raise HTTPException(403, f"Sem permissão para {texto}.")


def _visivel(p: dict, campo: str) -> bool:
    return p["campos"].get(campo, "editar") != "oculto"


def _editavel(p: dict, campo: str) -> bool:
    return p["campos"].get(campo, "editar") == "editar"


def _pax_para_usuario(doc_id: str, d: dict, p: dict) -> dict:
    out = {k: v for k, v in d.items() if k not in CAMPOS_PAX or _visivel(p, k)}
    out["id"] = doc_id
    return _json_seguro(out)


def _evento_para_usuario(doc_id: str, d: dict, p: dict) -> dict:
    ev = dict(d)
    if not _visivel(p, "valor_total"):
        ev.pop("valor", None)
        ev.pop("custo_onibus", None)
    ev["id"] = doc_id
    ev.setdefault("frotas", {dia: 1 for dia in ev.get("datas", [])})
    return _json_seguro(ev)


def _evento(id_evento: str) -> dict:
    snap = _db().collection("eventos").document(id_evento).get(timeout=banco.TIMEOUT)
    if not snap.exists:
        raise HTTPException(404, "Evento não encontrado (pode ter sido arquivado ou excluído).")
    return snap.to_dict() or {}


def _limpar_viagens(viagens, evento: dict) -> list[dict]:
    datas = evento.get("datas") or []
    frotas = evento.get("frotas") or {}
    out, vistos = [], set()
    for v in viagens or []:
        if not isinstance(v, dict):
            continue
        dia = str(v.get("dia") or "")
        if dia not in datas or dia in vistos:
            continue
        bus = int(_num(v.get("bus"), 1)) or 1
        bus = max(1, min(bus, int(frotas.get(dia, 1) or 1)))
        out.append({"dia": dia, "bus": bus})
        vistos.add(dia)
    # mesma ordem dos dias do evento
    return sorted(out, key=lambda x: datas.index(x["dia"]))


# ── cadastro central (mesma função do Streamlit) ────────────────────────────
_cad_cache: dict = {"t": 0.0, "itens": None}
_cad_trava = threading.Lock()


def _atualizar_cadastro_central(pax: dict):
    _db().collection("cadastro_geral").document(pax["nome"].lower().replace(" ", "")).set({
        "nome": pax["nome"], "rg": pax.get("rg", ""), "cpf": pax.get("cpf", ""),
        "grupo": pax.get("grupo", "Geral"), "ultima_atualizacao": datetime.now(),
    }, merge=True, timeout=banco.TIMEOUT)
    _cad_cache["itens"] = None


def _cadastros() -> list[dict]:
    with _cad_trava:
        if _cad_cache["itens"] is None or time.time() - _cad_cache["t"] > 300:
            _cad_cache["itens"] = [d.to_dict() or {} for d in _db().collection("cadastro_geral").stream(timeout=banco.TIMEOUT)]
            _cad_cache["t"] = time.time()
        return _cad_cache["itens"]


# ══════════════════════════════════════════════════════════════════════════════
# EVENTOS
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/eventos")
def listar_eventos(request: Request):
    _, _, p = _contexto(request)
    docs = _db().collection("eventos").where("status", "==", "ativo").stream(timeout=banco.TIMEOUT)
    eventos = [_evento_para_usuario(d.id, d.to_dict() or {}, p) for d in docs]
    eventos.sort(key=lambda e: str(e.get("criado_em") or ""), reverse=True)
    return {"eventos": eventos, "perm": p, "grupos": GRUPOS, "dias": DIAS_VALIDOS,
            "capacidade": CAPACIDADE, "custo_padrao": CUSTO_ONIBUS_PADRAO}


@router.post("/eventos")
async def criar_evento(request: Request):
    _, _, p = _contexto(request)
    _exigir(p, "eventos", "criar eventos")
    c = await request.json()
    nome = str(c.get("nome") or "").strip()
    datas = [d for d in DIAS_VALIDOS if d in (c.get("datas") or [])]
    if not nome or not datas:
        raise HTTPException(400, "Informe o nome e ao menos um dia.")
    id_evento = f"{nome.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"
    dados = {"nome": nome, "datas": datas, "valor": _num(c.get("valor"), 50.0),
             "custo_onibus": _num(c.get("custo_onibus"), CUSTO_ONIBUS_PADRAO),
             "status": "ativo", "criado_em": datetime.now(), "frotas": {d: 1 for d in datas}}
    _db().collection("eventos").document(id_evento).set(dados, timeout=banco.TIMEOUT)
    return {"ok": True, "evento": _evento_para_usuario(id_evento, dados, p)}


@router.put("/eventos/{id_evento}")
async def editar_evento(id_evento: str, request: Request):
    _, _, p = _contexto(request)
    _exigir(p, "eventos", "ajustar eventos")
    ev = _evento(id_evento)
    c = await request.json()
    dados = {}
    if "valor" in c:
        dados["valor"] = _num(c["valor"], ev.get("valor", 50.0))
    if "custo_onibus" in c:
        dados["custo_onibus"] = _num(c["custo_onibus"], ev.get("custo_onibus", CUSTO_ONIBUS_PADRAO))
    if dados:
        _db().collection("eventos").document(id_evento).update(dados, timeout=banco.TIMEOUT)
    return {"ok": True, "evento": _evento_para_usuario(id_evento, {**ev, **dados}, p)}


@router.post("/eventos/{id_evento}/onibus")
async def adicionar_onibus(id_evento: str, request: Request):
    _, _, p = _contexto(request)
    _exigir(p, "eventos", "adicionar ônibus")
    ev = _evento(id_evento)
    dia = str((await request.json()).get("dia") or "")
    if dia not in (ev.get("datas") or []):
        raise HTTPException(400, "Dia inválido para este evento.")
    frotas = ev.get("frotas") or {d: 1 for d in ev["datas"]}
    frotas[dia] = int(frotas.get(dia, 1)) + 1
    _db().collection("eventos").document(id_evento).update({"frotas": frotas}, timeout=banco.TIMEOUT)
    return {"ok": True, "evento": _evento_para_usuario(id_evento, {**ev, "frotas": frotas}, p)}


@router.post("/eventos/{id_evento}/arquivar")
async def arquivar_evento(id_evento: str, request: Request):
    _, _, p = _contexto(request)
    _exigir(p, "arquivar", "arquivar eventos")
    ev = _evento(id_evento)
    conf = str((await request.json()).get("confirmacao") or "").strip().lower()
    if conf != str(ev.get("nome", "")).strip().lower():
        raise HTTPException(400, "Nome não confere.")
    _db().collection("eventos").document(id_evento).update({"status": "finalizado"}, timeout=banco.TIMEOUT)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# PASSAGEIROS
# ══════════════════════════════════════════════════════════════════════════════
def _col_pax(id_evento: str):
    return _db().collection("eventos").document(id_evento).collection("passageiros")


@router.get("/eventos/{id_evento}/passageiros")
def listar_passageiros(id_evento: str, request: Request):
    _, _, p = _contexto(request)
    ev = _evento(id_evento)
    pax = [_pax_para_usuario(d.id, d.to_dict() or {}, p) for d in _col_pax(id_evento).stream(timeout=banco.TIMEOUT)]
    pax.sort(key=lambda x: str(x.get("nome", "")).lower())
    return {"evento": _evento_para_usuario(id_evento, ev, p), "passageiros": pax, "perm": p, "lido_em": time.time()}


@router.post("/eventos/{id_evento}/passageiros")
async def nova_reserva(id_evento: str, request: Request):
    _, _, p = _contexto(request)
    _exigir(p, "reservar", "criar reservas")
    ev = _evento(id_evento)
    c = (await request.json()).get("dados") or {}
    nome = str(c.get("nome") or "").strip()
    viagens = _limpar_viagens(c.get("dias_onibus"), ev)
    if not nome or not viagens:
        raise HTTPException(400, "Informe o nome e selecione ao menos um dia.")
    rg = str(c.get("rg") or "").strip() if _editavel(p, "rg") else ""
    cpf = str(c.get("cpf") or "").strip() if _editavel(p, "cpf") else ""
    grupo = str(c.get("grupo") or "Geral")
    if grupo not in GRUPOS or not _editavel(p, "grupo"):
        grupo = "Geral"
    pid = pax_id(nome, rg)
    ref = _col_pax(id_evento).document(pid)
    if ref.get(timeout=banco.TIMEOUT).exists:
        raise HTTPException(409, f"Já existe uma reserva para {nome}{' (RG ' + rg + ')' if rg else ''} neste evento. "
                                 "Abra a reserva existente para alterar.")
    vt = _num(ev.get("valor"), 0) * len(viagens)
    pode_pagar = (p["acoes"].get("receber") or p["acoes"].get("editar")) and _editavel(p, "pago")
    pago = bool(c.get("pago")) and bool(pode_pagar)
    dados = {"nome": nome, "rg": rg, "cpf": cpf, "grupo": grupo, "dias_onibus": viagens,
             "pago": pago, "embarcou": False, "valor_total": vt, "valor_pago": vt if pago else 0.0}
    ref.set(dados, timeout=banco.TIMEOUT)
    _atualizar_cadastro_central(dados)
    return {"ok": True, "passageiro": _pax_para_usuario(pid, dados, p)}


@router.put("/eventos/{id_evento}/passageiros/{pid}")
async def alterar_passageiro(id_evento: str, pid: str, request: Request):
    """Salva o "Gerenciar Reserva". Só os campos enviados são considerados;
    campos ocultos para o usuário simplesmente não vêm e ficam como estão."""
    _, esq, p = _contexto(request)
    ev = _evento(id_evento)
    ref = _col_pax(id_evento).document(pid)
    snap = ref.get(timeout=banco.TIMEOUT)
    if not snap.exists:
        raise HTTPException(404, "Reserva não encontrada (pode ter sido alterada ou excluída no outro sistema). Atualize a tela.")
    atual = snap.to_dict() or {}
    novos = {k: v for k, v in ((await request.json()).get("dados") or {}).items() if k in CAMPOS_PAX and k != "valor_total"}

    # normaliza
    if "nome" in novos:
        novos["nome"] = str(novos["nome"] or "").strip()
        if not novos["nome"]:
            raise HTTPException(400, "O nome não pode ficar vazio.")
    for k in ("rg", "cpf"):
        if k in novos:
            novos[k] = str(novos[k] or "").strip()
    if "grupo" in novos and novos["grupo"] not in GRUPOS:
        novos["grupo"] = "Geral"
    if "dias_onibus" in novos:
        novos["dias_onibus"] = _limpar_viagens(novos["dias_onibus"], ev)
    if "valor_pago" in novos:
        novos["valor_pago"] = max(_num(novos["valor_pago"]), 0.0)
    for k in ("pago", "embarcou"):
        if k in novos:
            novos[k] = bool(novos[k])

    mudados = [k for k, v in novos.items() if not _igual(atual.get(k), v)]
    proibidos = []
    for k in mudados:
        if any(p["acoes"].get(a) and k in campos for a, campos in REGRAS.items()) and _editavel(p, k):
            continue
        if not p["acoes"].get("editar") or not _editavel(p, k):
            proibidos.append(k)
    if proibidos:
        nomes = ", ".join(esq["campos"].get(k, k) for k in proibidos)
        raise HTTPException(403, f"Sem permissão para alterar: {nomes}.")
    if not mudados:
        return {"ok": True, "passageiro": _pax_para_usuario(pid, atual, p), "mudados": []}

    final = {**atual, **{k: novos[k] for k in mudados}}
    if "dias_onibus" in mudados:
        final["valor_total"] = _num(ev.get("valor"), 0) * len(final["dias_onibus"])
    final.setdefault("embarcou", False)

    novo_id = pax_id(final["nome"], final.get("rg", ""))
    if novo_id != pid:
        if _col_pax(id_evento).document(novo_id).get(timeout=banco.TIMEOUT).exists:
            raise HTTPException(409, "Já existe outra reserva com esse nome e RG neste evento.")
        _col_pax(id_evento).document(novo_id).set(final, timeout=banco.TIMEOUT)
        ref.delete(timeout=banco.TIMEOUT)
    else:
        ref.set(final, timeout=banco.TIMEOUT)
    if {"nome", "rg", "cpf", "grupo"} & set(mudados):
        _atualizar_cadastro_central(final)
    return {"ok": True, "passageiro": _pax_para_usuario(novo_id, final, p), "mudados": mudados, "id_antigo": pid}


@router.post("/eventos/{id_evento}/passageiros/{pid}/embarque")
async def marcar_embarque(id_evento: str, pid: str, request: Request):
    _, _, p = _contexto(request)
    if not ((p["acoes"].get("embarque") or p["acoes"].get("editar")) and _editavel(p, "embarcou")):
        raise HTTPException(403, "Sem permissão para confirmar embarque.")
    status = bool((await request.json()).get("embarcou"))
    ref = _col_pax(id_evento).document(pid)
    if not ref.get(timeout=banco.TIMEOUT).exists:
        raise HTTPException(404, "Reserva não encontrada. Atualize a tela.")
    ref.update({"embarcou": status}, timeout=banco.TIMEOUT)
    return {"ok": True, "embarcou": status}


@router.delete("/eventos/{id_evento}/passageiros/{pid}")
def excluir_passageiro(id_evento: str, pid: str, request: Request):
    _, _, p = _contexto(request)
    _exigir(p, "excluir", "excluir reservas")
    _col_pax(id_evento).document(pid).delete(timeout=banco.TIMEOUT)
    return {"ok": True}


@router.get("/cadastro")
def buscar_cadastro(request: Request, q: str = ""):
    _, _, p = _contexto(request)
    if not p["acoes"].get("reservar"):
        return {"itens": []}
    q = q.lower().strip()
    if len(q) < 2:
        return {"itens": []}
    achados = [c for c in _cadastros() if q in str(c.get("nome", "")).lower()][:8]
    return {"itens": [_json_seguro({k: v for k, v in c.items() if k in ("nome", "grupo") or _visivel(p, k)}) for c in achados]}


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTAR PLANILHA (mesmas regras do Streamlit)
# ══════════════════════════════════════════════════════════════════════════════
def _parse_dias(valor) -> list[dict]:
    if isinstance(valor, list):
        return [v for v in valor if isinstance(v, dict) and v.get("dia")]
    texto = str(valor or "").strip()
    if not texto or texto == "[]" or texto.lower() == "nan":
        return []
    try:
        r = ast.literal_eval(texto)
        if isinstance(r, list):
            return [v for v in r if isinstance(v, dict) and v.get("dia")]
    except Exception:  # noqa: BLE001
        pass
    return []


def _bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "sim", "s", "verdadeiro", "yes")
    return bool(v)


def _linha(row: dict) -> dict | None:
    nome = str(row.get("nome") or "").strip()
    if not nome or nome.lower() == "nan":
        return None
    grupo = str(row.get("grupo") or "").strip() or "Geral"
    limpo = lambda k: "" if str(row.get(k) or "").strip().lower() in ("", "nan", "none") else str(row.get(k)).strip()
    return {"nome": nome, "rg": limpo("rg"), "cpf": limpo("cpf"), "grupo": grupo if grupo in GRUPOS else "Geral",
            "dias_onibus": _parse_dias(row.get("dias_onibus")), "pago": _bool(row.get("pago")),
            "embarcou": _bool(row.get("embarcou")), "valor_total": _num(row.get("valor_total")),
            "valor_pago": _num(row.get("valor_pago"))}


def _analisar(linhas: list[dict]):
    datas, frotas, valores = [], {}, []
    for row in linhas:
        dias = _parse_dias(row.get("dias_onibus"))
        vt = _num(row.get("valor_total"))
        if dias and vt:
            valores.append(round(vt / len(dias), 2))
        for v in dias:
            d = v.get("dia")
            if d and d not in datas:
                datas.append(d)
            if d:
                frotas[d] = max(frotas.get(d, 1), int(_num(v.get("bus"), 1)) or 1)
    valor = Counter(valores).most_common(1)[0][0] if valores else 50.0
    pax = [x for x in (_linha(r) for r in linhas) if x]
    return datas, frotas, valor, pax


@router.post("/importar/previa")
async def importar_previa(request: Request):
    _, _, p = _contexto(request)
    _exigir(p, "importar", "importar planilhas")
    linhas = (await request.json()).get("linhas") or []
    if not linhas or not {"nome", "dias_onibus"} <= set(linhas[0].keys()):
        raise HTTPException(400, "Planilha fora do formato esperado. Precisa das colunas: nome, dias_onibus.")
    datas, frotas, valor, pax = _analisar(linhas)
    return {"datas": datas, "frotas": frotas, "valor": valor, "passageiros": pax, "total_linhas": len(linhas)}


@router.post("/importar")
async def importar(request: Request):
    _, _, p = _contexto(request)
    _exigir(p, "importar", "importar planilhas")
    c = await request.json()
    nome = str(c.get("nome") or "").strip()
    datas = [d for d in DIAS_VALIDOS if d in (c.get("datas") or [])]
    if not nome or not datas:
        raise HTTPException(400, "Informe o nome do evento e pelo menos um dia de operação.")
    _, frotas_det, _, pax = _analisar(c.get("linhas") or [])
    if not pax:
        raise HTTPException(400, "Nenhum passageiro com nome válido na planilha.")
    id_evento = f"{nome.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    db = _db()
    db.collection("eventos").document(id_evento).set({
        "nome": nome, "datas": datas, "valor": _num(c.get("valor"), 50.0),
        "custo_onibus": _num(c.get("custo_onibus"), CUSTO_ONIBUS_PADRAO),
        "status": "ativo", "criado_em": datetime.now(),
        "frotas": {d: frotas_det.get(d, 1) for d in datas}, "origem": "importado_planilha",
    }, timeout=banco.TIMEOUT)
    lote, n = db.batch(), 0
    for x in pax:
        lote.set(_col_pax(id_evento).document(pax_id(x["nome"], x["rg"])), x)
        lote.set(db.collection("cadastro_geral").document(x["nome"].lower().replace(" ", "")),
                 {"nome": x["nome"], "rg": x["rg"], "cpf": x["cpf"], "grupo": x["grupo"],
                  "ultima_atualizacao": datetime.now()}, merge=True)
        n += 1
        if n % 200 == 0:
            lote.commit(timeout=banco.TIMEOUT)
            lote = db.batch()
    lote.commit(timeout=banco.TIMEOUT)
    _cad_cache["itens"] = None
    return {"ok": True, "id": id_evento, "importados": n}
