"""
hub/weduca.py — WEDUCA · rede de conhecimento da King Star (feed, aprendizagem, documentos…)
─────────────────────────────────────────────────────────────────────────────
As PESSOAS geram a base de conhecimento. Tudo o que é publicado no WEDUCA (postagens,
comentários, fotos, PDFs, vídeos do YouTube com a transcrição) vira conhecimento da IA
do hub (agente.py) na hora — sem aprovação prévia.

  • Entra na base: postagens públicas e os comentários delas (a "conversa" do feed),
    o texto dos PDFs anexados e a descrição/transcrição dos vídeos.
  • NÃO entra: conversas privadas (mensagens diretas) — nunca.
  • Quem publica pode tirar a própria postagem da base ("só no feed").
  • Se alguém marca 👎 "Não resolveu" numa resposta que veio do WEDUCA, a postagem fica
    EM ANÁLISE e cai nas pendências do agente (mesmo fluxo de hoje). Quem alimenta ajusta
    (✏️ DE → PARA vira uma correção na postagem), revisa ou tira da base.

Arquivos (sem serviço pago): fotos (comprimidas no navegador) e PDFs ficam no próprio
Firestore, em pedaços de ~700 KB (weduca_partes). Vídeos: só link do YouTube (canal da
empresa) — o player é embutido e o título vem do oEmbed do YouTube (grátis, sem chave).

Firestore: weduca_posts · weduca_coment · weduca_arquivos · weduca_partes
API: /api/weduca/*   ·   Tela: modulos/weduca.html
"""
from __future__ import annotations

import io
import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

import acesso
import banco

router = APIRouter(prefix="/api/weduca")
MOD = "weduca"
COL_POST, COL_COM, COL_ARQ, COL_PARTE = "weduca_posts", "weduca_coment", "weduca_arquivos", "weduca_partes"

PARTE = 700_000                     # bytes por pedaço (o documento do Firestore aceita até ~1 MB)
MAX_FOTO = 3_000_000                # a foto já chega comprimida do navegador
MAX_PDF = 15_000_000
MAX_TEXTO_PDF = 40_000              # texto extraído de cada PDF que vai para a base
TIPOS_FOTO = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_CACHE_SEG = 20


# ══════════════════════════════════════════════════════════════════════════
# Persistência (trocável nos testes)
# ══════════════════════════════════════════════════════════════════════════
def _fs_listar(col: str) -> list:
    return [{**(d.to_dict() or {}), "id": d.id} for d in banco.db().collection(col).stream(timeout=banco.TIMEOUT)]


def _fs_ler(col: str, doc_id: str) -> Optional[dict]:
    s = banco.db().collection(col).document(doc_id).get(timeout=banco.TIMEOUT)
    return {**(s.to_dict() or {}), "id": s.id} if s.exists else None


def _fs_gravar(col: str, doc_id: str, dados: dict) -> None:
    banco.db().collection(col).document(doc_id).set({k: v for k, v in dados.items() if k != "id"}, timeout=banco.TIMEOUT)


def _fs_marcar(col: str, doc_id: str, campo: str, valor: str, ligar: bool) -> None:
    """Curtir/salvar sem corrida: ArrayUnion/ArrayRemove (duas pessoas ao mesmo tempo não se apagam)."""
    from google.cloud import firestore
    op = firestore.ArrayUnion([valor]) if ligar else firestore.ArrayRemove([valor])
    banco.db().collection(col).document(doc_id).update({campo: op}, timeout=banco.TIMEOUT)


P = {"listar": _fs_listar, "ler": _fs_ler, "gravar": _fs_gravar, "marcar": _fs_marcar}


# ══════════════════════════════════════════════════════════════════════════
# Utilidades, acesso
# ══════════════════════════════════════════════════════════════════════════
def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def novo_id() -> str:
    return uuid.uuid4().hex[:16]


def _ctx(request: Request, acao: Optional[str] = None, texto: str = "") -> tuple:
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(MOD)
    if esq is None:
        raise HTTPException(404, "Módulo WEDUCA não encontrado (falta modulos/weduca.html).")
    p = acesso.permissoes(u, MOD, esq)["acoes"]
    if not (u.get("admin") or p.get("acessar")):
        raise HTTPException(403, "Sem acesso ao WEDUCA.")
    if acao and not (u.get("admin") or p.get(acao)):
        raise HTTPException(403, f"Sem permissão para {texto or acao}.")
    if not banco.configurado():
        raise HTTPException(503, "Banco não configurado: falta FIRESTORE_CREDS no Render.")
    return u, {k: bool(u.get("admin") or p.get(k)) for k in ("publicar", "comentar", "moderar")}


def _quem(u: dict) -> dict:
    return {"login": str(u.get("login") or "").lower(), "nome": u.get("nome") or u.get("login") or ""}


def _eu(u: dict) -> str:
    return str(u.get("login") or "").lower()


# ══════════════════════════════════════════════════════════════════════════
# Leitura com cache curto (o feed e a IA leem muito; quem grava esquece o cache)
# ══════════════════════════════════════════════════════════════════════════
_cache = {"t": 0.0, "posts": [], "com": []}


def esquecer() -> None:
    _cache["t"] = 0.0
    try:
        import agente
        agente.esquecer_cache()
    except Exception:   # noqa: BLE001
        pass


def _dados() -> tuple:
    if time.time() - _cache["t"] > _CACHE_SEG:
        _cache.update(t=time.time(), posts=P["listar"](COL_POST), com=P["listar"](COL_COM))
    return _cache["posts"], _cache["com"]


def posts_ativos() -> list:
    return [p for p in _dados()[0] if p.get("status", "ativo") == "ativo"]


def comentarios_de(pid: str) -> list:
    return sorted((c for c in _dados()[1] if c.get("post_id") == pid and c.get("status", "ativo") == "ativo"), key=lambda c: c.get("em") or "")


# ══════════════════════════════════════════════════════════════════════════
# YouTube (só link — o canal da empresa hospeda tudo)
# ══════════════════════════════════════════════════════════════════════════
_YT = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/|youtube-nocookie\.com/embed/)([A-Za-z0-9_-]{11})")


def youtube_id(url: str) -> Optional[str]:
    m = _YT.search(str(url or ""))
    return m.group(1) if m else None


def youtube_titulo(vid: str) -> str:
    """Título do vídeo pelo oEmbed público do YouTube (sem chave). Se falhar, segue sem título."""
    try:
        u = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/watch?v={vid}", safe="")
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Hub-WEDUCA/1.0"}), timeout=6) as r:
            d = json.load(r)
        return str(d.get("title") or "")[:200]
    except Exception:   # noqa: BLE001
        return ""


# ══════════════════════════════════════════════════════════════════════════
# Arquivos: fotos e PDFs no Firestore, em pedaços
# ══════════════════════════════════════════════════════════════════════════
def texto_do_pdf(dados: bytes) -> tuple:
    """(texto, páginas). PDF escaneado (só imagem) devolve texto vazio — vai sem texto para a base."""
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(dados))
        partes, total = [], 0
        for pg in r.pages:
            t = (pg.extract_text() or "").strip()
            if t:
                partes.append(t); total += len(t)
            if total >= MAX_TEXTO_PDF:
                break
        return re.sub(r"[ \t]+", " ", "\n".join(partes))[:MAX_TEXTO_PDF], len(r.pages)
    except Exception:   # noqa: BLE001
        return "", 0


def gravar_arquivo(u: dict, nome: str, tipo: str, dados: bytes) -> dict:
    tipo = (tipo or "").split(";")[0].strip().lower()
    nome = re.sub(r"[\\/\x00-\x1f]", "", nome or "arquivo")[:120] or "arquivo"
    if tipo in TIPOS_FOTO:
        if len(dados) > MAX_FOTO:
            raise HTTPException(413, "Foto grande demais (máx. 3 MB depois de comprimida).")
        kind = "foto"
    elif tipo == "application/pdf" or nome.lower().endswith(".pdf"):
        if not dados.startswith(b"%PDF"):
            raise HTTPException(400, "Esse arquivo não é um PDF válido.")
        if len(dados) > MAX_PDF:
            raise HTTPException(413, "PDF grande demais (máx. 15 MB).")
        tipo, kind = "application/pdf", "pdf"
    else:
        raise HTTPException(415, "Envie foto (JPG, PNG, WEBP, GIF) ou PDF. Vídeo: use o link do YouTube.")
    if not dados:
        raise HTTPException(400, "Arquivo vazio.")
    aid = novo_id()
    n = 0
    for i in range(0, len(dados), PARTE):
        P["gravar"](COL_PARTE, f"{aid}_{n}", {"arq": aid, "i": n, "dados": dados[i:i + PARTE]})
        n += 1
    meta = {"id": aid, "nome": nome, "tipo": tipo, "kind": kind, "tam": len(dados), "partes": n, "dono": _quem(u), "em": agora(), "post_id": None}
    if kind == "pdf":
        meta["texto"], meta["paginas"] = texto_do_pdf(dados)
    P["gravar"](COL_ARQ, aid, meta)
    return meta


def ler_arquivo(aid: str) -> tuple:
    meta = P["ler"](COL_ARQ, aid)
    if not meta:
        raise HTTPException(404, "Arquivo não encontrado.")
    pedacos = []
    for i in range(int(meta.get("partes") or 0)):
        p = P["ler"](COL_PARTE, f"{aid}_{i}")
        if not p:
            raise HTTPException(500, "Arquivo incompleto no banco.")
        pedacos.append(bytes(p.get("dados") or b""))
    return meta, b"".join(pedacos)


def _midia_publica(m: dict) -> dict:
    return {k: m.get(k) for k in ("id", "nome", "tipo", "kind", "tam", "paginas", "w", "h") if m.get(k) is not None}


# ══════════════════════════════════════════════════════════════════════════
# O que a IA lê: cada postagem (com os comentários) vira um "artigo" para o agente
# ══════════════════════════════════════════════════════════════════════════
def _data_br(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


def _blocos(texto: str, tam: int = 600) -> list:
    """Quebra um texto longo em trechos (parágrafos de até `tam` letras) — é assim que o agente pontua e lê."""
    saida = []
    for par in re.split(r"\n\s*\n|\n", str(texto or "")):
        par = par.strip()
        while len(par) > tam:
            corte = par.rfind(" ", 0, tam)
            corte = corte if corte > tam // 2 else tam
            saida.append(par[:corte]); par = par[corte:].strip()
        if par:
            saida.append(par)
    return saida


def como_artigo(p: dict, comentarios: list) -> dict:
    autor = (p.get("autor") or {}).get("nome", "")
    rev = "revisada" if p.get("revisado") else "não revisada"
    tit = (p.get("video") or {}).get("titulo") or (_blocos(p.get("texto"), 90) or [""])[0] or "Postagem"
    passos = [f"Correção ({(c.get('por') or {}).get('nome', '')}): {c.get('texto')}" for c in (p.get("correcoes") or [])]
    passos += _blocos(p.get("texto"))
    if p.get("transcricao"):
        passos += ["Vídeo — descrição/transcrição:"] + _blocos(p.get("transcricao"))
    for m in p.get("pdfs_texto") or []:
        passos += [f"PDF “{m.get('nome')}”:"] + _blocos(m.get("texto"))[:60]
    for c in comentarios:
        passos.append(f"Comentário de {(c.get('autor') or {}).get('nome', '')}: {c.get('texto')}")
    tags = " ".join(re.findall(r"#(\w+)", p.get("texto") or ""))
    return {"id": f"weduca:{p['id']}", "origem": "weduca", "post_id": p["id"], "ativo": True,
            "titulo": f"{tit} — postagem de {autor} no WEDUCA em {_data_br(p.get('em'))} ({rev})",
            "palavras": f"{tags} {autor} {(p.get('video') or {}).get('titulo', '')}".strip(),
            "passos": passos[:120], "versao": int(p.get("versao") or 1),
            "atualizado_em": p.get("editado_em") or p.get("em"), "atualizado_por": p.get("autor")}


def base_conhecimento() -> list:
    """Chamado pelo agente a cada pergunta (com cache): postagens públicas que estão na base."""
    try:
        if not banco.configurado():
            return []
        return [como_artigo(p, comentarios_de(p["id"])) for p in posts_ativos() if p.get("base", True)]
    except Exception as e:   # noqa: BLE001 — a IA nunca pode cair por causa do WEDUCA
        print(f"[weduca] base indisponível: {type(e).__name__}: {e}")
        return []


def nao_resolveu(post_id: str, u: dict, obs: str) -> None:
    """👎 numa resposta que veio do WEDUCA: a postagem fica EM ANÁLISE (a pendência é criada pelo agente)."""
    p = P["ler"](COL_POST, post_id)
    if p:
        p["analise"] = {"em": agora(), "por": _quem(u), "obs": (obs or "")[:300]}
        P["gravar"](COL_POST, post_id, p); esquecer()


def ajustar(post_id: str, de: str, para: str, u: dict) -> dict:
    """✏️ DE → PARA de quem alimenta o agente: vira uma CORREÇÃO visível na postagem (vale mais que o texto)."""
    p = P["ler"](COL_POST, post_id)
    if not p:
        raise HTTPException(404, "Postagem não encontrada.")
    p.setdefault("correcoes", []).append({"texto": f"onde se dizia “{de}”, o correto é: {para}", "por": _quem(u), "em": agora()})
    p.update(analise=None, versao=int(p.get("versao") or 1) + 1)
    P["gravar"](COL_POST, post_id, p); esquecer()
    return {"modo": "correcao", "onde": "correção na postagem do WEDUCA"}


# ══════════════════════════════════════════════════════════════════════════
# Feed
# ══════════════════════════════════════════════════════════════════════════
def _pode_mexer(p: dict, u: dict, pode: dict) -> bool:
    return pode["moderar"] or (p.get("autor") or {}).get("login") == _eu(u)


def publico(p: dict, u: dict, pode: dict, todos_coment: bool = False) -> dict:
    eu = _eu(u)
    com = comentarios_de(p["id"])
    curt = list(p.get("curtidas") or [])
    return {"id": p["id"], "autor": p.get("autor"), "em": p.get("em"), "editado_em": p.get("editado_em"),
            "texto": p.get("texto") or "", "midias": p.get("midias") or [], "video": p.get("video"),
            "transcricao": p.get("transcricao") or "", "base": p.get("base", True), "revisado": bool(p.get("revisado")),
            "analise": p.get("analise") if pode["moderar"] or (p.get("autor") or {}).get("login") == eu else bool(p.get("analise")),
            "correcoes": p.get("correcoes") or [], "curtidas": len(curt), "curti": eu in curt, "salvei": eu in (p.get("salvos") or []),
            "n_coment": len(com), "comentarios": [_com_publico(c, u, pode) for c in (com if todos_coment else com[-3:])],
            "pode_mexer": _pode_mexer(p, u, pode)}


def _com_publico(c: dict, u: dict, pode: dict) -> dict:
    return {"id": c["id"], "autor": c.get("autor"), "em": c.get("em"), "texto": c.get("texto"),
            "pode_mexer": pode["moderar"] or (c.get("autor") or {}).get("login") == _eu(u)}


def _tipo(p: dict) -> set:
    t = {m.get("kind") for m in p.get("midias") or []}
    if p.get("video"):
        t.add("video")
    return t


@router.get("/me")
def weduca_me(request: Request):
    u, pode = _ctx(request)
    return {"login": _eu(u), "nome": u.get("nome") or u.get("login"), "pode": pode}


@router.get("/feed")
def weduca_feed(request: Request, filtro: str = "", q: str = "", antes: str = "", n: int = 15):
    u, pode = _ctx(request)
    eu = _eu(u)
    lst = posts_ativos()
    if filtro in ("foto", "pdf", "video"):
        lst = [p for p in lst if filtro in _tipo(p)]
    elif filtro == "salvos":
        lst = [p for p in lst if eu in (p.get("salvos") or [])]
    elif filtro == "meus":
        lst = [p for p in lst if (p.get("autor") or {}).get("login") == eu]
    elif filtro == "analise":
        lst = [p for p in lst if p.get("analise")]
    if q.strip():
        import agente
        termos = agente.palavras(q)
        def tem(p):
            alvo = agente.sem_acento(" ".join([p.get("texto") or "", p.get("transcricao") or "", (p.get("autor") or {}).get("nome", ""),
                                                 (p.get("video") or {}).get("titulo", "")] + [m.get("nome", "") for m in p.get("midias") or []]
                                                + [c.get("texto") or "" for c in comentarios_de(p["id"])]))
            return all(t in alvo for t in termos)
        lst = [p for p in lst if tem(p)]
    lst.sort(key=lambda p: p.get("em") or "", reverse=True)
    if antes:
        lst = [p for p in lst if (p.get("em") or "") < antes]
    n = max(1, min(int(n or 15), 40))
    pagina = lst[:n]
    return {"posts": [publico(p, u, pode) for p in pagina], "mais": len(lst) > n, "agora": agora()}


@router.get("/novidades")
def weduca_novidades(request: Request, desde: str = ""):
    """Tempo real (o feed pergunta a cada 20 s): quantas postagens novas de OUTRAS pessoas desde `desde`."""
    u, _ = _ctx(request)
    eu = _eu(u)
    novas = [p for p in posts_ativos() if (p.get("em") or "") > desde and (p.get("autor") or {}).get("login") != eu]
    return {"novas": len(novas), "agora": agora()}


@router.get("/destaques")
def weduca_destaques(request: Request):
    """Coluna da direita: quem mais compartilha e as postagens mais curtidas."""
    u, pode = _ctx(request)
    posts = posts_ativos()
    autores: dict = {}
    for p in posts:
        a = p.get("autor") or {}
        x = autores.setdefault(a.get("login"), {"login": a.get("login"), "nome": a.get("nome"), "posts": 0, "curtidas": 0})
        x["posts"] += 1; x["curtidas"] += len(p.get("curtidas") or [])
    top = sorted(autores.values(), key=lambda x: (-x["posts"], -x["curtidas"]))[:5]
    curtidas = sorted((p for p in posts if p.get("curtidas")), key=lambda p: -len(p.get("curtidas") or []))[:4]
    return {"pessoas": top, "mais_curtidas": [{"id": p["id"], "autor": p.get("autor"), "texto": (p.get("texto") or (p.get("video") or {}).get("titulo") or "")[:120],
                                               "curtidas": len(p.get("curtidas") or [])} for p in curtidas],
            "na_base": sum(1 for p in posts if p.get("base", True)), "total": len(posts),
            "em_analise": sum(1 for p in posts if p.get("analise")) if pode["moderar"] else None}


@router.get("/posts/{pid}")
def weduca_post(pid: str, request: Request):
    u, pode = _ctx(request)
    p = P["ler"](COL_POST, pid)
    if not p or p.get("status", "ativo") != "ativo":
        raise HTTPException(404, "Essa postagem não existe mais.")
    return publico(p, u, pode, todos_coment=True)


class Post(BaseModel):
    texto: str = ""
    midias: List[str] = []          # ids de /arquivos
    video_url: Optional[str] = ""
    transcricao: Optional[str] = ""
    base: bool = True               # entra na base de conhecimento da IA

    @field_validator("texto", "transcricao")
    @classmethod
    def _t(cls, v):
        return str(v or "").strip()[:20000]


def _montar(payload: Post, u: dict, p: dict) -> dict:
    vid = None
    if (payload.video_url or "").strip():
        yid = youtube_id(payload.video_url)
        if not yid:
            raise HTTPException(400, "Link do YouTube inválido. Cole o link do vídeo (youtube.com/watch?v=… ou youtu.be/…).")
        antigo = p.get("video") or {}
        vid = {"id": yid, "url": f"https://www.youtube.com/watch?v={yid}",
               "titulo": antigo.get("titulo") if antigo.get("id") == yid else youtube_titulo(yid)}
    midias, pdfs = [], []
    for aid in payload.midias[:10]:
        m = P["ler"](COL_ARQ, aid)
        if not m:
            raise HTTPException(400, "Um dos anexos não foi encontrado — envie de novo.")
        if m.get("post_id") not in (None, p.get("id")):
            raise HTTPException(400, "Esse anexo já pertence a outra postagem.")
        midias.append(_midia_publica(m))
        if m.get("kind") == "pdf":
            pdfs.append({"nome": m.get("nome"), "texto": m.get("texto") or ""})
    if not (payload.texto or midias or vid):
        raise HTTPException(400, "Escreva algo, anexe uma foto/PDF ou cole o link do vídeo.")
    p.update(texto=payload.texto, midias=midias, pdfs_texto=pdfs, video=vid, transcricao=payload.transcricao or "", base=bool(payload.base))
    return p


@router.post("/posts")
def weduca_postar(payload: Post, request: Request):
    u, pode = _ctx(request, "publicar", "publicar no feed")
    pid = novo_id()
    p = _montar(payload, u, {"id": pid})
    p.update(autor=_quem(u), em=agora(), status="ativo", curtidas=[], salvos=[], versao=1, revisado=False, analise=None, correcoes=[])
    P["gravar"](COL_POST, pid, p)
    for m in p["midias"]:
        meta = P["ler"](COL_ARQ, m["id"])
        if meta:
            meta["post_id"] = pid; P["gravar"](COL_ARQ, m["id"], meta)
    esquecer()
    return publico(p, u, pode)


@router.put("/posts/{pid}")
def weduca_editar(pid: str, payload: Post, request: Request):
    u, pode = _ctx(request)
    p = P["ler"](COL_POST, pid)
    if not p or p.get("status", "ativo") != "ativo":
        raise HTTPException(404, "Postagem não encontrada.")
    if not _pode_mexer(p, u, pode):
        raise HTTPException(403, "Só quem publicou (ou quem modera) edita esta postagem.")
    _montar(payload, u, p)
    p.update(editado_em=agora(), editado_por=_quem(u), versao=int(p.get("versao") or 1) + 1)
    P["gravar"](COL_POST, pid, p)
    for m in p["midias"]:
        meta = P["ler"](COL_ARQ, m["id"])
        if meta and meta.get("post_id") != pid:
            meta["post_id"] = pid; P["gravar"](COL_ARQ, m["id"], meta)
    esquecer()
    return publico(p, u, pode)


@router.delete("/posts/{pid}")
def weduca_excluir(pid: str, request: Request):
    u, pode = _ctx(request)
    p = P["ler"](COL_POST, pid)
    if not p:
        raise HTTPException(404, "Postagem não encontrada.")
    if not _pode_mexer(p, u, pode):
        raise HTTPException(403, "Só quem publicou (ou quem modera) exclui esta postagem.")
    p.update(status="removido", removido_em=agora(), removido_por=_quem(u))   # sai do feed e da base (fica guardada)
    P["gravar"](COL_POST, pid, p); esquecer()
    return {"ok": True}


class Base(BaseModel):
    base: bool


@router.post("/posts/{pid}/base")
def weduca_base(pid: str, payload: Base, request: Request):
    """Entra / sai da base de conhecimento da IA (quem publicou ou quem modera)."""
    u, pode = _ctx(request)
    p = P["ler"](COL_POST, pid)
    if not p or p.get("status", "ativo") != "ativo":
        raise HTTPException(404, "Postagem não encontrada.")
    if not _pode_mexer(p, u, pode):
        raise HTTPException(403, "Só quem publicou (ou quem modera) muda isso.")
    p["base"] = payload.base
    P["gravar"](COL_POST, pid, p); esquecer()
    return {"ok": True, "base": p["base"]}


@router.post("/posts/{pid}/revisar")
def weduca_revisar(pid: str, request: Request):
    """Quem modera confere a postagem: ela passa a ir para a IA como "revisada" e sai de análise."""
    u, _ = _ctx(request, "moderar", "moderar o WEDUCA")
    p = P["ler"](COL_POST, pid)
    if not p:
        raise HTTPException(404, "Postagem não encontrada.")
    p.update(revisado=True, revisado_por=_quem(u), revisado_em=agora(), analise=None)
    P["gravar"](COL_POST, pid, p); esquecer()
    return {"ok": True}


def _alternar(pid: str, request: Request, campo: str) -> dict:
    u, _ = _ctx(request)
    p = P["ler"](COL_POST, pid)
    if not p or p.get("status", "ativo") != "ativo":
        raise HTTPException(404, "Postagem não encontrada.")
    eu = _eu(u)
    ligar = eu not in (p.get(campo) or [])
    P["marcar"](COL_POST, pid, campo, eu, ligar)
    lst = [x for x in (p.get(campo) or []) if x != eu] + ([eu] if ligar else [])
    for x in _cache["posts"]:
        if x.get("id") == pid:
            x[campo] = lst
    return {"ligado": ligar, "total": len(lst)}


@router.post("/posts/{pid}/curtir")
def weduca_curtir(pid: str, request: Request):
    return _alternar(pid, request, "curtidas")


@router.post("/posts/{pid}/salvar")
def weduca_salvar(pid: str, request: Request):
    return _alternar(pid, request, "salvos")


class Comentario(BaseModel):
    texto: str

    @field_validator("texto")
    @classmethod
    def _t(cls, v):
        v = str(v or "").strip()
        if not v:
            raise ValueError("Escreva o comentário.")
        return v[:3000]


@router.post("/posts/{pid}/comentarios")
def weduca_comentar(pid: str, payload: Comentario, request: Request):
    u, pode = _ctx(request, "comentar", "comentar")
    p = P["ler"](COL_POST, pid)
    if not p or p.get("status", "ativo") != "ativo":
        raise HTTPException(404, "Postagem não encontrada.")
    cid = novo_id()
    c = {"id": cid, "post_id": pid, "autor": _quem(u), "em": agora(), "texto": payload.texto, "status": "ativo"}
    P["gravar"](COL_COM, cid, c)
    _cache["com"].append(c)   # aparece na hora; a IA relê no próximo ciclo
    esquecer()
    return _com_publico(c, u, pode)


@router.delete("/comentarios/{cid}")
def weduca_apagar_comentario(cid: str, request: Request):
    u, pode = _ctx(request)
    c = P["ler"](COL_COM, cid)
    if not c:
        raise HTTPException(404, "Comentário não encontrado.")
    if not (pode["moderar"] or (c.get("autor") or {}).get("login") == _eu(u)):
        raise HTTPException(403, "Só quem comentou (ou quem modera) apaga.")
    c.update(status="removido", removido_em=agora(), removido_por=_quem(u))
    P["gravar"](COL_COM, cid, c); esquecer()
    return {"ok": True}


# ── anexos ──
@router.post("/arquivos")
async def weduca_enviar(request: Request):
    """Corpo = o arquivo cru (sem multipart). Cabeçalhos: Content-Type e X-Nome (nome do arquivo, URL-encoded)."""
    u, _ = _ctx(request, "publicar", "publicar no feed")
    dados = await request.body()
    nome = urllib.parse.unquote(request.headers.get("x-nome") or "arquivo")
    meta = gravar_arquivo(u, nome, request.headers.get("content-type") or "", dados)
    w, h = request.headers.get("x-largura"), request.headers.get("x-altura")
    if meta["kind"] == "foto" and w and h and w.isdigit() and h.isdigit():
        meta.update(w=int(w), h=int(h)); P["gravar"](COL_ARQ, meta["id"], meta)
    return {**_midia_publica(meta), "tem_texto": bool(meta.get("texto"))}


@router.get("/arquivos/{aid}")
def weduca_arquivo(aid: str, request: Request):
    _ctx(request)
    meta, dados = ler_arquivo(aid)
    nome = urllib.parse.quote(meta.get("nome") or "arquivo")
    return Response(dados, media_type=meta.get("tipo") or "application/octet-stream",
                    headers={"Cache-Control": "private, max-age=86400", "Content-Disposition": f"inline; filename*=UTF-8''{nome}"})
