import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    """
    Limpa nomes de colunas com erros de encoding e aplica regras iniciais.
    """
    # 1. Corrigir nomes de colunas (Encoding ANSI/UTF-8)
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]

    # 2. Padronização de nomes para garantir que o código encontre as colunas
    # Mapeamos variações comuns que podem vir do ERP
    mapeamento = {
        'Dt Emissão': 'Data Emissão',
        'Dt EmissÃ£o': 'Data Emissão',
        'Valor Venda': 'Valor Venda',
        'Custo': 'Custo',
        'Filial': 'Filial',
        'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 3. Conversão de Datas e Criação de Períodos
    colunas_data = ['Data Emissão', 'Dt Age', 'Data Lib', 'Data Prev', 'Data Ent']
    for col in colunas_data:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Criar colunas temporais apenas se a coluna de data existir
    if 'Data Emissão' in df.columns:
        # Remover linhas com datas inválidas para não quebrar o gráfico
        df = df.dropna(subset=['Data Emissão'])
        df['Ano_Mes'] = df['Data Emissão'].dt.to_period('M').astype(str)
        df['Semana_Ano'] = df['Data Emissão'].dt.isocalendar().week.astype(str)
        df['Data_Apenas'] = df['Data Emissão'].dt.date
    
    # 4. Tratamento Numérico
    cols_numericas = ['Valor Venda', 'Custo']
    for col in cols_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 5. Cálculo de Margem
    if 'Valor Venda' in df.columns and 'Custo' in df.columns:
        df['Margem R$'] = df['Valor Venda'] - df['Custo']
        df['Margem %'] = (df['Margem R$'] / df['Valor Venda'].replace(0, np.nan) * 100).round(2)
        
    return df

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    st.markdown("---")

    # Sistema de abas atualizado
    tab_dash, tab_config = st.tabs(["📊 Dashboard 360", "⚙️ Configurações"])

    # --- ABA DE CONFIGURAÇÕES (Reset e Upload) ---
    with tab_config:
        st.subheader("Gerenciamento de Dados")
        
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            st.write("### 📥 Upload")
            arquivo = st.file_uploader("Subir nova planilha (.xlsx, .xls, .csv)", type=['xlsx', 'csv', 'xls'])
            
            if arquivo:
                try:
                    if arquivo.name.endswith('.csv'):
                        df_raw = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin1')
                    elif arquivo.name.endswith('.xls'):
                        df_raw = pd.read_excel(arquivo, engine='xlrd')
                    else:
                        df_raw = pd.read_excel(arquivo, engine='openpyxl')
                    
                    with st.spinner('Processando...'):
                        df_limpo = tratar_dados(df_raw)
                        st.session_state['dados_vendas'] = df_limpo
                        st.success("Dados carregados!")
                        st.rerun() # Atualiza a tela para mostrar no Dash
                except Exception as e:
                    st.error(f"Erro: {e}")

        with col_c2:
            st.write("### 🧹 Reset")
            st.warning("Isso limpará os dados da sessão atual.")
            if st.button("RESETAR SISTEMA", type="primary", use_container_width=True):
                if 'dados_vendas' in st.session_state:
                    del st.session_state['dados_vendas']
                st.success("Dados limpos!")
                st.rerun()

    # --- ABA DO DASHBOARD ---
    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Vendas Totais", f"R$ {df['Valor Venda'].sum():,.2f}")
            c2.metric("Margem Bruta", f"R$ {df.get('Margem R$', pd.Series([0])).sum():,.2f}")
            c3.metric("Qtd Pedidos", len(df))
            c4.metric("Ticket Médio", f"R$ {df['Valor Venda'].mean():,.2f}")
                
            st.divider()
            
            # Visão Temporal com Tratamento de Erro (KeyError Fix)
            st.subheader("Análise Temporal")
            if 'Data_Apenas' in df.columns:
                visao = st.radio("Agrupar por:", ["Dia", "Semana", "Mês"], horizontal=True)
                mapa_tempo = {"Dia": "Data_Apenas", "Semana": "Semana_Ano", "Mês": "Ano_Mes"}
                
                vendas_tempo = df.groupby(mapa_tempo[visao])['Valor Venda'].sum()
                st.line_chart(vendas_tempo)
            else:
                st.warning("Coluna de data não encontrada para gerar gráfico temporal.")

            st.divider()
            
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.subheader("Vendas por Filial")
                if 'Filial' in df.columns:
                    st.bar_chart(df.groupby('Filial')['Valor Venda'].sum())
            
            with col_g2:
                st.subheader("Detalhamento")
                st.dataframe(df[['Data Emissão', 'Filial', 'Valor Venda', 'Margem %']].head(50), hide_index=True)
        else:
            st.info("Nenhum dado carregado. Vá em 'Configurações' para subir uma planilha.")
