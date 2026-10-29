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
import os
import re
import socket
import time
from urllib.parse import parse_qs, quote, urljoin, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

import acesso

router = APIRouter()
MOD = "web"
MAX_BYTES = 15 * 1024 * 1024
MAX_STREAM = 300 * 1024 * 1024   # vídeo/arquivo repassado aos pedaços (Range)

# ── ORIGEM SEPARADA (opcional, recomendado) ─────────────────────────────────────
# Um 2º serviço GRÁTIS no Render, rodando ESTE MESMO código, com outro endereço
# (ex.: https://wendleyweb.onrender.com) e o MESMO HUB_SEGREDO. No serviço do hub,
# configure WEB_PROXY_ORIGEM com esse endereço. Com isso, os sites abertos pelo
# modo hub ganham uma origem própria (que não é a do hub): podem usar memória do
# navegador, players de vídeo e quadros internos (YouTube embutido) sem nenhum
# acesso ao hub. Sem a variável, tudo continua funcionando no modo isolado.
ORIGEM_WEB = (os.environ.get("WEB_PROXY_ORIGEM") or "").strip().rstrip("/")
HOST_WEB = (urlsplit(ORIGEM_WEB).hostname or "").lower() if ORIGEM_WEB else ""
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
    return {"token": _token(u["login"]), "origem": ORIGEM_WEB}


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
# LINKS "EMBRULHADOS" (buscadores) → endereço real
# ══════════════════════════════════════════════════════════════════════════════
def desembrulhar(u: str) -> str:
    """Bing (/ck/a?u=a1…), Google (/url?q=…) e DuckDuckGo (/l/?uddg=…) escondem o
    endereço da matéria num redirecionamento feito por JavaScript — que escaparia
    do hub. Aqui o endereço real é tirado de dentro e aberto direto."""
    try:
        p = urlsplit(u)
        h, q = (p.hostname or "").lower(), parse_qs(p.query)
        if h.endswith("bing.com") and p.path == "/ck/a" and q.get("u"):
            v = q["u"][0]
            if v.startswith("a1"):
                v = base64.urlsafe_b64decode(v[2:] + "=" * (-len(v[2:]) % 4)).decode("utf-8", "replace")
            if re.match(r"^https?://", v, re.I):
                return v
        if re.search(r"(^|\.)google\.[a-z.]+$", h) and p.path == "/url":
            v = (q.get("q") or q.get("url") or [""])[0]
            if re.match(r"^https?://", v, re.I):
                return v
        if h.endswith("duckduckgo.com") and p.path.startswith("/l") and q.get("uddg"):
            return q["uddg"][0]
    except Exception:  # noqa: BLE001
        pass
    return u


# ══════════════════════════════════════════════════════════════════════════════
# O QUE VAI DENTRO DA PÁGINA
#   · links e formulários voltam a passar pelo hub (a navegação fica aqui dentro);
#   · links e janelas novas (target=_blank / window.open) abrem no MESMO quadro;
#   · vídeos do YouTube/Vimeo vão para o player próprio deles (o hub abre direto);
#   · fetch/XHR que o site bloqueia por CORS tentam de novo pelo hub (/web/r).
# ══════════════════════════════════════════════════════════════════════════════
_SCRIPT = r"""<script>(function(){
var HUB=%(hub)s, T=%(tok)s, AQUI=%(url)s;
function via(u){ return HUB+"/web/p?t="+encodeURIComponent(T)+"&u="+encodeURIComponent(u); }
function cru(u){ return HUB+"/web/r?t="+encodeURIComponent(T)+"&u="+encodeURIComponent(u); }
function avisar(){ try{ parent.postMessage({hubWeb:"url",url:AQUI,titulo:document.title||""},"*"); }catch(_){} }
avisar(); addEventListener("load",avisar);
function abs(h){ try{ return new URL(h, document.baseURI).href; }catch(_){ return null; } }
var VIDEO=/^https?:\/\/((www\.|m\.)?youtube\.com\/(watch|shorts\/|live\/)|youtu\.be\/|(www\.)?vimeo\.com\/\d)/i;
function ir(u){
  if(VIDEO.test(u)){ try{ parent.postMessage({hubWeb:"abrir",url:u},"*"); return; }catch(_){} }
  location.href=via(u);
}
document.addEventListener("click",function(e){
  if(e.defaultPrevented||e.button!==0) return;
  var a=e.target&&e.target.closest?e.target.closest("a[href]"):null; if(!a) return;
  if(a.hasAttribute("download")) return;
  var h=a.getAttribute("href")||""; if(!h||h.charAt(0)==="#"||/^(javascript|mailto|tel|data|blob|sms|whatsapp):/i.test(h)) return;
  var u=abs(h); if(!u||!/^https?:/i.test(u)) return;
  var semHash=u.split("#")[0], aquiSem=AQUI.split("#")[0]; if(semHash===aquiSem&&u.indexOf("#")>=0) return;
  e.preventDefault(); e.stopPropagation(); ir(u);
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
var oo=window.open; window.open=function(u,n,f){ var x=u?abs(String(u)):null; if(x&&/^https?:/i.test(x)){ ir(x); return window; } return oo.apply(window,arguments); };
["pushState","replaceState"].forEach(function(k){ var o=history[k]; history[k]=function(){ try{ return o.apply(history,arguments); }catch(_){ } }; });
/* fetch: tenta direto; se o site barrar (CORS), repete pelo hub */
var of=window.fetch;
if(of){ window.fetch=function(rq,op){
  var u; try{ u=abs(typeof rq==="string"?rq:(rq&&rq.url)||String(rq)); }catch(_){ u=null; }
  var p=of.apply(window,arguments);
  if(!u||!/^https?:/i.test(u)||u.indexOf(HUB)===0) return p;
  return p.catch(function(err){
    var o={}; try{ o.method=(op&&op.method)||(rq&&rq.method)||"GET"; if(op&&op.body&&typeof op.body==="string") o.body=op.body; if(op&&op.headers) o.headers=op.headers; }catch(_){}
    if(o.method&&!/^(GET|HEAD|POST)$/i.test(o.method)) throw err;
    return of.call(window,cru(u),o);
  });
}; }
/* XMLHttpRequest: pedidos para OUTRO endereço vão pelo hub (o navegador não deixa o site ler a resposta) */
var xo=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(m,u){
  try{ var x=abs(String(u)); if(x&&/^https?:/i.test(x)&&x.indexOf(HUB)!==0&&/^(GET|HEAD|POST)$/i.test(m)){ arguments[1]=cru(x); } }catch(_){}
  return xo.apply(this,arguments);
};
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
    # strict-origin: os sites recebem só "de onde" (o endereço do hub), nunca o token — e o YouTube exige isso
    inj = (f'<base href="{_esc(base_orig or final)}"><meta name="referrer" content="strict-origin">'
           + _SCRIPT % {"hub": json.dumps(hub), "tok": json.dumps(tok), "url": json.dumps(final)})
    if _RE_HEAD.search(texto):
        return _RE_HEAD.sub(lambda mm: mm.group(0) + inj, texto, count=1)
    return inj + texto


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


# Página entregue SEM a origem do hub: o site não lê cookies nem chama a API do hub.
_PERMITE = "allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads allow-presentation"
_SANDBOX = "sandbox " + _PERMITE
# Na ORIGEM SEPARADA (outro endereço, que não é o do hub) o site ganha origem própria:
# memória do navegador, players e quadros internos funcionam — e o hub continua inalcançável.
_SANDBOX_SEPARADA = "sandbox allow-same-origin allow-storage-access-by-user-activation " + _PERMITE


def _na_origem_separada(request: Request) -> bool:
    return bool(HOST_WEB) and (request.headers.get("host") or "").split(":")[0].lower() == HOST_WEB


def _base(request: Request) -> str:
    if _na_origem_separada(request):
        return ORIGEM_WEB
    hub = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https":
        hub = hub.replace("http://", "https://", 1)
    return hub


def _login(request: Request, t: str):
    login = _ler_token(t)
    if not login and not _na_origem_separada(request):
        cookie_u = acesso.usuario_da_requisicao(request)
        if cookie_u and acesso.pode_acessar(cookie_u, MOD):
            login = cookie_u["login"]
    return login


@router.api_route("/web/p", methods=["GET", "POST"])
async def proxy(request: Request, u: str = "", t: str = ""):
    login = _login(request, t)
    if not login:
        return HTMLResponse("<p style='font-family:sans-serif'>Sessão do módulo Web expirou — abra o site de novo pelo hub.</p>", status_code=401)
    tok = t if _ler_token(t) else _token(login)
    if not re.match(r"^https?://", u or "", re.I):
        raise HTTPException(400, "Endereço inválido.")
    real = desembrulhar(u)
    if real != u:   # link de buscador → vai direto para a matéria
        return RedirectResponse(f"{_base(request)}{link(real, tok)}", status_code=302)
    corpo = await request.body() if request.method == "POST" else None
    try:
        r, final = await run_in_threadpool(_buscar, u, request.method, corpo, request.headers.get("content-type"))
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        return HTMLResponse(f"<p style='font-family:sans-serif;padding:20px'>Não consegui abrir <b>{_esc(u)}</b> ({e.__class__.__name__}).</p>", status_code=502)
    tipo = r.headers.get("content-type", "")
    separada = _na_origem_separada(request)
    cab = {"Content-Security-Policy": _SANDBOX_SEPARADA if separada else _SANDBOX, "Referrer-Policy": "strict-origin",
           "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if len(r.content) > MAX_BYTES:
        raise HTTPException(413, "Arquivo grande demais para abrir aqui — use ↗.")
    if "html" in tipo:
        texto = _html(r.text, final, _base(request), tok)
        return HTMLResponse(texto, status_code=r.status_code if r.status_code < 400 else 200, headers=cab)
    disp = r.headers.get("content-disposition")
    if disp:
        cab["Content-Disposition"] = disp
    return Response(r.content, status_code=r.status_code, media_type=tipo or "application/octet-stream", headers=cab)


# ══════════════════════════════════════════════════════════════════════════════
# /web/r — REPASSE "CRU" (dados, APIs e pedaços de vídeo pedidos pelo próprio site)
#   · responde com Access-Control-Allow-Origin: * (o site consegue ler);
#   · aceita Range (vídeo/áudio avançam e voltam);
#   · sem cookies de ninguém: cada pedido é um cliente novo.
# ══════════════════════════════════════════════════════════════════════════════
_CAB_PASSA = ("content-type", "content-length", "content-range", "accept-ranges", "last-modified", "etag", "content-disposition")
_CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, HEAD, POST, OPTIONS",
         "Access-Control-Allow-Headers": "*", "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, Content-Type"}


@router.options("/web/r")
def repasse_opcoes():
    return Response(status_code=204, headers=_CORS)


@router.api_route("/web/r", methods=["GET", "HEAD", "POST"])
async def repasse(request: Request, u: str = "", t: str = ""):
    if not _ler_token(t):
        return Response("Sessão do módulo Web expirou.", status_code=401, headers=_CORS)
    u = desembrulhar(u)
    p = urlsplit(u or "")
    if p.scheme not in ("http", "https") or not p.hostname:
        return Response("Endereço inválido.", status_code=400, headers=_CORS)
    if not await run_in_threadpool(_host_publico, p.hostname):
        return Response("Endereço interno bloqueado.", status_code=403, headers=_CORS)
    cab = dict(_CAB)
    for k in ("range", "content-type", "accept"):
        if request.headers.get(k):
            cab[k] = request.headers[k]
    corpo = await request.body() if request.method == "POST" else None
    cli = httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0), follow_redirects=True, headers=cab)
    try:
        req = cli.build_request(request.method, u, content=corpo)
        r = await cli.send(req, stream=True)
    except httpx.HTTPError as e:
        await cli.aclose()
        return Response(f"Falhou: {e.__class__.__name__}", status_code=502, headers=_CORS)
    if not await run_in_threadpool(_host_publico, r.url.host or ""):   # redirecionou para endereço interno
        await r.aclose(); await cli.aclose()
        return Response("Endereço interno bloqueado.", status_code=403, headers=_CORS)
    tam = int(r.headers.get("content-length") or 0)
    if tam > MAX_STREAM:
        await r.aclose(); await cli.aclose()
        return Response("Grande demais para passar pelo hub.", status_code=413, headers=_CORS)
    comprimido = bool(r.headers.get("content-encoding"))
    saida = {k: v for k, v in r.headers.items() if k.lower() in _CAB_PASSA and not (comprimido and k.lower() == "content-length")}
    saida.update(_CORS)
    saida["Cache-Control"] = "private, max-age=300"

    async def fluxo():
        enviados = 0
        async for parte in (r.aiter_bytes() if comprimido else r.aiter_raw()):
            enviados += len(parte)
            if enviados > MAX_STREAM:
                break
            yield parte

    async def fechar():
        await r.aclose()
        await cli.aclose()
    return StreamingResponse(fluxo(), status_code=r.status_code, headers=saida, background=BackgroundTask(fechar))


def link(u: str, token_: str) -> str:
    return f"/web/p?t={quote(token_)}&u={quote(u, safe='')}"
