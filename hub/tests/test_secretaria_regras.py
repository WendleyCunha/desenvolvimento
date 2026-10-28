"""Testes das regras da Secretaria — rodar: python -m pytest hub/tests -q"""
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import secretaria_regras as R  # noqa: E402


# ── meses ────────────────────────────────────────────────────────────────────
def test_ano_servico_e_rotulos():
    assert R.ano_servico("2026-09") == 2027
    assert R.ano_servico("2026-08") == 2026
    assert R.rotulo_banco("2026-09") == "SETEMBRO 2027"
    assert R.rotulo_banco("2027-01") == "JANEIRO 2027"
    assert R.rotulo_civil("2026-09") == "SETEMBRO 2026"
    assert R.meses_do_as(2027)[0] == "2026-09" and R.meses_do_as(2027)[-1] == "2027-08"
    assert R.somar("2026-12", 1) == "2027-01" and R.somar("2027-01", -2) == "2026-11"


def test_corte_dia_20():
    assert R.chave_por_data(date(2026, 10, 20)) == "2026-09"
    assert R.chave_por_data(date(2026, 10, 21)) == "2026-10"
    assert R.chave_por_data(date(2027, 1, 5)) == "2026-12"


def test_formulario_com_ano_civil_vai_para_o_mes_certo():
    # formulário enviou em 05/10/2026 rotulado "SETEMBRO 2026" (ano civil)
    rel = {"mes_referencia": "SETEMBRO 2026", "data_envio": datetime(2026, 10, 5, 12, tzinfo=timezone.utc)}
    assert R.resolver_chave(rel) == "2026-09"
    # baixa do admin (ano de serviço) feita em 06/10/2026
    rel = {"mes_referencia": "SETEMBRO 2027", "timestamp": datetime(2026, 10, 6, tzinfo=timezone.utc)}
    assert R.resolver_chave(rel) == "2026-09"
    # registro migrado (antigo formulário de out/2025, hoje rotulado no padrão novo)
    rel = {"mes_referencia": "SETEMBRO 2026", "data_envio": datetime(2025, 10, 3, tzinfo=timezone.utc)}
    assert R.resolver_chave(rel) == "2025-09"
    # sem data → convenção do admin
    assert R.resolver_chave({"mes_referencia": "DEZEMBRO 2027"}) == "2026-12"
    assert R.resolver_chave({"mes_referencia": "Março 2027"}) == "2027-03"
    assert R.resolver_chave({"mes_chave": "2026-11", "mes_referencia": "X"}) == "2026-11"


# ── classificação ────────────────────────────────────────────────────────────
def test_regra_das_15_horas():
    pub = {"categoria": "PUBLICADOR"}
    assert R.classificar(pub, {"horas": 15}) == R.AUX
    assert R.classificar(pub, {"horas": 14}) == R.PUB
    assert R.classificar({"categoria": R.REG}, {"horas": 3}) == R.REG
    assert R.classificar({"cargo": ["Pioneiro regular"]}, {"horas": 50}) == R.REG
    assert R.classificar(pub, {"horas": 2, "categoria_mes": R.AUX}) == R.AUX
    assert R.classificar(pub, {"horas": 30}, limite=30) == R.AUX


def test_participou():
    assert R.participou({"participou_ministerio": True})
    assert not R.participou({"participou_ministerio": False, "horas": 0})
    assert R.participou({"participou_ministerio": False, "estudos_biblicos": 1})
    assert R.participou({"horas": 0})  # baixa antiga sem o campo


def test_achar_membro_igual_streamlit():
    nomes = ["Wendley Leite Cunha", "Maria Almeida Nunes Couto", "Josefa Santos Araujo"]
    assert R.achar_membro("wendley cunha", nomes) == "Wendley Leite Cunha"
    assert R.achar_membro("Josefa", nomes) == "Josefa Santos Araujo"
    assert R.achar_membro("Fulano de Tal", nomes) is None


# ── preparar / duplicidade / S-1 ─────────────────────────────────────────────
def _base():
    membros = {
        "Ana Reg": {"nome_oficial": "Ana Reg", "categoria": R.REG},
        "Bia Pub": {"nome_oficial": "Bia Pub", "categoria": R.PUB},
        "Caio Pub": {"nome_oficial": "Caio Pub", "categoria": R.PUB},
    }
    rels = [
        {"id": "1", "nome": "Ana Reg", "mes_chave": "2026-09", "horas": 50, "estudos_biblicos": 2, "participou_ministerio": True},
        {"id": "2", "nome": "Bia Pub", "mes_chave": "2026-09", "horas": 16, "estudos_biblicos": 1, "participou_ministerio": True},
        {"id": "3", "nome": "Caio Pub", "mes_chave": "2026-09", "horas": 0, "estudos_biblicos": 1, "participou_ministerio": True},
        {"id": "4", "nome": "caio pub", "mes_chave": "2026-09", "horas": 0, "estudos_biblicos": 3, "participou_ministerio": True,
         "data_envio": "2026-10-09T10:00:00"},
        {"id": "5", "nome": "Desconhecido Total", "mes_chave": "2026-09", "horas": 0},
    ]
    return membros, rels


def test_duplicado_conta_uma_vez_e_s1():
    membros, rels = _base()
    linhas = R.preparar(rels, membros)
    tri = [ln for ln in linhas if ln["situacao"] == "TRIAGEM"]
    assert len(tri) == 1
    caio = [ln for ln in linhas if ln["membro_id"] == "Caio Pub"]
    assert all(ln["duplicado"] for ln in caio) and sum(ln["principal"] for ln in caio) == 1
    s = R.s1("2026-09", linhas, membros, media_fim_semana=105)
    assert s["publicadores"] == {"relatorios": 1, "horas": 0, "estudos": 3}  # vale o mais recente (id 4)
    assert s["auxiliares"] == {"relatorios": 1, "horas": 16, "estudos": 1}
    assert s["regulares"] == {"relatorios": 1, "horas": 50, "estudos": 2}
    assert s["ativos"] == 3


def test_pendencias_e_inativos():
    membros = {
        "Ana Lima": {"nome_oficial": "Ana Lima"}, "Bruno Reis": {"nome_oficial": "Bruno Reis"},
        "Carla Dias": {"nome_oficial": "Carla Dias", "saiu_em": "2026-08"},
    }
    rels = [{"id": "x", "nome": "Ana Lima", "mes_chave": "2026-09"},
            {"id": "y", "nome": "Bruno Reis", "mes_chave": "2026-01"}]  # Bruno parou em jan/2026
    linhas = R.preparar(rels, membros)
    p = R.pendencias("2026-09", linhas, membros)
    assert [x["membro_id"] for x in p["inativos"]] == ["Bruno Reis"]
    assert p["cobrar"] == []  # C saiu, A entregou


# ── atividade ────────────────────────────────────────────────────────────────
def test_inativo_e_reativado():
    m = {"nome_oficial": "X"}
    part = {"2025-09", "2026-08"}
    meses = R.meses_do_as(2026)  # 2025-09..2026-08
    ev = R.eventos(m, part, meses)
    assert {"chave": "2026-03", "tipo": "inativou"} in ev   # 6 meses sem participar após set/25
    assert {"chave": "2026-08", "tipo": "reativou"} in ev
    assert R.situacao(m, part, "2026-02") == "ativo"
    assert R.situacao(m, part, "2026-03") == "inativo"


def test_s10_media_anual_igual_s88():
    # S-88 2026 (meio de semana) do arquivo da visita: média das médias = 89,56
    dados = [(4, 386), (5, 483), (3, 283), (5, 428), (4, 418), (4, 364), (3, 283), (4, 393), (4, 397), (4, 97), (4, 402)]
    medias = [R.resumo_mes(q, t)["media"] for q, t in dados]
    assert abs(R.media_anual(medias) - 89.56) < 0.02
    meses = {R.meses_do_as(2026)[i]: R.resumo_mes(q, t) for i, (q, t) in enumerate(dados)}
    assert R.suspeitos_assistencia(meses) == ["2026-06"]  # junho: 97 em 4 reuniões


def test_cartao_s21():
    membros, rels = _base()
    linhas = R.preparar(rels, membros)
    c = R.cartao("Bia Pub", 2027, linhas)
    assert c[0]["entregou"] and c[0]["auxiliar"] and c[0]["horas"] == 16
    assert not c[1]["entregou"]
    t = R.cartao_total(R.PUB, 2027, linhas)
    assert t[0]["observacoes"] == "1" and t[0]["horas"] == 0


def test_inativo_manual():
    m = {"nome_oficial": "X", "inativo_desde": "2026-05"}
    part = {"2026-03", "2026-04"}
    assert R.situacao(m, part, "2026-04") == "ativo"
    assert R.situacao(m, part, "2026-05") == "inativo"          # marcado, ignora mar/abr
    assert R.situacao({"nome_oficial": "X"}, part, "2026-05") == "ativo"   # sem marca seguiria ativo
    ev = R.eventos(m, part | {"2026-08"}, [R.somar("2026-04", i) for i in range(6)])
    assert {"chave": "2026-05", "tipo": "inativou"} in ev and {"chave": "2026-08", "tipo": "reativou"} in ev
    assert R.situacao(m, part | {"2026-08"}, "2026-09") == "ativo"


def test_meta_regular():
    membros = {"Ana Reg": {"nome_oficial": "Ana Reg", "categoria": R.REG}}
    rels = [{"id": str(i), "nome": "Ana Reg", "mes_chave": c, "horas": 52, "estudos_biblicos": 1}
            for i, c in enumerate(R.meses_do_as(2026))]
    linhas = R.preparar(rels, membros)
    t = R.totais_ano(membros["Ana Reg"], "Ana Reg", 2026, linhas, meta=600, ate="2026-08")
    assert t["horas"] == 624 and t["estudos"] == 12 and t["atingiu"] and t["encerrado"]
    t2 = R.totais_ano(membros["Ana Reg"], "Ana Reg", 2026, linhas[:3], meta=600, ate="2025-11")
    assert not t2["atingiu"] and t2["falta"] == 600 - 156 and t2["meses_restantes"] == 9
