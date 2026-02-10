import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    """
    Limpa nomes de colunas e prepara a base de dados.
    """
    # 1. Corrigir nomes de colunas (Encoding ANSI/UTF-8 para evitar Dt EmissÃ£o)
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]

    # 2. Padronização de nomes (Ajuste para Tipo Venda e Pedido)
    mapeamento = {
        'Dt Emissão': 'Data Emissão',
        'Dt EmissÃ£o': 'Data Emissão',
        'Valor Venda': 'Valor Venda',
        'Custo': 'Custo',
        'Pedido': 'Pedido',
        'Orçamento': 'Pedido',
        'Tipo Venda': 'Tipo Venda'
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
    for col in ['Valor Venda', 'Custo']:
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
            
            # --- AJUSTE 1: LÓGICA DE PEDIDOS ÚNICOS ---
            faturamento_total = df['Valor Venda'].sum()
            margem_total = df['Margem R$'].sum() if 'Margem R$' in df.columns else 0
            
            # Criamos um DataFrame consolidado por pedido para métricas de contagem e tipo
            # Isso garante que se um pedido tem 10 linhas, ele conta como 1 para o Tipo Venda
            df_pedidos_unicos = df.drop_duplicates(subset=['Pedido']).copy()
            qtd_pedidos = len(df_pedidos_unicos)

            ticket_medio = faturamento_total / qtd_pedidos if qtd_pedidos > 0 else 0
            
            # KPIs formatados
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Vendas Totais", f"R$ {faturamento_total:,.2f}")
            c2.metric("Margem Bruta", f"R$ {margem_total:,.2f}")
            c3.metric("Qtd Pedidos (Únicos)", f"{qtd_pedidos}")
            c4.metric("Ticket Médio (Real)", f"R$ {ticket_medio:,.2f}")
                
            st.divider()
            
            # --- AJUSTE 2: ANÁLISE POR TIPO DE VENDA (PORCENTAGEM) ---
            st.subheader("Distribuição por Tipo de Venda (Base: Pedidos Únicos)")
            
            if 'Tipo Venda' in df_pedidos_unicos.columns:
                # Contagem de pedidos únicos para cada tipo
                contagem_tipo = df_pedidos_unicos['Tipo Venda'].value_counts()
                porcentagem_tipo = (contagem_tipo / qtd_pedidos * 100).round(2)
                
                # Criando colunas para exibir os 3 itens solicitados com destaque
                col_t1, col_t2, col_t3 = st.columns(3)
                
                tipos_alvo = {
                    "002-RETIRA": col_t1,
                    "003-ENTREGA": col_t2,
                    "004-ENCOMENDA": col_t3
                }
                
                for nome, col in tipos_alvo.items():
                    val = porcentagem_tipo.get(nome, 0)
                    qtd = contagem_tipo.get(nome, 0)
                    col.metric(nome, f"{val}%", f"{qtd} pedidos")

                # Gráfico visual da distribuição
                st.bar_chart(porcentagem_tipo)
            else:
                st.warning("Coluna 'Tipo Venda' não encontrada para análise de porcentagem.")

            st.divider()
            
            # Gráfico de Evolução Temporária (Pedidos Únicos)
            if 'Data_Apenas' in df_pedidos_unicos.columns:
                st.subheader("Evolução Diária de Pedidos")
                evolucao = df_pedidos_unicos.groupby('Data_Apenas').size()
                st.line_chart(evolucao)

        else:
            st.info("Aguardando upload de dados.")
