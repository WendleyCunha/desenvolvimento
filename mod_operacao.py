import streamlit as st
import pandas as pd
import plotly.express as px
from database import inicializar_db  

# --- FUNÇÕES DE DADOS ---
def carregar_estoque_firebase():
    db = inicializar_db()
    if not db: return {"analises": [], "idx_atual": 0, "picos": []}
    try:
        doc = db.collection("config").document("operacao_armazem").get()
        if doc.exists: 
            dados = doc.to_dict()
            if "picos" not in dados: dados["picos"] = []
            return dados
        return {"analises": [], "idx_atual": 0, "picos": []}
    except:
        return {"analises": [], "idx_atual": 0, "picos": []}

def salvar_estoque_firebase(dados):
    db = inicializar_db()
    if db:
        db.collection("config").document("operacao_armazem").set(dados)

# --- ABA 1: ANALISE DE COMPRAS ---
def aba_analise_compras():
    db_data = carregar_estoque_firebase()
    
    st.markdown("""
        <style>
            .metric-card {
                background: white; padding: 20px; border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-top: 4px solid #D4AF37;
                text-align: center; margin-bottom: 10px; color: #002366;
            }
        </style>
    """, unsafe_allow_html=True)

    # --- DIFERENCIAÇÃO DE SUBIDA (SETUP) ---
    if not db_data.get("analises") and not db_data.get("picos"):
        st.info("📦 Armazém 41: Aguardando carga de dados.")
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("🛒 Planilha de Compras")
            arq_c = st.file_uploader("Subir Projeção (Excel)", type=["xlsx"], key="up_compras")
            if arq_c:
                df_i = pd.read_excel(arq_c)
                df_i['SOLICITADO'] = df_i['QUANTIDADE'] if 'QUANTIDADE' in df_i.columns else 0
                cols_faltantes = ['STATUS', 'ANALISADO', 'QTD_COMPRADA', 'SALDO_VAL', 'STATUS_REC', 'QTD_RECEBIDA', 'CONFERIDO']
                for col in cols_faltantes:
                    df_i[col] = 0 if 'QTD' in col or 'VAL' in col else (False if col != 'STATUS_REC' else "Aguardando")
                df_i['STATUS'] = "Pendente"
                db_data["analises"] = df_i.to_dict(orient='records')
                salvar_estoque_firebase(db_data); st.rerun()

        with c2:
            st.subheader("🔥 Planilha de Picos")
            arq_p = st.file_uploader("Relatório Whats (Excel)", type=["xlsx"], key="up_picos")
            if arq_p:
                df_p = pd.read_excel(arq_p)
                db_data["picos"] = df_p.to_dict(orient='records')
                salvar_estoque_firebase(db_data); st.rerun()
        return

    # --- INTERFACE PRINCIPAL ---
    t_exec, t_dash, t_picos, t_rel = st.tabs(["🚀 Execução", "📊 Dash Compras", "🔥 Dash Picos", "📋 Relatório"])

    df = pd.DataFrame(db_data.get("analises", []))
    df_p = pd.DataFrame(db_data.get("picos", []))

    with t_exec:
        if not df.empty:
            idx = int(db_data.get("idx_atual", 0))
            if idx < len(df):
                item = df.iloc[idx]
                st.subheader(f"Item {idx+1} de {len(df)}")
                st.info(f"**Descrição:** {item.get('DESCRICAO', 'N/A')}")
                c1, c2, c3 = st.columns(3)
                with c1: saldo = st.number_input("Saldo em estoque:", min_value=0, key=f"sld_{idx}")
                with c2:
                    if st.button("✅ COMPRA TOTAL", use_container_width=True):
                        df.at[idx, 'STATUS'] = "Compra Efetuada"; df.at[idx, 'QTD_COMPRADA'] = item['SOLICITADO']
                        df.at[idx, 'SALDO_VAL'] = saldo; df.at[idx, 'ANALISADO'] = True
                        db_data["idx_atual"] = idx + 1; db_data["analises"] = df.to_dict(orient='records')
                        salvar_estoque_firebase(db_data); st.rerun()
                with c3:
                    if st.button("🔍 SEM ENCOMENDA", use_container_width=True):
                        df.at[idx, 'STATUS'] = "Sem Encomenda"; df.at[idx, 'SALDO_VAL'] = saldo; df.at[idx, 'ANALISADO'] = True
                        db_data["idx_atual"] = idx + 1; db_data["analises"] = df.to_dict(orient='records')
                        salvar_estoque_firebase(db_data); st.rerun()
            else:
                st.success("✅ Todas as análises foram concluídas!")
                if st.button("Reiniciar Processo"):
                    db_data["idx_atual"] = 0; salvar_estoque_firebase(db_data); st.rerun()
        else:
            st.warning("Nenhuma planilha de compras carregada.")

    with t_dash:
        if not df.empty:
            k1, k2, k3 = st.columns(3)
            analisados = len(df[df['ANALISADO'] == True])
            k1.markdown(f'<div class="metric-card"><h4>Total</h4><h2>{len(df)}</h2></div>', unsafe_allow_html=True)
            k2.markdown(f'<div class="metric-card"><h4>Analisados</h4><h2>{analisados}</h2></div>', unsafe_allow_html=True)
            k3.markdown(f'<div class="metric-card"><h4>Pendentes</h4><h2>{len(df) - analisados}</h2></div>', unsafe_allow_html=True)
            if analisados > 0:
                fig = px.pie(df, names='STATUS', title="Status das Operações", hole=0.4)
                st.plotly_chart(fig, use_container_width=True)

    with t_picos:
        if not df_p.empty:
            st.subheader("Análise de Picos (Tickets/Whats)")
            # Mapeamento automático das 6 colunas do seu arquivo
            df_p.columns = [c.strip().upper() for c in df_p.columns]
            col_tickets = [c for c in df_p.columns if 'TICKETS' in c][0]
            col_hora = [c for c in df_p.columns if 'HORA' in c][0]
            col_dia = [c for c in df_p.columns if 'DIA DA SEMANA' in c or 'SEMANA' in c][0]

            fig_pico = px.bar(df_p, x=col_hora, y=col_tickets, color=col_dia, title="Volume por Hora e Dia")
            st.plotly_chart(fig_pico, use_container_width=True)
            
            with st.expander("Ver dados brutos de picos"):
                st.dataframe(df_p, use_container_width=True)
        else:
            st.info("Aguardando upload da planilha de Picos em 'Relatório'.")

    with t_rel:
        if not df.empty:
            st.dataframe(df[['CODIGO', 'DESCRICAO', 'SOLICITADO', 'STATUS', 'QTD_COMPRADA']], use_container_width=True)
        if st.button("🗑️ Resetar Tudo (Compras e Picos)"):
            salvar_estoque_firebase({"analises": [], "idx_atual": 0, "picos": []})
            st.rerun()

# --- FUNÇÃO PRINCIPAL ---
def exibir_operacao_completa():
    st.title("📊 Gestão Operacional")
    
    sub_aba = st.segmented_control(
        "Selecione a área:", 
        ["🛒 Analise Compras", "🎧 Atendimento", "🎫 Chamados", "💬 Chat Interno"],
        default="🛒 Analise Compras"
    )

    st.divider()

    if sub_aba == "🛒 Analise Compras":
        aba_analise_compras()
    elif sub_aba == "🎧 Atendimento":
        st.info("Área de Atendimento em desenvolvimento...")
    elif sub_aba == "🎫 Chamados":
        st.info("Gestão de Chamados em desenvolvimento...")
    elif sub_aba == "💬 Chat Interno":
        st.info("Chat Interno em desenvolvimento...")
