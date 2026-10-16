"""
hub/banco.py — conexão única com o Firestore (projeto da env var FIRESTORE_CREDS).

Criada SOB DEMANDA, nunca no import: no PQI, criar o cliente no import deixava
o gRPC pendurado para sempre. Toda chamada usa TIMEOUT para nunca travar a rota.
"""
from __future__ import annotations

import json
import os
import threading

TIMEOUT = 15  # segundos por operação no Firestore

_db = None
_trava = threading.Lock()


class SemBanco(RuntimeError):
    """FIRESTORE_CREDS não configurada no Render."""


def configurado() -> bool:
    return bool(os.environ.get("FIRESTORE_CREDS", "").strip())


def db():
    global _db
    if _db is None:
        with _trava:
            if _db is None:
                bruto = os.environ.get("FIRESTORE_CREDS", "").strip()
                if not bruto:
                    raise SemBanco("FIRESTORE_CREDS não configurada no Render.")
                from google.cloud import firestore
                from google.oauth2 import service_account

                info = json.loads(bruto)
                cred = service_account.Credentials.from_service_account_info(info)
                _db = firestore.Client(credentials=cred, project=info["project_id"])
    return _db
