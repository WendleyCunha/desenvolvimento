"""GOVERNANÇA: módulo → aba → campo, conferida no servidor. E a regra para função nova: toda rota tem aba."""
import sys
from fnmatch import fnmatchcase
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_empresas as T  # noqa: E402
from test_empresas import entrar, hub  # noqa: E402,F401  (fixture)


def test_toda_rota_de_modulo_tem_aba_e_nivel():
    """Função nova sem regra de acesso NÃO passa: inclua a rota em hub/governanca.py (ABAS)."""
    import governanca
    import main
    faltando = []
    for r in main.app.routes:
        caminho = getattr(r, "path", "")
        for metodo in sorted((getattr(r, "methods", None) or set()) - {"HEAD"}):
            exemplo = caminho.replace("{tid:path}", "X/1")
            import re
            exemplo = re.sub(r"\{[^}]+\}", "x1", exemplo)
            if "/api/dados/{mod}" in caminho:
                exemplo = exemplo.replace("/api/dados/x1", "/api/dados/lila", 1)
            achado = governanca.localizar(metodo, exemplo)
            if achado and achado[1] == "?":
                faltando.append(f"{metodo} {caminho}")
    assert not faltando, "Rotas sem aba na governança:\n" + "\n".join(faltando)


def test_abas_tem_rotulo_e_niveis_validos():
    import governanca
    for slug, m in governanca.ABAS.items():
        assert m["prefixos"], slug
        for aba, d in m["abas"].items():
            assert d["rotulo"], (slug, aba)
            for metodo, padrao, nivel in d["rotas"]:
                assert nivel in ("auto", "ver", "incluir", "editar", "excluir", governanca.ACESSO), (slug, aba, padrao)
                assert any(padrao.startswith(p) for p in m["prefixos"]), (slug, padrao)


def _usuario(chefe, login, modulos):
    r = chefe.post("/api/admin/usuarios", json={"login": login, "nome": login.title(), "senha": "123456", "modulos": modulos})
    assert r.status_code == 200, r.text


def test_aba_ver_bloqueia_gravar_e_nenhum_esconde(hub):
    import secretaria
    T.DB[(secretaria.COL_MEMBROS, "Ana Teste")] = {"nome_oficial": "Ana Teste", "categoria": "PUBLICADOR", "genero": "Feminino",
                                                  "data_nascimento": "01/02/1990"}
    c = hub()
    chefe = entrar(c, "chefe", "senha-forte")
    todas = {a: True for a in ["acessar", "lancar", "triagem", "excluir", "membros", "assistencia", "fechar", "exportar", "anuncios", "ajustes"]}
    _usuario(chefe, "leitor", {"secretaria": {"acoes": todas, "gov": True, "abas": {"membros": "ver", "ajustes": "nenhum", "mes": "incluir"}}})
    secretaria.BASE.membros = None
    leitor = entrar(hub(), "leitor", "123456")
    assert leitor.get("/api/secretaria/base").status_code == 200                       # abre o módulo
    assert leitor.get("/api/secretaria/membro/Ana Teste").status_code == 200            # Ver
    r = leitor.put("/api/secretaria/membros/Ana Teste", json={"genero": "Masculino"})
    assert r.status_code == 403 and "Membros" in r.json()["detail"]
    assert leitor.delete("/api/secretaria/membros/Ana Teste").status_code == 403
    assert leitor.put("/api/secretaria/config", json={"limite_aux": 20}).status_code == 403      # Ajustes: sem acesso
    # a página do módulo já chega com a aba Ajustes escondida
    html = leitor.get("/m/secretaria").text
    assert '[data-sec="ajustes"]' in html and "HUB_GOV" in html


def test_campo_ver_e_editar_sem_excluir(hub):
    import secretaria
    T.DB[(secretaria.COL_MEMBROS, "Bia Teste")] = {"nome_oficial": "Bia Teste", "categoria": "PUBLICADOR", "genero": "Feminino",
                                                  "data_nascimento": "01/02/1990", "telefone_emergencia": "Mãe 11 99999-0000"}
    chefe = entrar(hub(), "chefe", "senha-forte")
    _usuario(chefe, "edita", {"secretaria": {"acoes": {"acessar": True, "membros": True}, "gov": True,
                                            "campos": {"genero": "ver", "telefone_emergencia": "editar", "data_nascimento": "excluir"}}})
    secretaria.BASE.membros = None
    ed = entrar(hub(), "edita", "123456")
    base = {"nome_oficial": "Bia Teste", "categoria": "PUBLICADOR", "genero": "Feminino"}
    assert ed.put("/api/secretaria/membros/Bia Teste", json={**base, "genero": "Masculino"}).status_code == 403         # só ver
    assert ed.put("/api/secretaria/membros/Bia Teste", json={**base, "telefone_emergencia": "Pai 11 98888-0000"}).status_code == 200
    r = ed.put("/api/secretaria/membros/Bia Teste", json={**base, "telefone_emergencia": ""})
    assert r.status_code == 403 and "apagar" in r.json()["detail"]                                                    # editar ≠ excluir
    assert ed.put("/api/secretaria/membros/Bia Teste", json={**base, "data_nascimento": ""}).status_code == 200        # excluir


def test_sem_configurar_continua_como_antes(hub):
    import acesso
    esq = {"acoes": {"acessar": "x", "membros": "y"}, "campos": {"genero": "G"}, "abas": {"membros": {}}}
    p = acesso.permissoes({"modulos": {"secretaria": {"acoes": {"acessar": True}, "campos": {"genero": "editar"}}}}, "secretaria",
                          acesso.normalizar_esquema(esq))
    assert p["abas"] == {"membros": "excluir"} and p["campos_nivel"]["genero"] == "excluir" and p["campos"]["genero"] == "editar"


def test_rota_compartilhada_usa_a_aba_da_chave(hub):
    import governanca
    perm = lambda slug: {"acoes": {"acessar": True}, "abas": {"ajustes": "nenhum", "it": "editar", "fechamentos": "ver"}}
    u = {"login": "x"}
    assert governanca.checar(u, "PUT", "/api/secretaria/config", {"its": []}, perm) is None
    assert governanca.checar(u, "PUT", "/api/secretaria/config", {"pastas": []}, perm)
    assert governanca.checar(u, "PUT", "/api/secretaria/config", {"limite_aux": 3}, perm)


def test_corpo_lido_pela_governanca_chega_na_rota(hub):
    chefe = entrar(hub(), "chefe", "senha-forte")
    _usuario(chefe, "ajusta", {"secretaria": {"acoes": {"acessar": True, "ajustes": True}, "gov": True, "abas": {"ajustes": "editar"}}})
    aj = entrar(hub(), "ajusta", "123456")
    r = aj.put("/api/secretaria/config", json={"limite_aux": 21})
    assert r.status_code == 200, r.text
    assert aj.get("/api/secretaria/base").json()["config"]["limite_aux"] == 21
