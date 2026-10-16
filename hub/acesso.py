"""
hub/acesso.py — login, sessões, usuários e permissões do hub.
─────────────────────────────────────────────────────────────────────────────
MODELO DE PERMISSÃO (validado AQUI no servidor — não só escondido na tela)

  Cada módulo declara no próprio HTML o que pode ser controlado:
      <script type="application/json" id="hub-permissoes">
        { "acoes":  {"acessar":"Abrir", "incluir":"Criar", "editar":"Editar", ...},
          "campos": {"titulo":"Título", "prioridade":"Prioridade", ...},
          "regras": {"concluir": {"campos":["status","concluido_em"], "cria":true}},
          "padroes":{"prioridade":"P3"} }
      </script>

  Cada usuário guarda, por módulo:
      modulos.<slug>.acoes.<acao>   = true | false          (padrão: false)
      modulos.<slug>.campos.<campo> = "editar"|"ver"|"oculto" (padrão: "editar")

  Administrador = acesso total a tudo, sempre.

ADMIN DE FÁBRICA (para o primeiro acesso e para nunca ficar trancado de fora)
  Render → Environment:  HUB_ADMIN_USUARIO = wendley
                          HUB_ADMIN_SENHA   = <uma senha forte>
  Ele não fica gravado no banco; vale enquanto essas variáveis existirem.

SESSÃO
  Cookie assinado (HMAC-SHA256). Configure HUB_SEGREDO no Render com um texto
  longo e aleatório — sem ele as sessões caem toda vez que o Render reinicia.
  Trocar a senha, desativar ou excluir o usuário derruba as sessões dele.

USUÁRIOS no Firestore: coleção "hub_usuarios" (documento = login).
Senhas guardadas só como hash PBKDF2-SHA256 (200 mil iterações + sal).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import banco

COOKIE = "hub_sessao"
COLECAO = "hub_usuarios"
NIVEIS_CAMPO = ("editar", "ver", "oculto")
LOGIN_OK = re.compile(r"^[a-z0-9][a-z0-9._-]{1,39}$")

SEGREDO = os.environ.get("HUB_SEGREDO", "").strip()
SEGREDO_TEMPORARIO = not SEGREDO
if not SEGREDO:
    SEGREDO = secrets.token_hex(32)

ADMIN_FAB_LOGIN = os.environ.get("HUB_ADMIN_USUARIO", "").strip().lower()
ADMIN_FAB_SENHA = os.environ.get("HUB_ADMIN_SENHA", "")

# main.py preenche estas duas funções (evita import circular)
obter_esquema: Callable[[str], dict | None] = lambda slug: None
listar_modulos: Callable[[], list[dict]] = lambda: []

ESQUEMA_PADRAO = {"acoes": {"acessar": "Abrir o módulo"}, "campos": {}, "regras": {}, "padroes": {}}


# ══════════════════════════════════════════════════════════════════════════════
# SENHAS
# ══════════════════════════════════════════════════════════════════════════════
def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    it = 200_000
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, it)
    return f"pbkdf2${it}${sal.hex()}${h.hex()}"


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        _, it, sal, h = guardado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), int(it))
        return hmac.compare_digest(calc.hex(), h)
    except Exception:  # noqa: BLE001
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN DE SESSÃO (cookie assinado)
# ══════════════════════════════════════════════════════════════════════════════
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _assinar(texto: str) -> str:
    return hmac.new(SEGREDO.encode(), texto.encode(), hashlib.sha256).hexdigest()


def gerar_token(login: str, versao: int, dias: float, fabrica: bool = False) -> str:
    corpo = _b64(json.dumps({"u": login, "v": versao, "f": int(fabrica), "e": int(time.time() + dias * 86400)}).encode())
    return corpo + "." + _assinar(corpo)


def ler_token(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    corpo, assinatura = token.rsplit(".", 1)
    if not hmac.compare_digest(_assinar(corpo), assinatura):
        return None
    try:
        d = json.loads(_unb64(corpo))
    except Exception:  # noqa: BLE001
        return None
    if d.get("e", 0) < time.time():
        return None
    return d


# ══════════════════════════════════════════════════════════════════════════════
# USUÁRIOS — cache em memória (o hub é a única porta de escrita nesta coleção,
# então o cache fica válido e economiza leituras da cota grátis do Firestore)
# ══════════════════════════════════════════════════════════════════════════════
class _Usuarios:
    def __init__(self) -> None:
        self._cache: dict[str, dict] | None = None
        self._trava = threading.Lock()

    def _col(self):
        return banco.db().collection(COLECAO)

    def todos(self) -> dict[str, dict]:
        if not banco.configurado():
            return {}
        with self._trava:
            if self._cache is None:
                self._cache = {d.id: (d.to_dict() or {}) for d in self._col().stream(timeout=banco.TIMEOUT)}
            return self._cache

    def obter(self, login: str) -> dict | None:
        return self.todos().get(login)

    def salvar(self, login: str, dados: dict) -> None:
        self._col().document(login).set(dados, timeout=banco.TIMEOUT)
        self.todos()[login] = dados

    def excluir(self, login: str) -> None:
        self._col().document(login).delete(timeout=banco.TIMEOUT)
        self.todos().pop(login, None)


USUARIOS = _Usuarios()


def _fabrica() -> dict:
    return {"login": ADMIN_FAB_LOGIN, "nome": "Administrador", "admin": True, "ativo": True,
            "fabrica": True, "versao_sessao": 0, "modulos": {}, "preferencias": {}}


def usuario_da_requisicao(request: Request) -> dict | None:
    d = ler_token(request.cookies.get(COOKIE))
    if not d:
        return None
    login = d.get("u", "")
    if d.get("f"):
        return _fabrica() if ADMIN_FAB_LOGIN and login == ADMIN_FAB_LOGIN else None
    try:
        u = USUARIOS.obter(login)
    except Exception:  # noqa: BLE001
        return None
    if not u or not u.get("ativo", True) or int(u.get("versao_sessao", 0)) != int(d.get("v", -1)):
        return None
    return {**u, "login": login}


def publico(u: dict) -> dict:
    return {
        "login": u.get("login"), "nome": u.get("nome") or u.get("login"),
        "admin": bool(u.get("admin")), "ativo": bool(u.get("ativo", True)),
        "fabrica": bool(u.get("fabrica")), "modulos": u.get("modulos") or {},
        "criado_em": u.get("criado_em", ""), "atualizado_em": u.get("atualizado_em", ""),
        "ultimo_acesso": u.get("ultimo_acesso", ""),
    }


def normalizar_esquema(e: dict | None) -> dict:
    e = e or {}
    acoes = dict(e.get("acoes") or {})
    acoes.setdefault("acessar", "Abrir o módulo")
    acoes = {"acessar": acoes.pop("acessar"), **acoes}
    return {"acoes": acoes, "campos": dict(e.get("campos") or {}),
            "regras": dict(e.get("regras") or {}), "padroes": dict(e.get("padroes") or {})}


def permissoes(u: dict, slug: str, esquema: dict) -> dict:
    """Permissões efetivas do usuário num módulo."""
    if u.get("admin"):
        return {"acoes": {a: True for a in esquema["acoes"]}, "campos": {c: "editar" for c in esquema["campos"]}}
    p = (u.get("modulos") or {}).get(slug) or {}
    pa, pc = p.get("acoes") or {}, p.get("campos") or {}
    acoes = {a: bool(pa.get(a, False)) for a in esquema["acoes"]}
    if not acoes.get("acessar"):
        acoes = {a: False for a in acoes}
    campos = {c: (pc.get(c) if pc.get(c) in NIVEIS_CAMPO else "editar") for c in esquema["campos"]}
    return {"acoes": acoes, "campos": campos}


def pode_acessar(u: dict | None, slug: str) -> bool:
    if not u:
        return False
    if u.get("admin"):
        return True
    return bool(((u.get("modulos") or {}).get(slug) or {}).get("acoes", {}).get("acessar"))


def exigir_usuario(request: Request) -> dict:
    u = usuario_da_requisicao(request)
    if not u:
        raise HTTPException(401, "Faça login.")
    return u


def exigir_admin(request: Request) -> dict:
    u = exigir_usuario(request)
    if not u.get("admin"):
        raise HTTPException(403, "Somente administradores.")
    return u


def _exigir_banco():
    if not banco.configurado():
        raise HTTPException(503, "Configure FIRESTORE_CREDS no Render para salvar usuários.")


def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _limpar_modulos(m: dict | None) -> dict:
    """Aceita só o formato esperado: {slug: {acoes:{a:bool}, campos:{c:nivel}}}."""
    saida = {}
    for slug, p in (m or {}).items():
        if not isinstance(p, dict) or not re.match(r"^[a-z0-9][a-z0-9_-]{0,60}$", str(slug)):
            continue
        acoes = {str(a): bool(v) for a, v in (p.get("acoes") or {}).items()}
        campos = {str(c): v for c, v in (p.get("campos") or {}).items() if v in NIVEIS_CAMPO}
        saida[slug] = {"acoes": acoes, "campos": campos}
    return saida


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════════════════════════
router = APIRouter()
_falhas: dict[str, list[float]] = {}  # ip → [qtd, bloqueado_ate]


def _https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"


@router.post("/api/auth/entrar")
async def entrar(request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    qtd, ate = _falhas.get(ip, [0, 0])
    if ate > time.time():
        raise HTTPException(429, f"Muitas tentativas. Tente de novo em {int(ate - time.time()) // 60 + 1} min.")
    corpo = await request.json()
    login = str(corpo.get("login", "")).strip().lower()
    senha = str(corpo.get("senha", ""))
    lembrar = bool(corpo.get("lembrar"))

    ok_user, fabrica, versao = None, False, 0
    if ADMIN_FAB_LOGIN and ADMIN_FAB_SENHA and login == ADMIN_FAB_LOGIN and hmac.compare_digest(senha, ADMIN_FAB_SENHA):
        ok_user, fabrica = _fabrica(), True
    else:
        try:
            u = USUARIOS.obter(login)
        except Exception:  # noqa: BLE001
            u = None
        if u and u.get("ativo", True) and conferir_senha(senha, u.get("senha_hash", "")):
            ok_user, versao = {**u, "login": login}, int(u.get("versao_sessao", 0))
            try:
                USUARIOS.salvar(login, {**u, "ultimo_acesso": _agora()})
            except Exception:  # noqa: BLE001
                pass

    if not ok_user:
        qtd += 1
        # 6 erros seguidos → bloqueia este IP por 5 minutos
        _falhas[ip] = [0, time.time() + 300] if qtd >= 6 else [qtd, 0]
        raise HTTPException(401, "Usuário ou senha incorretos.")

    _falhas.pop(ip, None)
    dias = 30 if lembrar else 0.5
    resp = JSONResponse({"ok": True, "usuario": publico(ok_user)})
    resp.set_cookie(COOKIE, gerar_token(login, versao, dias, fabrica), httponly=True, samesite="lax",
                    secure=_https(request), max_age=int(dias * 86400) if lembrar else None, path="/")
    return resp


@router.post("/api/auth/sair")
def sair():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@router.get("/api/eu")
def eu(request: Request, modulo: str = ""):
    u = exigir_usuario(request)
    saida = {"usuario": publico(u), "preferencias": u.get("preferencias") or {}, "banco": banco.configurado()}
    if modulo:
        esq = obter_esquema(modulo)
        if esq is None:
            raise HTTPException(404, "Módulo não encontrado.")
        saida["esquema"] = esq
        saida["perm"] = permissoes(u, modulo, esq)
    return saida


@router.post("/api/eu/senha")
async def trocar_senha(request: Request):
    u = exigir_usuario(request)
    if u.get("fabrica"):
        raise HTTPException(400, "A senha do administrador de fábrica é a variável HUB_ADMIN_SENHA do Render.")
    corpo = await request.json()
    if not conferir_senha(str(corpo.get("atual", "")), u.get("senha_hash", "")):
        raise HTTPException(400, "Senha atual incorreta.")
    nova = str(corpo.get("nova", ""))
    if len(nova) < 6:
        raise HTTPException(400, "A nova senha precisa de pelo menos 6 caracteres.")
    dados = {k: v for k, v in u.items() if k != "login"}
    dados.update(senha_hash=hash_senha(nova), versao_sessao=int(u.get("versao_sessao", 0)) + 1, atualizado_em=_agora())
    USUARIOS.salvar(u["login"], dados)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, gerar_token(u["login"], dados["versao_sessao"], 0.5), httponly=True, samesite="lax",
                    secure=_https(request), path="/")
    return resp


@router.put("/api/eu/preferencias")
async def salvar_preferencias(request: Request):
    u = exigir_usuario(request)
    corpo = await request.json()
    if u.get("fabrica") or not banco.configurado():
        return {"ok": True, "salvo": "navegador"}
    prefs = {**(u.get("preferencias") or {}), **{k: v for k, v in corpo.items() if k in ("tema",)}}
    if len(json.dumps(prefs)) > 8000:
        raise HTTPException(400, "Preferências grandes demais.")
    dados = {k: v for k, v in u.items() if k != "login"}
    dados["preferencias"] = prefs
    USUARIOS.salvar(u["login"], dados)
    return {"ok": True, "salvo": "conta"}


# ── administração ────────────────────────────────────────────────────────────
@router.get("/api/admin/usuarios")
def admin_listar(request: Request):
    exigir_admin(request)
    usuarios = [] if not banco.configurado() else [publico({**u, "login": k}) for k, u in sorted(USUARIOS.todos().items())]
    return {"usuarios": usuarios, "modulos": listar_modulos(), "banco": banco.configurado(),
            "admin_fabrica": ADMIN_FAB_LOGIN or None}


@router.post("/api/admin/usuarios")
async def admin_criar(request: Request):
    exigir_admin(request)
    _exigir_banco()
    c = await request.json()
    login = str(c.get("login", "")).strip().lower()
    if not LOGIN_OK.match(login):
        raise HTTPException(400, "Login inválido: use 2 a 40 letras minúsculas, números, ponto, - ou _.")
    if login == ADMIN_FAB_LOGIN or USUARIOS.obter(login):
        raise HTTPException(409, "Já existe um usuário com esse login.")
    senha = str(c.get("senha", ""))
    if len(senha) < 6:
        raise HTTPException(400, "A senha precisa de pelo menos 6 caracteres.")
    dados = {"nome": str(c.get("nome", "")).strip() or login, "senha_hash": hash_senha(senha),
             "admin": bool(c.get("admin")), "ativo": bool(c.get("ativo", True)), "versao_sessao": 0,
             "modulos": _limpar_modulos(c.get("modulos")), "preferencias": {}, "criado_em": _agora(), "atualizado_em": _agora()}
    USUARIOS.salvar(login, dados)
    return {"ok": True, "usuario": publico({**dados, "login": login})}


@router.put("/api/admin/usuarios/{login}")
async def admin_editar(login: str, request: Request):
    eu_ = exigir_admin(request)
    _exigir_banco()
    atual = USUARIOS.obter(login)
    if not atual:
        raise HTTPException(404, "Usuário não encontrado.")
    c = await request.json()
    dados = dict(atual)
    derrubar = False
    if "nome" in c:
        dados["nome"] = str(c["nome"]).strip() or login
    if "admin" in c:
        if login == eu_.get("login") and not c["admin"]:
            raise HTTPException(400, "Você não pode tirar o seu próprio acesso de administrador.")
        dados["admin"] = bool(c["admin"])
    if "ativo" in c:
        if login == eu_.get("login") and not c["ativo"]:
            raise HTTPException(400, "Você não pode desativar a si mesmo.")
        derrubar |= dados.get("ativo", True) and not c["ativo"]
        dados["ativo"] = bool(c["ativo"])
    if c.get("senha"):
        if len(str(c["senha"])) < 6:
            raise HTTPException(400, "A senha precisa de pelo menos 6 caracteres.")
        dados["senha_hash"] = hash_senha(str(c["senha"]))
        derrubar = True
    if "modulos" in c:
        dados["modulos"] = _limpar_modulos(c["modulos"])
    if derrubar:
        dados["versao_sessao"] = int(dados.get("versao_sessao", 0)) + 1
    dados["atualizado_em"] = _agora()
    USUARIOS.salvar(login, dados)
    return {"ok": True, "usuario": publico({**dados, "login": login})}


@router.delete("/api/admin/usuarios/{login}")
def admin_excluir(login: str, request: Request):
    eu_ = exigir_admin(request)
    _exigir_banco()
    if login == eu_.get("login"):
        raise HTTPException(400, "Você não pode excluir a si mesmo.")
    if not USUARIOS.obter(login):
        raise HTTPException(404, "Usuário não encontrado.")
    USUARIOS.excluir(login)
    return {"ok": True}


@router.put("/api/admin/permissao")
async def admin_permissao(request: Request):
    """Ajusta UMA ação ou UM campo de um módulo, para vários usuários de uma vez.
    Corpo: {modulo, tipo:"acao"|"campo", chave, valores:{login: true|false|"editar"|"ver"|"oculto"}}"""
    exigir_admin(request)
    _exigir_banco()
    c = await request.json()
    modulo, tipo, chave = str(c.get("modulo", "")), c.get("tipo"), str(c.get("chave", ""))
    if obter_esquema(modulo) is None or tipo not in ("acao", "campo") or not chave:
        raise HTTPException(400, "Pedido inválido.")
    alterados = 0
    for login, valor in (c.get("valores") or {}).items():
        u = USUARIOS.obter(login)
        if not u:
            continue
        mods = _limpar_modulos(u.get("modulos"))
        p = mods.setdefault(modulo, {"acoes": {}, "campos": {}})
        if tipo == "acao":
            p["acoes"][chave] = bool(valor)
        else:
            if valor not in NIVEIS_CAMPO:
                continue
            p["campos"][chave] = valor
        USUARIOS.salvar(login, {**u, "modulos": mods, "atualizado_em": _agora()})
        alterados += 1
    return {"ok": True, "alterados": alterados}
