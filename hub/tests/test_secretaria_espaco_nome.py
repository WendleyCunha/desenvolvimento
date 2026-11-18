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
