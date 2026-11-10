"""App do cliente (/cliente/) — fluxo completo sem Firestore de verdade.

    cd hub && python -m pytest tests/test_cliente_app.py -q
"""
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
                 "historico": [{"em": "x", "por": "joao.vendas", "evento": "Pedido criado"}], "obs": "cliente chato", "tentativas": []},
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
    tudo = {k: True for k in ("acessar", "atender", "abrir", "encerrar", "transferir", "setor", "equipe", "gestao", "configurar")}
    monkeypatch.setattr(acesso, "permissoes", lambda u, slug, esq: {"acoes": tudo, "campos": {}})
    app = FastAPI()
    app.include_router(C.router)
    app.include_router(T.router)
    return TestClient(app)


def entrar(t, cpf=CPF_ANA, email="ana@exemplo.com"):
    return t.post("/api/cliente/entrar", json={"cpf": cpf, "email": email})


def test_login_confere_cpf_e_email_e_gera_codigo(t):
    assert t.get("/api/cliente/eu").status_code == 401
    assert entrar(t, email="outra@exemplo.com").status_code == 401
    assert entrar(t, cpf="123.456.789-00").status_code == 422          # dígito verificador errado
    r = entrar(t, email="  ANA@exemplo.com ")                          # e-mail sem diferença de maiúsculas/espaços
    assert r.status_code == 200 and r.json()["nome"] == "Ana"
    cod = E.ST.dados["parceiros"]["c_ana"]["codigo"]
    assert len(cod) == 6                                                # código do cliente criado no login
    eu = t.get("/api/cliente/eu").json()
    assert eu["codigo"] == cod


def test_pedidos_so_os_meus_sem_rascunho_e_sem_dado_interno(t):
    entrar(t)
    ps = t.get("/api/cliente/eu").json()["pedidos"]
    assert [p["numero"] for p in ps] == [101]                           # 102 é rascunho, 103 é da Bia
    p = ps[0]
    assert p["rotulo"] == "Entrega agendada" and p["entrega"] == {"data": "2026-11-14", "janela": "Manhã"}
    assert p["itens"] == [{"nome": "Colchão Casal Molas", "qtd": 1}]
    assert "historico" not in p and "obs" not in p and "joao" not in str(p)


def test_freio_de_tentativas(t):
    for _ in range(C.LIMITE_DOC):
        assert entrar(t, email="errado@x.com").status_code == 401
    assert entrar(t).status_code == 429                                 # mesmo com o e-mail certo, o CPF ficou travado


def test_chat_ida_e_volta_com_a_central(t):
    entrar(t)
    r = t.post("/api/cliente/chamados", json={"opcao": "entrega", "pedido_id": "ped1", "texto": "Posso mudar para a tarde?"})
    assert r.status_code == 200 and r.json()["existente"] is False
    sid = r.json()["id"]
    # na central: chega como ticket do app, sem dono, cliente aguardando, ligado ao pedido
    est = t.get("/api/tickets/estado").json()
    tk = next(x for x in est["tickets"] if x["id"].endswith("#" + sid))
    assert tk["origem"] == "app" and tk["app_pendente"] and tk["sem_dono"] and tk["erp_pedido_numero"] == 101
    assert tk["motivo_pai"] == "Logística" and tk["departamento"] == "Logística"
    # atendente assume, faz nota interna e responde no app
    t.post(f"/api/tickets/ticket/{quote(tk['id'], safe='')}/alterar", json={"atribuir": "atendente"})
    t.post(f"/api/tickets/ticket/{quote(tk['id'], safe='')}/comentar", json={"texto": "cliente VIP, cuidado", "tipo": "nota"})
    t.post(f"/api/tickets/ticket/{quote(tk['id'], safe='')}/comentar", json={"texto": "Pode sim! Alterei para a tarde.", "tipo": "resposta", "status": "aguardando"})
    tk = next(x for x in t.get("/api/tickets/estado").json()["tickets"] if x["id"] == tk["id"])
    assert tk["app_pendente"] is False and tk["status"] == "aguardando"
    # no app: só a abertura e a resposta pública — nada de nota interna ou registro do sistema
    ch = t.get(f"/api/cliente/chamado/{sid}").json()
    assert [(m["de"], m["texto"]) for m in ch["mensagens"]] == [("cliente", "Posso mudar para a tarde?"), ("central", "Pode sim! Alterei para a tarde.")]
    assert ch["mensagens"][1]["autor"] == "Carla"
    assert ch["rotulo"] == "Aguardando sua resposta"
    # cliente responde → volta para em andamento e acende o alerta do atendente
    assert t.post(f"/api/cliente/chamado/{sid}/mensagem", json={"texto": "Obrigada!"}).status_code == 200
    tk = next(x for x in t.get("/api/tickets/estado").json()["tickets"] if x["id"] == tk["id"])
    assert tk["status"] == "em_andamento" and tk["app_pendente"] and tk["nao_visto"]


def test_mesmo_assunto_junta_no_chamado_aberto(t):
    entrar(t)
    a = t.post("/api/cliente/chamados", json={"opcao": "troca", "texto": "Veio rasgado"}).json()
    b = t.post("/api/cliente/chamados", json={"opcao": "troca", "texto": "Mandei foto?"}).json()
    assert b["existente"] and b["id"] == a["id"]
    assert len(t.get("/api/cliente/eu").json()["chamados"]) == 1


def test_um_cliente_nao_ve_o_do_outro(t):
    entrar(t)
    sid = t.post("/api/cliente/chamados", json={"opcao": "outro", "texto": "Dúvida da Ana"}).json()["id"]
    assert t.post("/api/cliente/chamados", json={"opcao": "outro", "pedido_id": "ped3", "texto": "x"}).status_code == 404  # pedido da Bia
    t.post("/api/cliente/sair")
    t.cookies.clear()
    assert entrar(t, CPF_BIA, "bia@exemplo.com").status_code == 200
    assert t.get("/api/cliente/eu").json()["chamados"] == []
    assert t.get(f"/api/cliente/chamado/{sid}").status_code == 404
    assert t.post(f"/api/cliente/chamado/{sid}/mensagem", json={"texto": "oi"}).status_code == 404


def test_chamado_aberto_pela_central_aparece_sem_o_interno(t):
    entrar(t)
    cod = E.ST.dados["parceiros"]["c_ana"]["codigo"]
    tid = T.criar_solicitacao({"assunto": "Retorno sobre avaria", "descricao": "texto interno da abertura", "cliente_codigo": cod,
                               "cliente_nome": "ana souza", "origem": "hub"}, {"usuario": "atendente", "nome": "Carla"})
    ch = t.get(f"/api/cliente/chamado/{tid.split('#')[-1]}").json()
    assert ch["assunto"] == "Retorno sobre avaria" and ch["mensagens"] == []   # descrição de abertura interna não vaza


def test_sessao_cai_se_o_email_mudar_no_erp(t):
    entrar(t)
    assert t.get("/api/cliente/eu").status_code == 200
    E.ST.dados["parceiros"]["c_ana"]["email"] = "novo@exemplo.com"
    assert t.get("/api/cliente/eu").status_code == 401


def test_token_do_cliente_nao_vale_no_hub_e_vice_versa(t):
    tk = C.gerar_token("c_ana", PARCEIROS["c_ana"])
    assert acesso.ler_token(tk) is None
    assert C.ler_token(acesso.gerar_token("admin", 0, 1)) is None


def test_encerrado_nao_aceita_mensagem_e_app_desligado_bloqueia_entrada(t):
    entrar(t)
    sid = t.post("/api/cliente/chamados", json={"opcao": "outro", "texto": "oi"}).json()["id"]
    tid = next(x["id"] for x in t.get("/api/tickets/estado").json()["tickets"] if x["id"].endswith(sid))
    t.post(f"/api/tickets/ticket/{quote(tid, safe='')}/alterar", json={"status": "finalizado"})
    assert t.post(f"/api/cliente/chamado/{sid}/mensagem", json={"texto": "e aí?"}).status_code == 409
    T.BASE.cfg_cache["tickets_hub"] = {"app_cliente": {"ativo": False}}
    t.cookies.clear()
    assert entrar(t).status_code == 503


def test_ajustes_do_app_salvam_pela_central(t):
    r = t.put("/api/tickets/config", json={"app_cliente": {"ativo": True, "empresa": "KingStar Atende",
                                                           "ura": [{"rotulo": "Garantia", "motivo_pai": "Pedido", "departamento": "CX"}]}})
    assert r.status_code == 200
    T.BASE.t_cfg = time.time() + 3600      # sem reler o resto do banco falso: usa o que a central acabou de gravar
    cfg = C.cfg_app()
    assert cfg["empresa"] == "KingStar Atende" and cfg["ura"][0]["id"] == "op1" and cfg["ura"][0]["rotulo"] == "Garantia"
