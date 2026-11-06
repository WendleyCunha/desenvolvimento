"""
hub/relatorios_publico.py — App "Relatórios Parque Aliança" (página pública) + anúncios.

Página aberta, sem login, em /relatorios/ — substitui o formulário Streamlit
(relatoriosparquealianca.streamlit.app), que continua funcionando em paralelo.

Grava EXATAMENTE no formato do formulário antigo (coleção relatorios_parque_alianca),
então a triagem do Secretário recebe sem mudar nada:
    nome, mes_referencia ("OUTUBRO 2027" = ano de serviço, convenção do admin),
    mes_chave ("2026-10"), participou_ministerio, estudos_biblicos, horas,
    observacoes, data_envio, status_pdf="PENDENTE"
Quem envia vê o mês CIVIL ("Outubro 2026"); o ano de serviço fica só no banco.

Anúncios: coleção "anuncios", mesmo formato do admin Streamlit (mod_anuncios.py):
    tipo (texto|imagem|agenda), titulo, conteudo_html, renderizar_markdown,
    dados_agenda (agenda), data_postagem
A página pública NÃO injeta o HTML gravado: monta texto/imagem/agenda com o
próprio visual (o HTML continua sendo gravado para o admin antigo ler igual).
"""
from __future__ import annotations

import html
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

import banco
import secretaria
import secretaria_regras as R

router = APIRouter()
PASTA = Path(__file__).parent / "static" / "relatorios"
COL_ANUNCIOS = "anuncios"
MAX_IMAGEM = 900_000          # data URI (o documento do Firestore tem limite de 1 MB)
CACHE_ANUNCIOS_S = 90         # poupa leitura do Firestore (plano gratuito)


# ══════════════════════════════════════════════════════════════════════════════
# Página e app instalável (escopo próprio: /relatorios/)
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/relatorios", include_in_schema=False)
def _sem_barra():
    return RedirectResponse("/relatorios/", status_code=307)


@router.get("/relatorios/", include_in_schema=False)
def pagina():
    return FileResponse(PASTA / "index.html", media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


@router.get("/relatorios/manifest.webmanifest", include_in_schema=False)
def manifesto():
    return FileResponse(PASTA / "manifest.webmanifest", media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"})


@router.get("/relatorios/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(PASTA / "sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/relatorios/"})


# ══════════════════════════════════════════════════════════════════════════════
# Envio do relatório (público)
# ══════════════════════════════════════════════════════════════════════════════
def _mes_chave() -> str:
    return R.chave_por_data(datetime.now(R.FUSO),
                            secretaria.BASE.config().get("corte_dia", R.CORTE_DIA_PADRAO) if banco.configurado() else R.CORTE_DIA_PADRAO)


_envios: dict[str, list[float]] = {}
_trava_envios = threading.Lock()


def _limitar(request: Request, maximo=8, janela=600):
    """Freio simples contra robô: até 8 envios por 10 min por endereço."""
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "?")
    agora = time.time()
    with _trava_envios:
        l = [t for t in _envios.get(ip, []) if agora - t < janela]
        if len(l) >= maximo:
            raise HTTPException(429, "Muitos envios seguidos. Aguarde alguns minutos e tente de novo.")
        l.append(agora)
        _envios[ip] = l
        if len(_envios) > 5000:
            _envios.clear()


def _int(v, lo, hi) -> int:
    try:
        n = int(float(str(v).replace(",", ".") or 0))
    except (TypeError, ValueError):
        raise HTTPException(422, "Use só números em estudos e horas.")
    if n < lo or n > hi:
        raise HTTPException(422, f"Valor fora do esperado ({lo} a {hi}).")
    return n


@router.get("/api/relatorios-publico/info")
def info():
    ch = _mes_chave()
    return {"mes_chave": ch, "mes": R.rotulo(ch), "congregacao": "Parque Aliança", "numero": "72249"}


@router.post("/api/relatorios-publico/enviar")
async def enviar(request: Request):
    if not banco.configurado():
        raise HTTPException(503, "Sistema em manutenção. Tente mais tarde.")
    try:
        d = await request.json()
    except Exception:
        raise HTTPException(400, "Envio inválido.")
    nome = re.sub(r"\s+", " ", str(d.get("nome") or "")).strip()
    if len(nome) < 3:
        raise HTTPException(422, "Escreva seu nome completo.")
    if len(nome) > 80:
        raise HTTPException(422, "Nome muito longo.")
    obs = str(d.get("observacoes") or "").strip()[:600]
    _limitar(request)
    ch = _mes_chave()
    dados = {
        "nome": nome,
        "mes_referencia": R.rotulo_banco(ch),
        "mes_chave": ch,
        "participou_ministerio": bool(d.get("participou")),
        "estudos_biblicos": _int(d.get("estudos") or 0, 0, 99),
        "horas": _int(d.get("horas") or 0, 0, 400),
        "observacoes": obs,
        "data_envio": datetime.now(timezone.utc),
        "status_pdf": "PENDENTE",
        "origem": "app-relatorios",
    }
    ref = banco.db().collection(secretaria.COL_REL).document()
    secretaria.BASE.gravar_rel(ref.id, dados, merge=False)   # grava e já entra no cache do Secretário
    return {"ok": True, "nome": nome, "mes": R.rotulo(ch), "protocolo": ref.id[:6].upper()}


# ══════════════════════════════════════════════════════════════════════════════
# Anúncios
# ══════════════════════════════════════════════════════════════════════════════
_cache = {"t": 0.0, "lista": None}
_trava_cache = threading.Lock()


def limpar_cache():
    with _trava_cache:
        _cache["t"], _cache["lista"] = 0.0, None


def _iso(v):
    if hasattr(v, "isoformat"):
        try:
            return v.astimezone(R.FUSO).isoformat()
        except Exception:
            return v.isoformat()
    return str(v or "")


_IMG = re.compile(r'src="(data:image/(?:png|jpe?g|webp);base64,[A-Za-z0-9+/=]+)"')


def _publico(doc_id: str, a: dict) -> dict:
    tipo = a.get("tipo") or ("texto" if a.get("renderizar_markdown") else "html")
    out = {"id": doc_id, "tipo": tipo, "titulo": a.get("titulo") or "Anúncio", "data": _iso(a.get("data_postagem"))}
    if tipo == "imagem":
        m = _IMG.search(a.get("conteudo_html") or "")
        out["imagem"] = a.get("imagem") or (m.group(1) if m else "")
        out["legenda"] = a.get("legenda", a.get("titulo") or "")
    elif tipo == "agenda":
        out["agenda"] = a.get("dados_agenda") or {}
    else:
        txt = a.get("conteudo_html") or ""
        if not a.get("renderizar_markdown"):   # HTML antigo: só o texto, sem tag
            txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
        out["tipo"], out["texto"] = "texto", txt
    return out


def listar(limite=30) -> list[dict]:
    with _trava_cache:
        if _cache["lista"] is not None and time.time() - _cache["t"] < CACHE_ANUNCIOS_S:
            return _cache["lista"]
    docs = list(banco.db().collection(COL_ANUNCIOS).stream(timeout=banco.TIMEOUT))
    lista = [_publico(d.id, d.to_dict() or {}) for d in docs]
    lista.sort(key=lambda x: x["data"], reverse=True)
    lista = lista[:limite]
    with _trava_cache:
        _cache["t"], _cache["lista"] = time.time(), lista
    return lista


@router.get("/api/relatorios-publico/anuncios")
def anuncios_publicos():
    if not banco.configurado():
        return {"anuncios": []}
    try:
        return {"anuncios": listar()}
    except Exception:
        return {"anuncios": [], "erro": "Não foi possível carregar os anúncios agora."}


# ── HTML compatível com o admin Streamlit (mod_anuncios.gerar_html_agenda) ──
def html_agenda(d: dict) -> str:
    e = html.escape
    C_CANT, C_TES, C_TES_I, C_MIN, C_MIN_I, C_NVC, C_NVC_I = "#1a78b4", "#1a3566", "#1a5fa8", "#8a6200", "#a07800", "#cc0000", "#1a5fa8"

    def row(it, bg, cor):
        t = str(it.get("titulo", "")).strip()
        if not t:
            return ""
        dur = str(it.get("duracao", "")).strip()
        dur = f'<br><span style="font-size:12px;color:#888;margin-left:4px;">({e(dur)})</span>' if dur else ""
        return (f'<div style="padding:6px 14px;background:{bg};border-bottom:1px solid #e8e8e8;">'
                f'<span style="color:{cor};font-weight:bold;">{e(str(it.get("num", "")))}. {e(t)}</span>{dur}</div>')

    def cab(t, bg):
        return f'<div style="background:{bg};color:white;padding:9px 14px;font-weight:bold;font-size:14.5px;letter-spacing:0.3px;">{t}</div>'

    h = ('<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;border:1px solid #ccc;border-radius:10px;'
         'overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.12);margin:auto;"><div style="padding:12px 14px 8px;background:#ffffff;">'
         f'<div style="font-size:19px;font-weight:bold;color:#111;">{e(d.get("data_texto", ""))}</div>')
    if d.get("escritura"):
        h += f'<div style="color:{C_CANT};font-size:13px;font-weight:bold;margin-top:2px;">{e(d["escritura"])}</div>'
    h += '</div><hr style="margin:0;border:0;border-top:1px solid #ddd;">'
    if d.get("cantico_abertura"):
        h += (f'<div style="padding:7px 14px;font-size:13px;background:#fff;"><span style="color:{C_CANT};font-weight:bold;">'
              f'Cântico {e(d["cantico_abertura"])}</span> e oração | <strong>Comentários iniciais</strong> (1 min)</div>')
    h += '<div style="margin-top:8px;">' + cab("TESOUROS DA PALAVRA DE DEUS", C_TES) + "".join(row(i, "#f0f4ff", C_TES_I) for i in d.get("tesouros", [])) + "</div>"
    h += '<div style="margin-top:8px;">' + cab("FAÇA SEU MELHOR NO MINISTÉRIO", C_MIN) + "".join(row(i, "#fffcf0", C_MIN_I) for i in d.get("ministerio", [])) + "</div>"
    h += '<div style="margin-top:8px;">' + cab("NOSSA VIDA CRISTÃ", C_NVC)
    if d.get("cantico_meio"):
        h += (f'<div style="padding:6px 14px;background:#fff5f5;border-bottom:1px solid #e8e8e8;">'
              f'<span style="color:{C_CANT};font-weight:bold;">Cântico {e(d["cantico_meio"])}</span></div>')
    h += "".join(row(i, "#fff5f5", C_NVC_I) for i in d.get("vida_crista", [])) + "</div>"
    if d.get("cantico_final"):
        h += (f'<hr style="margin:0;border:0;border-top:1px solid #ddd;"><div style="padding:9px 14px;font-size:13px;background:#fff;">'
              f'<strong>Comentários finais</strong> (3 min) | <span style="color:{C_CANT};font-weight:bold;">Cântico {e(d["cantico_final"])}</span> e oração</div>')
    return h + "</div>"


def _itens(lista, inicio) -> list[dict]:
    out = []
    for it in (lista or [])[:12]:
        t = str((it or {}).get("titulo", "")).strip()[:160]
        if t:
            out.append({"num": inicio + len(out) + 1, "titulo": t, "duracao": str((it or {}).get("duracao", "")).strip()[:20]})
    return out


# ── Gestão (dentro do Secretário, com login e permissão "anuncios") ──
def _ctx_editar(request: Request):
    u, p = secretaria._contexto(request)
    if not p["acoes"].get("anuncios"):
        raise HTTPException(403, "Sem permissão para publicar anúncios.")
    return u


@router.get("/api/secretaria/anuncios")
def anuncios_gestao(request: Request):
    secretaria._contexto(request)
    limpar_cache()
    return {"anuncios": listar(100), "link": "/relatorios/"}


@router.post("/api/secretaria/anuncios")
async def anuncio_novo(request: Request):
    u = _ctx_editar(request)
    d = await request.json()
    tipo = d.get("tipo")
    titulo = str(d.get("titulo") or "").strip()[:120]
    doc = {"tipo": tipo, "data_postagem": datetime.now(timezone.utc), "autor": u.get("nome") or u.get("login") or "",
           "origem": "hub"}
    if tipo == "texto":
        txt = str(d.get("texto") or "").strip()[:6000]
        if not txt:
            raise HTTPException(422, "Escreva o conteúdo.")
        doc.update(titulo=titulo or "Anúncio", conteudo_html=txt, renderizar_markdown=True)
    elif tipo == "imagem":
        img = str(d.get("imagem") or "")
        if not re.fullmatch(r"data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+", img):
            raise HTTPException(422, "Imagem inválida.")
        if len(img) > MAX_IMAGEM:
            raise HTTPException(413, "Imagem grande demais — use uma foto menor.")
        leg = html.escape(titulo)
        doc.update(titulo=titulo or "Imagem", renderizar_markdown=False,
                   conteudo_html=(f'<div style="text-align:center;padding:10px;"><img src="{img}" style="max-width:100%;border-radius:8px;" />'
                                  + (f'<p style="margin-top:8px;color:#555;">{leg}</p>' if leg else "") + "</div>"))
    elif tipo == "agenda":
        a = d.get("agenda") or {}
        per = str(a.get("data_texto") or "").strip()[:60]
        if not per:
            raise HTTPException(422, "Informe o período (ex.: 18-24 DE MAIO).")
        tes = _itens(a.get("tesouros"), 0)
        mini = _itens(a.get("ministerio"), len(tes))
        nvc = _itens(a.get("vida_crista"), len(tes) + len(mini))
        ag = {"data_texto": per, "escritura": str(a.get("escritura") or "").strip()[:60],
              "cantico_abertura": str(a.get("cantico_abertura") or "").strip()[:5],
              "cantico_meio": str(a.get("cantico_meio") or "").strip()[:5],
              "cantico_final": str(a.get("cantico_final") or "").strip()[:5],
              "tesouros": tes, "ministerio": mini, "vida_crista": nvc}
        doc.update(titulo=per, renderizar_markdown=False, dados_agenda=ag, conteudo_html=html_agenda(ag))
    else:
        raise HTTPException(422, "Tipo de anúncio inválido.")
    ref = banco.db().collection(COL_ANUNCIOS).document()
    ref.set(doc, timeout=banco.TIMEOUT)
    limpar_cache()
    return {"ok": True, "id": ref.id}


@router.delete("/api/secretaria/anuncios/{aid}")
def anuncio_apagar(aid: str, request: Request):
    _ctx_editar(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", aid):
        raise HTTPException(400, "Anúncio inválido.")
    banco.db().collection(COL_ANUNCIOS).document(aid).delete(timeout=banco.TIMEOUT)
    limpar_cache()
    return {"ok": True}
