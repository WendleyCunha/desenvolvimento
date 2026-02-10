import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# =========================================================
# 1. TRATAMENTO DE DADOS (CÉREBRO DO SISTEMA)
# =========================================================
def tratar_dados(df):
    df.columns = [col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col for col in df.columns]
    mapeamento = {
        'Dt EmissÃ£o': 'Data Emissão', 'OrÃ§amento': 'Orçamento', 
        'Data Ent': 'Data Entrega', 'Tipo Venda': 'Tipo Venda',
        'Produto': 'Produto', 'Qtd': 'Qtd'
    }
    df.rename(columns=mapeamento, inplace=True)

    for col in ['Data Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    for col in ['Valor Venda', 'Custo']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # ID Único Híbrido: Prioridade Pedido, senão Orçamento
    df['ID_Hibrido'] = df['Pedido'].fillna(df['Orçamento']).astype(str)
    return df

# =========================================================
# 2. COMPONENTES VISUAIS (GRITANDO A EFICIÊNCIA)
# =========================================================
def renderizar_velocimetro(valor, titulo, meta=100):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = valor,
        title = {'text': titulo, 'font': {'size': 20}},
        number = {'suffix': "%", 'font': {'size': 40}},
        gauge = {
            'axis': {'range': [None, 100], 'tickwidth': 1},
            'bar': {'color': "#1f1f1f"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 40], 'color': "#ff4d4d"}, # Vermelho (Crítico)
                {'range': [40, 80], 'color': "#ffcc00"}, # Amarelo (Atenção)
                {'range': [80, 100], 'color': "#00cc66"} # Verde (Excelente)
            ],
            'threshold': {
                'line': {'color': "black", 'width': 4},
                'thickness': 0.75,
                'value': meta
            }
        }
    ))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
    return fig

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def exibir_manutencao(user_role=None):
    st.set_page_config(layout="wide", page_title="Sistema Premium de Vendas")
    
    # Botão de Reset no topo da Sidebar
    if st.sidebar.button("🚨 RESETAR SISTEMA (LIMPAR CACHE)", use_container_width=True):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

    st.title("🚀 Hub de Inteligência Comercial")

    tab_vendas, tab_produtos, tab_config = st.tabs([
        "📊 Eficiência Vendas (SLA)", 
        "📦 Eficiência Produtos (Curva)", 
        "⚙️ Configurações"
    ])

    # --- ABA: CONFIGURAÇÕES ---
    with tab_config:
        st.subheader("Configurações de Dados")
        arquivo = st.file_uploader("Subir base de dados (Excel/CSV)", type=['xlsx', 'csv'])
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
                else:
                    df_raw = pd.read_excel(arquivo)
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("Dados carregados e amarrados com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro no processamento: {e}")

    # Verificação de Dados
    if 'dados_vendas' not in st.session_state:
        st.info("Aguardando upload da planilha para iniciar as análises.")
        return

    df = st.session_state['dados_vendas']
    df_unicos = df.drop_duplicates(subset=['ID_Hibrido'])

    # --- ABA: EFICIÊNCIA VENDAS ---
    with tab_vendas:
        st.header("Análise de Eficiência de Agendamento (SLA)")
        
        # Lógica de SLA 003
        df_003 = df_unicos[df_unicos['Tipo Venda'].str.contains('003', na=False)].copy()
        df_003 = df_003.dropna(subset=['Data Emissão', 'Data Entrega'])
        
        if not df_003.empty:
            emissao = df_003['Data Emissão'].values.astype('datetime64[D]')
            entrega = df_003['Data Entrega'].values.astype('datetime64[D]')
            df_003['Dias_Uteis'] = np.busday_count(emissao, entrega)
            
            total_003 = len(df_003)
            qtd_48h = len(df_003[df_003['Dias_Uteis'] <= 2])
            perc_48h = (qtd_48h / total_003 * 100)

            # Dashboard "Gritando"
            c1, c2 = st.columns([1, 1.5])
            with c1:
                st.plotly_chart(renderizar_velocimetro(perc_48h, "EFICIÊNCIA 48H"), use_container_width=True)
                if perc_48h < 50:
                    st.error(f"PONTO CRÍTICO: Sua eficiência está em {perc_48h:.1f}%. A logística precisa de atenção imediata.")
                else:
                    st.success(f"BOM DESEMPENHO: {perc_48h:.1f}% dentro do prazo.")
            
            with c2:
                # Pizza do Mix Total
                cont_tipo = df_unicos['Tipo Venda'].value_counts()
                fig_mix = px.pie(names=cont_tipo.index, values=cont_tipo.values, title="Mix de Venda Total (Pedidos)", hole=0.4)
                st.plotly_chart(fig_mix, use_container_width=True)
        else:
            st.warning("Não há dados de entregas (003) para calcular a eficiência.")

    # --- ABA: EFICIÊNCIA PRODUTOS ---
    with tab_produtos:
        st.header("Análise de Giro de Produtos")
        
        col_p1, col_p2 = st.columns(2)
        
        with col_p1:
            st.subheader("🏆 Top Produtos (003 - Entrega)")
            # Aqui focamos no volume (Qtd) somado por Produto
            top_003 = df[df['Tipo Venda'].str.contains('003', na=False)].groupby('Produto')['Qtd'].sum().sort_values(ascending=False).head(10)
            st.bar_chart(top_003)
            st.dataframe(top_003, use_container_width=True)

        with col_p2:
            st.subheader("🏆 Top Produtos (004 - Encomenda)")
            top_004 = df[df['Tipo Venda'].str.contains('004', na=False)].groupby('Produto')['Qtd'].sum().sort_values(ascending=False).head(10)
            st.bar_chart(top_004, color="#3b82f6")
            st.dataframe(top_004, use_container_width=True)

        st.divider()
        st.info("💡 Estes produtos são os que mais movimentam seu estoque e logística. Verifique se o código do produto (Coluna N) está integrado ao seu sistema de ERP.")
