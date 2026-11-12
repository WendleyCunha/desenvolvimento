"""Disparos no app (notificação) e vales com QR code.

    cd hub && python -m pytest tests/test_promocoes.py -q
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acesso  # noqa: E402
import promocoes as P  # noqa: E402
import tickets as T  # noqa: E402
from test_cliente_app import entrar, t  # noqa: E402,F401  (fixture)

SUB = {"endpoint": "https://push.exemplo/abc", "keys": {"p256dh": "BPchave", "auth": "segredo"}}


@pytest.fixture()
def p(t, monkeypatch):  # noqa: F811
    P._insc, P._idx, P._vapid = None, None, None
    P._cart.clear()
    P._dest.clear()
    t.app.include_router(P.router)
    enviados = []
    monkeypatch.setattr(P, "enviar_push", lambda sub, dados: enviados.append((sub["endpoint"], dados)) or "ok")
    monkeypatch.setattr(P, "_disparar_em_fundo", P._executar)   # no teste, roda na hora
    t.enviados = enviados
    return t


def inscrever(p, cpf=None, **prefs):
    assert (entrar(p, **({"cpf": cpf, "email": "bia@exemplo.com"} if cpf else {}))).status_code == 200
    r = p.post("/api/cliente/push", json={"inscricao": SUB if not cpf else {**SUB, "endpoint": "https://push.exemplo/bia"}, **prefs})
    assert r.status_code == 200, r.text
    return p.get("/api/cliente/eu").json()["codigo"]


def test_chave_vapid_gerada_e_guardada(p):
    k1 = p.get("/api/cliente/push/chave").json()["publica"]
    P._vapid = None
    assert p.get("/api/cliente/push/chave").json()["publica"] == k1 and len(k1) > 80


def test_cupom_por_cliente_e_validacao_unica(p):
    from test_cliente_app import CPF_BIA
    ana = inscrever(p)
    bia = inscrever(p, cpf=CPF_BIA, promocoes=False)   # Bia desligou promoções
    r = p.post("/api/promo/disparos", json={"tipo": "cupom", "titulo": "Black Friday", "texto": "30% em toda a loja", "percentual": 30,
                                            "validade": "2099-12-31", "publico": {"modo": "todos"}})
    assert r.status_code == 200, r.text
    d = r.json()["disparo"]
    assert d["status"] == "enviado" and d["enviados"] == 1 and d["total"] == 1
    assert [e for e, _ in p.enviados] == ["https://push.exemplo/abc"]   # só a Ana (Bia desligou)
    entrar(p)
    vales = p.get("/api/cliente/vantagens").json()["vales"]
    assert len(vales) == 1 and vales[0]["percentual"] == 30 and vales[0]["status"] == "valido" and vales[0]["qr"].endswith("/v/" + vales[0]["codigo"])
    cod = vales[0]["codigo"]
    assert p.get("/api/promo/vale/" + cod.replace("-", "").lower()).json()["status"] == "valido"   # digitado sem hífen, minúsculo
    assert p.post(f"/api/promo/vale/{cod}/usar", json={"local": "Loja Tatuapé"}).status_code == 200
    r2 = p.post(f"/api/promo/vale/{cod}/usar", json={"local": "Site"})
    assert r2.status_code == 409 and "JÁ FOI USADO" in r2.json()["detail"]
    assert p.get("/api/cliente/vantagens").json()["vales"][0]["status"] == "usado"
    assert p.get("/api/promo/disparos").json()["disparos"][0]["usados"] == 1
    assert bia and ana != bia


def test_acima_do_limite_precisa_de_outro_gestor(p, monkeypatch):
    inscrever(p)
    d = p.post("/api/promo/disparos", json={"tipo": "cupom", "titulo": "Presente", "texto": "100% off", "percentual": 100,
                                            "validade": "2099-12-31"}).json()["disparo"]
    assert d["status"] == "aguardando_aprovacao" and not p.enviados
    assert p.post(f"/api/promo/disparos/{d['id']}/aprovar").status_code == 403    # quem criou não aprova
    T.BASE.cfg_cache["usuarios"]["gestor2"] = {"nome": "Gil Gestor", "depto": "CX"}
    monkeypatch.setattr(acesso, "exigir_usuario", lambda request: {"login": "gestor2", "nome": "Gil Gestor"})
    assert p.post(f"/api/promo/disparos/{d['id']}/aprovar").status_code == 200
    assert P._disparo(d["id"])["status"] == "enviado" and len(p.enviados) == 1


def test_so_gestor_dispara_e_publico_selecionado(p, monkeypatch):
    ana = inscrever(p)
    conta = p.post("/api/promo/publico", json={"tipo": "promocao", "publico": {"modo": "codigos", "codigos": [ana, "ZZZ999"]}}).json()
    assert (conta["escolhidos"], conta["com_app"], conta["aceitam"], conta["sem_app"]) == (2, 1, 1, 1)
    T.BASE.cfg_cache["tickets_hub"] = {"perfis": {"atendente": "atendente"}}
    monkeypatch.setattr(acesso, "permissoes", lambda u, slug, esq: {"acoes": {"acessar": True, "atender": True}, "campos": {}})
    assert p.post("/api/promo/disparos", json={"tipo": "aviso", "titulo": "x", "texto": "y"}).status_code == 403


def test_vale_vencido_nao_valida(p):
    inscrever(p)
    p.post("/api/promo/disparos", json={"tipo": "brinde", "titulo": "Travesseiro", "texto": "Retire na loja", "beneficio": "1 travesseiro",
                                        "validade": "2099-01-01"})
    v = p.get("/api/cliente/vantagens").json()["vales"][0]
    P._ler_vale(v["codigo"])  # existe
    vale = P.db().collection(P.COL_VALE).document(v["codigo"]).get().to_dict()
    P.db().collection(P.COL_VALE).document(v["codigo"]).set({**vale, "validade": "2020-01-01"})
    r = p.post(f"/api/promo/vale/{v['codigo']}/usar", json={})
    assert r.status_code == 409 and "vencido" in r.json()["detail"]
    time.sleep(0)


def test_aceita_corpo_enviado_como_texto(p):
    """O app chegou a mandar o JSON já convertido em texto (erro 'str'); o servidor tem de aceitar."""
    import json
    entrar(p)
    r = p.post("/api/cliente/push", content=json.dumps(json.dumps({"inscricao": SUB, "avisos": True, "promocoes": True})),
               headers={"Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    r = p.post("/api/cliente/push/preferencias", content=json.dumps(json.dumps({"promocoes": False})), headers={"Content-Type": "application/json"})
    assert r.status_code == 200 and r.json()["promocoes"] is False


def test_recebimentos_cliente_a_cliente_e_avisos_sempre_ativos(p):
    from test_cliente_app import CPF_BIA
    ana = inscrever(p, avisos=False)                      # o app não deixa desligar avisos do pedido
    assert P.inscricoes()[ana]["avisos"] is True
    entrar(p)
    assert p.post("/api/cliente/push/preferencias", json={"avisos": False}).json()["avisos"] is True
    inscrever(p, cpf=CPF_BIA)
    d = p.post("/api/promo/disparos", json={"tipo": "cupom", "titulo": "10%", "texto": "x", "percentual": 10, "validade": "2099-12-31"}).json()["disparo"]
    entrar(p)
    p.post("/api/cliente/push/aberto", json={"disparo": d["id"]})
    vale = p.get("/api/cliente/vantagens").json()["vales"][0]["codigo"]
    p.post(f"/api/promo/vale/{vale}/usar", json={"local": "Loja Centro"})
    r = p.get("/api/promo/recebimentos?dias=30").json()
    assert r["total"] == 2 and r["clientes"] == 2 and r["por_situacao"]["usou"] == 1 and r["por_situacao"]["entregue"] == 1
    usou = next(x for x in r["linhas"] if x["situacao"] == "usou")
    assert usou["cliente"] == ana and usou["usado_local"] == "Loja Centro" and usou["aberto_em"] and usou["vale"] == vale
    assert p.get("/api/promo/recebimentos?situacao=nao_abriu").json()["total"] == 1
    assert p.get("/api/promo/recebimentos?q=bia").json()["total"] == 1
    assert len(p.get("/api/promo/disparos?dias=1").json()["disparos"]) == 1
