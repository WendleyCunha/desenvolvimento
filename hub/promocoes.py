"""
hub/promocoes.py — DISPAROS NO APP DO CLIENTE (notificação no celular) + VALES COM QR CODE
─────────────────────────────────────────────────────────────────────────────
100% interno e grátis: Web Push do próprio navegador (chaves VAPID geradas e guardadas no banco),
sem WhatsApp, sem serviço pago.

  • O cliente, no app (/cliente/ › Vantagens), aceita receber "Avisos do meu pedido" e/ou "Promoções e cupons".
    Cada celular aceito vira uma inscrição. Só recebe quem instalou o app e aceitou (iPhone: app na tela de início).
  • Na Caixa do Atendimento, o ícone 📣 abre o disparo: quem recebe (todos com o app, ou os clientes marcados na
    Caixa) · o quê (Aviso, Promoção, Cupom %, Brinde) · revisar e enviar. Só o perfil Gestor dispara.
    Cupom acima do limite (Ajustes; padrão 50%) fica "aguardando aprovação" de OUTRO gestor.
  • Cupom e brinde viram um VALE por cliente: código próprio (não circula), validade, uso único, guardado na
    Carteira do app com QR code. O QR aponta para <hub>/v/<código>.
  • Validar em qualquer lugar (loja, site, venda na rua): o ícone ⌗ da Caixa abre a câmera e lê o QR (ou digita o
    código), ou a câmera do celular abre /v/<código> com o login do hub. Validar = marcar como usado, com quem,
    onde e quando. Usado não volta.

Banco (coleções próprias, poucas leituras — tudo com cache em memória):
  hub_push_inscricoes/<0-9A-Z>  inscrições, em 36 "gavetas" pela 1ª letra do código do cliente
  hub_carteira/<código>         vales de cada cliente (o app lê só a dele)
  hub_vales/<código do vale>    o vale (para validar pelo QR)
  hub_promocoes/disparos        índice dos últimos disparos (com resultados)
  hub_promocoes/vapid           chaves do Web Push (geradas sozinhas na 1ª vez)
"""
from __future__ import annotations

import base64
import copy
import json
import secrets
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

import acesso
import tickets as T

router = APIRouter()
PASTA = Path(__file__).parent / "static"
COL_INSC, COL_CART, COL_VALE, COL_CFG = "hub_push_inscricoes", "hub_carteira", "hub_vales", "hub_promocoes"
GAVETAS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TIPOS = {"aviso": "Aviso", "promocao": "Promoção", "cupom": "Cupom", "brinde": "Brinde"}
LIMITE_PADRAO = 50
MAX_DISPAROS = 200
_lock = threading.RLock()
_insc: dict[str, dict] | None = None      # código do cliente → {"subs": [...], "avisos": bool, "promocoes": bool, "nome": str}
_cart: dict[str, dict] = {}
_idx: dict | None = None
_vapid: dict | None = None


def db():
    return T.db()


def agora() -> str:
    return T.agora()


def _gaveta(cod: str) -> str:
    g = (cod or "?")[0].upper()
    return g if g in GAVETAS else "0"


# ── inscrições ────────────────────────────────────────────────────────────────
def inscricoes() -> dict:
    global _insc
    with _lock:
        if _insc is None:
            tudo = {}
            for g in GAVETAS:
                try:
                    snap = db().collection(COL_INSC).document(g).get(timeout=T.banco.TIMEOUT)
                    tudo.update((snap.to_dict() if snap.exists else None) or {})
                except Exception:
                    return {}   # banco fora: tenta de novo na próxima
            _insc = tudo
        return _insc


def _gravar_insc(cod: str, dado: dict | None):
    with _lock:
        tudo = inscricoes()
        if dado is None:
            tudo.pop(cod, None)
        else:
            tudo[cod] = dado
        g = _gaveta(cod)
        db().collection(COL_INSC).document(g).set({k: v for k, v in tudo.items() if _gaveta(k) == g}, timeout=T.banco.TIMEOUT)


# ── chaves VAPID (geradas uma vez, guardadas no banco) ───────────────────────
def vapid() -> dict:
    global _vapid
    with _lock:
        if _vapid:
            return _vapid
        ref = db().collection(COL_CFG).document("vapid")
        snap = ref.get(timeout=T.banco.TIMEOUT)
        d = snap.to_dict() if snap.exists else None
        if not d:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            chave = ec.generate_private_key(ec.SECP256R1())
            pem = chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
            pub = chave.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            d = {"privada_pem": pem, "publica": base64.urlsafe_b64encode(pub).rstrip(b"=").decode(), "criada_em": agora()}
            ref.set(d, timeout=T.banco.TIMEOUT)
        _vapid = d
        return d


def enviar_push(sub: dict, dados: dict) -> str:
    """'ok' · 'expirou' (o celular saiu: apagar a inscrição) · 'falhou'."""
    try:
        from py_vapid import Vapid01
        from pywebpush import WebPushException, webpush
    except Exception:
        return "falhou"
    try:
        webpush(subscription_info=sub, data=json.dumps(dados, ensure_ascii=False),
                vapid_private_key=Vapid01.from_pem(vapid()["privada_pem"].encode()),
                vapid_claims={"sub": "mailto:atendimento@kingstarcolchoes.com.br"}, ttl=86400 * 3, timeout=10)
        return "ok"
    except WebPushException as e:
        st = getattr(getattr(e, "response", None), "status_code", 0)
        return "expirou" if st in (404, 410) else "falhou"
    except Exception:
        return "falhou"


# ── carteira e vales ──────────────────────────────────────────────────────────
def carteira(cod: str) -> dict:
    with _lock:
        if cod not in _cart:
            snap = db().collection(COL_CART).document(cod).get(timeout=T.banco.TIMEOUT)
            _cart[cod] = (snap.to_dict() if snap.exists else None) or {"vales": []}
        return _cart[cod]


def _novo_codigo() -> str:
    alfa = "ACDEFGHJKMNPQRTUVWXY3479"   # sem letras/números que confundem (0/O, 1/I, 5/S…)
    c = "".join(secrets.choice(alfa) for _ in range(8))
    return c[:4] + "-" + c[4:]


def _vale_publico(v: dict) -> dict:
    hoje = datetime.now(T.BRT).strftime("%Y-%m-%d")
    st = "usado" if v.get("usado_em") else "vencido" if str(v.get("validade") or "9999") < hoje else "valido"
    return {k: v.get(k) for k in ("codigo", "tipo", "titulo", "beneficio", "percentual", "validade", "criado_em", "usado_em", "usado_local", "cliente_nome")} | {"status": st}


# ── disparos ──────────────────────────────────────────────────────────────────
def indice() -> dict:
    global _idx
    with _lock:
        if _idx is None:
            snap = db().collection(COL_CFG).document("disparos").get(timeout=T.banco.TIMEOUT)
            _idx = (snap.to_dict() if snap.exists else None) or {"lista": []}
        return _idx


def _gravar_indice():
    with _lock:
        _idx["lista"] = _idx["lista"][:MAX_DISPAROS]
        db().collection(COL_CFG).document("disparos").set(_idx, timeout=T.banco.TIMEOUT)


def _disparo(did: str) -> dict:
    d = next((x for x in indice()["lista"] if x["id"] == did), None)
    if not d:
        raise HTTPException(404, "Disparo não encontrado.")
    return d


def limite_aprovacao() -> int:
    try:
        return int(T.hub_cfg().get("promo_limite_aprovacao") or LIMITE_PADRAO)
    except Exception:
        return LIMITE_PADRAO


def _publico(publico: dict, categoria: str) -> tuple[list[str], dict]:
    """Quem recebe: códigos com celular inscrito que aceitam a categoria. Devolve também a conta para a tela."""
    ins = inscricoes()
    if publico.get("modo") == "codigos":
        alvo = [str(c).strip().upper() for c in publico.get("codigos") or [] if str(c).strip()]
    else:
        alvo = list(ins)
    alvo = list(dict.fromkeys(alvo))
    com_app = [c for c in alvo if c in ins and ins[c].get("subs")]
    aceitam = [c for c in com_app if ins[c].get(categoria, True)]
    return aceitam, {"escolhidos": len(alvo), "com_app": len(com_app), "aceitam": len(aceitam), "desligaram": len(com_app) - len(aceitam),
                     "sem_app": len(alvo) - len(com_app)}


def _executar(d: dict):
    """Cria os vales (cupom/brinde) e manda a notificação. Roda em segundo plano; vai gravando o resultado."""
    cat = "avisos" if d["tipo"] == "aviso" else "promocoes"
    cods, _ = _publico(d["publico"], cat)
    d.update(status="enviando", inicio_em=agora(), total=len(cods), enviados=0, falhas=0)
    _gravar_indice()
    ins = inscricoes()
    for i, cod in enumerate(cods):
        vale = None
        if d["tipo"] in ("cupom", "brinde"):
            vale = {"codigo": _novo_codigo(), "cliente": cod, "cliente_nome": ins.get(cod, {}).get("nome", ""), "disparo": d["id"],
                    "tipo": d["tipo"], "titulo": d["titulo"], "beneficio": d.get("beneficio", ""), "percentual": d.get("percentual"),
                    "validade": d.get("validade"), "criado_em": agora(), "usado_em": None}
            with _lock:
                db().collection(COL_VALE).document(vale["codigo"]).set(vale, timeout=T.banco.TIMEOUT)
                c = copy.deepcopy(carteira(cod))
                c["vales"] = ([vale] + c["vales"])[:100]
                db().collection(COL_CART).document(cod).set(c, timeout=T.banco.TIMEOUT)
                _cart[cod] = c
        dados = {"titulo": d["titulo"], "texto": d["texto"], "tag": d["id"],
                 "url": f"/cliente/?aba=vantagens&d={d['id']}" + (f"&v={vale['codigo']}" if vale else "")}
        ok, vivas = False, []
        for sub in ins.get(cod, {}).get("subs", []):
            r = enviar_push(sub, dados)
            ok = ok or r == "ok"
            if r != "expirou":
                vivas.append(sub)
        if len(vivas) != len(ins.get(cod, {}).get("subs", [])):
            _gravar_insc(cod, {**ins[cod], "subs": vivas} if vivas else None)
        d["enviados" if ok else "falhas"] += 1
        if i % 25 == 24:
            _gravar_indice()
    d.update(status="enviado", fim_em=agora())
    _gravar_indice()


def _disparar_em_fundo(d: dict):
    threading.Thread(target=_executar, args=(d,), daemon=True).start()


async def _json(request: Request) -> dict:
    """Corpo da requisição como dict (aceita também JSON enviado como texto, por segurança)."""
    try:
        c = await request.json()
        if isinstance(c, str):
            c = json.loads(c)
    except Exception:
        raise HTTPException(400, "Dados inválidos.")
    if not isinstance(c, dict):
        raise HTTPException(400, "Dados inválidos.")
    return c


def _gestor(request: Request):
    u, p, me = T._contexto(request)
    if me.get("perfil") != "gestor":
        raise HTTPException(403, "Só o perfil Gestor faz disparos no app.")
    return u, p, me


# ══════════════════════════════════════════════════════════════════════════════
# LADO DO CLIENTE (app)
# ══════════════════════════════════════════════════════════════════════════════
def _cliente(request: Request) -> tuple[str, dict]:
    import cliente_app as C
    pid, cli = C._cliente_da_sessao(request)
    return (cli.get("codigo") or pid).upper(), cli


@router.get("/api/cliente/push/chave")
def chave_publica():
    return {"publica": vapid()["publica"]}


@router.get("/api/cliente/vantagens")
def vantagens(request: Request):
    cod, cli = _cliente(request)
    i = inscricoes().get(cod) or {}
    vales = [_vale_publico(v) for v in carteira(cod).get("vales", [])]
    base = str(request.base_url).rstrip("/")
    for v in vales:
        v["qr"] = f"{base}/v/{v['codigo']}"
    return {"inscrito": bool(i.get("subs")), "avisos": i.get("avisos", True), "promocoes": i.get("promocoes", True), "vales": vales}


@router.post("/api/cliente/push")
async def inscrever(request: Request):
    """O celular aceitou: guarda a inscrição e as duas chaves (avisos / promoções)."""
    cod, cli = _cliente(request)
    c = await _json(request)
    sub = c.get("inscricao") or {}
    if not str(sub.get("endpoint") or "").startswith("https://") or not (sub.get("keys") or {}).get("p256dh"):
        raise HTTPException(400, "Inscrição inválida.")
    atual = copy.deepcopy(inscricoes().get(cod) or {"subs": []})
    subs = [s for s in atual.get("subs", []) if s.get("endpoint") != sub["endpoint"]] + [{"endpoint": sub["endpoint"], "keys": sub["keys"]}]
    atual.update(subs=subs[-5:], nome=cli.get("nome", ""), avisos=bool(c.get("avisos", True)), promocoes=bool(c.get("promocoes", True)), em=agora())
    _gravar_insc(cod, atual)
    return {"ok": True}


@router.post("/api/cliente/push/preferencias")
async def preferencias(request: Request):
    cod, cli = _cliente(request)
    c = await _json(request)
    atual = copy.deepcopy(inscricoes().get(cod))
    if not atual:
        raise HTTPException(409, "Ative as notificações neste celular primeiro.")
    for k in ("avisos", "promocoes"):
        if k in c:
            atual[k] = bool(c[k])
    _gravar_insc(cod, atual)
    return {"ok": True, "avisos": atual["avisos"], "promocoes": atual["promocoes"]}


@router.post("/api/cliente/push/aberto")
async def aberto(request: Request):
    """O cliente tocou na notificação (conta 'abertos' do disparo, uma vez por cliente)."""
    cod, cli = _cliente(request)
    did = str((await _json(request)).get("disparo") or "")
    with _lock:
        d = next((x for x in indice()["lista"] if x["id"] == did), None)
        if d and cod not in d.setdefault("abriram", []):
            d["abriram"].append(cod)
            d["abertos"] = len(d["abriram"])
            _gravar_indice()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# LADO DO HUB (Caixa › 📣 e ⌗)
# ══════════════════════════════════════════════════════════════════════════════
@router.post("/api/promo/publico")
async def contar_publico(request: Request):
    _gestor(request)
    c = await _json(request)
    cat = "avisos" if c.get("tipo") == "aviso" else "promocoes"
    _, conta = _publico(c.get("publico") or {}, cat)
    return conta | {"total_app": len(inscricoes()), "limite_aprovacao": limite_aprovacao()}


@router.get("/api/promo/disparos")
def listar(request: Request):
    u, p, me = _gestor(request)
    return {"disparos": [{k: v for k, v in d.items() if k != "abriram"} for d in indice()["lista"]], "eu": me["usuario"],
            "limite_aprovacao": limite_aprovacao(), "total_app": len(inscricoes())}


@router.post("/api/promo/disparos")
async def criar(request: Request):
    u, p, me = _gestor(request)
    c = await _json(request)
    tipo = str(c.get("tipo") or "")
    if tipo not in TIPOS:
        raise HTTPException(400, "Escolha o tipo: aviso, promoção, cupom ou brinde.")
    titulo, texto = str(c.get("titulo") or "").strip()[:60], str(c.get("texto") or "").strip()[:240]
    if not titulo or not texto:
        raise HTTPException(400, "Escreva o título e o texto da notificação.")
    d = {"id": "d" + datetime.now(T.BRT).strftime("%y%m%d%H%M%S") + secrets.token_hex(2), "tipo": tipo, "titulo": titulo, "texto": texto,
         "publico": {"modo": "codigos" if c.get("publico", {}).get("modo") == "codigos" else "todos",
                     "codigos": [str(x).strip().upper() for x in (c.get("publico") or {}).get("codigos") or []][:5000]},
         "criado_em": agora(), "criado_por": me["usuario"], "criado_por_nome": me["nome"], "status": "", "abertos": 0, "usados": 0}
    if tipo in ("cupom", "brinde"):
        validade = str(c.get("validade") or "")
        try:
            datetime.strptime(validade, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Informe a validade do vale.")
        if validade < datetime.now(T.BRT).strftime("%Y-%m-%d"):
            raise HTTPException(400, "A validade já passou.")
        d["validade"] = validade
        if tipo == "cupom":
            try:
                pct = int(c.get("percentual"))
            except (TypeError, ValueError):
                raise HTTPException(400, "Informe o desconto em %.")
            if not 1 <= pct <= 100:
                raise HTTPException(400, "Desconto entre 1% e 100%.")
            d.update(percentual=pct, beneficio=f"{pct}% de desconto" + (f" · {str(c.get('beneficio') or '').strip()[:80]}" if c.get("beneficio") else ""))
        else:
            d["beneficio"] = str(c.get("beneficio") or "").strip()[:120]
            if not d["beneficio"]:
                raise HTTPException(400, "Diga qual é o brinde.")
    cods, conta = _publico(d["publico"], "avisos" if tipo == "aviso" else "promocoes")
    if not cods:
        raise HTTPException(400, "Ninguém desse público tem o app com notificações aceitas.")
    d["previsto"] = conta["aceitam"]
    precisa = tipo == "cupom" and d["percentual"] > limite_aprovacao()
    d["status"] = "aguardando_aprovacao" if precisa else "na_fila"
    with _lock:
        indice()["lista"].insert(0, d)
        _gravar_indice()
    if not precisa:
        _disparar_em_fundo(d)
    return {"ok": True, "disparo": d}


@router.post("/api/promo/disparos/{did}/aprovar")
def aprovar(did: str, request: Request):
    u, p, me = _gestor(request)
    d = _disparo(did)
    if d["status"] != "aguardando_aprovacao":
        raise HTTPException(409, "Este disparo não está aguardando aprovação.")
    if d["criado_por"] == me["usuario"]:
        raise HTTPException(403, "A aprovação precisa ser de OUTRO gestor.")
    d.update(status="na_fila", aprovado_por=me["usuario"], aprovado_por_nome=me["nome"], aprovado_em=agora())
    _gravar_indice()
    _disparar_em_fundo(d)
    return {"ok": True}


@router.post("/api/promo/disparos/{did}/cancelar")
def cancelar(did: str, request: Request):
    u, p, me = _gestor(request)
    d = _disparo(did)
    if d["status"] != "aguardando_aprovacao":
        raise HTTPException(409, "Só dá para cancelar o que ainda não saiu.")
    d.update(status="cancelado", cancelado_por=me["usuario"], cancelado_em=agora())
    _gravar_indice()
    return {"ok": True}


def _ler_vale(cod: str) -> dict:
    cod = cod.strip().upper().replace(" ", "")
    if len(cod) == 8 and "-" not in cod:
        cod = cod[:4] + "-" + cod[4:]
    snap = db().collection(COL_VALE).document(cod).get(timeout=T.banco.TIMEOUT)
    if not snap.exists:
        raise HTTPException(404, "Vale não encontrado. Confira o código.")
    return snap.to_dict()


@router.get("/api/promo/vale/{cod}")
def ver_vale(cod: str, request: Request):
    acesso.exigir_usuario(request)   # qualquer pessoa logada no hub valida (loja, site, venda na rua)
    return _vale_publico(_ler_vale(cod))


@router.post("/api/promo/vale/{cod}/usar")
async def usar_vale(cod: str, request: Request):
    u = acesso.exigir_usuario(request)
    local = str((await _json(request)).get("local") or "").strip()[:80]
    with _lock:
        v = _ler_vale(cod)
        pub = _vale_publico(v)
        if pub["status"] == "usado":
            raise HTTPException(409, f"Este vale JÁ FOI USADO em {v.get('usado_em', '')[:16]} ({v.get('usado_local') or 'sem local'}).")
        if pub["status"] == "vencido":
            raise HTTPException(409, f"Vale vencido em {v.get('validade')}.")
        v.update(usado_em=agora(), usado_por=u.get("login"), usado_por_nome=u.get("nome"), usado_local=local)
        db().collection(COL_VALE).document(v["codigo"]).set(v, timeout=T.banco.TIMEOUT)
        c = copy.deepcopy(carteira(v["cliente"]))
        c["vales"] = [v if x.get("codigo") == v["codigo"] else x for x in c.get("vales", [])]
        db().collection(COL_CART).document(v["cliente"]).set(c, timeout=T.banco.TIMEOUT)
        _cart[v["cliente"]] = c
        d = next((x for x in indice()["lista"] if x["id"] == v.get("disparo")), None)
        if d:
            d["usados"] = d.get("usados", 0) + 1
            _gravar_indice()
    return {"ok": True, "vale": _vale_publico(v)}


@router.get("/v/{cod}", include_in_schema=False)
def pagina_vale(cod: str):
    """O QR code do vale abre aqui (câmera do celular): página de validação com o login do hub."""
    return FileResponse(PASTA / "vale.html", headers={"Cache-Control": "no-store"})
