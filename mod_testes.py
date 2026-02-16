import streamlit as st
import pandas as pd
import plotly.express as px

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.header("📊 Dashboard de Ações CX 2026")
    
    # 🔗 LINK AJUSTADO: Usando o parâmetro ?download=1 para evitar o erro 403 Forbidden
    # Este link aponta diretamente para o arquivo que seu robô gera na pasta BackUp/Wendley
    URL_BASE = "https://colchoeskingstar.sharepoint.com/sites/PQI/Documentos%20Compartilhados/dados_planner.csv"
    URL_DIRETA = f"{URL_BASE}?download=1"
    
    try:
        # Lendo os dados reais
        # O 'sep' garante que o Python entenda a vírgula do CSV que vimos no seu Excel
        df = pd.read_csv(URL_DIRETA, sep=',', encoding='utf-8')
        
        # Limpeza rápida: Remove espaços extras que o Power Automate possa ter deixado
        df.columns = df.columns.str.strip()
        
        st.subheader("Visualização Real de Demandas (Planner King Star)")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Exibindo a tabela com os nomes reais como 'MATERIAL DE BLINDAGEM'
            st.dataframe(df, use_container_width=True)
            
        with col2:
            # Gerando o gráfico baseado na coluna 'Progresso'
            # Verificamos se a coluna existe para não dar erro na tela
            if 'Progresso' in df.columns:
                fig = px.pie(
                    df, 
                    names='Progresso', 
                    title="Resumo por Status",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Coluna 'Progresso' não detectada no arquivo.")

        st.success(f"✅ Sincronizado com sucesso! {len(df)} tarefas carregadas.")

    except Exception as e:
        st.error(f"Erro ao conectar com o SharePoint: {e}")
        st.info("Verifique se você está logado na rede da King Star ou se o link do arquivo mudou.")

# Para rodar localmente no teste:
if __name__ == "__main__":
    exibir_teste_planner()
