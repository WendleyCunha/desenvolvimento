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
COL_CURSO, COL_AULA, COL_PROG = "weduca_cursos", "weduca_aulas", "weduca_progresso"   # Aprendizagem

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
    return u, {k: bool(u.get("admin") or p.get(k)) for k in ("publicar", "comentar", "moderar", "cursos")}


def _quem(u: dict) -> dict:
    return {"login": str(u.get("login") or "").lower(), "nome": u.get("nome") or u.get("login") or ""}


def _eu(u: dict) -> str:
    return str(u.get("login") or "").lower()


# ══════════════════════════════════════════════════════════════════════════
# Leitura com cache curto (o feed e a IA leem muito; quem grava esquece o cache)
# ══════════════════════════════════════════════════════════════════════════
_cache = {"t": 0.0, "posts": [], "com": [], "cursos": [], "aulas": []}


def esquecer() -> None:
    _cache["t"] = 0.0
    try:
        import agente
        agente.esquecer_cache()
    except Exception:   # noqa: BLE001
        pass


def _dados() -> tuple:
    if time.time() - _cache["t"] > _CACHE_SEG:
        _cache.update(t=time.time(), posts=P["listar"](COL_POST), com=P["listar"](COL_COM),
                      cursos=P["listar"](COL_CURSO), aulas=P["listar"](COL_AULA))
    return _cache["posts"], _cache["com"], _cache["cursos"], _cache["aulas"]


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
    return {"id": f"weduca:{p['id']}", "origem": "weduca", "post_id": p["id"], "hash": f"post={p['id']}", "ativo": True,
            "titulo": f"{tit} — postagem de {autor} no WEDUCA em {_data_br(p.get('em'))} ({rev})",
            "palavras": f"{tags} {autor} {(p.get('video') or {}).get('titulo', '')}".strip(),
            "passos": passos[:120], "versao": int(p.get("versao") or 1),
            "atualizado_em": p.get("editado_em") or p.get("em"), "atualizado_por": p.get("autor")}


def base_conhecimento() -> list:
    """Chamado pelo agente a cada pergunta (com cache): postagens públicas que estão na base."""
    try:
        if not banco.configurado():
            return []
        posts = [como_artigo(p, comentarios_de(p["id"])) for p in posts_ativos() if p.get("base", True)]
        return posts + aulas_na_base()
    except Exception as e:   # noqa: BLE001 — a IA nunca pode cair por causa do WEDUCA
        print(f"[weduca] base indisponível: {type(e).__name__}: {e}")
        return []


def nao_resolveu(post_id: str, u: dict, obs: str) -> None:
    """👎 numa resposta que veio do WEDUCA: a postagem (ou a aula) fica EM ANÁLISE (a pendência é criada pelo agente)."""
    col, post_id = (COL_AULA, post_id[5:]) if post_id.startswith("aula:") else (COL_POST, post_id)
    p = P["ler"](col, post_id)
    if p:
        p["analise"] = {"em": agora(), "por": _quem(u), "obs": (obs or "")[:300]}
        P["gravar"](col, post_id, p); esquecer()


def ajustar(post_id: str, de: str, para: str, u: dict) -> dict:
    """✏️ DE → PARA de quem alimenta o agente: vira uma CORREÇÃO visível na postagem/aula (vale mais que o texto)."""
    col, post_id = (COL_AULA, post_id[5:]) if post_id.startswith("aula:") else (COL_POST, post_id)
    p = P["ler"](col, post_id)
    if not p:
        raise HTTPException(404, "Postagem não encontrada.")
    p.setdefault("correcoes", []).append({"texto": f"onde se dizia “{de}”, o correto é: {para}", "por": _quem(u), "em": agora()})
    p.update(analise=None, versao=int(p.get("versao") or 1) + 1)
    P["gravar"](col, post_id, p); esquecer()
    return {"modo": "correcao", "onde": "correção na " + ("aula" if col == COL_AULA else "postagem") + " do WEDUCA"}


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
    u, pode = _ctx(request)
    if not (pode["publicar"] or pode["cursos"]):
        raise HTTPException(403, "Sem permissão para enviar arquivos.")
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


# ══════════════════════════════════════════════════════════════════════════
# APRENDIZAGEM — cursos feitos pela própria equipe (aulas de vídeo, texto, PDF e fotos),
# progresso de cada pessoa, avaliação com nota mínima e certificado.
# Cada aula de curso PUBLICADO entra na base da IA (com as dúvidas da aula).
# A avaliação NÃO entra na base (as respostas certas não vazam pela IA).
# ══════════════════════════════════════════════════════════════════════════
STATUS_CURSO = ("rascunho", "publicado", "arquivado")
TIPOS_AULA = ("video", "texto", "pdf")


def cursos_todos() -> list:
    return list(_dados()[2])


def aulas_de(cid: str) -> list:
    return sorted((a for a in _dados()[3] if a.get("curso_id") == cid and a.get("status", "ativo") == "ativo"),
                  key=lambda a: (a.get("ordem", 0), a.get("em") or ""))


def _pode_editar_curso(c: dict, u: dict, pode: dict) -> bool:
    return pode["moderar"] or (pode["cursos"] and (c.get("autor") or {}).get("login") == _eu(u))


def _visivel(c: dict, u: dict, pode: dict) -> bool:
    return c.get("status") == "publicado" or _pode_editar_curso(c, u, pode)


def _prog_id(login: str, cid: str) -> str:
    return f"{login}__{cid}"


def progresso(login: str, cid: str) -> dict:
    return P["ler"](COL_PROG, _prog_id(login, cid)) or {"login": login, "curso_id": cid, "aulas": [], "quiz": None, "concluido_em": None}


def _pct(prog: dict, aulas: list) -> int:
    ids = {a["id"] for a in aulas}
    feitas = len(ids & set(prog.get("aulas") or []))
    return round(100 * feitas / len(ids)) if ids else 0


def _tem_quiz(c: dict) -> bool:
    return bool(((c.get("quiz") or {}).get("perguntas")))


def _resumo_curso(c: dict, u: dict, pode: dict, prog: Optional[dict] = None) -> dict:
    aulas = aulas_de(c["id"])
    prog = prog or progresso(_eu(u), c["id"])
    return {"id": c["id"], "titulo": c.get("titulo"), "descricao": c.get("descricao") or "", "categoria": c.get("categoria") or "Geral",
            "capa": c.get("capa"), "obrigatorio": bool(c.get("obrigatorio")), "status": c.get("status"), "base": c.get("base", True),
            "autor": c.get("autor"), "em": c.get("em"), "atualizado_em": c.get("atualizado_em"),
            "n_aulas": len(aulas), "minutos": sum(int(a.get("minutos") or 0) for a in aulas), "tem_quiz": _tem_quiz(c),
            "nota_min": int((c.get("quiz") or {}).get("nota_min") or 70), "pct": _pct(prog, aulas),
            "iniciado": bool(prog.get("aulas") or prog.get("inicio")), "concluido_em": prog.get("concluido_em"),
            "ultima_aula": prog.get("ultima_aula"), "pode_editar": _pode_editar_curso(c, u, pode)}


def _aula_publica(a: dict, u: dict, pode: dict, editor: bool) -> dict:
    d = {k: a.get(k) for k in ("id", "curso_id", "titulo", "tipo", "texto", "video", "transcricao", "midias", "minutos", "ordem", "correcoes", "base")}
    d["midias"] = d.get("midias") or []
    d["correcoes"] = d.get("correcoes") or []
    d["analise"] = a.get("analise") if editor else bool(a.get("analise"))
    d["n_duvidas"] = len(comentarios_de("aula:" + a["id"]))
    return d


def aulas_na_base() -> list:
    saida = []
    cursos = {c["id"]: c for c in cursos_todos() if c.get("status") == "publicado" and c.get("base", True)}
    for a in _dados()[3]:
        c = cursos.get(a.get("curso_id"))
        if not c or a.get("status", "ativo") != "ativo" or a.get("base") is False:
            continue
        autor = (c.get("autor") or {}).get("nome", "")
        passos = [f"Correção ({(x.get('por') or {}).get('nome', '')}): {x.get('texto')}" for x in (a.get("correcoes") or [])]
        if c.get("descricao"):
            passos.append(f"Sobre o curso: {c['descricao'][:400]}")
        passos += _blocos(a.get("texto"))
        if a.get("transcricao"):
            passos += ["Vídeo da aula — descrição/transcrição:"] + _blocos(a.get("transcricao"))
        for m in a.get("pdfs_texto") or []:
            passos += [f"PDF “{m.get('nome')}”:"] + _blocos(m.get("texto"))[:60]
        for x in comentarios_de("aula:" + a["id"]):
            passos.append(f"Dúvida/comentário de {(x.get('autor') or {}).get('nome', '')}: {x.get('texto')}")
        saida.append({"id": f"weduca:aula:{a['id']}", "origem": "weduca", "post_id": None, "aula_id": a["id"], "curso_id": c["id"],
                      "hash": f"curso={c['id']}&aula={a['id']}", "ativo": True,
                      "titulo": f"Aula “{a.get('titulo')}” do curso “{c.get('titulo')}” no WEDUCA (de {autor})",
                      "palavras": f"{c.get('titulo', '')} {c.get('categoria', '')} {a.get('titulo', '')} {(a.get('video') or {}).get('titulo', '')}",
                      "passos": passos[:120], "versao": int(a.get("versao") or 1),
                      "atualizado_em": a.get("editado_em") or a.get("em"), "atualizado_por": c.get("autor")})
    return saida


# ── cursos ──
class Pergunta(BaseModel):
    texto: str
    opcoes: List[str]
    correta: int

    @field_validator("texto")
    @classmethod
    def _t(cls, v):
        v = str(v or "").strip()
        if not v:
            raise ValueError("Escreva o enunciado de cada pergunta.")
        return v[:600]

    @field_validator("opcoes")
    @classmethod
    def _o(cls, v):
        v = [str(x).strip()[:300] for x in (v or []) if str(x).strip()]
        if len(v) < 2:
            raise ValueError("Cada pergunta precisa de pelo menos 2 alternativas.")
        return v[:6]


class Quiz(BaseModel):
    nota_min: int = 70
    perguntas: List[Pergunta] = []


class Curso(BaseModel):
    titulo: str
    descricao: str = ""
    categoria: str = "Geral"
    capa: Optional[str] = None          # id de foto em /arquivos (opcional — sem foto, a capa é gerada)
    obrigatorio: bool = False
    status: str = "rascunho"
    base: bool = True                   # as aulas entram na base da IA quando o curso está publicado
    quiz: Optional[Quiz] = None

    @field_validator("titulo")
    @classmethod
    def _t(cls, v):
        v = str(v or "").strip()
        if not v:
            raise ValueError("Dê um título ao curso.")
        return v[:140]

    @field_validator("descricao")
    @classmethod
    def _d(cls, v):
        return str(v or "").strip()[:4000]

    @field_validator("categoria")
    @classmethod
    def _c(cls, v):
        return str(v or "").strip()[:60] or "Geral"

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        if v not in STATUS_CURSO:
            raise ValueError("Status inválido.")
        return v


def _aplicar_curso(payload: Curso, c: dict) -> dict:
    if payload.capa:
        m = P["ler"](COL_ARQ, payload.capa)
        if not m or m.get("kind") != "foto":
            raise HTTPException(400, "A capa precisa ser uma foto enviada pelo WEDUCA.")
    quiz = None
    if payload.quiz and payload.quiz.perguntas:
        for q in payload.quiz.perguntas:
            if not 0 <= q.correta < len(q.opcoes):
                raise HTTPException(400, f"Marque a alternativa certa da pergunta “{q.texto[:40]}”.")
        quiz = {"nota_min": max(0, min(int(payload.quiz.nota_min), 100)),
                "perguntas": [{"id": novo_id()[:8], **q.model_dump()} for q in payload.quiz.perguntas[:40]]}
    if payload.status == "publicado" and c.get("id") and not aulas_de(c["id"]):
        raise HTTPException(400, "Adicione pelo menos uma aula antes de publicar.")
    c.update(titulo=payload.titulo, descricao=payload.descricao, categoria=payload.categoria, capa=payload.capa,
             obrigatorio=payload.obrigatorio, status=payload.status, base=payload.base, quiz=quiz)
    return c


def _curso_ou_404(cid: str) -> dict:
    c = P["ler"](COL_CURSO, cid)
    if not c or c.get("status") == "excluido":
        raise HTTPException(404, "Curso não encontrado.")
    return c


@router.get("/cursos")
def weduca_cursos(request: Request):
    u, pode = _ctx(request)
    eu = _eu(u)
    progs = {p.get("curso_id"): p for p in _progresso_de(eu)}
    lst = [_resumo_curso(c, u, pode, progs.get(c["id"])) for c in cursos_todos() if c.get("status") != "excluido" and _visivel(c, u, pode)]
    lst.sort(key=lambda c: c.get("atualizado_em") or c.get("em") or "", reverse=True)        # mais recentes primeiro…
    lst.sort(key=lambda c: (c["status"] != "publicado", not c["obrigatorio"]))              # …publicados e obrigatórios na frente
    return {"cursos": lst, "pode_criar": pode["cursos"] or pode["moderar"],
            "categorias": sorted({c["categoria"] for c in lst})}


def _progresso_de(login: str) -> list:
    return [p for p in P["listar"](COL_PROG) if p.get("login") == login]


@router.get("/cursos/{cid}")
def weduca_curso(cid: str, request: Request):
    u, pode = _ctx(request)
    c = _curso_ou_404(cid)
    if not _visivel(c, u, pode):
        raise HTTPException(404, "Curso não encontrado.")
    editor = _pode_editar_curso(c, u, pode)
    prog = progresso(_eu(u), cid)
    quiz = c.get("quiz") or {}
    perguntas = quiz.get("perguntas") or []
    return {**_resumo_curso(c, u, pode, prog), "aulas": [_aula_publica(a, u, pode, editor) for a in aulas_de(cid)],
            "feitas": prog.get("aulas") or [], "quiz_resultado": prog.get("quiz"),
            "quiz": ({"nota_min": quiz.get("nota_min", 70), "perguntas": perguntas} if editor
                     else {"nota_min": quiz.get("nota_min", 70), "perguntas": [{"id": q["id"], "texto": q["texto"], "opcoes": q["opcoes"]} for q in perguntas]})}


@router.post("/cursos")
def weduca_criar_curso(payload: Curso, request: Request):
    u, pode = _ctx(request, "cursos", "criar cursos")
    cid = novo_id()
    payload.status = "rascunho" if payload.status == "publicado" else payload.status   # publica depois de ter aula
    c = _aplicar_curso(payload, {"id": cid})
    c.update(autor=_quem(u), em=agora(), atualizado_em=agora())
    P["gravar"](COL_CURSO, cid, c); esquecer()
    return _resumo_curso(c, u, pode)


@router.put("/cursos/{cid}")
def weduca_editar_curso(cid: str, payload: Curso, request: Request):
    u, pode = _ctx(request)
    c = _curso_ou_404(cid)
    if not _pode_editar_curso(c, u, pode):
        raise HTTPException(403, "Só quem criou o curso (ou quem modera) edita.")
    _aplicar_curso(payload, c)
    c.update(atualizado_em=agora(), atualizado_por=_quem(u))
    P["gravar"](COL_CURSO, cid, c); esquecer()
    return _resumo_curso(c, u, pode)


@router.delete("/cursos/{cid}")
def weduca_excluir_curso(cid: str, request: Request):
    u, pode = _ctx(request)
    c = _curso_ou_404(cid)
    if not _pode_editar_curso(c, u, pode):
        raise HTTPException(403, "Só quem criou o curso (ou quem modera) exclui.")
    c.update(status="excluido", excluido_em=agora(), excluido_por=_quem(u))   # some da tela e da IA; progresso e certificados ficam guardados
    P["gravar"](COL_CURSO, cid, c); esquecer()
    return {"ok": True}


# ── aulas ──
class Aula(BaseModel):
    titulo: str
    tipo: str = "texto"
    texto: str = ""
    video_url: Optional[str] = ""
    transcricao: Optional[str] = ""
    midias: List[str] = []
    minutos: int = 0
    base: bool = True

    @field_validator("titulo")
    @classmethod
    def _t(cls, v):
        v = str(v or "").strip()
        if not v:
            raise ValueError("Dê um título à aula.")
        return v[:140]

    @field_validator("tipo")
    @classmethod
    def _tp(cls, v):
        if v not in TIPOS_AULA:
            raise ValueError("Tipo de aula inválido.")
        return v

    @field_validator("texto", "transcricao")
    @classmethod
    def _x(cls, v):
        return str(v or "").strip()[:30000]


def _montar_aula(payload: Aula, a: dict) -> dict:
    vid = None
    if (payload.video_url or "").strip():
        yid = youtube_id(payload.video_url)
        if not yid:
            raise HTTPException(400, "Link do YouTube inválido. Cole o link do vídeo (youtube.com/watch?v=… ou youtu.be/…).")
        antigo = a.get("video") or {}
        vid = {"id": yid, "url": f"https://www.youtube.com/watch?v={yid}", "titulo": antigo.get("titulo") if antigo.get("id") == yid else youtube_titulo(yid)}
    if payload.tipo == "video" and not vid:
        raise HTTPException(400, "Aula de vídeo: cole o link do YouTube.")
    dono = "aula:" + a["id"]
    midias, pdfs = [], []
    for aid in payload.midias[:12]:
        m = P["ler"](COL_ARQ, aid)
        if not m:
            raise HTTPException(400, "Um dos anexos não foi encontrado — envie de novo.")
        if m.get("post_id") not in (None, dono):
            raise HTTPException(400, "Esse anexo já pertence a outro conteúdo.")
        midias.append(_midia_publica(m))
        if m.get("kind") == "pdf":
            pdfs.append({"nome": m.get("nome"), "texto": m.get("texto") or ""})
        if m.get("post_id") != dono:
            m["post_id"] = dono; P["gravar"](COL_ARQ, aid, m)
    if payload.tipo == "pdf" and not pdfs:
        raise HTTPException(400, "Aula de PDF: anexe o PDF.")
    if payload.tipo == "texto" and not (payload.texto or midias):
        raise HTTPException(400, "Escreva o conteúdo da aula (ou anexe fotos).")
    a.update(titulo=payload.titulo, tipo=payload.tipo, texto=payload.texto, video=vid, transcricao=payload.transcricao or "",
             midias=midias, pdfs_texto=pdfs, minutos=max(0, min(int(payload.minutos or 0), 600)), base=payload.base)
    return a


def _aula_ou_404(aid: str) -> dict:
    a = P["ler"](COL_AULA, aid)
    if not a or a.get("status", "ativo") != "ativo":
        raise HTTPException(404, "Aula não encontrada.")
    return a


@router.post("/cursos/{cid}/aulas")
def weduca_nova_aula(cid: str, payload: Aula, request: Request):
    u, pode = _ctx(request)
    c = _curso_ou_404(cid)
    if not _pode_editar_curso(c, u, pode):
        raise HTTPException(403, "Só quem criou o curso (ou quem modera) mexe nas aulas.")
    aid = novo_id()
    a = _montar_aula(payload, {"id": aid})
    a.update(curso_id=cid, ordem=len(aulas_de(cid)) + 1, em=agora(), autor=_quem(u), status="ativo", versao=1, correcoes=[], analise=None)
    P["gravar"](COL_AULA, aid, a)
    c["atualizado_em"] = agora(); P["gravar"](COL_CURSO, cid, c); esquecer()
    return _aula_publica(a, u, pode, True)


@router.put("/aulas/{aid}")
def weduca_editar_aula(aid: str, payload: Aula, request: Request):
    u, pode = _ctx(request)
    a = _aula_ou_404(aid)
    if not _pode_editar_curso(_curso_ou_404(a["curso_id"]), u, pode):
        raise HTTPException(403, "Só quem criou o curso (ou quem modera) mexe nas aulas.")
    _montar_aula(payload, a)
    a.update(editado_em=agora(), editado_por=_quem(u), versao=int(a.get("versao") or 1) + 1)
    P["gravar"](COL_AULA, aid, a); esquecer()
    return _aula_publica(a, u, pode, True)


@router.delete("/aulas/{aid}")
def weduca_excluir_aula(aid: str, request: Request):
    u, pode = _ctx(request)
    a = _aula_ou_404(aid)
    c = _curso_ou_404(a["curso_id"])
    if not _pode_editar_curso(c, u, pode):
        raise HTTPException(403, "Só quem criou o curso (ou quem modera) mexe nas aulas.")
    if c.get("status") == "publicado" and len(aulas_de(c["id"])) <= 1:
        raise HTTPException(400, "Curso publicado precisa de pelo menos uma aula. Volte para rascunho para apagar a última.")
    a.update(status="removido", removido_em=agora(), removido_por=_quem(u))
    P["gravar"](COL_AULA, aid, a); esquecer()
    return {"ok": True}


class Ordem(BaseModel):
    aulas: List[str]


@router.post("/cursos/{cid}/ordem")
def weduca_ordem(cid: str, payload: Ordem, request: Request):
    u, pode = _ctx(request)
    c = _curso_ou_404(cid)
    if not _pode_editar_curso(c, u, pode):
        raise HTTPException(403, "Só quem criou o curso (ou quem modera) mexe nas aulas.")
    atuais = {a["id"]: a for a in aulas_de(cid)}
    if set(payload.aulas) != set(atuais):
        raise HTTPException(400, "A lista de aulas mudou — recarregue o curso.")
    for i, aid in enumerate(payload.aulas, 1):
        a = atuais[aid]
        if a.get("ordem") != i:
            a["ordem"] = i; P["gravar"](COL_AULA, aid, a)
    esquecer()
    return {"ok": True}


# ── progresso, avaliação e certificado ──
def _concluir_se_pronto(c: dict, prog: dict, u: dict) -> None:
    aulas = aulas_de(c["id"])
    tudo = aulas and {a["id"] for a in aulas} <= set(prog.get("aulas") or [])
    ok_quiz = (not _tem_quiz(c)) or bool((prog.get("quiz") or {}).get("aprovado"))
    if tudo and ok_quiz and not prog.get("concluido_em"):
        prog.update(concluido_em=agora(), certificado=novo_id()[:10].upper(), curso_titulo=c.get("titulo"),
                    minutos=sum(int(a.get("minutos") or 0) for a in aulas), nome=u.get("nome") or u.get("login"))


class Concluir(BaseModel):
    feita: bool = True


@router.get("/aulas/{aid}")
def weduca_aula(aid: str, request: Request):
    """Só para achar o curso de uma aula (link de pendência do agente: #aula=ID)."""
    u, pode = _ctx(request)
    a = _aula_ou_404(aid)
    c = _curso_ou_404(a["curso_id"])
    if not _visivel(c, u, pode):
        raise HTTPException(404, "Aula não encontrada.")
    return {"curso_id": c["id"], "aula_id": aid}


@router.post("/aulas/{aid}/concluir")
def weduca_concluir_aula(aid: str, payload: Concluir, request: Request):
    u, pode = _ctx(request)
    a = _aula_ou_404(aid)
    c = _curso_ou_404(a["curso_id"])
    if c.get("status") != "publicado" and not _pode_editar_curso(c, u, pode):
        raise HTTPException(400, "Esse curso não está publicado.")
    eu = _eu(u)
    prog = progresso(eu, c["id"])
    prog.setdefault("inicio", agora())
    feitas = [x for x in (prog.get("aulas") or []) if x != aid] + ([aid] if payload.feita else [])
    prog.update(login=eu, nome=u.get("nome") or eu, curso_id=c["id"], aulas=feitas, ultima_aula=aid, atualizado_em=agora())
    _concluir_se_pronto(c, prog, u)
    P["gravar"](COL_PROG, _prog_id(eu, c["id"]), prog)
    return {"feitas": feitas, "pct": _pct(prog, aulas_de(c["id"])), "concluido_em": prog.get("concluido_em"), "certificado": prog.get("certificado")}


@router.post("/aulas/{aid}/visto")
def weduca_aula_vista(aid: str, request: Request):
    """Abriu a aula: guarda onde parou ("continuar de onde parei")."""
    u, _ = _ctx(request)
    a = _aula_ou_404(aid)
    eu = _eu(u)
    prog = progresso(eu, a["curso_id"])
    prog.setdefault("inicio", agora())
    prog.update(login=eu, nome=u.get("nome") or eu, curso_id=a["curso_id"], ultima_aula=aid, atualizado_em=agora())
    prog.setdefault("aulas", [])
    P["gravar"](COL_PROG, _prog_id(eu, a["curso_id"]), prog)
    return {"ok": True}


class Respostas(BaseModel):
    respostas: dict   # {id_da_pergunta: índice da alternativa}


@router.post("/cursos/{cid}/avaliacao")
def weduca_avaliacao(cid: str, payload: Respostas, request: Request):
    u, pode = _ctx(request)
    c = _curso_ou_404(cid)
    if c.get("status") != "publicado":
        raise HTTPException(400, "Esse curso não está publicado.")
    perguntas = (c.get("quiz") or {}).get("perguntas") or []
    if not perguntas:
        raise HTTPException(400, "Esse curso não tem avaliação.")
    eu = _eu(u)
    prog = progresso(eu, cid)
    aulas = aulas_de(cid)
    if not {a["id"] for a in aulas} <= set(prog.get("aulas") or []):
        raise HTTPException(400, "Conclua todas as aulas antes da avaliação.")
    certas = sum(1 for q in perguntas if str(payload.respostas.get(q["id"])) == str(q["correta"]))
    nota = round(100 * certas / len(perguntas))
    minimo = int((c.get("quiz") or {}).get("nota_min") or 70)
    antes = prog.get("quiz") or {}
    prog["quiz"] = {"nota": max(nota, int(antes.get("nota") or 0)), "ultima": nota, "aprovado": bool(antes.get("aprovado")) or nota >= minimo,
                    "tentativas": int(antes.get("tentativas") or 0) + 1, "em": agora()}
    prog.update(login=eu, nome=u.get("nome") or eu, curso_id=cid, atualizado_em=agora())
    _concluir_se_pronto(c, prog, u)
    P["gravar"](COL_PROG, _prog_id(eu, cid), prog)
    gabarito = {q["id"]: {"certa": q["correta"], "marcou": payload.respostas.get(q["id"])} for q in perguntas} if nota >= minimo else None
    return {"nota": nota, "certas": certas, "total": len(perguntas), "minimo": minimo, "aprovado": nota >= minimo,
            "concluido_em": prog.get("concluido_em"), "certificado": prog.get("certificado"), "gabarito": gabarito}


@router.get("/certificados")
def weduca_certificados(request: Request):
    u, _ = _ctx(request)
    return {"certificados": sorted(({"curso_id": p.get("curso_id"), "curso": p.get("curso_titulo"), "codigo": p.get("certificado"),
                                     "concluido_em": p.get("concluido_em"), "minutos": p.get("minutos"), "nota": (p.get("quiz") or {}).get("nota"),
                                     "nome": p.get("nome")} for p in _progresso_de(_eu(u)) if p.get("concluido_em")),
                                   key=lambda x: x["concluido_em"], reverse=True)}


@router.get("/cursos/{cid}/turma")
def weduca_turma(cid: str, request: Request):
    """Quem criou o curso (ou modera) acompanha: quem começou, quanto andou, nota e conclusão."""
    u, pode = _ctx(request)
    c = _curso_ou_404(cid)
    if not _pode_editar_curso(c, u, pode):
        raise HTTPException(403, "Só quem criou o curso (ou quem modera) vê a turma.")
    aulas = aulas_de(cid)
    lst = [{"nome": p.get("nome") or p.get("login"), "login": p.get("login"), "pct": _pct(p, aulas), "inicio": p.get("inicio"),
            "atualizado_em": p.get("atualizado_em"), "nota": (p.get("quiz") or {}).get("nota"), "tentativas": (p.get("quiz") or {}).get("tentativas"),
            "concluido_em": p.get("concluido_em")} for p in P["listar"](COL_PROG) if p.get("curso_id") == cid]
    return {"turma": sorted(lst, key=lambda x: (-x["pct"], x["nome"] or ""))}


# ── dúvidas da aula (públicas → entram na base junto com a aula) ──
@router.get("/aulas/{aid}/duvidas")
def weduca_duvidas(aid: str, request: Request):
    u, pode = _ctx(request)
    _aula_ou_404(aid)
    return {"duvidas": [_com_publico(x, u, pode) for x in comentarios_de("aula:" + aid)]}


@router.post("/aulas/{aid}/duvidas")
def weduca_nova_duvida(aid: str, payload: Comentario, request: Request):
    u, pode = _ctx(request, "comentar", "comentar")
    _aula_ou_404(aid)
    cid = novo_id()
    x = {"id": cid, "post_id": "aula:" + aid, "autor": _quem(u), "em": agora(), "texto": payload.texto, "status": "ativo"}
    P["gravar"](COL_COM, cid, x)
    _cache["com"].append(x); esquecer()
    return _com_publico(x, u, pode)
