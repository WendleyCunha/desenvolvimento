"""
hub/wrouter.py — WROUTER · acompanhamento da entrega (app do motorista, Ao vivo, chat, link do cliente).
─────────────────────────────────────────────────────────────────────────────
100% dentro do wendleyservice (sem PQI). A lógica é a do RouterKing do PQI, adaptada à carga do ERP:

  WLOGISTICA libera a carga  →  ela aparece no APP DO MOTORISTA (/motorista/, login pela PLACA do veículo)
  "Iniciar rota"  →  ERP: saída da carga (reservado → trânsito) e os dados das entregas descem para o celular
  Em cada cliente: ENTREGUE (com a palavra-chave do pedido) · PARCIAL · RETORNO (motivo + foto)
      → BAIXA AUTOMÁTICA NO ERP (entregue / ausente / avaria / recusado) e o armazém espera o que volta
  Sem sinal: o registro fica no celular e sobe sozinho; palavra errada sem sinal → a frota valida.
  Palavra errada N vezes trava → "Cliente não tem a palavra" → a frota libera ou nega.
  Chat motorista ↔ frota por cliente (motivo, prazo do atendimento, foto), presença de quem está tratando.
  "Cheguei no CD" fecha a rota.

  CLIENTE: link próprio por cliente + CEP (/entrega/<código>) com a palavra-chave, a situação e a distância
  em km (linha reta) depois do "Iniciar rota" (laranja < 7 km, vermelho < 2 km). Entregar ao vizinho
  (número, nome e telefone — o NOME vira a palavra; sem nome = sem palavra).

  POSIÇÃO: GPS do app → localização da REDE (GPS do celular desligado) → ESTIMADA pelo último cliente
  atendido (o app avisa que está com internet). Ao vivo só na memória; trilha gravada a cada 3 min (cota grátis).

Gravado no documento da carga do ERP, em car["rota"] (mesma transação do ERP). Senhas das placas e a
configuração do app ficam em wrouter/app (Firestore). Fotos em wrouter_fotos.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import secrets
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

import acesso
import anexos as A
import banco
import erp as E

router = APIRouter()
MOD = "wrouter"
PASTA = Path(__file__).resolve().parent / "static" / "motorista"
COOKIE = "hub_motorista"


def _ck() -> str:
    """Nome do cookie de sessão — um por empresa (o mesmo celular pode usar o app de duas empresas sem misturar)."""
    return COOKIE if banco.empresa_atual() == banco.PRINCIPAL else f"{COOKIE}_{banco.empresa_atual()}"
SENHA_INICIAL = os.environ.get("WROUTER_SENHA_INICIAL") or "Rota@2026"
DURACAO_DIAS = 14
COL_APP, DOC_APP, COL_FOTOS = "wrouter", "app", "wrouter_fotos"
FOTO_MAX = 450_000
DESFAZER_MIN = 15
TRILHA_SEG = 180
KM_LARANJA, KM_VERMELHO = 7.0, 2.0   # padrão; o valor do dia fica em WROUTER › Motoristas e app (cfg)
LINK_DIAS = 7
FROTA_MOTIVO = "Contato da frota"
CHAT_MAX = 300
GEO_UA = "wendleyservice-WROUTER/1.0 (entregas)"
MOTIVOS_PADRAO = [{"motivo": "Cliente ausente", "tipo": "ausente"}, {"motivo": "Endereço não localizado", "tipo": "ausente"},
                  {"motivo": "Sem acesso / escadas", "tipo": "ausente"}, {"motivo": "Reagendado pelo cliente", "tipo": "ausente"},
                  {"motivo": "Avaria", "tipo": "avaria"}, {"motivo": "Recusado pelo cliente", "tipo": "recusa"}]
TIPO_ERP = {"ausente": "ausente", "avaria": "avaria", "recusa": "recusado"}


def agora() -> str:
    return E.agora()


def norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return re.sub(r"[^A-Z0-9]", "", "".join(c for c in s if unicodedata.category(c) != "Mn").upper())


def norm_placa(p) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(p or "").upper())[:8]


def _dig(x) -> str:
    return re.sub(r"\D", "", str(x or ""))


def _min_desde(iso) -> float:
    try:
        return (datetime.fromisoformat(str(iso)) - datetime.fromisoformat(agora())).total_seconds() / -60
    except (TypeError, ValueError):
        return 1e9


def _ts(iso) -> float:
    try:
        return datetime.fromisoformat(str(iso)).replace(tzinfo=E.FUSO).timestamp()
    except (TypeError, ValueError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO DO APP (wrouter/app): senhas das placas + regras
# ══════════════════════════════════════════════════════════════════════════════
class _App:
    def __init__(self):
        self.d: dict | None = None
        self.trava = threading.RLock()

    def dados(self) -> dict:
        with self.trava:
            if self.d is None:
                snap = banco.db().collection(COL_APP).document(DOC_APP).get(timeout=banco.TIMEOUT)
                d = (snap.to_dict() if snap.exists else None) or {}
                self.d = {"placas": d.get("placas") or {}, "cfg": d.get("cfg") or {}}
            return self.d

    def salvar(self):
        with self.trava:
            banco.db().collection(COL_APP).document(DOC_APP).set(self.dados(), timeout=banco.TIMEOUT)


APP = banco.por_empresa(_App)   # um estado por empresa


def cfg() -> dict:
    c = APP.dados()["cfg"]
    return {"tentativas": int(c.get("tentativas") or 5), "chat_minutos": int(c.get("chat_minutos") or 15),
            "raio_chegada_m": max(50, min(int(c.get("raio_chegada_m") or 250), 2000)),
            "motivos": [m for m in (c.get("motivos") or MOTIVOS_PADRAO) if m.get("motivo")],
            "palavra": dict(c.get("palavra") or {}),
            # faixas de distância (km): laranja = "se aproximando" (e, a partir dela, o cliente vê o mapa); vermelho = "bem perto"
            "km_laranja": _km(c.get("km_laranja"), KM_LARANJA), "km_vermelho": min(_km(c.get("km_vermelho"), KM_VERMELHO), _km(c.get("km_laranja"), KM_LARANJA)),
            "mapa_cliente": c.get("mapa_cliente") is not False}


def _km(v, padrao: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return padrao
    return round(min(max(v, 0.1), 100.0), 1) if v > 0 else padrao


def motivos() -> list:
    return [m["motivo"] for m in cfg()["motivos"]]


def tipo_motivo(motivo: str) -> str:
    return next((m.get("tipo") for m in cfg()["motivos"] if m["motivo"] == motivo), "ausente")


def palavra_ligada(motorista_id: str) -> bool:
    return bool(cfg()["palavra"].get(motorista_id or ""))


# ══════════════════════════════════════════════════════════════════════════════
# CARGA → ROTA
# ══════════════════════════════════════════════════════════════════════════════
def rota(car: dict) -> dict:
    r = car.get("rota")
    if not isinstance(r, dict):
        r = car["rota"] = {}
    for k, v in (("pedidos", {}), ("trilha", []), ("links", {}), ("geo", {}), ("chats", {})):
        r.setdefault(k, v)
    return r


def placa_da_carga(car: dict) -> str:
    v = E.ST.dados["parceiros"].get(car.get("veiculo_id") or "") or {}
    return norm_placa(v.get("placa") or "")


def motorista_da_carga(car: dict) -> dict:
    m = E.ST.dados["parceiros"].get(car.get("motorista_id") or "") or {}
    return {"id": car.get("motorista_id") or "", "nome": m.get("nome") or "Motorista"}


def placas_cadastradas() -> dict:
    return {norm_placa(v.get("placa")): {"id": k, "nome": v.get("nome"), "placa": norm_placa(v.get("placa"))}
            for k, v in E.ST.dados["parceiros"].items() if v.get("tipo") == "veiculo" and v.get("ativo", True) and norm_placa(v.get("placa"))}


def na_rua(car: dict) -> bool:
    return car.get("status") == "em_rota" and not rota(car).get("chegada")


def liberada_para_app(car: dict) -> bool:
    if car.get("status") != "montando" or not car.get("pedidos"):
        return False
    if E.exigir_faturamento() and not E.faturada(car):
        return False
    if not E.exigir_wlog():
        return True
    import wlogistica
    return wlogistica.liberada(car)


def cargas_da_placa(pl: str) -> list:
    hoje = E.hoje()
    out = []
    for cid, car in E.ST.dados["cargas"].items():
        if placa_da_carga(car) != pl:
            continue
        r = car.get("rota") or {}
        chegou_hoje = str((r.get("chegada") or {}).get("em") or "")[:10] == hoje
        if liberada_para_app(car) or na_rua(car) or chegou_hoje:
            out.append((cid, car))
    return sorted(out, key=lambda x: (x[1].get("data") or "", x[1].get("numero") or 0))


def ev_de(car: dict, pid: str) -> dict:
    return rota(car)["pedidos"].setdefault(pid, {})


def palavra_efetiva(car: dict, pid: str, ped: dict | None = None) -> str:
    vz = (rota(car)["pedidos"].get(pid) or {}).get("vizinho")
    if vz:
        return str(vz.get("nome") or "")
    ped = ped or E.ST.dados["pedidos"].get(pid) or {}
    return str(ped.get("palavra_chave") or "")


def palavra_confere(digitada, certa: str, vizinho: bool) -> bool:
    d = norm(digitada)
    if not d or not certa:
        return False
    return d == norm(certa) or (vizinho and d == norm(str(certa).split()[0]))


def _desfecho_de(car: dict, pid: str) -> str:
    """entregue · retorno · parcial — o que o motorista registrou (ou a baixa manual do ERP)."""
    ev = rota(car)["pedidos"].get(pid) or {}
    if ev.get("desfecho"):
        return ev["desfecho"]
    b = (car.get("baixas") or {}).get(pid)
    return {"entregue": "entregue", "avaria": "parcial", "ausente": "retorno", "recusado": "retorno"}.get(b, "")


# ── geocodificação (grátis: OpenStreetMap + BrasilAPI pelo CEP), uma vez por pedido, em segundo plano ──
GEO_FILA = banco.por_empresa(list)
GEO_ESTADO = banco.por_empresa(lambda: {"rodando": False})


def _http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": GEO_UA, "Accept": "application/json", "Accept-Language": "pt-BR"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.load(r)


def geocodificar(end: dict) -> dict | None:
    rua_txt = " ".join(x for x in (end.get("logradouro"), end.get("numero")) if x).strip()
    cidade, cep = str(end.get("cidade") or "").strip(), _dig(end.get("cep"))
    tent = []
    if rua_txt and cidade:
        tent.append({"street": rua_txt, "city": cidade, "country": "Brasil", **({"postalcode": cep} if len(cep) == 8 else {})})
        tent.append({"q": ", ".join(x for x in (rua_txt, end.get("bairro"), cidade, end.get("uf"), "Brasil") if x)})
    for t in tent:
        try:
            r = _http_json("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({**t, "format": "json", "limit": 1, "countrycodes": "br"}))
            time.sleep(1.1)
            if r:
                return {"lat": round(float(r[0]["lat"]), 6), "lng": round(float(r[0]["lon"]), 6), "fonte": "endereço"}
        except Exception:  # noqa: BLE001
            time.sleep(1.1)
    if len(cep) == 8:
        try:
            co = ((_http_json(f"https://brasilapi.com.br/api/cep/v2/{cep}") or {}).get("location") or {}).get("coordinates") or {}
            if co.get("latitude") and co.get("longitude"):
                return {"lat": round(float(co["latitude"]), 6), "lng": round(float(co["longitude"]), 6), "fonte": "CEP"}
        except Exception:  # noqa: BLE001
            pass
    return None


def _geo_trabalhar():
    while True:
        with E.ST.trava:
            if not GEO_FILA:
                GEO_ESTADO["rodando"] = False
                return
            cid, pid = GEO_FILA.pop(0)
            car = E.ST.dados["cargas"].get(cid) or {}
            if pid in ((car.get("rota") or {}).get("geo") or {}):
                continue
            end = dict((E.ST.dados["pedidos"].get(pid) or {}).get("endereco") or {})
        achou = geocodificar(end)
        with E.ST.trava:
            tx = E.Tx({"login": "wrouter"})
            car = tx.get("cargas", cid)
            if not car:
                continue
            rota(car)["geo"][pid] = {**achou, "em": agora()} if achou else {"falhou": True, "em": agora()}
            tx.put("cargas", cid, car)
            try:
                tx.commit()
            except Exception as ex:  # noqa: BLE001
                print(f"[wrouter] geo não gravou: {ex}")


def pedir_geo(cid: str, car: dict):
    geo = (car.get("rota") or {}).get("geo") or {}
    import cargas_plano
    for pid in car.get("pedidos") or []:
        if cargas_plano.geo_do_pedido(E.ST.dados["pedidos"].get(pid) or {}):
            continue     # já localizado no planejamento de cargas
        if pid not in geo and (cid, pid) not in GEO_FILA:
            GEO_FILA.append((cid, pid))
    if GEO_FILA and not GEO_ESTADO["rodando"] and os.environ.get("WROUTER_GEO", "1") != "0":
        GEO_ESTADO["rodando"] = True
        banco.thread(_geo_trabalhar)


def destino(car: dict, pid: str) -> dict | None:
    g = ((car.get("rota") or {}).get("geo") or {}).get(pid) or {}
    if g.get("lat") is None:     # o planejamento de cargas já pode ter localizado o pedido
        import cargas_plano
        g = cargas_plano.geo_do_pedido(E.ST.dados["pedidos"].get(pid) or {}) or {}
    return {"lat": g["lat"], "lng": g["lng"], "fonte": g.get("fonte")} if g.get("lat") is not None else None


def distancia_m(a_lat, a_lng, b_lat, b_lng) -> int:
    f1, f2 = math.radians(a_lat), math.radians(b_lat)
    df, dl = math.radians(b_lat - a_lat), math.radians(b_lng - a_lng)
    h = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return int(round(2 * 6371000.0 * math.asin(math.sqrt(h))))


# ── posição: GPS → rede → estimada pelo último cliente atendido ──
GPS = banco.por_empresa(dict)     # placa → última posição (memória, por empresa: a mesma placa pode existir em duas)
SINAL = banco.por_empresa(dict)   # placa → {t, gps}


def posicao_atual(car: dict) -> dict | None:
    r = rota(car)
    if r.get("chegada") or not r.get("saida"):
        return None
    cands = []
    g = GPS.get(placa_da_carga(car))
    if g:
        cands.append({**g, "fonte": g.get("fonte") or "gps"})
    elif r.get("gps"):
        x = r["gps"]
        cands.append({**x, "t": _ts(x["em"]), "fonte": x.get("fonte") or "gps"})
    s = r.get("saida") or {}
    if s.get("lat") is not None:
        cands.append({"lat": s["lat"], "lng": s["lng"], "prec": 0, "em": s["em"], "t": _ts(s["em"]), "fonte": "gps"})
    for pid in car.get("pedidos") or []:
        ev = r["pedidos"].get(pid) or {}
        dest = destino(car, pid)
        nome = (E.ST.dados["pedidos"].get(pid) or {}).get("cliente_nome") or "cliente"
        for marco, em, la, ln in (("chegou", (ev.get("chegou") or {}).get("em"), (ev.get("chegou") or {}).get("lat"), (ev.get("chegou") or {}).get("lng")),
                                  ("atendeu", ev.get("em") if ev.get("desfecho") else None, ev.get("lat"), ev.get("lng"))):
            if not em:
                continue
            if la is not None and ln is not None:
                cands.append({"lat": la, "lng": ln, "prec": 0, "em": em, "t": _ts(em), "fonte": "gps"})
            elif dest:
                cands.append({"lat": dest["lat"], "lng": dest["lng"], "prec": 0, "em": em, "t": _ts(em), "fonte": "estimada",
                              "ref": f"{nome} ({marco} às {str(em)[11:16]})"})
    if not cands:
        return None
    best = max(cands, key=lambda x: x["t"])
    out = {k: best.get(k) for k in ("lat", "lng", "prec", "em", "fonte", "ref")}
    out["ha_seg"] = int(max(0, time.time() - best["t"])) if best["t"] else None
    out["aprox"] = best["fonte"] != "gps" or (best.get("prec") or 0) > 1000
    return out


def cor_km(km) -> str:
    c = cfg()
    return "" if km is None else "vermelho" if km < c["km_vermelho"] else "laranja" if km < c["km_laranja"] else "normal"


def rumo(car: dict, pos: dict | None) -> float | None:
    """Direção do caminhão (graus, 0 = norte) pelos dois últimos pontos conhecidos — gira o triângulo no mapa."""
    pts = [(t[0], t[1]) for t in ((car.get("rota") or {}).get("trilha") or [])[-3:]]
    if pos:
        pts.append((pos["lat"], pos["lng"]))
    for i in range(len(pts) - 1, 0, -1):
        (a1, b1), (a2, b2) = pts[i - 1], pts[i]
        if distancia_m(a1, b1, a2, b2) >= 15:
            f1, f2, dl = math.radians(a1), math.radians(a2), math.radians(b2 - b1)
            y = math.sin(dl) * math.cos(f2)
            x = math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl)
            return round((math.degrees(math.atan2(y, x)) + 360) % 360)
    return None


def dist_pedido(car: dict, pid: str, pos: dict | None) -> dict:
    if _desfecho_de(car, pid) or not pos:
        return {"km": None, "km_cor": ""}
    dest = destino(car, pid)
    km = round(distancia_m(pos["lat"], pos["lng"], dest["lat"], dest["lng"]) / 1000, 1) if dest else None
    return {"km": km, "km_cor": cor_km(km), "km_aprox": bool(pos.get("aprox")) if km is not None else False}


def sinal_pub(car: dict) -> dict | None:
    s = SINAL.get(placa_da_carga(car))
    return {"ha_seg": int(time.time() - s["t"]), "gps": s.get("gps") or ""} if s else None


# ── link do cliente: um por cliente + CEP da carga ──
def garantir_links(car: dict) -> bool:
    r = rota(car)
    por = {v.get("grupo"): t for t, v in r["links"].items()}
    mudou = False
    for pid in car.get("pedidos") or []:
        ped = E.ST.dados["pedidos"].get(pid) or {}
        g = f"{ped.get('cliente_id') or norm(ped.get('cliente_nome'))}|{_dig((ped.get('endereco') or {}).get('cep'))}"
        t = por.get(g)
        if not t:
            t = secrets.token_urlsafe(9)
            r["links"][t] = {"grupo": g, "pids": [], "em": agora()}
            por[g] = t
            mudou = True
        if pid not in r["links"][t]["pids"]:
            for v in r["links"].values():
                if pid in v["pids"]:
                    v["pids"].remove(pid)
            r["links"][t]["pids"].append(pid)
            mudou = True
    return mudou


def link_do_pedido(car: dict, pid: str) -> str:
    return next((t for t, v in ((car.get("rota") or {}).get("links") or {}).items() if pid in (v.get("pids") or [])), "")


# ══════════════════════════════════════════════════════════════════════════════
# SESSÃO DO MOTORISTA (cookie próprio — não abre nada do hub)
# ══════════════════════════════════════════════════════════════════════════════
_falhas: dict = {}


def _sessao(request: Request) -> dict:
    d = acesso.ler_token(request.cookies.get(_ck()))
    if not d or not str(d.get("u", "")).startswith("mot:"):
        raise HTTPException(401, "Entre com a placa e a senha.")
    pl = d["u"][4:]
    E.ST.carregar()
    info = APP.dados()["placas"].get(pl) or {}
    if int(info.get("versao") or 0) != int(d.get("v", -1)):
        raise HTTPException(401, "A senha desta placa mudou. Entre de novo.")
    if pl not in placas_cadastradas():
        raise HTTPException(401, "Esta placa não está mais cadastrada.")
    if info.get("trocar", True):
        raise HTTPException(403, "Troque a senha inicial antes de continuar.")
    return {"placa": pl}


def _quem_mot(s: dict, car: dict) -> dict:
    m = motorista_da_carga(car)
    return {"login": f"motorista:{s['placa']}", "nome": m["nome"], "mid": m["id"], "placa": s["placa"]}


def _cookie(resp, pl: str, versao: int, request: Request):
    resp.set_cookie(_ck(), acesso.gerar_token(f"mot:{pl}", versao, DURACAO_DIAS), max_age=DURACAO_DIAS * 86400, httponly=True,
                    samesite="lax", secure=acesso._https(request), path="/")


@router.get("/motorista", include_in_schema=False)
def _mot_barra():
    return RedirectResponse(banco.prefixo_publico() + "/motorista/", status_code=307)


@router.get("/motorista/", include_in_schema=False)
def pagina_motorista():
    return FileResponse(PASTA / "index.html", media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})


@router.get("/motorista/manifest.webmanifest", include_in_schema=False)
def manifesto_motorista():
    return acesso.manifesto_publico(PASTA / "manifest.webmanifest", "/motorista/")


@router.get("/motorista/sw.js", include_in_schema=False)
def sw_motorista():
    return FileResponse(PASTA / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": banco.prefixo_publico() + "/motorista/"})


@router.post("/api/wrouter/app/login")
async def app_login(request: Request):
    c = await request.json()
    pl, senha = norm_placa(c.get("placa")), str(c.get("senha") or "")
    E.ST.carregar()
    f = _falhas.get(pl) or {"n": 0, "ate": 0}
    if f["ate"] > time.time():
        raise HTTPException(429, "Muitas tentativas erradas. Espere 5 minutos ou peça à frota para resetar a senha.")
    if pl not in placas_cadastradas():
        raise HTTPException(401, "Placa ou senha não conferem.")
    with APP.trava:
        info = APP.dados()["placas"].get(pl)
        ok = acesso.conferir_senha(senha, info["hash"]) if info and info.get("hash") else senha == SENHA_INICIAL
        if not ok:
            f["n"] += 1
            if f["n"] >= 5:
                f.update(n=0, ate=time.time() + 300)
            _falhas[pl] = f
            raise HTTPException(401, "Placa ou senha não conferem.")
        _falhas.pop(pl, None)
        if not info:
            info = APP.dados()["placas"][pl] = {"hash": "", "versao": 1, "trocar": True, "em": agora()}
            APP.salvar()
    resp = JSONResponse({"placa": pl, "trocar_senha": bool(info.get("trocar", True))})
    _cookie(resp, pl, int(info.get("versao") or 1), request)
    return resp


@router.post("/api/wrouter/app/senha")
async def app_senha(request: Request):
    d = acesso.ler_token(request.cookies.get(_ck()))
    if not d or not str(d.get("u", "")).startswith("mot:"):
        raise HTTPException(401, "Entre com a placa e a senha.")
    pl = d["u"][4:]
    c = await request.json()
    nova, rep = str(c.get("nova") or ""), str(c.get("repetir") or "")
    if nova != rep:
        raise HTTPException(400, "As duas senhas não são iguais.")
    if len(nova) < 6 or nova != nova.strip():
        raise HTTPException(400, "A senha precisa ter pelo menos 6 caracteres, sem espaço no começo ou no fim.")
    if nova == SENHA_INICIAL:
        raise HTTPException(400, "Use uma senha diferente da inicial.")
    with APP.trava:
        info = APP.dados()["placas"].setdefault(pl, {"versao": 1})
        if int(info.get("versao") or 0) != int(d.get("v", -1)):
            raise HTTPException(401, "A senha desta placa mudou. Entre de novo.")
        info.update(hash=acesso.hash_senha(nova), versao=int(info.get("versao") or 1) + 1, trocar=False, em=agora())
        APP.salvar()
    resp = JSONResponse({"ok": True})
    _cookie(resp, pl, info["versao"], request)
    return resp


@router.get("/api/wrouter/app/me")
def app_me(request: Request):
    try:
        s = _sessao(request)
    except HTTPException as ex:
        if ex.status_code == 403:
            return {"logado": True, "trocar_senha": True}
        return {"logado": False}
    v = placas_cadastradas().get(s["placa"]) or {}
    return {"logado": True, "placa": s["placa"], "veiculo": v.get("nome"), "trocar_senha": False}


@router.post("/api/wrouter/app/sair")
def app_sair():
    r = JSONResponse({"ok": True})
    r.delete_cookie(_ck(), path="/")
    return r


# ══════════════════════════════════════════════════════════════════════════════
# O QUE O APP VÊ
# ══════════════════════════════════════════════════════════════════════════════
def _ped_app(car: dict, pid: str, mid: str) -> dict:
    ped = E.ST.dados["pedidos"].get(pid) or {}
    ev = rota(car)["pedidos"].get(pid) or {}
    end = ped.get("endereco") or {}
    vz = ev.get("vizinho")
    lib = ev.get("liberacao") or {}
    prod = lambda i: E.ST.dados["produtos"].get(i) or {}
    return {"pid": pid, "numero": ped.get("numero"), "nome": ped.get("cliente_nome"), "telefone": ped.get("telefone"),
            "endereco": " ".join(x for x in (end.get("logradouro"), end.get("numero")) if x), "compl": end.get("complemento"),
            "bairro": end.get("bairro"), "cidade": end.get("cidade"), "uf": end.get("uf"), "cep": end.get("cep"), "referencia": end.get("referencia"),
            "tipo": ped.get("tipo"), "obs": ped.get("obs") or "", "obs_entrega": (ped.get("agendamento") or {}).get("obs") or "",
            "nf": {"numero": (ped.get("nf") or {}).get("numero"), "serie": (ped.get("nf") or {}).get("serie"), "tem_etiqueta": bool((ped.get("nf") or {}).get("chave"))} if ped.get("nf") else None,
            "recebido": {k: (ev.get("comprovante") or {}).get(k) for k in ("recebedor", "parentesco", "palavra")} if ev.get("comprovante") else None,
            "itens": [{"produto_id": i["produto_id"], "desc": prod(i["produto_id"]).get("nome", "Produto"), "qtd": i["qtd"]} for i in ped.get("pendentes") or []]
            if not ev.get("desfecho") else [{"produto_id": i["produto_id"], "desc": prod(i["produto_id"]).get("nome", "Produto"), "qtd": i["qtd"]}
                                            for i in (ev.get("itens_saida") or ped.get("itens") or [])],
            "recolher": [{"desc": prod(i["produto_id"]).get("nome", "Produto"), "qtd": i["qtd"]} for i in ped.get("recolher") or []],
            "desfecho": ev.get("desfecho") or "", "motivo": ev.get("motivo") or "", "em": ev.get("em") or "", "por": ev.get("por") or "",
            "palavra_conferida": bool(ev.get("palavra_ok")), "liberacao": lib.get("status") or "", "tentativas": int(ev.get("tentativas") or 0),
            "pode_desfazer": bool(ev.get("desfecho")) and ev.get("mid") == mid and _min_desde(ev.get("em")) <= DESFAZER_MIN
                             and not (ev.get("validar_palavra") or {}).get("status") == "aceita",
            "validar_palavra": (ev.get("validar_palavra") or {}).get("status") or "",
            "chat": _chat_resumo(car, pid, "motorista"), "motivo_chat": motivo_do_chat(car, pid),
            "destino": destino(car, pid), "chegou": ev.get("chegou"),
            "vizinho": {"numero": vz.get("numero") or "", "tel": vz.get("tel") or "", "sem_palavra": not str(vz.get("nome") or "").strip()} if vz else None}


def carga_app(cid: str, car: dict) -> dict:
    r = rota(car)
    m = motorista_da_carga(car)
    todos = [_ped_app(car, pid, m["id"]) for pid in car.get("pedidos") or []]
    peds = todos if r.get("saida") else []   # os dados das entregas só descem para o celular no "Iniciar rota"
    c = cfg()
    return {"id": cid, "numero": car.get("numero"), "data": car.get("data"), "status": car.get("status"), "motorista": m["nome"],
            "saida": r.get("saida"), "chegada": r.get("chegada"), "pedidos": peds, "total": len(todos), "feitos": sum(1 for p in todos if p["desfecho"]),
            "palavra_ligada": palavra_ligada(m["id"]), "tentativas_max": c["tentativas"], "motivos": motivos(), "raio_chegada_m": c["raio_chegada_m"],
            "km_laranja": c["km_laranja"]}   # perto do cliente o app manda a posição mais vezes (o cliente acompanha no mapa)


@router.get("/api/wrouter/app/cargas")
def app_cargas(request: Request):
    s = _sessao(request)
    with E.ST.trava:
        cs = cargas_da_placa(s["placa"])
        for cid, car in cs:
            pedir_geo(cid, car)
        v = placas_cadastradas().get(s["placa"]) or {}
        return {"placa": s["placa"], "veiculo": v.get("nome"), "cargas": [carga_app(cid, car) for cid, car in cs], "servidor": agora()}


def _carga_mot(tx, s: dict, cid: str, aberta: bool = True) -> dict:
    car = tx.get("cargas", cid)
    if not car or placa_da_carga(car) != s["placa"]:
        raise HTTPException(404, "Esta carga não é da sua placa.")
    if aberta and (rota(car).get("chegada") or car.get("status") not in ("montando", "em_rota", "finalizada")):
        raise HTTPException(409, "Você já avisou a chegada no CD. Correções agora só pela frota.")
    return car


def _gravar(tx, cid: str, car: dict):
    car["atualizado_em"] = agora()
    tx.put("cargas", cid, {k: v for k, v in car.items() if k != "id"})
    tx.commit()


def _hist(car: dict, q: dict, acao: str, det: str = ""):
    r = rota(car)
    r.setdefault("hist", []).append({"em": agora(), "por": q.get("nome") or q.get("login"), "acao": acao, "det": det[:300]})
    r["hist"] = r["hist"][-300:]


@router.post("/api/wrouter/app/cargas/{cid}/saida")
async def app_saida(cid: str, request: Request):
    """INICIAR ROTA: saída da carga no ERP (reservado → trânsito) e os dados das entregas descem para o celular."""
    s = _sessao(request)
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx({"login": f"motorista:{s['placa']}"})
        car = _carga_mot(tx, s, cid)
        q = _quem_mot(s, car)
        tx.u = q
        if car.get("status") == "montando":
            if not liberada_para_app(car):
                raise HTTPException(409, "A carga ainda não foi liberada pelo armazém.")
            E._sair(tx, q, cid)
            car = tx.get("cargas", cid)
        r = rota(car)
        if not r.get("saida"):
            r["saida"] = {"em": agora(), "mid": q["mid"], "nome": q["nome"], "lat": c.get("lat"), "lng": c.get("lng")}
            garantir_links(car)
            _hist(car, q, "iniciou a rota (app)", f"{len(car.get('pedidos') or [])} entrega(s)")
        _gravar(tx, cid, car)
        pedir_geo(cid, car)
        return carga_app(cid, E.ST.dados["cargas"][cid])


def _salvar_foto(data_url: str, cid: str, pid: str) -> str:
    m = re.fullmatch(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)", str(data_url or ""))
    if not m or len(m.group(2)) > FOTO_MAX:
        raise HTTPException(413, "Foto grande demais ou inválida. Tire de novo.")
    try:
        base64.b64decode(m.group(2), validate=True)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Foto inválida.")
    fid = uuid.uuid4().hex[:16]
    banco.db().collection(COL_FOTOS).document(fid).set({"tipo": m.group(1), "b64": m.group(2), "carga": cid, "pid": pid, "em": agora()}, timeout=banco.TIMEOUT)
    return fid


def _foto(fid: str, placa: str = ""):
    if not re.fullmatch(r"[0-9a-f]{16}", fid):
        raise HTTPException(404, "Foto não encontrada.")
    snap = banco.db().collection(COL_FOTOS).document(fid).get(timeout=banco.TIMEOUT)
    d = snap.to_dict() if snap.exists else None
    if not d or (placa and placa_da_carga(E.ST.dados["cargas"].get(d.get("carga")) or {}) != placa):
        raise HTTPException(404, "Foto não encontrada.")
    return Response(base64.b64decode(d["b64"]), media_type=f"image/{d.get('tipo') or 'jpeg'}", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/wrouter/app/foto/{fid}")
def app_foto(fid: str, request: Request):
    s = _sessao(request)
    return _foto(fid, s["placa"])


def baixa_no_erp(tx, q: dict, cid: str, car: dict, pid: str, desfecho: str, motivo: str, linhas: list, obs: str, recebedor: str):
    """O que o motorista registrou vira a BAIXA do ERP (automática)."""
    ped = tx.get("pedidos", pid) or {}
    if desfecho == "entregue":
        c = {"pedido_id": pid, "resultado": "entregue", "recebedor": recebedor, "obs": obs}
    elif desfecho == "parcial":
        c = {"pedido_id": pid, "resultado": "avaria", "motivo": motivo, "avariados": linhas, "obs": obs, "recebedor": recebedor}
    else:
        t = TIPO_ERP.get(tipo_motivo(motivo), "ausente")
        c = {"pedido_id": pid, "resultado": t, "motivo": motivo, "obs": obs}
        if t == "avaria":
            c["avariados"] = [dict(i) for i in ped.get("pendentes") or []]
    E._baixa(tx, q, cid, c)
    return c["resultado"]


def _abrir_ticket_auto(pid: str, resultado: str, motivo: str, q: dict):
    if resultado not in ("avaria", "recusado", "ausente"):
        return
    try:
        import tickets
        banco.thread(tickets.auto_de_baixa, pid, resultado, motivo, q)
    except Exception as ex:  # noqa: BLE001
        print(f"[wrouter] não abriu ticket automático: {ex}")


def _comprovante(tx, car: dict, cid: str, pid: str, ev: dict, q: dict, desf: str, prova: dict | None, c: dict, foto: str, assinatura: str, vz):
    """Monta e sela o comprovante de entrega; o resumo vai para o pedido (ERP, CX e app do cliente)."""
    import entrega_prova as P
    ped = tx.get("pedidos", pid) or {}
    dest = destino(car, pid)
    lat, lng = c.get("lat"), c.get("lng")
    dist = distancia_m(lat, lng, dest["lat"], dest["lng"]) if dest and isinstance(lat, (int, float)) and isinstance(lng, (int, float)) else None
    nf = ped.get("nf") or {}
    vz_sem_nome = bool(vz and not str(vz.get("nome") or "").strip())
    reg = {"resultado": desf, "em": ev.get("em") or agora(), "pedido": ped.get("numero"), "pid": pid, "cliente": ped.get("cliente_nome"),
           "recebedor": str((prova or {}).get("recebedor") or ("" if not vz else f"vizinho nº {vz.get('numero')}")).strip()[:80],
           "parentesco": str((prova or {}).get("parentesco") or ("Vizinho" if vz else "")).strip()[:40],
           "doc_final": re.sub(r"[^0-9Xx]", "", str((prova or {}).get("doc_final") or ""))[-4:],
           "palavra": P.texto_palavra(ev.get("palavra_ok"), (ev.get("liberacao") or {}).get("status") or "", ev.get("validar_palavra"),
                                      palavra_ligada(q["mid"]), vz_sem_nome),
           "lat": round(lat, 6) if isinstance(lat, (int, float)) else None, "lng": round(lng, 6) if isinstance(lng, (int, float)) else None,
           "dist_m": dist, "chegou_em": (ev.get("chegou") or {}).get("em"), "motorista": q.get("nome"), "placa": placa_da_carga(car),
           "carga": car.get("numero"), "carga_id": cid, "nf_numero": nf.get("numero") or "", "nf_chave": nf.get("chave") or "",
           "foto": foto, "assinatura": assinatura, "offline_em": str(c.get("offline_em") or "")[:40] or None,
           "completo": bool(prova and foto and assinatura)}
    fb = ab = ""
    if c.get("foto"):
        fb = str(c["foto"]).split(",", 1)[-1]
    if prova and prova.get("assinatura"):
        ab = str(prova["assinatura"]).split(",", 1)[-1]
    P.selar(reg, fb, ab)
    ev["comprovante"] = reg
    ped["entrega"] = {k: reg.get(k) for k in ("resultado", "em", "recebedor", "parentesco", "doc_final", "palavra", "dist_m", "motorista", "placa",
                                              "carga", "carga_id", "nf_numero", "hash", "completo")}
    ped.setdefault("historico", []).append({"em": agora(), "por": f"motorista:{q.get('placa') or ''}",
                                            "evento": f"Comprovante de entrega: recebido por {reg['recebedor'] or '—'}"
                                                      + (f" ({reg['parentesco']})" if reg["parentesco"] else "") + f" · palavra {reg['palavra']}"})
    tx.put("pedidos", pid, ped)


def _comprovante_evento(tx, car: dict, pid: str, texto: str, por: str):
    """Fato posterior (frota validou/liberou) — entra como evento, sem mexer no código de integridade."""
    ev = rota(car)["pedidos"].get(pid) or {}
    reg = ev.get("comprovante")
    if not reg:
        return
    reg.setdefault("eventos", []).append({"em": agora(), "por": por, "texto": texto[:200]})
    if "validada" in texto:
        reg["palavra"] = "validada pela frota (registro sem sinal)"
    ped = tx.get("pedidos", pid)
    if ped and ped.get("entrega"):
        ped["entrega"]["palavra"] = reg["palavra"]
        tx.put("pedidos", pid, ped)


@router.post("/api/wrouter/app/cargas/{cid}/pedido/{pid}")
async def app_desfecho(cid: str, pid: str, request: Request):
    s = _sessao(request)
    c = await request.json()
    desf = c.get("desfecho")
    if desf not in ("entregue", "retorno", "parcial"):
        raise HTTPException(400, "Escolha Entregue, Retorno ou Parcial.")
    with E.ST.trava:
        tx = E.Tx({"login": f"motorista:{s['placa']}"})
        car = _carga_mot(tx, s, cid)
        if pid not in (car.get("pedidos") or []):
            raise HTTPException(404, "Pedido não encontrado nesta carga.")
        q = _quem_mot(s, car)
        tx.u = q
        ev = ev_de(car, pid)
        if ev.get("desfecho") or pid in (car.get("baixas") or {}):
            if c.get("cid") and ev.get("cid") == c.get("cid"):
                return {"resultado": "ok", "carga": carga_app(cid, car)}   # reenvio do mesmo registro (estava sem sinal)
            raise HTTPException(409, "Este pedido já tem registro. Use Corrigir (até 15 min) ou fale com a frota.")
        if car.get("status") == "montando":   # registrou sem ter tocado em Iniciar rota (sem sinal): a saída acontece agora
            if not liberada_para_app(car):
                raise HTTPException(409, "A carga ainda não foi liberada pelo armazém.")
            E._sair(tx, q, cid)
            car = tx.get("cargas", cid)
            ev = ev_de(car, pid)
        r = rota(car)
        if not r.get("saida"):
            r["saida"] = {"em": agora(), "mid": q["mid"], "nome": q["nome"], "lat": c.get("lat"), "lng": c.get("lng"), "auto": True}
            garantir_links(car)
        maxt = cfg()["tentativas"]
        offline = bool(c.get("offline_em"))
        vz = ev.get("vizinho")
        palavra_ok, validar = None, None
        if desf in ("entregue", "parcial") and palavra_ligada(q["mid"]) and not (vz and not str(vz.get("nome") or "").strip()):
            lib = (ev.get("liberacao") or {}).get("status")
            if lib != "liberada":
                certa = palavra_confere(c.get("palavra"), palavra_efetiva(car, pid), bool(vz))
                if offline and not certa:
                    validar = {"status": "pendente", "digitada": str(c.get("palavra") or "")[:60], "em": agora(), "offline_em": c.get("offline_em")}
                elif int(ev.get("tentativas") or 0) >= maxt:
                    raise HTTPException(423, "Tentativas esgotadas. Peça a liberação à frota.")
                elif not str(c.get("palavra") or "").strip():
                    return {"resultado": "pede_palavra"}
                elif not certa:
                    ev["tentativas"] = int(ev.get("tentativas") or 0) + 1
                    _hist(car, q, "palavra da entrega incorreta", f"pedido #{(tx.get('pedidos', pid) or {}).get('numero')} · {ev['tentativas']}/{maxt}")
                    _gravar(tx, cid, car)
                    return {"resultado": "palavra_errada", "restam": maxt - ev["tentativas"], "carga": carga_app(cid, E.ST.dados["cargas"][cid])}
                else:
                    palavra_ok = True
            else:
                palavra_ok = False
        motivo = str(c.get("motivo") or "").strip()[:120]
        linhas = []
        if desf in ("retorno", "parcial"):
            motivo = motivo or motivo_do_chat(car, pid)[:120]
            if not motivo:
                raise HTTPException(400, "Escolha o motivo do retorno.")
            if not c.get("foto"):
                raise HTTPException(400, "Tire a foto da peça para registrar o retorno.")
        ped = tx.get("pedidos", pid) or {}
        if desf == "parcial":
            pend = {i["produto_id"]: i["qtd"] for i in ped.get("pendentes") or []}
            for ln in c.get("linhas") or []:
                prd, n = str(ln.get("produto_id") or ""), E._int(ln.get("qtd"))
                if 0 < n <= pend.get(prd, 0):
                    linhas.append({"produto_id": prd, "qtd": n})
            if not linhas:
                raise HTTPException(400, "Marque quais peças voltaram.")
        prova = c.get("prova") if desf in ("entregue", "parcial") and isinstance(c.get("prova"), dict) else None
        if prova is not None:   # app novo: comprovante completo é obrigatório
            if not str(prova.get("recebedor") or "").strip():
                raise HTTPException(400, "Digite o nome de quem recebeu.")
            if not str(prova.get("parentesco") or "").strip():
                raise HTTPException(400, "Escolha quem recebeu (próprio cliente, familiar, vizinho…).")
            if not prova.get("assinatura"):
                raise HTTPException(400, "Falta a assinatura de quem recebeu.")
            if not c.get("foto"):
                raise HTTPException(400, "Tire a foto da entrega para registrar.")
        foto = _salvar_foto(c["foto"], cid, pid) if c.get("foto") else ""
        assinatura = _salvar_foto(prova["assinatura"], cid, pid) if prova else ""
        ev["itens_saida"] = [dict(i) for i in ped.get("pendentes") or []]
        recebedor = (f"vizinho nº {vz.get('numero')}" + (f" ({vz.get('nome')})" if vz.get("nome") else "")) if vz else "cliente"
        if prova:
            recebedor = str(prova.get("recebedor") or "").strip()[:80] + (f" ({str(prova.get('parentesco'))[:40]})" if prova.get("parentesco") else "") \
                + (f" · vizinho nº {vz.get('numero')}" if vz else "")
        tx.put("cargas", cid, {k: v for k, v in car.items() if k != "id"})   # a baixa do ERP lê a carga da transação
        resultado = baixa_no_erp(tx, q, cid, car, pid, desf, motivo, linhas, str(c.get("obs") or "")[:300], recebedor)
        car = tx.get("cargas", cid)
        ev = ev_de(car, pid)
        ev.update(cid=str(c.get("cid") or "")[:40], desfecho=desf, motivo=motivo if desf != "entregue" else "", linhas=linhas,
                  obs=str(c.get("obs") or "")[:300], foto=foto, em=agora(), mid=q["mid"], por=q["nome"], lat=c.get("lat"), lng=c.get("lng"),
                  palavra_ok=palavra_ok, validar_palavra=validar, offline_em=str(c.get("offline_em") or "")[:40] or None, baixa_erp=resultado,
                  itens_saida=ev.get("itens_saida") or [dict(i) for i in ped.get("pendentes") or []])
        if desf in ("entregue", "parcial"):
            _comprovante(tx, car, cid, pid, ev, q, desf, prova, c, foto, assinatura, vz)
        rot = {"entregue": "ENTREGUE", "retorno": "RETORNO", "parcial": "ENTREGA PARCIAL"}[desf]
        _hist(car, q, f"{rot} (app)", f"pedido #{ped.get('numero')} · {ped.get('cliente_nome')}" + (f" · {motivo}" if motivo and desf != "entregue" else "")
              + (" · palavra conferida" if palavra_ok else " · liberado pela frota" if palavra_ok is False else "") + (" · vizinho" if vz else "")
              + (f" · SEM SINAL às {str(c.get('offline_em'))[11:16]}" if offline else "") + (" · PALAVRA NÃO CONFERIU: frota valida" if validar else ""))
        _gravar(tx, cid, car)
    _abrir_ticket_auto(pid, resultado, motivo, q)
    if desf in ("entregue", "parcial"):
        _avisar_cliente_entrega(pid)
    return {"resultado": "ok", "validar_palavra": bool(validar), "carga": carga_app(cid, E.ST.dados["cargas"][cid])}


def _avisar_cliente_entrega(pid: str):
    """Logo depois da entrega o cliente recebe no app: quem recebeu e a hora (dificulta contestar depois)."""
    try:
        ped = E.ST.dados["pedidos"].get(pid) or {}
        ent = ped.get("entrega") or {}
        cod = (E.ST.dados["parceiros"].get(ped.get("cliente_id") or "") or {}).get("codigo")
        if not cod or not ent:
            return
        import promocoes
        texto = (f"Pedido #{ped.get('numero')} {'entregue' if ent.get('resultado') == 'entregue' else 'entregue em parte'} às "
                 f"{str(ent.get('em') or '')[11:16]}, recebido por {ent.get('recebedor') or '—'}. Não reconhece? Fale com a central no app.")
        banco.thread(promocoes.avisar_cliente, cod, "📦 Entrega realizada", texto, f"{banco.prefixo_publico()}/cliente/", f"entrega-{pid}")
    except Exception as ex:  # noqa: BLE001
        print(f"[wrouter] não avisou o cliente: {ex}")


def _desfazer(tx, q: dict, cid: str, car: dict, pid: str, nota: str, pela_frota: str = ""):
    ev = ev_de(car, pid)
    ant = {k: ev.get(k) for k in ("desfecho", "motivo", "em", "por")}
    if ev.get("comprovante"):
        ant["comprovante"] = ev.pop("comprovante")
        ped = tx.get("pedidos", pid)
        if ped and ped.pop("entrega", None) is not None:
            tx.put("pedidos", pid, ped)
    tx.put("cargas", cid, {k: v for k, v in car.items() if k != "id"})
    E.desfazer_baixa(tx, q, cid, pid, nota or "registro corrigido")
    car = tx.get("cargas", cid)
    ev = ev_de(car, pid)
    for k in ("cid", "desfecho", "motivo", "linhas", "obs", "foto", "em", "mid", "por", "lat", "lng", "palavra_ok", "baixa_erp", "validar_palavra", "offline_em", "itens_saida"):
        ev.pop(k, None)
    ev.setdefault("corrigidos", []).append({**ant, "desfeito_em": agora(), **({"pela_frota": pela_frota, "nota": nota} if pela_frota else {})})
    return car


@router.post("/api/wrouter/app/cargas/{cid}/pedido/{pid}/desfazer")
def app_desfazer(cid: str, pid: str, request: Request):
    s = _sessao(request)
    with E.ST.trava:
        tx = E.Tx({"login": f"motorista:{s['placa']}"})
        car = _carga_mot(tx, s, cid)
        q = _quem_mot(s, car)
        tx.u = q
        ev = rota(car)["pedidos"].get(pid) or {}
        if not ev.get("desfecho"):
            raise HTTPException(404, "Não há registro para corrigir.")
        if ev.get("mid") != q["mid"] or _min_desde(ev.get("em")) > DESFAZER_MIN:
            raise HTTPException(409, f"Só dá para corrigir o próprio registro em até {DESFAZER_MIN} minutos. Fale com a frota.")
        car = _desfazer(tx, q, cid, car, pid, "o motorista corrigiu")
        _hist(car, q, "registro corrigido pelo motorista", f"pedido #{(tx.get('pedidos', pid) or {}).get('numero')} · era {ev.get('desfecho')}")
        _gravar(tx, cid, car)
        return carga_app(cid, E.ST.dados["cargas"][cid])


@router.post("/api/wrouter/app/cargas/{cid}/pedido/{pid}/chegou")
async def app_chegou(cid: str, pid: str, request: Request):
    s = _sessao(request)
    c = await request.json()
    lat, lng = c.get("lat"), c.get("lng")
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(400, "Sem a sua localização. Ligue o GPS do celular e tente de novo.")
    with E.ST.trava:
        tx = E.Tx({"login": f"motorista:{s['placa']}"})
        car = _carga_mot(tx, s, cid)
        q = _quem_mot(s, car)
        ev = ev_de(car, pid)
        if ev.get("chegou") or ev.get("desfecho"):
            return {"chegou": ev.get("chegou"), "carga": carga_app(cid, car)}
        dest = destino(car, pid)
        dist = distancia_m(lat, lng, dest["lat"], dest["lng"]) if dest else None
        folga = min(int(c.get("prec") or 0), 150)
        conferido = dist is not None and dist <= cfg()["raio_chegada_m"] + folga
        if c.get("auto") and not conferido:
            raise HTTPException(409, "Ainda longe do endereço.")
        ev["chegou"] = {"em": agora(), "lat": round(lat, 6), "lng": round(lng, 6), "prec": round(c.get("prec") or 0), "dist_m": dist,
                        "conferido": conferido, "sem_endereco": dest is None, "auto": bool(c.get("auto")), "mid": q["mid"], "nome": q["nome"]}
        try:
            import regua
            regua.motorista_chegou(pid, cid)
        except Exception as ex:  # noqa: BLE001
            print(f"[wrouter] régua: {ex}")
        _hist(car, q, "chegou no cliente", f"pedido #{(tx.get('pedidos', pid) or {}).get('numero')} · "
              + (f"no endereço ({dist} m)" if conferido else f"LONGE do endereço ({dist} m)" if dist is not None else "endereço sem coordenada"))
        _gravar(tx, cid, car)
        return {"chegou": ev["chegou"], "carga": carga_app(cid, E.ST.dados["cargas"][cid])}


@router.post("/api/wrouter/app/cargas/{cid}/pedido/{pid}/liberacao")
async def app_pedir_liberacao(cid: str, pid: str, request: Request):
    s = _sessao(request)
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx({"login": f"motorista:{s['placa']}"})
        car = _carga_mot(tx, s, cid)
        q = _quem_mot(s, car)
        ev = ev_de(car, pid)
        if (ev.get("liberacao") or {}).get("status") in ("pendente", "liberada"):
            return carga_app(cid, car)
        ev["liberacao"] = {"status": "pendente", "pedido_em": agora(), "pedido_por": q["nome"], "motivo": str(c.get("motivo") or "Cliente não tem a palavra")[:200]}
        _hist(car, q, "pediu liberação sem palavra", f"pedido #{(tx.get('pedidos', pid) or {}).get('numero')}")
        _gravar(tx, cid, car)
        return carga_app(cid, E.ST.dados["cargas"][cid])


@router.post("/api/wrouter/app/cargas/{cid}/chegada")
async def app_chegada(cid: str, request: Request):
    s = _sessao(request)
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx({"login": f"motorista:{s['placa']}"})
        car = _carga_mot(tx, s, cid)
        q = _quem_mot(s, car)
        faltam = [pid for pid in car.get("pedidos") or [] if pid not in (car.get("baixas") or {})]
        if faltam:
            raise HTTPException(409, f"Ainda falta registrar {len(faltam)} pedido(s).")
        rota(car)["chegada"] = {"em": agora(), "mid": q["mid"], "nome": q["nome"], "lat": c.get("lat"), "lng": c.get("lng")}
        _hist(car, q, "chegou no CD (app)", f"{sum(1 for v in (car.get('baixas') or {}).values() if v != 'entregue')} pedido(s) com peça voltando")
        _gravar(tx, cid, car)
        GPS.pop(s["placa"], None)
        return carga_app(cid, E.ST.dados["cargas"][cid])


@router.post("/api/wrouter/app/gps")
async def app_gps(request: Request):
    s = _sessao(request)
    c = await request.json()
    lat, lng = c.get("lat"), c.get("lng")
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(400, "Posição inválida.")
    fonte = "rede" if c.get("fonte") == "rede" else "gps"
    pos = {"lat": round(lat, 6), "lng": round(lng, 6), "prec": round(c.get("prec") or 0), "em": agora(), "t": time.time(), "fonte": fonte}
    GPS[s["placa"]] = pos
    SINAL[s["placa"]] = {"t": time.time(), "gps": "ativo" if fonte == "gps" else "rede"}
    with E.ST.trava:
        for cid, car in cargas_da_placa(s["placa"]):
            if not na_rua(car):
                continue
            try:   # régua do cliente: "o motorista está a X km"
                import regua
                for pid in car.get("pedidos") or []:
                    regua.motorista_perto(pid, cid, dist_pedido(car, pid, pos).get("km"))
            except Exception as ex:  # noqa: BLE001
                print(f"[wrouter] régua: {ex}")
            r = car.get("rota") or {}
            ult = (r.get("trilha") or [None])[-1]
            if not ult or time.time() - float(ult[3] if len(ult) > 3 else 0) >= TRILHA_SEG:
                tx = E.Tx({"login": "wrouter"})
                car = tx.get("cargas", cid)
                rr = rota(car)
                rr["trilha"] = (rr["trilha"] + [[pos["lat"], pos["lng"], pos["em"][11:16], round(time.time())]])[-400:]
                rr["gps"] = {k: pos[k] for k in ("lat", "lng", "prec", "em", "fonte")}
                try:
                    _gravar(tx, cid, car)
                except Exception as ex:  # noqa: BLE001
                    print(f"[wrouter] trilha não gravou: {ex}")
    return {"ok": True}


@router.post("/api/wrouter/app/sinal")
async def app_sinal(request: Request):
    s = _sessao(request)
    c = await request.json()
    SINAL[s["placa"]] = {"t": time.time(), "gps": str(c.get("gps") or "")[:12]}
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# CHAT motorista ↔ frota (por cliente da carga) + presença de quem está tratando
# ══════════════════════════════════════════════════════════════════════════════
def _chats(car: dict, pid: str) -> dict:
    return rota(car)["chats"].setdefault(pid, {"atual": None, "atendimentos": []})


def _chat_atual(ch: dict):
    return next((a for a in ch["atendimentos"] if a["id"] == ch.get("atual")), None) if ch.get("atual") else None


def motivo_do_chat(car: dict, pid: str) -> str:
    ch = ((car.get("rota") or {}).get("chats") or {}).get(pid) or {}
    ats = [a for a in ch.get("atendimentos") or [] if a.get("motivo") != FROTA_MOTIVO]
    return str(ats[-1].get("motivo") or "") if ats else ""


def _restante(a):
    if not a or a.get("fechado_em") or not a.get("prazo_ts"):
        return None
    return int(float(a["prazo_ts"]) - time.time())


def _a_pub(a):
    return {**a, "restante_seg": _restante(a)} if a else None


PRESENCA = banco.por_empresa(dict)
PRESENCA_SEG = 25


def presenca_marcar(cid, pid, q: dict, sair: bool = False):
    k, em = f"{cid}|{pid}", str(q.get("login") or "")
    if sair:
        (PRESENCA.get(k) or {}).pop(em, None)
    elif em:
        PRESENCA.setdefault(k, {})[em] = {"por": q.get("nome") or em, "t": time.time()}


def presentes(cid, pid) -> list:
    d = PRESENCA.get(f"{cid}|{pid}") or {}
    for em in [e for e, v in d.items() if v["t"] < time.time() - PRESENCA_SEG]:
        d.pop(em, None)
    return [{"login": e, "por": v["por"]} for e, v in sorted(d.items(), key=lambda x: x[1]["t"])]


def _ult(a: dict) -> dict:
    m = next((x for x in reversed(a.get("msgs") or []) if x.get("de") != "sistema"), None) or ((a.get("msgs") or [None])[-1]) or {}
    return {"ult_txt": ("📷 Foto" if m.get("foto") and (m.get("txt") or "") in ("", "📷 Foto") else str(m.get("txt") or ""))[:120],
            "ult_de": m.get("de") or "", "ult_nome": m.get("nome") or ""}


def _chat_resumo(car: dict, pid: str, lado: str) -> dict:
    ch = ((car.get("rota") or {}).get("chats") or {}).get(pid) or {"atual": None, "atendimentos": []}
    a = _chat_atual(ch)
    extra = {"presenca": presentes(car.get("id") or "", pid)} if lado == "frota" else {}
    if not a:
        ats = ch.get("atendimentos") or []
        if lado == "frota" and ats:
            u = ats[-1]
            extra.update(_ult(u), ult_em=(u["msgs"][-1]["em"] if u.get("msgs") else u.get("aberto_em")), ult_motivo=u.get("motivo"),
                         fechado_em=u.get("fechado_em"), fechado_por=u.get("fechado_por"), assumido=u.get("assumido"))
        return {"aberto": False, "motivo": "", "nao_lidas": 0, "ult_em": "", "atendimentos": len(ats), **extra}
    outro = "motorista" if lado == "frota" else "frota"
    lidas = int(a.get(f"lido_{lado}") or 0)
    if lado == "frota":
        extra.update(_ult(a), assumido=a.get("assumido"), aberto_por=a.get("aberto_por") or "motorista")
    return {"aberto": True, "motivo": a.get("motivo"), "ult_em": (a["msgs"][-1]["em"] if a["msgs"] else a.get("aberto_em")),
            "restante_seg": _restante(a), "prazo_min": a.get("prazo_min"),
            "nao_lidas": sum(1 for m in a["msgs"][lidas:] if m.get("de") == outro), "atendimentos": len(ch["atendimentos"]), **extra}


def _msg(a: dict, de: str, nome: str, txt: str, foto: str = "", anexos: list | None = None):
    a["msgs"].append({"de": de, "nome": nome, "txt": txt[:2000], "em": agora(), **({"foto": foto} if foto else {}), **({"anexos": anexos} if anexos else {})})
    a["msgs"] = a["msgs"][-CHAT_MAX:]


def _novo_atendimento(motivo: str, quem: dict, aberto_por: str) -> dict:
    m = cfg()["chat_minutos"]
    return {"id": uuid.uuid4().hex[:8], "motivo": motivo, "aberto_em": agora(), "mid": quem.get("mid"), "nome": quem.get("nome"),
            "msgs": [], "lido_frota": 0, "lido_motorista": 0, "fechado_em": None, "fechado_por": None, "aberto_por": aberto_por,
            "prazo_min": m, "prazo_ts": time.time() + m * 60}


@router.get("/api/wrouter/app/cargas/{cid}/pedido/{pid}/chat")
def app_chat(cid: str, pid: str, request: Request):
    s = _sessao(request)
    with E.ST.trava:
        tx = E.Tx({"login": "motorista"})
        car = _carga_mot(tx, s, cid, aberta=False)
        ch = _chats(car, pid)
        a = _chat_atual(ch)
        if a and a.get("lido_motorista") != len(a["msgs"]):
            a["lido_motorista"] = len(a["msgs"])
            _gravar(tx, cid, car)
        return {"atual": _a_pub(a), "motivos": motivos()}


@router.post("/api/wrouter/app/cargas/{cid}/pedido/{pid}/chat")
async def app_chat_enviar(cid: str, pid: str, request: Request):
    s = _sessao(request)
    c = await request.json()
    txt = str(c.get("texto") or "").strip()
    with E.ST.trava:
        tx = E.Tx({"login": "motorista"})
        car = _carga_mot(tx, s, cid, aberta=False)
        q = _quem_mot(s, car)
        ch = _chats(car, pid)
        a = _chat_atual(ch)
        if not a:
            motivo = str(c.get("motivo") or "").strip()
            if motivo not in motivos():
                raise HTTPException(400, "Escolha o motivo para falar com a frota.")
            a = _novo_atendimento(motivo, q, "motorista")
            _msg(a, "sistema", "", f"{q['nome']} abriu o chat: {motivo}")
            ch["atendimentos"].append(a)
            ch["atual"] = a["id"]
            _hist(car, q, "chat com a frota aberto", f"pedido #{(E.ST.dados['pedidos'].get(pid) or {}).get('numero')} · {motivo}")
        anx = A.salvar_lista(c.get("anexos"), {"carga": cid, "pid": pid}) if c.get("anexos") else []
        if c.get("foto"):
            _msg(a, "motorista", q["nome"], txt or "📷 Foto", _salvar_foto(c["foto"], cid, pid), anx)
        elif txt or anx:
            _msg(a, "motorista", q["nome"], txt, anexos=anx)
        a["lido_motorista"] = len(a["msgs"])
        _gravar(tx, cid, car)
        return {"atual": _a_pub(a), "motivos": motivos()}


# ══════════════════════════════════════════════════════════════════════════════
# PAINEL (hub, permissões do módulo WROUTER)
# ══════════════════════════════════════════════════════════════════════════════
def _ctx(request: Request, acao: str | None = None, texto: str = ""):
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(MOD)
    if esq is None:
        raise HTTPException(404, "Módulo WROUTER não encontrado (falta modulos/wrouter.html).")
    p = acesso.permissoes(u, MOD, esq)
    if not p["acoes"].get("acessar"):
        raise HTTPException(403, "Sem acesso ao WROUTER.")
    if acao and not p["acoes"].get(acao):
        raise HTTPException(403, f"Sem permissão para {texto or acao}.")
    if not banco.configurado():
        raise HTTPException(503, "Banco não configurado: falta FIRESTORE_CREDS no Render.")
    E.ST.carregar()
    return {"login": u.get("login", ""), "nome": u.get("nome") or u.get("login", ""), "admin": bool(u.get("admin"))}, p


def _ped_pub(car: dict, cid: str, pid: str, pos) -> dict:
    ped = E.ST.dados["pedidos"].get(pid) or {}
    ev = rota(car)["pedidos"].get(pid) or {}
    end = ped.get("endereco") or {}
    w = ((car.get("wlog") or {}).get("retorno") or {}).get("itens") or []
    its = [x for x in w if x.get("pid") == pid]
    return {"pid": pid, "numero": ped.get("numero"), "nome": ped.get("cliente_nome"), "cliente_id": ped.get("cliente_id"), "telefone": ped.get("telefone"),
            "bairro": end.get("bairro"), "cidade": end.get("cidade"), "tipo": ped.get("tipo"), "status_erp": ped.get("status"),
            "pecas": sum(E._int(i.get("qtd")) for i in ped.get("itens") or []),
            "desfecho": _desfecho_de(car, pid), "baixa_erp": (car.get("baixas") or {}).get(pid) or "", "manual": bool((car.get("baixas") or {}).get(pid) and not ev.get("desfecho")),
            "motivo": ev.get("motivo") or "", "obs": ev.get("obs") or "", "em": ev.get("em") or "", "por": ev.get("por") or "", "foto": ev.get("foto") or "",
            "lat": ev.get("lat"), "lng": ev.get("lng"), "linhas": ev.get("linhas") or [], "palavra_ok": ev.get("palavra_ok"),
            "comprovante": {k: (ev.get("comprovante") or {}).get(k) for k in ("recebedor", "parentesco", "palavra", "hash", "completo")} if ev.get("comprovante") else None,
            "tentativas": int(ev.get("tentativas") or 0), "liberacao": ev.get("liberacao"), "validar_palavra": ev.get("validar_palavra"),
            "offline_em": ev.get("offline_em"), "corrigidos": len(ev.get("corrigidos") or []), "chegou": ev.get("chegou"), "destino": destino(car, pid),
            "vizinho": ev.get("vizinho"), "link": link_do_pedido(car, pid), "chat": _chat_resumo(car, pid, "frota"), "cliente_chat": _cliente_chat_resumo(ev, ped, car, pid),
            "palavra": palavra_efetiva(car, pid, ped), "palavra_original": ped.get("palavra_chave") if ev.get("vizinho") else "",
            "retorno_esperado": len(its), "retorno_recebido": sum(1 for x in its if x.get("recebido")),
            **dist_pedido(car, pid, pos)}


def carga_viva(cid: str, car: dict) -> dict:
    car = {**car, "id": cid}
    r = rota(car)
    pos = posicao_atual(car)
    peds = [_ped_pub(car, cid, pid, pos) for pid in car.get("pedidos") or []]
    m = motorista_da_carga(car)
    v = E.ST.dados["parceiros"].get(car.get("veiculo_id") or "") or {}
    fase = "chegou" if r.get("chegada") else ("rua" if r.get("saida") or car.get("status") == "em_rota" else "aguardando")
    return {"id": cid, "numero": car.get("numero"), "data": car.get("data"), "placa": placa_da_carga(car), "veiculo": v.get("nome"),
            "motorista": m["nome"], "motorista_id": m["id"], "palavra_ligada": palavra_ligada(m["id"]), "status": car.get("status"), "fase": fase,
            "saida": r.get("saida"), "chegada": r.get("chegada"), "pos": {**pos, "rumo": rumo(car, pos)} if pos else None, "sinal": sinal_pub(car) if fase == "rua" else None,
            "trilha": [t[:3] for t in r.get("trilha") or []], "pedidos": peds, "hist": (r.get("hist") or [])[-40:],
            "cont": {"total": len(peds), "entregue": sum(1 for p in peds if p["desfecho"] == "entregue"), "retorno": sum(1 for p in peds if p["desfecho"] == "retorno"),
                     "parcial": sum(1 for p in peds if p["desfecho"] == "parcial"), "pendente": sum(1 for p in peds if not p["desfecho"]),
                     "chegou": sum(1 for p in peds if not p["desfecho"] and p.get("chegou")),
                     "liberacoes": sum(1 for p in peds if (p["liberacao"] or {}).get("status") == "pendente"),
                     "pecas_esperadas": sum(p["retorno_esperado"] for p in peds), "pecas_recebidas": sum(p["retorno_recebido"] for p in peds),
                     "chats_abertos": sum(1 for p in peds if p["chat"]["aberto"]), "chats_nao_lidos": sum(p["chat"]["nao_lidas"] for p in peds)}}


def _cargas_do_dia(dia: str) -> list:
    out = []
    for cid, car in E.ST.dados["cargas"].items():
        r = car.get("rota") or {}
        ativa = (liberada_para_app(car) or na_rua(car)) and dia == E.hoje()
        do_dia = car.get("data") == dia or any(str((x or {}).get("em") or "")[:10] == dia for x in (r.get("saida"), r.get("chegada")))
        if (ativa or do_dia) and car.get("pedidos") and (car.get("status") != "montando" or liberada_para_app(car)):
            out.append((cid, car))
    return sorted(out, key=lambda x: (x[1].get("data") or "", x[1].get("numero") or 0))


@router.get("/api/wrouter/eu")
def eu(request: Request):
    q, p = _ctx(request)
    return {"eu": q, "perm": p, "base": banco.prefixo_publico()}   # "" na principal, "/<empresa>" nas outras


@router.get("/api/wrouter/ao-vivo")
def ao_vivo(request: Request, data: str = ""):
    q, p = _ctx(request, "aovivo", "ver o Ao vivo")
    dia = data if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data or "") else E.hoje()
    with E.ST.trava:
        cs = _cargas_do_dia(dia)
        for cid, car in cs:
            if garantir_links(car):
                tx = E.Tx(q)
                c2 = tx.get("cargas", cid)
                garantir_links(c2)
                _gravar(tx, cid, c2)
            pedir_geo(cid, car)
        lista = [carga_viva(cid, E.ST.dados["cargas"][cid]) for cid, _ in cs]
    soma = lambda k: sum(x["cont"][k] for x in lista)
    return {"data": dia, "servidor": agora(), "pode_tratar": bool(p["acoes"].get("tratar")), "eu": q, "motivos": motivos(), "motivo_frota": FROTA_MOTIVO,
            "km_laranja": cfg()["km_laranja"], "km_vermelho": cfg()["km_vermelho"],
            "kpi": {"na_rua": sum(1 for x in lista if x["fase"] == "rua"), "aguardando_saida": sum(1 for x in lista if x["fase"] == "aguardando"),
                    "chegaram": sum(1 for x in lista if x["fase"] == "chegou"), "entregues": soma("entregue"), "retornos": soma("retorno") + soma("parcial"),
                    "pendentes": soma("pendente"), "liberacoes": soma("liberacoes"), "pecas_a_receber": max(0, soma("pecas_esperadas") - soma("pecas_recebidas")),
                    "chats_abertos": soma("chats_abertos"), "chats_nao_lidos": soma("chats_nao_lidos")},
            "cargas": lista}


def _carga_painel(tx, cid: str) -> dict:
    car = tx.get("cargas", cid)
    if not car:
        raise HTTPException(404, "Carga não encontrada.")
    car["id"] = cid
    return car


@router.get("/api/wrouter/cargas/{cid}/pedido/{pid}")
def cliente_completo(cid: str, pid: str, request: Request, presenca: int = 1):
    q, p = _ctx(request, "aovivo", "ver o cliente")
    with E.ST.trava:
        tx = E.Tx(q)
        car = _carga_painel(tx, cid)
        if pid not in (car.get("pedidos") or []):
            raise HTTPException(404, "Pedido não encontrado nesta carga.")
        ped = E.ST.dados["pedidos"].get(pid) or {}
        ch = _chats(car, pid)
        a = _chat_atual(ch)
        if presenca:
            presenca_marcar(cid, pid, q)
        if a and a.get("lido_frota") != len(a["msgs"]):
            a["lido_frota"] = len(a["msgs"])
            _gravar(tx, cid, car)
            car = {**E.ST.dados["cargas"][cid], "id": cid}
        prod = lambda i: E.ST.dados["produtos"].get(i) or {}
        w = ((car.get("wlog") or {}).get("retorno") or {}).get("itens") or []
        return {**_ped_pub(car, cid, pid, posicao_atual(car)), "carga": car.get("numero"), "carga_id": cid, "placa": placa_da_carga(car),
                "motorista": motorista_da_carga(car)["nome"], "data": car.get("data"), "endereco": ped.get("endereco") or {},
                "itens": [{"desc": prod(i["produto_id"]).get("nome"), "sku": prod(i["produto_id"]).get("sku"), "qtd": i["qtd"]} for i in ped.get("itens") or []],
                "recolher": [{"desc": prod(i["produto_id"]).get("nome"), "qtd": i["qtd"]} for i in ped.get("recolher") or []],
                "obs_pedido": ped.get("obs"), "agendamento": ped.get("agendamento"), "saida": rota(car).get("saida"), "chegada": rota(car).get("chegada"),
                "corrigidos_det": (rota(car)["pedidos"].get(pid) or {}).get("corrigidos") or [],
                "retorno_itens": [x for x in w if x.get("pid") == pid],
                "historico": [h for h in rota(car).get("hist") or [] if f"#{ped.get('numero')}" in str(h.get("det") or "")],
                "chat_det": {"atual": _a_pub(_chat_atual(ch)), "atendimentos": ch["atendimentos"]},
                "pode_tratar": bool(p["acoes"].get("tratar")), "motivos": motivos(), "motivo_frota": FROTA_MOTIVO,
                "presentes": presentes(cid, pid), "eu": q}


@router.post("/api/wrouter/cargas/{cid}/pedido/{pid}/presenca")
async def rota_presenca(cid: str, pid: str, request: Request):
    q, p = _ctx(request, "aovivo")
    c = await request.json()
    presenca_marcar(cid, pid, q, bool(c.get("sair")))
    return {"presenca": presentes(cid, pid)}


@router.post("/api/wrouter/cargas/{cid}/pedido/{pid}/chat")
async def frota_chat(cid: str, pid: str, request: Request):
    q, p = _ctx(request, "tratar", "falar com o motorista")
    c = await request.json()
    txt = str(c.get("texto") or "").strip()
    with E.ST.trava:
        tx = E.Tx(q)
        car = _carga_painel(tx, cid)
        ch = _chats(car, pid)
        a = _chat_atual(ch)
        if not a:
            if not c.get("iniciar"):
                raise HTTPException(409, "Não há atendimento aberto com o motorista.")
            if not txt and not c.get("anexos"):
                raise HTTPException(400, "Escreva a mensagem para o motorista.")
            a = _novo_atendimento(FROTA_MOTIVO, motorista_da_carga(car) | {"mid": car.get("motorista_id")}, "frota")
            _msg(a, "sistema", "", f"{q['nome']} chamou o motorista")
            ch["atendimentos"].append(a)
            ch["atual"] = a["id"]
        if not a.get("assumido"):
            a["assumido"] = {"por": q["nome"], "login": q["login"], "em": agora()}
        anx = A.salvar_lista(c.get("anexos"), {"carga": cid, "pid": pid}) if c.get("anexos") else []
        if c.get("foto"):
            _msg(a, "frota", q["nome"], txt or "📷 Foto", _salvar_foto(c["foto"], cid, pid), anx)
        elif txt or anx:
            _msg(a, "frota", q["nome"], txt, anexos=anx)
        a["lido_frota"] = len(a["msgs"])
        _gravar(tx, cid, car)
        return {"atual": _a_pub(a), "atendimentos": ch["atendimentos"]}


@router.post("/api/wrouter/cargas/{cid}/pedido/{pid}/chat/encerrar")
async def frota_chat_encerrar(cid: str, pid: str, request: Request):
    q, p = _ctx(request, "tratar", "encerrar o atendimento")
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(q)
        car = _carga_painel(tx, cid)
        ch = _chats(car, pid)
        a = _chat_atual(ch)
        if not a:
            raise HTTPException(409, "Não há atendimento aberto.")
        nota = str(c.get("texto") or "").strip()
        _msg(a, "sistema", "", f"{q['nome']} encerrou o atendimento" + (f": {nota}" if nota else "."))
        a.update(fechado_em=agora(), fechado_por=q["nome"], lido_frota=len(a["msgs"]))
        ch["atual"] = None
        _hist(car, q, "chat com o motorista encerrado", f"pedido #{(E.ST.dados['pedidos'].get(pid) or {}).get('numero')} · {a.get('motivo')}")
        _gravar(tx, cid, car)
        return {"atual": None, "atendimentos": ch["atendimentos"]}


@router.put("/api/wrouter/cargas/{cid}/liberacao/{pid}")
async def frota_liberacao(cid: str, pid: str, request: Request):
    q, p = _ctx(request, "tratar", "liberar entrega sem palavra")
    c = await request.json()
    if c.get("acao") not in ("liberar", "negar"):
        raise HTTPException(400, "Ação inválida.")
    with E.ST.trava:
        tx = E.Tx(q)
        car = _carga_painel(tx, cid)
        ev = ev_de(car, pid)
        if ev.get("desfecho"):
            raise HTTPException(409, "Este pedido já tem registro do motorista.")
        lib = ev.get("liberacao")
        if not lib or lib.get("status") != "pendente":
            if c["acao"] != "liberar":
                raise HTTPException(409, "Não há pedido de liberação aberto.")
            lib = ev["liberacao"] = {"status": "pendente", "pedido_em": agora(), "pedido_por": f"frota ({q['nome']})", "motivo": "liberado direto pela frota"}
        lib.update(status="liberada" if c["acao"] == "liberar" else "negada", decidido_por=q["nome"], decidido_em=agora(), nota=str(c.get("nota") or "")[:300])
        _hist(car, q, f"entrega sem palavra {'LIBERADA' if c['acao'] == 'liberar' else 'negada'}", f"pedido #{(E.ST.dados['pedidos'].get(pid) or {}).get('numero')}")
        _gravar(tx, cid, car)
        return {"ok": True}


@router.put("/api/wrouter/cargas/{cid}/validar-palavra/{pid}")
async def frota_validar(cid: str, pid: str, request: Request):
    q, p = _ctx(request, "tratar", "validar entrega sem sinal")
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(q)
        car = _carga_painel(tx, cid)
        ev = ev_de(car, pid)
        v = ev.get("validar_palavra") or {}
        if v.get("status") != "pendente":
            raise HTTPException(409, "Não há palavra para validar neste pedido.")
        if c.get("acao") == "aceitar":
            v.update(status="aceita", por=q["nome"], decidido_em=agora())
            ev["palavra_ok"] = False
            _comprovante_evento(tx, car, pid, "palavra validada pela frota (registro sem sinal)", q["nome"])
            _hist(car, q, "entrega sem sinal VALIDADA pela frota", f"pedido #{(E.ST.dados['pedidos'].get(pid) or {}).get('numero')} · digitou {v.get('digitada') or '—'}")
        elif c.get("acao") == "reabrir":
            car = _desfazer(tx, q, cid, car, pid, "palavra não conferiu (sem sinal)", pela_frota=q["nome"])
            _hist(car, q, "entrega sem sinal REABERTA pela frota", f"pedido #{(E.ST.dados['pedidos'].get(pid) or {}).get('numero')}")
        else:
            raise HTTPException(400, "Ação inválida.")
        _gravar(tx, cid, car)
        return {"ok": True}


@router.post("/api/wrouter/cargas/{cid}/pedido/{pid}/reabrir")
async def frota_reabrir(cid: str, pid: str, request: Request):
    """A frota desfaz o registro do motorista (e a baixa no ERP) para ele registrar de novo."""
    q, p = _ctx(request, "tratar", "reabrir registro do motorista")
    c = await request.json()
    nota = str(c.get("nota") or "").strip()
    if not nota:
        raise HTTPException(400, "Diga o motivo.")
    with E.ST.trava:
        tx = E.Tx(q)
        car = _carga_painel(tx, cid)
        if pid not in (car.get("baixas") or {}):
            raise HTTPException(404, "Não há registro para reabrir.")
        if rota(car).get("chegada"):
            raise HTTPException(409, "O motorista já chegou no CD — corrija pela baixa do ERP.")
        car = _desfazer(tx, q, cid, car, pid, nota, pela_frota=q["nome"])
        _hist(car, q, "registro do motorista reaberto", f"pedido #{(E.ST.dados['pedidos'].get(pid) or {}).get('numero')} · {nota}")
        _gravar(tx, cid, car)
        return {"ok": True}


def comprovante_do_pedido(pid: str) -> tuple[dict, dict]:
    """(comprovante, pedido) da entrega mais recente do pedido. 404 se não houver."""
    ped = E.ST.dados["pedidos"].get(pid)
    if not ped:
        raise HTTPException(404, "Pedido não encontrado.")
    regs = [(rota(car)["pedidos"].get(pid) or {}).get("comprovante") for car in E.ST.dados["cargas"].values() if pid in (car.get("pedidos") or [])]
    regs = [r for r in regs if r]
    if not regs:
        raise HTTPException(404, "Este pedido ainda não tem comprovante de entrega.")
    return max(regs, key=lambda r: str(r.get("em") or "")), ped


def comprovante_pdf_resposta(pid: str) -> Response:
    import entrega_prova as P
    with E.ST.trava:
        reg, ped = comprovante_do_pedido(pid)
        reg, ped = json.loads(json.dumps(reg)), json.loads(json.dumps(ped))
    pdf = P.pdf(reg, ped, empresa=str(E.ST.config.get("empresa") or ""))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="comprovante_pedido_{ped.get("numero")}.pdf"'})


@router.post("/api/wrouter/cargas/{cid}/pedido/{pid}/falar-cliente")
async def falar_com_cliente(cid: str, pid: str, request: Request):
    """Chama o cliente pelo APP do cliente (chat do Atendimento + notificação no celular)."""
    q, _p = _ctx(request)
    c = await request.json()
    with E.ST.trava:
        car = E.ST.dados["cargas"].get(cid)
        if not car or pid not in (car.get("pedidos") or []):
            raise HTTPException(404, "Pedido não encontrado nesta carga.")
        ped = dict(E.ST.dados["pedidos"].get(pid) or {}, id=pid)
    import cliente_app
    r = cliente_app.central_chama(ped.get("cliente_id") or "", c.get("texto"), q, ped, anexos=c.get("anexos"))
    with E.ST.trava:
        tx = E.Tx(q)
        car = tx.get("cargas", cid)
        ev = rota(car)["pedidos"].setdefault(pid, {})
        novo = not (ev.get("cliente_chamado") and not ev["cliente_chamado"].get("fim"))
        ev["cliente_chamado"] = {"em": agora(), "por": q.get("nome") or q.get("login"), "tid": r.get("id")}
        if novo:
            _hist(car, q, f"chamou o cliente do pedido #{ped.get('numero')} pelo app")
        tx.put("cargas", cid, car)
        tx.commit()
    return r


def _ped_da_carga(cid: str, pid: str) -> dict:
    car = E.ST.dados["cargas"].get(cid)
    if not car or pid not in (car.get("pedidos") or []):
        raise HTTPException(404, "Pedido não encontrado nesta carga.")
    return E.ST.dados["pedidos"].get(pid) or {}


@router.get("/api/wrouter/cargas/{cid}/pedido/{pid}/cliente-chat")
def ver_chat_cliente(cid: str, pid: str, request: Request):
    """Lado direito (azul) da tela dividida: a conversa com o cliente pelo app."""
    _ctx(request)
    with E.ST.trava:
        ped = _ped_da_carga(cid, pid)
        tid = ((rota(E.ST.dados["cargas"][cid])["pedidos"].get(pid) or {}).get("cliente_chamado") or {}).get("tid") or ""
    import cliente_app
    return cliente_app.chat_com_cliente(ped.get("cliente_id") or "", tid)


@router.post("/api/wrouter/cargas/{cid}/pedido/{pid}/cliente-chat/finalizar")
def finalizar_chat_cliente(cid: str, pid: str, request: Request):
    """Finaliza só a conversa com o cliente — a do motorista continua como está."""
    q, _p = _ctx(request)
    with E.ST.trava:
        ped = _ped_da_carga(cid, pid)
    import cliente_app
    ok = cliente_app.central_finaliza_chat(ped.get("cliente_id") or "", q)
    with E.ST.trava:
        tx = E.Tx(q)
        car = tx.get("cargas", cid)
        ev = rota(car)["pedidos"].setdefault(pid, {})
        if ev.get("cliente_chamado"):
            ev["cliente_chamado"]["fim"] = agora()
        _hist(car, q, f"finalizou a conversa com o cliente do pedido #{ped.get('numero')}")
        tx.put("cargas", cid, car)
        tx.commit()
    return {"ok": True, "finalizado": ok}


def em_rastreio(car: dict, pid: str) -> bool:
    """Pedido EM RASTREIO = é entrega da frota, a carga já saiu (na rua) e este pedido ainda não teve desfecho.
    Só nesse caso a conversa do cliente pelo app aparece também no WROUTER; fora disso ela fica só no CX."""
    r = rota(car)
    if r.get("chegada") or not (r.get("saida") or car.get("status") == "em_rota"):
        return False
    return not _desfecho_de(car, pid)


def _cliente_chat_resumo(ev: dict, ped: dict, car: dict | None = None, pid: str = "") -> dict | None:
    """Balão AZUL no painel: conversa do cliente pelo app — SÓ para pedido em rastreio (frota na rua).
    Cliente sem pedido em rastreio (montando carga, conferindo na doca…) → a conversa cai apenas no CX."""
    if car is not None and not em_rastreio(car, pid):
        return None
    cc = ev.get("cliente_chamado") or {}
    try:
        import cliente_app
        st = cliente_app.chat_com_cliente(ped.get("cliente_id") or "")
    except Exception:  # noqa: BLE001
        return {"ativo": True, "nova": False} if cc and not cc.get("fim") else None
    if not st.get("ativo"):
        return None   # sem conversa aberta (ou a central/CX já encerrou)
    if cc.get("fim") and cc.get("tid") and str(st.get("id", "")).split("#")[-1] == str(cc["tid"]).split("#")[-1]:
        return None
    return {"ativo": True, "nova": st.get("nova", False), "chamado_wrouter": bool(cc and not cc.get("fim"))}


@router.get("/api/wrouter/comprovante/{pid}")
def frota_comprovante(pid: str, request: Request):
    _ctx(request)
    return comprovante_pdf_resposta(pid)


@router.get("/api/wrouter/app/cargas/{cid}/pedido/{pid}/nf")
def app_nf(cid: str, pid: str, request: Request):
    """NF simplificada (etiqueta) do pedido, para o motorista mostrar na fiscalização."""
    s = _sessao(request)
    import nf_simplificada as NFS
    with E.ST.trava:
        car = E.ST.dados["cargas"].get(cid)
        if not car or placa_da_carga(car) != s["placa"] or pid not in (car.get("pedidos") or []):
            raise HTTPException(404, "Pedido não encontrado nesta carga.")
        ped = E.ST.dados["pedidos"].get(pid) or {}
        nf = ped.get("nf") or {}
        if not NFS.chave_valida(nf.get("chave")):
            raise HTTPException(404, "A NF-e deste pedido ainda não foi importada no ERP.")
        pdf = NFS.etiquetas_pdf([(nf, E.etiqueta_extra(pid, ped, car))], mostrar_valor=False)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="nf_{nf.get("numero")}.pdf"'})


def _anexo_da_carga(aid: str, cid: str, pid: str):
    doc = A.ler(aid)
    if doc.get("carga") != cid or doc.get("pid") != pid:
        raise HTTPException(404, "Anexo não encontrado.")
    return A.resposta(doc)


@router.get("/api/wrouter/app/cargas/{cid}/pedido/{pid}/anexo/{aid}")
def app_anexo(cid: str, pid: str, aid: str, request: Request):
    s = _sessao(request)
    with E.ST.trava:
        _carga_mot(E.Tx({"login": "motorista"}), s, cid, aberta=False)
    return _anexo_da_carga(aid, cid, pid)


@router.get("/api/wrouter/cargas/{cid}/pedido/{pid}/anexo/{aid}")
def frota_anexo(cid: str, pid: str, aid: str, request: Request):
    _ctx(request)
    return _anexo_da_carga(aid, cid, pid)


@router.get("/api/wrouter/cargas/{cid}/pedido/{pid}/cliente-anexo/{aid}")
def frota_cliente_anexo(cid: str, pid: str, aid: str, request: Request):
    """Anexo da conversa com o cliente (fica no chamado do cliente, no CX)."""
    _ctx(request)
    with E.ST.trava:
        ped = _ped_da_carga(cid, pid)
    cli = E.ST.dados["parceiros"].get(ped.get("cliente_id") or "") or {}
    doc = A.ler(aid)
    import tickets as T
    if not cli.get("codigo") or doc.get("cont") != T._id_doc(cli["codigo"]):
        raise HTTPException(404, "Anexo não encontrado.")
    return A.resposta(doc)


@router.get("/api/wrouter/foto/{fid}")
def frota_foto(fid: str, request: Request):
    _ctx(request)
    return _foto(fid)


@router.get("/api/wrouter/historico")
def historico(request: Request, de: str = "", ate: str = "", busca: str = ""):
    q, p = _ctx(request, "historico", "ver o histórico de entregas")
    ate = ate if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ate or "") else E.hoje()
    de = de if re.fullmatch(r"\d{4}-\d{2}-\d{2}", de or "") else (datetime.strptime(ate, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")
    termo = norm(busca)
    out = []
    with E.ST.trava:
        for cid, car in E.ST.dados["cargas"].items():
            if not (de <= str(car.get("data") or "") <= ate) or car.get("status") == "montando":
                continue
            car = {**car, "id": cid}
            m = motorista_da_carga(car)
            for pid in car.get("pedidos") or []:
                ped = E.ST.dados["pedidos"].get(pid) or {}
                end = ped.get("endereco") or {}
                cli = E.ST.dados["parceiros"].get(ped.get("cliente_id") or "") or {}
                if termo and termo not in norm(" ".join(str(x or "") for x in (car.get("numero"), placa_da_carga(car), m["nome"], ped.get("numero"),
                                                                                 ped.get("cliente_nome"), cli.get("codigo"), end.get("bairro"), end.get("cidade")))):
                    continue
                ev = rota(car)["pedidos"].get(pid) or {}
                ch = rota(car)["chats"].get(pid) or {}
                out.append({"carga_id": cid, "carga": car.get("numero"), "data": car.get("data"), "placa": placa_da_carga(car), "motorista": m["nome"],
                            "pid": pid, "numero": ped.get("numero"), "nome": ped.get("cliente_nome"), "codigo": cli.get("codigo"), "bairro": end.get("bairro"),
                            "desfecho": _desfecho_de(car, pid), "baixa_erp": (car.get("baixas") or {}).get(pid) or "", "motivo": ev.get("motivo") or "",
                            "em": ev.get("em") or "", "foto": bool(ev.get("foto")), "palavra_ok": ev.get("palavra_ok"), "vizinho": bool(ev.get("vizinho")),
                            "comprovante": bool(ev.get("comprovante")), "recebedor": (ev.get("comprovante") or {}).get("recebedor") or "",
                            "chats": len(ch.get("atendimentos") or []), "chat_aberto": bool(ch.get("atual")),
                            "motivos_chat": [a.get("motivo") for a in ch.get("atendimentos") or []]})
    out.sort(key=lambda x: (x["data"] or "", x["carga"] or 0, x["em"] or ""), reverse=True)
    return {"de": de, "ate": ate, "total": len(out), "itens": out[:2000]}


@router.get("/api/wrouter/motoristas")
def motoristas_app(request: Request):
    q, p = _ctx(request, "motoristas", "ver motoristas e app")
    with E.ST.trava:
        c = cfg()
        pl = APP.dados()["placas"]
        mots = [{"id": k, "nome": v.get("nome"), "telefone": v.get("telefone") or "", "doc": v.get("doc") or "", "obs": v.get("obs") or "",
                 "palavra": bool(c["palavra"].get(k)), "ativo": v.get("ativo", True)}
                for k, v in E.ST.dados["parceiros"].items() if v.get("tipo") == "motorista"]
        veics = []
        for k, v in E.ST.dados["parceiros"].items():
            if v.get("tipo") != "veiculo":
                continue
            pla = norm_placa(v.get("placa"))
            info = pl.get(pla) or {}
            veics.append({"id": k, "nome": v.get("nome") or "", "placa": pla, "ativo": v.get("ativo", True), "obs": v.get("obs") or "",
                          **{x: v.get(x) or 0 for x in ("capacidade", "max_pontos", "max_m3", "max_kg")},
                          "senha": "trocada" if info.get("hash") and not info.get("trocar") else "inicial", "senha_em": info.get("em"),
                          "na_rua": bool(pla and GPS.get(pla))})
    return {"motoristas": sorted(mots, key=lambda x: (not x["ativo"], str(x["nome"] or "").lower())),
            "veiculos": sorted(veics, key=lambda x: (not x["ativo"], x["placa"] or x["nome"])),
            "cfg": {k: v for k, v in c.items() if k != "palavra"}, "senha_inicial_padrao": not os.environ.get("WROUTER_SENHA_INICIAL")}


# ── CADASTRO de motoristas e veículos (mudou do ERP para cá; os dados continuam nos
#    cadastros do ERP, porque a carga escolhe motorista e veículo de lá) ──
CAMPOS_CAD = {"motorista": ("nome", "telefone", "doc", "obs", "ativo"),
              "veiculo": ("nome", "placa", "capacidade", "max_pontos", "max_m3", "max_kg", "obs", "ativo")}


@router.post("/api/wrouter/cadastros")
async def criar_cadastro(request: Request):
    return await _salvar_cadastro(request, None)


@router.put("/api/wrouter/cadastros/{pid}")
async def editar_cadastro(pid: str, request: Request):
    return await _salvar_cadastro(request, pid)


async def _salvar_cadastro(request: Request, pid: str | None):
    q, p = _ctx(request, "motoristas", "cadastrar motoristas e veículos")
    c = await request.json()
    with E.ST.trava:
        atual = E.ST.dados["parceiros"].get(pid) if pid else None
        if pid and not atual:
            raise HTTPException(404, "Cadastro não encontrado.")
        tipo = (atual or {}).get("tipo") or c.get("tipo")
        if tipo not in CAMPOS_CAD:
            raise HTTPException(400, "Aqui só se cadastram motoristas e veículos.")
        dados = {k: c[k] for k in CAMPOS_CAD[tipo] if k in c}
        dados["tipo"] = tipo
        if tipo == "veiculo":
            pla = norm_placa(dados.get("placa", (atual or {}).get("placa")))
            if len(pla) < 7:
                raise HTTPException(400, "Informe a placa (ex.: ABC1D23) — ela é o login do app do motorista.")
            if any(v.get("tipo") == "veiculo" and k != pid and norm_placa(v.get("placa")) == pla for k, v in E.ST.dados["parceiros"].items()):
                raise HTTPException(409, f"A placa {pla} já está cadastrada.")
            dados["placa"] = pla
            if not str(dados.get("nome", (atual or {}).get("nome")) or "").strip():
                dados["nome"] = pla
        pid, d = E.gravar_parceiro(q, pid, dados, True)
    return {"ok": True, "id": pid, "cadastro": {**d, "id": pid}}


@router.put("/api/wrouter/motoristas/{mid}")
async def motorista_palavra(mid: str, request: Request):
    q, p = _ctx(request, "motoristas", "configurar motoristas")
    c = await request.json()
    with APP.trava:
        pal = APP.dados()["cfg"].setdefault("palavra", {})
        pal[mid] = bool(c.get("palavra"))
        APP.salvar()
    return {"ok": True, "palavra": pal[mid]}


@router.post("/api/wrouter/placas/{placa}/resetar")
def resetar_senha(placa: str, request: Request):
    q, p = _ctx(request, "motoristas", "resetar senha da placa")
    pl = norm_placa(placa)
    with APP.trava:
        info = APP.dados()["placas"].setdefault(pl, {"versao": 0})
        info.update(hash="", trocar=True, versao=int(info.get("versao") or 0) + 1, em=agora(), resetado_por=q["nome"])
        APP.salvar()
    GPS.pop(pl, None)
    return {"ok": True}


@router.put("/api/wrouter/cfg")
async def salvar_cfg(request: Request):
    q, p = _ctx(request, "motoristas", "configurar o app")
    c = await request.json()
    with APP.trava:
        d = APP.dados()["cfg"]
        if "tentativas" in c:
            d["tentativas"] = max(1, min(E._int(c["tentativas"]), 20))
        if "chat_minutos" in c:
            d["chat_minutos"] = max(1, min(E._int(c["chat_minutos"]), 240))
        if "raio_chegada_m" in c:
            d["raio_chegada_m"] = max(50, min(E._int(c["raio_chegada_m"]), 2000))
        if "km_laranja" in c or "km_vermelho" in c:
            la = _km(c.get("km_laranja", d.get("km_laranja")), KM_LARANJA)
            vm = _km(c.get("km_vermelho", d.get("km_vermelho")), KM_VERMELHO)
            if vm >= la:
                raise HTTPException(400, "O vermelho (bem perto) precisa ser menor que o laranja (se aproximando).")
            d["km_laranja"], d["km_vermelho"] = la, vm
        if "mapa_cliente" in c:
            d["mapa_cliente"] = bool(c["mapa_cliente"])
        if "motivos" in c:
            ms = [{"motivo": str(m.get("motivo") or "").strip()[:60], "tipo": m.get("tipo") if m.get("tipo") in TIPO_ERP else "ausente"}
                  for m in c["motivos"] or [] if str(m.get("motivo") or "").strip()]
            if not ms:
                raise HTTPException(400, "Deixe ao menos um motivo.")
            d["motivos"] = ms[:20]
        APP.salvar()
    return {"ok": True, "cfg": {k: v for k, v in cfg().items() if k != "palavra"}}


@router.get("/api/wrouter/links")
def links_do_dia(request: Request, data: str = ""):
    """Link de acompanhamento de cada pedido do dia (para mandar ao cliente)."""
    q, p = _ctx(request, "aovivo", "ver os links")
    base = os.environ.get("HUB_URL_PUBLICA", "").rstrip("/") or f"{request.headers.get('x-forwarded-proto') or request.url.scheme}://{request.headers.get('host')}"
    dia = data if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data or "") else E.hoje()
    out = []
    with E.ST.trava:
        for cid, car in _cargas_do_dia(dia):
            for pid in car.get("pedidos") or []:
                t = link_do_pedido(car, pid)
                ped = E.ST.dados["pedidos"].get(pid) or {}
                out.append({"carga": car.get("numero"), "pid": pid, "numero": ped.get("numero"), "cliente": ped.get("cliente_nome"), "link": f"{base}{banco.prefixo_publico()}/entrega/{t}" if t else ""})
    return out


# ══════════════════════════════════════════════════════════════════════════════
# LINK DO CLIENTE (público — o código do link é a chave)
# ══════════════════════════════════════════════════════════════════════════════
def _carga_do_link(token: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,20}", str(token or "")):
        raise HTTPException(404, "Link não encontrado.")
    E.ST.carregar()
    for cid, car in E.ST.dados["cargas"].items():
        v = ((car.get("rota") or {}).get("links") or {}).get(token)
        if v:
            if str(car.get("data") or "") < (datetime.strptime(E.hoje(), "%Y-%m-%d") - timedelta(days=LINK_DIAS)).strftime("%Y-%m-%d"):
                raise HTTPException(410, "Este link de acompanhamento expirou.")
            pids = [p for p in v["pids"] if p in (car.get("pedidos") or [])]
            if pids:
                return cid, {**car, "id": cid}, pids
    raise HTTPException(404, "Link não encontrado.")


def entrega_pub(car: dict, pids: list) -> dict:
    r = rota(car)
    pos = posicao_atual(car)
    exige = palavra_ligada(car.get("motorista_id") or "")
    fase = "cd" if r.get("chegada") else ("rua" if r.get("saida") else "aguardando")
    itens = []
    for pid in pids:
        ped = E.ST.dados["pedidos"].get(pid) or {}
        ev = r["pedidos"].get(pid) or {}
        vz = ev.get("vizinho")
        des = _desfecho_de(car, pid)
        itens.append({"pid": pid, "numero": ped.get("numero"), "desfecho": des, "em": ev.get("em") or "",
                      "chegou": (ev.get("chegou") or {}).get("em") if ev.get("chegou") and not des else "",
                      "pecas": [{"desc": (E.ST.dados["produtos"].get(i["produto_id"]) or {}).get("nome", "Produto"), "qtd": i["qtd"]} for i in ped.get("itens") or []],
                      "palavra": (str(ped.get("palavra_chave") or "") if not vz else "") if exige and not des else "",
                      "vizinho": {k: vz.get(k) for k in ("nome", "tel", "numero", "em")} if vz else None, **dist_pedido(car, pid, pos)})
    pend = [x for x in itens if not x["desfecho"]]
    kms = [x["km"] for x in pend if x["km"] is not None]
    km = min(kms) if kms else None
    p0 = E.ST.dados["pedidos"].get(pids[0]) or {}
    end = p0.get("endereco") or {}
    c = cfg()
    # MAPA DO CLIENTE: só na rua, com entrega pendente e o caminhão DENTRO da faixa laranja (antes disso, só "a caminho")
    mapa = None
    perto = [x for x in pend if x["km"] is not None and not x["chegou"]]
    if fase == "rua" and c["mapa_cliente"] and perto and pos and min(x["km"] for x in perto) < c["km_laranja"]:
        alvo = min(perto, key=lambda x: x["km"])
        dest = destino(car, alvo["pid"])
        if dest:
            mapa = {"destino": {"lat": dest["lat"], "lng": dest["lng"]},
                    "motorista": {"lat": pos["lat"], "lng": pos["lng"], "aprox": bool(pos.get("aprox")), "rumo": rumo(car, pos)},
                    "dist_m": int(distancia_m(pos["lat"], pos["lng"], dest["lat"], dest["lng"]))}
    return {"km_laranja": c["km_laranja"], "km_vermelho": c["km_vermelho"], "mapa": mapa,"nome": str(p0.get("cliente_nome") or "").split(" ")[0].title(), "empresa": E.ST.config.get("empresa") or "",
            "endereco": ", ".join(x for x in (" ".join(y for y in (end.get("logradouro"), end.get("numero")) if y), end.get("complemento"), end.get("bairro"), end.get("cidade")) if x),
            "cep": end.get("cep") or "", "data": car.get("data"), "fase": fase, "exige_palavra": exige,
            "km": km if fase == "rua" else None, "km_cor": cor_km(km) if fase == "rua" else "", "km_aprox": bool(pos and pos.get("aprox")) and km is not None,
            "pos_ha_seg": pos.get("ha_seg") if pos and fase == "rua" else None, "pode_vizinho": bool(pend) and fase in ("aguardando", "rua"),
            "pedidos": itens, "servidor": agora()}


@router.get("/entrega/{token}", include_in_schema=False)
def pagina_entrega(token: str):
    return FileResponse(PASTA.parent / "entrega" / "index.html", media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache", "X-Robots-Tag": "noindex"})


@router.get("/api/entrega/{token}")
def api_entrega(token: str):
    with E.ST.trava:
        cid, car, pids = _carga_do_link(token)
        return entrega_pub(car, pids)


@router.post("/api/entrega/{token}/vizinho")
async def api_vizinho(token: str, request: Request):
    c = await request.json()
    with E.ST.trava:
        cid, car, pids = _carga_do_link(token)
        tx = E.Tx({"login": "cliente:link", "nome": "Cliente (link)"})
        car = tx.get("cargas", cid)
        r = rota(car)
        if r.get("chegada"):
            raise HTTPException(409, "Esta entrega já foi encerrada.")
        abertos = [pid for pid in pids if not _desfecho_de(car, pid)]
        if not abertos:
            raise HTTPException(409, "A entrega já foi registrada pelo motorista.")
        nome = re.sub(r"\s+", " ", str(c.get("nome") or "")).strip()[:60]
        tel = _dig(c.get("tel"))[:13]
        numero = re.sub(r"\s+", " ", str(c.get("numero") or "")).strip()[:30]
        for pid in abertos:
            ev = ev_de(car, pid)
            if c.get("cancelar"):
                if ev.pop("vizinho", None):
                    ev.setdefault("vizinho_hist", []).append({"cancelado": True, "em": agora()})
                continue
            if not numero:
                raise HTTPException(400, "Informe o número da casa (ou apartamento) do vizinho.")
            if len(ev.get("vizinho_hist") or []) >= 10:
                raise HTTPException(429, "Muitas alterações. Fale com a central de atendimento.")
            ev["vizinho"] = {"nome": nome, "tel": tel, "numero": numero, "em": agora()}
            ev.setdefault("vizinho_hist", []).append(dict(ev["vizinho"]))
        nums = ", ".join(f"#{(E.ST.dados['pedidos'].get(x) or {}).get('numero')}" for x in abertos)
        _hist(car, {"nome": "Cliente (link)"}, "cliente cancelou a entrega ao vizinho" if c.get("cancelar") else "cliente pediu entregar ao vizinho",
              f"pedido {nums}" + ("" if c.get("cancelar") else f" · nº {numero}{' · tel ' + tel if tel else ''} · {'com nome (vira a palavra)' if nome else 'SEM nome: sem palavra'}"))
        for pid in abertos:   # vira comentário no ticket aberto do cliente (Atendimento)
            ped = tx.get("pedidos", pid)
            E._hist(ped, {"login": "cliente"}, "Cliente cancelou a entrega ao vizinho (link)" if c.get("cancelar") else
                    f"Cliente pediu entregar ao vizinho (nº {numero})" + (" — sem palavra-chave" if not nome else ""))
            ped["atualizado_em"] = agora()
            tx.put("pedidos", pid, ped)
        _gravar(tx, cid, car)
        return entrega_pub({**E.ST.dados["cargas"][cid], "id": cid}, pids)


# ── para o app do cliente (/cliente/) mostrar o acompanhamento do pedido ──
def acompanhamento_do_pedido(pid: str) -> dict | None:
    ped = E.ST.dados["pedidos"].get(pid) or {}
    cid = ped.get("carga_id") or next((t.get("carga_id") for t in reversed(ped.get("tentativas") or []) if t.get("carga_id")), "")
    car = E.ST.dados["cargas"].get(cid or "")
    if not car or not liberada_para_app(car) and car.get("status") not in ("em_rota", "finalizada"):
        return None
    car = {**car, "id": cid}
    t = link_do_pedido(car, pid)
    pids = ((car.get("rota") or {}).get("links") or {}).get(t, {}).get("pids") or [pid]
    return {**entrega_pub(car, pids), "token": t}
