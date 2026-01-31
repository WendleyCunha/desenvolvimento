import streamlit as st
import pandas as pd
import plotly.express as px
from database import inicializar_db  # Importação da conexão central

# --- FUNÇÕES DE DADOS (FIREBASE) ---

def carregar_estoque_firebase():
    db = inicializar_db()
    if not db: return {"analises": [], "idx_atual": 0}
    try:
        doc = db.collection("config").document("operacao_armazem").get()
        if doc.exists:
            dados = doc.to_dict()
            df = pd.DataFrame(dados.get("analises", []))
            if not df.empty:
                # Garante integridade das colunas
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

# --- INTERFACE E MÉTRICAS ---

def exibir_estoque():
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

    if not db_data.get("analises"):
        st.info("📦 Armazém 41: Aguardando carga de dados no Firebase.")
        arq = st.file_uploader("Subir Projeção Inicial (Excel)", type=["xlsx"], key="up_estoque")
        if arq:
            df_i = pd.read_excel(arq)
            df_i['SOLICITADO'] = df_i['QUANTIDADE'] if 'QUANTIDADE' in df_i.columns else 0
            for col in ['STATUS', 'ANALISADO', 'QTD_COMPRADA', 'SALDO_VAL', 'STATUS_REC', 'QTD_RECEBIDA', 'CONFERIDO']:
                df_i[col] = 0 if 'QTD' in col or 'VAL' in col else (False if col != 'STATUS_REC' else "Aguardando")
            df_i['STATUS'] = "Pendente"
            
            db_data = {"analises": df_i.to_dict(orient='records'), "idx_atual": 0}
            salvar_estoque_firebase(db_data)
            st.rerun()
        return

    df = pd.DataFrame(db_data["analises"])
    t_exec, t_dash, t_rel = st.tabs(["🚀 Execução", "📊 Dashboard", "📋 Relatório"])

    with t_exec:
        idx = int(db_data.get("idx_atual", 0))
        if idx < len(df):
            item = df.iloc[idx]
            st.subheader(f"Analisando: {item.get('DESCRICAO', 'Sem Descrição')}")
            
            c1, c2, c3 = st.columns(3)
            # Campo de entrada que estava faltando
            saldo = c1.number_input("Saldo encontrado em estoque:", min_value=0, key=f"sld_{idx}")
            
            if c2.button("✅ COMPRA TOTAL", use_container_width=True):
                df.at[idx, 'STATUS'] = "Compra Efetuada"
                df.at[idx, 'QTD_COMPRADA'] = item['SOLICITADO']
                df.at[idx, 'SALDO_VAL'] = saldo
                df.at[idx, 'ANALISADO'] = True
                db_data["idx_atual"] = idx + 1
                db_data["analises"] = df.to_dict(orient='records')
                salvar_estoque_firebase(db_data)
                st.rerun()

            if c3.button("🔍 SEM ENCOMENDA", use_container_width=True):
                df.at[idx, 'STATUS'] = "Sem Encomenda"
                df.at[idx, 'SALDO_VAL'] = saldo
                df.at[idx, 'ANALISADO'] = True
                db_data["idx_atual"] = idx + 1
                db_data["analises"] = df.to_dict(orient='records')
                salvar_estoque_firebase(db_data)
                st.rerun()
        else:
            st.success("✅ Todas as análises de estoque concluídas!")
            if st.button("Resetar Índice"):
                db_data["idx_atual"] = 0
                salvar_estoque_firebase(db_data)
                st.rerun()

    with t_dash:
        # Métricas Ajustadas
        col_m1, col_m2, col_m3 = st.columns(3)
        total_sol = df['SOLICITADO'].sum()
        total_com = df['QTD_COMPRADA'].sum()
        analisados = len(df[df['ANALISADO'] == True])

        col_m1.markdown(f'<div class="metric-card-estoque"><h4>Solicitado</h4><h2>{int(total_sol)}</h2></div>', unsafe_allow_html=True)
        col_m2.markdown(f'<div class="metric-card-estoque"><h4>Comprado</h4><h2>{int(total_com)}</h2></div>', unsafe_allow_html=True)
        col_m3.markdown(f'<div class="metric-card-estoque"><h4>Itens Analisados</h4><h2>{analisados}</h2></div>', unsafe_allow_html=True)
        
        fig = px.pie(df, names='STATUS', title="Composição da Operação", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

    with t_rel:
        st.dataframe(df[['CODIGO', 'DESCRICAO', 'SOLICITADO', 'STATUS', 'QTD_COMPRADA']], use_container_width=True)
