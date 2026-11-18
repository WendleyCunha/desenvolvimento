"""
hub/banco.py — conexão única com o Firestore (projeto da env var FIRESTORE_CREDS).

Criada SOB DEMANDA, nunca no import: no PQI, criar o cliente no import deixava
o gRPC pendurado para sempre. Toda chamada usa TIMEOUT para nunca travar a rota.
"""
from __future__ import annotations

import contextvars
import json
import os
import threading
from contextlib import contextmanager

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


def _cliente():
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


# ══════════════════════════════════════════════════════════════════════════════
# EMPRESAS — o mesmo hub, vários "sistemas" separados (Configurações → Duplicar sistema)
# ──────────────────────────────────────────────────────────────────────────────
# A empresa da requisição fica num contextvar (o main.py põe a do usuário logado).
# PRINCIPAL = os dados de sempre, com os nomes de coleção de sempre (nada migra).
# Outra empresa = as MESMAS coleções com prefixo "e_<id>__" → começa vazia e nada
# dela se mistura com as outras. Usuários e o cadastro de empresas são globais.
# ══════════════════════════════════════════════════════════════════════════════
PRINCIPAL = "principal"
GLOBAIS = {"hub_usuarios", "hub_empresas"}
_EMPRESA: contextvars.ContextVar[str] = contextvars.ContextVar("empresa", default=PRINCIPAL)


def empresa_atual() -> str:
    return _EMPRESA.get()


def definir_empresa(eid: str | None):
    """Põe a empresa no contexto atual; devolve o token para desfazer (contextvars.reset)."""
    return _EMPRESA.set(eid or PRINCIPAL)


@contextmanager
def usar_empresa(eid: str | None):
    tk = _EMPRESA.set(eid or PRINCIPAL)
    try:
        yield
    finally:
        _EMPRESA.reset(tk)


def nome_colecao(nome: str, eid: str | None = None) -> str:
    eid = eid or empresa_atual()
    if eid == PRINCIPAL or nome in GLOBAIS:
        return nome
    return f"e_{eid}__{nome}"


class _Banco:
    """Cliente do Firestore que separa as coleções por empresa (o resto passa direto)."""
    __slots__ = ("_c",)

    def __init__(self, cliente):
        self._c = cliente

    def collection(self, nome: str, *resto):
        return self._c.collection(nome_colecao(nome), *resto)

    def __getattr__(self, n):
        return getattr(self._c, n)


def envolver(cliente):
    """Para outro cliente do Firestore (ex.: o banco próprio dos Tickets) também separar por empresa."""
    return _Banco(cliente)


def db():
    """Firestore da empresa da requisição."""
    return _Banco(_cliente())


def db_global():
    """Firestore sem prefixo — só para o que é do hub inteiro (usuários e empresas)."""
    return _cliente()


class _PorEmpresa:
    """Um objeto (cache, fila, estado) por empresa: `BASE = banco.por_empresa(_Base)`.
    Por fora parece o objeto de sempre; por dentro cada empresa tem o seu."""
    __slots__ = ("_fab", "_mapa", "_trava")

    def __init__(self, fabrica):
        object.__setattr__(self, "_fab", fabrica)
        object.__setattr__(self, "_mapa", {})
        object.__setattr__(self, "_trava", threading.Lock())

    def _alvo(self):
        e, m = empresa_atual(), self._mapa
        if e not in m:
            with self._trava:
                if e not in m:
                    m[e] = self._fab()
        return m[e]

    def __getattr__(self, n):
        return getattr(self._alvo(), n)

    def __setattr__(self, n, v):
        setattr(self._alvo(), n, v)

    def __delattr__(self, n):
        delattr(self._alvo(), n)

    def __getitem__(self, k):
        return self._alvo()[k]

    def __setitem__(self, k, v):
        self._alvo()[k] = v

    def __delitem__(self, k):
        del self._alvo()[k]

    def __contains__(self, k):
        return k in self._alvo()

    def __iter__(self):
        return iter(self._alvo())

    def __len__(self):
        return len(self._alvo())

    def __bool__(self):
        return bool(self._alvo())

    def __repr__(self):
        return f"<por empresa {empresa_atual()}: {self._alvo()!r}>"


def por_empresa(fabrica):
    return _PorEmpresa(fabrica)


def thread(alvo, *args, **kw):
    """threading.Thread que leva junto a empresa de quem pediu (o contextvar não passa sozinho)."""
    ctx = contextvars.copy_context()
    t = threading.Thread(target=lambda: ctx.run(alvo, *args, **kw), daemon=True)
    t.start()
    return t
