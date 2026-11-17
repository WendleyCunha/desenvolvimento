"""
hub/cargas_plano.py — ERP · PLANEJAMENTO DE CARGAS (puxar pedidos e sugerir cargas sozinho).
─────────────────────────────────────────────────────────────────────────────
A aba Cargas do ERP lista os pedidos prontos para sair (por padrão: agendados para
amanhã), deixa filtrar qualquer data e "puxar" pedidos de outros dias ou ainda sem
agenda. Daqui sai a SUGESTÃO DE CARGAS:

  1. cada pedido vira um PONTO com volumes, m³ (cubagem) e kg (peso) — somados dos
     produtos (o que vai + o que a troca recolhe) — e a localização do endereço;
  2. a semente de cada carga é o pedido mais PRIORITÁRIO (entrega agendada mais cedo,
     depois o pedido mais antigo); a carga cresce sempre pelo ponto MAIS PRÓXIMO que
     ainda cabe nos limites: pontos · m³ · kg · volumes do veículo · raio em km
     (qualquer mistura; limite 0 = não usa aquele critério);
  3. a ordem de entrega sai do CD pelo vizinho mais próximo + 2-opt (desfaz cruzamentos);
     com "respeitar janela", primeiro as entregas da manhã, depois as sem janela, por
     fim as da tarde;
  4. o que não coube, o que não tem localização e o que não pode ir em carga voltam
     listados com o motivo. Nada é gravado até confirmar.

Localização grátis: OpenStreetMap (Nominatim) e BrasilAPI pelo CEP — a mesma do WROUTER —,
uma vez por endereço, em segundo plano, guardada no pedido (ped["geo"]).
"""
from __future__ import annotations

import math
import os
import re
import threading

from fastapi import APIRouter, HTTPException, Request

import erp as E

router = APIRouter(prefix="/api/erp/plano")

PADRAO = {"cd": {}, "max_pontos": 0, "max_m3": 0.0, "max_kg": 0.0, "raio_km": 0.0,
          "respeitar_janela": True, "exigir_faturamento": False}
PRONTOS = ("agendado", "confirmado", "reagendar")


def cfg() -> dict:
    return {**PADRAO, **(E.ST.config.get("plano") or {})}


# ══════════════════════════════════════════════════════════════════════════════
# LOCALIZAÇÃO DOS PEDIDOS
# ══════════════════════════════════════════════════════════════════════════════
def chave_endereco(end: dict) -> str:
    end = end or {}
    return "|".join(re.sub(r"\s+", " ", str(end.get(k) or "").strip().lower()) for k in ("logradouro", "numero", "bairro", "cidade", "uf", "cep"))


def geo_do_pedido(ped: dict) -> dict | None:
    """Coordenadas do pedido, só se foram tiradas do endereço ATUAL (mudou o endereço → localiza de novo)."""
    g = ped.get("geo") or {}
    if g.get("lat") is None or g.get("chave") != chave_endereco(ped.get("endereco")):
        return None
    return {"lat": g["lat"], "lng": g["lng"], "fonte": g.get("fonte") or ""}


def _geo_falhou(ped: dict) -> bool:
    g = ped.get("geo") or {}
    return bool(g.get("falhou")) and g.get("chave") == chave_endereco(ped.get("endereco"))


FILA: list = []
ESTADO = {"rodando": False}


def _trabalhar():
    import wrouter
    while True:
        with E.ST.trava:
            if not FILA:
                ESTADO["rodando"] = False
                return
            pid = FILA.pop(0)
            ped = E.ST.dados["pedidos"].get(pid) or {}
            if geo_do_pedido(ped) or _geo_falhou(ped):
                continue
            end = dict(ped.get("endereco") or {})
        achou = wrouter.geocodificar(end)
        with E.ST.trava:
            tx = E.Tx({"login": "planejamento"})
            ped = tx.get("pedidos", pid)
            if not ped or chave_endereco(ped.get("endereco")) != chave_endereco(end):
                continue
            base = {"chave": chave_endereco(end), "em": E.agora()}
            ped["geo"] = {**achou, **base} if achou else {"falhou": True, **base}
            tx.put("pedidos", pid, ped)
            try:
                tx.commit()
            except Exception as ex:  # noqa: BLE001
                print(f"[plano] localização não gravou: {ex}")


def localizar(pids) -> int:
    """Põe na fila (segundo plano) os pedidos ainda sem localização. Devolve quantos estão na fila."""
    for pid in pids:
        ped = E.ST.dados["pedidos"].get(pid) or {}
        if ped and not geo_do_pedido(ped) and not _geo_falhou(ped) and pid not in FILA:
            FILA.append(pid)
    if FILA and not ESTADO["rodando"] and os.environ.get("WROUTER_GEO", "1") != "0":
        ESTADO["rodando"] = True
        threading.Thread(target=_trabalhar, daemon=True).start()
    return len(FILA)


# ══════════════════════════════════════════════════════════════════════════════
# MEDIDAS DO PEDIDO
# ══════════════════════════════════════════════════════════════════════════════
def medidas(ped: dict) -> dict:
    """Volumes, m³ e kg do que a entrega ocupa no caminhão (o que vai + o que a troca recolhe)."""
    vol, m3, kg, falta = 0, 0.0, 0.0, set()
    for lista, conta_vol in ((ped.get("pendentes") or [], True), (ped.get("recolher") or [], False)):
        for it in lista:
            pr = E.ST.dados["produtos"].get(it.get("produto_id")) or {}
            q = E._int(it.get("qtd"))
            if conta_vol:
                vol += q * max(1, E._int(pr.get("volumes"), 1))
            c, p = E._num(pr.get("cubagem")), E._num(pr.get("peso"))
            if not c:
                falta.add("cubagem")
            if not p:
                falta.add("peso")
            m3 += q * c
            kg += q * p
    return {"vol": vol, "m3": round(m3, 3), "kg": round(kg, 1), "sem_medida": sorted(falta)}


def _rank_janela(j: str) -> int:
    j = str(j or "").lower()
    return 0 if "manh" in j else 2 if "tarde" in j else 1


def _dist_km(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    f1, f2 = math.radians(a["lat"]), math.radians(b["lat"])
    df, dl = math.radians(b["lat"] - a["lat"]), math.radians(b["lng"] - a["lng"])
    h = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def elegivel(ped: dict) -> str:
    """'' se o pedido pode entrar numa carga; senão o motivo."""
    if not ped:
        return "pedido não encontrado"
    if ped.get("carga_id"):
        return "já está em outra carga"
    if ped.get("status") not in PRONTOS:
        return f"está {ped.get('status')}"
    if ped.get("status") != "agendado" and ped.get("pendentes") and not ped.get("reservado"):
        return "sem estoque reservado"
    return ""


def ponto(pid: str, ped: dict) -> dict:
    ag = ped.get("agendamento") or {}
    return {"id": pid, "numero": ped.get("numero"), "cliente": ped.get("cliente_nome") or "", "geo": geo_do_pedido(ped),
            "janela": ag.get("janela") or "", "data_ag": ag.get("data") or "", "criado_em": ped.get("criado_em") or "",
            "bairro": " · ".join(x for x in ((ped.get("endereco") or {}).get("bairro"), (ped.get("endereco") or {}).get("cidade")) if x),
            **medidas(ped)}


def _prio(p: dict):
    # entrega agendada mais cedo primeiro (sem agenda vai depois), depois o pedido mais antigo
    return (p["data_ag"] or "9999-99-99", p["criado_em"], p["numero"] or 0)


# ══════════════════════════════════════════════════════════════════════════════
# O PLANEJADOR (puro: recebe pontos e veículos, devolve a sugestão)
# ══════════════════════════════════════════════════════════════════════════════
def limites_do_veiculo(v: dict, padrao: dict) -> dict:
    v = v or {}
    return {"pontos": E._int(v.get("max_pontos")) or E._int(padrao.get("max_pontos")),
            "m3": E._num(v.get("max_m3")) or E._num(padrao.get("max_m3")),
            "kg": E._num(v.get("max_kg")) or E._num(padrao.get("max_kg")),
            "vol": E._int(v.get("capacidade")),
            "raio": E._num(padrao.get("raio_km"))}


def _cabe(p: dict, tot: dict, L: dict) -> bool:
    return not ((L["pontos"] and tot["pontos"] + 1 > L["pontos"]) or (L["m3"] and tot["m3"] + p["m3"] > L["m3"] + 1e-9)
                or (L["kg"] and tot["kg"] + p["kg"] > L["kg"] + 1e-9) or (L["vol"] and tot["vol"] + p["vol"] > L["vol"]))


def _somar(tot: dict, p: dict):
    tot["pontos"] += 1
    tot["vol"] += p["vol"]
    tot["m3"] = round(tot["m3"] + p["m3"], 3)
    tot["kg"] = round(tot["kg"] + p["kg"], 1)


def _custo(seq: list, ini: dict | None) -> float:
    d = _dist_km(ini, seq[0]["geo"]) if ini and seq else 0.0
    return d + sum(_dist_km(seq[i]["geo"], seq[i + 1]["geo"]) for i in range(len(seq) - 1))


def _vizinho(pts: list, ini: dict | None) -> list:
    resto = list(pts)
    if not resto:
        return []
    if ini is None:        # sem CD: começa pela ponta (o ponto mais longe do centro do grupo)
        c = {"lat": sum(p["geo"]["lat"] for p in resto) / len(resto), "lng": sum(p["geo"]["lng"] for p in resto) / len(resto)}
        primeiro = max(resto, key=lambda p: _dist_km(c, p["geo"]))
    else:
        primeiro = min(resto, key=lambda p: _dist_km(ini, p["geo"]))
    seq = [primeiro]
    resto.remove(primeiro)
    while resto:
        nx = min(resto, key=lambda p: _dist_km(seq[-1]["geo"], p["geo"]))
        seq.append(nx)
        resto.remove(nx)
    return seq


def _dois_opt(seq: list, ini: dict | None) -> list:
    melhor, custo = list(seq), _custo(seq, ini)
    melhorou = True
    while melhorou and len(melhor) > 2:
        melhorou = False
        for i in range(0, len(melhor) - 1):
            for k in range(i + 1, len(melhor)):
                novo = melhor[:i] + melhor[i:k + 1][::-1] + melhor[k + 1:]
                c = _custo(novo, ini)
                if c < custo - 1e-9:
                    melhor, custo, melhorou = novo, c, True
    return melhor


def ordenar(pts: list, cd: dict | None, respeitar_janela: bool) -> list:
    blocos = [[p for p in pts if _rank_janela(p["janela"]) == r] for r in (0, 1, 2)] if respeitar_janela else [pts]
    rota, cur = [], cd
    for b in blocos:
        if not b:
            continue
        seq = _dois_opt(_vizinho(b, cur), cur)
        rota += seq
        cur = seq[-1]["geo"]
    return rota


def planejar(pontos: list, veiculos: list, padrao: dict, cd: dict | None = None, respeitar_janela: bool = True, max_cargas: int = 40) -> dict:
    """veiculos: [{"veiculo_id", "motorista_id", "parceiro": {cadastro do veículo}}]. Lista vazia =
    monta quantas cargas precisar com os limites padrão (veículo a definir)."""
    com = sorted([p for p in pontos if p["geo"]], key=_prio)
    sem_local = [p for p in pontos if not p["geo"]]
    livres = list(veiculos) if veiculos else [{"veiculo_id": "", "motorista_id": "", "parceiro": {}} for _ in range(max_cargas)]
    cargas, sobra = [], []
    for v in livres:
        if not com:
            break
        L = limites_do_veiculo(v.get("parceiro"), padrao)
        zero = {"pontos": 0, "vol": 0, "m3": 0.0, "kg": 0.0}
        semente = next((p for p in com if _cabe(p, zero, L)), None)
        if not semente:
            continue
        grupo, tot = [semente], dict(zero)
        _somar(tot, semente)
        com.remove(semente)
        while True:
            cands = [p for p in com if _cabe(p, tot, L) and (not L["raio"] or _dist_km(semente["geo"], p["geo"]) <= L["raio"])]
            if not cands:
                break
            nx = min(cands, key=lambda p: (min(_dist_km(g["geo"], p["geo"]) for g in grupo), _prio(p)))
            grupo.append(nx)
            _somar(tot, nx)
            com.remove(nx)
        seq = ordenar(grupo, cd, respeitar_janela)
        oc = {k: (round(tot[k] / L[k] * 100) if L[k] else None) for k in ("pontos", "m3", "kg", "vol")}
        cargas.append({"veiculo_id": v.get("veiculo_id") or "", "motorista_id": v.get("motorista_id") or "",
                       "pedidos": [p["id"] for p in seq], "totais": tot, "limites": L, "ocupacao": oc,
                       "km": round(_custo(seq, cd), 1), "sem_medida": sorted({m for p in seq for m in p["sem_medida"]})})
    for p in com:
        sozinho = any(_cabe(p, {"pontos": 0, "vol": 0, "m3": 0.0, "kg": 0.0}, limites_do_veiculo(v.get("parceiro"), padrao)) for v in livres)
        sobra.append({"id": p["id"], "motivo": "não coube nos veículos escolhidos" if sozinho else "maior que o limite de qualquer veículo"})
    return {"cargas": cargas, "sobra": sobra, "sem_local": [p["id"] for p in sem_local]}


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════════════════════════
def _cd() -> dict | None:
    c = cfg().get("cd") or {}
    return {"lat": c["lat"], "lng": c["lng"]} if c.get("lat") is not None and c.get("lng") is not None else None


@router.post("/localizar")
async def rota_localizar(request: Request):
    """Põe na fila de localização os pedidos informados (ou de todos os prontos para carga) e devolve o que já se sabe."""
    E._ctx(request, "cargas", "montar cargas")
    c = await request.json()
    with E.ST.trava:
        ids = [str(x) for x in (c.get("pedidos") or [])] or [i for i, p in E.ST.dados["pedidos"].items() if not elegivel(p)]
        na_fila = localizar(ids)
        geo = {}
        for i in ids:
            ped = E.ST.dados["pedidos"].get(i) or {}
            geo[i] = geo_do_pedido(ped) or ({"falhou": True} if _geo_falhou(ped) else None)
    return {"ok": True, "geo": geo, "na_fila": na_fila}


@router.post("/sugerir")
async def sugerir(request: Request):
    u, p = E._ctx(request, "planejar", "sugerir cargas")
    c = await request.json()
    cf = cfg()
    lim = {**{k: cf[k] for k in ("max_pontos", "max_m3", "max_kg", "raio_km")}, **{k: v for k, v in (c.get("limites") or {}).items() if k in ("max_pontos", "max_m3", "max_kg", "raio_km")}}
    janela = bool(c.get("respeitar_janela", cf["respeitar_janela"]))
    with E.ST.trava:
        pontos, fora = [], []
        for pid in dict.fromkeys(str(x) for x in (c.get("pedidos") or [])):
            ped = E.ST.dados["pedidos"].get(pid)
            m = elegivel(ped)
            if m:
                fora.append({"id": pid, "motivo": m})
            else:
                pontos.append(ponto(pid, ped))
        if not pontos:
            raise HTTPException(400, "Nenhum pedido pronto para carga na seleção.")
        veics = []
        for v in c.get("veiculos") or []:
            vid = str(v.get("veiculo_id") or "")
            par = E.ST.dados["parceiros"].get(vid) or {}
            if vid and par.get("tipo") != "veiculo":
                raise HTTPException(400, "Veículo inválido.")
            veics.append({"veiculo_id": vid, "motorista_id": str(v.get("motorista_id") or ""), "parceiro": par})
        r = planejar(pontos, veics, lim, _cd(), janela)
        localizar(r["sem_local"])
    info = {pt["id"]: {k: pt[k] for k in ("numero", "cliente", "bairro", "janela", "data_ag", "vol", "m3", "kg", "sem_medida", "geo")} for pt in pontos}
    return {"ok": True, **r, "sobra": r["sobra"] + fora, "pontos": info, "cd": _cd(), "limites": lim, "respeitar_janela": janela,
            "data": str(c.get("data") or "")}


@router.post("/confirmar")
async def confirmar(request: Request):
    """Cria de uma vez as cargas sugeridas (tudo ou nada). Pedidos de outros dias são puxados para a data."""
    u, p = E._ctx(request, "cargas", "montar cargas")
    c = await request.json()
    data = str(c.get("data") or "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", data):
        raise HTTPException(400, "Data da carga inválida.")
    cargas = [x for x in (c.get("cargas") or []) if x.get("pedidos")]
    if not cargas:
        raise HTTPException(400, "Nenhuma carga com pedidos para criar.")
    with E.ST.trava:
        tx = E.Tx(u)
        ids = []
        for x in cargas:
            car = E._nova_carga(tx, u, {"data": data, "veiculo_id": x.get("veiculo_id"), "motorista_id": x.get("motorista_id"),
                                        "ajudante": x.get("ajudante"), "obs": x.get("obs") or "Sugerida pelo planejamento", "pedidos": x["pedidos"]})
            ids.append(car["id"])
        tx.commit()
        return {"ok": True, "cargas": ids, **E._parcial(p, tx)}


@router.put("/config")
async def salvar_config(request: Request):
    u, p = E._ctx(request, "configurar", "configurar o ERP")
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(u)
        cf = tx.config()
        pl = {**PADRAO, **(cf.get("plano") or {})}
        for k in ("max_pontos",):
            if k in c:
                pl[k] = max(E._int(c[k]), 0)
        for k in ("max_m3", "max_kg", "raio_km"):
            if k in c:
                pl[k] = round(max(E._num(c[k]), 0), 3)
        for k in ("respeitar_janela", "exigir_faturamento"):
            if k in c:
                pl[k] = bool(c[k])
        if isinstance(c.get("cd"), dict):
            d = c["cd"]
            cd = {"endereco": str(d.get("endereco") or "").strip()[:200]}
            lat, lng = d.get("lat"), d.get("lng")
            if lat not in (None, "") and lng not in (None, ""):
                lat, lng = E._num(lat, None), E._num(lng, None)
                if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
                    raise HTTPException(400, "Coordenadas do CD inválidas.")
                cd.update(lat=round(lat, 6), lng=round(lng, 6))
            pl["cd"] = cd
        cf["plano"] = pl
        tx.commit()
        return {"ok": True, "plano": E.ST.config["plano"]}


@router.post("/cd/localizar")
async def localizar_cd(request: Request):
    """Acha as coordenadas do endereço do CD (não grava: o Ajustes mostra e a pessoa salva)."""
    E._ctx(request, "configurar", "configurar o ERP")
    c = await request.json()
    txt = str(c.get("endereco") or "").strip()
    if len(txt) < 6:
        raise HTTPException(400, "Digite o endereço do CD (rua, número, cidade).")
    import urllib.parse
    import wrouter
    try:
        r = wrouter._http_json("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": txt, "format": "json", "limit": 1, "countrycodes": "br"}))
        if r:
            return {"ok": True, "lat": round(float(r[0]["lat"]), 6), "lng": round(float(r[0]["lon"]), 6), "achado": r[0].get("display_name", "")}
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r"\b\d{5}-?\d{3}\b", txt)
    if m:
        g = wrouter.geocodificar({"cep": m.group(0)})
        if g:
            return {"ok": True, "lat": g["lat"], "lng": g["lng"], "achado": "pelo CEP"}
    raise HTTPException(404, "Não achei esse endereço. Confira ou informe a latitude/longitude (no Google Maps: clique com o botão direito no local).")
