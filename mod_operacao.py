import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io

# =========================================================
# 1. FUNÇÕES DE BANCO DE DADOS
# =========================================================
def carregar_dados_op(mes_referencia):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_referencia).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados, mes_referencia):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_referencia).set(dados)

def listar_meses_gravados():
    fire = inicializar_db()
    return [doc.id for doc in fire.collection("operacoes_mensais").stream()]

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# =========================================================
# 2. COMPONENTES DE INTERFACE (TRATATIVAS)
# =========================================================
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    # Proteção para campos obrigatórios na exibição
    desc = item.get('DESCRICAO', 'SEM DESCRICAO')
    cod = item.get('CODIGO', 'S/C')
    qtd = item.get('QUANTIDADE', 0)
    
    st.markdown(f"#### {desc}")
    tipo = "🆕 NOVO" if item.get('TIPO') == 'NOVO_DIRETORIA' else "📦 LISTA"
    st.caption(f"{tipo} | Cód: {cod} | Qtd: {qtd}")
    
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = qtd
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True

    if c3.button("❌ NÃO", key=f"zer_{index}_{key_suffix}", use_container_width=True):
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

# =========================================================
# 3. FUNÇÃO PRINCIPAL E IMPORTAÇÃO BLINDADA
# =========================================================
def exibir_operacao_completa(user_role):
    st.markdown("""<style>.main-card { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }</style>""", unsafe_allow_html=True)
    
    mes_atual_str = datetime.now().strftime("%Y-%m")
    with st.sidebar:
        st.divider()
        meses_dispo = listar_meses_gravados()
        if mes_atual_str not in meses_dispo: meses_dispo.append(mes_atual_str)
        mes_selecionado = st.selectbox("📅 Mês de Análise", sorted(meses_dispo, reverse=True))
    
    db_data = carregar_dados_op(mes_selecionado)
    tab_compra, tab_receb, tab_dash, tab_novo, tab_config = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARDS", "➕ NOVO ITEM", "⚙️ CONFIGURAÇÕES"])

    with tab_compra:
        if not db_data.get("analises"):
            st.warning("Nenhum dado. Vá em CONFIGURAÇÕES e importe a planilha.")
        else:
            df_c = pd.DataFrame(db_data["analises"])
            
            # Garante que as colunas essenciais existam no DataFrame para evitar erros de interface
            for col in ['CODIGO', 'DESCRICAO', 'QUANTIDADE', 'STATUS_COMPRA']:
                if col not in df_c.columns: df_c[col] = 0 if col == 'QUANTIDADE' else "N/A"

            idx_s = db_data.get("idx_solic", 0)
            while idx_s < len(df_c) and df_c.iloc[idx_s].get('STATUS_COMPRA') != "Pendente":
                idx_s += 1
            
            db_data["idx_solic"] = idx_s
            if idx_s < len(df_c):
                st.subheader(f"🚀 Esteira de Compra ({idx_s + 1}/{len(df_c)})")
                with st.markdown("<div class='main-card'>", unsafe_allow_html=True):
                    renderizar_tratativa_compra(df_c.iloc[idx_s], idx_s, df_c, db_data, mes_selecionado, "esteira")
                    st.markdown("</div>", unsafe_allow_html=True)

    with tab_config:
        st.subheader("⚙️ Importação de Dados")
        up = st.file_uploader("Subir Planilha Excel", type="xlsx")
        if up:
            df_up = pd.read_excel(up)
            
            # --- NORMALIZAÇÃO DE COLUNAS (O SEGREDO DO AJUSTE) ---
            # Transforma tudo em MAIÚSCULO para evitar erro de digitação
            df_up.columns = [str(c).upper().strip() for c in df_up.columns]
            
            # Mapeamento inteligente (Se vier 'QTD', vira 'QUANTIDADE')
            mapeamento = {'QTD': 'QUANTIDADE', 'PRODUTO': 'DESCRICAO', 'COD': 'CODIGO'}
            df_up.rename(columns=mapeamento, inplace=True)
            
            # Garante que as colunas padrão existam
            for col in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']:
                df_up[col] = "Pendente" if "STATUS" in col else 0
            
            if 'QUANTIDADE' not in df_up.columns: df_up['QUANTIDADE'] = 0
            if 'CODIGO' not in df_up.columns: df_up['CODIGO'] = 'S/C'
            if 'DESCRICAO' not in df_up.columns: df_up['DESCRICAO'] = 'SEM NOME'
                
            df_up['TIPO'] = 'LISTA_ESTOQUE'
            db_data["analises"] = df_up.to_dict(orient='records')
            db_data["idx_solic"] = 0
            salvar_dados_op(db_data, mes_selecionado)
            st.success("Planilha importada com sucesso!"); st.rerun()

    # (As outras abas mantêm a lógica anterior, com o uso de .get() para segurança)
    with tab_novo:
        st.subheader("➕ Novo Item")
        with st.form("f_novo"):
            n_cod = st.text_input("Código").upper()
            n_desc = st.text_input("Descrição").upper()
            n_qtd = st.number_input("Qtd", min_value=1)
            if st.form_submit_button("Salvar"):
                novo = {"CODIGO": n_cod, "DESCRICAO": n_desc, "QUANTIDADE": n_qtd, "TIPO": "NOVO_DIRETORIA", "STATUS_COMPRA": "Pendente"}
                db_data["analises"].append(novo)
                salvar_dados_op(db_data, mes_selecionado); st.rerun()

    with tab_dash:
        df_dash = pd.DataFrame(db_data.get("analises", []))
        if not df_dash.empty:
            st.write("### Dashboard de Operação")
            # Uso seguro de colunas no dash
            q_col = 'QUANTIDADE' if 'QUANTIDADE' in df_dash.columns else df_dash.columns[0]
            st.bar_chart(df_dash, x='DESCRICAO' if 'DESCRICAO' in df_dash.columns else None, y=q_col)
