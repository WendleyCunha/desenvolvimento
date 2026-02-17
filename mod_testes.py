import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import database as db  # Importando seu banco de dados existente

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.title("👑 Hub King Star | Inteligência de Tickets")
    
    # --- 1. CARREGAMENTO DE DADOS DO BANCO ---
    # Assume-se que você tenha uma função db.carregar_tickets() que retorna uma lista/DF
    # Se não existir, iniciamos um DF vazio para o primeiro uso
    try:
        dados_banco = db.carregar_tickets() 
        df_base = pd.DataFrame(dados_banco)
    except:
        df_base = pd.DataFrame(columns=['Criação do ticket - Data', 'ID do ticket', 'Nome do solicitante', 'Assunto CX:', 'Status do ticket'])

    # --- 2. ÁREA DE UPLOAD E PERSISTÊNCIA ---
    with st.sidebar:
        st.header("📥 Alimentar Base")
        uploaded_file = st.file_uploader("Subir nova planilha", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                # Leitura do arquivo
                if uploaded_file.name.endswith('.csv'):
                    df_novo = pd.read_csv(uploaded_file)
                else:
                    df_novo = pd.read_excel(uploaded_file)
                
                st.success(f"{len(df_novo)} registros lidos.")
                
                if st.button("🚀 GRAVAR NOVOS DADOS", use_container_width=True, type="primary"):
                    # Lógica de Deduplicação pelo ID do Ticket
                    ids_existentes = set(df_base['ID do ticket'].astype(str)) if not df_base.empty else set()
                    
                    # Filtra apenas o que NÃO está no banco (comparando IDs)
                    df_filtrado = df_novo[~df_novo['ID do ticket'].astype(str).isin(ids_existentes)]
                    
                    if not df_filtrado.empty:
                        novos_registros = df_filtrado.to_dict('records')
                        # Chama a função que você adicionou no database.py
                        db.salvar_tickets(novos_registros) 
                        st.balloons()
                        st.success(f"Sucesso! {len(df_filtrado)} novos tickets adicionados.")
                        st.rerun()
                    else:
                        st.warning("Todos os tickets deste arquivo já constam no banco.")
            except Exception as e:
                st.error(f"Erro no processamento: {e}")

    if df_base.empty:
        st.info("O banco de dados está vazio. Suba uma planilha na barra lateral para começar.")
        st.stop()

    # --- 3. TRATAMENTO E FILTROS DE ANÁLISE ---
    df_base['Criação do ticket - Data'] = pd.to_datetime(df_base['Criação do ticket - Data'])
    df_base['Mes_Ano'] = df_base['Criação do ticket - Data'].dt.strftime('%m/%Y')
    
    with st.sidebar:
        st.divider()
        st.header("🔍 Filtros de Análise")
        meses_disponiveis = sorted(df_base['Mes_Ano'].unique(), reverse=True)
        mes_sel = st.selectbox("Escolha o Mês:", ["Todos"] + meses_disponiveis)

    # Filtragem dos dados para o dashboard
    df_view = df_base if mes_sel == "Todos" else df_base[df_base['Mes_Ano'] == mes_sel]

    # --- 4. DASHBOARD INTERATIVO ---
    tab_dash, tab_detalhes = st.tabs(["📊 Visão 360º", "📋 Detalhamento dos Dados"])

    with tab_dash:
        # KPIs
        c1, c2, c3 = st.columns(3)
        c1.metric("Volume no Período", len(df_view))
        c2.metric("Lojas Atendidas", df_view['Nome do solicitante'].nunique())
        taxa_closed = (df_view['Status do ticket'] == 'Closed').mean() * 100
        c3.metric("Taxa de Conclusão", f"{taxa_closed:.1f}%")

        st.divider()
        
        col_esq, col_dir = st.columns(2)
        
        with col_esq:
            st.subheader("🎯 O 80/20 de Motivos")
            # Gráfico de Pareto baseado na imagem
            df_pareto = df_view['Assunto CX:'].value_counts().reset_index()
            df_pareto.columns = ['Motivo', 'Qtd']
            fig = px.bar(df_pareto.head(10), x='Motivo', y='Qtd', color='Qtd', color_continuous_scale='Blues')
            st.plotly_chart(fig, use_container_width=True)

        with col_dir:
            st.subheader("📈 Ranking por Loja")
            df_loja = df_view['Nome do solicitante'].value_counts().reset_index().head(10)
            df_loja.columns = ['Loja', 'Qtd']
            fig_loja = px.bar(df_loja, y='Loja', x='Qtd', orientation='h', color='Qtd', color_continuous_scale='GnBu')
            st.plotly_chart(fig_loja, use_container_width=True)

    with tab_detalhes:
        st.subheader("Lista Detalhada de Tickets")
        
        # Filtros extras na aba de detalhes
        c_f1, c_f2 = st.columns(2)
        loja_f = c_f1.multiselect("Filtrar Loja:", options=df_view['Nome do solicitante'].unique())
        status_f = c_f2.multiselect("Filtrar Status:", options=df_view['Status do ticket'].unique())

        df_final = df_view.copy()
        if loja_f: df_final = df_final[df_final['Nome do solicitante'].isin(loja_f)]
        if status_f: df_final = df_final[df_final['Status do ticket'].isin(status_f)]

        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        # Botão de Exportação para Excel/CSV
        csv = df_final.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar Dados Filtrados para Excel (CSV)",
            data=csv,
            file_name=f'tickets_kingstar_{mes_sel.replace("/", "_")}.csv',
            mime='text/csv',
            use_container_width=True
        )

# Para rodar direto se necessário
if __name__ == "__main__":
    exibir_teste_planner()
