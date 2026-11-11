"""Motivos por setor, retabulação e fila do setor.

    cd hub && python -m pytest tests/test_motivos_setor.py -q
"""
import time
from urllib.parse import quote

import tickets as T
from test_ajuda import t  # noqa: F401  (fixture)

def salvar(t, motivos, setor):
    assert t.put("/api/tickets/config/motivos", json={"motivos": motivos, "setor": setor}).status_code == 200
    T.BASE.t_cfg = time.time() + 3600   # o FakeDB não relê usuários; o cache já foi atualizado pelo PUT


LOG = {"Entrega": {"Atraso": {"sla": 5, "ativo": True, "etapas": ["Rastrear", "Reagendar"]}}}


def test_arvore_por_setor_e_retabular(t):  # noqa: F811
    t.como("adm")
    salvar(t, LOG, "Logística")
    e = t.get("/api/tickets/estado").json()
    assert e["motivos_setor"]["Logística"]["Entrega"]["Atraso"]["exige_codigo"] is True and "Entrega" not in e["motivos"]   # a geral continua a mesma
    t.como("carla")
    r = t.post("/api/tickets/tickets", json={"departamento": "Logística", "cliente_codigo": "C1", "cliente_nome": "Ana", "assunto": "x",
                                             "descricao": "y", "motivo_pai": "Entrega", "motivo_filho": "Atraso"}).json()
    tid = r["id"]; u = "/api/tickets/ticket/" + quote(tid, safe="")
    s = lambda: next(x for x in T.BASE.tickets() if x["id"] == tid)  # noqa: E731
    assert s()["sla1_prazo_dias"] == 5
    # trava o prazo e depois corrige a tabulação: muda setor/motivo, o prazo combinado continua
    assert t.post(u + "/classificar", json={"motivo_pai": "Entrega", "motivo_filho": "Atraso", "etapa": "Rastrear", "data_prevista": "2099-01-01"}).status_code == 200
    geral = next(iter(T.MOTIVOS_PADRAO.items()))
    pai, filho = geral[0], next(iter(geral[1]))
    et = (geral[1][filho].get("etapas") or [""])[0]
    assert t.post(u + "/classificar", json={"departamento": "Logística", "motivo_pai": pai, "motivo_filho": filho}).status_code == 400   # fora da árvore da Logística
    rr = t.post(u + "/classificar", json={"departamento": "CX", "motivo_pai": pai, "motivo_filho": filho, "etapa": et}); assert rr.status_code == 200, rr.text
    x = s()
    assert (x["departamento"], x["motivo_pai"], x["motivo_filho"]) == ("CX", pai, filho)
    assert x["etapa_travada"] and x["etapa_data_prevista"] == "2099-01-01"
    assert any("Tabulação ajustada" in c["texto"] for c in x["comentarios"])
    # apagar a árvore do setor = volta a usar a geral
    t.como("adm")
    salvar(t, {}, "Logística")
    assert "Logística" not in t.get("/api/tickets/estado").json()["motivos_setor"]


def test_setor_ve_o_que_foi_aberto_para_ele(t, monkeypatch):  # noqa: F811
    import acesso
    sem_equipe = lambda u, slug, esq: {"acoes": {k: True for k in ("acessar", "atender", "abrir", "encerrar")}, "campos": {}}  # noqa: E731
    t.como("carla")
    tid = t.post("/api/tickets/tickets", json={"departamento": "Logística", "cliente_codigo": "C2", "cliente_nome": "Bia",
                                               "assunto": "x", "descricao": "y"}).json()["id"]
    monkeypatch.setattr(acesso, "permissoes", sem_equipe)
    t.como("lucas")   # Logística, sem permissão de equipe: vê o ticket do setor
    assert tid in [x["id"] for x in t.get("/api/tickets/estado").json()["tickets"]]
    t.como("gil")     # Compras: não vê
    assert tid not in [x["id"] for x in t.get("/api/tickets/estado").json()["tickets"]]


def test_submotivo_sem_codigo_vira_solicitacao_interna(t):  # noqa: F811
    t.como("adm")
    salvar(t, {"Predial": {"Torneira": {"sla": 2, "ativo": True, "etapas": [], "exige_codigo": False}}}, "Manutenção")
    t.como("carla")
    r = t.post("/api/tickets/tickets", json={"departamento": "Manutenção", "motivo_pai": "Predial", "motivo_filho": "Torneira",
                                             "assunto": "Torneira pingando", "descricao": "copa do 2º andar"})
    assert r.status_code == 200 and r.json()["interno"], r.text      # sem código de cliente e mesmo assim abre
    x = next(x for x in t.get("/api/tickets/estado").json()["tickets"] if x["id"] == r.json()["id"])
    assert x["interno"] and x["cliente_codigo"] == "INTERNO-carla" and x["departamento"] == "Manutenção"
    # não entra na fila da Caixa (pegar o próximo)
    assert t.get("/api/tickets/estado").json()["fila"]["clientes"] == 0
    # um submotivo que exige código continua exigindo
    assert t.post("/api/tickets/tickets", json={"departamento": "Logística", "assunto": "x", "descricao": "y"}).status_code == 400
