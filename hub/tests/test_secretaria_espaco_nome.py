"""Salvar a ficha de quem tem espaço sobrando no nome não pode renomear (o id é o nome)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_empresas as T  # noqa: E402
from test_empresas import entrar, hub  # noqa: E402,F401  (fixture)


def test_editar_ficha_com_espaco_no_nome_nao_renomeia(hub):
    import secretaria
    T.DB[(secretaria.COL_MEMBROS, "Fulano de Tal ")] = {"nome_oficial": "Fulano de Tal ", "categoria": "PUBLICADOR"}
    chefe = entrar(hub(), "chefe", "senha-forte")
    secretaria.BASE.membros = None
    r = chefe.put("/api/secretaria/membros/" + "Fulano de Tal ", json={"genero": "Masculino", "data_nascimento": "01/02/1990"})
    assert r.status_code == 200 and r.json()["id"] == "Fulano de Tal "
    assert T.DB[(secretaria.COL_MEMBROS, "Fulano de Tal ")]["genero"] == "Masculino"
    assert (secretaria.COL_MEMBROS, "Fulano de Tal") not in T.DB
