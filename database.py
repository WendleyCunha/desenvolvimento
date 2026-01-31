import streamlit as st
import pandas as pd
import plotly.express as px
from database import inicializar_db # Importando sua conexão segura

# --- CONFIGURAÇÃO FIREBASE PARA OPERAÇÕES ---

def carregar_estoque_firebase():
    db = inicializar_db()
    if not db: return {"analises": [], "idx_atual": 0}
    try:
        # Busca a configuração da operação no Firestore
        doc = db.collection("config").document("operacao_armazem").get()
        if doc.exists:
            dados = doc.to_dict()
            # Garante que as colunas essenciais existam no DataFrame
            df = pd.DataFrame(dados.get("analises", []))
            if not df.empty:
                cols = ['SALDO_VAL', 'QTD_COMPRADA', 'STATUS_REC', 'QTD_RECEBIDA', 'CONFERIDO', 'ANALISADO', 'STATUS']
                for col in cols:
                    if col not in df.columns:
                        df[col] = 0 if 'QTD' in col or 'VAL' in col else (False if col != 'STATUS_REC' else "Aguardando")
                dados["analises"] = df.to_dict(orient='records')
            return dados
        return {"analises": [], "idx_atual": 0}
    except Exception as e:
        st.error(f"Erro ao carregar operações: {e}")
        return {"analises": [], "idx_atual": 0}

def salvar_estoque_firebase(dados):
    db = inicializar_db()
    if db:
        try:
            db.collection("config").document("operacao_armazem").set(dados)
        except Exception as e:
            st.error(f"Erro ao salvar operações: {e}")

# --- INTERFACE AJUSTADA ---

def exibir_estoque():
    # Agora carregamos do Firebase, não mais do JSON local!
    db_data = carregar_estoque_firebase()
    
    st.markdown("""
        <style>
            .metric-card-estoque {
                background: white; padding: 20px; border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-top: 4px solid #D4AF37;
                text-align: center; margin-bottom: 10px; color: #002366;
            }
        </style>
    """, unsafe_allow_html=True)

    if not db_data["analises"]:
        st.info("📦 Armazém 41: Aguardando carga de dados no Firebase.")
        arq = st.file_uploader("Subir Projeção Inicial (Excel)", type=["xlsx"], key="up_estoque")
        if arq:
            df_i = pd.read_excel(arq)
            # ... (seu processamento de colunas permanece igual)
            df_i['SOLICITADO'] = df_i['QUANTIDADE'] if 'QUANTIDADE' in df_i.columns else 0
            for col in ['STATUS', 'ANALISADO', 'QTD_COMPRADA', 'SALDO_VAL', 'STATUS_REC', 'QTD_RECEBIDA', 'CONFERIDO']:
                df_i[col] = 0 if 'QTD' in col or 'VAL' in col else (False if col != 'STATUS_REC' else "Aguardando")
            df_i['STATUS'] = "Pendente"
            
            db_data["analises"] = df_i.to_dict(orient='records')
            db_data["idx_atual"] = 0
            salvar_estoque_firebase(db_data)
            st.rerun()
        return

    # O RESTANTE DO SEU CÓDIGO DE TABS (Execução, Recebimento, etc)
    # APENAS TROQUE: salvar_db(db_data) por salvar_estoque_firebase(db_data)
    
    df = pd.DataFrame(db_data["analises"])
    t_exec, t_dash, t_rel = st.tabs(["🚀 Execução", "📊 Dashboard", "📋 Relatório"])

    with t_exec:
        idx = int(db_data.get("idx_atual", 0))
        if idx < len(df):
            item = df.iloc[idx]
            st.subheader(f"Analisando: {item.get('DESCRICAO', 'Sem Descrição')}")
            # ... campos de input e botões
            if st.button("✅ COMPRA TOTAL"):
                df.at[idx, 'STATUS'] = "Compra Efetuada"
                db_data["idx_atual"] = idx + 1
                db_data["analises"] = df.to_dict(orient='records')
                salvar_estoque_firebase(db_data)
                st.rerun()
        else:
            st.success("✅ Concluído!")
            if st.button("Resetar"):
                db_data["idx_atual"] = 0
                salvar_estoque_firebase(db_data)
                st.rerun()
