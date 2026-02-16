import streamlit as st
import pandas as pd
import plotly.express as px
import urllib.request

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.header("📊 Dashboard de Ações CX 2026")
    
    # URL de Download Direto
    URL_DIRETA = "https://colchoeskingstar.sharepoint.com/sites/PQI/Documentos%20Compartilhados/dados_planner.csv?download=1"
    
    try:
        # Configuração para pular o bloqueio de segurança que funcionou antes
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        
        # 1. Baixamos o conteúdo bruto do arquivo
        # 2. Lemos com separador de vírgula (conforme image_a4e3e4.png)
        # 3. 'on_bad_lines' e 'engine' tratam a bagunça das linhas
        df = pd.read_csv(
            URL_DIRETA, 
            sep=',', 
            encoding='utf-8', 
            on_bad_lines='skip', 
            engine='c'
        )
        
        # Limpa os nomes das colunas (Tarefa, Progresso, Bucket)
        df.columns = df.columns.str.strip()
        
        st.subheader("Visualização Real de Demandas (Planner King Star)")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Exibe a tabela organizada (ex: MATERIAL DE BLINDAGEM)
            st.dataframe(df, use_container_width=True)
            
        with col2:
            # Gráfico de Status (Progresso)
            if 'Progresso' in df.columns:
                # Converte para numérico caso o Python leia como texto
                df['Progresso'] = pd.to_numeric(df['Progresso'], errors='coerce').fillna(0)
                
                fig = px.pie(
                    df, 
                    names='Progresso', 
                    title="Distribuição por % de Conclusão",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Coluna 'Progresso' não encontrada no arquivo.")

        st.success(f"✅ Sincronizado! {len(df)} tarefas carregadas do SharePoint.")

    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
        st.info("💡 Verifique se o arquivo no SharePoint ainda contém os dados no formato: Tarefa,Progresso,Bucket")
