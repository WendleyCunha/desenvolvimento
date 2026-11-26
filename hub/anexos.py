"""
hub/anexos.py — ANEXOS das conversas (CX/Caixa, chat do cliente pelo app e chat com o motorista no WROUTER)
─────────────────────────────────────────────────────────────────────────────
Um anexo é gravado uma vez (coleção "anexos") e a mensagem guarda só o resumo {id, nome, tipo, tam}.
Limites (o banco aceita até ~1 MB por documento):
  • tipos: imagem (JPEG, PNG, WEBP, GIF) e PDF
  • até 650 KB por arquivo (as fotos já chegam reduzidas pela tela) e até 3 por mensagem
Quem pode abrir é conferido por quem chama (cliente do chamado, placa do motorista, permissão do módulo).
"""
from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime

from fastapi import HTTPException
from fastapi.responses import Response

import banco

COL = "anexos"
MAX_BYTES = 650 * 1024
MAX_POR_MSG = 3
TIPOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "application/pdf": "pdf"}


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def salvar_lista(lista, dono: dict) -> list[dict]:
    """Grava os anexos de uma mensagem. `dono` vai junto para conferir o acesso depois
    (ex.: {"cid": cliente} no CX, {"carga": cid, "pid": pid} no WROUTER)."""
    lista = [a for a in (lista or []) if isinstance(a, dict)]
    if len(lista) > MAX_POR_MSG:
        raise HTTPException(413, f"No máximo {MAX_POR_MSG} anexos por mensagem.")
    out = []
    for a in lista:
        m = re.fullmatch(r"data:([a-z/+.-]+);base64,([A-Za-z0-9+/=]+)", str(a.get("dados") or ""))
        tipo = (m.group(1) if m else str(a.get("tipo") or "")).lower()
        b64 = m.group(2) if m else str(a.get("b64") or "")
        if tipo not in TIPOS:
            raise HTTPException(415, "Tipo de anexo não aceito. Envie imagem (JPG, PNG, WEBP, GIF) ou PDF.")
        try:
            bruto = base64.b64decode(b64, validate=True)
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "Anexo inválido.")
        if len(bruto) > MAX_BYTES:
            raise HTTPException(413, f"Anexo grande demais (máximo {MAX_BYTES // 1024} KB). Envie um PDF menor ou uma foto.")
        nome = re.sub(r"[\\/\r\n\"]+", "_", str(a.get("nome") or f"anexo.{TIPOS[tipo]}"))[:80]
        aid = uuid.uuid4().hex[:20]
        doc = {"tipo": tipo, "nome": nome, "tam": len(bruto), "b64": b64, "em": _agora(), **{k: v for k, v in (dono or {}).items() if v}}
        banco.db().collection(COL).document(aid).set(doc, timeout=banco.TIMEOUT)
        out.append({"id": aid, "nome": nome, "tipo": tipo, "tam": len(bruto)})
    return out


def ler(aid: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{20}", str(aid or "")):
        raise HTTPException(404, "Anexo não encontrado.")
    snap = banco.db().collection(COL).document(aid).get(timeout=banco.TIMEOUT)
    if not snap.exists:
        raise HTTPException(404, "Anexo não encontrado.")
    return snap.to_dict()


def resposta(doc: dict) -> Response:
    nome = str(doc.get("nome") or "anexo").replace('"', "")
    disp = "inline" if doc.get("tipo", "").startswith("image/") or doc.get("tipo") == "application/pdf" else "attachment"
    return Response(base64.b64decode(doc.get("b64") or ""), media_type=doc.get("tipo") or "application/octet-stream",
                    headers={"Content-Disposition": f'{disp}; filename="{nome}"', "Cache-Control": "private, max-age=86400",
                             "X-Content-Type-Options": "nosniff"})
