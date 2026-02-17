import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import database as db  

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.title("👑 Hub King Star | Inteligência de Tickets")
    
    # --- 1. CARREGAMENTO DE DADOS DO BANCO ---
    try:
        dados_banco = db.carregar_tickets()
        if dados_banco:
            df_base = pd.DataFrame(dados_banco)
            # Normalização crucial: Garante que ID seja sempre String para comparar certo
            if 'ID do ticket' in df_base.columns:
                df_base['ID do ticket'] = df_base['ID do ticket'].astype(str)
        else:
            df_base = pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao conectar com o banco: {e}")
        df_base = pd.DataFrame()

    # --- 2. ÁREA DE UPLOAD E PERSISTÊNCIA ---
    with st.sidebar:
        st.header("📥 Alimentar Base")
        uploaded_file = st.file_uploader("Subir nova planilha", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_novo = pd.read_csv(uploaded_file)
                else:
                    df_novo = pd.read_excel(uploaded_file)
                
                # Limpeza básica: remove linhas totalmente vazias
                df_novo = df_novo.dropna(how='all')
                
                if 'ID do ticket' in df_novo.columns:
                    df_novo['ID do ticket'] = df_novo['ID do ticket'].astype(str)
                    st.success(f"{len(df_novo)} registros lidos no arquivo.")
                    
                    if st.button("🚀 GRAVAR NOVOS DADOS", use_container_width=True, type="primary"):
                        # Lógica de Deduplicação Robusta
                        if not df_base.empty:
                            ids_existentes = set(df_base['ID do ticket'].tolist())
                            df_filtrado = df_novo[~df_novo['ID do ticket'].isin(ids_existentes)]
                        else:
                            df_filtrado = df_novo
                        
                        if not df_filtrado.empty:
                            # Converte datas para string antes de enviar para o Firebase (evita erro de JSON)
                            df_para_gravar = df_filtrado.copy()
                            for col in df_para_gravar.columns:
                                if 'Data' in col or 'Criação' in col:
                                    df_para_gravar[col] = df_para_gravar[col].astype(str)
                            
                            novos_registros = df_para_gravar.to_dict('records')
                            db.salvar_tickets(novos_registros) 
                            st.balloons()
                            st.success(f"Sucesso! {len(df_filtrado)} novos tickets adicionados.")
                            st.rerun()
                        else:
                            st.warning("Todos os tickets deste arquivo já constam no banco.")
                else:
                    st.error("Coluna 'ID do ticket' não encontrada na planilha!")
            except Exception as e:
                st.error(f"Erro no processamento: {e}")

    # Se o banco estiver vazio, para aqui
    if df_base.empty:
        st.info("O banco de dados está vazio. Suba uma planilha para começar.")
        st.stop()

    # --- 3. TRATAMENTO E FILTROS DE ANÁLISE ---
    # Converte para data tratando erros (registros inválidos viram NaT)
    df_base['Criação do ticket - Data'] = pd.to_datetime(df_base['Criação do ticket - Data'], errors='coerce')
    df_base = df_base.dropna(subset=['Criação do ticket - Data'])
    df_base['Mes_Ano'] = df_base['Criação do ticket - Data'].dt.strftime('%m/%Y')
    
    with st.sidebar:
        st.divider()
        st.header("🔍 Filtros de Análise")
        meses_disponiveis = sorted(df_base['Mes_Ano'].unique(), reverse=True)
        mes_sel = st.selectbox("Escolha o Mês:", ["Todos"] + meses_disponiveis)

    df_view = df_base if mes_sel == "Todos" else df_base[df_base['Mes_Ano'] == mes_sel]

    # --- 4. DASHBOARD INTERATIVO ---
    tab_dash, tab_detalhes = st.tabs(["📊 Visão 360º", "📋 Detalhamento dos Dados"])

    with tab_dash:
        c1, c2, c3 = st.columns(3)
        c1.metric("Volume no Período", len(df_view))
        c2.metric("Lojas Atendidas", df_view['Nome do solicitante'].nunique() if 'Nome do solicitante' in df_view else 0)
        
        if 'Status do ticket' in df_view:
            taxa = (df_view['Status do ticket'] == 'Closed').mean() * 100
            c3.metric("Taxa de Conclusão", f"{taxa:.1f}%")

        st.divider()
        col_esq, col_dir = st.columns(2)
        
        with col_esq:
            st.subheader("🎯 O 80/20 de Motivos")
            col_motivo = 'Assunto CX:' if 'Assunto CX:' in df_view.columns else df_view.columns[0]
            df_pareto = df_view[col_motivo].value_counts().reset_index()
            df_pareto.columns = ['Motivo', 'Qtd']
            fig = px.bar(df_pareto.head(10), x='Motivo', y='Qtd', color='Qtd', color_continuous_scale='Blues')
            st.plotly_chart(fig, use_container_width=True)

        with col_dir:
            st.subheader("📈 Ranking por Loja")
            col_loja = 'Nome do solicitante' if 'Nome do solicitante' in df_view.columns else df_view.columns[0]
            df_loja = df_view[col_loja].value_counts().reset_index().head(10)
            df_loja.columns = ['Loja', 'Qtd']
            fig_loja = px.bar(df_loja, y='Loja', x='Qtd', orientation='h', color='Qtd', color_continuous_scale='GnBu')
            fig_loja.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_loja, use_container_width=True)

    with tab_detalhes:
        st.subheader("Lista Detalhada de Tickets")
        st.dataframe(df_view, use_container_width=True, hide_index=True)
        
        csv = df_view.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Exportar para Excel (CSV)", csv, "tickets.csv", "text/csv")

if __name__ == "__main__":
    exibir_teste_planner()
