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

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    # Identificador único por Mês/Ano no Firebase
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# --- TRATATIVAS ---
def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado: {item['QTD_SOLICITADA']}**")
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"; df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True
    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"; df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=int(item['QTD_SOLICITADA']), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"; df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"; df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"; df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# --- DASHBOARDS ORIGINAIS RESTAURADOS ---
def renderizar_dashboard_compras(df):
    if df.empty: return
    total_itens = len(df)
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    itens_conferidos = len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    
    perc_conf = (itens_conferidos / total_itens * 100) if total_itens > 0 else 0
    perc_ok = (compras_ok / itens_conferidos * 100) if itens_conferidos > 0 else 0
    
    df_nao_efetuada = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
    nao_efet_com_estoque = df_nao_efetuada[df_nao_efetuada['SALDO_FISICO'] > 0]
    nao_efet_sem_estoque = df_nao_efetuada[df_nao_efetuada['SALDO_FISICO'] == 0]
    
    perc_est = (len(nao_efet_com_estoque) / itens_conferidos * 100) if itens_conferidos > 0 else 0
    perc_rup = (len(nao_efet_sem_estoque) / itens_conferidos * 100) if itens_conferidos > 0 else 0

    st.subheader("📊 Performance de Compras")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conferidos}</h3><p>{perc_conf:.1f}% da lista</p></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>COMPRAS EFETIVAS</small><h3 style='color:#002366;'>{compras_ok}</h3><p>{perc_ok:.1f}% do proc.</p></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>ESTRATÉGICO (C/ EST.)</small><h3 style='color:#16a34a;'>{len(nao_efet_com_estoque)}</h3><p>{perc_est:.1f}% do proc.</p></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>RUPTURA (S/ EST.)</small><h3 style='color:#ef4444;'>{len(nao_efet_sem_estoque)}</h3><p>{perc_rup:.1f}% do proc.</p></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st_counts = df['STATUS_COMPRA'].value_counts().reset_index()
        st_counts.columns = ['Status', 'Qtd']
        fig_p = px.pie(st_counts, values='Qtd', names='Status', title="Decisões de Compra", 
                       color='Status', color_discrete_map={'Total': '#002366', 'Parcial': '#3b82f6', 'Não Efetuada': '#ef4444', 'Pendente': '#cbd5e1'}, hole=0.4)
        st.plotly_chart(fig_p, use_container_width=True)
    with c2:
        fig_rup = go.Figure(data=[
            go.Bar(name='Com Estoque', x=['Não Efetuadas'], y=[len(nao_efet_com_estoque)], marker_color='#16a34a'),
            go.Bar(name='Sem Estoque', x=['Não Efetuadas'], y=[len(nao_efet_sem_estoque)], marker_color='#ef4444')
        ])
        fig_rup.update_layout(title="Motivo das Não Encomendas", barmode='group', height=400)
        st.plotly_chart(fig_rup, use_container_width=True)

    st.markdown("### 🔍 Detalhamento e Exportação")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        with st.expander("🟢 Não Efetuadas - COM ESTOQUE (Estratégico)"):
            if not nao_efet_com_estoque.empty:
                st.download_button("📥 Baixar Excel Estratégico", data=to_excel(nao_efet_com_estoque), file_name="estrategico.xlsx", key="dl_est")
                st.dataframe(nao_efet_com_estoque[['DESCRICAO', 'QUANTIDADE', 'SALDO_FISICO']], use_container_width=True)
    with col_f2:
        with st.expander("🔴 Não Efetuadas - SEM ESTOQUE (Ruptura)"):
            if not nao_efet_sem_estoque.empty:
                st.download_button("📥 Baixar Excel Ruptura", data=to_excel(nao_efet_sem_estoque), file_name="ruptura.xlsx", key="dl_rup")
                st.dataframe(nao_efet_sem_estoque[['DESCRICAO', 'QUANTIDADE']], use_container_width=True)

def renderizar_dashboard_recebimento(df):
    if df.empty: return
    encomendados = df[df['QTD_SOLICITADA'] > 0]
    total_enc = len(encomendados)
    if total_enc == 0:
        st.warning("Aguardando encomendas para gerar dashboard de recebimento.")
        return
    
    df_rec = encomendados[encomendados['STATUS_RECEB'] != "Pendente"]
    itens_rec = len(df_rec)
    rec_total = len(df_rec[df_rec['STATUS_RECEB'] == "Recebido Total"])
    rec_parcial = len(df_rec[df_rec['STATUS_RECEB'] == "Recebido Parcial"])
    faltou = len(df_rec[df_rec['STATUS_RECEB'] == "Faltou"])
    perc_rec = (itens_rec / total_enc * 100)
    
    st.subheader("📊 Performance de Recebimento")
    r1, r2, r3, r4 = st.columns(4)
    r1.markdown(f"<div class='metric-box'><small>ITENS CONFERIDOS</small><h3>{itens_rec}/{total_enc}</h3><p>{perc_rec:.1f}% do total</p></div>", unsafe_allow_html=True)
    r2.markdown(f"<div class='metric-box'><small>RECEBIDO TOTAL</small><h3 style='color:#16a34a;'>{rec_total}</h3></div>", unsafe_allow_html=True)
    r3.markdown(f"<div class='metric-box'><small>RECEBIDO PARCIAL</small><h3 style='color:#facc15;'>{rec_parcial}</h3></div>", unsafe_allow_html=True)
    r4.markdown(f"<div class='metric-box'><small>FALTOU/ERRO</small><h3 style='color:#ef4444;'>{faltou}</h3></div>", unsafe_allow_html=True)

    fig_r = px.bar(df_rec, x='CODIGO', y=['QTD_SOLICITADA', 'QTD_RECEBIDA'], 
                   title="Confronto: Solicitado vs Recebido", barmode='group',
                   color_discrete_sequence=['#002366', '#16a34a'])
    st.plotly_chart(fig_r, use_container_width=True)

# --- EXIBIÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    
    # 3 - Alternar entre meses e anos na Sidebar
    st.sidebar.title("📅 Seleção de Período")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês de Trabalho", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano de Trabalho", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 DASHBOARD RECEBIMENTO", "⚙️ CONFIGURAÇÕES"])

    with tab5:
        st.header(f"⚙️ Configuração: {mes_sel}/{ano_sel}")
        
        col_up1, col_up2 = st.columns(2)
        
        # 2 - Duas opções de Upload
        with col_up1:
            st.subheader("📄 Planilha NOVA")
            st.caption("Use para iniciar um mês do zero (Crua).")
            up_nova = st.file_uploader("Upload Base Crua", type="xlsx", key="up_nova")
            if up_nova:
                df_nova = pd.read_excel(up_nova)
                for col in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']:
                    df_nova[col] = "Pendente" if "STATUS" in col else 0
                if st.button("🚀 Iniciar Mês com esta Base"):
                    db_data = {"analises": df_nova.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}
                    salvar_dados_op(db_data, mes_ref)
                    st.success("Mês iniciado!")
                    st.rerun()

        with col_up2:
            st.subheader("📝 Planilha PREENCHIDA")
            st.caption("Use para subir dados já analisados fora do sistema.")
            up_pre = st.file_uploader("Upload Base Analisada", type="xlsx", key="up_pre")
            if up_pre:
                df_pre = pd.read_excel(up_pre)
                # Verifica colunas mínimas para não quebrar o dash
                cols_necessarias = ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'STATUS_RECEB', 'QTD_RECEBIDA']
                for c in cols_necessarias:
                    if c not in df_pre.columns: df_pre[c] = 0
                
                if st.button("📥 Importar Análise Pronta"):
                    db_data = {"analises": df_pre.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}
                    salvar_dados_op(db_data, mes_ref)
                    st.success("Dados importados! Dashboards atualizados.")
                    st.rerun()

        st.divider()
        if st.button("🗑️ RESETAR ESTE MÊS"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}, mes_ref)
            st.rerun()

    if not db_data.get("analises"):
        st.warning(f"⚠️ Sem dados para {mes_sel}/{ano_sel}. Vá na aba CONFIGURAÇÕES e suba uma planilha.")
        return

    df_atual = pd.DataFrame(db_data["analises"])

    with tab1:
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar Item:").upper()
        if q:
            it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
            for i, r in it_b.iterrows():
                with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "busca_c")
        st.markdown('</div>', unsafe_allow_html=True)
        
        idx_s = db_data.get("idx_solic", 0)
        while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
        db_data["idx_solic"] = idx_s
        if idx_s < len(df_atual):
            st.subheader(f"🚀 Esteira de Compra ({idx_s + 1}/{len(df_atual)})")
            with st.container():
                st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "esteira_c")
                st.markdown("</div>", unsafe_allow_html=True)

    with tab2:
        pendentes_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
        if not pendentes_rec.empty:
            st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
            q_rec = st.text_input("🔍 Localizar no Recebimento:").upper()
            if q_rec:
                it_b_rec = pendentes_rec[pendentes_rec['CODIGO'].astype(str).str.contains(q_rec) | pendentes_rec['DESCRICAO'].astype(str).str.contains(q_rec)]
                for _, r in it_b_rec.iterrows():
                    with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "busca_r")
            st.markdown('</div>', unsafe_allow_html=True)

            idx_r = db_data.get("idx_receb", 0)
            if idx_r >= len(pendentes_rec): idx_r = 0
            st.subheader(f"📥 Esteira de Recebimento ({idx_r + 1}/{len(pendentes_rec)})")
            item_r = pendentes_rec.iloc[idx_r]
            with st.container():
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(item_r, item_r['index'], df_atual, db_data, mes_ref, "esteira_r")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.success("✅ Tudo recebido!")

    with tab3:
        renderizar_dashboard_compras(df_atual)

    with tab4:
        renderizar_dashboard_recebimento(df_atual)
