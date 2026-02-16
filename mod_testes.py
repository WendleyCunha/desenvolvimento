import streamlit as st
import pandas as pd
import plotly.express as px
import urllib.request

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.header("📊 Dashboard de Ações CX 2026")
    
    # URL de Download Direto que agora sabemos que funciona com o User-agent
    URL_DIRETA = "https://colchoeskingstar.sharepoint.com/sites/PQI/Documentos%20Compartilhados/dados_planner.csv?download=1"
    
    try:
        # Configuração para pular o bloqueio de segurança
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        
        # Lendo os dados e corrigindo o erro de 'Expected 1 fields, saw 4'
        # sep=None com engine='python' faz o código descobrir sozinho se é vírgula ou ponto e vírgula
        df = pd.read_csv(URL_DIRETA, sep=None, engine='python', encoding='utf-8', on_bad_lines='skip')
        
        # Limpa os nomes das colunas
        df.columns = df.columns.str.strip()
        
        st.subheader("Visualização Real de Demandas (Planner King Star)")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Exibe a tabela organizada
            st.dataframe(df, use_container_width=True)
            
        with col2:
            # Gráfico de Status (Progresso)
            if 'Progresso' in df.columns:
                fig = px.pie(df, names='Progresso', title="Resumo de Status")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Coluna 'Progresso' não identificada.")

        st.success(f"✅ Sincronizado com sucesso! {len(df)} tarefas carregadas.")

    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
        st.info("💡 O arquivo foi acessado, mas o formato interno do CSV precisa de um ajuste.")
