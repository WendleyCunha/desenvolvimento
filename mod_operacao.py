import streamlit as st
import pandas as pd
import plotly.express as px
from database import inicializar_db

# --- CONFIGURAÇÃO FIREBASE ---

def carregar_estoque_firebase():
    db = inicializar_db()
    if not db: return {"analises": [], "idx_atual": 0}
    try:
        doc = db.collection("config").document("operacao_armazem").get()
        if doc.exists:
            return doc.to_dict()
        return {"analises": [], "idx_atual": 0}
    except:
        return {"analises": [], "idx_atual": 0}

def salvar_estoque_firebase(dados):
    db = inicializar_db()
    if db:
        db.collection("config").document("operacao_armazem").set(dados)

def exibir_estoque():
    db_data = carregar_estoque_firebase()
    
    # Estilização CSS
    st.markdown("""
        <style>
            .metric-card {
                background: white; padding: 20px; border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-top: 4px solid #D4AF37;
                text-align: center; margin-bottom: 10px; color: #002366;
            }
        </style>
    """, unsafe_allow_html=True)

    # Verifica se há dados
    if not db_data.get("analises"):
        st.info("📦 Armazém 41: Aguardando carga de dados no Firebase.")
        arq = st.file_uploader("Subir Projeção Inicial (Excel)", type=["xlsx"])
        if arq:
            df_i = pd.read_excel(arq)
            df_i['SOLICITADO'] = df_i['QUANTIDADE'] if 'QUANTIDADE' in df_i.columns else 0
            cols_faltantes = ['STATUS', 'ANALISADO', 'QTD_COMPRADA', 'SALDO_VAL', 'STATUS_REC', 'QTD_RECEBIDA', 'CONFERIDO']
            for col in cols_faltantes:
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
            st.subheader(f"Item {idx+1} de {len(df)}")
            st.info(f"**Descrição:** {item.get('DESCRICAO', 'N/A')}")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                saldo = st.number_input("Saldo em estoque:", min_value=0, key=f"sld_{idx}")
            
            with c2:
                if st.button("✅ COMPRA TOTAL", use_container_width=True):
                    df.at[idx, 'STATUS'] = "Compra Efetuada"
                    df.at[idx, 'QTD_COMPRADA'] = item['SOLICITADO']
                    df.at[idx, 'SALDO_VAL'] = saldo
                    df.at[idx, 'ANALISADO'] = True
                    db_data["idx_atual"] = idx + 1
                    db_data["analises"] = df.to_dict(orient='records')
                    salvar_estoque_firebase(db_data)
                    st.rerun()
            
            with c3:
                if st.button("🔍 SEM ENCOMENDA", use_container_width=True):
                    df.at[idx, 'STATUS'] = "Sem Encomenda"
                    df.at[idx, 'SALDO_VAL'] = saldo
                    df.at[idx, 'ANALISADO'] = True
                    db_data["idx_atual"] = idx + 1
                    db_data["analises"] = df.to_dict(orient='records')
                    salvar_estoque_firebase(db_data)
                    st.rerun()
        else:
            st.success("✅ Todas as análises foram concluídas!")
            if st.button("Reiniciar Processo"):
                db_data["idx_atual"] = 0
                salvar_estoque_firebase(db_data)
                st.rerun()

    with t_dash:
        k1, k2, k3 = st.columns(3)
        total_itens = len(df)
        analisados = len(df[df['ANALISADO'] == True])
        
        k1.markdown(f'<div class="metric-card"><h4>Total Itens</h4><h2>{total_itens}</h2></div>', unsafe_allow_html=True)
        k2.markdown(f'<div class="metric-card"><h4>Analisados</h4><h2>{analisados}</h2></div>', unsafe_allow_html=True)
        k3.markdown(f'<div class="metric-card"><h4>Pendentes</h4><h2>{total_itens - analisados}</h2></div>', unsafe_allow_html=True)
        
        if analisados > 0:
            fig = px.pie(df, names='STATUS', title="Status das Operações", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

    with t_rel:
        st.dataframe(df[['CODIGO', 'DESCRICAO', 'SOLICITADO', 'STATUS', 'QTD_COMPRADA']], use_container_width=True)
        if st.button("Limpar Banco de Dados (CUIDADO)"):
            salvar_estoque_firebase({"analises": [], "idx_atual": 0})
            st.rerun()
