"""WROUTER: app do motorista (placa), baixa automática no ERP, palavra-chave, chat, link do cliente, vizinho e km."""
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["WROUTER_GEO"] = "0"

import acesso  # noqa: E402
import banco  # noqa: E402
import erp as E  # noqa: E402
import wlogistica as W  # noqa: E402
import wrouter as R  # noqa: E402
from test_cliente_app import FakeDB  # noqa: E402

FOTO = "data:image/jpeg;base64," + "A" * 200


class Tudo(dict):
    def get(self, k, d=None):
        return True


@pytest.fixture()
def t(monkeypatch):
    fake = FakeDB()
    monkeypatch.setenv("FIRESTORE_CREDS", "teste")
    monkeypatch.setattr(banco, "db", lambda: fake)
    E.ST.pronto = True
    E.ST.config = {**E.CONFIG_PADRAO, "seq": {"pedido": 10, "carga": 0}, "wlog": {"exigir": False}}
    E.ST.dados = {k: {} for k in E.COLS}
    E.ST.dados["produtos"] = {"p1": {"nome": "Colchão Casal", "sku": "CM138", "volumes": 1}}
    E.ST.dados["parceiros"] = {"v1": {"tipo": "veiculo", "nome": "Furgão", "placa": "ABC-1D23"}, "m1": {"tipo": "motorista", "nome": "João Ferreira"},
                               "c1": {"tipo": "cliente", "nome": "Maria Souza"}, "c2": {"tipo": "cliente", "nome": "Pedro Alves"}}
    E.ST.dados["saldos"] = {"p1": {"reservado": 3}}
    base = {"status": "agendado", "tipo": "venda", "reservado": True, "historico": [], "tentativas": [], "agendamento": {"data": E.hoje()}}
    E.ST.dados["pedidos"] = {
        "ped1": {**base, "numero": 1, "cliente_id": "c1", "cliente_nome": "Maria Souza", "palavra_chave": "SOL42", "itens": [{"produto_id": "p1", "qtd": 1}],
                 "pendentes": [{"produto_id": "p1", "qtd": 1}], "endereco": {"logradouro": "Rua A", "numero": "1", "cep": "04001-000", "cidade": "São Paulo"}},
        "ped2": {**base, "numero": 2, "cliente_id": "c2", "cliente_nome": "Pedro Alves", "palavra_chave": "LUA17", "itens": [{"produto_id": "p1", "qtd": 2}],
                 "pendentes": [{"produto_id": "p1", "qtd": 2}], "endereco": {"logradouro": "Rua B", "numero": "2", "cep": "04002-000", "cidade": "São Paulo"}},
    }
    R.APP.d = None
    R.GPS.clear()
    R.SINAL.clear()
    R._falhas.clear()
    monkeypatch.setattr(acesso, "exigir_usuario", lambda request: {"login": "frota", "nome": "Bia Frota"})
    monkeypatch.setattr(acesso, "obter_esquema", lambda slug: {"acoes": {}, "campos": {}})
    monkeypatch.setattr(acesso, "permissoes", lambda u, slug, esq: {"acoes": Tudo(), "campos": {}})
    import tickets
    monkeypatch.setattr(tickets, "auto_de_baixa", lambda *a, **k: None)
    monkeypatch.setattr(tickets, "eventos_do_erp", lambda *a, **k: None)
    app = FastAPI()
    for r in (E.router, W.router, R.router):
        app.include_router(r)
    return app


def entrar(mot):
    r = mot.post("/api/wrouter/app/login", json={"placa": "abc1d23", "senha": R.SENHA_INICIAL})
    assert r.status_code == 200 and r.json()["trocar_senha"], r.text
    assert mot.get("/api/wrouter/app/cargas").status_code == 403, "sem trocar a senha não vê carga"
    assert mot.post("/api/wrouter/app/senha", json={"nova": "rota99", "repetir": "rota99"}).status_code == 200


def montar(t):
    pq = TestClient(t)
    cid = pq.post("/api/erp/cargas", json={"pedidos": ["ped1", "ped2"], "veiculo_id": "v1", "motorista_id": "m1", "data": E.hoje()}).json()["carga_id"]
    return pq, cid


def test_fluxo_do_motorista_com_baixa_automatica(t):
    pq, cid = montar(t)
    mot = TestClient(t)
    assert mot.post("/api/wrouter/app/login", json={"placa": "ZZZ9Z99", "senha": R.SENHA_INICIAL}).status_code == 401, "placa sem veículo cadastrado não entra"
    entrar(mot)
    car = mot.get("/api/wrouter/app/cargas").json()["cargas"][0]
    assert car["pedidos"] == [] and car["total"] == 2, "antes do Iniciar rota os dados das entregas não descem"
    assert pq.put("/api/wrouter/motoristas/m1", json={"palavra": True}).json()["palavra"] is True
    car = mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={}).json()
    assert len(car["pedidos"]) == 2 and car["palavra_ligada"], "Iniciar rota: as entregas aparecem"
    assert E.ST.dados["cargas"][cid]["status"] == "em_rota" and E.ST.dados["saldos"]["p1"]["transito"] == 3, "saída no ERP (reservado → trânsito)"
    assert "SOL42" not in str(car) and "LUA17" not in str(car), "a palavra nunca vai para o app"
    url = f"/api/wrouter/app/cargas/{cid}/pedido/ped1"
    assert mot.post(url, json={"desfecho": "entregue"}).json()["resultado"] == "pede_palavra"
    assert mot.post(url, json={"desfecho": "entregue", "palavra": "lua17"}).json()["resultado"] == "palavra_errada"
    assert mot.post(url, json={"desfecho": "entregue", "palavra": " sol42 ", "cid": "a1"}).json()["resultado"] == "ok"
    assert mot.post(url, json={"desfecho": "entregue", "palavra": "SOL42", "cid": "a1"}).json()["resultado"] == "ok", "reenvio sem sinal não duplica"
    assert E.ST.dados["pedidos"]["ped1"]["status"] == "entregue" and E.ST.dados["saldos"]["p1"]["entregue"] == 1, "BAIXA AUTOMÁTICA no ERP"
    u2 = f"/api/wrouter/app/cargas/{cid}/pedido/ped2"
    assert mot.post(u2, json={"desfecho": "retorno", "motivo": "Cliente ausente"}).status_code == 400, "retorno exige foto"
    assert mot.post(u2, json={"desfecho": "retorno", "motivo": "Cliente ausente", "foto": FOTO, "cid": "b1"}).json()["resultado"] == "ok"
    ped2 = E.ST.dados["pedidos"]["ped2"]
    assert ped2["status"] == "reagendar" and ped2["pendencia"] == "ausente" and E.ST.dados["saldos"]["p1"]["reservado"] == 2, "ausente volta reservado"
    assert W.retorno_resumo(E.ST.dados["cargas"][cid])["total"] == 2, "o armazém espera as 2 peças no retorno"
    assert mot.post(f"{u2}/desfazer").status_code == 200, "o motorista corrige em até 15 min"
    assert E.ST.dados["pedidos"]["ped2"]["status"] == "em_rota" and E.ST.dados["saldos"]["p1"]["transito"] == 2, "a baixa é estornada no ERP"
    assert W.retorno_resumo(E.ST.dados["cargas"][cid])["total"] == 0
    r = mot.post(u2, json={"desfecho": "parcial", "motivo": "Avaria", "foto": FOTO, "palavra": "LUA17", "linhas": [{"produto_id": "p1", "qtd": 1}], "cid": "b2"}).json()
    assert r["resultado"] == "ok" and E.ST.dados["pedidos"]["ped2"]["pendencia"] == "reposicao", "parcial = avaria no ERP (reposição)"
    assert E.ST.dados["saldos"]["p1"]["triagem"] == 1 and E.ST.dados["saldos"]["p1"]["entregue"] == 2
    assert mot.post(f"/api/wrouter/app/cargas/{cid}/chegada", json={}).status_code == 200
    av = pq.get("/api/wrouter/ao-vivo").json()
    g = av["cargas"][0]
    assert g["fase"] == "chegou" and g["cont"]["entregue"] == 1 and g["cont"]["parcial"] == 1
    assert {p["palavra"] for p in g["pedidos"]} == {"SOL42", "LUA17"}, "a frota vê a palavra"


def test_liberacao_chat_reabrir_e_vizinho(t):
    pq, cid = montar(t)
    mot = TestClient(t)
    entrar(mot)
    pq.put("/api/wrouter/motoristas/m1", json={"palavra": True})
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    url = f"/api/wrouter/app/cargas/{cid}/pedido/ped1"
    for _ in range(5):
        mot.post(url, json={"desfecho": "entregue", "palavra": "chute"})
    assert mot.post(url, json={"desfecho": "entregue", "palavra": "SOL42"}).status_code == 423, "5 erros travam"
    mot.post(f"{url}/liberacao", json={"motivo": "Cliente não tem a palavra"})
    assert pq.get("/api/wrouter/ao-vivo").json()["kpi"]["liberacoes"] == 1
    assert pq.put(f"/api/wrouter/cargas/{cid}/liberacao/ped1", json={"acao": "liberar"}).status_code == 200
    assert mot.post(url, json={"desfecho": "entregue", "cid": "x"}).json()["resultado"] == "ok", "liberado pela frota entra sem palavra"
    assert pq.post(f"/api/wrouter/cargas/{cid}/pedido/ped1/reabrir", json={"nota": "tocou errado"}).status_code == 200
    assert E.ST.dados["pedidos"]["ped1"]["status"] == "em_rota", "a frota reabriu: baixa desfeita"
    # chat
    ch = f"/api/wrouter/app/cargas/{cid}/pedido/ped2/chat"
    assert mot.post(ch, json={"texto": "oi"}).status_code == 400, "abre o chat escolhendo o motivo"
    assert mot.post(ch, json={"motivo": "Cliente ausente"}).json()["atual"]["motivo"] == "Cliente ausente"
    mot.post(ch, json={"texto": "ninguém atende"})
    p2 = next(p for p in pq.get("/api/wrouter/ao-vivo").json()["cargas"][0]["pedidos"] if p["pid"] == "ped2")
    assert p2["chat"]["aberto"] and p2["chat"]["nao_lidas"] == 1
    assert pq.post(f"/api/wrouter/cargas/{cid}/pedido/ped2/chat", json={"texto": "aguarde 10 min"}).status_code == 200
    assert mot.get(ch).json()["atual"]["msgs"][-1]["de"] == "frota"
    pq.post(f"/api/wrouter/cargas/{cid}/pedido/ped2/chat/encerrar", json={})
    assert mot.get(ch).json()["atual"] is None
    # link do cliente e vizinho
    lk = next(p for p in pq.get("/api/wrouter/ao-vivo").json()["cargas"][0]["pedidos"] if p["pid"] == "ped2")["link"]
    cli = TestClient(t)
    e = cli.get(f"/api/entrega/{lk}").json()
    assert e["nome"] == "Pedro" and e["pedidos"][0]["palavra"] == "LUA17" and e["fase"] == "rua"
    assert cli.post(f"/api/entrega/{lk}/vizinho", json={"nome": "Clara"}).status_code == 400, "vizinho exige o número"
    e = cli.post(f"/api/entrega/{lk}/vizinho", json={"nome": "Clara Mendes", "numero": "125", "tel": "11 98888-7777"}).json()
    assert e["pedidos"][0]["palavra"] == "" and e["pedidos"][0]["vizinho"]["numero"] == "125"
    app_p = next(p for p in mot.get("/api/wrouter/app/cargas").json()["cargas"][0]["pedidos"] if p["pid"] == "ped2")
    assert app_p["vizinho"] == {"numero": "125", "tel": "11988887777", "sem_palavra": False} and "Clara" not in str(app_p)
    u2 = f"/api/wrouter/app/cargas/{cid}/pedido/ped2"
    assert mot.post(u2, json={"desfecho": "entregue", "palavra": "LUA17"}).json()["resultado"] == "palavra_errada", "a palavra antiga deixa de valer"
    assert mot.post(u2, json={"desfecho": "entregue", "palavra": "clara", "cid": "v"}).json()["resultado"] == "ok", "o nome do vizinho libera"
    assert "vizinho" in E.ST.dados["pedidos"]["ped2"]["tentativas"][-1]["recebedor"]
    assert cli.post(f"/api/entrega/{lk}/vizinho", json={"numero": "1"}).status_code == 409, "depois da entrega não muda"


def test_km_e_posicao_sem_gps(t):
    pq, cid = montar(t)
    mot = TestClient(t)
    entrar(mot)
    car = E.ST.dados["cargas"][cid]
    R.rota(car)["geo"].update({"ped1": {"lat": -23.55, "lng": -46.63}, "ped2": {"lat": -23.60, "lng": -46.70}})
    lk = R.link_do_pedido(car, "ped1") or (R.garantir_links(car) and R.link_do_pedido(car, "ped1"))
    cli = TestClient(t)
    assert cli.get(f"/api/entrega/{lk}").json()["km"] is None, "antes do Iniciar rota: sem km"
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    mot.post("/api/wrouter/app/gps", json={"lat": -23.55 - 0.09, "lng": -46.63, "prec": 10})
    e = cli.get(f"/api/entrega/{lk}").json()
    assert 9.5 < e["km"] < 10.5 and e["km_cor"] == "normal" and e["mapa"] is None, "longe (fora do laranja): o cliente só vê o km, sem mapa"
    mot.post("/api/wrouter/app/gps", json={"lat": -23.55 - 0.045, "lng": -46.63, "prec": 10})
    e = cli.get(f"/api/entrega/{lk}").json()
    assert 4.5 < e["km"] < 5.5 and e["km_cor"] == "laranja", "< 7 km laranja"
    m = e["mapa"]
    assert m and m["destino"] == {"lat": -23.55, "lng": -46.63} and 4900 < m["dist_m"] < 5100 and m["motorista"]["rumo"] in (0, 360, None), "dentro do laranja: mapa com o caminhão e o endereço"
    mot.post("/api/wrouter/app/gps", json={"lat": -23.555, "lng": -46.63, "prec": 900, "fonte": "rede"})
    g = pq.get("/api/wrouter/ao-vivo").json()["cargas"][0]
    p1 = next(p for p in g["pedidos"] if p["pid"] == "ped1")
    assert p1["km_cor"] == "vermelho" and g["pos"]["fonte"] == "rede" and g["pos"]["aprox"], "< 2 km vermelho; posição pela rede"
    R.GPS.clear()
    car = E.ST.dados["cargas"][cid]
    car["rota"].pop("gps", None)
    mot.post(f"/api/wrouter/app/cargas/{cid}/pedido/ped1", json={"desfecho": "entregue", "cid": "e"})   # sem lat/lng
    assert mot.post("/api/wrouter/app/sinal", json={"gps": "negado"}).json()["ok"]
    g = pq.get("/api/wrouter/ao-vivo").json()["cargas"][0]
    assert g["pos"]["fonte"] == "estimada" and "Maria" in g["pos"]["ref"] and g["sinal"]["gps"] == "negado", "sem GPS: estimada pelo último cliente"
    e2 = cli.get(f"/api/entrega/{R.link_do_pedido(E.ST.dados['cargas'][cid], 'ped2')}").json()
    assert e2["km"] is not None and e2["km_aprox"], "o cliente continua vendo o km (aproximado)"
    import cliente_app
    r = cliente_app._rota_do_pedido("ped2")
    assert r["fase"] == "rua" and r["km"] is not None and r["link"].startswith("/entrega/"), "o app do cliente mostra o km e o link do acompanhamento"
    assert cliente_app._rota_do_pedido("ped1")["desfecho"] == "entregue"


def test_carga_so_aparece_liberada_pelo_armazem(t):
    E.ST.config["wlog"] = {"exigir": True}
    pq, cid = montar(t)
    mot = TestClient(t)
    entrar(mot)
    assert mot.get("/api/wrouter/app/cargas").json()["cargas"] == [], "sem a liberação do WLOGISTICA o motorista não vê a carga"
    E.ST.config["wlog"] = {"exigir": False}
    assert len(mot.get("/api/wrouter/app/cargas").json()["cargas"]) == 1


def test_faixas_de_km_configuraveis(t):
    pq, cid = montar(t)
    mot = TestClient(t)
    entrar(mot)
    car = E.ST.dados["cargas"][cid]
    R.rota(car)["geo"].update({"ped1": {"lat": -23.55, "lng": -46.63}, "ped2": {"lat": -23.60, "lng": -46.70}})
    R.garantir_links(car)
    lk = R.link_do_pedido(car, "ped1")
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    mot.post("/api/wrouter/app/gps", json={"lat": -23.55 - 0.045, "lng": -46.63, "prec": 10})   # ~5 km
    assert pq.put("/api/wrouter/cfg", json={"km_laranja": 1, "km_vermelho": 3}).status_code == 400, "vermelho precisa ser menor que o laranja"
    c = pq.put("/api/wrouter/cfg", json={"km_laranja": "3", "km_vermelho": 1}).json()["cfg"]
    assert (c["km_laranja"], c["km_vermelho"]) == (3.0, 1.0)
    e = TestClient(t).get(f"/api/entrega/{lk}").json()
    assert e["km_cor"] == "normal" and e["mapa"] is None and e["km_laranja"] == 3.0, "com 3 km, 5 km ainda é longe: sem mapa"
    mot.post("/api/wrouter/app/gps", json={"lat": -23.55 - 0.0072, "lng": -46.63, "prec": 10})   # ~800 m
    e = TestClient(t).get(f"/api/entrega/{lk}").json()
    assert e["km_cor"] == "vermelho" and e["mapa"] and 700 < e["mapa"]["dist_m"] < 900 and e["mapa"]["motorista"]["rumo"] == 0, "indo para o norte: triângulo aponta 0°"
    assert pq.get("/api/wrouter/ao-vivo").json()["km_laranja"] == 3.0
    pq.put("/api/wrouter/cfg", json={"mapa_cliente": False})
    assert TestClient(t).get(f"/api/entrega/{lk}").json()["mapa"] is None, "dá para desligar o mapa do cliente"


def test_cadastro_de_motoristas_e_veiculos_no_wrouter(t):
    pq = TestClient(t)
    r = pq.post("/api/wrouter/cadastros", json={"tipo": "veiculo", "placa": "kst-2e45", "nome": "Caminhão 3/4", "capacidade": "40", "max_m3": 18})
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    v = E.ST.dados["parceiros"][vid]
    assert v["placa"] == "KST2E45" and v["capacidade"] == 40 and v["max_m3"] == 18 and v["tipo"] == "veiculo"
    assert pq.post("/api/wrouter/cadastros", json={"tipo": "veiculo", "placa": "KST 2E45"}).status_code == 409, "placa repetida"
    assert pq.post("/api/wrouter/cadastros", json={"tipo": "veiculo", "placa": "AB1"}).status_code == 400, "placa obrigatória"
    assert pq.post("/api/wrouter/cadastros", json={"tipo": "cliente", "nome": "X"}).status_code == 400, "cliente fica no ERP"
    mid = pq.post("/api/wrouter/cadastros", json={"tipo": "motorista", "nome": "Rogério", "telefone": "11 9999"}).json()["id"]
    assert pq.put(f"/api/wrouter/cadastros/{mid}", json={"ativo": False, "tipo": "veiculo"}).json()["cadastro"]["tipo"] == "motorista", "não troca o tipo"
    d = pq.get("/api/wrouter/motoristas").json()
    assert any(x["id"] == vid and x["capacidade"] == 40 for x in d["veiculos"]) and any(x["id"] == mid and x["ativo"] is False for x in d["motoristas"])
    r = pq.post("/api/erp/cargas", json={"pedidos": ["ped1"], "veiculo_id": vid, "motorista_id": "m1", "data": E.hoje()})
    assert r.status_code == 200, "a montagem da carga no ERP usa o veículo cadastrado no WROUTER"
    assert "KST2E45" in R.placas_cadastradas(), "e a placa já serve de login do app"


PNG_1PX = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


def test_chat_do_cliente_so_aparece_com_pedido_em_rastreio(t, monkeypatch):
    """O cliente escreveu no app: no WROUTER só aparece se o pedido está EM RASTREIO (frota na rua, sem desfecho).
    Montando carga / na doca / já entregue → a conversa fica só no CX."""
    import cliente_app
    monkeypatch.setattr(cliente_app, "chat_com_cliente", lambda cid, tid="": {"ativo": True, "id": "x#s1", "nova": True})
    pq, cid = montar(t)
    cc = lambda pid: next(p for p in pq.get("/api/wrouter/ao-vivo").json()["cargas"][0]["pedidos"] if p["pid"] == pid)["cliente_chat"]
    assert cc("ped1") is None, "carga montada, ainda não saiu: só no CX"
    mot = TestClient(t)
    entrar(mot)
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    assert cc("ped1") == {"ativo": True, "nova": True, "chamado_wrouter": False}, "na rua: aparece no WROUTER (balão azul)"
    import tickets as TK
    rs = TK._ped_resumo(E, "ped1", E.ST.dados["pedidos"]["ped1"])["rastreio"]
    lk = next(p for p in pq.get("/api/wrouter/ao-vivo").json()["cargas"][0]["pedidos"] if p["pid"] == "ped1")["link"]
    assert lk and rs.endswith("/entrega/" + lk), "CX: RASTREIO piscando abre o MESMO link do cliente"
    assert mot.post(f"/api/wrouter/app/cargas/{cid}/pedido/ped1", json={"desfecho": "entregue", "cid": "z"}).json()["resultado"] == "ok"
    assert cc("ped1") is None, "entregue: não está mais em rastreio"
    assert TK._ped_resumo(E, "ped1", E.ST.dados["pedidos"]["ped1"])["rastreio"] == "", "entregue: sai o RASTREIO do CX"
    assert cc("ped2") is not None


def test_anexo_no_chat_com_o_motorista(t):
    pq, cid = montar(t)
    mot = TestClient(t)
    entrar(mot)
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    url = f"/api/wrouter/cargas/{cid}/pedido/ped1/chat"
    r = pq.post(url, json={"iniciar": True, "texto": "*Atenção*: veja o mapa", "anexos": [{"nome": "mapa.png", "dados": PNG_1PX}]})
    assert r.status_code == 200, r.text
    m = r.json()["atual"]["msgs"][-1]
    assert m["txt"] == "*Atenção*: veja o mapa" and m["anexos"][0]["nome"] == "mapa.png"
    aid = m["anexos"][0]["id"]
    assert pq.get(f"/api/wrouter/cargas/{cid}/pedido/ped1/anexo/{aid}").status_code == 200
    assert mot.get(f"/api/wrouter/app/cargas/{cid}/pedido/ped1/anexo/{aid}").status_code == 200, "o motorista abre"
    assert pq.get(f"/api/wrouter/cargas/{cid}/pedido/ped2/anexo/{aid}").status_code == 404, "anexo de outro pedido não abre"
    assert pq.post(url, json={"anexos": [{"nome": "x.zip", "dados": "data:application/zip;base64,AAAA"}]}).status_code == 415


def test_caixa_marca_chat_de_cliente_em_rastreio_como_frota(t):
    """CX › Caixa: chat do app de cliente com pedido em rastreio vai para a fila Frota (não para Atendimentos agora)."""
    import tickets as TK
    pq, cid = montar(t)
    cli_id = E.ST.dados["pedidos"]["ped1"]["cliente_id"]
    assert cli_id not in TK.clientes_em_rastreio()[0], "carga ainda não saiu"
    mot = TestClient(t)
    entrar(mot)
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    assert cli_id in TK.clientes_em_rastreio()[0], "na rua: em rastreio"
    for pid in ("ped1", "ped2"):
        mot.post(f"/api/wrouter/app/cargas/{cid}/pedido/{pid}", json={"desfecho": "entregue", "cid": pid, "palavra": E.ST.dados["pedidos"][pid].get("palavra_chave") or ""})
    import wrouter as WR
    if all(WR._desfecho_de(E.ST.dados["cargas"][cid], p) for p in ("ped1", "ped2")):
        assert not TK.clientes_em_rastreio()[0], "entregue: sai da Frota"


def test_corrigir_baixa_errada_no_retorno_do_cd(t, monkeypatch):
    """Motorista baixou invertido: no Retorno do WLOGISTICA a baixa é desfeita e refeita na hora (estoque, pedido, peças no CD, tickets)."""
    import tickets
    abertos, encerrados = [], []
    monkeypatch.setattr(tickets, "auto_de_baixa", lambda pid, res, *a, **k: abertos.append((pid, res)))
    monkeypatch.setattr(tickets, "encerrar_auto_de_baixa", lambda pid, ev, *a, **k: encerrados.append((pid, ev)))
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    pq, cid = montar(t)
    mot = TestClient(t)
    entrar(mot)
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    assert mot.post(f"/api/wrouter/app/cargas/{cid}/pedido/ped1", json={"desfecho": "entregue", "palavra": "SOL42", "cid": "a1"}).json()["resultado"] == "ok"
    assert mot.post(f"/api/wrouter/app/cargas/{cid}/pedido/ped2", json={"desfecho": "retorno", "motivo": "Cliente ausente", "foto": FOTO, "cid": "b1"}).json()["resultado"] == "ok"
    sal = lambda: E.ST.dados["saldos"]["p1"]
    assert sal()["entregue"] == 1 and sal()["reservado"] == 2 and E.ST.dados["cargas"][cid]["status"] == "finalizada"
    url = f"/api/wlog/cargas/{cid}/retorno/corrigir-baixa"
    assert pq.post(url, json={"pedido_id": "ped1", "resultado": "ausente"}).status_code == 400, "motivo obrigatório"

    # 1) era ENTREGUE, virou AUSENTE: a peça fica no estoque (reservada para o reenvio) e já entra como recebida no CD
    r = pq.post(url, json={"pedido_id": "ped1", "resultado": "ausente", "motivo": "cliente não estava; motorista apertou errado", "peca_no_cd": True})
    assert r.status_code == 200, r.text
    p1 = E.ST.dados["pedidos"]["ped1"]
    assert p1["status"] == "reagendar" and p1["reservado"] and sal()["entregue"] == 0 and sal()["reservado"] == 3, "volta ao estoque reservado para o reenvio"
    its = [x for x in W.wl(E.ST.dados["cargas"][cid])["retorno"]["itens"] if x["pid"] == "ped1"]
    assert its and all(x["recebido"] for x in its), "peça já recebida no CD"
    assert "entrega" not in p1, "o comprovante da entrega errada deixa de valer"
    assert ("ped1", "ausente") in abertos, "abre o ticket de ausente"
    assert E.ST.dados["cargas"][cid]["status"] == "finalizada"
    assert pq.post(url, json={"pedido_id": "ped1", "resultado": "entregue", "motivo": "x"}).status_code == 409, "já recebida no CD: corrigir o retorno é o plano B"

    # 2) era AUSENTE (esperando a peça), virou ENTREGUE: baixa no estoque e o CD deixa de esperar
    r = pq.post(url, json={"pedido_id": "ped2", "resultado": "entregue", "motivo": "cliente recebeu, motorista errou", "recebedor": "Pedro"})
    assert r.status_code == 200, r.text
    p2 = E.ST.dados["pedidos"]["ped2"]
    assert p2["status"] == "entregue" and sal()["entregue"] == 2 and sal()["reservado"] == 1, "a peça sai do estoque"
    assert not [x for x in W.wl(E.ST.dados["cargas"][cid])["retorno"]["itens"] if x["pid"] == "ped2"], "o CD não espera mais a peça"
    assert ("ped2", "ausente") in encerrados, "o ticket de ausente é encerrado"
    ev = E.ST.dados["cargas"][cid]["rota"]["pedidos"]["ped2"]
    assert ev["desfecho"] == "entregue" and ev["corrigidos"][-1]["no_cd"], "o WROUTER mostra a baixa certa e guarda a correção"
