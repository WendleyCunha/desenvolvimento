import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_option_menu import option_menu

# Configuração da página
st.set_page_config(page_title="Gestão de Demanda & SLA", layout="wide", page_icon="📊")

# Custom CSS para "belezura" (Cards e fontes)
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E88E5; }
    .main { background-color: #f8f9fa; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 5px; }
    .stTabs [aria-selected="true"] { background-color: #1E88E5 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# =========================================================
# 1. TRATAMENTO DE DADOS (MELHORADO)
# =========================================================
def tratar_dados(df):
    # Tratamento de encoding nas colunas
    df.columns = [col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col for col in df.columns]
    
    mapeamento = {
        'Dt EmissÃ£o': 'Data Emissão', 
        'OrÃ§amento': 'Orçamento', 
        'Data Ent': 'Data Entrega',
        'Tipo Venda': 'Tipo Venda',
        'Qtd': 'Qtd'
    }
    df.rename(columns=mapeamento, inplace=True)

    # Limpeza de strings e IDs
    for c in ['Pedido', 'Orçamento', 'Produto']:
        if c in df.columns:
            df[c] = df[c].astype(str).replace(['nan', 'None', '/ /'], '').str.strip()

    # Conversão de Datas com tratamento de erro
    for col in ['Data Emissão', 'Data Entrega', 'Data Lib', 'Data Prev']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Tratamento Financeiro Robusto
    for col in ['Valor Venda', 'Custo', 'Qtd']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # ID Único Híbrido
    df['ID_Hibrido'] = df['Pedido'].replace('', np.nan).fillna(df['Orçamento']).astype(str)
    
    # Adicionar mês/ano para filtros temporais
    df['Mes_Ano'] = df['Data Emissão'].dt.to_period('M').astype(str)
    
    return df

# =========================================================
# 2. COMPONENTES VISUAIS
# =========================================================
def renderizar_velocimetro(valor, titulo):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = valor,
        title = {'text': titulo, 'font': {'size': 20, 'color': '#333'}},
        number = {'suffix': "%", 'font': {'size': 40, 'color': '#1E88E5'}},
        gauge = {
            'axis': {'range': [0, 100], 'tickwidth': 1},
            'bar': {'color': "#2c3e50"},
            'steps': [
                {'range': [0, 60], 'color': "#ffb3b3"},
                {'range': [60, 85], 'color': "#ffe0b3"},
                {'range': [85, 100], 'color': "#b3ffcc"}
            ],
            'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 90}
        }
    ))
    fig.update_layout(height=300, margin=dict(l=30, r=30, t=50, b=20), paper_bgcolor="rgba(0,0,0,0)")
    return fig

# =========================================================
# 3. INTERFACE E LOGICA
# =========================================================
def main():
    # Sidebar com Menu Estilizado
    with st.sidebar:
        st.title("Settings")
        selected = option_menu(
            menu_title=None,
            options=["Dashboard", "Projeção", "Configurações"],
            icons=["house", "cart-check", "gear"],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"padding": "5!important", "background-color": "#fafafa"},
                "nav-link-selected": {"background-color": "#1E88E5"},
            }
        )
        
        st.divider()
        if st.button("🚨 Resetar Sistema", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # --- ABA CONFIGURAÇÕES (UPLOAD) ---
    if selected == "Configurações":
        st.title("⚙️ Configurações do Sistema")
        st.subheader("Upload de Dados")
        arquivo = st.file_uploader("Arraste aqui a planilha de vendas (CSV ou XLSX)", type=['xlsx', 'csv'])
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("✅ Base de dados atualizada com sucesso!")
                if st.button("Ir para Dashboard"):
                    st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar: {e}")

    # Verificação de Dados
    if 'dados_vendas' not in st.session_state:
        st.warning("⚠️ Por favor, faça o upload da planilha na aba 'Configurações' para começar.")
        return

    df = st.session_state['dados_vendas']

    # --- ABA DASHBOARD (OPERACIONAL) ---
    if selected == "Dashboard":
        st.title("📊 Eficiência de Entrega (SLA)")
        
        # Filtros Rápidos
        col1, col2, col3 = st.columns(3)
        pedidos_unicos = df['ID_Hibrido'].nunique()
        faturamento = df.drop_duplicates('ID_Hibrido')['Valor Venda'].sum()
        
        col1.metric("Total de Pedidos", pedidos_unicos)
        col2.metric("Venda Total", f"R$ {faturamento:,.2f}")
        col3.metric("Itens Vendidos", int(df['Qtd'].sum()))

        st.divider()

        # Lógica SLA 48h
        df_003 = df[df['Tipo Venda'].str.contains('003', na=False)].drop_duplicates('ID_Hibrido').copy()
        df_003 = df_003.dropna(subset=['Data Emissão', 'Data Entrega'])
        
        if not df_003.empty:
            df_003['Dias_Uteis'] = np.busday_count(
                df_003['Data Emissão'].values.astype('datetime64[D]'), 
                df_003['Data Entrega'].values.astype('datetime64[D]')
            )
            p_48h = (len(df_003[df_003['Dias_Uteis'] <= 2]) / len(df_003)) * 100
            
            c_gauge, c_chart = st.columns([1, 1])
            with c_gauge:
                st.plotly_chart(renderizar_velocimetro(p_48h, "SLA de Entrega (48h)"), use_container_width=True)
            with c_chart:
                # Vendas por dia
                vendas_dia = df.groupby(df['Data Emissão'].dt.date)['Valor Venda'].sum().reset_index()
                fig_vendas = px.line(vendas_dia, x='Data Emissão', y='Valor Venda', title="Volume de Vendas Diário")
                st.plotly_chart(fig_vendas, use_container_width=True)

    # --- ABA PROJEÇÃO (COMPRAS) ---
    if selected == "Projeção":
        st.title("📈 Planejamento de Compras (Base 90 Dias)")
        
        # Parâmetros de Projeção
        with st.expander("🛠️ Ajustar Parâmetros de Cálculo", expanded=True):
            c1, c2 = st.columns(2)
            dias_projecao = c1.slider("Projetar para quantos dias?", 25, 60, 30)
            safety_margin = c2.slider("Margem de Segurança (%)", 0, 50, 10)

        # Filtro de data: Últimos 90 dias
        data_max = df['Data Emissão'].max()
        data_corte = data_max - timedelta(days=90)
        df_90 = df[(df['Data Emissão'] >= data_corte) & (df['Tipo Venda'].str.contains('004', na=False))].copy()

        if not df_90.empty:
            # Cálculo VMD (Venda Média Diária)
            # Agrupamos por Produto e calculamos a soma da Qtd no período
            compras = df_90.groupby('Produto').agg(
                Venda_Total=('Qtd', 'sum'),
                Primeira_Venda=('Data Emissão', 'min'),
                Ultima_Venda=('Data Emissão', 'max')
            ).reset_index()

            # Dias ativos (mínimo de 1 para evitar divisão por zero)
            compras['Dias_Ativos'] = 90 
            compras['VMD'] = compras['Venda_Total'] / compras['Dias_Ativos']
            
            # Cálculo da Necessidade
            compras['Necessidade_Projetada'] = (compras['VMD'] * dias_projecao) * (1 + (safety_margin/100))
            compras['Sugestão_Compra'] = compras['Necessidade_Projetada'].apply(np.ceil).astype(int)

            # Formatação da Tabela
            st.subheader(f"Sugestão de Pedido para {dias_projecao} dias")
            
            # Gráfico de Top Itens a Comprar
            fig_compra = px.bar(
                compras.sort_values('Sugestão_Compra', ascending=False).head(15),
                x='Produto', y='Sugestão_Compra',
                title="Top 15 Produtos com maior necessidade de compra",
                color='Sugestão_Compra', color_continuous_scale='Blues'
            )
            st.plotly_chart(fig_compra, use_container_width=True)

            # Tabela Interativa
            st.dataframe(
                compras[['Produto', 'Venda_Total', 'VMD', 'Sugestão_Compra']].sort_values('Sugestão_Compra', ascending=False),
                column_config={
                    "VMD": st.column_config.NumberColumn("Venda Média/Dia", format="%.2f"),
                    "Sugestão_Compra": st.column_config.ProgressColumn("Sugestão de Compra (Qtd)", format="%d", min_value=0, max_value=int(compras['Sugestão_Compra'].max()))
                },
                use_container_width=True, hide_index=True
            )
        else:
            st.error("Dados insuficientes para os últimos 90 dias com o tipo '004-ENCOMENDA'.")

if __name__ == "__main__":
    main()
