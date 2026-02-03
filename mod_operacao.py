import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime

# --- CONFIGURAÇÃO VISUAL PREMIUM ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; }
        .stButton>button { border-radius: 8px; font-weight: 600; transition: all 0.3s; }
        .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .badge-pendente { background: #fff7ed; color: #c2410c; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

# --- NÚCLEO DE DADOS ---
def carregar_dados_op():
    fire = inicializar_db()
    doc = fire.collection("config").document("operacao_v2").get()
    return doc.to_dict() if doc.exists else {"analises": [], "recebimento": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados):
    fire = inicializar_db()
    fire.collection("config").document("operacao_v2").set(dados)

# --- DASHBOARD DE CONFRONTO ---
def renderizar_dashboard(df):
    st.subheader("📊 Confronto de Fluxo")
    if df.empty: return

    c1, c2, c3, c4 = st.columns(4)
    total_lista = df['QUANTIDADE'].sum()
    total_encomendado = df['QTD_SOLICITADA'].sum()
    total_recebido = df['QTD_RECEBIDA'].sum()
    
    with c1: st.markdown(f"<div class='metric-box'><small>LISTA ORIGINAL</small><h3>{total_lista}</h3></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-box'><small>ENCOMENDADO</small><h3 style='color:#002366;'>{total_encomendado}</h3></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-box'><small>RECEBIDO</small><h3 style='color:#16a34a;'>{total_recebido}</h3></div>", unsafe_allow_html=True)
    with c4: 
        eficiencia = (total_recebido / total_lista * 100) if total_lista > 0 else 0
        st.markdown(f"<div class='metric-box'><small>EFICIÊNCIA</small><h3>{eficiencia:.1f}%</h3></div>", unsafe_allow_html=True)

    # Gráfico de Barras de Confronto
    fig = go.Figure(data=[
        go.Bar(name='Original', x=df['CODIGO'][:10], y=df['QUANTIDADE'][:10], marker_color='#cbd5e1'),
        go.Bar(name='Encomendado', x=df['CODIGO'][:10], y=df['QTD_SOLICITADA'][:10], marker_color='#002366'),
        go.Bar(name='Recebido', x=df['CODIGO'][:10], y=df['QTD_RECEBIDA'][:10], marker_color='#16a34a')
    ])
    fig.update_layout(barmode='group', title="Top 10 Itens: Confronto Quantitativo", height=350)
    st.plotly_chart(fig, use_container_width=True)

# --- FUNÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    db_data = carregar_dados_op()
    
    tab1, tab2, tab3 = st.tabs(["🛒 ESTEIRA DE COMPRAS", "📥 RECEBIMENTO", "📈 DASHBOARD & BD"])

    # --- ABA 1: COMPRAS ---
    with tab1:
        if not db_data["analises"]:
            uploaded_file = st.file_uploader("Upload da Lista de Compras (Excel)", type="xlsx")
            if uploaded_file:
                df_upload = pd.read_excel(uploaded_file)
                # Normalização conforme sua imagem (CODIGO, DESCRICAO, QUANTIDADE, etc)
                df_upload['STATUS_COMPRA'] = "Pendente"
                df_upload['QTD_SOLICITADA'] = 0
                df_upload['QTD_RECEBIDA'] = 0
                df_upload['STATUS_RECEB'] = "Aguardando"
                db_data["analises"] = df_upload.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()
            st.stop()

        df_c = pd.DataFrame(db_data["analises"])
        
        # BUSCA INDIVIDUAL
        with st.expander("🔍 Busca por Código ou Descrição"):
            query = st.text_input("Digite o código ou parte da descrição:").upper()
            if query:
                it_busca = df_c[(df_c['CODIGO'].str.contains(query)) | (df_c['DESCRICAO'].str.contains(query))]
                st.dataframe(it_busca[['CODIGO', 'DESCRICAO', 'QUANTIDADE', 'STATUS_COMPRA']])

        # ESTEIRA (SEQUENCIAL)
        idx = db_data["idx_solic"]
        if idx < len(df_c):
            item = df_c.iloc[idx]
            st.markdown(f"""<div class='main-card'>
                <span class='badge-pendente'>ITEM {idx+1} / {len(df_c)}</span>
                <h2 style='margin-top:10px;'>{item['DESCRICAO']}</h2>
                <p><b>CÓDIGO:</b> {item['CODIGO']} | <b>FORNECEDOR:</b> {item['FORNECEDOR']}</p>
                <h1 style='color:#002366;'>Solicitado na Lista: {item['QUANTIDADE']}</h1>
            </div>""", unsafe_allow_html=True)

            col1, col2, col3 = st.columns(3)
            if col1.button("✅ COMPRA TOTAL", use_container_width=True):
                df_c.at[idx, 'STATUS_COMPRA'] = "Total"
                df_c.at[idx, 'QTD_SOLICITADA'] = item['QUANTIDADE']
                db_data["idx_solic"] += 1; db_data["analises"] = df_c.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()

            if col2.button("⚠️ COMPRA PARCIAL", use_container_width=True):
                st.session_state.parcial_solic = True

            if col3.button("❌ SEM ENCOMENDA", use_container_width=True):
                df_c.at[idx, 'STATUS_COMPRA'] = "Zerado"
                df_c.at[idx, 'QTD_SOLICITADA'] = 0
                db_data["idx_solic"] += 1; db_data["analises"] = df_c.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()

            if st.session_state.get('parcial_solic'):
                qtd_p = st.number_input("Informe a Quantidade Parcial:", min_value=1, max_value=int(item['QUANTIDADE']))
                if st.button("Confirmar Parcial"):
                    df_c.at[idx, 'STATUS_COMPRA'] = "Parcial"
                    df_c.at[idx, 'QTD_SOLICITADA'] = qtd_p
                    db_data["idx_solic"] += 1; db_data["analises"] = df_c.to_dict(orient='records')
                    del st.session_state.parcial_solic
                    salvar_dados_op(db_data); st.rerun()
        else:
            st.success("🎉 Ciclo de Encomendas Finalizado!")

    # --- ABA 2: RECEBIMENTO ---
    with tab2:
        st.subheader("📥 Esteira de Recebimento (Conferência)")
        # Apenas itens que tiveram alguma solicitação (>0)
        df_r = pd.DataFrame(db_data["analises"])
        itens_para_receber = df_r[df_r['QTD_SOLICITADA'] > 0].reset_index()
        
        idx_r = db_data["idx_receb"]
        if idx_r < len(itens_para_receber):
            it_r = itens_para_receber.iloc[idx_r]
            original_idx = it_r['index']

            st.markdown(f"""<div class='main-card' style='border-top-color:#16a34a;'>
                <h3>RECEBENDO: {it_r['DESCRICAO']}</h3>
                <p><b>CÓDIGO:</b> {it_r['CODIGO']}</p>
                <h1 style='color:#16a34a;'>Esperado (Encomenda): {it_r['QTD_SOLICITADA']}</h1>
            </div>""", unsafe_allow_html=True)

            r1, r2, r3 = st.columns(3)
            if r1.button("🟢 RECEBIDO TOTAL", use_container_width=True):
                df_r.at[original_idx, 'STATUS_RECEB'] = "Recebido Total"
                df_r.at[original_idx, 'QTD_RECEBIDA'] = it_r['QTD_SOLICITADA']
                db_data["idx_receb"] += 1; db_data["analises"] = df_r.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()

            if r2.button("🟡 RECEBIDO PARCIAL", use_container_width=True):
                st.session_state.parcial_receb = True

            if r3.button("🔴 NÃO RECEBIDO", use_container_width=True):
                df_r.at[original_idx, 'STATUS_RECEB'] = "Não Recebido"
                df_r.at[original_idx, 'QTD_RECEBIDA'] = 0
                db_data["idx_receb"] += 1; db_data["analises"] = df_r.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()

            if st.session_state.get('parcial_receb'):
                qtd_rp = st.number_input("Qtd Realmente Recebida:", min_value=0, max_value=int(it_r['QTD_SOLICITADA']))
                if st.button("Validar Entrada Parcial"):
                    df_r.at[original_idx, 'STATUS_RECEB'] = "Recebido Parcial"
                    df_r.at[original_idx, 'QTD_RECEBIDA'] = qtd_rp
                    db_data["idx_receb"] += 1; db_data["analises"] = df_r.to_dict(orient='records')
                    del st.session_state.parcial_receb
                    salvar_dados_op(db_data); st.rerun()
        else:
            st.info("Nenhum item pendente de recebimento.")

    # --- ABA 3: DASHBOARD & BD ---
    with tab3:
        df_final = pd.DataFrame(db_data["analises"])
        renderizar_dashboard(df_final)
        
        st.divider()
        st.subheader("🗄️ Banco de Dados Consolidado")
        st.dataframe(df_final, use_container_width=True)
        
        if st.button("🗑️ Resetar Ciclo e Limpar Banco"):
            salvar_dados_op({"analises": [], "recebimento": [], "idx_solic": 0, "idx_receb": 0})
            st.rerun()
