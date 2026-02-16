import streamlit as st
import pandas as pd
import plotly.express as px

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.header("📊 Dashboard de Ações CX 2026")
    
    # 🔗 O link oficial que você gerou no SharePoint da King Star
    URL_SHAREPOINT = "https://colchoeskingstar.sharepoint.com/sites/PQI/Documentos%20Compartilhados/dados_planner.csv"
    
    try:
        # Lendo os dados reais (O segredo: o Python organiza a "bagunça" do CSV sozinho)
        df = pd.read_csv(URL_SHAREPOINT)
        
        st.subheader("Visualização Real de Demandas (Planner King Star)")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Exibindo a tabela com Tarefa, Progresso e Bucket
            st.dataframe(df, use_container_width=True)
            
        with col2:
            # Gerando o gráfico baseado na coluna 'Progresso' (Não iniciado, Em andamento, Concluído)
            fig = px.pie(df, names='Progresso', title="Status das Ações", color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig, use_container_width=True)
            
        st.success(f"✅ Sincronizado com sucesso! Total de {len(df)} tarefas monitoradas.")

    except Exception as e:
        st.error(f"Erro ao conectar com o SharePoint: {e}")
        st.info("Verifique se o arquivo 'dados_planner.csv' está na pasta Documentos Compartilhados.")
