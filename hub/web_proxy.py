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
# MODO AUTOMÁTICO — o site aceita abrir dentro do quadro?
#   sim → "direto" (navegador de verdade: login, cookies, vídeos)
#   não (X-Frame-Options / CSP frame-ancestors) → "hub" (o hub busca a página)
# ══════════════════════════════════════════════════════════════════════════════
_CACHE_MODO: dict = {}   # host → (modo, quando)


def _bloqueia_quadro(cab) -> bool:
    xfo = (cab.get("x-frame-options") or "").strip().lower()
    if xfo in ("deny", "sameorigin") or xfo.startswith("allow-from"):
        return True
    for csp in cab.get_list("content-security-policy") if hasattr(cab, "get_list") else [cab.get("content-security-policy") or ""]:
        m = re.search(r"frame-ancestors([^;]*)", csp or "", re.I)
        if m:
            fontes = m.group(1).split()
            if "*" not in fontes and "https:" not in fontes:
                return True
    return False


def _decidir_modo(u: str) -> dict:
    host = (urlsplit(u).hostname or "").lower()
    agora = time.time()
    if host in _CACHE_MODO and agora - _CACHE_MODO[host][1] < 6 * 3600:
        return {"modo": _CACHE_MODO[host][0], "host": host, "cache": True}
    if not host or not _host_publico(host):
        return {"modo": "hub", "host": host}
    try:
        with httpx.Client(timeout=httpx.Timeout(12.0, connect=6.0), follow_redirects=True, headers=_CAB) as cli:
            with cli.stream("GET", u) as r:
                if not _host_publico(r.url.host or ""):
                    return {"modo": "hub", "host": host}
                modo = "hub" if _bloqueia_quadro(r.headers) or r.status_code >= 400 else "direto"
    except httpx.HTTPError:
        modo = "hub"
    _CACHE_MODO[host] = (modo, agora)
    if len(_CACHE_MODO) > 3000:
        _CACHE_MODO.clear()
    return {"modo": modo, "host": host}


@router.get("/api/web/modo")
async def modo(request: Request, u: str = ""):
    us = acesso.exigir_usuario(request)
    if not acesso.pode_acessar(us, MOD):
        raise HTTPException(403, "Sem acesso ao módulo Web.")
    if not re.match(r"^https?://", u or "", re.I):
        raise HTTPException(400, "Endereço inválido.")
    return await run_in_threadpool(_decidir_modo, desembrulhar(u))


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


# ══════════════════════════════════════════════════════════════════════════════
# POTE DE CADA USUÁRIO, POR SITE — cookies e memória (localStorage) dos sites abertos
# pelo modo hub. Assim "Aceitar cookies", preferências e logins simples continuam
# valendo de uma página para a outra. Fica só na memória do servidor: nunca se mistura
# entre usuários e some quando o serviço reinicia.
# ══════════════════════════════════════════════════════════════════════════════
_POTES: dict = {}
_SLD = {"com", "net", "org", "gov", "edu", "co", "art", "blog", "jus", "mil", "nom", "app", "tv"}


def site_de(host: str) -> str:
    p = (host or "").lower().strip(".").split(".")
    if len(p) >= 3 and p[-2] in _SLD and len(p[-1]) == 2:
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def _pote(login: str, host: str) -> dict:
    k = (login, site_de(host))
    pt = _POTES.get(k)
    if pt is None:
        if len(_POTES) > 2000:
            for velho in sorted(_POTES, key=lambda x: _POTES[x]["em"])[:500]:
                _POTES.pop(velho, None)
        pt = _POTES[k] = {"ck": {}, "ls": {}, "em": time.time()}
    pt["em"] = time.time()
    return pt


def _guardar_cookies(pt: dict, resposta) -> None:
    for linha in resposta.headers.get_list("set-cookie"):
        partes = [x.strip() for x in linha.split(";")]
        if "=" not in partes[0]:
            continue
        nome, valor = partes[0].split("=", 1)
        attrs = {a.split("=", 1)[0].lower(): (a.split("=", 1)[1] if "=" in a else "") for a in partes[1:]}
        apaga = attrs.get("max-age", "").strip() in ("0", "-1") or "1970" in attrs.get("expires", "")
        if apaga or not valor:
            pt["ck"].pop(nome.strip(), None)
        elif len(pt["ck"]) < 150 and len(valor) < 4096:
            pt["ck"][nome.strip()] = {"v": valor, "http": "httponly" in attrs}


def _cab_cookie(pt: dict | None) -> dict:
    if not pt or not pt["ck"]:
        return {}
    return {"Cookie": "; ".join(f"{k}={c['v']}" for k, c in pt["ck"].items())}


def _buscar(url: str, metodo: str = "GET", corpo: bytes | None = None, tipo: str | None = None, login: str | None = None):
    # cliente novo a cada página; os cookies vêm do POTE do próprio usuário (nunca de outro)
    with httpx.Client(timeout=httpx.Timeout(25.0, connect=10.0), follow_redirects=False, headers=_CAB) as cli:
        return _buscar_com(cli, url, metodo, corpo, tipo, login)


def _buscar_com(cli, url, metodo, corpo, tipo, login=None):
    for _ in range(8):
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise HTTPException(400, "Endereço inválido.")
        if not _host_publico(p.hostname):
            raise HTTPException(403, "Endereço interno bloqueado.")
        cab = {"Content-Type": tipo} if corpo and tipo else {}
        pt = _pote(login, p.hostname) if login else None
        cab.update(_cab_cookie(pt))
        r = cli.request(metodo, url, content=corpo, headers=cab)
        if pt is not None:
            _guardar_cookies(pt, r)
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
/* MEMÓRIA E COOKIES DO SITE: no modo isolado o navegador proíbe a página de usar
   localStorage, sessionStorage e cookies — e os scripts dos sites quebram. Aqui eles
   ganham versões que o hub GUARDA por usuário e por site (o "Aceitar cookies" e as
   preferências continuam valendo na próxima página), sem nenhum acesso ao hub. */
var HUB=%(hub)s, T=%(tok)s, SITE=%(site)s, CK=%(ck)s, LS=%(ls)s;
function guardar(o){ try{ o.s=SITE; var u=HUB+"/web/c?t="+encodeURIComponent(T); if(window.fetch) fetch(u,{method:"POST",body:JSON.stringify(o),keepalive:true,headers:{"Content-Type":"text/plain"}}).catch(function(){}); }catch(_){} }
function memoria(ini,persiste){ var d={}; Object.keys(ini||{}).forEach(function(k){ d[k]=String(ini[k]); });
  return { getItem:function(k){ k=String(k); return Object.prototype.hasOwnProperty.call(d,k)?d[k]:null; },
  setItem:function(k,v){ k=String(k); v=String(v); if(d[k]===v) return; d[k]=v; if(persiste) guardar({ls:k,v:v}); },
  removeItem:function(k){ k=String(k); if(!(k in d)) return; delete d[k]; if(persiste) guardar({ls:k,del:1}); },
  clear:function(){ Object.keys(d).forEach(function(k){ if(persiste) guardar({ls:k,del:1}); }); d={}; },
  key:function(i){ return Object.keys(d)[i]||null; }, get length(){ return Object.keys(d).length; } }; }
[["localStorage",LS,true],["sessionStorage",{},false]].forEach(function(x){ try{ var s=window[x[0]]; s.getItem("_"); }catch(_){ try{ Object.defineProperty(window,x[0],{value:memoria(x[1],x[2]),configurable:true}); }catch(__){} } });
try{ document.cookie; }catch(_){ var pote={}; Object.keys(CK||{}).forEach(function(k){ pote[k]=CK[k]; });
  try{ Object.defineProperty(document,"cookie",{configurable:true,
  get:function(){ return Object.keys(pote).map(function(k){ return k+"="+pote[k]; }).join("; "); },
  set:function(v){ v=String(v); var p=v.split(";")[0], i=p.indexOf("="); if(i<=0) return; var n=p.slice(0,i).trim(), val=p.slice(i+1).trim();
    if(/expires=[^;]*1970|max-age=(0|-)/i.test(v)||!val){ delete pote[n]; guardar({ck:n,del:1}); }
    else if(pote[n]!==val){ pote[n]=val; guardar({ck:n,v:val}); } } }); }catch(__){} }
})();</script><script>(function(){
var HUB=%(hub)s, T=%(tok)s, AQUI=%(url)s;
function via(u){ return HUB+"/web/p?t="+encodeURIComponent(T)+"&u="+encodeURIComponent(u); }
function cru(u){ return HUB+"/web/r?t="+encodeURIComponent(T)+"&u="+encodeURIComponent(u); }
function avisar(){ try{ parent.postMessage({hubWeb:"url",url:AQUI,titulo:document.title||""},"*"); }catch(_){} }
avisar(); addEventListener("load",avisar);
function abs(h){ try{ return new URL(h, document.baseURI).href; }catch(_){ return null; } }
var VIDEO=/^https?:\/\/((www\.|m\.)?youtube\.com\/(watch|shorts\/|live\/)|youtu\.be\/|(www\.)?vimeo\.com\/\d)/i;
var PAI=false; try{ PAI = parent!==window; }catch(_){}
function ir(u){
  /* o hub decide: o destino aceita abrir no quadro → direto (navegador de verdade); senão → modo hub */
  if(PAI){ try{ parent.postMessage({hubWeb:"abrir",url:u},"*"); return; }catch(_){} }
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


def _html(texto: str, final: str, hub: str, tok: str, pote: dict | None = None) -> str:
    texto = _RE_META_CSP.sub("", texto)
    base_orig = None
    m = re.search(r"<base\b[^>]*href\s*=\s*[\"']([^\"']+)", texto, re.I)
    if m:
        base_orig = urljoin(final, m.group(1))
    texto = _RE_BASE.sub("", texto)
    # strict-origin: os sites recebem só "de onde" (o endereço do hub), nunca o token — e o YouTube exige isso
    inj = (f'<base href="{_esc(base_orig or final)}"><meta name="referrer" content="strict-origin">'
           + _SCRIPT % {"hub": json.dumps(hub), "tok": json.dumps(tok), "url": json.dumps(final),
                        "site": json.dumps(site_de(urlsplit(final).hostname or "")),
                        "ck": json.dumps({k: c["v"] for k, c in (pote or {}).get("ck", {}).items() if not c.get("http")}).replace("</", "<\\/"),
                        "ls": json.dumps((pote or {}).get("ls", {})).replace("</", "<\\/")})
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
        r, final = await run_in_threadpool(_buscar, u, request.method, corpo, request.headers.get("content-type"), login)
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
        texto = _html(r.text, final, _base(request), tok, _pote(login, urlsplit(final).hostname or ""))
        return HTMLResponse(texto, status_code=r.status_code if r.status_code < 400 else 200, headers=cab)
    disp = r.headers.get("content-disposition")
    if disp:
        cab["Content-Disposition"] = disp
    return Response(r.content, status_code=r.status_code, media_type=tipo or "application/octet-stream", headers=cab)


@router.options("/web/c")
def guardar_opcoes():
    return Response(status_code=204, headers=_CORS)


@router.post("/web/c")
async def guardar(request: Request, t: str = ""):
    """O site gravou um cookie ou um item de memória → vai para o pote do usuário."""
    login = _ler_token(t)
    if not login:
        return Response(status_code=401, headers=_CORS)
    try:
        d = json.loads((await request.body())[:40000] or b"{}")
    except Exception:  # noqa: BLE001
        return Response(status_code=400, headers=_CORS)
    site = str(d.get("s") or "")
    if not re.fullmatch(r"[a-z0-9.-]{3,120}", site):
        return Response(status_code=400, headers=_CORS)
    pt = _pote(login, site)
    if "ck" in d:
        n = str(d["ck"])[:200]
        if d.get("del"):
            pt["ck"].pop(n, None)
        elif len(pt["ck"]) < 150:
            pt["ck"][n] = {"v": str(d.get("v") or "")[:4096], "http": False}
    elif "ls" in d:
        k = str(d["ls"])[:300]
        if d.get("del"):
            pt["ls"].pop(k, None)
        else:
            v = str(d.get("v") or "")
            if len(v) <= 20000 and (k in pt["ls"] or sum(len(x) for x in pt["ls"].values()) < 300000):
                pt["ls"][k] = v
    return Response(status_code=204, headers=_CORS)


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
    pt = _pote(_ler_token(t), p.hostname)
    cab.update(_cab_cookie(pt))
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
    _guardar_cookies(pt, r)
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
