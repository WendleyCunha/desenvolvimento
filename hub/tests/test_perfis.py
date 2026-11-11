"""Perfis (atendente / supervisor / gestor), pegar o próximo e painel da equipe.

    cd hub && python -m pytest tests/test_perfis.py -q
"""
import tickets as T
from test_ajuda import t  # noqa: F401  (fixture)

USU2 = {"lucas": {"nome": "Lucas Log", "depto": "Logística"}, "lia": {"nome": "Lia Log", "depto": "Logística"},
        "carla": {"nome": "Carla CX", "depto": "CX"}, "gil": {"nome": "Gil Compras", "depto": "Compras"}, "adm": {"nome": "Adm", "depto": ""}}


def abrir(t, cod, setor="Logística"):
    t.como("carla")
    return t.post("/api/tickets/tickets", json={"departamento": setor, "cliente_codigo": cod, "cliente_nome": cod, "assunto": "x", "descricao": "y"}).json()["id"]


def test_perfis_e_pegar_proximo(t, monkeypatch):  # noqa: F811
    import acesso
    T.BASE.cfg_cache["usuarios"] = USU2
    monkeypatch.setattr(acesso, "exigir_usuario", lambda r: {"login": t.quem(), "nome": USU2[t.quem()]["nome"]})
    a, b = abrir(t, "A1"), abrir(t, "B2")
    abrir(t, "C3", "CX")
    T.BASE.cfg_cache["tickets_hub"] = {"perfis": {"lucas": "atendente", "lia": "supervisor", "gil": "gestor"}}
    ids = lambda: {x["id"] for x in t.get("/api/tickets/estado").json()["tickets"]}  # noqa: E731
    t.como("lucas")   # atendente: não vê a fila, só o número
    e = t.get("/api/tickets/estado").json()
    assert e["eu"]["perfil"] == "atendente" and not ({a, b} & ids()) and e["fila"]["clientes"] == 2
    r = t.post("/api/tickets/proximo").json()   # pega o mais urgente do setor dele
    assert r["cid"] in ("A1", "B2") and len({a, b} & ids()) == 1
    t.como("lia")     # supervisor: vê o setor inteiro
    assert {a, b} <= ids()
    eq = t.get("/api/tickets/equipe").json()
    assert {x["usuario"] for x in eq["pessoas"]} == {"lucas", "lia"} and eq["fila"]["clientes"] == 1
    assert next(x for x in eq["pessoas"] if x["usuario"] == "lucas")["online"]
    t.como("gil")     # gestor: todos os setores
    assert len(t.get("/api/tickets/equipe").json()["pessoas"]) == len(USU2)
    t.como("lucas")
    assert [x["usuario"] for x in t.get("/api/tickets/equipe").json()["pessoas"]] == ["lucas"]   # atendente: só a própria linha
    t.post("/api/tickets/proximo")
    assert t.post("/api/tickets/proximo").status_code == 404   # fila do setor vazia
