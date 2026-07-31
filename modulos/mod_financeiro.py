"""
modulos/mod_financeiro.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
BLOCO FINANCEIRO — versão 2 (reestruturação).

O QUE MUDOU EM RELAÇÃO À VERSÃO ANTERIOR (v11.2):
  1. Recebimentos deixaram de ser um campo acumulado ("valor_recebido" na
     encomenda) e passaram a ser LANÇAMENTOS INDIVIDUAIS E DATADOS, na nova
     coleção "recebimentos". Isso é o que permite reconciliação bancária e
     fechamento de caixa corretos. O campo "valor_recebido" na encomenda
     continua existindo e sendo atualizado (para não quebrar outras telas
     que leem esse campo), mas ele é apenas um CACHE — a fonte de verdade
     passa a ser a soma dos registros em "recebimentos".
  2. Nova aba "🚀 Lançamento Rápido": um único lugar para lançar qualquer
     entrada ou saída de dinheiro (pedido ou avulso), com um clique.
  3. Nova aba "🔒 Fechamento & Conciliação": fecha o caixa do mês, confronta
     lançamento por lançamento com o extrato bancário, e guarda o saldo
     final — que se torna automaticamente o saldo inicial do mês seguinte.
  4. O card "💵 Saldo em Caixa Atual" no topo agora é real: saldo herdado do
     último fechamento + tudo que entrou/saiu de dinheiro pago desde então.
  5. Gastos ganharam o campo "conciliado" (0/1), usado na conciliação.

[v3] Baseado no modelo de Relatório Mensal de Contas usado como referência
(estrutura em letras a→k):
  6. Nova aba "📈 Projeção": mostra o que ainda vai entrar e sair de um mês
     específico (padrão: o mês seguinte), e o Lucro Projetado resultante —
     sem misturar com o que já é fato consumado (Lucro Real).
  7. Novo conceito "🎯 Grande Despesa Prevista": um gasto grande já esperado
     (campo "grande_despesa_prevista" em lila_gastos) fica reservado — some
     do "saldo bruto" para mostrar o "(k) Fundos realmente disponíveis" —
     e continua visível mês a mês até ser pago, não se perde no fechamento.
  8. O fechamento agora segue a estrutura letrada do modelo: (a) saldo
     inicial, (d) entradas, (g) saídas, (h) lucro real do mês, (i) saldo
     final, (j) grandes despesas previstas, (k) fundos disponíveis.
  9. Fechar o mês agora avança automaticamente para o mês seguinte (fluxo
     em esteira) e permite baixar (Excel) o fechamento de qualquer mês.

Requisitos em database.py — todas as funções usadas aqui (recebimentos_*,
fechamento_*, fechamentos_listar) já estão no database.py entregue
anteriormente. Nenhuma coleção nova é necessária para esta versão — apenas
o campo opcional "grande_despesa_prevista" dentro de "lila_gastos".

Ponto de entrada: `renderizar_financeiro(df_enc_all, hoje_dt)`
  - df_enc_all: DataFrame de encomendas ativas (não canceladas).
  - hoje_dt: data de hoje (date), no fuso de Brasília.
"""

import io

import pandas as pd
import streamlit as st
import xlsxwriter

from database import (
    cfg_get,
    encomendas_atualizar,
    encomendas_listar,
    fechamento_buscar,
    fechamento_salvar,
    fechamentos_listar,
    gastos_atualizar,
    gastos_deletar,
    gastos_inserir,
    gastos_listar,
    recebimentos_atualizar,
    recebimentos_deletar,
    recebimentos_inserir,
    recebimentos_listar,
)
from modulos.utils import (
    CAT_GASTOS,
    MESES_PT,
    agora_br,
    brl,
    formatar_data_br,
    formatar_data_hora_br,
    hoje_brasilia,
    pct_str,
)

CAT_RECEITAS = ["Venda de peça", "Sinal/Entrada", "Aula/Consultoria", "Reembolso recebido", "Outro"]
FORMAS_PAGAMENTO = ["Pix", "Dinheiro", "Cartão de Débito", "Cartão de Crédito", "Transferência", "Boleto"]


# ── HELPERS DE CÁLCULO ────────────────────────────────────────────────────

def _flt(df, col, default=0.0):
    if df.empty or col not in df.columns:
        return default
    return float(df[col].fillna(0).astype(float).sum())


def _mes_de(data_iso: str) -> str:
    """Extrai 'YYYY-MM' de uma string de data isoformat. String vazia/None -> ''."""
    if not data_iso:
        return ""
    return str(data_iso)[:7]


def _ultimo_fechamento(df_fech: pd.DataFrame):
    """Retorna (dict do último mês FECHADO, ou None)."""
    if df_fech.empty or "fechado" not in df_fech.columns:
        return None
    fechados = df_fech[df_fech["fechado"].astype(int) == 1].copy()
    if fechados.empty:
        return None
    fechados = fechados.sort_values("mes", ascending=False)
    return fechados.iloc[0].to_dict()


def _mes_seguinte(mes_str: str) -> str:
    """'2026-03' -> '2026-04'."""
    ts = pd.Timestamp(f"{mes_str}-01") + pd.DateOffset(months=1)
    return ts.strftime("%Y-%m")


def _grandes_despesas_previstas(df_gastos: pd.DataFrame) -> pd.DataFrame:
    """
    Despesas grandes já esperadas, ainda não pagas, com fundos reservados.
    Não são filtradas por mês — ficam "rolando" de um mês para o outro até
    serem pagas (mesma lógica do campo (j) do Relatório Mensal de Contas
    usado como modelo: "Grandes Despesas Previstas").
    """
    if df_gastos.empty or "grande_despesa_prevista" not in df_gastos.columns:
        return pd.DataFrame()
    df = df_gastos[
        (df_gastos["pago"].astype(int) == 0)
        & (df_gastos["grande_despesa_prevista"].fillna(0).astype(int) == 1)
    ].copy()
    return df


def _saldo_em_caixa(df_receb: pd.DataFrame, df_gastos: pd.DataFrame, df_fech: pd.DataFrame):
    """
    Saldo real de caixa hoje = saldo herdado do último mês fechado
    + recebimentos posteriores a esse fechamento
    - gastos pagos posteriores a esse fechamento.

    Se nunca houve fechamento, considera o histórico completo (saldo herdado = 0).
    """
    ult = _ultimo_fechamento(df_fech)
    mes_corte = ult["mes"] if ult else None
    saldo_herdado = float(ult["saldo_final"]) if ult else 0.0

    if not df_receb.empty:
        receb_pos = df_receb[df_receb["data"].apply(_mes_de) > mes_corte] if mes_corte else df_receb
        total_receb_pos = _flt(receb_pos, "valor")
    else:
        total_receb_pos = 0.0

    if not df_gastos.empty:
        pagos = df_gastos[df_gastos["pago"].astype(int) == 1]
        pagos_pos = pagos[pagos["data"].apply(_mes_de) > mes_corte] if mes_corte else pagos
        total_gastos_pos = _flt(pagos_pos, "valor")
    else:
        total_gastos_pos = 0.0

    saldo_atual = saldo_herdado + total_receb_pos - total_gastos_pos
    return saldo_atual, mes_corte, saldo_herdado


def renderizar_financeiro(df_enc_all: pd.DataFrame, hoje_dt):
    """Renderiza o BLOCO FINANCEIRO completo."""
    st.markdown("## 💰 Financeiro")
    st.markdown("### 💰 Controle Financeiro Profissional")

    df_enc_fin = df_enc_all
    df_g_fin   = gastos_listar()
    df_r_fin   = recebimentos_listar()
    df_f_fin   = fechamentos_listar()

    receita_total    = _flt(df_r_fin, "valor")
    receita_prevista = float(df_enc_fin[df_enc_fin["etapa"].astype(int) < 7]["valor_total"].fillna(0).astype(float).sum()) if not df_enc_fin.empty else 0.0
    gastos_pagos     = float(df_g_fin[df_g_fin["pago"].astype(int) == 1]["valor"].fillna(0).astype(float).sum()) if not df_g_fin.empty else 0.0
    gastos_previstos = float(df_g_fin[df_g_fin["pago"].astype(int) == 0]["valor"].fillna(0).astype(float).sum()) if not df_g_fin.empty else 0.0
    lucro_real       = receita_total - gastos_pagos
    lucro_previsto   = (receita_total + receita_prevista) - (gastos_pagos + gastos_previstos)

    saldo_caixa_atual, mes_corte_fech, saldo_herdado = _saldo_em_caixa(df_r_fin, df_g_fin, df_f_fin)

    pct_reserva   = int(cfg_get("reserva_emergencia_meses") or 3)
    pct_capital   = float(cfg_get("capital_giro_pct") or 20) / 100
    margem_min    = float(cfg_get("margem_minima_pct") or 30) / 100
    meta_fat_fin  = float(cfg_get("meta_faturamento") or 5000)

    reserva_sugerida = gastos_pagos * pct_reserva / 12 if gastos_pagos > 0 else gastos_previstos * pct_reserva
    capital_giro_sug = receita_total * pct_capital
    teto_gasto_mens  = (receita_total + receita_prevista) * (1 - margem_min) if (receita_total + receita_prevista) > 0 else 0

    # ── KPI de topo: agora com o Saldo em Caixa Atual em destaque ──
    col_sc, col_sc2 = st.columns([2, 3])
    with col_sc:
        st.markdown(f"""
        <div class="kcard" style="border:2px solid #3d1f10;">
          <div class="kcard-title" style="font-size:1.6rem;">💵 {brl(saldo_caixa_atual)}</div>
          <div class="kcard-sub">Saldo em Caixa Atual
            {f"(herdado do fechamento de {mes_corte_fech})" if mes_corte_fech else "(nenhum mês fechado ainda — considerando todo o histórico)"}
          </div>
        </div>""", unsafe_allow_html=True)
    with col_sc2:
        if not mes_corte_fech:
            st.markdown('<div class="fin-alerta">📌 Você ainda não fez nenhum fechamento de caixa. Vá até a aba "🔒 Fechamento &amp; Conciliação" e feche o primeiro mês para começar a ter um saldo confiável de arrastar entre os meses.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="fin-ok">✅ Último mês fechado: <b>{mes_corte_fech}</b>, com saldo final de <b>{brl(saldo_herdado)}</b>. Tudo lançado depois disso já está somado ao saldo acima.</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    col_f1.metric("💰 Receita Recebida", brl(receita_total))
    col_f2.metric("📉 Gastos Pagos",     brl(gastos_pagos))
    col_f3.metric("✅ Lucro Real",        brl(lucro_real),
                  delta=f"{pct_str(lucro_real, receita_total)} de margem" if receita_total > 0 else "")
    col_f4.metric("🔮 Lucro Previsto",   brl(lucro_previsto))

    prog_fat = min(receita_total / meta_fat_fin, 1.0) if meta_fat_fin > 0 else 0
    st.progress(prog_fat, text=f"Faturamento: {brl(receita_total)} / {brl(meta_fat_fin)} (meta)")
    st.markdown("<br>", unsafe_allow_html=True)

    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        st.markdown("#### 💡 Capital de Giro")
        st.markdown(f'<div class="kcard"><div class="kcard-title">{brl(capital_giro_sug)}</div><div class="kcard-sub">Sugestão: manter {int(pct_capital*100)}% da receita disponível.</div></div>', unsafe_allow_html=True)
        saldo_capital = lucro_real - capital_giro_sug
        if saldo_capital >= 0:
            st.markdown(f'<div class="fin-ok">✅ Capital de giro adequado. Sobram {brl(saldo_capital)}.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="fin-danger">⚠️ Faltam {brl(abs(saldo_capital))} para o capital mínimo.</div>', unsafe_allow_html=True)

    with col_h2:
        st.markdown("#### 🛡️ Reserva de Emergência")
        st.markdown(f'<div class="kcard"><div class="kcard-title">{brl(reserva_sugerida)}</div><div class="kcard-sub">Sugestão: {pct_reserva} meses de custos guardados.</div></div>', unsafe_allow_html=True)
        if lucro_real >= reserva_sugerida:
            st.markdown(f'<div class="fin-ok">✅ Reserva coberta pelo lucro acumulado.</div>', unsafe_allow_html=True)
        else:
            falta = reserva_sugerida - lucro_real
            st.markdown(f'<div class="fin-alerta">⚠️ Faltam {brl(falta)} para a reserva ideal.</div>', unsafe_allow_html=True)

    with col_h3:
        st.markdown("#### 🎯 Teto de Gastos")
        st.markdown(f'<div class="kcard"><div class="kcard-title">{brl(teto_gasto_mens)}</div><div class="kcard-sub">Para margem mínima de {int(margem_min*100)}%.</div></div>', unsafe_allow_html=True)
        if gastos_pagos <= teto_gasto_mens:
            st.markdown(f'<div class="fin-ok">✅ Dentro do limite. Margem de {brl(teto_gasto_mens - gastos_pagos)}.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="fin-danger">🚨 Gastos {brl(gastos_pagos - teto_gasto_mens)} acima do teto!</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    f_rapido, f_dash, f_proj, f_pedidos, f_fecha, f_relat = st.tabs([
        "🚀 Lançamento Rápido", "📊 Dashboard", "📈 Projeção",
        "💳 Pagamentos por Pedido", "🔒 Fechamento & Conciliação", "📋 Relatório Mensal",
    ])

    # ═══════════════════════════════════════════════════════════════════
    # ABA: LANÇAMENTO RÁPIDO
    # ═══════════════════════════════════════════════════════════════════
    with f_rapido:
        st.markdown("#### 🚀 Lançar Entrada ou Saída")
        tipo_lanc = st.radio("O que você quer lançar?", ["💰 Entrada (recebi dinheiro)", "📉 Saída (gastei dinheiro)"],
                              horizontal=True, key="tipo_lanc_rapido")

        df_enc_ativos = encomendas_listar(cancelado=False)
        enc_ativos_list = []
        if not df_enc_ativos.empty:
            enc_ativos_list = [
                (row["rowid"], f"#{row['rowid'][:6]} – {row['cliente']}: {row['peca']}")
                for _, row in df_enc_ativos[df_enc_ativos["etapa"].astype(int) < 7].iterrows()
            ]
        enc_list = ["— Nenhum (avulso / custo geral) —"] + [e[1] for e in enc_ativos_list]

        if tipo_lanc.startswith("💰"):
            with st.form("form_receb_rapido", clear_on_submit=True):
                c1, c2 = st.columns(2)
                r_desc = c1.text_input("Descrição *", placeholder="Ex: Sinal do vestido da Ana")
                r_val  = c2.number_input("Valor (R$) *", min_value=0.01, step=10.0, format="%.2f")
                c3, c4 = st.columns(2)
                r_cat  = c3.selectbox("Categoria", CAT_RECEITAS)
                r_data = c4.date_input("Data do recebimento", hoje_brasilia(), format="DD/MM/YYYY")
                r_forma = st.selectbox("Forma de pagamento", FORMAS_PAGAMENTO)
                r_enc_lbl = st.selectbox("Vincular a um pedido? (opcional)", enc_list)
                r_enc_id = None
                if r_enc_lbl != "— Nenhum (avulso / custo geral) —":
                    idx = enc_list.index(r_enc_lbl) - 1
                    r_enc_id = enc_ativos_list[idx][0]

                if st.form_submit_button("💾 Lançar Entrada", use_container_width=True, type="primary"):
                    if r_desc.strip() and r_val > 0:
                        recebimentos_inserir({
                            "encomenda_id": r_enc_id,
                            "descricao": r_desc.strip(),
                            "valor": r_val,
                            "categoria": r_cat,
                            "data": r_data.isoformat(),
                            "forma_pagamento": r_forma,
                            "conciliado": 0,
                            "criado_em": agora_br().isoformat(),
                        })
                        if r_enc_id:
                            enc_atual = df_enc_ativos[df_enc_ativos["rowid"] == r_enc_id].iloc[0]
                            novo_total_receb = float(enc_atual.get("valor_recebido", 0) or 0) + r_val
                            encomendas_atualizar(str(r_enc_id), {"valor_recebido": novo_total_receb})
                        st.success("✅ Entrada lançada!")
                        st.rerun()
                    else:
                        st.error("Preencha descrição e valor.")
        else:
            with st.form("form_gasto_rapido", clear_on_submit=True):
                c1, c2 = st.columns(2)
                g_desc = c1.text_input("Descrição *")
                g_val  = c2.number_input("Valor (R$) *", min_value=0.01, step=10.0, format="%.2f")
                c3, c4 = st.columns(2)
                g_cat  = c3.selectbox("Categoria", CAT_GASTOS)
                g_data = c4.date_input("Data", hoje_brasilia(), format="DD/MM/YYYY")
                c5, c6 = st.columns(2)
                g_pago  = c5.checkbox("Já foi pago?", value=True)
                g_recor = c6.checkbox("Gasto recorrente (mensal)?")
                g_grande = st.checkbox(
                    "🎯 É uma grande despesa prevista? (reservar fundos até o pagamento)",
                    value=False,
                    help='Use para gastos grandes já esperados mas que ainda vão acontecer (ex: aluguel de local para evento, compra de equipamento). Enquanto não for pago, ele aparece separado na aba "Fechamento" reservando parte do saldo, e continua visível mês a mês até você quitar.',
                )
                g_enc_lbl = st.selectbox("Vincular a pedido? (opcional)", enc_list, key="g_enc_rapido")
                g_enc_id = None
                if g_enc_lbl != "— Nenhum (avulso / custo geral) —":
                    idx = enc_list.index(g_enc_lbl) - 1
                    g_enc_id = enc_ativos_list[idx][0]

                if st.form_submit_button("💾 Lançar Saída", use_container_width=True, type="primary"):
                    if g_desc.strip() and g_val > 0:
                        gastos_inserir({
                            "encomenda_id": g_enc_id,
                            "descricao": g_desc.strip(), "valor": g_val,
                            "data": g_data.isoformat(), "categoria": g_cat,
                            "pago": 1 if g_pago else 0,
                            "recorrente": 1 if g_recor else 0,
                            "grande_despesa_prevista": 1 if g_grande else 0,
                            "conciliado": 0,
                            "criado_em": agora_br().isoformat(),
                        })
                        st.success("✅ Saída lançada!")
                        st.rerun()
                    else:
                        st.error("Preencha descrição e valor.")

        st.markdown("---")
        st.markdown("#### 🕘 Últimos lançamentos")
        col_ult1, col_ult2 = st.columns(2)
        with col_ult1:
            st.markdown("**Entradas recentes**")
            if df_r_fin.empty:
                st.info("Nenhum recebimento lançado ainda.")
            else:
                ult_r = df_r_fin.sort_values("data", ascending=False).head(8)
                for _, r in ult_r.iterrows():
                    st.markdown(f"- {formatar_data_br(r['data'])} — {r['descricao']} — **{brl(float(r['valor']))}**")
        with col_ult2:
            st.markdown("**Saídas recentes**")
            if df_g_fin.empty:
                st.info("Nenhum gasto lançado ainda.")
            else:
                ult_g = df_g_fin.sort_values("data", ascending=False).head(8)
                for _, g in ult_g.iterrows():
                    st.markdown(f"- {formatar_data_br(g['data'])} — {g['descricao']} — **{brl(float(g['valor']))}**")

    # ═══════════════════════════════════════════════════════════════════
    # ABA: DASHBOARD
    # ═══════════════════════════════════════════════════════════════════
    with f_dash:
        st.markdown("#### 📊 Visão Financeira Geral")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("**📥 Receitas por Status**")
            rec_pendente = (
                float(df_enc_fin[df_enc_fin["etapa"].astype(int) < 7]["valor_total"].fillna(0).astype(float).sum())
                - float(df_enc_fin[df_enc_fin["etapa"].astype(int) < 7]["valor_recebido"].fillna(0).astype(float).sum())
            ) if not df_enc_fin.empty else 0.0
            df_rec_chart = pd.DataFrame({
                "Categoria": ["Recebido", "Previsto (em andamento)", "A receber (saldo)"],
                "Valor": [receita_total, receita_prevista, rec_pendente],
            })
            st.bar_chart(df_rec_chart.set_index("Categoria"))

        with col_d2:
            st.markdown("**📤 Gastos por Categoria**")
            if not df_g_fin.empty and "categoria" in df_g_fin.columns:
                cat_group = df_g_fin.groupby("categoria")["valor"].sum().reset_index()
                cat_group.columns = ["Categoria","Valor"]
                st.bar_chart(cat_group.set_index("Categoria"))
            else:
                st.info("Nenhum gasto lançado.")

        st.markdown("---")
        st.markdown("**🔄 Fluxo de Caixa – Pedidos Ativos**")
        if not df_enc_fin.empty:
            pedidos_ativos = df_enc_fin[df_enc_fin["etapa"].astype(int) < 7].copy()
            if pedidos_ativos.empty:
                st.info("Nenhum pedido ativo.")
            else:
                pedidos_ativos["Saldo a Receber"] = pedidos_ativos["valor_total"].astype(float) - pedidos_ativos["valor_recebido"].astype(float)
                pedidos_ativos["Entrega"] = pedidos_ativos["data_entrega"].apply(formatar_data_br)
                df_fluxo = pedidos_ativos[["cliente","peca","valor_total","valor_recebido","Saldo a Receber","Entrega"]].copy()
                df_fluxo.columns = ["Cliente","Peça","Total","Recebido","A Receber","Entrega Prevista"]
                for c in ["Total","Recebido","A Receber"]:
                    df_fluxo[c] = df_fluxo[c].apply(lambda x: brl(float(x)))
                st.dataframe(df_fluxo, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("**📆 Contas a Pagar (em aberto)**")
        df_cp = df_g_fin[df_g_fin["pago"].astype(int) == 0].copy() if not df_g_fin.empty else pd.DataFrame()
        if df_cp.empty:
            st.success("✅ Nenhuma conta em aberto.")
        else:
            df_cp["Data"] = df_cp["data"].apply(formatar_data_br)
            df_cp_show = df_cp[["Data","descricao","categoria","valor"]].copy()
            df_cp_show.columns = ["Data","Descrição","Categoria","Valor"]
            df_cp_show["Valor"] = df_cp_show["Valor"].apply(lambda x: brl(float(x)))
            st.dataframe(df_cp_show, use_container_width=True, hide_index=True)
            st.markdown(f'<div class="fin-alerta">Total em aberto: <b>{brl(float(df_cp["valor"].sum()))}</b></div>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### 📋 Todos os Gastos")
        if df_g_fin.empty:
            st.info("Nenhum gasto registrado.")
        else:
            for _, g in df_g_fin.iterrows():
                status_g = "✅ Pago" if int(g.get("pago", 0) or 0) else "⏳ Em aberto"
                badge_g  = "badge-green" if int(g.get("pago", 0) or 0) else "badge-amber"
                lancado_em = g.get("criado_em")
                lancado_html = f" &nbsp;|&nbsp; 🕐 lançado em {formatar_data_hora_br(lancado_em)}" if lancado_em else ""
                conc_badge = "&nbsp;<span class='badge badge-blue'>🔗 conciliado</span>" if int(g.get("conciliado", 0) or 0) else ""
                col_gi, col_gb = st.columns([5, 1])
                col_gi.markdown(f"""
                <div class="kcard">
                  <div class="kcard-title">{g['descricao']} — <b>{brl(float(g.get('valor',0)))}</b></div>
                  <div class="kcard-sub">
                    📂 {g.get('categoria','')} &nbsp;|&nbsp; 📅 {formatar_data_br(g.get('data',''))}{lancado_html}
                    &nbsp;<span class="badge {badge_g}">{status_g}</span>
                    {"&nbsp;<span class='badge badge-blue'>🔁 Recorrente</span>" if int(g.get('recorrente', 0) or 0) else ""}
                    {conc_badge}
                  </div>
                </div>""", unsafe_allow_html=True)
                with col_gb:
                    st.write("")
                    if not int(g.get("pago", 0) or 0):
                        if st.button("💳 Quitar", key=f"qt_{g['rowid']}"):
                            gastos_atualizar(str(g["rowid"]), {"pago": 1})
                            st.rerun()
                    else:
                        if st.button("🗑️", key=f"del_g_{g['rowid']}", help="Remover"):
                            gastos_deletar(str(g["rowid"]))
                            st.rerun()

    # ═══════════════════════════════════════════════════════════════════
    # ABA: PROJEÇÃO
    # ═══════════════════════════════════════════════════════════════════
    with f_proj:
        st.markdown("#### 📈 Projeção de Lucro")
        st.caption("Baseado no que você já sabe que vai receber (pedidos em andamento) e no que já sabe que vai gastar (despesas previstas) — filtre o mês que quiser ver.")

        mes_atual_str = f"{hoje_dt.year}-{hoje_dt.month:02d}"
        mes_seguinte_str = _mes_seguinte(mes_atual_str)
        opcoes_mes_proj = [mes_atual_str, mes_seguinte_str, _mes_seguinte(mes_seguinte_str)]
        labels_mes_proj = {
            mes_atual_str: f"Mês atual ({MESES_PT[int(mes_atual_str[5:7])-1]}/{mes_atual_str[:4]})",
            mes_seguinte_str: f"Mês seguinte ({MESES_PT[int(mes_seguinte_str[5:7])-1]}/{mes_seguinte_str[:4]})",
            opcoes_mes_proj[2]: f"Depois ({MESES_PT[int(opcoes_mes_proj[2][5:7])-1]}/{opcoes_mes_proj[2][:4]})",
        }
        mes_proj_sel = st.selectbox(
            "Ver projeção de qual mês?", opcoes_mes_proj,
            format_func=lambda m: labels_mes_proj[m], index=1,  # padrão: mês seguinte
        )

        # Receita prevista do mês escolhido = saldo a receber de pedidos com entrega nesse mês
        if not df_enc_fin.empty and "data_entrega" in df_enc_fin.columns:
            pedidos_mes_proj = df_enc_fin[
                (df_enc_fin["etapa"].astype(int) < 7)
                & (df_enc_fin["data_entrega"].fillna("").apply(_mes_de) == mes_proj_sel)
            ].copy()
        else:
            pedidos_mes_proj = pd.DataFrame()

        rec_prevista_proj = 0.0
        if not pedidos_mes_proj.empty:
            pedidos_mes_proj["a_receber"] = pedidos_mes_proj["valor_total"].astype(float) - pedidos_mes_proj["valor_recebido"].astype(float)
            rec_prevista_proj = float(pedidos_mes_proj["a_receber"].clip(lower=0).sum())

        # Despesas previstas do mês escolhido = gastos em aberto com data nesse mês
        if not df_g_fin.empty:
            gastos_mes_proj = df_g_fin[
                (df_g_fin["pago"].astype(int) == 0)
                & (df_g_fin["data"].fillna("").apply(_mes_de) == mes_proj_sel)
            ].copy()
        else:
            gastos_mes_proj = pd.DataFrame()
        desp_prevista_proj = _flt(gastos_mes_proj, "valor")

        lucro_projetado = rec_prevista_proj - desp_prevista_proj
        saldo_projetado_fim_mes = saldo_caixa_atual + lucro_projetado

        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        col_p1.metric("📥 A receber no mês", brl(rec_prevista_proj))
        col_p2.metric("📤 A pagar no mês", brl(desp_prevista_proj))
        col_p3.metric("🔮 Lucro Projetado", brl(lucro_projetado))
        col_p4.metric("💵 Saldo projetado ao fim do mês", brl(saldo_projetado_fim_mes))

        st.caption("\"Saldo projetado\" parte do Saldo em Caixa Atual de hoje e soma o lucro projetado do mês escolhido — é uma estimativa, assumindo que tudo que está previsto realmente vai entrar/sair.")

        st.markdown("---")
        col_pp1, col_pp2 = st.columns(2)
        with col_pp1:
            st.markdown("**Pedidos que geram essa receita prevista**")
            if pedidos_mes_proj.empty:
                st.info("Nenhum pedido com entrega prevista neste mês.")
            else:
                df_pp = pedidos_mes_proj[["cliente", "peca", "a_receber", "data_entrega"]].copy()
                df_pp.columns = ["Cliente", "Peça", "A Receber", "Entrega"]
                df_pp["Entrega"] = df_pp["Entrega"].apply(formatar_data_br)
                df_pp["A Receber"] = df_pp["A Receber"].apply(lambda x: brl(float(x)))
                st.dataframe(df_pp, use_container_width=True, hide_index=True)
        with col_pp2:
            st.markdown("**Despesas previstas para o mês**")
            if gastos_mes_proj.empty:
                st.info("Nenhuma despesa em aberto com vencimento neste mês.")
            else:
                df_gp = gastos_mes_proj[["descricao", "categoria", "valor"]].copy()
                df_gp.columns = ["Descrição", "Categoria", "Valor"]
                df_gp["Valor"] = df_gp["Valor"].apply(lambda x: brl(float(x)))
                st.dataframe(df_gp, use_container_width=True, hide_index=True)

    # ═══════════════════════════════════════════════════════════════════
    # ABA: PAGAMENTOS POR PEDIDO
    # ═══════════════════════════════════════════════════════════════════
    with f_pedidos:
        st.markdown("#### 💳 Gestão de Pagamentos por Pedido")
        if df_enc_fin.empty:
            st.info("Nenhum pedido cadastrado.")
        else:
            for _, enc in df_enc_fin.iterrows():
                v_total_e  = float(enc.get("valor_total", 0) or 0)
                v_recebido = float(enc.get("valor_recebido", 0) or 0)
                v_restante = v_total_e - v_recebido

                gasto_enc = 0.0
                if not df_g_fin.empty and "encomenda_id" in df_g_fin.columns:
                    gasto_enc = float(df_g_fin[df_g_fin["encomenda_id"] == enc["rowid"]]["valor"].fillna(0).astype(float).sum())
                lucro_enc  = v_recebido - gasto_enc
                margem_enc = lucro_enc / v_recebido * 100 if v_recebido > 0 else 0
                margem_min_val = float(cfg_get("margem_minima_pct") or 30)

                with st.expander(
                    f"👗 {enc['cliente']} – {enc['peca']}  |  "
                    f"Recebido: {brl(v_recebido)} / {brl(v_total_e)}  |  Margem: {margem_enc:.0f}%"
                ):
                    col_pm1, col_pm2, col_pm3, col_pm4 = st.columns(4)
                    col_pm1.metric("Valor Total",  brl(v_total_e))
                    col_pm2.metric("Recebido",     brl(v_recebido))
                    col_pm3.metric("A Receber",    brl(max(v_restante, 0)))
                    col_pm4.metric("Custo Direto", brl(gasto_enc))

                    if margem_enc >= margem_min_val:
                        st.markdown(f'<div class="fin-ok">✅ Margem de <b>{margem_enc:.1f}%</b> — saudável.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="fin-danger">🚨 Margem de <b>{margem_enc:.1f}%</b> abaixo do mínimo ({margem_min_val:.0f}%).</div>', unsafe_allow_html=True)

                    if v_restante > 0.01:
                        col_rec1, col_rec2, col_rec3 = st.columns([2, 2, 1])
                        novo_val = col_rec1.number_input(
                            "Valor recebido agora (R$)",
                            min_value=0.01, max_value=float(v_restante + 0.01),
                            value=float(v_restante), step=10.0, format="%.2f",
                            key=f"rec_val_{enc['rowid']}",
                        )
                        forma_rec = col_rec2.selectbox("Forma de pagamento", FORMAS_PAGAMENTO, key=f"forma_{enc['rowid']}")
                        if col_rec3.button("✅ Confirmar", key=f"rec_btn_{enc['rowid']}"):
                            recebimentos_inserir({
                                "encomenda_id": str(enc["rowid"]),
                                "descricao": f"Pagamento – {enc['cliente']}: {enc['peca']}",
                                "valor": novo_val,
                                "categoria": "Venda de peça",
                                "data": hoje_brasilia().isoformat(),
                                "forma_pagamento": forma_rec,
                                "conciliado": 0,
                                "criado_em": agora_br().isoformat(),
                            })
                            novo_total = v_recebido + novo_val
                            encomendas_atualizar(str(enc["rowid"]), {"valor_recebido": novo_total})
                            st.success(f"✅ {brl(novo_val)} registrado!")
                            st.rerun()

                        if st.button(f"💰 Quitar saldo total ({brl(v_restante)})", key=f"quit_total_{enc['rowid']}"):
                            recebimentos_inserir({
                                "encomenda_id": str(enc["rowid"]),
                                "descricao": f"Quitação – {enc['cliente']}: {enc['peca']}",
                                "valor": v_restante,
                                "categoria": "Venda de peça",
                                "data": hoje_brasilia().isoformat(),
                                "forma_pagamento": "Pix",
                                "conciliado": 0,
                                "criado_em": agora_br().isoformat(),
                            })
                            encomendas_atualizar(str(enc["rowid"]), {"valor_recebido": v_total_e})
                            st.rerun()
                    else:
                        st.markdown('<div class="fin-ok">✅ Pedido totalmente pago.</div>', unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════
    # ABA: FECHAMENTO & CONCILIAÇÃO
    # ═══════════════════════════════════════════════════════════════════
    with f_fecha:
        st.markdown("#### 🔒 Fechamento de Caixa & Conciliação Bancária")
        st.caption("Confira, mês a mês, se tudo que está no sistema bate com o extrato do banco — e trave o saldo do mês pra ele virar automaticamente o saldo inicial do mês seguinte.")

        col_fm1, col_fm2 = st.columns(2)
        mes_sel = col_fm1.selectbox("Mês", list(range(1, 13)),
            format_func=lambda x: MESES_PT[x-1], index=hoje_dt.month-1, key="mes_fechamento")
        ano_sel = col_fm2.number_input("Ano", min_value=2020, max_value=2030, value=hoje_dt.year, key="ano_fechamento")
        mes_str = f"{ano_sel}-{mes_sel:02d}"

        fech_existente = fechamento_buscar(mes_str)
        ja_fechado = bool(fech_existente and int(fech_existente.get("fechado", 0) or 0) == 1)

        # saldo inicial: vem do fechamento do mês anterior (se existir e estiver fechado)
        mes_ant_dt = pd.Timestamp(year=int(ano_sel), month=int(mes_sel), day=1) - pd.DateOffset(months=1)
        mes_ant_str = mes_ant_dt.strftime("%Y-%m")
        fech_ant = fechamento_buscar(mes_ant_str)
        saldo_inicial_sugerido = float(fech_ant["saldo_final"]) if (fech_ant and int(fech_ant.get("fechado", 0) or 0) == 1) else 0.0

        if fech_existente:
            saldo_inicial = float(fech_existente.get("saldo_inicial", saldo_inicial_sugerido))
        else:
            saldo_inicial = saldo_inicial_sugerido

        if not fech_ant and mes_ant_str not in ("", None):
            st.info(f"📌 Não há fechamento do mês anterior ({mes_ant_str}). Se este for o primeiro mês que você está controlando, ajuste o saldo inicial manualmente abaixo (ex: o que você tem hoje na conta/caixa).")

        saldo_inicial = st.number_input("(a) Saldo inicial do mês (herdado do fechamento anterior)", value=float(saldo_inicial), step=10.0, format="%.2f", disabled=ja_fechado)

        df_r_mes = df_r_fin[df_r_fin["data"].apply(_mes_de) == mes_str].copy() if not df_r_fin.empty else pd.DataFrame()
        df_g_mes = df_g_fin[(df_g_fin["data"].apply(_mes_de) == mes_str) & (df_g_fin["pago"].astype(int) == 1)].copy() if not df_g_fin.empty else pd.DataFrame()

        receitas_mes = _flt(df_r_mes, "valor")
        despesas_mes = _flt(df_g_mes, "valor")
        lucro_real_mes = receitas_mes - despesas_mes           # (h)
        saldo_teorico = saldo_inicial + lucro_real_mes          # (i)

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        col_r1.metric("(d) Entradas do mês", brl(receitas_mes))
        col_r2.metric("(g) Saídas do mês (pagas)", brl(despesas_mes))
        col_r3.metric("(h) = Lucro Real do mês", brl(lucro_real_mes))
        col_r4.metric("(i) = Saldo final do mês", brl(saldo_teorico))
        st.caption("Lucro Real (h) só conta o que já foi de fato recebido e pago neste mês — é diferente do Lucro Projetado da aba \"📈 Projeção\", que inclui o que ainda está previsto.")

        # ── (j) Grandes Despesas Previstas — fundos reservados, rolam de mês a mês ──
        st.markdown("---")
        st.markdown("##### 🎯 Grandes Despesas Previstas (fundos reservados)")
        st.caption("Despesas grandes já esperadas mas ainda não pagas — ficam aqui até serem quitadas, não importa o mês. Elas reservam parte do seu saldo para você não gastar esse dinheiro por engano em outra coisa.")
        df_grandes = _grandes_despesas_previstas(df_g_fin)
        total_grandes = _flt(df_grandes, "valor")
        fundos_disponiveis = saldo_teorico - total_grandes

        if df_grandes.empty:
            st.info("Nenhuma grande despesa prevista em aberto no momento.")
        else:
            for _, gd in df_grandes.sort_values("data").iterrows():
                col_gd1, col_gd2 = st.columns([5, 1])
                col_gd1.markdown(f"- {formatar_data_br(gd['data'])} — **{gd['descricao']}** — {brl(float(gd['valor']))}")
                if col_gd2.button("✅ Já paguei", key=f"pagar_grande_{gd['rowid']}"):
                    gastos_atualizar(str(gd["rowid"]), {"pago": 1})
                    st.rerun()

        col_j, col_k = st.columns(2)
        col_j.metric("(j) Total reservado", brl(total_grandes))
        col_k.metric("(k) = Fundos realmente disponíveis", brl(fundos_disponiveis),
                     help="(i) Saldo final do mês menos (j) o que já está reservado para as grandes despesas previstas.")
        if fundos_disponiveis < 0:
            st.markdown(f'<div class="fin-danger">⚠️ O saldo não cobre todas as grandes despesas reservadas — faltam {brl(abs(fundos_disponiveis))}.</div>', unsafe_allow_html=True)

        with st.expander("➕ Lançar nova grande despesa prevista"):
            with st.form("form_grande_despesa", clear_on_submit=True):
                cg1, cg2 = st.columns(2)
                gg_desc = cg1.text_input("Descrição *", placeholder="Ex: Aluguel do espaço para o desfile de fim de ano")
                gg_val  = cg2.number_input("Valor (R$) *", min_value=0.01, step=50.0, format="%.2f")
                gg_data = st.date_input("Data prevista", hoje_brasilia(), format="DD/MM/YYYY")
                if st.form_submit_button("💾 Reservar", use_container_width=True, type="primary"):
                    if gg_desc.strip() and gg_val > 0:
                        gastos_inserir({
                            "encomenda_id": None,
                            "descricao": gg_desc.strip(), "valor": gg_val,
                            "data": gg_data.isoformat(), "categoria": "Grande despesa prevista",
                            "pago": 0, "recorrente": 0,
                            "grande_despesa_prevista": 1,
                            "conciliado": 0,
                            "criado_em": agora_br().isoformat(),
                        })
                        st.success("✅ Reservado!")
                        st.rerun()
                    else:
                        st.error("Preencha descrição e valor.")

        st.markdown("---")
        st.markdown("##### ✅ Conferência com o extrato bancário")
        st.caption("Marque cada lançamento conforme você for conferindo linha por linha com o extrato do banco.")

        total_itens = len(df_r_mes) + len(df_g_mes)
        conc_itens = 0
        if not df_r_mes.empty:
            conc_itens += int(df_r_mes["conciliado"].fillna(0).astype(int).sum())
        if not df_g_mes.empty:
            conc_itens += int(df_g_mes["conciliado"].fillna(0).astype(int).sum())
        st.progress(conc_itens / total_itens if total_itens else 0, text=f"{conc_itens} de {total_itens} lançamentos conferidos")

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.markdown("**Entradas**")
            if df_r_mes.empty:
                st.info("Nenhuma entrada neste mês.")
            else:
                for _, r in df_r_mes.sort_values("data").iterrows():
                    marcado = st.checkbox(
                        f"{formatar_data_br(r['data'])} — {r['descricao']} — {brl(float(r['valor']))}",
                        value=bool(int(r.get("conciliado", 0) or 0)),
                        key=f"conc_r_{r['rowid']}",
                        disabled=ja_fechado,
                    )
                    if marcado != bool(int(r.get("conciliado", 0) or 0)) and not ja_fechado:
                        recebimentos_atualizar(str(r["rowid"]), {"conciliado": 1 if marcado else 0})
                        st.rerun()
        with col_c2:
            st.markdown("**Saídas**")
            if df_g_mes.empty:
                st.info("Nenhuma saída paga neste mês.")
            else:
                for _, g in df_g_mes.sort_values("data").iterrows():
                    marcado = st.checkbox(
                        f"{formatar_data_br(g['data'])} — {g['descricao']} — {brl(float(g['valor']))}",
                        value=bool(int(g.get("conciliado", 0) or 0)),
                        key=f"conc_g_{g['rowid']}",
                        disabled=ja_fechado,
                    )
                    if marcado != bool(int(g.get("conciliado", 0) or 0)) and not ja_fechado:
                        gastos_atualizar(str(g["rowid"]), {"conciliado": 1 if marcado else 0})
                        st.rerun()

        st.markdown("---")
        st.markdown("##### 🏦 Confronto final com o saldo do banco")
        saldo_extrato = st.number_input(
            "Saldo que aparece no extrato bancário no último dia do mês (R$)",
            value=float(fech_existente.get("saldo_extrato_informado", saldo_teorico)) if fech_existente and fech_existente.get("saldo_extrato_informado") is not None else float(saldo_teorico),
            step=10.0, format="%.2f", disabled=ja_fechado,
        )
        diferenca = saldo_teorico - saldo_extrato
        if abs(diferenca) < 0.01:
            st.markdown('<div class="fin-ok">✅ Bateu certinho! O saldo do sistema é igual ao do extrato.</div>', unsafe_allow_html=True)
        else:
            sinal = "a mais no sistema do que no banco" if diferenca > 0 else "a mais no banco do que no sistema"
            st.markdown(f'<div class="fin-danger">⚠️ Diferença de <b>{brl(abs(diferenca))}</b> ({sinal}). Confira se falta algum lançamento, se houve tarifa bancária, ou lançamento duplicado antes de fechar.</div>', unsafe_allow_html=True)

        observacoes = st.text_area("Observações do fechamento (opcional)",
                                    value=fech_existente.get("observacoes", "") if fech_existente else "",
                                    disabled=ja_fechado)

        if ja_fechado:
            st.success(f"🔒 Mês {mes_str} já está FECHADO (fechamento em {formatar_data_hora_br(fech_existente.get('data_fechamento'))}). Saldo final (i): {brl(float(fech_existente.get('saldo_final', 0)))} — Fundos disponíveis (k): {brl(float(fech_existente.get('fundos_disponiveis', fech_existente.get('saldo_final', 0))))}")
            col_reab, col_avc = st.columns(2)
            if col_reab.button("🔓 Reabrir este mês (usar apenas para corrigir erro)", key="reabrir_mes", use_container_width=True):
                fechamento_salvar(mes_str, {"fechado": 0})
                st.warning("Mês reaberto. Os valores voltaram a ser editáveis.")
                st.rerun()
            if col_avc.button("➡️ Ir para o próximo mês", key="ir_prox_mes", use_container_width=True):
                prox = _mes_seguinte(mes_str)
                st.session_state["mes_fechamento"] = int(prox[5:7])
                st.session_state["ano_fechamento"] = int(prox[:4])
                st.rerun()
        else:
            pode_fechar = total_itens == 0 or conc_itens == total_itens
            if not pode_fechar:
                st.warning("⚠️ Ainda existem lançamentos não conferidos. Recomendado conferir tudo antes de fechar — mas se precisar, pode fechar mesmo assim registrando o motivo nas observações.")
            if st.button("🔒 Fechar Mês e Avançar para o Próximo ➡️", type="primary", use_container_width=True):
                saldo_final_oficial = saldo_extrato if abs(diferenca) >= 0.01 else saldo_teorico
                fundos_disp_oficial = saldo_final_oficial - total_grandes
                fechamento_salvar(mes_str, {
                    "mes": mes_str,
                    "saldo_inicial": saldo_inicial,
                    "receitas_mes": receitas_mes,
                    "despesas_mes": despesas_mes,
                    "lucro_real_mes": lucro_real_mes,
                    "saldo_final": saldo_final_oficial,
                    "grandes_despesas_previstas": total_grandes,
                    "fundos_disponiveis": fundos_disp_oficial,
                    "saldo_extrato_informado": saldo_extrato,
                    "diferenca": diferenca,
                    "fechado": 1,
                    "observacoes": observacoes,
                    "data_fechamento": agora_br().isoformat(),
                    "atualizado_em": agora_br().isoformat(),
                })
                prox = _mes_seguinte(mes_str)
                st.session_state["mes_fechamento"] = int(prox[5:7])
                st.session_state["ano_fechamento"] = int(prox[:4])
                st.success(f"✅ Mês {mes_str} fechado! Saldo final de {brl(saldo_final_oficial)} vira o saldo inicial de {prox}. Indo para o próximo mês...")
                st.rerun()

        # ── Download do fechamento (funciona pra mês fechado ou em edição) ──
        st.markdown("---")
        buf_fech = io.BytesIO()
        wb_fech = xlsxwriter.Workbook(buf_fech)
        fmt_h_fech = wb_fech.add_format({"bold": True, "bg_color": "#3d1f10", "font_color": "white", "border": 1})
        fmt_brl_fech = wb_fech.add_format({"num_format": "R$ #,##0.00", "border": 1})
        fmt_n_fech = wb_fech.add_format({"border": 1})
        ws_fech = wb_fech.add_worksheet("Fechamento")
        ws_fech.set_column(0, 0, 45)
        ws_fech.set_column(1, 1, 18)
        ws_fech.write(0, 0, f"Fechamento de Caixa — {mes_str}", wb_fech.add_format({"bold": True, "font_size": 14, "font_color": "#3d1f10"}))
        linhas_fech = [
            ("(a) Saldo inicial do mês", saldo_inicial),
            ("(d) Entradas do mês", receitas_mes),
            ("(g) Saídas do mês (pagas)", despesas_mes),
            ("(h) Lucro Real do mês [(d) - (g)]", lucro_real_mes),
            ("(i) Saldo final do mês [(a) + (h)]", saldo_teorico if not ja_fechado else float(fech_existente.get("saldo_final", saldo_teorico))),
            ("(j) Grandes despesas previstas (reservado)", total_grandes),
            ("(k) Fundos realmente disponíveis [(i) - (j)]", fundos_disponiveis if not ja_fechado else float(fech_existente.get("fundos_disponiveis", fundos_disponiveis))),
        ]
        for ri, (label, val) in enumerate(linhas_fech, 2):
            ws_fech.write(ri, 0, label, fmt_n_fech)
            ws_fech.write(ri, 1, float(val), fmt_brl_fech)
        r0 = len(linhas_fech) + 4
        ws_fech.write(r0, 0, "Entradas do mês (detalhado)", fmt_h_fech)
        ws_fech.write(r0, 1, "Valor", fmt_h_fech)
        for i, (_, r) in enumerate(df_r_mes.sort_values("data").iterrows(), 1):
            ws_fech.write(r0 + i, 0, f"{formatar_data_br(r['data'])} — {r['descricao']}", fmt_n_fech)
            ws_fech.write(r0 + i, 1, float(r["valor"]), fmt_brl_fech)
        r1 = r0 + len(df_r_mes) + 3
        ws_fech.write(r1, 0, "Saídas do mês (detalhado)", fmt_h_fech)
        ws_fech.write(r1, 1, "Valor", fmt_h_fech)
        for i, (_, g) in enumerate(df_g_mes.sort_values("data").iterrows(), 1):
            ws_fech.write(r1 + i, 0, f"{formatar_data_br(g['data'])} — {g['descricao']}", fmt_n_fech)
            ws_fech.write(r1 + i, 1, float(g["valor"]), fmt_brl_fech)
        wb_fech.close()
        buf_fech.seek(0)
        st.download_button(
            label=f"📥 Baixar Fechamento de {mes_str} (Excel)",
            data=buf_fech,
            file_name=f"Lila_Fechamento_{mes_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.markdown("---")
        st.markdown("##### 🗓️ Histórico de fechamentos")
        if df_f_fin.empty:
            st.info("Nenhum mês fechado ainda.")
        else:
            df_hist = df_f_fin[df_f_fin["fechado"].astype(int) == 1].sort_values("mes", ascending=False).copy()
            if df_hist.empty:
                st.info("Nenhum mês fechado ainda.")
            else:
                if "fundos_disponiveis" not in df_hist.columns:
                    df_hist["fundos_disponiveis"] = df_hist["saldo_final"]
                df_hist_show = df_hist[["mes","saldo_inicial","receitas_mes","despesas_mes","saldo_final","fundos_disponiveis"]].copy()
                df_hist_show.columns = ["Mês","(a) Saldo Inicial","(d) Entradas","(g) Saídas","(i) Saldo Final","(k) Fundos Disponíveis"]
                for c in ["(a) Saldo Inicial","(d) Entradas","(g) Saídas","(i) Saldo Final","(k) Fundos Disponíveis"]:
                    df_hist_show[c] = df_hist_show[c].fillna(0).apply(lambda x: brl(float(x)))
                st.dataframe(df_hist_show, use_container_width=True, hide_index=True)

    # ═══════════════════════════════════════════════════════════════════
    # ABA: RELATÓRIO MENSAL
    # ═══════════════════════════════════════════════════════════════════
    with f_relat:
        st.markdown("#### 📋 Relatório Financeiro Mensal")
        col_rm1, col_rm2 = st.columns(2)
        mes_sel_fin = col_rm1.selectbox("Mês", list(range(1,13)),
            format_func=lambda x: MESES_PT[x-1], index=hoje_dt.month-1, key="mes_rel_fin")
        ano_sel_fin = col_rm2.number_input("Ano", min_value=2020, max_value=2030, value=hoje_dt.year, key="ano_rel_fin")

        mes_str_rel = f"{ano_sel_fin}-{mes_sel_fin:02d}"

        df_r_mes_rel = df_r_fin[df_r_fin["data"].apply(_mes_de) == mes_str_rel].copy() if not df_r_fin.empty else pd.DataFrame()
        df_g_mes_rel = df_g_fin[df_g_fin["data"].apply(_mes_de) == mes_str_rel].copy() if not df_g_fin.empty else pd.DataFrame()

        rec_mes   = _flt(df_r_mes_rel, "valor")
        gasto_mes = float(df_g_mes_rel[df_g_mes_rel["pago"].astype(int) == 1]["valor"].fillna(0).astype(float).sum()) if not df_g_mes_rel.empty else 0.0
        lucro_mes = rec_mes - gasto_mes
        margem_mes = lucro_mes / rec_mes * 100 if rec_mes > 0 else 0

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        col_r1.metric("Receita do Mês", brl(rec_mes))
        col_r2.metric("Gastos do Mês",  brl(gasto_mes))
        col_r3.metric("Lucro Líquido",  brl(lucro_mes))
        col_r4.metric("Margem",         f"{margem_mes:.1f}%")

        meta_fat_f = float(cfg_get("meta_faturamento") or 5000)
        if rec_mes >= meta_fat_f:
            st.markdown(f'<div class="fin-ok">🏆 Meta de {brl(meta_fat_f)} atingida!</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="fin-alerta">📌 Faltam {brl(meta_fat_f - rec_mes)} para a meta de {brl(meta_fat_f)}.</div>', unsafe_allow_html=True)

        st.markdown("---")
        col_rt1, col_rt2 = st.columns(2)
        with col_rt1:
            st.markdown("**Entradas do mês**")
            if df_r_mes_rel.empty:
                st.info("Nenhuma entrada neste mês.")
            else:
                df_em = df_r_mes_rel[["descricao","categoria","valor","forma_pagamento"]].copy()
                df_em.columns = ["Descrição","Categoria","Valor","Forma"]
                df_em["Valor"] = df_em["Valor"].apply(lambda x: brl(float(x)))
                st.dataframe(df_em, use_container_width=True, hide_index=True)

        with col_rt2:
            st.markdown("**Gastos do mês**")
            if df_g_mes_rel.empty:
                st.info("Nenhum gasto registrado neste mês.")
            else:
                df_gm = df_g_mes_rel[["descricao","categoria","valor","pago"]].copy()
                df_gm.columns = ["Descrição","Categoria","Valor","Pago?"]
                df_gm["Valor"] = df_gm["Valor"].apply(lambda x: brl(float(x)))
                df_gm["Pago?"] = df_gm["Pago?"].apply(lambda x: "✅" if int(x or 0) else "⏳")
                st.dataframe(df_gm, use_container_width=True, hide_index=True)

        st.markdown("---")
        if st.button("📥 Exportar Relatório Mensal (Excel)", use_container_width=True):
            buf_xl = io.BytesIO()
            wb     = xlsxwriter.Workbook(buf_xl)
            fmt_h   = wb.add_format({"bold":True,"bg_color":"#3d1f10","font_color":"white","border":1})
            fmt_brl = wb.add_format({"num_format":"R$ #,##0.00","border":1})
            fmt_n   = wb.add_format({"border":1})

            ws1 = wb.add_worksheet("Entradas")
            for ci, h in enumerate(["Descrição","Categoria","Valor","Forma","Data"]):
                ws1.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_r_mes_rel.iterrows(), 1):
                ws1.write(ri, 0, row.get("descricao",""), fmt_n)
                ws1.write(ri, 1, row.get("categoria",""), fmt_n)
                ws1.write(ri, 2, float(row.get("valor",0) or 0), fmt_brl)
                ws1.write(ri, 3, row.get("forma_pagamento",""), fmt_n)
                ws1.write(ri, 4, str(row.get("data","")), fmt_n)

            ws2 = wb.add_worksheet("Gastos")
            for ci, h in enumerate(["Data","Descrição","Categoria","Valor","Pago?"]):
                ws2.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_g_mes_rel.iterrows(), 1):
                ws2.write(ri, 0, str(row.get("data","")), fmt_n)
                ws2.write(ri, 1, row.get("descricao",""), fmt_n)
                ws2.write(ri, 2, row.get("categoria",""), fmt_n)
                ws2.write(ri, 3, float(row.get("valor",0) or 0), fmt_brl)
                ws2.write(ri, 4, "Sim" if int(row.get("pago",0) or 0) else "Não", fmt_n)

            ws3 = wb.add_worksheet("Resumo")
            ws3.write(0, 0, f"Relatório – {MESES_PT[mes_sel_fin-1]} {ano_sel_fin}",
                      wb.add_format({"bold":True,"font_size":14,"font_color":"#3d1f10"}))
            fmt_key = wb.add_format({"bold":True})
            for ri, (k, v) in enumerate([("Receita Total", rec_mes),("Gastos Totais", gasto_mes),("Lucro Líquido", lucro_mes)], 2):
                ws3.write(ri, 0, k, fmt_key)
                ws3.write(ri, 1, v, fmt_brl)

            wb.close()
            buf_xl.seek(0)
            st.download_button(
                label=f"📥 Baixar Excel – {MESES_PT[mes_sel_fin-1]} {ano_sel_fin}",
                data=buf_xl,
                file_name=f"Lila_Financeiro_{mes_sel_fin:02d}_{ano_sel_fin}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
