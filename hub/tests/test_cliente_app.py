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
