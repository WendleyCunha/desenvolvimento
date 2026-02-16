import streamlit as st
import pandas as pd
import plotly.express as px
import urllib.request

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.header("📊 Dashboard de Ações CX 2026")
    
    # URL de Download Direto
    URL_DIRETA = "https://colchoeskingstar.sharepoint.com/sites/PQI/Documentos%20Compartilhados/dados_planner.csv?download=1"
    
    try:
        # Simulando um navegador real para tentar enganar o Proxy/SharePoint
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        
        # Tentando baixar o arquivo para a memória
        df = pd.read_csv(URL_DIRETA, sep=',', encoding='utf-8')
        
        df.columns = df.columns.str.strip()
        st.subheader("Visualização Real de Demandas")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(df, use_container_width=True)
        with col2:
            if 'Progresso' in df.columns:
                fig = px.pie(df, names='Progresso', title="Status")
                st.plotly_chart(fig, use_container_width=True)
                
        st.success("✅ Sincronizado!")

    except Exception as e:
        st.error(f"Bloqueio de Segurança detectado: {e}")
        st.info("💡 Como o SharePoint da King Star bloqueou o acesso direto, vamos tentar o plano B.")
        
        # BOTÃO PARA CARREGAMENTO MANUAL (Enquanto resolvemos o bloqueio)
        uploaded_file = st.file_uploader("Para testar agora, baixe o arquivo do SharePoint e arraste-o aqui:", type="csv")
        if uploaded_file is not None:
            df_manual = pd.read_csv(uploaded_file)
            st.dataframe(df_manual)
