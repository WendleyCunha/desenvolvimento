import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import atelier_regras as R  # noqa: E402


def enc(i, cliente, conf="2026-11-10", prova="2026-11-20", entrega="2026-11-30", **k):
    return {"id": i, "cliente": cliente, "peca": k.pop("peca", "Vestido"), "data_confeccao": conf, "data_prova": prova,
            "data_entrega": entrega, "cancelado": 0, "etapa": 1, **k}


def test_confeccao_pergunta_quando_ja_tem_encomenda():
    encs = [enc("a", "Ana")]
    st, msg = R.validar_data_confeccao(encs, date(2026, 11, 10))
    assert st == "confirmar" and "Ana" in msg
    assert R.validar_data_confeccao(encs, date(2026, 11, 10), confirmar=True)[0] == "ok"
    assert R.validar_data_confeccao(encs, date(2026, 11, 10), excluir_id="a")[0] == "ok"


def test_confeccao_bloqueada_com_mais_de_3_provas():
    encs = [enc(str(i), f"C{i}", conf="2026-11-01", prova="2026-11-15") for i in range(4)]
    assert R.validar_data_confeccao(encs, date(2026, 11, 15))[0] == "bloqueado"
    encs3 = encs[:3]
    assert R.validar_data_confeccao(encs3, date(2026, 11, 15))[0] == "ok"


def test_conserto_nao_conta_e_cancelado_nao_conta():
    encs = [enc("a", "Ana", peca="[Conserto] Barra"), enc("b", "Bia", cancelado=1)]
    assert R.validar_data_confeccao(encs, date(2026, 11, 10))[0] == "ok"


def test_segunda_prova_conta():
    encs = [enc(str(i), f"C{i}", prova="2026-11-01", tem_prova2=1, data_prova2="2026-11-15") for i in range(4)]
    assert R.contar_provas_no_dia(encs, date(2026, 11, 15)) == 4


def test_urgentes_exclui_concluidos():
    encs = [enc("a", "Ana", entrega="2026-11-03"), enc("b", "Bia", entrega="2026-11-03", etapa=4), enc("c", "Cris", entrega="2026-12-30")]
    u = R.entregas_urgentes(encs, date(2026, 11, 1), 7)
    assert [x["id"] for x in u] == ["a"] and u[0]["_dias_restantes"] == 2


def test_etapa_maxima_nunca_conclui():
    assert R.etapa_maxima_por_datas(date(2026, 12, 31), date(2026, 11, 1), date(2026, 11, 2)) == 3
    assert R.etapa_maxima_por_datas(date(2026, 10, 1), date(2026, 11, 1), date(2026, 11, 2)) == 1


def test_saldo_em_caixa_herda_ultimo_fechamento():
    rec = [{"valor": 100, "data": "2026-09-05"}, {"valor": 50, "data": "2026-10-05"}]
    gas = [{"valor": 30, "data": "2026-10-06", "pago": 1}, {"valor": 999, "data": "2026-10-07", "pago": 0}]
    fec = [{"mes": "2026-09", "fechado": 1, "saldo_final": 80}]
    caixa, corte, herd = R.saldo_em_caixa(rec, gas, fec)
    assert (caixa, corte, herd) == (100, "2026-09", 80)


def test_a_receber_usa_saldo_e_nao_bruto():
    encs = [enc("a", "Ana", entrega="2026-11-30", valor_total=500, valor_recebido=200)]
    r = R.a_receber_do_mes(encs, "2026-11")
    assert r[0]["_saldo"] == 300


def test_resumo_mes_transporta_saldo():
    rec = [{"valor": 100, "data": "2026-10-05", "conciliado": 1}]
    gas = [{"valor": 40, "data": "2026-10-06", "pago": 1}, {"valor": 70, "data": "2026-10-09", "pago": 0, "grande_despesa_prevista": 1}]
    fec = [{"mes": "2026-09", "fechado": 1, "saldo_final": 500}]
    r = R.resumo_mes("2026-10", rec, gas, fec)
    assert r["saldo_inicial"] == 500 and r["saldo_teorico"] == 560 and r["total_grandes"] == 70 and r["fundos_disponiveis"] == 490
    assert not r["saldo_inicial_editavel"] and r["conciliados"] == 1
    primeiro = R.resumo_mes("2026-08", rec, gas, fec, 123)
    assert primeiro["saldo_inicial"] == 123 and primeiro["saldo_inicial_editavel"]


def test_mes_seguinte_e_anterior():
    assert R.mes_seguinte("2026-12") == "2027-01" and R.mes_anterior("2027-01") == "2026-12"
