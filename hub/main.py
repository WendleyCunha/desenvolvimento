"""
hub/main.py — Hub Wendley Desenvolvimento (Menu Túnel)
─────────────────────────────────────────────────────────────────────────────
Casca em FastAPI que roda no Render (plano Free) e serve:

    /                 → home.html (o "túnel": menu lateral + abas + iframes)
    /api/modulos      → catálogo de tudo que aparece no menu
    /m/<slug>         → um módulo HTML descoberto automaticamente
    /m/<slug>/<arq>   → arquivos auxiliares de um módulo em pasta (css, js, img)
    /login            → tela de entrada (todo o resto exige login)
    /configuracoes    → engrenagem: aparência, usuários e permissões, conta
    /api/auth/*  /api/eu  /api/admin/*   → acesso.py (login, usuários, permissões)
    /api/dados/<modulo>/<colecao>        → dados.py  (dados com permissão por campo)
    /healthz          → health check do Render (obrigatório)
    /api/diag         → diagnóstico (Firestore conecta? quantos módulos?)

O main.py da RAIZ do repo (Streamlit) NÃO é usado nem tocado por este serviço.
Ele continua no Streamlit Cloud e aparece aqui dentro como um "sistema
externo" (iframe). O Render roda SÓ esta pasta (Root Directory = hub).

COMO ADICIONAR UM MÓDULO NOVO (sem mexer neste arquivo):
    Opção A — arquivo único:   hub/modulos/painel-do-dia.html
    Opção B — pasta própria:   hub/modulos/medidas/index.html  (+ css/js/img)

    O nome do arquivo/pasta vira o endereço: /m/painel-do-dia
    (use só letras minúsculas, números, "-" ou "_").

    No <head> do módulo, opcionalmente:
        <title>Painel do Dia</title>
        <meta name="hub-icone"     content="grafico">   ← nome de ícone ou emoji
        <meta name="hub-cor"       content="#22d3ee">   ← cor do brilho (opcional)
        <meta name="hub-grupo"     content="Operacional">
        <meta name="hub-ordem"     content="10">
        <meta name="hub-descricao" content="Tudo que vence hoje">
        <meta name="hub-oculto"    content="1">   ← não aparece no menu

    Permissões controláveis (aparecem em Configurações → Usuários):
        <script type="application/json" id="hub-permissoes">
          {"acoes":{"acessar":"Abrir","incluir":"Criar","editar":"Editar","excluir":"Excluir"},
           "campos":{"titulo":"Título","valor":"Valor"}}
        </script>

Render — configuração do Web Service:
    Root Directory : hub
    Build Command  : pip install -r requirements.txt
    Start Command  : uvicorn main:app --host 0.0.0.0 --port $PORT
    Instance Type  : Free
    Health Check   : /healthz
    Env vars       : HUB_ADMIN_USUARIO  = seu login de administrador de fábrica
                     HUB_ADMIN_SENHA    = a senha dele (forte!)
                     HUB_SEGREDO        = texto longo e aleatório (assina as sessões)
                     FIRESTORE_CREDS    = JSON cru da service account (usuários e dados)
                     LILA_STREAMLIT_URL = https://<seu-app>.streamlit.app/
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from html.parser import HTMLParser
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import acesso
import banco
import dados

VERSAO = "3.0.1"

BASE = Path(__file__).resolve().parent
PASTA_MODULOS = BASE / "modulos"
# aceita hub/static/home.html (preferido) ou hub/home.html
HOME_CANDIDATOS = [BASE / "static" / "home.html", BASE / "home.html"]


def _home_html() -> Path | None:
    return next((p for p in HOME_CANDIDATOS if p.is_file()), None)

SLUG_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")
SEM_CACHE = {"Cache-Control": "no-cache, must-revalidate"}

# ══════════════════════════════════════════════════════════════════════════════
# SISTEMAS EXTERNOS — abertos por URL dentro do túnel (iframe)
# Para trocar sem mexer no código: env var SISTEMAS_EXTERNOS_JSON com uma lista
# no mesmo formato abaixo.
# ══════════════════════════════════════════════════════════════════════════════
SISTEMAS_EXTERNOS_PADRAO = [
    {
        "id": "lila-closet",
        "titulo": "Lila Closet Atelier",
        "icone": "tesoura",
        "cor": "#fb7185",
        "grupo": "Sistemas",
        "ordem": 50,
        "descricao": "Gestão do atelier (Streamlit Cloud).",
        "url": os.environ.get("LILA_STREAMLIT_URL", ""),
    },
]


def _com_embed(url: str) -> str:
    """Apps do Streamlit Cloud abrem sem a barra/menu do Streamlit quando
    recebem ?embed=true — colocado aqui para não depender da env var."""
    if ".streamlit.app" in url and "embed=" not in url:
        url += ("&" if "?" in url else "?") + "embed=true"
    return url


def sistemas_externos() -> list[dict]:
    bruto = os.environ.get("SISTEMAS_EXTERNOS_JSON", "").strip()
    lista = SISTEMAS_EXTERNOS_PADRAO
    if bruto:
        try:
            lista = json.loads(bruto)
        except json.JSONDecodeError:
            print("[hub] SISTEMAS_EXTERNOS_JSON inválido — usando o padrão.")
    saida = []
    for s in lista:
        if not s.get("id") or not s.get("url"):
            continue  # sem URL configurada → não aparece no menu
        s = {**s, "url": _com_embed(s["url"])}
        saida.append({
            "id": str(s["id"]),
            "titulo": s.get("titulo") or s["id"],
            "icone": s.get("icone") or "globo",
            "cor": s.get("cor") or "",
            "grupo": s.get("grupo") or "Sistemas",
            "ordem": int(s.get("ordem", 0)),
            "descricao": s.get("descricao") or "",
            "url": s["url"],
            "tipo": "externo",
        })
    return saida


# ══════════════════════════════════════════════════════════════════════════════
# DESCOBERTA AUTOMÁTICA DE MÓDULOS HTML
# ══════════════════════════════════════════════════════════════════════════════
class _LeitorMeta(HTMLParser):
    """Lê só <title> e <meta name="hub-*"> do começo do arquivo."""

    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.titulo = ""
        self.permissoes = ""
        self._no_title = False
        self._no_perm = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._no_title = True
        elif tag == "script" and a.get("id") == "hub-permissoes":
            self._no_perm = True
        elif tag == "meta":
            nome = (a.get("name") or "").lower()
            if nome.startswith("hub-"):
                self.meta[nome[4:]] = (a.get("content") or "").strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._no_title = False
        elif tag == "script":
            self._no_perm = False

    def handle_data(self, data):
        if self._no_title:
            self.titulo += data
        elif self._no_perm:
            self.permissoes += data


def _ler_metadados(arquivo: Path) -> dict:
    leitor = _LeitorMeta()
    try:
        with arquivo.open("r", encoding="utf-8", errors="ignore") as f:
            leitor.feed(f.read(64_000))  # o <head> basta
    except OSError:
        pass
    esquema = None
    if leitor.permissoes.strip():
        try:
            esquema = json.loads(leitor.permissoes)
        except json.JSONDecodeError:
            print(f"[hub] JSON de permissões inválido em {arquivo.name} — usando só 'acessar'.")
    return {"titulo": leitor.titulo.strip(), **leitor.meta, "_esquema": esquema}


def _arquivo_do_modulo(slug: str) -> Path | None:
    if not SLUG_OK.match(slug):
        return None
    unico = PASTA_MODULOS / f"{slug}.html"
    if unico.is_file():
        return unico
    em_pasta = PASTA_MODULOS / slug / "index.html"
    if em_pasta.is_file():
        return em_pasta
    return None


def modulos_internos() -> list[dict]:
    if not PASTA_MODULOS.is_dir():
        return []
    vistos: dict[str, Path] = {}
    for p in sorted(PASTA_MODULOS.iterdir()):
        if p.name.startswith((".", "_")):
            continue
        if p.is_file() and p.suffix.lower() == ".html":
            slug = p.stem
        elif p.is_dir() and (p / "index.html").is_file():
            slug = p.name
        else:
            continue
        if not SLUG_OK.match(slug):
            print(f"[hub] ignorado '{p.name}': use só minúsculas, números, '-' ou '_'.")
            continue
        vistos.setdefault(slug, _arquivo_do_modulo(slug))

    saida = []
    for slug, arq in vistos.items():
        if arq is None:
            continue
        m = _ler_metadados(arq)
        if m.get("oculto") in ("1", "true", "sim"):
            continue
        try:
            ordem = int(m.get("ordem", 100))
        except ValueError:
            ordem = 100
        saida.append({
            "id": slug,
            "titulo": m.get("titulo") or slug.replace("-", " ").replace("_", " ").title(),
            "icone": m.get("icone") or "documento",
            "cor": m.get("cor") or "",
            "grupo": m.get("grupo") or "Módulos",
            "ordem": ordem,
            "descricao": m.get("descricao") or "",
            "url": f"/m/{slug}",
            "tipo": "interno",
            "_esquema": m.get("_esquema"),
        })
    return saida


# ══════════════════════════════════════════════════════════════════════════════
# FIRESTORE — criado sob demanda (NUNCA no import: no PQI isso travava o gRPC)
# ══════════════════════════════════════════════════════════════════════════════
db = banco.db  # conexão única (banco.py)


# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO + ESQUEMAS DE PERMISSÃO
# ══════════════════════════════════════════════════════════════════════════════
def catalogo() -> list[dict]:
    itens = sistemas_externos() + modulos_internos()
    itens.sort(key=lambda i: (i["ordem"], i["titulo"].lower()))
    return itens


def esquema_do_modulo(slug: str) -> dict | None:
    for i in catalogo():
        if i["id"] == slug:
            return acesso.normalizar_esquema(i.get("_esquema"))
    return None


def modulos_com_esquema() -> list[dict]:
    return [{k: v for k, v in i.items() if k != "_esquema"} | {"esquema": acesso.normalizar_esquema(i.get("_esquema"))}
            for i in catalogo()]


acesso.obter_esquema = esquema_do_modulo
acesso.listar_modulos = modulos_com_esquema


def _pagina(nome: str) -> FileResponse:
    arq = BASE / "static" / nome
    if not arq.is_file():
        raise HTTPException(500, f"static/{nome} não encontrado")
    return FileResponse(arq, media_type="text/html", headers=SEM_CACHE)


def _ir_para_login(request: Request) -> RedirectResponse:
    from urllib.parse import quote
    return RedirectResponse("/login?volta=" + quote(request.url.path), status_code=303)


_SEM_ACESSO = """<!doctype html><meta charset="utf-8"><title>Sem acesso</title>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#05060a;color:#eef0f5;font:15px Inter,system-ui,sans-serif">
<div style="text-align:center;max-width:380px;padding:24px"><div style="font-size:2.4rem">🔒</div>
<h2 style="font-weight:600;margin:10px 0 6px">Sem acesso a este módulo</h2>
<p style="color:#a3a9b8;line-height:1.6">Peça ao administrador para liberar o acesso em Configurações → Usuários.</p></div>"""


# ══════════════════════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════════════════════
app = FastAPI(title="Wendley Desenvolvimento", version=VERSAO, docs_url=None, redoc_url=None)


@app.exception_handler(Exception)
async def _erro_inesperado(request: Request, exc: Exception):
    """Em vez de um "HTTP 500" mudo, devolve o motivo — aparece na tela e no log do Render."""
    import traceback
    traceback.print_exc()
    if isinstance(exc, banco.SemBanco):
        return JSONResponse({"detail": str(exc)}, status_code=503)
    nome = type(exc).__name__
    msg = str(exc).split("\n")[0][:300]
    dica = ""
    if "Permission" in nome or "403" in msg:
        dica = " — a service account não tem permissão no Firestore (papel 'Cloud Datastore User')."
    elif "Deadline" in nome or "Timeout" in nome:
        dica = " — o Firestore demorou a responder; tente de novo em alguns segundos."
    elif "NotFound" in nome:
        dica = " — o banco Firestore não existe nesse projeto (crie em Firebase → Firestore Database)."
    return JSONResponse({"detail": f"Erro no servidor: {nome}: {msg}{dica}"}, status_code=500)
app.include_router(acesso.router)
app.include_router(dados.router)
_inicio = time.time()


@app.get("/healthz")
@app.get("/_stcore/health")
def healthz():
    return {"ok": True}


@app.get("/login")
def login(request: Request):
    if acesso.usuario_da_requisicao(request):
        return RedirectResponse("/", status_code=303)
    return _pagina("login.html")


@app.get("/configuracoes")
def configuracoes(request: Request):
    if not acesso.usuario_da_requisicao(request):
        return _ir_para_login(request)
    return _pagina("configuracoes.html")


@app.get("/")
def home(request: Request):
    if not acesso.usuario_da_requisicao(request):
        return _ir_para_login(request)
    home_html = _home_html()
    if home_html is None:
        raise HTTPException(500, "home.html não encontrado (procurei em hub/static/ e hub/)")
    return FileResponse(home_html, media_type="text/html", headers=SEM_CACHE)


@app.get("/api/modulos")
def api_modulos(request: Request):
    u = acesso.exigir_usuario(request)
    itens = [{k: v for k, v in i.items() if k != "_esquema"} for i in catalogo() if acesso.pode_acessar(u, i["id"])]
    return JSONResponse({"versao": VERSAO, "itens": itens, "usuario": acesso.publico(u)}, headers=SEM_CACHE)


@app.get("/m/{slug}")
def modulo(slug: str, request: Request):
    u = acesso.usuario_da_requisicao(request)
    if not u:
        return _ir_para_login(request)
    arq = _arquivo_do_modulo(slug)
    if arq is None:
        raise HTTPException(404, f"Módulo '{slug}' não encontrado em hub/modulos/")
    if not acesso.pode_acessar(u, slug):
        return HTMLResponse(_SEM_ACESSO, status_code=403)
    return FileResponse(arq, media_type="text/html", headers=SEM_CACHE)


@app.get("/m/{slug}/{caminho:path}")
def arquivo_do_modulo(slug: str, caminho: str, request: Request):
    if not SLUG_OK.match(slug):
        raise HTTPException(404)
    if not acesso.pode_acessar(acesso.usuario_da_requisicao(request), slug):
        raise HTTPException(403)
    pasta = (PASTA_MODULOS / slug).resolve()
    alvo = (pasta / caminho).resolve()
    # trava contra "../" — só serve o que está dentro da pasta do módulo
    if pasta not in alvo.parents or not alvo.is_file():
        raise HTTPException(404)
    return FileResponse(alvo, headers=SEM_CACHE)


@app.get("/api/diag")
def diag(request: Request):
    u = acesso.usuario_da_requisicao(request)
    resultado = {
        "versao": VERSAO,
        "no_ar_ha_seg": int(time.time() - _inicio),
        "firestore_configurado": banco.configurado(),
        "firestore": "não testado",
        "admin_fabrica_configurado": bool(acesso.ADMIN_FAB_LOGIN and acesso.ADMIN_FAB_SENHA),
        "segredo_temporario": acesso.SEGREDO_TEMPORARIO,
    }
    if u and u.get("admin"):
        resultado["modulos_internos"] = [m["id"] for m in modulos_internos()]
        resultado["sistemas_externos"] = [s["id"] for s in sistemas_externos()]
    if resultado["firestore_configurado"]:
        # timeout para nunca pendurar a rota se o gRPC travar
        # (sem "with": o with esperaria a thread travada e penduraria a rota)
        ex = ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(lambda: list(db().collection("config").limit(1).stream()))
        try:
            fut.result(timeout=8)
            resultado["firestore"] = "ok"
        except FutTimeout:
            resultado["firestore"] = "timeout (8s)"
        except Exception as e:  # noqa: BLE001
            resultado["firestore"] = f"erro: {type(e).__name__}: {e}"
        finally:
            ex.shutdown(wait=False)
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
# KIT VISUAL COMPARTILHADO — /static/aurora.css e /static/aurora.js
# (usado por todos os módulos: <link href="/static/aurora.css?v=1">)
# ══════════════════════════════════════════════════════════════════════════════
app.mount("/static", StaticFiles(directory=str(BASE / "static"), check_dir=False), name="static")
