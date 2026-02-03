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
        .search-box { background: #eef2ff; padding: 20px; border-radius: 15px; border-left: 5px solid #4f46e5; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

# --- NÚCLEO DE DADOS ---
def carregar_dados_op():
    fire = inicializar_db()
    doc = fire.collection("config").document("operacao_v2").get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados):
    fire = inicializar_db()
    fire.collection("config").document("operacao_v2").set(dados)

# --- COMPONENTE DE TRATATIVA (REUTILIZÁVEL) ---
def renderizar_tratativa(item, index, df_completo, db_data, key_suffix=""):
    st.markdown(f"### 📦 {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    
    # Voltando com o Saldo em Estoque
    saldo = st.number_input(f"Saldo em Estoque (Físico):", min_value=0, key=f"sld_{index}_{key_suffix}")
    
    col1, col2, col3 = st.columns(3)
    
    # Botão Compra Total
    if col1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        if key_suffix == "esteira": db_data["idx_solic"] += 1
        salvar_dados_op(db_data); st.rerun()

    # Botão Compra Parcial
    if col2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"input_parcial_{index}"] = True

    # Botão Sem Encomenda
    if col3.button("❌ ZERAR", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Zerado"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        if key_suffix == "esteira": db_data["idx_solic"] += 1
        salvar_dados_op(db_data); st.rerun()

    # Input dinâmico para Parcial
    if st.session_state.get(f"input_parcial_{index}"):
        c_p1, c_p2 = st.columns([2, 1])
        qtd_p = c_p1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}")
        if c_p2.button("Confirmar", key=f"conf_{index}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            if key_suffix == "esteira": db_data["idx_solic"] += 1
            del st.session_state[f"input_parcial_{index}"]
            salvar_dados_op(db_data); st.rerun()

# --- FUNÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    db_data = carregar_dados_op()
    
    tab1, tab2, tab3 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📈 DASHBOARD"])

    with tab1:
        if not db_data["analises"]:
            uploaded_file = st.file_uploader("Upload da Lista de Compras", type="xlsx")
            if uploaded_file:
                df_upload = pd.read_excel(uploaded_file)
                df_upload['STATUS_COMPRA'] = "Pendente"
                df_upload['QTD_SOLICITADA'] = 0
                df_upload['SALDO_FISICO'] = 0
                df_upload['QTD_RECEBIDA'] = 0
                df_upload['STATUS_RECEB'] = "Aguardando"
                db_data["analises"] = df_upload.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()
            st.stop()

        df_c = pd.DataFrame(db_data["analises"])
        
        # 1. BUSCA COM TRATATIVA IMEDIATA
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        query = st.text_input("🔍 BUSCA RÁPIDA (Tratativa Direta por Código/Descrição):").upper()
        if query:
            # Filtra itens que ainda estão pendentes ou que o usuário deseja re-analisar
            it_busca = df_c[(df_c['CODIGO'].str.contains(query)) | (df_c['DESCRICAO'].str.contains(query))]
            if not it_busca.empty:
                for i, row in it_busca.iterrows():
                    with st.container(border=True):
                        renderizar_tratativa(row, i, df_c, db_data, key_suffix="busca")
            else:
                st.warning("Nenhum item encontrado.")
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. ESTEIRA SEQUENCIAL
        st.subheader("🚀 Esteira de Operação")
        idx = db_data["idx_solic"]
        if idx < len(df_c):
            # Se o item atual já foi tratado via busca, pula ele na esteira
            while idx < len(df_c) and df_c.iloc[idx]['STATUS_COMPRA'] != "Pendente":
                idx += 1
                db_data["idx_solic"] = idx
                salvar_dados_op(db_data)
            
            if idx < len(df_c):
                item = df_c.iloc[idx]
                with st.container():
                    st.markdown(f"<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa(item, idx, df_c, db_data, key_suffix="esteira")
                    st.markdown(f"</div>", unsafe_allow_html=True)
        else:
            st.success("✅ Ciclo de Compras Concluído!")

    # --- ABA RECEBIMENTO E DASH (Mantendo a lógica anterior com os novos campos) ---
    # ... (Aba 2 e 3 seguem a mesma lógica de confronto usando SALDO_FISICO, QTD_SOLICITADA e QTD_RECEBIDA)
