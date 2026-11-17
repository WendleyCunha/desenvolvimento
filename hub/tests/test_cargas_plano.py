"""ERP · Planejamento de cargas: puxar pedidos de outros dias, sugerir cargas (pontos/m³/kg/raio), faturamento."""
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WROUTER_GEO"] = "0"

import acesso  # noqa: E402
import banco  # noqa: E402
import cargas_plano as P  # noqa: E402
import erp as E  # noqa: E402
import wrouter as WR  # noqa: E402
from test_cliente_app import FakeDB  # noqa: E402


class Tudo(dict):
    def get(self, k, d=None):
        return True


USR = {"login": "ana", "nome": "Ana"}
CD = {"lat": -23.55, "lng": -46.63}
END = {"logradouro": "Rua A", "numero": "1", "bairro": "Centro", "cidade": "São Paulo", "uf": "SP", "cep": ""}


def ped(n, lat, lng, data="2026-11-21", status="agendado", janela="", qtd=1, criado="2026-11-01T10:00:00", reservado=True):
    end = {**END, "numero": str(n)}
    p = {"numero": n, "cliente_id": "c1", "cliente_nome": f"Cliente {n}", "status": status, "tipo": "venda", "reservado": reservado,
         "historico": [], "tentativas": [], "endereco": end, "criado_em": criado,
         "itens": [{"produto_id": "p1", "qtd": qtd}], "pendentes": [{"produto_id": "p1", "qtd": qtd}]}
    if data:
        p["agendamento"] = {"data": data, "janela": janela}
    if lat is not None:
        p["geo"] = {"lat": lat, "lng": lng, "chave": P.chave_endereco(end)}
    return p


@pytest.fixture()
def t(monkeypatch):
    fake = FakeDB()
    monkeypatch.setenv("FIRESTORE_CREDS", "teste")
    monkeypatch.setattr(banco, "db", lambda: fake)
    E.ST.pronto = True
    E.ST.config = {**E.CONFIG_PADRAO, "seq": {"pedido": 10, "carga": 0}, "wlog": {"exigir": False}, "plano": {"cd": {"endereco": "CD", **CD}}}
    E.ST.dados = {k: {} for k in E.COLS}
    E.ST.dados["produtos"] = {"p1": {"nome": "Colchão", "sku": "C1", "volumes": 1, "cubagem": 0.5, "peso": 30}}
    E.ST.dados["parceiros"] = {"c1": {"tipo": "cliente", "nome": "X"}, "m1": {"tipo": "motorista", "nome": "João"},
                               "v1": {"tipo": "veiculo", "nome": "Furgão", "placa": "AAA1A11", "max_pontos": 3},
                               "v2": {"tipo": "veiculo", "nome": "Toco", "placa": "BBB2B22", "max_m3": 1.2}}
    E.ST.dados["saldos"] = {"p1": {"reservado": 50, "disponivel": 10}}
    # dois bairros: 3 pedidos a ~1 km do CD (norte) e 3 a ~20 km (sul)
    E.ST.dados["pedidos"] = {
        "a1": ped(1, -23.540, -46.630), "a2": ped(2, -23.541, -46.631, data="2026-11-25"), "a3": ped(3, -23.539, -46.629, janela="Tarde"),
        "b1": ped(4, -23.730, -46.630, janela="Manhã"), "b2": ped(5, -23.732, -46.631), "b3": ped(6, -23.731, -46.629, data="", status="confirmado"),
        "x": ped(7, None, None), "y": ped(8, -23.6, -46.6, status="confirmado", data="", reservado=False),
    }
    USR.update(login="ana", nome="Ana")
    monkeypatch.setattr(acesso, "exigir_usuario", lambda request: dict(USR))
    monkeypatch.setattr(acesso, "obter_esquema", lambda slug: {"acoes": {}, "campos": {}})
    monkeypatch.setattr(acesso, "permissoes", lambda u, slug, esq: {"acoes": Tudo(), "campos": {}})
    app = FastAPI()
    app.include_router(E.router)
    app.include_router(P.router)
    return TestClient(app)


def test_puxar_pedido_de_outro_dia_e_sem_agenda(t):
    r = t.post("/api/erp/cargas", json={"data": "2026-11-21", "pedidos": ["a1", "a2", "b3"]})
    assert r.status_code == 200, r.text
    a2, b3 = E.ST.dados["pedidos"]["a2"], E.ST.dados["pedidos"]["b3"]
    assert a2["agendamento"]["data"] == "2026-11-21" and a2["status"] == "em_carga"
    assert any("antecipada de 25/11 para 21/11" in h["evento"] for h in a2["historico"]), "fica no histórico (vai para o ticket/app)"
    assert b3["agendamento"]["data"] == "2026-11-21" and any("Agendado para 21/11" in h["evento"] for h in b3["historico"])
    assert t.post("/api/erp/cargas", json={"data": "2026-11-21", "pedidos": ["y"]}).status_code == 409, "sem estoque reservado não entra"
    cid = r.json()["carga_id"]
    assert t.put(f"/api/erp/cargas/{cid}", json={"data": "2026-11-22"}).status_code == 200
    assert {E.ST.dados["pedidos"][i]["agendamento"]["data"] for i in ("a1", "a2", "b3")} == {"2026-11-22"}, "a agenda acompanha a carga"


def test_sugere_por_distancia_e_limites(t):
    ids = ["a1", "a2", "a3", "b1", "b2", "b3", "x", "y"]
    r = t.post("/api/erp/plano/sugerir", json={"data": "2026-11-21", "pedidos": ids, "veiculos": [{"veiculo_id": "v1", "motorista_id": "m1"}, {"veiculo_id": "v2"}]}).json()
    assert len(r["cargas"]) == 2
    grupos = [set(c["pedidos"]) for c in r["cargas"]]
    assert {"a1", "a2", "a3"} in grupos, "os 3 do norte juntos (v1: máx. 3 pontos)"
    c2 = r["cargas"][1]
    assert c2["veiculo_id"] == "v2" and c2["totais"]["m3"] <= 1.2 and len(c2["pedidos"]) == 2, "v2 leva 1,2 m³ = 2 colchões de 0,5"
    assert c2["pedidos"][0] == "b1", "manhã primeiro"
    assert r["sem_local"] == ["x"] and {s["id"] for s in r["sobra"]} == {"y", next(i for i in ("b1", "b2", "b3") if i not in c2["pedidos"])}
    assert next(s for s in r["sobra"] if s["id"] == "y")["motivo"] == "sem estoque reservado"
    a = r["cargas"][0]
    assert a["pedidos"][-1] == "a3", "tarde por último"
    # sem veículos: quantas cargas precisar com o limite padrão (2 pontos, raio 5 km)
    r = t.post("/api/erp/plano/sugerir", json={"pedidos": ids[:6], "limites": {"max_pontos": 2, "raio_km": 5}}).json()
    assert len(r["cargas"]) == 4 and sorted(len(c["pedidos"]) for c in r["cargas"]) == [1, 1, 2, 2], "3 no norte + 3 no sul, 2 por carga"
    assert "a1" in r["cargas"][0]["pedidos"], "a 1ª carga nasce da entrega mais cedo (pedido mais antigo no empate)"
    for c in r["cargas"]:
        assert len({x[0] for x in c["pedidos"]}) == 1, "não mistura norte e sul (raio 5 km)"


def test_rota_dois_opt():
    pts = [{"id": str(i), "geo": {"lat": 0.0, "lng": float(x)}, "janela": ""} for i, x in enumerate([3, 1, 4, 2])]
    seq = P.ordenar(pts, {"lat": 0.0, "lng": 0.0}, False)
    assert [p["geo"]["lng"] for p in seq] == [1, 2, 3, 4]


def test_confirmar_e_faturar(t):
    r = t.post("/api/erp/plano/confirmar", json={"data": "2026-11-21", "cargas": [{"veiculo_id": "v1", "motorista_id": "m1", "pedidos": ["a3", "a1", "a2"]}, {"pedidos": ["b1"]}]})
    assert r.status_code == 200, r.text
    c1, c2 = r.json()["cargas"]
    assert E.ST.dados["cargas"][c1]["pedidos"] == ["a3", "a1", "a2"], "mantém a ordem sugerida"
    assert t.post("/api/erp/plano/confirmar", json={"data": "2026-11-21", "cargas": [{"pedidos": ["a1"]}]}).status_code == 409, "tudo ou nada"
    assert t.put("/api/erp/plano/config", json={"exigir_faturamento": True, "max_pontos": 12}).json()["plano"]["max_pontos"] == 12
    assert not WR.liberada_para_app(E.ST.dados["cargas"][c2]), "sem faturar não aparece no app do motorista"
    assert t.post(f"/api/erp/cargas/{c2}/sair").status_code == 409
    f = t.post(f"/api/erp/cargas/{c2}/faturar", json={"nfs": {"b1": " 12 345 "}}).json()
    assert f["faturada"] and E.ST.dados["pedidos"]["b1"]["nf"]["numero"] == "12345"
    assert any("Faturado — NF 12345" in h["evento"] for h in E.ST.dados["pedidos"]["b1"]["historico"])
    assert WR.liberada_para_app(E.ST.dados["cargas"][c2])
    assert t.post(f"/api/erp/cargas/{c2}/sair").status_code == 200


def test_medidas_e_geo_do_endereco_atual(t):
    p = E.ST.dados["pedidos"]["a1"]
    assert P.medidas(p) == {"vol": 1, "m3": 0.5, "kg": 30.0, "sem_medida": []}
    assert P.geo_do_pedido(p)
    p["endereco"]["numero"] = "999"
    assert P.geo_do_pedido(p) is None, "mudou o endereço: localiza de novo"
    E.ST.dados["produtos"]["p1"].pop("peso")
    assert P.medidas(p)["sem_medida"] == ["peso"]


def test_campos_produto_e_veiculo(t):
    r = t.put("/api/erp/produtos/p1", json={"cubagem": "0,8", "peso": "42.5"})
    assert r.status_code == 200 and E.ST.dados["produtos"]["p1"]["peso"] == 42.5
    r = t.put("/api/erp/parceiros/v1", json={"max_m3": "9.5", "max_kg": 1500, "max_pontos": "10"})
    v = E.ST.dados["parceiros"]["v1"]
    assert r.status_code == 200 and (v["max_m3"], v["max_kg"], v["max_pontos"]) == (9.5, 1500, 10)
