import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    """
    Limpa nomes de colunas e prepara dados.
    """
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]

    mapeamento = {
        'Dt Emissão': 'Data Emissão',
        'Dt EmissÃ£o': 'Data Emissão',
        'Valor Venda': 'Valor Venda',
        'Custo': 'Custo',
        'Pedido': 'Pedido',
        'Orçamento': 'Pedido' # Caso o PV venha como Orçamento em algum relatório
    }
    df.rename(columns=mapeamento, inplace=True)

    # Conversão de Datas
    if 'Data Emissão' in df.columns:
        df['Data Emissão'] = pd.to_datetime(df['Data Emissão'], errors='coerce')
        df = df.dropna(subset=['Data Emissão'])
        df['Ano_Mes'] = df['Data Emissão'].dt.to_period('M').astype(str)
        df['Semana_Ano'] = df['Data Emissão'].dt.isocalendar().week.astype(str)
        df['Data_Apenas'] = df['Data Emissão'].dt.date
    
    # Tratamento Numérico
    for col in ['Valor Venda', 'Custo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    st.markdown("---")

    tab_dash, tab_config = st.tabs(["📊 Dashboard 360", "⚙️ Configurações"])

    with tab_config:
        st.subheader("Gerenciamento de Dados")
        arquivo = st.file_uploader("Subir planilha", type=['xlsx', 'csv', 'xls'])
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin1')
                else:
                    engine = 'xlrd' if arquivo.name.endswith('.xls') else 'openpyxl'
                    df_raw = pd.read_excel(arquivo, engine=engine)
                
                df_limpo = tratar_dados(df_raw)
                st.session_state['dados_vendas'] = df_limpo
                st.success("Dados carregados!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

        if st.button("RESETAR SISTEMA", type="primary"):
            if 'dados_vendas' in st.session_state:
                del st.session_state['dados_vendas']
            st.rerun()

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # --- LÓGICA DE UNICIDADE ---
            # Se o pedido se repete, somamos o valor total mas contamos apenas 1 pedido
            total_vendas = df['Valor Venda'].sum()
            
            # Aqui está o "pulo do gato": contar valores únicos na coluna Pedido
            qtd_pedidos_reais = df['Pedido'].nunique() if 'Pedido' in df.columns else 0
            
            # Ticket Médio Real: Total vendido / Quantidade de Pedidos Únicos
            ticket_medio_real = total_vendas / qtd_pedidos_reais if qtd_pedidos_reais > 0 else 0
            
            # KPIs
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Faturamento Total", f"R$ {total_vendas:,.2f}")
            c2.metric("Qtd Pedidos (Únicos)", qtd_pedidos_reais)
            c3.metric("Ticket Médio (p/ Pedido)", f"R$ {ticket_medio_real:,.2f}")
            
            margem_bruta = (df['Valor Venda'].sum() - df['Custo'].sum())
            c4.metric("Margem Bruta", f"R$ {margem_bruta:,.2f}")
                
            st.divider()
            
            # --- ANÁLISE POR DATA (CONSIDERANDO PEDIDOS ÚNICOS) ---
            if 'Data_Apenas' in df.columns:
                st.subheader("Evolução de Pedidos Únicos")
                visao = st.radio("Agrupar por:", ["Dia", "Semana", "Mês"], horizontal=True, key="temp_radio")
                mapa_tempo = {"Dia": "Data_Apenas", "Semana": "Semana_Ano", "Mês": "Ano_Mes"}
                
                # Agrupando por tempo e contando quantos pedidos únicos existem em cada período
                pedidos_tempo = df.groupby(mapa_tempo[visao])['Pedido'].nunique()
                st.line_chart(pedidos_tempo)
                
            st.divider()
            
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.subheader("Faturamento por Filial")
                st.bar_chart(df.groupby('Filial')['Valor Venda'].sum())
            
            with col_g2:
                st.subheader("Últimos Pedidos Processados")
                # Mostra a lista sem repetir o mesmo pedido várias vezes (agrupado)
                resumo_pedidos = df.groupby('Pedido').agg({
                    'Data Emissão': 'first',
                    'Filial': 'first',
                    'Valor Venda': 'sum'
                }).reset_index().sort_values('Data Emissão', ascending=False)
                st.dataframe(resumo_pedidos.head(20), hide_index=True)
        else:
            st.info("Aguardando upload de dados nas Configurações.")
