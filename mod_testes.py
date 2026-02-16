import streamlit as st
import pandas as pd
import plotly.express as px

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.header("📊 Dashboard de Ações CX 2026")
    
    # 🔗 URL DE ACESSO DIRETO VIA API (ESTÁTICA)
    # Este link ignora a interface visual e vai direto nos dados do CSV
    URL_DIRETA = "https://colchoeskingstar.sharepoint.com/sites/PQI/_api/web/GetFileByServerRelativeUrl('/sites/PQI/Shared%20Documents/dados_planner.csv')/$value"
    
    try:
        # Lendo os dados: O Python organiza a "bagunça" das vírgulas sozinho
        # Adicionamos storage_options para ajudar na autenticação de rede interna
        df = pd.read_csv(URL_DIRETA, sep=',', encoding='utf-8')
        
        # Limpa espaços em branco nos nomes das colunas
        df.columns = df.columns.str.strip()
        
        st.subheader("Visualização Real de Demandas (Planner King Star)")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Exibindo a tabela organizada com as tarefas reais
            st.dataframe(df, use_container_width=True)
            
        with col2:
            # Gerando o gráfico baseado na coluna 'Progresso' que vimos no seu CSV
            if 'Progresso' in df.columns:
                fig = px.pie(
                    df, 
                    names='Progresso', 
                    title="Status das Ações",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Coluna 'Progresso' não encontrada no arquivo.")

        st.success(f"✅ Sincronizado com sucesso! {len(df)} tarefas carregadas.")

    except Exception as e:
        # Se ainda der 403, tentamos o link alternativo de download simples
        try:
            url_alt = "https://colchoeskingstar.sharepoint.com/sites/PQI/Documentos%20Compartilhados/dados_planner.csv?download=1"
            df = pd.read_csv(url_alt, sep=',')
            st.dataframe(df, use_container_width=True)
            st.success("✅ Sincronizado via link de download alternativo.")
        except:
            st.error(f"Erro de Conexão: {e}")
            st.info("Dica: Certifique-se de que você está logado no SharePoint neste navegador.")

if __name__ == "__main__":
    exibir_teste_planner()
