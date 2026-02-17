import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import database as db  # Certifique-se de que as funções acima foram adicionadas lá

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.title("📊 Indicadores 360º | Gestão de Tickets")
    
    # --- 1. CARREGAMENTO INICIAL (DO BANCO) ---
    try:
        dados_banco = db.carregar_tickets()
        df_base = pd.DataFrame(dados_banco)
        if not df_base.empty:
            df_base['ID do ticket'] = df_base['ID do ticket'].astype(str)
    except:
        df_base = pd.DataFrame()

    # --- 2. ÁREA DE ALIMENTAÇÃO (SIDEBAR) ---
    with st.sidebar:
        st.header("📥 Alimentar Dados")
        uploaded_file = st.file_uploader("Subir planilha de tickets", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                # Lógica para ler Excel ou CSV
                df_novo = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                df_novo['ID do ticket'] = df_novo['ID do ticket'].astype(str)
                
                st.info(f"Arquivo lido: {len(df_novo)} registros.")
                
                if st.button("🚀 GRAVAR NO BANCO DE DADOS", use_container_width=True, type="primary"):
                    # Verifica o que já existe para não duplicar
                    if not df_base.empty:
                        existentes = set(df_base['ID do ticket'])
                        df_para_gravar = df_novo[~df_novo['ID do ticket'].isin(existentes)]
                    else:
                        df_para_gravar = df_novo
                    
                    if not df_para_gravar.empty:
                        # Converte datas para string antes de enviar para o Firebase
                        df_para_gravar['Criação do ticket - Data'] = df_para_gravar['Criação do ticket - Data'].astype(str)
                        db.salvar_tickets(df_para_gravar.to_dict('records'))
                        st.success(f"Gravado! +{len(df_para_gravar)} novos registros.")
                        st.rerun()
                    else:
                        st.warning("Nada novo para gravar (IDs já existentes).")
            except Exception as e:
                st.error(f"Erro no upload: {e}")

    # Verificação: Se não houver dados em lugar nenhum, interrompe
    if df_base.empty:
        st.warning("⚠️ O banco de dados está vazio. Use a barra lateral para subir a primeira planilha.")
        st.stop()

    # --- 3. TRATAMENTO E FILTRO TEMPORAL ---
    df_base['Criação do ticket - Data'] = pd.to_datetime(df_base['Criação do ticket - Data'], errors='coerce')
    df_base = df_base.dropna(subset=['Criação do ticket - Data']) # Remove datas inválidas
    df_base['Mes_Ano'] = df_base['Criação do ticket - Data'].dt.strftime('%m/%Y')
    
    with st.sidebar:
        st.divider()
        st.header("🔍 Filtros")
        meses = sorted(df_base['Mes_Ano'].unique(), reverse=True)
        mes_sel = st.selectbox("Selecione o Mês de Análise:", ["Tudo"] + meses)

    # Aplica o filtro de mês
    df_view = df_base if mes_sel == "Tudo" else df_base[df_base['Mes_Ano'] == mes_sel]

    # --- 4. INTERFACE EM ABAS ---
    tab_graficos, tab_detalhes = st.tabs(["📊 Visão 360º", "📋 Detalhamento dos Dados"])

    with tab_graficos:
        # KPIs Rápidos
        total = len(df_view)
        resolvidos = len(df_view[df_view['Status do ticket'] == 'Closed'])
        taxa = (resolvidos/total*100) if total > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Tickets", total)
        c2.metric("Resolvidos", resolvidos)
        c3.metric("Taxa de Solução", f"{taxa:.1f}%")
        
        st.divider()
        
        col_esq, col_dir = st.columns(2)
        with col_esq:
            st.subheader("🎯 Motivos (Pareto)")
            df_motivo = df_view['Assunto CX:'].value_counts().reset_index()
            df_motivo.columns = ['Motivo', 'Qtd']
            fig_p = px.bar(df_motivo.head(10), x='Motivo', y='Qtd', color='Qtd', color_continuous_scale='Blues')
            st.plotly_chart(fig_p, use_container_width=True)
            
        with col_dir:
            st.subheader("🏪 Top Lojas")
            df_lojas = df_view['Nome do solicitante'].value_counts().head(10).reset_index()
            df_lojas.columns = ['Loja', 'Qtd']
            fig_l = px.bar(df_lojas, x='Qtd', y='Loja', orientation='h', color='Qtd')
            st.plotly_chart(fig_l, use_container_width=True)

    with tab_detalhes:
        st.subheader("🔍 Filtros de Tabela")
        col_f1, col_f2 = st.columns(2)
        loja_f = col_f1.multiselect("Filtrar por Loja:", options=df_view['Nome do solicitante'].unique())
        status_f = col_f2.multiselect("Filtrar por Status:", options=df_view['Status do ticket'].unique())
        
        df_final = df_view.copy()
        if loja_f: df_final = df_final[df_final['Nome do solicitante'].isin(loja_f)]
        if status_f: df_final = df_final[df_final['Status do ticket'].isin(status_f)]
        
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # Botão de Exportar
        csv_data = df_final.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Planilha Filtrada", csv_data, f"tickets_{mes_sel}.csv", "text/csv")

if __name__ == "__main__":
    exibir_teste_planner()
