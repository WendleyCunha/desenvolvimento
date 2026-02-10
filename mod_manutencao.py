import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    """
    Limpa nomes de colunas e prepara a base de dados.
    """
    # 1. Corrigir nomes de colunas (Encoding ANSI/UTF-8)
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]

    # 2. Padronização de nomes
    mapeamento = {
        'Dt Emissão': 'Data Emissão',
        'Dt EmissÃ£o': 'Data Emissão',
        'Valor Venda': 'Valor Venda',
        'Custo': 'Custo',
        'Pedido': 'Pedido',
        'Orçamento': 'Pedido' # Algumas planilhas usam Orçamento como ID
    }
    df.rename(columns=mapeamento, inplace=True)

    # 3. Conversão de Datas e Criação de Períodos
    if 'Data Emissão' in df.columns:
        df['Data Emissão'] = pd.to_datetime(df['Data Emissão'], errors='coerce')
        df = df.dropna(subset=['Data Emissão'])
        df['Ano_Mes'] = df['Data Emissão'].dt.to_period('M').astype(str)
        df['Semana_Ano'] = df['Data Emissão'].dt.isocalendar().week.astype(str)
        df['Data_Apenas'] = df['Data Emissão'].dt.date
    
    # 4. Tratamento Numérico
    cols_numericas = ['Valor Venda', 'Custo']
    for col in cols_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 5. Cálculo de Margem Individual (por linha)
    if 'Valor Venda' in df.columns and 'Custo' in df.columns:
        df['Margem R$'] = df['Valor Venda'] - df['Custo']
        
    return df

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    st.markdown("---")

    tab_dash, tab_config = st.tabs(["📊 Dashboard 360", "⚙️ Configurações"])

    with tab_config:
        st.subheader("Gerenciamento de Dados")
        arquivo = st.file_uploader("Subir planilha (.xlsx, .xls, .csv)", type=['xlsx', 'csv', 'xls'])
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin1')
                elif arquivo.name.endswith('.xls'):
                    df_raw = pd.read_excel(arquivo, engine='xlrd')
                else:
                    df_raw = pd.read_excel(arquivo, engine='openpyxl')
                
                df_limpo = tratar_dados(df_raw)
                st.session_state['dados_vendas'] = df_limpo
                st.success("Dados carregados e tratados!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro no processamento: {e}")

        if st.button("RESETAR SISTEMA", type="primary"):
            if 'dados_vendas' in st.session_state:
                del st.session_state['dados_vendas']
            st.rerun()

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # --- AJUSTE DE LÓGICA: PEDIDOS ÚNICOS ---
            # Faturamento Total é a soma de todas as linhas
            faturamento_total = df['Valor Venda'].sum()
            margem_total = df['Margem R$'].sum() if 'Margem R$' in df.columns else 0
            
            # Quantidade de Pedidos Únicos (Ignora repetições do mesmo ID)
            if 'Pedido' in df.columns:
                qtd_pedidos = df['Pedido'].nunique()
            else:
                qtd_pedidos = len(df) # Fallback caso a coluna não exista
                st.warning("Coluna 'Pedido' não encontrada. Contagem por linha.")

            # Ticket Médio Real: Faturamento / Qtd de Pedidos Únicos
            ticket_medio = faturamento_total / qtd_pedidos if qtd_pedidos > 0 else 0
            
            # KPIs formatados
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Vendas Totais", f"R$ {faturamento_total:,.2f}")
            c2.metric("Margem Bruta", f"R$ {margem_total:,.2f}")
            c3.metric("Qtd Pedidos (Únicos)", f"{qtd_pedidos}")
            c4.metric("Ticket Médio (Real)", f"R$ {ticket_medio:,.2f}")
                
            st.divider()
            
            # Gráfico de Evolução (Pedidos Únicos por Tempo)
            st.subheader("Evolução de Pedidos Únicos")
            if 'Data_Apenas' in df.columns and 'Pedido' in df.columns:
                visao = st.radio("Agrupar por:", ["Dia", "Semana", "Mês"], horizontal=True)
                mapa_tempo = {"Dia": "Data_Apenas", "Semana": "Semana_Ano", "Mês": "Ano_Mes"}
                
                # Agrupamos pelo tempo e contamos quantos Pedidos Únicos existem em cada data
                evolucao_pedidos = df.groupby(mapa_tempo[visao])['Pedido'].nunique()
                st.line_chart(evolucao_pedidos)

            st.divider()
            
            # Tabela de Conferência Agrupada
            st.subheader("Visualização por Pedido (Consolidado)")
            if 'Pedido' in df.columns:
                # Agrupamos para mostrar uma linha por pedido, somando os valores
                df_agrupado = df.groupby('Pedido').agg({
                    'Data Emissão': 'first',
                    'Filial': 'first',
                    'Valor Venda': 'sum',
                    'Margem R$': 'sum'
                }).reset_index().sort_values('Data Emissão', ascending=False)
                
                st.dataframe(df_agrupado.head(100), hide_index=True, use_container_width=True)

        else:
            st.info("Aguardando upload de dados.")
