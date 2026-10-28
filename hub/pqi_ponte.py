"""
═══════════════════════════════════════════════════════════════════════════════
 pqi_ponte.py — PONTE HUB ⇄ PQI (Carteira de Encomendas)
───────────────────────────────────────────────────────────────────────────────
 A equipe continua trabalhando no PQI (pqi-c2tu.onrender.com). Aqui no hub, o
 módulo Carteira mostra e grava EXATAMENTE os mesmos dados, ao vivo — porque
 cada chamada da tela passa por esta ponte e é atendida pelo próprio PQI.

 Por que ponte e não ler o Firestore direto?
   O PQI guarda a Carteira em memória (para economizar a cota grátis) e só
   relê o banco quando reinicia. Se o hub gravasse direto no Firestore, o PQI
   não veria a mudança. Passando pelo PQI:
     · o que a equipe faz lá aparece aqui na hora, e vice-versa;
     · as regras são as dele (reserva "um por vez", conflito de versão,
       permissões por aba, esteira automática) — nada duplicado;
     · cada pessoa grava com o PRÓPRIO usuário do PQI (aparece o nome certo).

 Como cada pessoa conecta:
   Na 1ª vez, a tela pede o e-mail e a senha do PQI. O hub faz o login no PQI
   e guarda só o cookie de sessão (a senha NÃO é guardada). "Desconectar"
   encerra a sessão lá no PQI também.

 Render → Environment (opcional):
   PQI_URL = https://pqi-c2tu.onrender.com   (padrão)
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import os
import re
import threading
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

import acesso
import banco

PQI_URL = (os.environ.get("PQI_URL") or "https://pqi-c2tu.onrender.com").rstrip("/")
COOKIE_PQI = "pqi_sessao"
COL = "hub_pqi_sessoes"
MOD = "carteira"

router = APIRouter()
_cli = httpx.Client(timeout=httpx.Timeout(90.0, connect=30.0), follow_redirects=False,
                    headers={"User-Agent": "hub-wendleydesenvolvimento/ponte-pqi"})
_mem: dict[str, dict] = {}
_trava = threading.Lock()

# Só o que a Carteira usa passa pela ponte (nada de admin, segurança etc.)
_PERMITIDO = re.compile(r"^(carteira(/.*)?|auth/me|base/cadastros)$")


def _exigir(request: Request) -> dict:
    u = acesso.exigir_usuario(request)
    if not acesso.pode_acessar(u, MOD):
        raise HTTPException(403, "Sem acesso ao módulo Carteira.")
    return u


def _sessao(login: str) -> dict | None:
    with _trava:
        if login in _mem:
            return _mem[login]
    s = None
    if banco.configurado():
        try:
            snap = banco.db().collection(COL).document(login).get(timeout=banco.TIMEOUT)
            s = snap.to_dict() if snap.exists else None
        except Exception:  # noqa: BLE001
            s = None
    with _trava:
        _mem[login] = s
    return s


def _gravar(login: str, s: dict | None) -> None:
    with _trava:
        _mem[login] = s
    if not banco.configurado():
        return
    ref = banco.db().collection(COL).document(login)
    try:
        ref.set(s, timeout=banco.TIMEOUT) if s else ref.delete(timeout=banco.TIMEOUT)
    except Exception:  # noqa: BLE001
        pass


# ══════════════════════════════════════════════════════════════════════════════
# CONECTAR / STATUS / DESCONECTAR
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/api/pqi/status")
def status(request: Request):
    u = _exigir(request)
    s = _sessao(u["login"])
    return {"conectado": bool(s and s.get("cookie")), "email": (s or {}).get("email", ""), "nome": (s or {}).get("nome", ""),
            "desde": (s or {}).get("em", ""), "pqi_url": PQI_URL}


@router.post("/api/pqi/conectar")
async def conectar(request: Request):
    u = _exigir(request)
    c = await request.json()
    email, senha = str(c.get("email") or "").strip().lower(), str(c.get("senha") or "")
    if not email or not senha:
        raise HTTPException(400, "Informe o e-mail e a senha do PQI.")
    try:
        r = _cli.post(PQI_URL + "/api/auth/login", json={"email": email, "senha": senha, "lembrar": True})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"O PQI não respondeu ({e.__class__.__name__}). Ele pode estar acordando — tente de novo em 1 minuto.")
    if r.status_code != 200:
        try:
            msg = r.json().get("detail")
        except Exception:  # noqa: BLE001
            msg = None
        raise HTTPException(r.status_code if r.status_code in (401, 403, 429) else 502, msg or f"O PQI recusou o login (HTTP {r.status_code}).")
    cookie = r.cookies.get(COOKIE_PQI)
    if not cookie:
        raise HTTPException(502, "O PQI aceitou o login, mas não devolveu a sessão.")
    pub = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    s = {"cookie": cookie, "email": email, "nome": pub.get("nome") or email, "em": time.strftime("%Y-%m-%d %H:%M:%S"), "hub": u["login"]}
    _gravar(u["login"], s)
    return {"ok": True, "email": email, "nome": s["nome"]}


@router.post("/api/pqi/desconectar")
def desconectar(request: Request):
    u = _exigir(request)
    s = _sessao(u["login"])
    if s and s.get("cookie"):
        try:
            _cli.post(PQI_URL + "/api/auth/logout", cookies={COOKIE_PQI: s["cookie"]})
        except httpx.HTTPError:
            pass
    _gravar(u["login"], None)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# A PONTE — /pqi/api/<caminho> → PQI /api/<caminho>, com a sessão da pessoa
# ══════════════════════════════════════════════════════════════════════════════
@router.api_route("/pqi/api/{caminho:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def ponte(caminho: str, request: Request):
    u = _exigir(request)
    if not _PERMITIDO.match(caminho):
        raise HTTPException(404, "Endereço do PQI não liberado na ponte.")
    s = _sessao(u["login"])
    if not s or not s.get("cookie"):
        return JSONResponse({"detail": "pqi_desconectado"}, status_code=401)
    corpo = await request.body()
    cab = {"Content-Type": request.headers.get("content-type", "application/json")} if corpo else {}
    url = f"{PQI_URL}/api/{caminho}"
    if request.url.query:
        url += "?" + request.url.query

    def _chamar():
        return _cli.request(request.method, url, content=corpo or None, headers=cab, cookies={COOKIE_PQI: s["cookie"]})
    try:
        from starlette.concurrency import run_in_threadpool
        r = await run_in_threadpool(_chamar)
    except httpx.HTTPError as e:
        return JSONResponse({"detail": f"O PQI não respondeu ({e.__class__.__name__}). Ele pode estar acordando — tente de novo."}, status_code=502)
    if r.status_code == 401:
        _gravar(u["login"], None)   # sessão do PQI expirou ou foi derrubada → pede para conectar de novo
        return JSONResponse({"detail": "pqi_desconectado"}, status_code=401)
    novo = r.cookies.get(COOKIE_PQI)   # o PQI renovou o cookie (ex.: troca de senha)
    if novo and novo != s["cookie"]:
        _gravar(u["login"], {**s, "cookie": novo})
    return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type", "application/json"),
                    headers={"Cache-Control": "no-store"})
