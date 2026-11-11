"""Pedidos de ajuda entre setores — cada setor vê só o seu, e a conversa vira chat.

    cd hub && python -m pytest tests/test_ajuda.py -q
"""
import sys
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acesso  # noqa: E402
import banco  # noqa: E402
import tickets as T  # noqa: E402
from test_cliente_app import FakeDB  # noqa: E402

USU = {"carla": {"nome": "Carla CX", "depto": "CX"}, "lucas": {"nome": "Lucas Log", "depto": "Logística"},
       "gil": {"nome": "Gil Compras", "depto": "Compras"}, "adm": {"nome": "Adm", "depto": ""}}


@pytest.fixture()
def t(monkeypatch):
    fake = FakeDB()
    monkeypatch.setenv("FIRESTORE_CREDS", "teste")
    monkeypatch.delenv("FIRESTORE_CREDS_TICKETS", raising=False)
    monkeypatch.setattr(banco, "db", lambda: fake)
    T.BASE.cont = {}
    T.BASE.t_completa = T.BASE.t_inc = time.time() + 3600
    T.BASE.cfg_cache = {"motivos_central": {"ticket": T.MOTIVOS_PADRAO}, "departamentos": {"lista": T.DEPARTAMENTOS_PADRAO},
                        "tickets_hub": {}, "usuarios": USU}
    T.BASE.t_cfg = time.time() + 3600
    quem = {"login": "carla"}
    monkeypatch.setattr(acesso, "exigir_usuario", lambda request: {"login": quem["login"], "nome": USU[quem["login"]]["nome"]})
    monkeypatch.setattr(acesso, "obter_esquema", lambda slug: {"acoes": {}, "campos": {}})

    def perms(u, slug, esq):
        a = {k: True for k in ("acessar", "atender", "abrir", "encerrar", "equipe")}
        if u["login"] == "adm":
            a["configurar"] = True
        return {"acoes": a, "campos": {}}
    monkeypatch.setattr(acesso, "permissoes", perms)
    app = FastAPI()
    app.include_router(T.router)
    c = TestClient(app)
    c.como = lambda login: quem.__setitem__("login", login)
    c.quem = lambda: quem["login"]
    return c


def abrir_e_pedir(t, destino="Logística", msg="Cadê a carga 123?"):
    t.como("carla")
    r = t.post("/api/tickets/tickets", json={"departamento": "Compras", "cliente_codigo": "ABC123", "cliente_nome": "Ana",
                                             "assunto": "Entrega", "descricao": "atrasou"}).json()
    assert t.post("/api/tickets/ticket/" + quote(r["id"], safe="") + "/pendencia", json={"setor": destino, "mensagem": msg}).status_code == 200
    return r["id"]


def test_cada_setor_ve_so_o_seu(t):
    abrir_e_pedir(t, "Logística")
    t.como("lucas")
    r = t.get("/api/tickets/ajuda").json()
    assert [v["papel"] for v in r["pedidos"]] == ["recebido"] and r["abertos_recebidos"] == 1
    # o setor de quem pediu é o do usuário (CX), não o do ticket (Compras)
    assert r["pedidos"][0]["setor_origem"] == "CX"
    t.como("gil")   # Compras não vê o pedido feito à Logística (mesmo o ticket sendo de Compras)
    assert t.get("/api/tickets/ajuda").json()["pedidos"] == []
    t.como("carla")
    assert [v["papel"] for v in t.get("/api/tickets/ajuda").json()["pedidos"]] == ["enviado"]
    t.como("gil")   # e não pode escrever nele
    v = {"tid": abrir_tid(t), "pid": "x", "texto": "oi"}
    assert t.post("/api/tickets/ajuda/mensagem", json=v).status_code == 404


def abrir_tid(t):
    return next(iter(T.BASE.cont)) + "#" + T.BASE.cont[next(iter(T.BASE.cont))]["solicitacoes"][0]["sid"]


def test_conversa_em_chat_e_encerramento(t):
    tid = abrir_e_pedir(t, "Logística")
    t.como("lucas")
    v = t.get("/api/tickets/ajuda").json()["pedidos"][0]
    assert t.post("/api/tickets/ajuda/mensagem", json={"tid": tid, "pid": v["id"], "texto": "Vou ver com o motorista"}).status_code == 200
    t.como("carla")
    assert t.post("/api/tickets/ajuda/mensagem", json={"tid": tid, "pid": v["id"], "texto": "Obrigada!"}).status_code == 200
    t.como("gil")
    assert t.post("/api/tickets/ajuda/mensagem", json={"tid": tid, "pid": v["id"], "texto": "intrometido"}).status_code == 403
    t.como("lucas")
    assert t.post("/api/tickets/ajuda/mensagem", json={"tid": tid, "pid": v["id"], "texto": "Sai amanhã cedo", "encerrar": True}).status_code == 200
    v2 = t.get("/api/tickets/ajuda").json()["pedidos"][0]
    assert v2["status"] == "resolvido" and [m["texto"] for m in v2["conversa"]] == ["Cadê a carga 123?", "Vou ver com o motorista", "Obrigada!", "Sai amanhã cedo"]
    assert t.post("/api/tickets/ajuda/mensagem", json={"tid": tid, "pid": v["id"], "texto": "de novo"}).status_code == 409
    # tudo fica registrado no atendimento
    coms = [c["texto"] for c in T.BASE.cont[tid.split("#")[0]]["solicitacoes"][0]["comentarios"]]
    assert any("Vou ver com o motorista" in x for x in coms) and any("encerrado" in x for x in coms)
    t.como("carla")   # a pendência sai do atendimento depois de encerrada
    assert T.pend_abertas(T.BASE.tickets()[0]) == []


def test_quem_configura_escolhe_o_setor(t):
    abrir_e_pedir(t, "Logística")
    t.como("adm")
    assert t.get("/api/tickets/ajuda").json()["pedidos"] == []                       # sem setor: nada
    assert len(t.get("/api/tickets/ajuda?setor=Logística").json()["pedidos"]) == 1     # escolheu ver a Logística
    t.como("carla")
    assert t.get("/api/tickets/ajuda?setor=Logística").json()["setor"] == "CX"          # quem não configura ignora o parâmetro


def test_conversa_com_a_equipe_sem_cliente(t):
    T._DM.clear()
    T.ONLINE.clear()
    t.como("carla")
    t.get("/api/tickets/ajuda")
    t.como("lucas")
    on = t.get("/api/tickets/ajuda").json()["online"]
    assert [x["usuario"] for x in on] == ["carla"]                      # quem está com o hub aberto (menos eu)
    assert t.post("/api/tickets/conversa", json={"para": "carla", "texto": "Oi Carla, a carga saiu?"}).status_code == 200
    assert t.post("/api/tickets/conversa", json={"para": "lucas", "texto": "eu mesmo"}).status_code == 400
    t.como("carla")
    cv = t.get("/api/tickets/ajuda").json()["conversas"]
    assert cv[0]["com"] == "lucas" and cv[0]["ultimo_de"] == "lucas"
    t.post("/api/tickets/conversa", json={"para": "lucas", "texto": "Saiu sim!"})
    assert [m["texto"] for m in t.get("/api/tickets/conversa/lucas").json()["mensagens"]] == ["Oi Carla, a carga saiu?", "Saiu sim!"]
    T._DM.clear()   # relê do banco: ficou gravado
    t.como("lucas")
    assert len(t.get("/api/tickets/conversa/carla").json()["mensagens"]) == 2
    assert not T.BASE.cont   # nada de cliente/ticket criado


def test_finalizar_nos_tres_cenarios(t, monkeypatch):
    # 1) pedido de ajuda (com código): finaliza mesmo sem mensagem final
    tid = abrir_e_pedir(t, "Logística")
    t.como("lucas")
    v = t.get("/api/tickets/ajuda").json()["pedidos"][0]
    assert t.post("/api/tickets/ajuda/mensagem", json={"tid": tid, "pid": v["id"], "texto": "", "encerrar": True}).status_code == 200
    assert t.get("/api/tickets/ajuda").json()["pedidos"][0]["status"] == "resolvido"
    # 2) conversa com a equipe (sem código): finaliza para os dois; mensagem nova reabre
    T._DM.clear()
    t.post("/api/tickets/conversa", json={"para": "carla", "texto": "oi"})
    assert t.post("/api/tickets/conversa/finalizar", json={"para": "carla"}).status_code == 200
    t.como("carla")
    assert t.get("/api/tickets/ajuda").json()["conversas"][0]["finalizada"] is True
    t.post("/api/tickets/conversa", json={"para": "lucas", "texto": "mais uma"})
    assert t.get("/api/tickets/ajuda").json()["conversas"][0]["finalizada"] is False
    assert t.post("/api/tickets/conversa/finalizar", json={"para": "gil"}).status_code == 404   # sem conversa
    # 3) solicitação interna (sem código): o setor de destino finaliza mesmo sem a permissão "encerrar"
    import acesso
    t.como("adm")
    assert t.put("/api/tickets/config/motivos", json={"setor": "Logística", "motivos": {"Predial": {"Torneira": {"sla": 1, "ativo": True, "etapas": [], "exige_codigo": False}}}}).status_code == 200
    T.BASE.t_cfg = time.time() + 3600
    t.como("carla")
    r = t.post("/api/tickets/tickets", json={"departamento": "Logística", "motivo_pai": "Predial", "motivo_filho": "Torneira", "assunto": "pingando", "descricao": "copa"}).json()
    sem_encerrar = lambda u, slug, esq: {"acoes": {k: True for k in ("acessar", "atender", "abrir")}, "campos": {}}  # noqa: E731
    monkeypatch.setattr(acesso, "permissoes", sem_encerrar)
    u = "/api/tickets/ticket/" + quote(r["id"], safe="") + "/alterar"
    t.como("gil")      # Compras não é o setor nem quem pediu
    assert t.post(u, json={"status": "finalizado"}).status_code in (403, 404)
    t.como("lucas")    # Logística: finaliza
    assert t.post(u, json={"status": "finalizado"}).status_code == 200
