import streamlit as st
import pandas as pd

def tratar_dados(df):
    """Aplica as regras de negócio e limpeza de colunas"""
    # Corrige o encoding das colunas que vimos na imagem
    mapeamento = {
        'Dt EmissÃ£o': 'Data Emissão',
        'OrÃ§amento': 'Orçamento',
        'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)
    
    # Converte colunas para datetime (essencial para Dash 360)
    colunas_data = ['Data Emissão', 'Dt Age', 'Data Lib', 'Data Prev', 'Data Ent']
    for col in colunas_data:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            
    # Regra de Margem (Exemplo inicial)
    if 'Valor Venda' in df.columns and 'Custo' in df.columns:
        df['Margem R$'] = df['Valor Venda'] - df['Custo']
        
    return df

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    st.markdown("---")

    # Sistema de abas para organizar o Dash 360
    tab_upload, tab_dash = st.tabs(["📥 Subir Relatório", "📊 Dashboard 360"])

    with tab_upload:
        st.subheader("Upload de Dados Diários")
        arquivo = st.file_uploader("Arraste o relatório de vendas aqui", type=['xlsx', 'csv'])
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin1')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                df_limpo = tratar_dados(df_raw)
                st.session_state['dados_vendas'] = df_limpo
                st.success("Dados processados com sucesso!")
                st.dataframe(df_limpo.head(10))
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # KPI Cards
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Volume de Vendas", f"R$ {df['Valor Venda'].sum():,.2f}")
            with c2:
                st.metric("Ticket Médio", f"R$ {df['Valor Venda'].mean():,.2f}")
            with c3:
                st.metric("Total Pedidos", len(df))
                
            st.divider()
            st.subheader("Análise por Filial")
            st.bar_chart(df.groupby('Filial')['Valor Venda'].sum())
        else:
            st.info("Por favor, suba um arquivo na aba 'Subir Relatório' para visualizar os indicadores.")
