"""
═══════════════════════════════════════════════════════════════════════════════
 web_proxy.py — "Modo hub" do módulo Web: abrir QUALQUER site aqui dentro
───────────────────────────────────────────────────────────────────────────────
 Muitos sites (UOL, Outlook, jornais…) mandam o navegador NÃO mostrar a
 página dentro de outra (X-Frame-Options / CSP frame-ancestors). A extensão do
 Chrome resolvia isso só no Chrome. Este modo funciona em qualquer navegador
 (inclusive o navegador do app Claude): o hub busca a página e a entrega sem
 essas travas; os links clicados voltam a passar pelo hub, então a navegação
 continua aqui dentro.

 Segurança:
   · só quem está logado no hub e tem o módulo Web (token próprio, curto e
     que NÃO serve como sessão do hub);
   · a página entregue roda em "sandbox" sem a origem do hub (CSP sandbox),
     então nenhum script do site consegue ler nada do hub;
   · bloqueia endereços internos (localhost, 10.x, 192.168.x, 169.254.x…).

 Limites (honestos): sites que exigem login (Outlook, Gmail, bancos) ou que
 são um app pesado em JavaScript podem não funcionar 100% — para esses, o
 botão ↗ abre numa aba do navegador. Para ler notícias e páginas comuns, vai.
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import base64
import hmac
import ipaddress
import json
import re
import socket
import time
from urllib.parse import quote, urljoin, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

import acesso

router = APIRouter()
MOD = "web"
MAX_BYTES = 15 * 1024 * 1024
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0.0.0 Safari/537.36")
_CAB = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN (só para o proxy — não é a sessão do hub)
# ══════════════════════════════════════════════════════════════════════════════
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _token(login: str, horas: float = 12) -> str:
    corpo = _b64(json.dumps({"w": login, "e": int(time.time() + horas * 3600)}).encode())
    return corpo + "." + acesso._assinar("web-proxy." + corpo)[:32]


def _ler_token(t: str) -> str | None:
    if not t or "." not in t:
        return None
    corpo, ass = t.rsplit(".", 1)
    if not hmac.compare_digest(acesso._assinar("web-proxy." + corpo)[:32], ass):
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    except Exception:  # noqa: BLE001
        return None
    return d.get("w") if d.get("e", 0) > time.time() else None


@router.get("/api/web/token")
def token(request: Request):
    u = acesso.exigir_usuario(request)
    if not acesso.pode_acessar(u, MOD):
        raise HTTPException(403, "Sem acesso ao módulo Web.")
    return {"token": _token(u["login"])}


# ══════════════════════════════════════════════════════════════════════════════
# BUSCA SEGURA
# ══════════════════════════════════════════════════════════════════════════════
def _host_publico(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


def _buscar(url: str, metodo: str = "GET", corpo: bytes | None = None, tipo: str | None = None):
    # cliente novo a cada página: os cookies de um usuário nunca se misturam com os de outro
    with httpx.Client(timeout=httpx.Timeout(25.0, connect=10.0), follow_redirects=False, headers=_CAB) as cli:
        return _buscar_com(cli, url, metodo, corpo, tipo)


def _buscar_com(cli, url, metodo, corpo, tipo):
    for _ in range(8):
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise HTTPException(400, "Endereço inválido.")
        if not _host_publico(p.hostname):
            raise HTTPException(403, "Endereço interno bloqueado.")
        cab = {"Content-Type": tipo} if corpo and tipo else {}
        r = cli.request(metodo, url, content=corpo, headers=cab)
        if r.is_redirect and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            if r.status_code in (301, 302, 303):
                metodo, corpo = "GET", None
            continue
        return r, url
    raise HTTPException(508, "Redirecionamentos demais.")


# ══════════════════════════════════════════════════════════════════════════════
# O QUE VAI DENTRO DA PÁGINA
# ══════════════════════════════════════════════════════════════════════════════
_SCRIPT = r"""<script>(function(){
var HUB=%(hub)s, T=%(tok)s, AQUI=%(url)s;
function via(u){ return HUB+"/web/p?t="+encodeURIComponent(T)+"&u="+encodeURIComponent(u); }
try{ parent.postMessage({hubWeb:"url",url:AQUI,titulo:document.title||""},"*"); }catch(_){}
addEventListener("load",function(){ try{ parent.postMessage({hubWeb:"url",url:AQUI,titulo:document.title||""},"*"); }catch(_){} });
function abs(h){ try{ return new URL(h, document.baseURI).href; }catch(_){ return null; } }
document.addEventListener("click",function(e){
  if(e.defaultPrevented||e.button!==0) return;
  var a=e.target&&e.target.closest?e.target.closest("a[href]"):null; if(!a) return;
  var h=a.getAttribute("href")||""; if(!h||h.charAt(0)==="#"||/^(javascript|mailto|tel|data|blob):/i.test(h)) return;
  var u=abs(h); if(!u||!/^https?:/i.test(u)) return;
  var semHash=u.split("#")[0], aquiSem=AQUI.split("#")[0]; if(semHash===aquiSem&&u.indexOf("#")>=0) return;
  e.preventDefault(); e.stopPropagation(); location.href=via(u);
},true);
document.addEventListener("submit",function(e){
  var f=e.target; if(!f||f.tagName!=="FORM") return;
  var m=(f.getAttribute("method")||"get").toLowerCase(); var act=abs(f.getAttribute("action")||AQUI); if(!act) return;
  e.preventDefault();
  if(m==="get"){ var q=new URLSearchParams(new FormData(f)).toString(); var x=new URL(act); x.search=q; location.href=via(x.href); return; }
  var t=document.createElement("form"); t.method="post"; t.action=via(act); t.enctype=f.enctype||"application/x-www-form-urlencoded";
  new FormData(f).forEach(function(v,k){ if(typeof v==="string"){ var i=document.createElement("input"); i.type="hidden"; i.name=k; i.value=v; t.appendChild(i);} });
  document.body.appendChild(t); HTMLFormElement.prototype.submit.call(t);
},true);
var oo=window.open; window.open=function(u,n,f){ var x=u?abs(String(u)):null; if(x&&/^https?:/i.test(x)){ location.href=via(x); return null; } return oo.apply(window,arguments); };
["pushState","replaceState"].forEach(function(k){ var o=history[k]; history[k]=function(){ try{ return o.apply(history,arguments); }catch(_){ } }; });
})();</script>"""

_RE_META_CSP = re.compile(r"<meta[^>]+http-equiv\s*=\s*[\"']?(content-security-policy|x-frame-options|refresh)[^>]*>", re.I)
_RE_BASE = re.compile(r"<base\b[^>]*>", re.I)
_RE_HEAD = re.compile(r"<head\b[^>]*>", re.I)


def _html(texto: str, final: str, hub: str, tok: str) -> str:
    texto = _RE_META_CSP.sub("", texto)
    base_orig = None
    m = re.search(r"<base\b[^>]*href\s*=\s*[\"']([^\"']+)", texto, re.I)
    if m:
        base_orig = urljoin(final, m.group(1))
    texto = _RE_BASE.sub("", texto)
    inj = (f'<base href="{_esc(base_orig or final)}"><meta name="referrer" content="no-referrer">'
           + _SCRIPT % {"hub": json.dumps(hub), "tok": json.dumps(tok), "url": json.dumps(final)})
    if _RE_HEAD.search(texto):
        return _RE_HEAD.sub(lambda mm: mm.group(0) + inj, texto, count=1)
    return inj + texto


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


# Página entregue SEM a origem do hub: o site não lê cookies nem chama a API do hub
_SANDBOX = "sandbox allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads allow-presentation"


@router.api_route("/web/p", methods=["GET", "POST"])
async def proxy(request: Request, u: str = "", t: str = ""):
    login = _ler_token(t)
    if not login:
        cookie_u = acesso.usuario_da_requisicao(request)
        if cookie_u and acesso.pode_acessar(cookie_u, MOD):
            login = cookie_u["login"]
    if not login:
        return HTMLResponse("<p style='font-family:sans-serif'>Sessão do módulo Web expirou — abra o site de novo pelo hub.</p>", status_code=401)
    tok = t if _ler_token(t) else _token(login)
    if not re.match(r"^https?://", u or "", re.I):
        raise HTTPException(400, "Endereço inválido.")
    corpo = await request.body() if request.method == "POST" else None
    try:
        r, final = await run_in_threadpool(_buscar, u, request.method, corpo, request.headers.get("content-type"))
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        return HTMLResponse(f"<p style='font-family:sans-serif;padding:20px'>Não consegui abrir <b>{_esc(u)}</b> ({e.__class__.__name__}).</p>", status_code=502)
    tipo = r.headers.get("content-type", "")
    cab = {"Content-Security-Policy": _SANDBOX, "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
           "X-Content-Type-Options": "nosniff"}
    if len(r.content) > MAX_BYTES:
        raise HTTPException(413, "Arquivo grande demais para abrir aqui — use ↗.")
    if "html" in tipo:
        hub = str(request.base_url).rstrip("/")
        if request.headers.get("x-forwarded-proto") == "https":
            hub = hub.replace("http://", "https://", 1)
        texto = _html(r.text, final, hub, tok)
        return HTMLResponse(texto, status_code=r.status_code if r.status_code < 400 else 200, headers=cab)
    disp = r.headers.get("content-disposition")
    if disp:
        cab["Content-Disposition"] = disp
    return Response(r.content, status_code=r.status_code, media_type=tipo or "application/octet-stream", headers=cab)


def link(u: str, token_: str) -> str:
    return f"/web/p?t={quote(token_)}&u={quote(u, safe='')}"
