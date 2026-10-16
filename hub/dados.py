"""
hub/dados.py — API genérica de dados dos módulos, COM permissão por ação e campo.
─────────────────────────────────────────────────────────────────────────────
    GET    /api/dados/<modulo>/<colecao>          lista   (precisa "acessar")
    POST   /api/dados/<modulo>/<colecao>          cria    (precisa "incluir")
    PUT    /api/dados/<modulo>/<colecao>/<id>     altera  (precisa "editar" + campo "editar")
    DELETE /api/dados/<modulo>/<colecao>/<id>     exclui  (precisa "excluir")

Regras aplicadas no SERVIDOR (não dá para burlar pelo navegador):
  • campo "oculto"  → nunca é enviado para esse usuário;
  • campo "ver"     → qualquer tentativa de mudar o valor é recusada (403);
  • ação com "regra" no esquema do módulo (ex.: "concluir") libera só os
    campos listados nela, mesmo para quem não tem "editar";
  • ao criar, campo que o usuário não pode editar recebe o valor padrão.

Firestore: hub_modulos/<modulo>/<colecao>/<id>
Cache em memória por coleção (o hub é a única porta de escrita) — economiza a
cota grátis de leituras: cada coleção é lida do banco só uma vez por reinício.
"""
from __future__ import annotations

import json
import re
import threading
import time

from fastapi import APIRouter, HTTPException, Request

import acesso
import banco

router = APIRouter()
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")
ID_OK = re.compile(r"^[A-Za-z0-9_-]{1,80}$")

_cache: dict[tuple[str, str], dict[str, dict]] = {}
_trava = threading.Lock()


def _col(mod: str, col: str):
    return banco.db().collection("hub_modulos").document(mod).collection(col)


def _itens(mod: str, col: str) -> dict[str, dict]:
    chave = (mod, col)
    with _trava:
        if chave not in _cache:
            _cache[chave] = {d.id: (d.to_dict() or {}) for d in _col(mod, col).stream(timeout=banco.TIMEOUT)}
        return _cache[chave]


def _igual(a, b) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _contexto(request: Request, mod: str, col: str):
    if not SLUG.match(mod) or not SLUG.match(col):
        raise HTTPException(404)
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(mod)
    if esq is None:
        raise HTTPException(404, "Módulo não encontrado.")
    p = acesso.permissoes(u, mod, esq)
    if not p["acoes"].get("acessar"):
        raise HTTPException(403, "Sem acesso a este módulo.")
    if not banco.configurado():
        raise HTTPException(503, "sem_banco")
    return u, esq, p


def _para_usuario(doc_id: str, doc: dict, p: dict) -> dict:
    vis = {k: v for k, v in doc.items() if p["campos"].get(k) != "oculto"}
    vis["id"] = doc_id
    return vis


@router.get("/api/dados/{mod}/{col}")
def listar(mod: str, col: str, request: Request):
    _, _, p = _contexto(request, mod, col)
    return {"itens": [_para_usuario(i, d, p) for i, d in _itens(mod, col).items()], "perm": p}


@router.post("/api/dados/{mod}/{col}")
async def criar(mod: str, col: str, request: Request):
    u, esq, p = _contexto(request, mod, col)
    corpo = await request.json()
    acao = str(corpo.get("acao") or "")
    regra = esq["regras"].get(acao) or {}
    via_regra = bool(acao and p["acoes"].get(acao) and regra.get("cria"))
    if not p["acoes"].get("incluir") and not via_regra:
        raise HTTPException(403, "Sem permissão para incluir.")
    dados = {k: v for k, v in (corpo.get("dados") or {}).items() if not str(k).startswith("_")}
    if not via_regra:
        for campo in esq["campos"]:
            if p["campos"].get(campo, "editar") != "editar":
                if campo in esq["padroes"]:
                    dados[campo] = esq["padroes"][campo]
                else:
                    dados.pop(campo, None)
    doc_id = str(corpo.get("id") or dados.get("id") or "")
    if not ID_OK.match(doc_id):
        doc_id = f"{int(time.time() * 1000):x}{abs(hash(json.dumps(dados, default=str))) % 99999:05d}"
    itens = _itens(mod, col)
    if doc_id in itens:
        raise HTTPException(409, "Já existe um registro com esse id.")
    dados.update(id=doc_id, _criado_em=_agora(), _criado_por=u["login"], _atualizado_em=_agora(), _atualizado_por=u["login"])
    _col(mod, col).document(doc_id).set(dados, timeout=banco.TIMEOUT)
    itens[doc_id] = dados
    return {"ok": True, "item": _para_usuario(doc_id, dados, p)}


@router.put("/api/dados/{mod}/{col}/{doc_id}")
async def alterar(mod: str, col: str, doc_id: str, request: Request):
    u, esq, p = _contexto(request, mod, col)
    itens = _itens(mod, col)
    atual = itens.get(doc_id)
    if atual is None:
        raise HTTPException(404, "Registro não encontrado (pode ter sido excluído).")
    corpo = await request.json()
    acao = str(corpo.get("acao") or "")
    liberados = set((esq["regras"].get(acao) or {}).get("campos") or []) if acao and p["acoes"].get(acao) else set()
    novos = {k: v for k, v in (corpo.get("dados") or {}).items() if not str(k).startswith("_") and k != "id"}
    mudados = [k for k, v in novos.items() if not _igual(atual.get(k), v)]

    proibidos = []
    for k in mudados:
        if k in liberados:
            continue
        if not p["acoes"].get("editar"):
            proibidos.append(k)
        elif k in esq["campos"] and p["campos"].get(k, "editar") != "editar":
            proibidos.append(k)
    if proibidos:
        nomes = ", ".join(esq["campos"].get(k, k) for k in proibidos)
        raise HTTPException(403, f"Sem permissão para alterar: {nomes}.")

    if mudados:
        atual = {**atual, **{k: novos[k] for k in mudados}, "_atualizado_em": _agora(), "_atualizado_por": u["login"]}
        _col(mod, col).document(doc_id).set(atual, timeout=banco.TIMEOUT)
        itens[doc_id] = atual
    return {"ok": True, "item": _para_usuario(doc_id, atual, p), "mudados": mudados}


@router.delete("/api/dados/{mod}/{col}/{doc_id}")
def excluir(mod: str, col: str, doc_id: str, request: Request):
    _, _, p = _contexto(request, mod, col)
    if not p["acoes"].get("excluir"):
        raise HTTPException(403, "Sem permissão para excluir.")
    itens = _itens(mod, col)
    if doc_id not in itens:
        return {"ok": True}
    _col(mod, col).document(doc_id).delete(timeout=banco.TIMEOUT)
    itens.pop(doc_id, None)
    return {"ok": True}
