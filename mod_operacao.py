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

def carregar_dados_op(mes_referencia):
    fire = inicializar_db()
    # Busca pelo documento do mês específico para manter histórico
    doc = fire.collection("operacoes_mensais").document(mes_referencia).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "novos_itens": []}

def salvar_dados_op(dados, mes_referencia):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_referencia).set(dados)

def listar_meses_disponiveis():
    fire = inicializar_db()
    docs = fire.collection("operacoes_mensais").stream()
    return [doc.id for doc in docs]

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# --- COMPONENTES DE INTERFACE ---
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    tag = "🆕 NOVO" if item.get('TIPO') == 'NOVO' else "📋 LISTA"
    st.caption(f"{tag} | Cód: {item['CODIGO']} | Sugestão: {item['QUANTIDADE']}")
    
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True

    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]
            salvar_dados_op(db_data, mes_ref); st.rerun()

# (Função de recebimento segue lógica similar, mas salvando no mes_ref)
def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado: {item['QTD_SOLICITADA']}**")
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"; df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    # ... (restante da lógica de recebimento)

# --- EXIBIÇÃO PRINCIPAL ---
def exibir_operacao_completa():
    aplicar_estilo_premium()
    
    # Gerenciamento de Mês
    mes_atual_str = datetime.now().strftime("%Y-%m")
    
    with st.sidebar:
        st.title("📂 Gestão Mensal")
        meses_dispo = listar_meses_disponiveis()
        if mes_atual_str not in meses_dispo: meses_dispo.append(mes_atual_str)
        mes_selecionado = st.selectbox("Selecione o Mês de Análise", sorted(meses_dispo, reverse=True))
        st.info(f"Visualizando: **{mes_selecionado}**")

    db_data = carregar_dados_op(mes_selecionado)
    
    tabs = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD", "➕ NOVO ITEM", "⚙️ CONFIG"])

    with tabs[0]: # COMPRAS
        if not db_data.get("analises"):
            st.warning("Nenhum dado para este mês. Vá em 'Configurações' para importar.")
        else:
            df_c = pd.DataFrame(db_data["analises"])
            # Busca e Esteira (Mesma lógica anterior, passando mes_selecionado para os saves)
            q = st.text_input("🔍 Localizar Item:").upper()
            if q:
                it_b = df_c[df_c['CODIGO'].astype(str).str.contains(q) | df_c['DESCRICAO'].astype(str).str.contains(q)]
                for i, r in it_b.iterrows():
                    with st.container(border=True): renderizar_tratativa_compra(r, i, df_c, db_data, mes_selecionado, "busca_c")
            
            idx_s = db_data.get("idx_solic", 0)
            while idx_s < len(df_c) and df_c.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
            db_data["idx_solic"] = idx_s
            if idx_s < len(df_c):
                st.subheader(f"🚀 Esteira de Compra ({idx_s + 1}/{len(df_c)})")
                renderizar_tratativa_compra(df_c.iloc[idx_s], idx_s, df_c, db_data, mes_selecionado, "esteira_c")

    with tabs[3]: # NOVO ITEM
        st.subheader("🆕 Cadastrar Produto Fora da Lista")
        with st.form("form_novo_item"):
            col1, col2 = st.columns(2)
            novo_cod = col1.text_input("Código do Item").upper()
            nova_desc = col2.text_input("Descrição Completa").upper()
            nova_qtd = st.number_input("Quantidade para Projeção", min_value=1)
            
            if st.form_submit_button("Adicionar à Projeção"):
                novo_dado = {
                    "CODIGO": novo_cod, "DESCRICAO": nova_desc, "QUANTIDADE": nova_qtd,
                    "STATUS_COMPRA": "Pendente", "STATUS_RECEB": "Pendente", 
                    "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "QTD_RECEBIDA": 0, "TIPO": "NOVO"
                }
                db_data["analises"].append(novo_dado)
                salvar_dados_op(db_data, mes_selecionado)
                st.success("Item adicionado com sucesso!")
                st.rerun()

    with tabs[4]: # CONFIGURAÇÕES
        st.subheader("⚙️ Painel de Controle")
        
        col_up, col_res = st.columns(2)
        with col_up:
            st.markdown("### 📥 Importar Dados")
            up = st.file_uploader(f"Subir Planilha para {mes_selecionado}", type="xlsx")
            if up:
                df_up = pd.read_excel(up)
                for col in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']:
                    df_up[col] = "Pendente" if "STATUS" in col else 0
                df_up['TIPO'] = 'LISTA'
                db_data["analises"] = df_up.to_dict(orient='records')
                salvar_dados_op(db_data, mes_selecionado)
                st.success("Dados importados!")
                st.rerun()

        with col_res:
            st.markdown("### 🧹 Reset Mensal")
            st.error("Isso apagará todos os dados APENAS do mês selecionado.")
            if st.button(f"LIMPAR MÊS {mes_selecionado}"):
                salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}, mes_selecionado)
                st.rerun()

# Execução
exibir_operacao_completa()
