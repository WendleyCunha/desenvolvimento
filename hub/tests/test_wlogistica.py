"""WLOGISTICA: carga do ERP → montagem do palete → doca (outra pessoa) → liberada → saída → retorno no CD."""
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import acesso  # noqa: E402
import banco  # noqa: E402
import erp as E  # noqa: E402
import wlogistica as W  # noqa: E402
from test_cliente_app import FakeDB  # noqa: E402


class Tudo(dict):
    def get(self, k, d=None):
        return True


USR = {"login": "ana", "nome": "Ana Montagem"}


@pytest.fixture()
def t(monkeypatch):
    fake = FakeDB()
    monkeypatch.setenv("FIRESTORE_CREDS", "teste")
    monkeypatch.setattr(banco, "db", lambda: fake)
    E.ST.pronto = True
    E.ST.config = {**E.CONFIG_PADRAO, "seq": {"pedido": 10, "carga": 0}}
    E.ST.dados = {k: {} for k in E.COLS}
    E.ST.dados["produtos"] = {"p1": {"nome": "Colchão Casal", "sku": "CM138", "volumes": 1},
                              "p2": {"nome": "Base Box Casal", "sku": "BX2", "ean": "789100", "volumes": 2}}
    E.ST.dados["parceiros"] = {"v1": {"tipo": "veiculo", "nome": "Furgão", "placa": "ABC1D23"}, "m1": {"tipo": "motorista", "nome": "João"},
                               "c1": {"tipo": "cliente", "nome": "Maria"}, "c2": {"tipo": "cliente", "nome": "Pedro"}}
    E.ST.dados["saldos"] = {"p1": {"reservado": 3, "disponivel": 5}, "p2": {"reservado": 1}}
    base = {"status": "agendado", "tipo": "venda", "reservado": True, "historico": [], "tentativas": [], "agendamento": {"data": "2026-11-20"}}
    E.ST.dados["pedidos"] = {
        "ped1": {**base, "numero": 1, "cliente_id": "c1", "cliente_nome": "Maria", "itens": [{"produto_id": "p1", "qtd": 1}, {"produto_id": "p2", "qtd": 1}],
                 "pendentes": [{"produto_id": "p1", "qtd": 1}, {"produto_id": "p2", "qtd": 1}]},
        "ped2": {**base, "numero": 2, "cliente_id": "c2", "cliente_nome": "Pedro", "itens": [{"produto_id": "p1", "qtd": 2}], "pendentes": [{"produto_id": "p1", "qtd": 2}]},
        "ped3": {**base, "numero": 3, "cliente_id": "c2", "cliente_nome": "Pedro", "reservado": False, "itens": [{"produto_id": "p1", "qtd": 1}],
                 "pendentes": [{"produto_id": "p1", "qtd": 1}]},
    }
    USR.update(login="ana", nome="Ana Montagem")
    monkeypatch.setattr(acesso, "exigir_usuario", lambda request: dict(USR))
    monkeypatch.setattr(acesso, "obter_esquema", lambda slug: {"acoes": {}, "campos": {}})
    monkeypatch.setattr(acesso, "permissoes", lambda u, slug, esq: {"acoes": Tudo(), "campos": {}})
    app = FastAPI()
    app.include_router(E.router)
    app.include_router(W.router)
    return TestClient(app)


def como(login, nome):
    USR.update(login=login, nome=nome)


def nova_carga(t, peds=("ped1", "ped2")):
    r = t.post("/api/erp/cargas", json={"pedidos": list(peds), "veiculo_id": "v1", "motorista_id": "m1", "data": "2026-11-20"})
    assert r.status_code == 200, r.text
    return r.json()["carga_id"]


def test_fluxo_completo(t):
    cid = nova_carga(t)
    assert t.post(f"/api/erp/cargas/{cid}/sair").status_code == 409, "sem a conferência do armazém a carga não sai"
    c = next(x for x in t.get("/api/wlog/estado").json()["cargas"] if x["id"] == cid)
    assert c["status"] == "aguardando" and c["volumes"] == 5 and c["placa"] == "ABC1D23", "1 colchão + base de 2 volumes + 2 colchões = 5 volumes"

    # 1ª conferência: montagem do palete (Ana)
    lt = lambda **k: t.post(f"/api/wlog/cargas/{cid}/montagem/leitura", json=k).json()
    r = lt(codigo="cm138")
    assert r["resultado"] == "escolher_pedido" and {o["numero"] for o in r["opcoes"]} == {1, 2}, "mesmo produto em 2 pedidos: pergunta qual"
    assert lt(codigo="CM138", pedido="ped1")["resultado"] == "ok"
    assert lt(codigo="789100")["resultado"] == "ok" and lt(codigo="BX2")["resultado"] == "ok", "EAN ou SKU valem; base tem 2 volumes"
    r = lt(codigo="789100")
    assert r["resultado"] == "sobra" and "A MAIS" in r["mensagem"]
    t.post(f"/api/wlog/cargas/{cid}/montagem/desfazer", json={"unidade": r["carga"]["sobras"]["montagem"][0]["id"]})
    assert lt(codigo="XYZ")["resultado"] == "sobra", "produto que não é da carga"
    sob = t.get(f"/api/wlog/cargas/{cid}").json()["sobras"]["montagem"][0]["id"]
    t.post(f"/api/wlog/cargas/{cid}/montagem/desfazer", json={"unidade": sob})
    u2 = [u for u in t.get(f"/api/wlog/cargas/{cid}").json()["unidades"] if u["pid"] == "ped2"]
    assert lt(unidade=u2[0]["id"])["resultado"] == "exige_codigo", "produto com código não confirma só tocando"
    assert t.post(f"/api/wlog/cargas/{cid}/montagem/leitura", json={"unidade": u2[0]["id"], "sem_leitor": True}).status_code == 400, "sem leitor exige motivo"
    assert lt(unidade=u2[0]["id"], sem_leitor=True, motivo="etiqueta rasgada")["resultado"] == "ok"
    assert lt(codigo="CM138")["resultado"] == "ok", "só sobrou o pedido 2: não pergunta"
    r = t.post(f"/api/wlog/cargas/{cid}/montagem/finalizar", json={}).json()
    assert r["resultado"] == "ok" and r["status"] == "montada" and not r["divergencias"]
    assert t.put(f"/api/erp/cargas/{cid}", json={"pedidos": ["ped1"]}).status_code == 409, "armazém começou: pedidos só pelo WLOGISTICA"

    # 2ª conferência: doca por OUTRA pessoa
    assert t.post(f"/api/wlog/cargas/{cid}/doca/leitura", json={"codigo": "CM138", "pedido": "ped1"}).status_code == 403, "quem montou não confere a doca"
    como("bia", "Bia Doca")
    ld = lambda **k: t.post(f"/api/wlog/cargas/{cid}/doca/leitura", json=k).json()
    for k in ({"codigo": "CM138", "pedido": "ped1"}, {"codigo": "BX2"}, {"codigo": "BX2"}, {"codigo": "CM138"}):
        assert ld(**k)["resultado"] == "ok"
    r = t.post(f"/api/wlog/cargas/{cid}/doca/finalizar", json={}).json()
    assert r["resultado"] == "precisa_motivo" and r["divergencias"][0]["tipo"] == "falta" and r["divergencias"][0]["numero"] == 2
    ch = r["divergencias"][0]["chave"]
    r = t.post(f"/api/wlog/cargas/{cid}/doca/finalizar", json={"respostas": [{"chave": ch, "motivo": "Produto não localizado no estoque"}]}).json()
    assert r["status"] == "divergencia"
    est = t.get("/api/wlog/estado").json()
    assert len(est["pendencias"]) == 1 and t.post(f"/api/erp/cargas/{cid}/sair").status_code == 409, "com apontamento aberto não sai"
    pid = est["pendencias"][0]["id"]
    assert t.put(f"/api/wlog/cargas/{cid}/pendencias/{pid}", json={"nota": ""}).status_code == 400
    c = t.put(f"/api/wlog/cargas/{cid}/pendencias/{pid}", json={"nota": "peça localizada e carregada"}).json()
    assert c["status"] == "liberada" and c["liberada"]["por"] == "Bia Doca"

    # saída e retorno no CD
    assert t.post(f"/api/erp/cargas/{cid}/sair").status_code == 200
    assert t.post(f"/api/erp/cargas/{cid}/baixa", json={"pedido_id": "ped1", "resultado": "entregue"}).status_code == 200
    assert t.post(f"/api/erp/cargas/{cid}/baixa", json={"pedido_id": "ped2", "resultado": "ausente", "motivo": "Cliente ausente"}).status_code == 200
    c = t.get(f"/api/wlog/cargas/{cid}").json()
    assert c["status"] == "finalizada" and c["retorno"]["total"] == 2 and c["retorno"]["pendentes"] == 2, "ausente: as 2 peças voltam para o CD"
    a, b = [x["id"] for x in c["retorno_itens"]]
    como("caio", "Caio Retorno")
    assert t.post(f"/api/wlog/cargas/{cid}/retorno/concluir").status_code == 409
    assert t.post(f"/api/wlog/cargas/{cid}/retorno/receber", json={"item_id": a, "estado": "ok"}).status_code == 200
    assert t.post(f"/api/wlog/cargas/{cid}/retorno/nao-voltou", json={"item_id": b, "obs": ""}).status_code == 400
    c = t.post(f"/api/wlog/cargas/{cid}/retorno/nao-voltou", json={"item_id": b, "obs": "motorista não trouxe"}).json()
    assert c["retorno"]["pendentes"] == 0 and any(p["tipo"] == "nao_voltou" for p in c["pendencias"]), "o que não voltou vira apontamento"
    assert t.post(f"/api/wlog/cargas/{cid}/retorno/concluir").json()["retorno"]["fim"]["por"] == "Caio Retorno"


def test_ajuste_trava_a_etapa(t):
    cid = nova_carga(t)
    assert t.post(f"/api/wlog/cargas/{cid}/montagem/leitura", json={"codigo": "BX2"}).json()["resultado"] == "ok"
    assert t.post(f"/api/wlog/cargas/{cid}/ajuste", json={"tipo": "retirar", "pedido_id": "ped1", "motivo": ""}).status_code == 400
    r = t.post(f"/api/wlog/cargas/{cid}/ajuste", json={"tipo": "retirar", "pedido_id": "ped1", "motivo": "cliente adiou"}).json()
    assert r["ajuste"]["status"] == "pendente" and r["carga"]["volumes"] == 2 and r["carga"]["montagem"]["lidas"] == 0, "leituras do pedido retirado saem"
    assert E.ST.dados["pedidos"]["ped1"]["status"] == "agendado" and not E.ST.dados["pedidos"]["ped1"]["carga_id"], "o pedido volta para agendado no ERP"
    assert t.post(f"/api/wlog/cargas/{cid}/montagem/leitura", json={"codigo": "CM138"}).status_code == 423, "travada até confirmarem o ajuste no palete"
    t.post(f"/api/wlog/cargas/{cid}/ajuste/{r['ajuste']['id']}/feito")
    assert t.post(f"/api/wlog/cargas/{cid}/montagem/leitura", json={"codigo": "CM138"}).json()["resultado"] == "ok"
    r = t.post(f"/api/wlog/cargas/{cid}/ajuste", json={"tipo": "agrupar", "pedido_id": "ped3", "motivo": "entrou de última hora"}).json()
    assert r["carga"]["volumes"] == 3 and E.ST.dados["pedidos"]["ped3"]["status"] == "em_carga"


def test_sem_exigir_o_armazem_a_carga_sai(t):
    cid = nova_carga(t, ("ped2",))
    assert t.put("/api/wlog/config", json={"exigir": False}).json()["cfg"]["exigir"] is False
    assert t.post(f"/api/erp/cargas/{cid}/sair").status_code == 200


def test_resumo_do_retorno_tem_totais_e_chegada_no_cd():
    """Card do Retorno: totais dos pedidos (ícones) e se o caminhão já chegou no CD (separa as etapas)."""
    import wlogistica as WL
    car = {"pedidos": ["a", "b", "c", "d"], "baixas": {"a": "entregue", "b": "ausente", "c": "avaria"}, "rota": {"chegada": {"em": "2026-11-26T16:00:00"}}}
    assert WL.baixas_resumo(car) == {"total": 4, "entregues": 1, "retornos": 2, "sem_baixa": 1}
    assert ((car.get("rota") or {}).get("chegada") or {}).get("em") == "2026-11-26T16:00:00"
