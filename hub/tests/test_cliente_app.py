"""App do cliente (/cliente/) — fluxo completo sem Firestore de verdade.

    cd hub && python -m pytest tests/test_cliente_app.py -q
"""
import re
import sys
import time
from urllib.parse import quote
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acesso  # noqa: E402
import banco  # noqa: E402
import cliente_app as C  # noqa: E402
import erp as E  # noqa: E402
import tickets as T  # noqa: E402


# ── Firestore de mentira (só o que tickets/erp usam no caminho de escrita) ──
class Snap:
    def __init__(self, d):
        self._d = d

    @property
    def exists(self):
        return self._d is not None

    def to_dict(self):
        return None if self._d is None else dict(self._d)


class Ref:
    def __init__(self, db, col, i):
        self.db, self.col, self.id = db, col, i

    def get(self, timeout=None):
        return Snap(self.db.dados.get(self.col, {}).get(self.id))

    def set(self, d, timeout=None):
        self.db.dados.setdefault(self.col, {})[self.id] = d


class Col:
    def __init__(self, db, nome):
        self.db, self.nome = db, nome

    def document(self, i):
        return Ref(self.db, self.nome, i)


class Lote:
    def __init__(self):
        self.ops = []

    def set(self, ref, d):
        self.ops.append((ref, d))

    def delete(self, ref):
        self.ops.append((ref, None))

    def commit(self, timeout=None):
        for ref, d in self.ops:
            if d is None:
                ref.db.dados.get(ref.col, {}).pop(ref.id, None)
            else:
                ref.set(d)


class FakeDB:
    def __init__(self):
        self.dados = {}

    def collection(self, nome):
        return Col(self, nome)

    def batch(self):
        return Lote()


CPF_ANA, CPF_BIA = "529.982.247-25", "111.444.777-35"
PARCEIROS = {
    "c_ana": {"tipo": "cliente", "nome": "ana souza", "doc": CPF_ANA, "email": "Ana@Exemplo.com", "telefone": "11 90000-0001", "codigo": "", "ativo": True},
    "c_bia": {"tipo": "cliente", "nome": "Bia Lima", "doc": CPF_BIA, "email": "bia@exemplo.com", "codigo": "BIA234", "ativo": True},
    "f_1": {"tipo": "fornecedor", "nome": "Fábrica", "doc": CPF_ANA, "email": "ana@exemplo.com"},
}


@pytest.fixture()
def t(monkeypatch):
    fake = FakeDB()
    monkeypatch.setenv("FIRESTORE_CREDS", "teste")
    monkeypatch.delenv("FIRESTORE_CREDS_TICKETS", raising=False)
    monkeypatch.setattr(banco, "db", lambda: fake)
    # ERP em memória
    E.ST.pronto = True
    E.ST.config = {**E.CONFIG_PADRAO}
    E.ST.dados = {k: {} for k in E.COLS}
    E.ST.dados["parceiros"] = {k: dict(v) for k, v in PARCEIROS.items()}
    E.ST.dados["produtos"] = {"p1": {"nome": "Colchão Casal Molas"}}
    E.ST.dados["pedidos"] = {
        "ped1": {"cliente_id": "c_ana", "numero": 101, "status": "agendado", "tipo": "venda", "agendamento": {"data": "2026-11-14", "janela": "Manhã"},
                 "itens": [{"produto_id": "p1", "qtd": 1, "preco": 1999}], "valor_total": 1999, "criado_em": "2026-11-01T10:00:00",
                 "historico": [{"em": "x", "por": "joao.vendas", "evento": "Pedido criado"}], "obs": "cliente chato", "tentativas": [],
                 "palavra_chave": "SOL42"},
        "ped9": {"cliente_id": "c_ana", "numero": 99, "status": "cancelado", "itens": [], "criado_em": "2026-10-01T10:00:00", "palavra_chave": "LUA10"},
        "ped2": {"cliente_id": "c_ana", "numero": 102, "status": "rascunho", "itens": [], "criado_em": "2026-11-05T10:00:00"},
        "ped3": {"cliente_id": "c_bia", "numero": 103, "status": "confirmado", "itens": [], "criado_em": "2026-11-05T10:00:00"},
    }
    # Tickets em memória (sem leitura do banco: marca como recém-atualizado)
    T.BASE.cont = {}
    T.BASE.t_completa = T.BASE.t_inc = time.time() + 3600
    T.BASE.cfg_cache = {"motivos_central": {"ticket": T.MOTIVOS_PADRAO}, "departamentos": {"lista": T.DEPARTAMENTOS_PADRAO},
                        "tickets_hub": {}, "usuarios": {"atendente": {"nome": "Carla Atendente", "depto": "CX"}}}
    T.BASE.t_cfg = time.time() + 3600
    C._falhas.clear()
    C._envios.clear()
    T.PRESENCA.clear()
    T._ULT_RECEBEU.clear()
    import cliente_acesso
    cliente_acesso._cache.clear()
    # login do hub (atendente) para o lado da central
    monkeypatch.setattr(acesso, "exigir_usuario", lambda request: {"login": "atendente", "nome": "Carla Atendente"})
    monkeypatch.setattr(acesso, "obter_esquema", lambda slug: {"acoes": {}, "campos": {}})
    tudo = {k: True for k in ("acessar", "atender", "abrir", "encerrar", "transferir", "setor", "equipe", "gestao", "configurar", "palavra_chave")}
    monkeypatch.setattr(acesso, "permissoes", lambda u, slug, esq: {"acoes": tudo, "campos": {}})
    app = FastAPI()
    app.include_router(C.router)
    app.include_router(T.router)
    return TestClient(app)


def entrar(t, cpf=CPF_ANA, email="ana@exemplo.com", palavra=""):
    return t.post("/api/cliente/entrar", json={"cpf": cpf, "email": email, "palavra": palavra})


def central(t, sid):
    """Resumo do ticket na central (pelo id curto que o app conhece)."""
    return next(x for x in t.get("/api/tickets/estado").json()["tickets"] if x["id"].endswith("#" + sid))


def url_tk(tid):
    return "/api/tickets/ticket/" + quote(tid, safe="")


def test_login_confere_cpf_e_email_e_gera_codigo(t):
    assert t.get("/api/cliente/eu").status_code == 401
    assert entrar(t, email="outra@exemplo.com").status_code == 401
    assert entrar(t, cpf="123.456.789-00").status_code == 422          # dígito verificador errado
    r = entrar(t, email="  ANA@exemplo.com ")                          # e-mail sem diferença de maiúsculas/espaços
    assert r.status_code == 200 and r.json()["nome"] == "Ana"
    cod = E.ST.dados["parceiros"]["c_ana"]["codigo"]
    assert len(cod) == 6 and t.get("/api/cliente/eu").json()["codigo"] == cod


def test_palavra_chave_quando_exigida(t):
    T.BASE.cfg_cache["tickets_hub"] = {"app_cliente": {"exigir_palavra": True}}
    assert t.get("/api/cliente/info").json()["exigir_palavra"] is True
    assert entrar(t).status_code == 422                                # sem a palavra
    assert entrar(t, palavra="SOL43").status_code == 401               # errada
    assert entrar(t, palavra="LUA10").status_code == 401               # de pedido cancelado não vale
    assert entrar(t, palavra=" sol-42 ").status_code == 200            # maiúscula/espaço/hífen não importam


def test_palavra_nasce_com_o_pedido_e_o_erp_nao_mostra(t):
    tx = E.Tx({"login": "vendedor"})
    E.ST.dados["produtos"]["p1"].update(ativo=True, preco=100)
    ped = E._novo_pedido(tx, {"login": "vendedor"}, {"acoes": {}, "campos": {}}, {"cliente_id": "c_bia", "itens": [{"produto_id": "p1", "qtd": 1}]})
    assert re.match(r"^[A-Z]+\d{2}$", ped["palavra_chave"])
    assert "palavra_chave" not in E._filtrar({"acoes": {}, "campos": {}}, "pedidos", dict(ped))


def test_central_consulta_e_gera_palavras(t):
    r = t.get("/api/tickets/app/palavras?q=ana").json()
    peds = {p["numero"]: p["palavra_chave"] for p in r["clientes"][0]["pedidos"]}
    assert peds[101] == "SOL42" and 102 not in peds                     # rascunho fora
    E.ST.dados["pedidos"]["ped3"].pop("palavra_chave", None)
    assert t.post("/api/tickets/app/palavras/gerar").json()["feitos"] == 1   # só o 103 (ativo e sem palavra)
    assert E.ST.dados["pedidos"]["ped3"]["palavra_chave"]
    nova = t.post("/api/tickets/app/palavra/ped1/nova").json()["palavra_chave"]
    assert nova != "SOL42" and E.ST.dados["pedidos"]["ped1"]["palavra_chave"] == nova


def test_pedidos_so_os_meus_sem_rascunho_e_sem_dado_interno(t):
    entrar(t)
    ps = t.get("/api/cliente/eu").json()["pedidos"]
    assert [p["numero"] for p in ps] == [101, 99]                       # 102 é rascunho, 103 é da Bia
    p = ps[0]
    assert p["rotulo"] == "Entrega agendada" and p["entrega"] == {"data": "2026-11-14", "janela": "Manhã"}
    assert "historico" not in p and "obs" not in p and "joao" not in str(p)
    assert p["palavra_chave"] == "SOL42" and ps[1]["palavra_chave"] == ""   # o cliente vê a do pedido dele; cancelado não mostra


def test_freio_de_tentativas(t):
    for _ in range(C.LIMITE_DOC):
        assert entrar(t, email="errado@x.com").status_code == 401
    assert entrar(t).status_code == 429


def test_atendimento_e_um_chat_so(t):
    entrar(t)
    a = t.post("/api/cliente/chat", json={"opcao": "entrega", "texto": "Posso mudar para a tarde?"}).json()
    b = t.post("/api/cliente/chat", json={"opcao": "outro", "texto": "E outra dúvida…"}).json()   # outro assunto, mesmo chat
    assert a["existente"] is False and b["existente"] is True and a["id"] == b["id"]
    eu = t.get("/api/cliente/eu").json()
    assert eu["chat"]["id"] == a["id"] and len(eu["chamados"]) == 1
    assert [m["texto"] for m in eu["chat"]["mensagens"]] == ["Posso mudar para a tarde?", "E outra dúvida…"]
    tk = central(t, a["id"])
    assert tk["origem"] == "app" and tk["app_tipo"] == "chat" and tk["app_pendente"] and tk["sem_dono"]
    assert tk["motivo_pai"] == "Logística" and tk["departamento"] == "Logística"


def test_chat_ida_e_volta_e_so_o_atendente_encerra(t):
    entrar(t)
    sid = t.post("/api/cliente/chat", json={"opcao": "troca", "texto": "Veio rasgado"}).json()["id"]
    tid = central(t, sid)["id"]
    t.post(url_tk(tid) + "/alterar", json={"atribuir": "atendente"})
    t.post(url_tk(tid) + "/comentar", json={"texto": "cliente VIP, cuidado", "tipo": "nota"})
    t.post(url_tk(tid) + "/comentar", json={"texto": "Já abrimos a troca!", "tipo": "resposta", "status": "aguardando"})
    tk = central(t, sid)
    assert tk["app_pendente"] is False and tk["status"] == "aguardando"
    chat = t.get("/api/cliente/eu").json()["chat"]
    assert [(m["de"], m["texto"]) for m in chat["mensagens"]] == [("cliente", "Veio rasgado"), ("central", "Já abrimos a troca!")]
    assert chat["mensagens"][1]["autor"] == "Carla" and chat["rotulo"] == "Aguardando sua resposta"
    assert t.post(f"/api/cliente/chamado/{sid}/mensagem", json={"texto": "Obrigada!"}).status_code == 200
    tk = central(t, sid)
    assert tk["status"] == "em_andamento" and tk["app_pendente"] and tk["nao_visto"]
    # o cliente não tem como encerrar; o atendente conclui → o chat sai do Atendimento e não aceita mais mensagem
    t.post(url_tk(tid) + "/alterar", json={"status": "resolvido"})
    eu = t.get("/api/cliente/eu").json()
    assert eu["chat"] is None and eu["chamados"][0]["pode_escrever"] is False
    assert t.post(f"/api/cliente/chamado/{sid}/mensagem", json={"texto": "e aí?"}).status_code == 409
    novo = t.post("/api/cliente/chat", json={"opcao": "outro", "texto": "Outra coisa"}).json()
    assert novo["existente"] is False and novo["id"] != sid             # agora sim, um chat novo


def test_chamado_pelo_cliente_com_motivo_e_submotivo(t):
    entrar(t)
    eu = t.get("/api/cliente/eu").json()
    assert "Cancelamento" in eu["motivos"]["Pedido"] and eu["chamado"] is None
    assert t.post("/api/cliente/chamados", json={"motivo_pai": "Pedido", "motivo_filho": "Inexistente", "texto": "x"}).status_code == 422
    r = t.post("/api/cliente/chamados", json={"motivo_pai": "Pedido", "motivo_filho": "Cancelamento", "pedido_id": "ped1", "texto": "Quero cancelar"}).json()
    cod = E.ST.dados["parceiros"]["c_ana"]["codigo"]
    assert r["agrupado"] is False and r["chamado"] == cod
    tk = central(t, r["id"])
    assert tk["app_tipo"] == "chamado" and tk["motivo_filho"] == "Cancelamento" and tk["erp_pedido_numero"] == 101 and tk["sla"]["limite"]
    dup = t.post("/api/cliente/chamados", json={"motivo_pai": "Pedido", "motivo_filho": "Arrependimento", "pedido_id": "ped1", "texto": "outro"})
    assert dup.status_code == 409 and cod in dup.json()["detail"]          # mesmo motivo + mesmo pedido
    r2 = t.post("/api/cliente/chamados", json={"motivo_pai": "Pedido", "motivo_filho": "Arrependimento", "texto": "sem pedido"}).json()
    assert r2["agrupado"] is True and r2["chamado"] == cod and r2["solicitacoes"] == 2   # outro pedido (nenhum) → agrupa
    assert t.post("/api/cliente/chamados", json={"motivo_pai": "Compras", "motivo_filho": "Falta de Peças", "pedido_id": "ped3", "texto": "x"}).status_code == 404
    ch = t.get("/api/cliente/eu").json()["chamado"]
    assert ch["numero"] == cod and len(ch["solicitacoes"]) == 2 and {s["cor"] for s in ch["solicitacoes"]} == {0, 1}
    assert [s["atualizacoes"][0]["texto"] for s in ch["solicitacoes"]] == ["Quero cancelar", "sem pedido"]   # o que o cliente pediu


def test_em_atendimento_nao_abre_chamado(t):
    entrar(t)
    t.post("/api/cliente/chat", json={"opcao": "outro", "texto": "Oi"})
    r = t.post("/api/cliente/chamados", json={"motivo_pai": "Cliente", "motivo_filho": "Reenvio", "texto": "x"})
    assert r.status_code == 409 and "atendente abre a solicitação" in r.json()["detail"]


def test_mensagem_no_chamado_vai_para_a_solicitacao_respondida(t):
    entrar(t)
    a = t.post("/api/cliente/chamados", json={"motivo_pai": "Pedido", "motivo_filho": "Cancelamento", "pedido_id": "ped1", "texto": "A"}).json()["id"]
    b = t.post("/api/cliente/chamados", json={"motivo_pai": "Cliente", "motivo_filho": "Reenvio", "texto": "B"}).json()["id"]
    tb = central(t, b)["id"]
    t.post(url_tk(tb) + "/comentar", json={"texto": "Sobre o reenvio: já saiu.", "tipo": "resposta"})
    assert t.post("/api/cliente/chamado/mensagem", json={"texto": "Obrigada!"}).json()["sol"] == b
    assert central(t, b)["app_pendente"] and not central(t, a)["status"] == "finalizado"


def test_central_ve_o_cliente_inteiro_com_um_dono(t):
    entrar(t)
    a = t.post("/api/cliente/chamados", json={"motivo_pai": "Pedido", "motivo_filho": "Cancelamento", "pedido_id": "ped1", "texto": "A"}).json()["id"]
    cid = central(t, a)["cid"]
    assert t.post(f"/api/tickets/cliente/{quote(cid, safe='')}/dono", json={"atribuir": "atendente"}).json()["feitas"] == 1
    b = t.post("/api/cliente/chamados", json={"motivo_pai": "Cliente", "motivo_filho": "Reenvio", "texto": "B"}).json()["id"]
    assert central(t, b)["atribuido_para"] == "atendente"                # a nova já nasce com o dono do cliente
    det = t.get(f"/api/tickets/cliente/{quote(cid, safe='')}").json()
    assert det["dono"] == ["atendente"] and [s["cor"] for s in det["solicitacoes"]] == [0, 1] and det["erp"]["pedidos"]
    # pela central: abrir de novo no mesmo código agrupa; mesmo motivo+pedido trava
    base = {"cliente_codigo": det["cliente"]["codigo"], "cliente_nome": "ana souza", "assunto": "x", "descricao": "y"}
    r = t.post("/api/tickets/tickets", json={**base, "motivo_pai": "Logística", "departamento": "Logística"}).json()
    assert r["agrupado"] is True and r["chamado"] == det["cliente"]["codigo"]
    assert t.post("/api/tickets/tickets", json={**base, "motivo_pai": "Pedido", "erp_pedido_id": "ped1"}).status_code == 409


def test_concluir_chat_anexando_ou_virando_solicitacao(t):
    entrar(t)
    c1 = t.post("/api/cliente/chat", json={"opcao": "outro", "texto": "Dúvida rápida"}).json()["id"]
    assert t.post(url_tk(central(t, c1)["id"]) + "/concluir-chat", json={"modo": "anexar"}).status_code == 200
    eu = t.get("/api/cliente/eu").json()
    assert eu["chat"] is None and eu["chamado"] is None                 # anexado: fica no histórico da conversa, não vira solicitação
    c2 = t.post("/api/cliente/chat", json={"opcao": "troca", "texto": "Veio rasgado"}).json()["id"]
    tid = central(t, c2)["id"]
    assert t.post(url_tk(tid) + "/concluir-chat", json={"modo": "solicitacao", "motivo_pai": "Pedido", "motivo_filho": "Troca Adaptação", "pedido_id": "ped1"}).status_code == 200
    tk = central(t, c2)
    assert tk["chat"] is False and tk["app_tipo"] == "chamado" and tk["motivo_filho"] == "Troca Adaptação" and tk["status"] in ("aberto", "em_andamento")
    eu = t.get("/api/cliente/eu").json()
    sol = eu["chamado"]["solicitacoes"]
    assert eu["chat"] is None and [s["assunto"] for s in sol] == ["Troca Adaptação · pedido #101"]
    assert sol[0]["atualizacoes"] == []                                  # a conversa do chat NÃO aparece em Chamados
    assert t.post(url_tk(tid) + "/concluir-chat", json={"modo": "anexar"}).status_code == 409     # já não é chat


def test_reenvio_da_fila_offline_nao_duplica(t):
    entrar(t)
    corpo = {"opcao": "outro", "texto": "escrito no metrô", "req": "abc123", "escrito_em": "2026-11-10 08:15:00"}
    a = t.post("/api/cliente/chat", json=corpo).json()
    b = t.post("/api/cliente/chat", json=corpo).json()
    assert b.get("repetido") and a["id"] == b["id"]
    m = {"texto": "segunda", "req": "def456", "escrito_em": "2026-11-10 08:16:00"}
    t.post(f"/api/cliente/chamado/{a['id']}/mensagem", json=m)
    assert t.post(f"/api/cliente/chamado/{a['id']}/mensagem", json=m).json().get("repetido")
    det = t.get(url_tk(central(t, a["id"])["id"])).json()["ticket"]
    assert len(det["comentarios"]) == 1 and det["comentarios"][0]["escrito_em"] == "2026-11-10 08:16:00"
    assert "escrito sem internet" in det["descricao"]


def test_um_cliente_nao_ve_o_do_outro(t):
    entrar(t)
    sid = t.post("/api/cliente/chat", json={"opcao": "outro", "texto": "Dúvida da Ana"}).json()["id"]
    t.post("/api/cliente/sair")
    t.cookies.clear()
    assert entrar(t, CPF_BIA, "bia@exemplo.com").status_code == 200
    eu = t.get("/api/cliente/eu").json()
    assert eu["chamados"] == [] and eu["chat"] is None
    assert t.get(f"/api/cliente/chamado/{sid}").status_code == 404
    assert t.post(f"/api/cliente/chamado/{sid}/mensagem", json={"texto": "oi"}).status_code == 404


def test_chamado_aberto_pela_central_aparece_sem_o_interno(t):
    entrar(t)
    cod = E.ST.dados["parceiros"]["c_ana"]["codigo"]
    tid = T.criar_solicitacao({"assunto": "Retorno sobre avaria", "descricao": "texto interno da abertura", "cliente_codigo": cod,
                               "cliente_nome": "ana souza", "origem": "hub"}, {"usuario": "atendente", "nome": "Carla"})
    ch = t.get(f"/api/cliente/chamado/{tid.split('#')[-1]}").json()
    assert ch["assunto"] == "Retorno sobre avaria" and ch["mensagens"] == [] and ch["tipo"] == "central"


def test_sessao_cai_se_o_email_mudar_no_erp(t):
    entrar(t)
    assert t.get("/api/cliente/eu").status_code == 200
    E.ST.dados["parceiros"]["c_ana"]["email"] = "novo@exemplo.com"
    assert t.get("/api/cliente/eu").status_code == 401


def test_token_do_cliente_nao_vale_no_hub_e_vice_versa(t):
    assert acesso.ler_token(C.gerar_token("c_ana", PARCEIROS["c_ana"])) is None
    assert C.ler_token(acesso.gerar_token("admin", 0, 1)) is None


def test_app_desligado_bloqueia_entrada(t):
    T.BASE.cfg_cache["tickets_hub"] = {"app_cliente": {"ativo": False}}
    assert entrar(t).status_code == 503


def test_ajustes_do_app_salvam_pela_central(t):
    r = t.put("/api/tickets/config", json={"app_cliente": {"ativo": True, "exigir_palavra": True, "empresa": "KingStar Atende",
                                                           "ura": [{"rotulo": "Garantia", "motivo_pai": "Pedido", "departamento": "CX"}]}})
    assert r.status_code == 200
    T.BASE.t_cfg = time.time() + 3600      # sem reler o resto do banco falso: usa o que a central acabou de gravar
    cfg = C.cfg_app()
    assert cfg["empresa"] == "KingStar Atende" and cfg["exigir_palavra"] and cfg["ura"][0]["id"] == "op1"


def test_chamados_no_app_mostram_o_definido_e_as_atualizacoes(t):
    entrar(t)
    sid = t.post("/api/cliente/chamados", json={"motivo_pai": "Logística", "motivo_filho": "Danos à Residência", "texto": "Riscaram a parede"}).json()["id"]
    tid = central(t, sid)["id"]
    t.post(url_tk(tid) + "/comentar", json={"texto": "Liguei: o técnico vai na quinta.", "tipo": "contato"})   # cliente vê
    t.post(url_tk(tid) + "/comentar", json={"texto": "cliente nervoso", "tipo": "nota"})                       # só a equipe
    t.post(url_tk(tid) + "/classificar", json={"motivo_pai": "Logística", "motivo_filho": "Danos à Residência", "etapa": "Apurar", "data_prevista": "2099-01-15"})
    s = t.get("/api/cliente/eu").json()["chamado"]["solicitacoes"][0]
    assert [a["texto"] for a in s["atualizacoes"]] == ["Riscaram a parede", "Liguei: o técnico vai na quinta."]
    assert s["definido"]["etapa"] == "Apurar" and s["definido"]["prazo"] == "2099-01-15" and s["definido"]["motivo"] == "Logística › Danos à Residência"
    assert "nervoso" not in str(s)


def test_central_chama_o_cliente_pelo_app(t, monkeypatch):
    """WROUTER › 💬 Falar com o cliente: abre o chat do app já com a mensagem da central (ou entra no chat ativo)."""
    import promocoes
    avisos = []
    monkeypatch.setattr(promocoes, "avisar_cliente_detalhe", lambda *a, **k: avisos.append(a) or {"total": 0, "enviados": 0})
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    me = {"login": "atendente", "nome": "Carla Atendente"}
    try:
        C.central_chama("c_ana", "Oi", me)
        assert False, "sem código do app não chama"
    except Exception as ex:  # noqa: BLE001
        assert getattr(ex, "status_code", 0) == 409
    entrar(t)   # gera o código do app
    r = C.central_chama("c_ana", "Olá, Ana! Aqui é da central de entregas, sobre o seu pedido #101.", me, {"id": "ped1", "numero": 101})
    assert r["existente"] is False and avisos and avisos[0][1].startswith("💬")
    chat = t.get("/api/cliente/eu").json()["chat"]
    assert chat and chat["id"] == r["id"] and [(m["de"], m["texto"][:9]) for m in chat["mensagens"]] == [("central", "Olá, Ana!")]
    tk = central(t, r["id"])
    assert tk["app_tipo"] == "chat" and tk["status"] == "em_andamento" and not tk["app_pendente"]
    assert t.post(f"/api/cliente/chamado/{r['id']}/mensagem", json={"texto": "Pode falar!"}).status_code == 200
    r2 = C.central_chama("c_ana", "O motorista chega em 10 min.", me)
    assert r2["existente"] is True and r2["id"] == r["id"], "entra no chat que já está aberto"
    msgs = [m["texto"] for m in t.get("/api/cliente/eu").json()["chat"]["mensagens"]]
    assert msgs[-2:] == ["Pode falar!", "O motorista chega em 10 min."]


def test_finalizar_so_o_chat_do_cliente(t, monkeypatch):
    """Tela dividida do WROUTER: finalizar com o cliente fecha só o chat do app (o do motorista é outro)."""
    import promocoes
    monkeypatch.setattr(promocoes, "avisar_cliente", lambda *a, **k: None)
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    me = {"login": "atendente", "nome": "Carla"}
    entrar(t)
    assert C.chat_com_cliente("c_ana")["ativo"] is False
    C.central_chama("c_ana", "Olá, Ana!", me)
    st = C.chat_com_cliente("c_ana")
    assert st["ativo"] and st["mensagens"][-1]["de"] == "central" and not st["nova"]
    assert t.post(f"/api/cliente/chamado/{st['id'].split('#')[-1]}/mensagem", json={"texto": "Oi!"}).status_code == 200
    assert C.chat_com_cliente("c_ana")["nova"] is True, "cliente respondeu: o balão mostra o ponto"
    assert C.central_finaliza_chat("c_ana", me) is True
    assert C.chat_com_cliente("c_ana")["ativo"] is False and t.get("/api/cliente/eu").json()["chat"] is None


def test_chat_finalizado_continua_no_pdf_do_caso(t, monkeypatch):
    """Depois de finalizado, o WROUTER ainda lê a conversa do cliente daquela entrega (para o PDF do caso)."""
    import promocoes
    monkeypatch.setattr(promocoes, "avisar_cliente", lambda *a, **k: None)
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    me = {"login": "atendente", "nome": "Carla"}
    entrar(t)
    r = C.central_chama("c_ana", "Olá, Ana!", me)
    C.central_finaliza_chat("c_ana", me)
    assert C.chat_com_cliente("c_ana")["mensagens"] == []
    st = C.chat_com_cliente("c_ana", r["id"])
    assert st["ativo"] is False and st["mensagens"][0]["texto"] == "Olá, Ana!"


PNG_1PX = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


def test_anexo_no_chat_do_cliente(t, monkeypatch):
    """Central manda anexo (com limite) no chat do app: o cliente abre só o que é dele."""
    import promocoes
    import anexos
    monkeypatch.setattr(promocoes, "avisar_cliente", lambda *a, **k: None)
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    me = {"login": "atendente", "nome": "Carla"}
    entrar(t)
    C.central_chama("c_ana", "Segue a *foto* da NF: https://exemplo.com", me, anexos=[{"nome": "nf.png", "dados": PNG_1PX}])
    m = t.get("/api/cliente/eu").json()["chat"]["mensagens"][-1]
    assert m["texto"].startswith("Segue a *foto*") and m["anexos"][0]["tipo"] == "image/png"
    r = t.get(f"/api/cliente/anexo/{m['anexos'][0]['id']}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert t.get("/api/cliente/anexo/" + "0" * 20).status_code == 404
    grande = "data:application/pdf;base64," + __import__("base64").b64encode(b"x" * (anexos.MAX_BYTES + 1)).decode()
    for ruim, cod in (([{"nome": "a.pdf", "dados": grande}], 413), ([{"nome": "a.exe", "dados": "data:application/x-msdownload;base64,AAAA"}], 415),
                      ([{"nome": "a.png", "dados": PNG_1PX}] * 4, 413)):
        try:
            C.central_chama("c_ana", "x", me, anexos=ruim)
            assert False, "devia recusar"
        except Exception as ex:  # noqa: BLE001
            assert getattr(ex, "status_code", 0) == cod


# ── LINK DE ATENDIMENTO (/atendimento/): bot valida com o que está no ERP → só chat ──
def _preparar_link():
    E.ST.dados["parceiros"]["c_ana"]["endereco"] = {"logradouro": "Rua A", "numero": "742", "bairro": "Centro", "cep": "01310-100", "cidade": "SP"}
    E.ST.dados["parceiros"]["c_bia"]["endereco"] = {"bairro": "Vila Nova"}
    for i, n in enumerate(["Travesseiro", "Box Solteiro", "Colchão Queen", "Protetor"]):
        E.ST.dados["produtos"][f"x{i}"] = {"nome": n}


def _certa(conv):
    q = C._conversas[conv]["atual"]
    return q["certo"][0] if q["modo"] == "sobrenome" else q["certo"]


def _errada(conv):
    q = C._conversas[conv]["atual"]
    return {"digitos": "0000", "sobrenome": "xyzw", "opcao": str(int(q.get("certo") or 1) % 4 + 1)}[q["modo"]]


def test_link_valida_cpf_e_duas_perguntas_e_so_abre_o_chat(t):
    _preparar_link()
    assert t.get("/api/cliente/atendimento/info").json()["validado"] is False
    assert t.post("/api/cliente/atendimento/cpf", json={"cpf": "123.456.789-00"}).status_code == 422
    assert t.post("/api/cliente/atendimento/cpf", json={"cpf": "390.533.447-05"}).status_code == 404   # CPF válido sem cadastro
    r = t.post("/api/cliente/atendimento/cpf", json={"cpf": CPF_ANA}).json()
    conv, q1 = r["conversa"], C._conversas[r["conversa"]]["atual"]
    assert "certo" not in str(r) and (q1["modo"] == "opcao" or q1["certo"] not in str(r))             # a resposta não vai para a página
    r = t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _certa(conv)}).json()
    assert r["ok"] and r["passo"] == 2 and r["pergunta"]["texto"]
    assert t.get("/api/cliente/atendimento/chat").status_code == 401                                   # ainda não validou
    r = t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _certa(conv)})
    assert r.json()["validado"] and "Ana" in r.json()["direcionando"]
    assert t.get("/api/cliente/atendimento/info").json()["validado"] is True
    sid = t.post("/api/cliente/atendimento/mensagem", json={"texto": "Quero saber da entrega", "req": "abc"}).json()["id"]
    tk = central(t, sid)
    assert tk["assunto"] == "Atendimento pelo link" and tk["app_tipo"] == "chat" and tk["departamento"] == "CX"
    tid = tk["id"]
    t.post(url_tk(tid) + "/comentar", json={"texto": "Chega amanhã!", "tipo": "resposta"})
    ch = t.get("/api/cliente/atendimento/chat").json()
    assert ch["ativo"] and [m["texto"] for m in ch["mensagens"]] == ["Quero saber da entrega", "Chega amanhã!"]
    # só atendimento: o cookie do link não vale no app (pedidos/chamados)
    assert t.get("/api/cliente/eu").status_code == 401
    assert t.post("/api/cliente/chamados", json={"motivo_pai": "Pedido", "motivo_filho": "Cancelamento", "texto": "x"}).status_code == 401


def test_link_erra_duas_vezes_e_encerra(t):
    _preparar_link()
    conv = t.post("/api/cliente/atendimento/cpf", json={"cpf": CPF_ANA}).json()["conversa"]
    r = t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _errada(conv)}).json()
    assert r["ok"] is False and not r.get("fim") and r["pergunta"]                                     # outra pergunta
    r = t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _errada(conv)}).json()
    assert r["fim"] and conv not in C._conversas
    assert t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": "1"}).status_code == 410
    assert t.get("/api/cliente/atendimento/chat").status_code == 401


def test_link_cadastro_incompleto_nao_valida(t):
    # só o primeiro nome e o CPF: não há 2 perguntas
    E.ST.dados["parceiros"]["c_ze"] = {"tipo": "cliente", "nome": "Zé", "doc": "123.123.123-87", "ativo": True}
    assert t.post("/api/cliente/atendimento/cpf", json={"cpf": "12312312387"}).status_code == 409


def test_respostas_aceitam_jeitos_de_escrever():
    q = {"id": "numero", "modo": "digitos", "certo": "42", "zeros": True}
    assert C.resposta_confere(q, "nº 042") and not C.resposta_confere(q, "")
    q = {"id": "produto", "modo": "opcao", "certo": "3", "opcoes": ["A", "B", "Colchão", "D"]}
    assert C.resposta_confere(q, "3") and C.resposta_confere(q, "colchao") and not C.resposta_confere(q, "2")


def test_wwhat_salva_pela_central_e_desliga_o_link(t):
    assert t.put("/api/tickets/config", json={"wwhat": {"ativo": False, "saudacao": "Oi, aqui é a {empresa}!", "departamento": "Logística"}}).status_code == 200
    T.BASE.t_cfg = time.time() + 3600      # usa o que a central acabou de gravar (sem reler o banco falso)
    est = t.get("/api/tickets/estado").json()["wwhat"]
    assert est["saudacao"] == "Oi, aqui é a {empresa}!" and est["departamento"] == "Logística" and est["ativo"] is False
    i = t.get("/api/cliente/atendimento/info").json()
    assert i["ativo"] is False and i["saudacao"] == "Oi, aqui é a Central do Cliente!"
    assert t.post("/api/cliente/atendimento/cpf", json={"cpf": CPF_ANA}).status_code == 503


def test_cpf_nao_achado_segue_sem_identificacao(t):
    for _ in range(4):   # a página dá 3 chances a mais com calma; depois segue sem identificação
        assert t.post("/api/cliente/atendimento/cpf", json={"cpf": "390.533.447-05"}).status_code == 404
    assert t.post("/api/cliente/atendimento/visitante", json={"nome": "a"}).status_code == 422
    r = t.post("/api/cliente/atendimento/visitante", json={"nome": "maria   da silva"}).json()
    assert r["nome"] == "Maria" and "Maria" in r["direcionando"]
    i = t.get("/api/cliente/atendimento/info").json()
    assert i["validado"] and i["visitante"] and i["nome"] == "Maria"
    sid = t.post("/api/cliente/atendimento/mensagem", json={"texto": "Comprei na loja e não tenho cadastro", "req": "v1"}).json()["id"]
    tk = central(t, sid)
    assert tk["assunto"] == "Atendimento pelo link · sem identificação" and tk["cliente_codigo"].startswith("V") and not tk.get("erp_cliente_id")
    t.post(url_tk(tk["id"]) + "/comentar", json={"texto": "Olá Maria! Me passa o número do pedido?", "tipo": "resposta"})
    assert [m["de"] for m in t.get("/api/cliente/atendimento/chat").json()["mensagens"]] == ["cliente", "central"]
    assert t.get("/api/cliente/eu").status_code == 401                                                  # nada do app


def _validar(t):
    conv = t.post("/api/cliente/atendimento/cpf", json={"cpf": CPF_ANA}).json()["conversa"]
    t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _certa(conv)})
    return t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _certa(conv)}).json()


def test_varias_entradas_pelo_link_caem_na_mesma_conversa(t):
    _preparar_link()
    r1 = _validar(t)
    assert r1["continua"] is None and r1["tk"]
    sid = t.post("/api/cliente/atendimento/mensagem", json={"texto": "Oi, é a Ana", "req": "a1"}).json()["id"]
    tid = central(t, sid)["id"]
    t.post(url_tk(tid) + "/alterar", json={"atribuir": "atendente"})
    # outro aparelho / outra pessoa da casa: valida de novo e cai na MESMA conversa
    t.cookies.clear()
    r2 = _validar(t)
    assert r2["continua"]["id"] == sid and r2["continua"]["atendente"] == "Carla"
    assert t.post("/api/cliente/atendimento/mensagem", json={"texto": "Sou o marido dela", "req": "m1"}).json()["id"] == sid
    ts = [x for x in t.get("/api/tickets/estado").json()["tickets"] if x.get("app_tipo") == "chat"]
    assert len(ts) == 1
    ch = t.get("/api/cliente/atendimento/chat").json()
    assert [m["texto"] for m in ch["mensagens"]] == ["Oi, é a Ana", "Sou o marido dela"]          # a nota da central não aparece para o cliente
    assert "Entrou de novo pelo link" in str(t.get(url_tk(tid)).json())                            # mas a central vê
    # navegador que apagou o cookie: o token guardado no aparelho continua a conversa
    t.cookies.clear()
    assert t.get("/api/cliente/atendimento/info").json()["validado"] is False
    i = t.get("/api/cliente/atendimento/info", headers={"X-Atend-Token": r2["tk"]}).json()
    assert i["validado"] and i["continua"]["id"] == sid


def test_banco_de_perguntas_so_com_numeros_e_sem_repetir_assunto(t):
    _preparar_link()
    E.ST.dados["parceiros"]["c_ana"]["nascimento"] = "1990-03-07"
    cli = E.ST.dados["parceiros"]["c_ana"]
    vistos = set()
    for _ in range(60):
        fila = C.perguntas_do_cliente("c_ana", cli)
        assert len({q["grupo"] for q in fila}) == len(fila)                              # um assunto por pergunta
        vistos |= {q["id"] for q in fila}
        for q in fila:
            assert q["certo"].isdigit()                                                  # tudo se responde com números
            if q["modo"] == "opcao":
                assert len(q["opcoes"]) == 4 and len({x.lower() for x in q["opcoes"]}) == 4
    assert {"numero", "telefone", "cep", "produto", "bairro", "sobrenome", "email", "complemento"} <= vistos
    assert vistos & {"nasc_dia", "nasc_mes", "nasc_ano", "nasc_data"}
    for _ in range(40):   # sem complemento cadastrado → "Sem complemento" é a resposta certa
        q = next((q for q in C.perguntas_do_cliente("c_ana", cli) if q["id"] == "complemento"), None)
        if q:
            assert q["opcoes"][int(q["certo"]) - 1] == "Sem complemento"
            break
    for _ in range(20):   # e-mail aparece mascarado e as respostas certas batem
        q = next((q for q in C.perguntas_do_cliente("c_ana", cli) if q["id"] == "email"), None)
        if q:
            assert q["opcoes"][int(q["certo"]) - 1] == "an•••@ex•••.com"
            break
    # o que foi perguntado na última validação vai para o fim da fila
    fila = C.perguntas_do_cliente("c_ana", cli, evitar=("numero", "telefone", "cep"))
    assert fila[0]["id"] not in ("numero", "telefone", "cep") and fila[1]["id"] not in ("numero", "telefone", "cep")


def test_erp_guarda_data_de_nascimento(t):
    with E.ST.trava:
        pid, d = E.gravar_parceiro({"login": "x"}, "c_ana", {"nascimento": "1990-03-07"})
    assert d["nascimento"] == "1990-03-07"
    with E.ST.trava:
        try:
            E.gravar_parceiro({"login": "x"}, "c_ana", {"nascimento": "07/03/1990"})
            assert False
        except Exception as ex:  # noqa: BLE001
            assert getattr(ex, "status_code", 0) == 400
    assert "nascimento" not in E._filtrar({"acoes": {}, "campos": {"contato": "oculto"}}, "parceiros", dict(d))


def test_chamar_cliente_pela_caixa_fica_em_chamei_ate_responder(t, monkeypatch):
    import promocoes
    avisos = []
    monkeypatch.setattr(promocoes, "avisar_cliente_detalhe", lambda *a, **k: avisos.append(a) or {"total": 1, "enviados": 1})
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    entrar(t)   # gera o código da Ana
    sid = t.post("/api/cliente/chamados", json={"motivo_pai": "Pedido", "motivo_filho": "Cancelamento", "texto": "Quero cancelar"}).json()["id"]
    cid = central(t, sid)["cid"]
    r = t.post(f"/api/tickets/cliente/{quote(cid, safe='')}/chamar", json={"texto": "Olá, Ana! Pode falar agora?"}).json()
    assert r["ok"] and avisos and avisos[-1][1] == "💬 A central está te chamando" and r["avisados"] == 1
    assert avisos[-1][4].startswith("central-")                                     # etiqueta nova a cada chamada (o celular toca de novo)
    chat = next(x for x in t.get("/api/tickets/estado").json()["tickets"] if x["app_tipo"] == "chat")
    assert chat["chamei_em"] and chat["status"] == "em_andamento"                                   # fila "Chamei"
    assert t.get("/api/cliente/eu").json()["chat"]["mensagens"][-1]["texto"] == "Olá, Ana! Pode falar agora?"
    t.post("/api/cliente/chat", json={"texto": "Oi, pode sim"})                                     # respondeu → sai de Chamei
    chat = next(x for x in t.get("/api/tickets/estado").json()["tickets"] if x["app_tipo"] == "chat")
    assert not chat["chamei_em"] and chat["app_pendente"]
    r = t.post(f"/api/tickets/cliente/{quote(cid, safe='')}/chamar", json={"texto": "Ana, ainda está aí?"}).json()   # chamar de novo
    assert r["existente"] and next(x for x in t.get("/api/tickets/estado").json()["tickets"] if x["app_tipo"] == "chat")["chamei_em"]


def test_chamar_visitante_do_link_e_avisar_no_link(t, monkeypatch):
    import promocoes
    guardadas, enviados = {}, []
    monkeypatch.setattr(promocoes, "inscricoes", lambda: guardadas)
    monkeypatch.setattr(promocoes, "_gravar_insc", lambda cod, d: guardadas.__setitem__(cod, d) if d else guardadas.pop(cod, None))
    monkeypatch.setattr(promocoes, "enviar_push", lambda sub, dados, *a: enviados.append((sub, dados)) or "ok")
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    t.post("/api/cliente/atendimento/visitante", json={"nome": "Maria"})
    sid = t.post("/api/cliente/atendimento/mensagem", json={"texto": "Oi", "req": "x1"}).json()["id"]
    cod = central(t, sid)["cliente_codigo"]
    sub = {"endpoint": "https://push.exemplo/abc", "keys": {"p256dh": "k", "auth": "a"}}
    assert t.post("/api/cliente/atendimento/push", json={"inscricao": sub}).status_code == 200
    assert guardadas[cod]["subs"][0]["url"] == "/atendimento/"
    r = C.chamar_por_codigo(cod, "Maria, pode falar?", {"login": "atendente", "nome": "Carla"})
    assert r["aparelhos"] == 1 and enviados[-1][1]["url"] == "/atendimento/" and "url" not in enviados[-1][0]   # toque abre o link
    assert r["avisados"] == 1
    assert t.get("/api/cliente/atendimento/chat").json()["mensagens"][-1]["texto"] == "Maria, pode falar?"
    assert all(x.get("url") for x in guardadas[cod]["subs"])                                       # celular só do link (fora dos disparos)


def test_presenca_online_pausa_offline_e_sem_sinal(t, monkeypatch):
    gravados = []
    monkeypatch.setattr(T, "_registrar", lambda *a: gravados.append(a))
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    T.PRESENCA.clear()
    r = t.get("/api/tickets/presenca?inicio=1").json()
    assert r["status"] == "online" and [p["id"] for p in r["pausas"]] == ["pausa", "almoco", "banheiro", "reuniao"]
    assert T.disponivel("atendente")
    assert t.post("/api/tickets/presenca", json={"status": "almoco"}).json()["status"] == "almoco"
    assert not T.disponivel("atendente") and gravados[-1][1] == "almoco" and gravados[-1][3] is not None   # fechou o online, abriu o almoço
    assert t.post("/api/tickets/presenca", json={"status": "dormindo"}).status_code == 400
    assert t.get("/api/tickets/presenca").json()["status"] == "almoco"                                  # o sinal não muda a pausa
    T.PRESENCA["atendente"]["ping"] -= T.SEM_SINAL_SEG + 10                                            # fechou o navegador
    assert T.presenca("atendente")["status"] == "offline"
    assert t.get("/api/tickets/presenca?inicio=1").json()["status"] == "online"                         # abriu o hub de novo
    eq = t.get("/api/tickets/equipe").json()["pessoas"]
    assert next(x for x in eq if x["usuario"] == "atendente")["status"] == "online"


def test_limites_e_pausas_salvam_em_ajustes(t):
    r = t.put("/api/tickets/config", json={"limites": {"atendente": 3, "outro": 0, "vazio": ""}, "pausas": [{"rotulo": "Treinamento", "emoji": "🎓"}, {"rotulo": ""}]})
    assert r.status_code == 200
    T.BASE.t_cfg = time.time() + 3600
    assert T.limite_de("atendente") == 3 and T.limite_de("outro") == 0 and T.limite_de("vazio") is None
    assert T.pausas() == [{"id": "treinamento", "rotulo": "Treinamento", "emoji": "🎓"}]
    assert t.put("/api/tickets/config", json={"limites": {"x": "abc"}}).status_code == 400


def test_presenca_grava_trechos_do_dia(t):
    t0 = time.time() - 3600
    T._registrar("carla", "online", t0, None)
    T._registrar("carla", "almoco", t0 + 1800, t0 + 1800)
    dia = T.datetime.fromtimestamp(t0, T.BRT).strftime("%Y-%m-%d")
    segs = T._seg_doc("carla", dia).get().to_dict()["segs"] if T.datetime.fromtimestamp(t0 + 1800, T.BRT).strftime("%Y-%m-%d") == dia else None
    if segs is not None:
        assert [s["s"] for s in segs] == ["online", "almoco"] and segs[0]["f"] and segs[1]["f"] is None


def test_distribuicao_automatica_respeita_status_limite_e_setor(t, monkeypatch):
    monkeypatch.setattr(T, "_registrar", lambda *a: None)
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    T.BASE.cfg_cache["usuarios"] = {"ana.cx": {"nome": "Ana CX", "depto": "CX"}, "beto.cx": {"nome": "Beto CX", "depto": "CX"},
                                    "carla.cx": {"nome": "Carla CX", "depto": "CX"}, "dani.cx": {"nome": "Dani CX", "depto": "CX"},
                                    "edu.log": {"nome": "Edu Log", "depto": "Logística"}}
    T.BASE.cfg_cache["tickets_hub"] = {"limites": {"ana.cx": 1, "dani.cx": 0}}
    agora_s = time.time()
    for u, st in (("ana.cx", "online"), ("beto.cx", "online"), ("carla.cx", "almoco"), ("dani.cx", "online"), ("edu.log", "online")):
        T.PRESENCA[u] = {"status": st, "desde": agora_s, "ping": agora_s}
    T._ULT_RECEBEU.update({"ana.cx": 1, "beto.cx": 2})          # empate → a Ana recebeu há mais tempo
    # três clientes abrem chat pelo link/app (setor CX)
    E.ST.dados["parceiros"]["c_bia"]["endereco"] = {}
    dono = []
    for cli in ("c_ana", "c_bia"):
        with E.ST.trava:
            tx = E.Tx({"login": "x"}); E.garantir_codigo(tx, cli); tx.commit()
        c = E.ST.dados["parceiros"][cli]
        sid = C._chat_do_cliente(cli, c, {"texto": "Oi", "opcao": "outro"})["id"]
        dono.append(central(t, sid)["atribuido_para"])
    assert dono == ["ana.cx", "beto.cx"]                         # Ana chegou no limite (1) → o segundo foi para o Beto
    assert not T.pode_receber("carla.cx") and not T.pode_receber("dani.cx") and not T.pode_receber("ana.cx")
    assert T.pode_receber("beto.cx")                              # sem limite
    # ninguém online no setor: o chat espera na fila
    for u in ("ana.cx", "beto.cx"):
        T.PRESENCA[u]["status"] = "reuniao"
    with E.ST.trava:
        tx = E.Tx({"login": "x"}); E.garantir_codigo(tx, "c_ana"); tx.commit()
    t.post(url_tk(central(t, C._chat_do_cliente("c_ana", E.ST.dados["parceiros"]["c_ana"], {"texto": "e aí?"})["id"])["id"]) + "/alterar", json={"status": "resolvido"})
    sid = C._chat_do_cliente("c_ana", E.ST.dados["parceiros"]["c_ana"], {"texto": "Outra coisa", "opcao": "outro"})["id"]
    assert central(t, sid)["sem_dono"]
    T.PRESENCA["beto.cx"]["status"] = "online"                     # voltou: recebe na próxima rodada
    T.distribuir(forcar=True)
    assert central(t, sid)["atribuido_para"] == "beto.cx"


def test_gestao_tempo_logado_e_curva(t, monkeypatch):
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    T._SEGS.clear()
    hoje = T.datetime.now(T.BRT).strftime("%Y-%m-%d")
    T._SEGS[("atendente", hoje)] = {"segs": [{"s": "online", "i": f"{hoje} 08:00:00", "f": f"{hoje} 10:00:00"},
                                             {"s": "almoco", "i": f"{hoje} 10:00:00", "f": f"{hoje} 11:00:00"},
                                             {"s": "online", "i": f"{hoje} 11:00:00", "f": f"{hoje} 11:30:00"}]}
    tm = T.tempos("atendente", hoje, hoje, por_hora=True)
    assert tm["min"] == {"online": 150, "almoco": 60} and tm["horas"][8] == 60 and tm["horas"][11] == 30
    entrar(t)
    sid = t.post("/api/cliente/chat", json={"texto": "Oi", "opcao": "outro"}).json()["id"]
    tid = central(t, sid)["id"]
    t.post(url_tk(tid) + "/alterar", json={"atribuir": "atendente"})
    t.post(url_tk(tid) + "/comentar", json={"texto": "Olá!", "tipo": "resposta"})
    t.post(url_tk(tid) + "/alterar", json={"status": "resolvido"})
    eq = next(x for x in t.get(f"/api/tickets/equipe?de={hoje}&ate={hoje}").json()["pessoas"] if x["usuario"] == "atendente")
    assert eq["min_online"] == 150 and eq["min_pausa"] == 60 and eq["pausas"] == {"almoco": 60} and eq["chats_atendidos"] == 1
    c = t.get(f"/api/tickets/equipe/curva?de={hoje}&ate={hoje}&usuarios=atendente").json()
    assert c["por"] == "hora" and len(c["rotulos"]) == 24 and c["totais"]["chats"] == 1 and c["totais"]["respostas"] == 1
    assert c["totais"]["online"] == 150 and c["status_min"]["almoco"] == 60
    ontem = (T.datetime.now(T.BRT) - T.timedelta(days=6)).strftime("%Y-%m-%d")
    c7 = t.get(f"/api/tickets/equipe/curva?de={ontem}&ate={hoje}").json()
    assert c7["por"] == "dia" and len(c7["rotulos"]) == 7 and c7["series"]["online"][-1] == 150
    assert t.get("/api/tickets/equipe/curva?de=2026-01-01&ate=2026-12-31").status_code == 400


# ── ACESSO SEGURO: link valida → senha → aparelho conectado ──────────────────
def _validar_link(t):
    conv = t.post("/api/cliente/atendimento/cpf", json={"cpf": CPF_ANA}).json()["conversa"]
    t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _certa(conv)})
    return t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _certa(conv)}).json()


def test_app_com_senha_aparelho_e_palavra_protegida(t, monkeypatch):
    import promocoes
    avisos = []
    monkeypatch.setattr(promocoes, "avisar_cliente", lambda *a, **k: avisos.append(a))
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    _preparar_link()
    assert _validar_link(t)["validado"]
    assert t.post("/api/cliente/atendimento/instalar", json={"senha": "111111"}).status_code == 422      # fácil demais
    r = t.post("/api/cliente/atendimento/instalar", json={"senha": "482916"})
    assert r.status_code == 200 and r.json()["url"] == "/cliente/" and not avisos                       # primeiro aparelho: ninguém para avisar
    eu = t.get("/api/cliente/eu").json()
    p = next(x for x in eu["pedidos"] if x["numero"] == 101)
    assert eu["palavra_protegida"] and p["palavra_chave"] == "" and p["palavra_protegida"]
    assert t.get("/api/cliente/pedido/ped1/pdf").status_code == 403
    r = t.post("/api/cliente/desbloquear", json={"senha": "000000"})
    assert r.status_code == 401 and "mais 2" in r.json()["detail"]
    assert t.post("/api/cliente/desbloquear", json={"senha": "482916"}).status_code == 200
    assert next(x for x in t.get("/api/cliente/eu").json()["pedidos"] if x["numero"] == 101)["palavra_chave"] == "SOL42"
    ap = t.get("/api/cliente/aparelhos").json()["aparelhos"]
    assert len(ap) == 1 and ap[0]["este"]
    # outro aparelho: CPF + senha (sem bot) → o primeiro recebe o aviso
    t.cookies.clear()
    assert t.post("/api/cliente/entrar-senha", json={"cpf": CPF_ANA, "senha": "482916"}).status_code == 200
    assert avisos and avisos[-1][1] == "📱 Novo aparelho conectado"
    assert len(t.get("/api/cliente/aparelhos").json()["aparelhos"]) == 2
    # central vê e desconecta todos
    cod = E.ST.dados["parceiros"]["c_ana"]["codigo"]
    cid_tk = T._id_doc(cod)
    T.BASE.cont.setdefault(cid_tk, {"cliente_codigo": cod, "solicitacoes": []})
    assert len(t.get(f"/api/tickets/cliente/{quote(cid_tk, safe='')}/app-acesso").json()["aparelhos"]) == 2
    t.post(f"/api/tickets/cliente/{quote(cid_tk, safe='')}/app-acesso", json={"acao": "desconectar", "aparelho": "todos"})
    r = t.get("/api/cliente/eu")
    assert r.status_code == 401 and "desconectado" in r.json()["detail"]
    assert t.get("/api/cliente/sessao").json()["estado"] == "revalidar"


def test_senha_errada_3_vezes_comeca_do_zero(t, monkeypatch):
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    _preparar_link()
    _validar_link(t)
    t.post("/api/cliente/atendimento/instalar", json={"senha": "482916"})
    t.cookies.clear()
    for _ in range(2):
        assert t.post("/api/cliente/entrar-senha", json={"cpf": CPF_ANA, "senha": "999999"}).status_code == 401
    assert t.post("/api/cliente/entrar-senha", json={"cpf": CPF_ANA, "senha": "999999"}).status_code == 423
    assert t.post("/api/cliente/entrar-senha", json={"cpf": CPF_ANA, "senha": "482916"}).status_code == 423   # bloqueada
    _validar_link(t)                                                                                          # valida de novo e cria outra
    assert t.post("/api/cliente/atendimento/instalar", json={"senha": "735190"}).status_code == 200
    assert t.get("/api/cliente/eu").status_code == 200


def test_depois_de_30_dias_pede_a_senha(t, monkeypatch):
    import cliente_acesso as CA
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    _preparar_link()
    _validar_link(t)
    aid = t.post("/api/cliente/atendimento/instalar", json={"senha": "482916"}).json()["aparelho"]
    A = CA.ler("c_ana")
    corpo = C._b64(__import__("json").dumps({"c": "c_ana", "d": aid, "k": A["imp"], "e": int(time.time() - 10)}).encode())
    t.cookies.clear()
    t.cookies.set(C._ck(), corpo + "." + C._assinar(corpo))
    assert t.get("/api/cliente/eu").status_code == 401
    assert t.get("/api/cliente/sessao").json() == {"estado": "senha", "nome": "Ana"}
    r = t.post("/api/cliente/reentrar", json={"senha": "482916"})
    assert r.status_code == 200
    t.cookies.clear()
    t.cookies.set(C._ck(), r.cookies[C._ck()])
    assert t.get("/api/cliente/eu").status_code == 200
    t.cookies.clear()
    t.cookies.set(C._ck(), corpo + "." + C._assinar(corpo))
    for _ in range(2):
        assert t.post("/api/cliente/reentrar", json={"senha": "1"}).status_code == 401
    assert t.post("/api/cliente/reentrar", json={"senha": "1"}).status_code == 423                         # 3 erros: do zero
    assert t.get("/api/cliente/sessao").json()["estado"] == "revalidar"


def test_mudou_endereco_valida_de_novo(t, monkeypatch):
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    _preparar_link()
    _validar_link(t)
    t.post("/api/cliente/atendimento/instalar", json={"senha": "482916"})
    assert t.get("/api/cliente/eu").status_code == 200
    E.ST.dados["pedidos"]["ped1"]["endereco"] = {"logradouro": "Rua Outra", "numero": "10", "cep": "04000-000"}   # entregar em outro lugar
    r = t.get("/api/cliente/eu")
    assert r.status_code == 401 and "dados de entrega mudaram" in r.json()["detail"]
    t.cookies.clear()
    assert t.post("/api/cliente/entrar-senha", json={"cpf": CPF_ANA, "senha": "482916"}).status_code == 409   # a senha não basta
    _validar_link(t)
    assert t.post("/api/cliente/atendimento/instalar", json={"senha": "482916"}).status_code == 200


def test_tres_validacoes_erradas_travam_24h(t, monkeypatch):
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    _preparar_link()
    import cliente_acesso as CA
    for _ in range(3):
        C._falhas.clear()   # (o freio por IP/CPF de 15 min é outro; aqui testa a trava de 24 h)
        conv = t.post("/api/cliente/atendimento/cpf", json={"cpf": CPF_ANA}).json()["conversa"]
        t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _errada(conv)})
        t.post("/api/cliente/atendimento/resposta", json={"conversa": conv, "resposta": _errada(conv)})
    C._falhas.clear()
    r = t.post("/api/cliente/atendimento/cpf", json={"cpf": CPF_ANA})
    assert r.status_code == 429 and "24 horas" in r.json()["detail"]
    CA.acao_central("c_ana", "destravar")
    assert t.post("/api/cliente/atendimento/cpf", json={"cpf": CPF_ANA}).status_code == 200


def test_ociosa_volta_online_ao_mexer_mas_offline_manual_fica(t, monkeypatch):
    monkeypatch.setattr(T, "_registrar", lambda *a: None)
    monkeypatch.setattr(banco, "thread", lambda fn, *a, **k: fn(*a, **k))
    assert t.get("/api/tickets/presenca?inicio=1").json()["status"] == "online"
    r = t.get("/api/tickets/presenca?ocioso=1").json()
    assert r["status"] == "offline" and r["auto"]                                    # 5 min parada → offline automático
    assert t.get("/api/tickets/presenca").json()["status"] == "offline"             # sinal sem movimento não volta
    assert t.get("/api/tickets/presenca?ativo=1").json()["status"] == "online"      # mexeu → online
    T.PRESENCA["atendente"]["ping"] -= T.SEM_SINAL_SEG + 10                         # sem sinal (notebook dormiu)
    r = t.get("/api/tickets/presenca").json()
    assert r["status"] == "offline" and r["auto"]
    assert t.get("/api/tickets/presenca?ativo=1").json()["status"] == "online"
    t.post("/api/tickets/presenca", json={"status": "offline"})                      # escolheu offline no botão
    for q in ("ativo=1", "inicio=1", "ocioso=1"):
        r = t.get("/api/tickets/presenca?" + q).json()
        assert r["status"] == "offline" and not r["auto"]                            # só sai no botão
    T.PRESENCA["atendente"]["desde"] -= 86400 * 2                                    # outro dia: ao abrir o hub entra online
    assert t.get("/api/tickets/presenca?inicio=1").json()["status"] == "online"


def test_pedidos_de_ajuda_so_tem_interno():
    s = open(Path(__file__).resolve().parents[1] / "modulos" / "tickets.html", encoding="utf-8").read()
    assert "function filaSetor(setor) { return setor ? S.e.tickets.filter((t) => t.interno && " in s
