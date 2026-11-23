"""Lembrete do relatório: passe por aparelho, 1 rodada por dia, só para quem ainda não enviou."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_empresas as T  # noqa: E402
from test_empresas import entrar, hub  # noqa: E402,F401  (fixture)

SUB = {"endpoint": "https://push.exemplo.test/abc", "keys": {"p256dh": "x", "auth": "y"}}


def _prep(secretaria):
    import relatorios_publico
    relatorios_publico._envios.clear()
    for n in ("Carla Souza Lima", "Joao Souza Lima", "Bruno Exemplo"):
        T.DB[(secretaria.COL_MEMBROS, n)] = {"nome_oficial": n, "categoria": "PUBLICADOR"}
    secretaria.BASE.membros = None
    secretaria.BASE.cfg = {**secretaria.CONFIG_PADRAO}


def test_inscrever_e_disparar(hub, monkeypatch):
    import promocoes
    import relatorios_lembretes as L
    import secretaria
    import secretaria_regras as R
    c = hub()
    _prep(secretaria)
    monkeypatch.setattr(promocoes, "vapid", lambda: {"publica": "PUB", "privada_pem": ""})
    enviados = []
    monkeypatch.setattr(promocoes, "enviar_push", lambda sub, d: enviados.append(d) or "ok")
    assert c.get("/api/relatorios-publico/lembretes/chave").json() == {"ligado": True, "publica": "PUB"}
    # sem passe ninguém se inscreve
    r = c.post("/api/relatorios-publico/lembretes/inscrever", json={"aparelho": "a" * 20, "sub": SUB, "passes": ["falso.x"]})
    assert r.status_code == 422
    # a mãe envia por ela e pelo filho: o aparelho guarda os dois passes
    p1 = c.post("/api/relatorios-publico/enviar", json={"nome": "Carla Souza Lima", "participou": True}).json()["lembrete"]["passe"]
    p2 = c.post("/api/relatorios-publico/enviar", json={"nome": "Joao Souza Lima", "participou": True}).json()["lembrete"]["passe"]
    r = c.post("/api/relatorios-publico/lembretes/inscrever", json={"aparelho": "a" * 20, "sub": SUB, "passes": [p1, p2]})
    assert r.json()["pessoas"] == 2
    # dois meses à frente (o envio de hoje conta para o mês atual): dia 3, 10h. A Carla já enviou o relatório do mês devido; o João não.
    hj = datetime.now(R.FUSO)
    ano, mes = (hj.year + (hj.month + 1) // 12, (hj.month + 1) % 12 + 1)
    agora = datetime(ano, mes, 3, 10, tzinfo=R.FUSO)
    ch = R.chave_por_data(agora)
    T.DB[(secretaria.COL_REL, "novo")] = {"nome": "Carla Souza Lima", "membro_id": "Carla Souza Lima", "mes_chave": ch,
                                         "mes_referencia": R.rotulo_banco(ch), "participou_ministerio": True}
    secretaria.BASE.atualizar(forcar=True)
    out = L.disparar_empresa(agora)
    assert out["enviados"] == 1 and "Joao" in enviados[0]["texto"] and "pendente" in enviados[0]["titulo"]
    # cada lembrete vira uma linha por pessoa: enviado → chegou → abriu (o aparelho avisa pelo recibo)
    eid = enviados[0]["id"]
    assert T.DB[(L.COL_ENV, eid)]["status"] == "enviado" and T.DB[(L.COL_ENV, eid)]["membro"] == "Joao Souza Lima"
    assert c.post("/api/relatorios-publico/lembretes/recibo", json={"id": eid, "ev": "chegou"}).json()["ok"] is True
    assert c.post("/api/relatorios-publico/lembretes/recibo", json={"id": "f" * 24, "ev": "chegou"}).json()["ok"] is False
    assert c.post("/api/relatorios-publico/lembretes/recibo", json={"id": "x", "ev": "abriu"}).json()["ok"] is False
    entrar(c, "chefe", "senha-forte")
    r = c.get("/api/secretaria/lembretes").json()
    assert r["aparelhos"] == 1 and r["por_membro"]["Joao Souza Lima"]["ultimo"]["situacao"] == "chegou"
    assert r["por_membro"]["Carla Souza Lima"]["aparelhos"] == 1 and r["por_membro"]["Carla Souza Lima"]["ultimo"] is None
    assert [e["nome"] for e in r["ultima_rodada"]["envios"]] == ["Joao Souza Lima"]
    c.post("/api/relatorios-publico/lembretes/recibo", json={"id": eid, "ev": "abriu"})
    m = c.get("/api/secretaria/lembretes/membros").json()["por_membro"]
    assert m["Joao Souza Lima"]["ultimo"]["situacao"] == "abriu"
    assert L.disparar_empresa(agora)["motivo"] == "já enviado hoje"          # chamar de novo não manda de novo
    assert L.disparar_empresa(datetime(2026, 12, 4, 8, tzinfo=R.FUSO))["motivo"] == "fora do horário"   # antes das 9h
    assert L.disparar_empresa(datetime(2026, 12, 25, 10, tzinfo=R.FUSO))["motivo"] == "fora do horário"  # depois do corte
    secretaria.BASE.cfg["lembretes_ligado"] = False
    assert L.disparar_empresa(datetime(2026, 12, 5, 10, tzinfo=R.FUSO))["motivo"] == "desligado"
    assert c.post("/api/lembretes-relatorio/disparar").json()["ok"] is True


def test_aparelho_que_saiu_e_apagado(hub, monkeypatch):
    import promocoes
    import relatorios_lembretes as L
    import secretaria
    import secretaria_regras as R
    c = hub()
    _prep(secretaria)
    monkeypatch.setattr(promocoes, "vapid", lambda: {"publica": "PUB", "privada_pem": ""})
    monkeypatch.setattr(promocoes, "enviar_push", lambda sub, d: "expirou")
    p = c.post("/api/relatorios-publico/enviar", json={"nome": "Bruno Exemplo", "participou": True}).json()["lembrete"]["passe"]
    c.post("/api/relatorios-publico/lembretes/inscrever", json={"aparelho": "b" * 20, "sub": SUB, "passes": [p]})
    assert (L.COL, "b" * 20) in T.DB
    L.disparar_empresa(datetime(2027, 1, 2, 12, tzinfo=R.FUSO))
    assert (L.COL, "b" * 20) not in T.DB

