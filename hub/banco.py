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


def ler_credenciais(bruto: str) -> dict:
    """Aceita o JSON da service account mesmo colado "torto" no Render:
    com quebras de linha reais dentro da private_key, entre aspas extras,
    ou no formato TOML dos secrets do Streamlit ([firebase] chave = "...")."""
    t = bruto.strip()
    if len(t) > 1 and t[0] == t[-1] and t[0] in "'\"" and not t.startswith('{"'):
        t = t[1:-1].strip()
    info = None
    if t.startswith("{"):
        try:
            info = json.loads(t, strict=False)  # strict=False: tolera quebras de linha reais
        except json.JSONDecodeError as e:
            raise SemBanco(f"FIRESTORE_CREDS não é um JSON válido (linha {e.lineno}, coluna {e.colno}). "
                           "Cole o conteúdo do arquivo .json inteiro, de { até }.") from None
    else:
        try:
            import tomllib
            dados = tomllib.loads(t)
        except Exception:
            raise SemBanco("FIRESTORE_CREDS precisa ser o conteúdo do arquivo .json da service account "
                           "(começa com { e termina com }).") from None
        def _achar(d):
            if isinstance(d, dict):
                if "private_key" in d:
                    return d
                for v in d.values():
                    r = _achar(v)
                    if r:
                        return r
            elif isinstance(d, str) and "private_key" in d:
                # ex.: textkey = """{ ...json... }"""  (secrets do Parque Aliança)
                try:
                    return json.loads(d, strict=False)
                except json.JSONDecodeError:
                    return None
            return None
        info = _achar(dados)
        if info is None:
            raise SemBanco("FIRESTORE_CREDS: não achei a private_key no texto colado.")
    if not isinstance(info, dict):
        raise SemBanco("FIRESTORE_CREDS: formato inesperado.")
    if isinstance(info.get("private_key"), str):
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    faltam = [k for k in ("project_id", "private_key", "client_email") if not info.get(k)]
    if faltam:
        raise SemBanco("FIRESTORE_CREDS: faltam os campos " + ", ".join(faltam) + ".")
    return info


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

                info = ler_credenciais(bruto)
                cred = service_account.Credentials.from_service_account_info(info)
                _db = firestore.Client(credentials=cred, project=info["project_id"])
    return _db
