"""Agente IA do topo — regras sem Firestore e sem IA externa.

    cd hub && python -m pytest tests/test_agente.py -q
"""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acesso  # noqa: E402
import agente as A  # noqa: E402

BANCO: dict = {}
EU: dict = {}
LIB = {"agente": {"acoes": {"acessar": True}}}
ALI = {"agente": {"acoes": {"acessar": True, "alimentar": True}}}
CONTAS = {
    "ana": {"nome": "Ana", "modulos": LIB},
    "chefe": {"nome": "Chefe", "modulos": ALI},
    "maria": {"nome": "Maria Paula", "modulos": LIB},
    "zeca": {"nome": "Zeca", "modulos": {}},
    "velho": {"nome": "Velho", "ativo": False, "modulos": LIB},
}
ARTIGO = {"titulo": "Como lançar uma encomenda no atelier", "setor": "Atelier",
          "passos": ["Abra o módulo Atelier.", "Clique em Nova encomenda.", "Preencha as datas de prova e entrega."],
          "palavras": "encomenda atelier lançar nova", "ativo": True}


@pytest.fixture()
def t(monkeypatch):
    BANCO.clear()
    A.P.update(
        listar=lambda col: [dict(v, id=k) for k, v in BANCO.get(col, {}).items()],
        ler=lambda col, i: (dict(BANCO[col][i], id=i) if i in BANCO.get(col, {}) else None),
        gravar=lambda col, i, d: BANCO.setdefault(col, {}).__setitem__(i, {k: v for k, v in d.items() if k != "id"}),
        desde=lambda col, campo, de: [dict(v, id=k) for k, v in BANCO.get(col, {}).items() if (v.get(campo) or "") >= de],
        usuarios=lambda: CONTAS,
    )
    A.esquecer_cache()
    monkeypatch.delenv("AGENTE_IA", raising=False)

    def usuario(request):
        if not EU:
            raise acesso.HTTPException(401, "Faça login.")
        return dict(EU)
    monkeypatch.setattr(acesso, "exigir_usuario", usuario)
    app = FastAPI()
    A.ligar(app)
    return TestClient(app)


def como(login, admin=False):
    EU.clear()
    EU.update({"login": login, "admin": admin, **{k: v for k, v in CONTAS.get(login, {"nome": login}).items()}})


def test_permissoes(t):
    como("zeca")
    assert t.get("/api/agente/me").status_code == 403            # agente não liberado → nem vê o botão
    como("ana")
    me = t.get("/api/agente/me").json()
    assert me["pode_alimentar"] is False
    assert t.post("/api/agente/artigos", json=ARTIGO).status_code == 403
    como("chefe")
    assert t.get("/api/agente/me").json()["pode_alimentar"] is True
    como("wendley", admin=True)
    assert t.post("/api/agente/artigos", json=ARTIGO).status_code == 200


def test_esquema_aparece_em_configuracoes():
    esq = acesso.normalizar_esquema(A.RECURSO["_esquema"])
    assert list(esq["acoes"]) == ["acessar", "alimentar"]
    assert A.RECURSO["tipo"] == "recurso" and A.RECURSO["url"] == ""   # não entra no menu


def test_pergunta_pendencia_e_versao(t):
    como("chefe")
    art = t.post("/api/agente/artigos", json=ARTIGO).json()
    como("ana")
    r = t.post("/api/agente/perguntar", json={"pergunta": "como lanço uma nova encomenda?"}).json()
    assert r["tipo"] == "resposta" and r["fonte"]["id"] == art["id"] and len(r["passos"]) == 3
    assert t.post("/api/agente/perguntar", json={"pergunta": "qual a senha do wifi?"}).json()["tipo"] == "nao_sei"
    t.post("/api/agente/retorno", json={"pergunta_id": r["pergunta_id"], "util": False, "obs": "faltou o sinal"})
    como("chefe")
    assert t.get("/api/agente/me").json()["pendencias"] == 2
    ed = t.put(f"/api/agente/artigos/{art['id']}", json={**ARTIGO, "passos": ARTIGO["passos"] + ["Registre o sinal."]}).json()
    assert ed["versao"] == 2 and len(ed["versoes"]) == 1
    rv = t.post(f"/api/agente/artigos/{art['id']}/restaurar", json={"versao": 1}).json()
    assert rv["versao"] == 3 and len(rv["passos"]) == 3
    p = t.get("/api/agente/painel").json()
    assert p["perguntas"] == 2 and p["respondidas"] == 1 and p["nao_resolveu"] == 1


def test_atribuir_responder_aprovar(t):
    como("ana")
    t.post("/api/agente/perguntar", json={"pergunta": "como faço o fechamento do caixa?"})
    como("chefe")
    pend = t.get("/api/agente/pendencias").json()["pendencias"][0]
    ps = {p["login"]: p for p in t.get("/api/agente/responsaveis").json()["pessoas"]}
    assert "velho" not in ps and ps["zeca"]["tem_login"] is False and ps["chefe"]["alimenta"] is True
    assert t.post(f"/api/agente/pendencias/{pend['id']}/atribuir", json={"login": "zeca"}).status_code == 400
    r = t.post(f"/api/agente/pendencias/{pend['id']}/atribuir", json={"login": "maria", "nota": "você faz isso todo dia"}).json()
    assert r["fase"] == "com_responsavel" and r["atribuida"]["nome"] == "Maria Paula"

    como("ana")
    assert t.post(f"/api/agente/pendencias/{pend['id']}/proposta", json={"titulo": "x", "passos": ["y"]}).status_code == 403
    como("maria")
    assert t.get("/api/agente/me").json()["comigo"] == 1
    prop = {"titulo": "Fechamento do caixa", "passos": ["Conte o dinheiro.", "Lance no sistema."], "palavras": "caixa fechamento"}
    assert t.post(f"/api/agente/pendencias/{pend['id']}/proposta", json=prop).json()["fase"] == "aguardando_aprovacao"
    como("chefe")
    assert t.post(f"/api/agente/pendencias/{pend['id']}/devolver", json={"motivo": "faltou o horário"}).json()["fase"] == "com_responsavel"
    como("maria")
    assert t.get("/api/agente/comigo").json()["pendencias"][0]["proposta"]["motivo_devolucao"] == "faltou o horário"
    t.post(f"/api/agente/pendencias/{pend['id']}/proposta", json={**prop, "passos": prop["passos"] + ["Até as 18h."]})
    como("chefe")
    art = t.post("/api/agente/artigos", json={**prop, "pendencia_id": pend["id"]}).json()
    assert all(p["id"] != pend["id"] for p in t.get("/api/agente/pendencias").json()["pendencias"])
    his = [h for h in t.get("/api/agente/historico").json()["historico"] if h["artigo_id"] == art["id"]][0]
    assert "Maria Paula" in his["detalhe"]
    como("ana")
    assert t.post("/api/agente/perguntar", json={"pergunta": "fechamento do caixa"}).json()["fonte"]["id"] == art["id"]
