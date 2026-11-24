"""Membros › Saíram: carta de transferência (carta + S-21 num PDF, status Transferido),
aviso de 1 ano de batismo com OK, carta recebida na ficha, contatos de emergência e S-21 com nome/contato."""
import io
import sys
from datetime import date, timedelta
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_empresas as T  # noqa: E402
from test_empresas import entrar, hub  # noqa: E402,F401  (fixture)


def _prep(secretaria):
    hoje = date.today()
    bat = (hoje - timedelta(days=366)).strftime("%d/%m/%Y")          # completou 1 ano ontem
    T.DB[(secretaria.COL_MEMBROS, "Neuza Cruz de Assis")] = {
        "categoria": "PUBLICADOR", "genero": "Feminino", "data_batismo": "05/05/1990",   # ficha antiga, SEM nome_oficial
        "telefone_emergencia": "Maria (filha) (11) 98888-7777", "saiu_em": "2026-10", "status": "Inativo"}
    T.DB[(secretaria.COL_MEMBROS, "Pedro Novo Batizado")] = {"nome_oficial": "Pedro Novo Batizado", "categoria": "PUBLICADOR",
                                                            "data_batismo": bat, "telefone_emergencia": "Ana 11 97777-0000"}
    T.DB[(secretaria.COL_MEMBROS, "Antigo Batizado")] = {"nome_oficial": "Antigo Batizado", "categoria": "PUBLICADOR",
                                                        "data_batismo": "01/01/2000"}
    T.DB[(secretaria.COL_REL, "r1")] = {"nome": "Neuza Cruz de Assis", "membro_id": "Neuza Cruz de Assis",
                                        "mes_referencia": "Setembro 2025", "participou_ministerio": True}
    secretaria.BASE.membros = None
    secretaria.BASE.cfg = {**secretaria.CONFIG_PADRAO}


def _membro(base, nome):
    return next(m for m in base["membros"] if m["id"] == nome)


def test_aniversario_de_batismo_pisca_ate_ok(hub):
    import secretaria
    c = entrar(hub(), "chefe", "senha-forte")
    _prep(secretaria)
    b = c.get("/api/secretaria/base").json()
    assert _membro(b, "Pedro Novo Batizado")["aniv_batismo"]["alerta"] is True
    assert _membro(b, "Antigo Batizado")["aniv_batismo"]["alerta"] is False      # 1 ano faz muito tempo: não pisca
    assert c.post("/api/secretaria/membros/Pedro Novo Batizado/batismo-ok").status_code == 200
    b = c.get("/api/secretaria/base").json()
    assert _membro(b, "Pedro Novo Batizado")["aniv_batismo"]["alerta"] is False
    assert secretaria.primeiro_aniversario_batismo("NB") is None
    assert secretaria.primeiro_aniversario_batismo("29/02/2024") == date(2025, 2, 28)


def test_carta_de_transferencia_marca_transferido_e_gera_pdf(hub):
    import secretaria
    c = entrar(hub(), "chefe", "senha-forte")
    _prep(secretaria)
    corpo = {"data": "21 de Novembro de 2026", "destino": "A Congregação:\nJenipapo de Minas, MG\nCONG094131029@jwpub.org",
             "referencia": "Ref.: Mudança de Publicador Neuza Cruz de Assis", "conteudo": "Prezados irmãos:\n\nSem mais..."}
    r = c.put("/api/secretaria/membros/Neuza Cruz de Assis/transferencia", json=corpo)
    assert r.status_code == 200 and r.json()["transferencia"]["feita"] is False                # rascunho
    r = c.put("/api/secretaria/membros/Neuza Cruz de Assis/transferencia", json={**corpo, "concluir": True})
    assert r.json()["transferencia"]["feita"] is True
    gravado = T.DB[(secretaria.COL_MEMBROS, "Neuza Cruz de Assis")]["transferencia"]
    assert gravado["destino"].startswith("A Congregação") and gravado["feita_por"] == "chefe"
    b = c.get("/api/secretaria/base").json()
    assert _membro(b, "Neuza Cruz de Assis")["transferencia"]["feita"] is True
    pdf = c.get("/api/secretaria/pdf/transferencia/Neuza Cruz de Assis")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    leitor = PdfReader(io.BytesIO(pdf.content))
    assert len(leitor.pages) >= 2                                                              # carta + S-21
    assert "Jenipapo de Minas" in leitor.pages[0].extract_text()


def test_s21_sem_nome_oficial_sai_com_nome_e_contato_de_emergencia(hub):
    import secretaria
    c = entrar(hub(), "chefe", "senha-forte")
    _prep(secretaria)
    r = c.get("/api/secretaria/pdf/s21/Neuza Cruz de Assis?ano=2026")
    assert r.status_code == 200
    leitor = PdfReader(io.BytesIO(r.content))
    campos = {str(a.get_object().get("/T")): a.get_object().get("/V") for a in leitor.pages[0]["/Annots"]}
    assert str(campos["900_1_Text_SanSerif"]) == "Neuza Cruz de Assis"                         # antes saía em branco
    assert "98888-7777" in leitor.pages[0].extract_text()                                     # contato de emergência


def test_contatos_de_emergencia_e_carta_recebida(hub):
    import secretaria
    c = entrar(hub(), "chefe", "senha-forte")
    _prep(secretaria)
    r = c.get("/api/secretaria/contatos-emergencia")
    assert r.status_code == 200
    txt = r.content.decode("utf-8-sig")
    assert txt.splitlines()[0] == "Publicador;Telefone de emergência;Grupo de campo;Situação"
    assert "Pedro Novo Batizado;Ana 11 97777-0000" in txt and "Neuza" not in txt               # quem saiu fica de fora
    assert "Neuza" in c.get("/api/secretaria/contatos-emergencia?todos=1").content.decode("utf-8-sig")
    r = c.post("/api/secretaria/membros", json={"nome_oficial": "Joana Recebida", "carta_recebida": "Prezados irmãos: apresentamos a irmã Joana."})
    assert r.status_code == 200
    assert "apresentamos" in T.DB[(secretaria.COL_MEMBROS, "Joana Recebida")]["carta_recebida"]


def test_modelo_da_carta_guarda_imagem_no_banco(hub):
    import base64
    import secretaria
    c = entrar(hub(), "chefe", "senha-forte")
    _prep(secretaria)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 20).decode()
    assert c.put("/api/secretaria/config", json={"carta_assinaturas": "nao-e-imagem"}).status_code == 400
    assert c.put("/api/secretaria/config", json={"carta_cabecalho": ["Linha 1"], "carta_assinaturas": png}).status_code == 200
    b = c.get("/api/secretaria/base").json()
    assert b["config"]["carta_assinaturas_ok"] is True and "carta_assinaturas" not in b["config"]   # a imagem não vai para a tela
