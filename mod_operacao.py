import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io

# --- CONFIGURAÇÃO E DADOS ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        .search-box-rec { background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid #16a34a; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

def carregar_dados_op():
    fire = inicializar_db()
    doc = fire.collection("config").document("operacao_v2").get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados):
    fire = inicializar_db()
    fire.collection("config").document("operacao_v2").set(dados)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# --- TRATATIVAS (COMPRA E RECEBIMENTO) ---
def renderizar_tratativa_recebimento(item, index, df_completo, db_data, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado: {item['QTD_SOLICITADA']}**")
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"; df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data); st.rerun()
    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True
    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"; df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data); st.rerun()
    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=int(item['QTD_SOLICITADA']), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"; df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data); st.rerun()

def renderizar_tratativa_compra(item, index, df_completo, db_data, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"; df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data); st.rerun()
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"; df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data); st.rerun()

# --- DASHBOARD ROBUSTO ---
def renderizar_dashboard(df):
    if df.empty: return
    
    # 1. Cálculos de Base
    total_itens = len(df)
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    itens_conferidos = len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    
    # Itens Não Efetuados (Com e Sem Estoque)
    df_nao_efetuada = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
    nao_efet_com_estoque = df_nao_efetuada[df_nao_efetuada['SALDO_FISICO'] > 0]
    nao_efet_sem_estoque = df_nao_efetuada[df_nao_efetuada['SALDO_FISICO'] == 0]

    st.subheader("📊 Performance e Ruptura de Estoque")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conferidos}/{total_itens}</h3></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>COMPRAS EFETIVAS</small><h3 style='color:#002366;'>{compras_ok}</h3></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>NÃO EFET. (C/ ESTOQUE)</small><h3 style='color:#16a34a;'>{len(nao_efet_com_estoque)}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>NÃO EFET. (SEM ESTOQUE)</small><h3 style='color:#ef4444;'>{len(nao_efet_sem_estoque)}</h3></div>", unsafe_allow_html=True)

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        # Pizza de Status (Agora com nome corrigido)
        st_counts = df['STATUS_COMPRA'].value_counts().reset_index()
        st_counts.columns = ['Status', 'Qtd']
        fig_p = px.pie(st_counts, values='Qtd', names='Status', title="Decisões de Compra", 
                       color='Status', color_discrete_map={'Total': '#002366', 'Parcial': '#3b82f6', 'Não Efetuada': '#ef4444', 'Pendente': '#cbd5e1'}, hole=0.4)
        st.plotly_chart(fig_p, use_container_width=True)

    with c2:
        # Gráfico de Ruptura
        fig_rup = go.Figure(data=[
            go.Bar(name='Com Estoque (Estratégico)', x=['Não Efetuadas'], y=[len(nao_efet_com_estoque)], marker_color='#16a34a'),
            go.Bar(name='Sem Estoque (Ruptura)', x=['Não Efetuadas'], y=[len(nao_efet_sem_estoque)], marker_color='#ef4444')
        ])
        fig_rup.update_layout(title="Motivo das Não Encomendas", barmode='group', height=400)
        st.plotly_chart(fig_rup, use_container_width=True)

    # --- FLAGS DETALHADAS ---
    st.markdown("### 🔍 Detalhamento Estratégico")
    
    col_flag1, col_flag2 = st.columns(2)
    
    with col_flag1:
        with st.expander("🟢 Não Efetuadas - COM ESTOQUE (Estratégico)"):
            if not nao_efet_com_estoque.empty:
                # Mini Dash Interno
                qtd_poupada = nao_efet_com_estoque['QUANTIDADE'].sum()
                st.info(f"Evitamos a compra de **{qtd_poupada} unidades** pois já temos saldo.")
                st.dataframe(nao_efet_com_estoque[['DESCRICAO', 'QUANTIDADE', 'SALDO_FISICO']], use_container_width=True)
            else: st.write("Nenhum item nesta categoria.")

    with col_flag2:
        with st.expander("🔴 Não Efetuadas - SEM ESTOQUE (Alerta de Ruptura)"):
            if not nao_efet_sem_estoque.empty:
                # Mini Dash Interno
                qtd_perdida = nao_efet_sem_estoque['QUANTIDADE'].sum()
                st.error(f"Ruptura detectada: **{qtd_perdida} unidades** deixaram de ser compradas sem estoque disponível.")
                st.dataframe(nao_efet_sem_estoque[['DESCRICAO', 'QUANTIDADE']], use_container_width=True)
            else: st.write("Nenhum item nesta categoria.")

# --- EXIBIÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    db_data = carregar_dados_op()
    tab1, tab2, tab3 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD"])

    with tab1:
        if not db_data.get("analises"):
            up = st.file_uploader("Subir Planilha Base", type="xlsx")
            if up:
                df_up = pd.read_excel(up)
                for col in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']:
                    df_up[col] = "Pendente" if "STATUS" in col else 0
                db_data["analises"] = df_up.to_dict(orient='records'); salvar_dados_op(db_data); st.rerun()
            return
        
        df_c = pd.DataFrame(db_data["analises"])
        c_exp1, c_exp2 = st.columns([8, 2])
        c_exp2.download_button("📥 Exportar Compras", data=to_excel(df_c), file_name="compras.xlsx")

        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar Item:").upper()
        if q:
            it_b = df_c[df_c['CODIGO'].astype(str).str.contains(q) | df_c['DESCRICAO'].astype(str).str.contains(q)]
            for i, r in it_b.iterrows():
                with st.container(border=True): renderizar_tratativa_compra(r, i, df_c, db_data, "busca_c")
        st.markdown('</div>', unsafe_allow_html=True)
        
        idx_s = db_data.get("idx_solic", 0)
        while idx_s < len(df_c) and df_c.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
        db_data["idx_solic"] = idx_s
        if idx_s < len(df_c):
            st.subheader(f"🚀 Esteira ({idx_s + 1}/{len(df_c)})")
            with st.container():
                st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                renderizar_tratativa_compra(df_c.iloc[idx_s], idx_s, df_c, db_data, "esteira_c")
                st.markdown("</div>", unsafe_allow_html=True)

    with tab2:
        df_r = pd.DataFrame(db_data["analises"])
        st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
        q_rec = st.text_input("🔍 Localizar no Recebimento:").upper()
        if q_rec:
            it_b_rec = df_r[(df_r['QTD_SOLICITADA'] > 0) & (df_r['CODIGO'].astype(str).str.contains(q_rec) | df_r['DESCRICAO'].astype(str).str.contains(q_rec))]
            for i, r in it_b_rec.iterrows():
                with st.container(border=True): renderizar_tratativa_recebimento(r, i, df_r, db_data, "busca_r")
        st.markdown('</div>', unsafe_allow_html=True)

    with tab3:
        renderizar_dashboard(pd.DataFrame(db_data["analises"]))
        if st.button("🗑️ RESETAR SISTEMA"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}); st.rerun()
