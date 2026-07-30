"""
modulos/mod_financeiro.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
BLOCO FINANCEIRO — extraído do main.py (v11.2). Primeiro módulo da série de
refatoração que vai, aos poucos, reduzir o main.py (mesmo espírito da
modularização já feita no Painel KingStar).

Contém: dashboard financeiro (capital de giro, reserva de emergência, teto
de gastos), lançamento de gastos, gestão de pagamentos por pedido e
relatório mensal exportável em Excel.

Ponto de entrada: `renderizar_financeiro(df_enc_all, hoje_dt)`
  - df_enc_all: DataFrame de encomendas ativas (não canceladas), já
    carregado uma vez no main.py e reaproveitado por vários blocos.
  - hoje_dt: data de hoje (date), no fuso de Brasília.

Nenhuma função de banco de dados (`database.py`) foi alterada. Nenhuma
regra de negócio foi modificada nesta extração — é uma cópia fiel do bloco
que já existia dentro do main.py.
"""

import io

import pandas as pd
import streamlit as st
import xlsxwriter

from database import (
    cfg_get,
    encomendas_atualizar,
    encomendas_listar,
    gastos_atualizar,
    gastos_deletar,
    gastos_inserir,
    gastos_listar,
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


def renderizar_financeiro(df_enc_all: pd.DataFrame, hoje_dt):
    """
    Renderiza o BLOCO FINANCEIRO completo: KPIs de topo (receita, gastos,
    lucro real/previsto), painéis de capital de giro / reserva de
    emergência / teto de gastos, e as 4 abas internas (Dashboard, Lançar
    Gastos, Pagamentos por Pedido, Relatório Mensal).
    """
    st.markdown("## 💰 Financeiro")
    st.markdown("### 💰 Controle Financeiro Profissional")

    df_enc_fin = df_enc_all
    df_g_fin   = gastos_listar()

    def _flt(df, col, default=0.0):
        if df.empty or col not in df.columns:
            return default
        return float(df[col].fillna(0).astype(float).sum())

    receita_total    = _flt(df_enc_fin, "valor_recebido")
    receita_prevista = float(df_enc_fin[df_enc_fin["etapa"].astype(int) < 7]["valor_total"].fillna(0).astype(float).sum()) if not df_enc_fin.empty else 0.0
    gastos_pagos     = float(df_g_fin[df_g_fin["pago"].astype(int) == 1]["valor"].fillna(0).astype(float).sum()) if not df_g_fin.empty else 0.0
    gastos_previstos = float(df_g_fin[df_g_fin["pago"].astype(int) == 0]["valor"].fillna(0).astype(float).sum()) if not df_g_fin.empty else 0.0
    lucro_real       = receita_total - gastos_pagos
    lucro_previsto   = (receita_total + receita_prevista) - (gastos_pagos + gastos_previstos)

    pct_reserva   = int(cfg_get("reserva_emergencia_meses") or 3)
    pct_capital   = float(cfg_get("capital_giro_pct") or 20) / 100
    margem_min    = float(cfg_get("margem_minima_pct") or 30) / 100
    meta_fat_fin  = float(cfg_get("meta_faturamento") or 5000)

    reserva_sugerida = gastos_pagos * pct_reserva / 12 if gastos_pagos > 0 else gastos_previstos * pct_reserva
    capital_giro_sug = receita_total * pct_capital
    teto_gasto_mens  = (receita_total + receita_prevista) * (1 - margem_min) if (receita_total + receita_prevista) > 0 else 0

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
    f_dash, f_gastos, f_pedidos, f_relat = st.tabs([
        "📊 Dashboard", "📝 Lançar Gastos",
        "💳 Pagamentos por Pedido", "📋 Relatório Mensal",
    ])

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

    with f_gastos:
        st.markdown("#### 📝 Lançar Gasto ou Previsão")
        col_g1, col_g2 = st.columns([3, 2])
        with col_g1:
            with st.form("form_gasto_novo", clear_on_submit=True):
                c1, c2 = st.columns(2)
                g_desc = c1.text_input("Descrição do gasto *")
                g_val  = c2.number_input("Valor (R$) *", min_value=0.01, step=10.0, format="%.2f")
                c3, c4 = st.columns(2)
                g_cat  = c3.selectbox("Categoria", CAT_GASTOS)
                g_data = c4.date_input("Data", hoje_brasilia(), format="DD/MM/YYYY")
                c5, c6 = st.columns(2)
                g_pago  = c5.checkbox("Já foi pago?", value=True)
                g_recor = c6.checkbox("Gasto recorrente (mensal)?")

                df_enc_ativos = encomendas_listar(cancelado=False)
                enc_ativos_list = []
                if not df_enc_ativos.empty:
                    enc_ativos_list = [
                        (row["rowid"], f"#{row['rowid'][:6]} – {row['cliente']}: {row['peca']}")
                        for _, row in df_enc_ativos[df_enc_ativos["etapa"].astype(int) < 7].iterrows()
                    ]
                enc_list  = ["— Nenhum (custo fixo/geral) —"] + [e[1] for e in enc_ativos_list]
                g_enc_lbl = st.selectbox("Vincular a pedido? (opcional)", enc_list)
                g_enc_id  = None
                if g_enc_lbl != "— Nenhum (custo fixo/geral) —":
                    idx = enc_list.index(g_enc_lbl) - 1
                    g_enc_id = enc_ativos_list[idx][0]

                if st.form_submit_button("💾 Lançar Gasto", use_container_width=True, type="primary"):
                    if g_desc.strip() and g_val > 0:
                        gastos_inserir({
                            "encomenda_id": g_enc_id,
                            "descricao": g_desc.strip(), "valor": g_val,
                            "data": g_data.isoformat(), "categoria": g_cat,
                            "pago": 1 if g_pago else 0,
                            "recorrente": 1 if g_recor else 0,
                            "criado_em": agora_br().isoformat(),
                        })
                        st.success("✅ Gasto lançado!")
                        st.rerun()
                    else:
                        st.error("Preencha descrição e valor.")

        with col_g2:
            st.markdown("**📊 Resumo por Categoria**")
            if not df_g_fin.empty and "categoria" in df_g_fin.columns:
                df_cat_sum = df_g_fin.groupby("categoria")["valor"].sum().reset_index()
                df_cat_sum.columns = ["Categoria","Total"]
                df_cat_sum = df_cat_sum.sort_values("Total", ascending=False)
                df_cat_sum["Total"] = df_cat_sum["Total"].apply(lambda x: brl(float(x)))
                st.dataframe(df_cat_sum, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum gasto registrado.")

        st.markdown("---")
        st.markdown("#### 📋 Todos os Gastos")
        df_g_fin_fresh = gastos_listar()
        if df_g_fin_fresh.empty:
            st.info("Nenhum gasto registrado.")
        else:
            for _, g in df_g_fin_fresh.iterrows():
                status_g = "✅ Pago" if int(g.get("pago", 0) or 0) else "⏳ Em aberto"
                badge_g  = "badge-green" if int(g.get("pago", 0) or 0) else "badge-amber"
                lancado_em = g.get("criado_em")
                lancado_html = f" &nbsp;|&nbsp; 🕐 lançado em {formatar_data_hora_br(lancado_em)}" if lancado_em else ""
                col_gi, col_gb = st.columns([5, 1])
                col_gi.markdown(f"""
                <div class="kcard">
                  <div class="kcard-title">{g['descricao']} — <b>{brl(float(g.get('valor',0)))}</b></div>
                  <div class="kcard-sub">
                    📂 {g.get('categoria','')} &nbsp;|&nbsp; 📅 {formatar_data_br(g.get('data',''))}{lancado_html}
                    &nbsp;<span class="badge {badge_g}">{status_g}</span>
                    {"&nbsp;<span class='badge badge-blue'>🔁 Recorrente</span>" if int(g.get('recorrente', 0) or 0) else ""}
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
                            "Valor recebido (R$)",
                            min_value=0.01, max_value=float(v_restante + 0.01),
                            value=float(v_restante), step=10.0, format="%.2f",
                            key=f"rec_val_{enc['rowid']}",
                        )
                        col_rec2.metric("Saldo após:", brl(v_restante - novo_val))
                        if col_rec3.button("✅ Confirmar", key=f"rec_btn_{enc['rowid']}"):
                            novo_total = v_recebido + novo_val
                            encomendas_atualizar(str(enc["rowid"]), {"valor_recebido": novo_total})
                            st.success(f"✅ {brl(novo_val)} registrado!")
                            st.rerun()

                        if st.button(f"💰 Quitar saldo total ({brl(v_restante)})", key=f"quit_total_{enc['rowid']}"):
                            encomendas_atualizar(str(enc["rowid"]), {"valor_recebido": v_total_e})
                            st.rerun()
                    else:
                        st.markdown('<div class="fin-ok">✅ Pedido totalmente pago.</div>', unsafe_allow_html=True)

    with f_relat:
        st.markdown("#### 📋 Relatório Financeiro Mensal")
        col_rm1, col_rm2 = st.columns(2)
        mes_sel_fin = col_rm1.selectbox("Mês", list(range(1,13)),
            format_func=lambda x: MESES_PT[x-1], index=hoje_dt.month-1, key="mes_rel_fin")
        ano_sel_fin = col_rm2.number_input("Ano", min_value=2020, max_value=2030, value=hoje_dt.year)

        mes_str = f"{ano_sel_fin}-{mes_sel_fin:02d}"

        df_enc_mes = pd.DataFrame()
        if not df_enc_fin.empty and "data_entrega" in df_enc_fin.columns:
            df_enc_mes = df_enc_fin[df_enc_fin["data_entrega"].fillna("").str.startswith(mes_str)]

        df_g_mes = pd.DataFrame()
        if not df_g_fin.empty and "data" in df_g_fin.columns:
            df_g_mes = df_g_fin[df_g_fin["data"].fillna("").str.startswith(mes_str)]

        rec_mes   = float(df_enc_mes["valor_recebido"].fillna(0).astype(float).sum()) if not df_enc_mes.empty else 0.0
        gasto_mes = float(df_g_mes["valor"].fillna(0).astype(float).sum()) if not df_g_mes.empty else 0.0
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
            st.markdown("**Pedidos do mês**")
            if df_enc_mes.empty:
                st.info("Nenhum pedido com entrega neste mês.")
            else:
                df_em = df_enc_mes[["cliente","peca","valor_recebido","valor_total"]].copy()
                df_em.columns = ["Cliente","Peça","Recebido","Total"]
                df_em["Recebido"] = df_em["Recebido"].apply(lambda x: brl(float(x)))
                df_em["Total"]    = df_em["Total"].apply(lambda x: brl(float(x)))
                st.dataframe(df_em, use_container_width=True, hide_index=True)

        with col_rt2:
            st.markdown("**Gastos do mês**")
            if df_g_mes.empty:
                st.info("Nenhum gasto registrado neste mês.")
            else:
                df_gm = df_g_mes[["descricao","categoria","valor","pago"]].copy()
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

            ws1 = wb.add_worksheet("Receitas")
            for ci, h in enumerate(["Cliente","Peça","Total","Recebido","A Receber","Entrega"]):
                ws1.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_enc_mes.iterrows(), 1):
                ws1.write(ri, 0, row.get("cliente",""), fmt_n)
                ws1.write(ri, 1, row.get("peca",""), fmt_n)
                ws1.write(ri, 2, float(row.get("valor_total",0) or 0), fmt_brl)
                ws1.write(ri, 3, float(row.get("valor_recebido",0) or 0), fmt_brl)
                ws1.write(ri, 4, float(row.get("valor_total",0) or 0) - float(row.get("valor_recebido",0) or 0), fmt_brl)
                ws1.write(ri, 5, str(row.get("data_entrega","")), fmt_n)

            ws2 = wb.add_worksheet("Gastos")
            for ci, h in enumerate(["Data","Descrição","Categoria","Valor","Pago?"]):
                ws2.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_g_mes.iterrows(), 1):
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
