import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =========================================================
# 1. TRATAMENTO DE DADOS (AGORA COM DEEP SEARCH DE COLUNAS)
# =========================================================
def tratar_dados(df):
    # Limpeza básica de nomes
    df.columns = [str(col).strip() for col in df.columns]
    
    # Mapeamento Inteligente (Busca por palavras-chave para evitar KeyError)
    novas_colunas = {}
    for col in df.columns:
        c_upper = col.upper()
        if 'EMISS' in c_upper: novas_colunas[col] = 'Data Emissão'
        elif 'ENT' in c_upper and 'DATA' in c_upper: novas_colunas[col] = 'Data Entrega'
        elif 'OR' in c_upper and 'AMENTO' in c_upper: novas_colunas[col] = 'Orçamento'
        elif 'PED' in c_upper and 'IDO' in c_upper: novas_colunas[col] = 'Pedido'
        elif 'TIPO' in c_upper and 'VENDA' in c_upper: novas_colunas[col] = 'Tipo Venda'
        elif 'PROD' in c_upper: novas_colunas[col] = 'Produto'
        elif 'QTD' in c_upper: novas_colunas[col] = 'Qtd'
    
    df.rename(columns=novas_colunas, inplace=True)

    # Garantir que as colunas críticas existam (mesmo que vazias) para não quebrar o código
    colunas_obrigatorias = ['Data Emissão', 'Data Entrega', 'Tipo Venda', 'Produto', 'Qtd', 'Pedido', 'Orçamento']
    for c in colunas_obrigatorias:
        if c not in df.columns:
            df[c] = np.nan

    # Conversão de Datas
    for col in ['Data Emissão', 'Data Entrega']:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    # Conversão de Números
    for col in ['Valor Venda', 'Custo', 'Qtd']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # ID Único Híbrido
    df['ID_Hibrido'] = df['Pedido'].fillna(df['Orçamento']).astype(str)
    return df

# =========================================================
# 2. GRÁFICOS
# =========================================================
def renderizar_velocimetro(valor, titulo):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = valor,
        title = {'text': titulo, 'font': {'size': 18}},
        number = {'suffix': "%", 'font': {'size': 35}, 'valueformat': '.1f'},
        gauge = {
            'axis': {'range': [0, 100]},
            'bar': {'color': "#1f2937"},
            'steps': [
                {'range': [0, 50], 'color': "#ef4444"},
                {'range': [50, 85], 'color': "#facc15"},
                {'range': [85, 100], 'color': "#16a34a"}
            ]
        }
    ))
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=50, b=20))
    return fig

# =========================================================
# 3. INTERFACE
# =========================================================
def exibir_manutencao(user_role=None):
    st.sidebar.title("Configurações")
    if st.sidebar.button("🚨 LIMPAR TUDO E REINICIAR"):
        st.session_state.clear()
        st.rerun()

    st.title("🚀 Hub de Inteligência Comercial")

    tab_vendas, tab_produtos, tab_projecao, tab_config = st.tabs([
        "📊 Eficiência Vendas", 
        "📦 Eficiência Produtos", 
        "📈 Projeção de Compras",
        "⚙️ Configurações"
    ])

    with tab_config:
        st.subheader("Upload da Planilha")
        arquivo = st.file_uploader("Arraste seu arquivo Excel ou CSV aqui", type=['xlsx', 'csv', 'xls'])
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                # O segredo está aqui: tratar e salvar no estado
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("✅ Dados processados com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    if 'dados_vendas' not in st.session_state:
        st.info("📢 Por favor, faça o upload dos dados na aba 'Configurações' para ativar o sistema.")
        return

    df = st.session_state['dados_vendas']

    # --- ABA 1: EFICIÊNCIA VENDAS ---
    with tab_vendas:
        st.header("Eficiência de Logística (SLA 48h)")
        df_003 = df[df['Tipo Venda'].astype(str).str.contains('003', na=False)].copy()
        
        # Só dropamos se as colunas existirem de fato
        df_sla = df_003.dropna(subset=['Data Emissão', 'Data Entrega'])
        
        if not df_sla.empty:
            df_sla['Dias_Uteis'] = np.busday_count(
                df_sla['Data Emissão'].dt.floor('D').values.astype('datetime64[D]'), 
                df_sla['Data Entrega'].dt.floor('D').values.astype('datetime64[D]')
            )
            total = len(df_sla)
            dentro_prazo = len(df_sla[df_sla['Dias_Uteis'] <= 2])
            perc = (dentro_prazo / total) * 100

            col1, col2 = st.columns([1, 2])
            with col1:
                st.plotly_chart(renderizar_velocimetro(perc, "SLA ENTREGA 48H"), use_container_width=True)
            with col2:
                st.metric("Total de Pedidos analisados", total)
                st.metric("Pedidos dentro das 48h", dentro_prazo)
                if perc < 50: 
                    st.error("⚠️ BAIXA EFICIÊNCIA: O tempo de agendamento está ultrapassando 48h úteis.")
                else:
                    st.success("✅ BOA EFICIÊNCIA: A logística está fluindo no prazo.")
        else:
            st.warning("⚠️ Dados de 'Data Entrega' não encontrados para calcular o SLA.")

    # --- ABA 2: PRODUTOS ---
    with tab_produtos:
        st.header("Ranking de Movimentação")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🏆 Mais Vendidos (003)")
            t003 = df[df['Tipo Venda'].astype(str).str.contains('003', na=False)].groupby('Produto')['Qtd'].sum().nlargest(10)
            st.bar_chart(t003)
        with c2:
            st.subheader("🏆 Mais Vendidos (004)")
            t004 = df[df['Tipo Venda'].astype(str).str.contains('004', na=False)].groupby('Produto')['Qtd'].sum().nlargest(10)
            st.bar_chart(t004)

    # --- ABA 3: PROJEÇÃO ---
    with tab_projecao:
        st.header("📈 Projeção de Compras (Lead Time)")
        lead_time = st.number_input("Dias para o fornecedor entregar:", value=25)
        
        # Lógica de Venda Média Diária
        df_encomenda = df[df['Tipo Venda'].astype(str).str.contains('004', na=False)]
        if not df_encomenda.empty:
            proj = df_encomenda.groupby('Produto').agg(
                Vendido=('Qtd', 'sum'),
                Dias=('Data Emissão', lambda x: (x.max() - x.min()).days + 1)
            ).reset_index()
            
            proj['VMD'] = proj['Vendido'] / proj['Dias']
            proj['Previsão 30 dias'] = (proj['VMD'] * 30).round(0)
            proj['Sugestão de Compra'] = (proj['VMD'] * (30 + lead_time)).round(0)
            
            st.dataframe(proj.sort_values('VMD', ascending=False), use_container_width=True, hide_index=True)
            st.info(f"💡 A sugestão de compra considera o que você vende em 30 dias + a cobertura do atraso de {lead_time} dias do fornecedor.")
        else:
            st.warning("Sem dados de encomendas (004) para projetar.")
