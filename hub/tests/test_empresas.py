"""Empresas ("Duplicar sistema"): cada empresa com seus usuários e seus dados, login único no hub.

    cd hub && python -m pytest tests/test_empresas.py -q
"""
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acesso  # noqa: E402
import banco  # noqa: E402

DB: dict = {}


class _Snap:
    def __init__(self, i, d):
        self.id, self._d = i, d

    exists = property(lambda s: s._d is not None)

    def to_dict(self):
        return dict(self._d) if self._d is not None else None


class _Doc:
    def __init__(self, path):
        self.path, self.id = path, path[-1]

    def collection(self, n):
        return _Col(self.path + (n,))

    def get(self, **k):
        return _Snap(self.id, DB.get(self.path))

    def set(self, d, merge=False, **k):
        DB[self.path] = {**(DB.get(self.path) or {}), **d} if merge else dict(d)

    def delete(self, **k):
        DB.pop(self.path, None)


class _Col:
    def __init__(self, path):
        self.path = path

    def document(self, i=None):
        return _Doc(self.path + (i or uuid.uuid4().hex,))

    def stream(self, **k):
        return [_Snap(p[-1], d) for p, d in list(DB.items()) if p[:-1] == self.path]

    def where(self, *a, **k):
        return self

    def limit(self, n):
        return self


class _Fake:
    def collection(self, n):
        return _Col((n,))


@pytest.fixture()
def hub(monkeypatch):
    DB.clear()
    monkeypatch.setenv("FIRESTORE_CREDS", "teste")
    monkeypatch.setattr(banco, "_cliente", lambda: _Fake())
    monkeypatch.setattr(acesso, "ADMIN_FAB_LOGIN", "chefe")
    monkeypatch.setattr(acesso, "ADMIN_FAB_SENHA", "senha-forte")
    acesso.USUARIOS._cache = None
    acesso.EMPRESAS._cache = None
    import main
    import weduca
    monkeypatch.setattr(weduca, "_CACHE_SEG", -1)
    novo = lambda: TestClient(main.app)  # noqa: E731
    yield novo


def entrar(c, login, senha):
    r = c.post("/api/auth/entrar", json={"login": login, "senha": senha})
    assert r.status_code == 200, r.text
    return c


def test_duplicar_sistema_isola_usuarios_e_dados(hub):
    chefe = entrar(hub(), "chefe", "senha-forte")
    assert chefe.get("/api/eu").json()["usuario"]["super"] is True
    # usuário da principal (como hoje)
    assert chefe.post("/api/admin/usuarios", json={"login": "ana", "nome": "Ana", "senha": "123456", "admin": True}).status_code == 200
    chefe.post("/api/weduca/posts", json={"texto": "Post da principal"})
    # cria a empresa nova + o admin dela
    r = chefe.post("/api/super/empresas", json={"nome": "Loja Exemplo", "admin": {"login": "joao", "nome": "João", "senha": "123456"}})
    assert r.status_code == 200, r.text
    eid = r.json()["empresa"]["id"]
    assert eid == "loja-exemplo" and r.json()["empresa"]["usuarios"] == 1
    assert "weduca" in r.json()["empresa"]["modulos"]
    # login repetido não pode, em empresa nenhuma
    r = chefe.post("/api/super/empresas", json={"nome": "Outra", "admin": {"login": "ana", "senha": "123456"}})
    assert r.status_code == 409 and "não é permitido" in r.json()["detail"]
    # o admin da empresa nova entra direto nela, vazia
    joao = entrar(hub(), "joao", "123456")
    assert joao.get("/api/eu").json()["empresa"] == {"id": eid, "nome": "Loja Exemplo"}
    assert [u["login"] for u in joao.get("/api/admin/usuarios").json()["usuarios"]] == ["joao"]
    assert joao.get("/api/weduca/feed").json()["posts"] == []
    assert joao.post("/api/admin/usuarios", json={"login": "ana", "senha": "123456"}).status_code == 409
    assert joao.post("/api/admin/usuarios", json={"login": "maria", "nome": "Maria", "senha": "123456"}).status_code == 200
    joao.post("/api/weduca/posts", json={"texto": "Post da loja"})
    assert [p["texto"] for p in joao.get("/api/weduca/feed").json()["posts"]] == ["Post da loja"]
    assert joao.get("/api/super/empresas").status_code == 403                  # mini admin não vê outras empresas
    assert joao.put("/api/admin/usuarios/ana", json={"nome": "X"}).status_code == 404   # nem mexe em usuário de outra
    # a principal continua igual e não vê nada da loja
    ana = entrar(hub(), "ana", "123456")
    assert {u["login"] for u in ana.get("/api/admin/usuarios").json()["usuarios"]} == {"ana"}
    assert [p["texto"] for p in ana.get("/api/weduca/feed").json()["posts"]] == ["Post da principal"]
    assert ana.delete("/api/admin/usuarios/maria").status_code == 404
    # super troca de empresa sem sair
    assert chefe.post("/api/super/entrar-empresa", json={"empresa": eid}).status_code == 200
    assert {u["login"] for u in chefe.get("/api/admin/usuarios").json()["usuarios"]} == {"joao", "maria"}
    assert [p["texto"] for p in chefe.get("/api/weduca/feed").json()["posts"]] == ["Post da loja"]
    # desligar um módulo para a empresa
    mods = [m for m in chefe.get("/api/super/empresas").json()["modulos"] if m["id"] != "weduca"]
    assert chefe.put(f"/api/super/empresas/{eid}", json={"modulos": [m["id"] for m in mods]}).status_code == 200
    assert "weduca" not in [i["id"] for i in joao.get("/api/modulos").json()["itens"]]
    assert joao.get("/api/weduca/feed").status_code == 403
    assert joao.get("/m/weduca").status_code == 403
    # desativar a empresa bloqueia o login de quem é dela
    chefe.put(f"/api/super/empresas/{eid}", json={"ativo": False})
    assert hub().post("/api/auth/entrar", json={"login": "maria", "senha": "123456"}).status_code == 401
    chefe.post("/api/super/entrar-empresa", json={"empresa": "principal"})
    assert [p["texto"] for p in chefe.get("/api/weduca/feed").json()["posts"]] == ["Post da principal"]
    # os dados da loja ficam em coleções separadas no banco
    assert any(p[0].startswith(f"e_{eid}__weduca") for p in DB) and any(p[0] == "weduca_posts" for p in DB)


def test_cache_por_empresa():
    c = banco.por_empresa(lambda: {"n": 0})
    c["n"] = 1
    with banco.usar_empresa("x"):
        assert c["n"] == 0
        c["n"] = 5
    assert c["n"] == 1 and banco.nome_colecao("hub_usuarios", "x") == "hub_usuarios"
    assert banco.nome_colecao("weduca_posts", "x") == "e_x__weduca_posts"
