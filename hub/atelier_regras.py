"""
atelier_regras.py — regras de negócio do Lila Closet Atelier (funções puras)
───────────────────────────────────────────────────────────────────────────────
Mesmas regras do sistema em Streamlit (modulos/regras_agenda.py,
mod_encomendas.py e mod_financeiro.py), sem pandas e sem banco — testáveis.

Agenda
  · régua: 1 Confecção · 2 Prova · 3 Entrega · 4 Concluído (o 4 é sempre humano)
  · Data da Confecção: dia com outra encomenda → pergunta (confirmar);
    dia com MAIS de 3 provas → bloqueado. Consertos ("[Conserto] …") não
    entram nem bloqueiam essas contas.
  · alerta urgente: entrega dentro de N dias (config), pedidos < etapa 4.
Financeiro
  · saldo em caixa = saldo do último mês fechado + recebimentos e gastos
    pagos DEPOIS dele;
  · a receber = valor_total − valor_recebido (nunca o bruto), pela data de entrega;
  · fechamento: saldo anterior + entradas − despesas pagas = saldo final
    (transportado para o mês seguinte).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

ETAPAS = {1: ("🪡", "Confecção"), 2: ("👗", "Prova"), 3: ("🎁", "Entrega"), 4: ("✅", "Concluído")}
ETAPA_CONCLUIDO = 4
LIMITE_PROVAS_PARA_CONFECCAO = 3
PREFIXO_CONSERTO = "[Conserto]"
DIC_MEDIDAS = {"Ombros": "ombros", "Costas": "costas", "Alt. Busto": "alt_busto", "Alt. Frente": "alt_frente", "Busto": "busto",
               "Cintura": "cintura", "Quadril": "quadril", "Larg. Braço": "larg_braco", "Comp. Braço": "comp_braco",
               "Comprimento": "comprimento", "Comp. Perna": "comp_perna", "Coxa": "coxa", "Gancho": "gancho", "Colarinho": "colarinho"}
CAT_GASTOS = ["Tecido", "Aviamentos/Linhas", "Zíper/Botões", "Transporte", "Manutenção de máquina", "Marketing/Redes Sociais",
              "Embalagem", "Água/Luz/Aluguel", "Impostos/Taxas", "Outros"]
CAT_RECEITAS = ["Venda de peça", "Sinal/Entrada", "Aula/Consultoria", "Reembolso recebido", "Outro"]
FORMAS_PAGAMENTO = ["Pix", "Dinheiro", "Cartão de Débito", "Cartão de Crédito", "Transferência", "Boleto"]
FORMAS_PEDIDO = ["PIX", "Dinheiro", "Cartão de Crédito", "Cartão de Débito", "A combinar"]
CAT_PESSOAL = ["Saúde/Médico", "Exercícios", "Atividades Domésticas", "Compras", "Lazer", "Família", "Outros"]
CONFIG_PADRAO = {"meta_faturamento": "5000", "meta_pedidos_mes": "8", "margem_minima_pct": "30", "reserva_emergencia_meses": "3",
                 "capital_giro_pct": "20", "cnpj": "40.717.967/0001-03", "telefone": "(11) 94600-6761",
                 "endereco": "Embu das Artes – SP", "alerta_entrega_dias": "7"}
META_HORAS_CAMPO, META_PESO_KG, PESO_INICIAL_KG = 50.0, 57.0, 70.0

# Prefixos das tarefas automáticas (os mesmos do Streamlit — é por eles que a agenda acha a etapa)
PREF_TECIDO, PREF_CONF, PREF_PROVA2, PREF_PROVA, PREF_ENTREGA = "🛍️ Tecido:", "🪡 Confecção:", "👗 2ª Prova:", "👗 Prova:", "🎁 Entrega:"
PREFIXO_CAMPO = {PREF_TECIDO: "data_tecido", PREF_CONF: "data_confeccao", PREF_PROVA2: "data_prova2",
                 PREF_PROVA: "data_prova", PREF_ENTREGA: "data_entrega"}


# ══════════════════════════════════════════════════════════════════════════════
# AUXILIARES
# ══════════════════════════════════════════════════════════════════════════════
def d(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def i(v, padrao=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return padrao


def f(v) -> float:
    try:
        x = float(v)
        return 0.0 if x != x else x
    except (TypeError, ValueError):
        return 0.0


def mes_de(v) -> str:
    return str(v or "")[:7]


def mes_seguinte(m: str) -> str:
    a, mm = int(m[:4]), int(m[5:7])
    return f"{a + (mm == 12)}-{(mm % 12) + 1:02d}"


def mes_anterior(m: str) -> str:
    a, mm = int(m[:4]), int(m[5:7])
    return f"{a - (mm == 1)}-{(mm - 2) % 12 + 1:02d}"


def ativos(encs: list[dict], excluir_id: str | None = None) -> list[dict]:
    return [e for e in encs if not i(e.get("cancelado")) and str(e.get("id")) != str(excluir_id or "")]


def sem_consertos(encs: list[dict]) -> list[dict]:
    return [e for e in encs if not str(e.get("peca") or "").startswith(PREFIXO_CONSERTO)]


def eh_conserto(e: dict) -> bool:
    return str(e.get("peca") or "").startswith(PREFIXO_CONSERTO)


# ══════════════════════════════════════════════════════════════════════════════
# AGENDA
# ══════════════════════════════════════════════════════════════════════════════
def clientes_em_confeccao_no_dia(encs, dia: date, excluir_id=None) -> list[str]:
    return [str(e.get("cliente") or "—") for e in sem_consertos(ativos(encs, excluir_id)) if d(e.get("data_confeccao")) == dia]


def contar_provas_no_dia(encs, dia: date, excluir_id=None) -> int:
    n = 0
    for e in sem_consertos(ativos(encs, excluir_id)):
        if d(e.get("data_prova")) == dia:
            n += 1
        tem_p2 = bool(i(e.get("tem_prova2"))) or bool(str(e.get("data_prova2") or "").strip())
        if tem_p2 and d(e.get("data_prova2")) == dia:
            n += 1
    return n


def validar_data_confeccao(encs, dia: date | None, excluir_id=None, confirmar=False) -> tuple[str, str]:
    """("ok"|"confirmar"|"bloqueado", mensagem) — igual ao Streamlit (v20)."""
    if dia is None:
        return "ok", ""
    provas = contar_provas_no_dia(encs, dia, excluir_id)
    if provas > LIMITE_PROVAS_PARA_CONFECCAO:
        return "bloqueado", (f"O dia {dia:%d/%m/%Y} já tem {provas} provas marcadas (mais de {LIMITE_PROVAS_PARA_CONFECCAO}) "
                             f"e por isso não pode receber confecção. Escolha outro dia.")
    if not confirmar:
        nomes = clientes_em_confeccao_no_dia(encs, dia, excluir_id)
        if nomes:
            plural = "encomenda" if len(nomes) == 1 else "encomendas"
            return "confirmar", (f"O dia {dia:%d/%m/%Y} já tem {len(nomes)} {plural} marcada(s) para confecção "
                                 f"({', '.join(nomes)}). Marcar mais uma para esse mesmo dia?")
    return "ok", ""


def ocupacao_mes(encs, ano: int, mes: int, excluir_id=None) -> dict:
    """{ 'AAAA-MM-DD': {'confeccoes': [nomes], 'provas': n, 'lotado': bool} } — para o mini-calendário."""
    base = sem_consertos(ativos(encs, excluir_id))
    out: dict[str, dict] = {}
    for e in base:
        for campo, tipo in (("data_confeccao", "c"), ("data_prova", "p"), ("data_prova2", "p")):
            dd = d(e.get(campo))
            if not dd or dd.year != ano or dd.month != mes:
                continue
            if campo == "data_prova2" and not (i(e.get("tem_prova2")) or str(e.get("data_prova2") or "").strip()):
                continue
            k = dd.isoformat()
            o = out.setdefault(k, {"confeccoes": [], "provas": 0})
            if tipo == "c":
                o["confeccoes"].append(str(e.get("cliente") or "—"))
            else:
                o["provas"] += 1
    for o in out.values():
        o["lotado"] = o["provas"] > LIMITE_PROVAS_PARA_CONFECCAO
    return out


def entregas_urgentes(encs, hoje: date, dias: int) -> list[dict]:
    out = []
    for e in ativos(encs):
        if i(e.get("etapa"), 1) >= ETAPA_CONCLUIDO:
            continue
        de = d(e.get("data_entrega"))
        if de and (de - hoje).days <= dias:
            out.append({**e, "_dias_restantes": (de - hoje).days})
    return sorted(out, key=lambda x: x["_dias_restantes"])


def etapa_maxima_por_datas(hoje: date, d_conf: date, d_prova: date) -> int:
    etapa = 1
    if d_conf and hoje >= d_conf:
        etapa = 2
    if d_prova and hoje >= d_prova:
        etapa = 3
    return etapa


def tarefas_do_pedido(enc_id: str, cliente: str, peca: str, precisa_tecido: bool, d_tecido, d_conf, d_prova,
                      tem_prova2: bool, d_prova2, d_entrega) -> list[tuple]:
    """(prefixo, categoria, horas, data, deve_existir) — mesma especificação do Streamlit."""
    return [(PREF_TECIDO, "Compras", 1.0, d_tecido, bool(precisa_tecido)),
            (PREF_CONF, "Costura", 3.0, d_conf, True),
            (PREF_PROVA2, "Costura", 1.0, d_prova2, bool(tem_prova2) and d_prova2 is not None),
            (PREF_PROVA, "Costura", 1.0, d_prova, True),
            (PREF_ENTREGA, "Costura", 0.5, d_entrega, True)]


# ══════════════════════════════════════════════════════════════════════════════
# FINANCEIRO
# ══════════════════════════════════════════════════════════════════════════════
def saldo_pendente(e: dict) -> float:
    return max(f(e.get("valor_total")) - f(e.get("valor_recebido")), 0.0)


def ultimo_fechado(fechs: list[dict]) -> dict | None:
    fs = sorted([x for x in fechs if i(x.get("fechado"))], key=lambda x: str(x.get("mes")), reverse=True)
    return fs[0] if fs else None


def saldo_em_caixa(receb, gastos, fechs) -> tuple[float, str | None, float]:
    ult = ultimo_fechado(fechs)
    corte = ult["mes"] if ult else None
    herd = f(ult.get("saldo_final")) if ult else 0.0
    r = sum(f(x.get("valor")) for x in receb if not corte or mes_de(x.get("data")) > corte)
    g = sum(f(x.get("valor")) for x in gastos if i(x.get("pago")) and (not corte or mes_de(x.get("data")) > corte))
    return herd + r - g, corte, herd


def a_receber_do_mes(encs, mes: str) -> list[dict]:
    return [{**e, "_saldo": saldo_pendente(e)} for e in ativos(encs) if saldo_pendente(e) > 0.01 and mes_de(e.get("data_entrega")) == mes]


def a_receber_atrasado(encs, hoje: date) -> list[dict]:
    return [{**e, "_saldo": saldo_pendente(e)} for e in ativos(encs)
            if saldo_pendente(e) > 0.01 and d(e.get("data_entrega")) and d(e.get("data_entrega")) < hoje]


def despesas_abertas_do_mes(gastos, mes: str) -> list[dict]:
    return [g for g in gastos if not i(g.get("pago")) and mes_de(g.get("data")) == mes]


def despesas_atrasadas(gastos, hoje: date) -> list[dict]:
    return [g for g in gastos if not i(g.get("pago")) and d(g.get("data")) and d(g.get("data")) < hoje]


def grandes_previstas(gastos) -> list[dict]:
    return [g for g in gastos if not i(g.get("pago")) and i(g.get("grande_despesa_prevista"))]


def visao_geral(encs, receb, gastos, fechs, cfg: dict, hoje: date) -> dict:
    mes = hoje.strftime("%Y-%m")
    receita_total = sum(f(r.get("valor")) for r in receb)
    pagos = [g for g in gastos if i(g.get("pago"))]
    gastos_pagos = sum(f(g.get("valor")) for g in pagos)
    lucro_real = receita_total - gastos_pagos
    caixa, corte, herd = saldo_em_caixa(receb, gastos, fechs)
    rec_mes = sum(e["_saldo"] for e in a_receber_do_mes(encs, mes))
    pag_mes = sum(f(g.get("valor")) for g in despesas_abertas_do_mes(gastos, mes))
    atr_r = a_receber_atrasado(encs, hoje)
    atr_p = despesas_atrasadas(gastos, hoje)
    receber_total = sum(saldo_pendente(e) for e in ativos(encs))
    abertos_total = sum(f(g.get("valor")) for g in gastos if not i(g.get("pago")))
    reserva_meses = i(cfg.get("reserva_emergencia_meses"), 3)
    capital_pct = f(cfg.get("capital_giro_pct") or 20) / 100
    margem_min = f(cfg.get("margem_minima_pct") or 30) / 100
    meta_fat = f(cfg.get("meta_faturamento") or 5000)
    reserva = gastos_pagos * reserva_meses / 12 if gastos_pagos > 0 else abertos_total * reserva_meses
    base_teto = receita_total + receber_total
    return {
        "mes": mes, "receita_total": receita_total, "gastos_pagos": gastos_pagos, "lucro_real": lucro_real,
        "saldo_caixa": caixa, "mes_corte": corte, "saldo_herdado": herd,
        "receber_mes": rec_mes, "pagar_mes": pag_mes, "lucro_previsto_mes": lucro_real + rec_mes,
        "saldo_projetado_mes": caixa + rec_mes - pag_mes,
        "receber_atrasado": sum(e["_saldo"] for e in atr_r), "n_receber_atrasado": len(atr_r),
        "pagar_atrasado": sum(f(g.get("valor")) for g in atr_p), "n_pagar_atrasado": len(atr_p),
        "receber_total": receber_total, "meta_faturamento": meta_fat,
        "capital_giro": receita_total * capital_pct, "capital_pct": capital_pct * 100,
        "reserva": reserva, "reserva_meses": reserva_meses,
        "teto_gastos": base_teto * (1 - margem_min) if base_teto > 0 else 0.0, "margem_min": margem_min * 100,
    }


def projecao(encs, gastos, fechs, receb, hoje: date, mes_alvo: str) -> dict:
    caixa, _, _ = saldo_em_caixa(receb, gastos, fechs)
    cursor, base = hoje.strftime("%Y-%m"), caixa
    for _ in range(36):
        if cursor >= mes_alvo:
            break
        base += sum(e["_saldo"] for e in a_receber_do_mes(encs, cursor)) - sum(f(g.get("valor")) for g in despesas_abertas_do_mes(gastos, cursor))
        cursor = mes_seguinte(cursor)
    rec = a_receber_do_mes(encs, mes_alvo)
    pag = despesas_abertas_do_mes(gastos, mes_alvo)
    tr, tp = sum(e["_saldo"] for e in rec), sum(f(g.get("valor")) for g in pag)
    return {"mes": mes_alvo, "receber": tr, "pagar": tp, "lucro": tr - tp, "saldo_fim": base + tr - tp,
            "pedidos": [{"id": e["id"], "cliente": e.get("cliente"), "peca": e.get("peca"), "saldo": e["_saldo"], "entrega": e.get("data_entrega")} for e in rec],
            "despesas": [{"id": g["id"], "descricao": g.get("descricao"), "categoria": g.get("categoria"), "valor": f(g.get("valor")), "data": g.get("data")} for g in pag]}


def resumo_mes(mes: str, receb, gastos, fechs, saldo_inicial_digitado: float | None = None) -> dict:
    """Fechamento: o mesmo cálculo do Streamlit (v19)."""
    por_mes = {x.get("mes"): x for x in fechs}
    atual, ant = por_mes.get(mes), por_mes.get(mes_anterior(mes))
    ja_fechado = bool(atual and i(atual.get("fechado")))
    tem_ant = bool(ant and i(ant.get("fechado")))
    if tem_ant:
        saldo_ini = f(ant.get("saldo_final"))
    elif saldo_inicial_digitado is not None and not ja_fechado:
        saldo_ini = f(saldo_inicial_digitado)
    elif atual:
        saldo_ini = f(atual.get("saldo_inicial"))
    else:
        saldo_ini = 0.0
    r_mes = [r for r in receb if mes_de(r.get("data")) == mes]
    g_mes = [g for g in gastos if mes_de(g.get("data")) == mes and i(g.get("pago"))]
    entradas = sum(f(r.get("valor")) for r in r_mes)
    despesas = sum(f(g.get("valor")) for g in g_mes)
    grandes = grandes_previstas(gastos)
    total_grandes = sum(f(g.get("valor")) for g in grandes)
    saldo_teorico = saldo_ini + entradas - despesas
    conc = sum(1 for x in r_mes + g_mes if i(x.get("conciliado")))
    return {"mes": mes, "ja_fechado": ja_fechado, "tem_anterior": tem_ant, "saldo_inicial_editavel": not ja_fechado and not tem_ant,
            "saldo_inicial": saldo_ini, "entradas": entradas, "despesas": despesas, "resultado": entradas - despesas,
            "saldo_teorico": saldo_teorico, "total_grandes": total_grandes, "fundos_disponiveis": saldo_teorico - total_grandes,
            "recebimentos": r_mes, "gastos": g_mes, "grandes": grandes, "conciliados": conc, "total_itens": len(r_mes) + len(g_mes),
            "fechamento": atual or None}
