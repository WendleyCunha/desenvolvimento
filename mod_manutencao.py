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

    # 2. Padronização de Nomes Críticos
    mapeamento = {
        'Dt Emissão': 'Data Emissão',
        'Dt EmissÃ£o': 'Data Emissão',
        'Valor Venda': 'Valor Venda',
        'Custo': 'Custo'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 3. Conversão de Datas e Criação de Períodos (Dia, Semana, Mês)
    colunas_data = ['Data Emissão', 'Dt Age', 'Data Lib', 'Data Prev', 'Data Ent']
    for col in colunas_data:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    if 'Data Emissão' in df.columns:
        # Criar colunas de agrupamento temporal
        df['Ano_Mes'] = df['Data Emissão'].dt.to_period('M').astype(str)
        df['Semana_Ano'] = df['Data Emissão'].dt.isocalendar().week
        df['Dia_Semana_Nome'] = df['Data Emissão'].dt.day_name()
        df['Data_Apenas'] = df['Data Emissão'].dt.date

    # 4. Regras de Negócio (Margem e Lucro)
    if 'Valor Venda' in df.columns and 'Custo' in df.columns:
        df['Valor Venda'] = pd.to_numeric(df['Valor Venda'], errors='coerce').fillna(0)
        df['Custo'] = pd.to_numeric(df['Custo'], errors='coerce').fillna(0)
        
        df['Margem R$'] = df['Valor Venda'] - df['Custo']
        df['Margem %'] = (df['Margem R$'] / df['Valor Venda'].replace(0, np.nan) * 100).round(2)
        
    return df

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    st.markdown("---")

    tab_upload, tab_dash = st.tabs(["📥 Subir Relatório", "📊 Dashboard 360"])

    with tab_upload:
        st.subheader("Upload de Dados Diários")
        arquivo = st.file_uploader("Selecione a planilha (.xlsx, .xls ou .csv)", type=['xlsx', 'csv', 'xls'])
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin1')
                elif arquivo.name.endswith('.xls'):
                    df_raw = pd.read_excel(arquivo, engine='xlrd')
                else:
                    df_raw = pd.read_excel(arquivo, engine='openpyxl')
                
                with st.spinner('Processando dados...'):
                    df_limpo = tratar_dados(df_raw)
                    st.session_state['dados_vendas'] = df_limpo
                    st.success(f"Arquivo '{arquivo.name}' carregado com sucesso!")
                
                st.dataframe(df_limpo.head(10), use_container_width=True)
                
            except Exception as e:
                st.error(f"Erro ao processar: {e}")

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # --- KPIs ---
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("Vendas Totais", f"R$ {df['Valor Venda'].sum():,.2f}")
            with c2: st.metric("Margem Total", f"R$ {df.get('Margem R$', pd.Series([0])).sum():,.2f}")
            with c3: st.metric("Total Pedidos", len(df))
            with c4: st.metric("Ticket Médio", f"R$ {df['Valor Venda'].mean():,.2f}")
                
            st.divider()
            
            # --- SELETOR DE VISÃO TEMPORAL ---
            st.subheader("Análise Temporal")
            visao = st.radio("Agrupar por:", ["Dia", "Semana", "Mês"], horizontal=True)
            
            mapa_tempo = {"Dia": "Data_Apenas", "Semana": "Semana_Ano", "Mês": "Ano_Mes"}
            col_tempo = mapa_tempo[visao]
            
            vendas_tempo = df.groupby(col_tempo)['Valor Venda'].sum()
            st.line_chart(vendas_tempo)

            st.divider()
            
            col_graf1, col_graf2 = st.columns(2)
            with col_graf1:
                st.subheader("Vendas por Filial")
                st.bar_chart(df.groupby('Filial')['Valor Venda'].sum())
                
            with col_graf2:
                st.subheader("Distribuição por Tipo")
                if 'Tipo Venda' in df.columns:
                    # Correção do erro: Convertendo Series para DataFrame para o gráfico
                    vendas_tipo = df['Tipo Venda'].value_counts().reset_index()
                    vendas_tipo.columns = ['Tipo', 'Quantidade']
                    st.dataframe(vendas_tipo, hide_index=True, use_container_width=True)
                    # st.pie_chart alternativo para evitar erros de versão:
                    st.bar_chart(vendas_tipo.set_index('Tipo'))

        else:
            st.info("Aguardando upload de dados.")
