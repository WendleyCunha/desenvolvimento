import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    """
    Limpa nomes de colunas com erros de encoding e aplica regras iniciais.
    """
    # 1. Corrigir nomes de colunas (Encoding ANSI/UTF-8)
    # Transforma 'Dt EmissÃ£o' em 'Dt Emissão' automaticamente
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]

    # 2. Padronização de Nomes Críticos para o Código
    mapeamento = {
        'Dt Emissão': 'Data Emissão',
        'Dt EmissÃ£o': 'Data Emissão', # Backup caso o decode falhe
        'Valor Venda': 'Valor Venda',
        'Custo': 'Custo'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 3. Conversão de Datas
    colunas_data = ['Data Emissão', 'Dt Age', 'Data Lib', 'Data Prev', 'Data Ent']
    for col in colunas_data:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # 4. Regras de Negócio (Margem e Lucro)
    if 'Valor Venda' in df.columns and 'Custo' in df.columns:
        # Garante que os valores sejam numéricos
        df['Valor Venda'] = pd.to_numeric(df['Valor Venda'], errors='coerce').fillna(0)
        df['Custo'] = pd.to_numeric(df['Custo'], errors='coerce').fillna(0)
        
        df['Margem R$'] = df['Valor Venda'] - df['Custo']
        df['Margem %'] = (df['Margem R$'] / df['Valor Venda'].replace(0, np.nan) * 100).round(2)

    # 5. Regra de Dia da Semana (Para controle de Fim de Semana)
    if 'Data Emissão' in df.columns:
        df['Dia Semana'] = df['Data Emissão'].dt.day_name()
        
    return df

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    st.markdown("---")

    # Sistema de abas para organizar o processo
    tab_upload, tab_dash = st.tabs(["📥 Subir Relatório", "📊 Dashboard 360"])

    with tab_upload:
        st.subheader("Upload de Dados")
        st.info("Formatos aceitos: .xlsx, .xls (Excel Antigo) e .csv")
        
        # Inclusão do 'xls' nos tipos permitidos
        arquivo = st.file_uploader("Selecione a planilha diária", type=['xlsx', 'csv', 'xls'])
        
        if arquivo:
            try:
                # Lógica de leitura baseada na extensão
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin1')
                elif arquivo.name.endswith('.xls'):
                    # Requer biblioteca 'xlrd' no requirements.txt
                    df_raw = pd.read_excel(arquivo, engine='xlrd')
                else:
                    # Requer biblioteca 'openpyxl' no requirements.txt
                    df_raw = pd.read_excel(arquivo, engine='openpyxl')
                
                with st.spinner('Aplicando regras de negócio...'):
                    df_limpo = tratar_dados(df_raw)
                    st.session_state['dados_vendas'] = df_limpo
                    st.success(f"Arquivo '{arquivo.name}' processado!")
                
                st.dataframe(df_limpo.head(10), use_container_width=True)
                
            except Exception as e:
                st.error(f"Erro ao processar o arquivo: {e}")
                st.warning("Dica: Verifique se o arquivo não está aberto no seu computador.")

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # --- KPIs SUPERIORES ---
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Vendas Totais", f"R$ {df['Valor Venda'].sum():,.2f}")
            with c2:
                st.metric("Margem Bruta", f"R$ {df.get('Margem R$', pd.Series([0])).sum():,.2f}")
            with c3:
                st.metric("Qtd Pedidos", len(df))
            with c4:
                media = df['Valor Venda'].mean()
                st.metric("Ticket Médio", f"R$ {media:,.2f}")
                
            st.divider()
            
            # --- GRÁFICOS ---
            col_graf1, col_graf2 = st.columns(2)
            
            with col_graf1:
                st.subheader("Vendas por Filial")
                vendas_filial = df.groupby('Filial')['Valor Venda'].sum().sort_values(ascending=False)
                st.bar_chart(vendas_filial)
                
            with col_graf2:
                st.subheader("Vendas por Tipo")
                if 'Tipo Venda' in df.columns:
                    vendas_tipo = df.groupby('Tipo Venda')['Valor Venda'].count()
                    st.pie_chart(vendas_tipo)

        else:
            st.info("Aguardando upload de dados para gerar o Dashboard.")
