"""App Relatórios mostra a congregação de cada empresa (usa o banco falso de test_empresas)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_empresas import entrar, hub  # noqa: E402,F401  (fixture)


def test_app_relatorios_mostra_a_congregacao_da_empresa(hub):
    chefe = entrar(hub(), "chefe", "senha-forte")
    eid = chefe.post("/api/super/empresas", json={"nome": "Congregação Areia Branca", "admin": {"login": "ab", "senha": "123456"}}).json()["empresa"]["id"]
    assert eid == "congregacao-areia-branca"
    pub = hub()
    pg = pub.get(f"/{eid}/relatorios/").text
    assert "Areia Branca" in pg and "Parque Aliança" not in pg and "72249" not in pg
    assert pub.get(f"/{eid}/api/relatorios-publico/info").json()["congregacao"] == "Areia Branca"
    assert "Areia Branca" in pub.get(f"/{eid}/relatorios/manifest.webmanifest").text
    assert "Parque Aliança" in pub.get("/relatorios/").text and "72249" in pub.get("/relatorios/").text   # a principal fica igual
    chefe.post("/api/super/entrar-empresa", json={"empresa": eid})
    assert chefe.put("/api/secretaria/config", json={"congregacao_nome": "Areia Branca (Sul)", "congregacao_numero": "12345"}).status_code == 200
    assert chefe.get("/api/secretaria/base").json()["identidade"] == {"nome": "Areia Branca (Sul)", "numero": "12345"}
    pg = pub.get(f"/{eid}/relatorios/").text
    assert "Areia Branca (Sul)" in pg and "12345" in pg


def test_menu_mostra_o_nome_da_empresa_no_lugar_de_parque_alianca(hub):
    chefe = entrar(hub(), "chefe", "senha-forte")
    grupos = {i["grupo"] for i in chefe.get("/api/modulos").json()["itens"]}
    assert "Parque Aliança" in grupos                       # principal igual
    eid = chefe.post("/api/super/empresas", json={"nome": "Congregação Areia Branca", "admin": {"login": "ab2", "senha": "123456"}}).json()["empresa"]["id"]
    chefe.post("/api/super/entrar-empresa", json={"empresa": eid})
    grupos = {i["grupo"] for i in chefe.get("/api/modulos").json()["itens"]}
    assert "Parque Aliança" not in grupos and "Congregação Areia Branca" in grupos
