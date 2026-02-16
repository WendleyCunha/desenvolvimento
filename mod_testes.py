import streamlit as st
import pandas as pd
import plotly.express as px

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.header("🧪 Central de Testes & API Planner")
    
    # Exemplo de como você organizaria as tarefas para o gestor
    st.subheader("Visualização Clara de Demandas (AÇÕES CX 2026)")
    
    # Simulando dados que viriam da API do Planner
    dados_planner = [
        {"Tarefa": "Ajustar KPI Compras", "Status": "Em Andamento", "Prazo": "2026-02-20", "Responsável": "Você"},
        {"Tarefa": "Integração Graph API", "Status": "Teste", "Prazo": "2026-02-25", "Responsável": "TI"},
        {"Tarefa": "Dashboard Recebimento", "Status": "Concluído", "Prazo": "2026-02-15", "Responsável": "Você"},
    ]
    df = pd.DataFrame(dados_planner)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.dataframe(df, use_container_width=True)
        
    with col2:
        fig = px.pie(df, names='Status', title="Resumo por Status")
        st.plotly_chart(fig, use_container_width=True)

    if st.button("🔄 Sincronizar com Microsoft Graph (API)"):
        st.warning("Aqui entrará a chamada da API para ler o Planner Cloud.")
