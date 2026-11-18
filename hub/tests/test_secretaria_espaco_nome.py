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


class _Lote:
    def __init__(self):
        self.ops = []

    def set(self, ref, d, merge=False):
        self.ops.append(lambda: ref.set(d, merge=merge))

    def delete(self, ref):
        self.ops.append(ref.delete)

    def commit(self, **k):
        for o in self.ops:
            o()


def test_renomear_guarda_a_ficha_antiga(hub, monkeypatch):
    import secretaria
    monkeypatch.setattr(T._Fake, "batch", lambda self: _Lote(), raising=False)
    T.DB[(secretaria.COL_MEMBROS, "Ana Exemplo")] = {"nome_oficial": "Ana Exemplo", "categoria": "PUBLICADOR", "genero": "Feminino"}
    T.DB[(secretaria.COL_REL, "r1")] = {"nome": "Ana Exemplo", "membro_id": "Ana Exemplo", "mes_referencia": "Outubro 2026", "participou_ministerio": True}
    chefe = entrar(hub(), "chefe", "senha-forte")
    secretaria.BASE.membros = None
    r = chefe.put("/api/secretaria/membros/Ana Exemplo", json={"nome_oficial": "Ana Exemplo Souza"})
    assert r.json()["id"] == "Ana Exemplo Souza"
    antiga = T.DB[(secretaria.COL_MEMBROS, "Ana Exemplo")]                   # NÃO foi apagada
    assert antiga["renomeado_para"] == "Ana Exemplo Souza" and antiga["genero"] == "Feminino"
    nova = T.DB[(secretaria.COL_MEMBROS, "Ana Exemplo Souza")]
    assert nova["nomes_anteriores"] == ["Ana Exemplo"] and T.DB[(secretaria.COL_REL, "r1")]["membro_id"] == "Ana Exemplo Souza"
    secretaria.BASE.membros = None
    ids = [m["id"] for m in chefe.get("/api/secretaria/base").json()["membros"]]
    assert "Ana Exemplo Souza" in ids and "Ana Exemplo" not in ids              # a guardada não aparece nas listas
    r = chefe.post("/api/secretaria/membros", json={"nome_oficial": "Ana Exemplo"})
    assert r.status_code == 409 and "renomeada" in r.json()["detail"]
    # relatório novo que chegar com o nome antigo cai na ficha nova
    T.DB[(secretaria.COL_REL, "r2")] = {"nome": "Ana Exemplo", "mes_referencia": "Setembro 2026", "participou_ministerio": True}
    secretaria.BASE.atualizar(forcar=True)
    assert [ln["membro_id"] for ln in secretaria.BASE.linhas() if ln["id"] == "r2"] == ["Ana Exemplo Souza"]


def test_selo_ficha_completa_e_excluir(hub):
    import secretaria
    assert secretaria.campos_faltando({"nome_oficial": "X", "categoria": "PUBLICADOR", "grupo": "g1", "genero": "Feminino", "classe": "Outras ovelhas",
                                       "data_nascimento": "01/02/1990", "data_batismo": "NB", "telefone_emergencia": "Ana, filha 11 99999-0000"}) == []
    assert secretaria.campos_faltando({"nome_oficial": "X", "categoria": "PUBLICADOR", "data_batismo": "26/12/1071"}) == [
        "Grupo de campo", "Gênero", "Classe", "Data de nascimento", "Data de batismo", "Telefone de emergência"]
    T.DB[(secretaria.COL_MEMBROS, "Bia Completa")] = {"nome_oficial": "Bia Completa", "categoria": "PUBLICADOR", "grupo": "g1", "genero": "Feminino",
                                                     "classe": "Outras ovelhas", "data_nascimento": "01/02/1990", "data_batismo": "03/04/2005",
                                                     "telefone_emergencia": "Carlos, irmão 11 98888-7777 / Ana, mãe 11 97777-6666"}
    T.DB[(secretaria.COL_MEMBROS, "Rui Incompleto")] = {"nome_oficial": "Rui Incompleto", "categoria": "PUBLICADOR"}
    chefe = entrar(hub(), "chefe", "senha-forte")
    secretaria.BASE.membros = None
    ms = {m["id"]: m for m in chefe.get("/api/secretaria/base").json()["membros"]}
    assert ms["Bia Completa"]["completo"] is True and ms["Rui Incompleto"]["completo"] is False and "Gênero" in ms["Rui Incompleto"]["faltando"]
    assert chefe.get("/api/secretaria/membro/Bia Completa").json()["membro"]["completo"] is True
    longo = "Carlos, irmão 11 98888-7777 / Ana, mãe 11 97777-6666 / trabalho 11 3333-4444"
    chefe.put("/api/secretaria/membros/Rui Incompleto", json={"telefone_emergencia": longo})
    assert T.DB[(secretaria.COL_MEMBROS, "Rui Incompleto")]["telefone_emergencia"] == longo          # não corta em 40
    assert chefe.delete("/api/secretaria/membros/Rui Incompleto").status_code == 200
    assert "excluido_em" in T.DB[(secretaria.COL_MEMBROS, "Rui Incompleto")]                          # guardada, não apagada
    secretaria.BASE.membros = None
    assert "Rui Incompleto" not in {m["id"] for m in chefe.get("/api/secretaria/base").json()["membros"]}
    assert chefe.post("/api/secretaria/membros", json={"nome_oficial": "Rui Incompleto"}).status_code == 409
