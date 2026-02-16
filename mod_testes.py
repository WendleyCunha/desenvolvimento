import streamlit as st
import pandas as pd
import plotly.express as px

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.header("📊 Dashboard de Ações CX 2026")
    
    # 🔗 URL DE ACESSO DIRETO: O final '?download=1' é o que resolve o erro 403 Forbidden
    URL_DIRETA = "https://colchoeskingstar.sharepoint.com/sites/PQI/Documentos%20Compartilhados/dados_planner.csv?download=1"
    
    try:
        # Lendo os dados: forçamos o separador de vírgula que vimos no seu arquivo
        df = pd.read_csv(URL_DIRETA, sep=',', encoding='utf-8')
        
        # Limpa nomes de colunas (remove espaços que o SharePoint às vezes adiciona)
        df.columns = df.columns.str.strip()
        
        st.subheader("Visualização Real de Demandas (Planner King Star)")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Exibe a tabela com as tarefas reais (ex: MATERIAL DE BLINDAGEM)
            st.dataframe(df, use_container_width=True)
            
        with col2:
            # Cria o gráfico de pizza baseado na coluna 'Progresso'
            if 'Progresso' in df.columns:
                fig = px.pie(
                    df, 
                    names='Progresso', 
                    title="Status das Ações",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Coluna 'Progresso' não encontrada no CSV.")

        st.success(f"✅ Sincronizado! {len(df)} tarefas carregadas do SharePoint.")

    except Exception as e:
        st.error(f"Erro ao conectar com o SharePoint: {e}")
        st.info("Dica: Certifique-se de que o arquivo 'dados_planner.csv' existe na pasta raiz de Documentos do site PQI.")

if __name__ == "__main__":
    exibir_teste_planner()
