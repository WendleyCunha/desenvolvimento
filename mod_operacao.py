import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =========================================================
# 1. TRATAMENTO DE DADOS
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

    # Limpeza financeira e numérica
    for col in ['Valor Venda', 'Custo', 'Qtd']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['ID_Hibrido'] = df['Pedido'].fillna(df['Orçamento']).astype(str)
    return df

# =========================================================
# 2. GRÁFICOS DE IMPACTO
# =========================================================
def renderizar_velocimetro(valor, titulo):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = valor,
        title = {'text': titulo, 'font': {'size': 18}},
        number = {'suffix': "%", 'font': {'size': 35}},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': "black"},
            'steps': [
                {'range': [0, 50], 'color': "#ef4444"},
                {'range': [50, 85], 'color': "#facc15"},
                {'range': [85, 100], 'color': "#16a34a"}
            ],
            'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 90}
        }
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
    return fig

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def exibir_manutencao(user_role=None):
    # Sidebar com Reset Total
    st.sidebar.title("Configurações do Sistema")
    if st.sidebar.button("🚨 RESETAR E LIMPAR CACHE"):
        st.session_state.clear()
        st.rerun()

    st.title("🚀 Hub de Inteligência e Projeção")

    # Criando as 4 Abas Solicitadas
    tab_vendas, tab_produtos, tab_projecao, tab_config = st.tabs([
        "📊 Eficiência Vendas (SLA)", 
        "📦 Eficiência Produtos", 
        "📈 Projeção de Compras",
        "⚙️ Configurações"
    ])

    with tab_config:
        st.subheader("Importação de Dados")
        arquivo = st.file_uploader("Subir base Excel/CSV", type=['xlsx', 'csv'])
        if arquivo:
            if arquivo.name.endswith('.csv'):
                df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
            else:
                df_raw = pd.read_excel(arquivo)
            st.session_state['dados_vendas'] = tratar_dados(df_raw)
            st.success("Base atualizada!")
            st.rerun()

    if 'dados_vendas' not in st.session_state:
        st.info("Aguardando upload na aba Configurações.")
        return

    df = st.session_state['dados_vendas']
    
    # --- ABA 1: EFICIÊNCIA VENDAS ---
    with tab_vendas:
        df_unicos = df.drop_duplicates(subset=['ID_Hibrido'])
        df_003 = df_unicos[df_unicos['Tipo Venda'].str.contains('003', na=False)].dropna(subset=['Data Emissão', 'Data Entrega'])
        
        if not df_003.empty:
            # Cálculo de SLA
            df_003['Dias_Uteis'] = np.busday_count(df_003['Data Emissão'].values.astype('datetime64[D]'), 
                                                  df_003['Data Entrega'].values.astype('datetime64[D]'))
            perc_48h = (len(df_003[df_003['Dias_Uteis'] <= 2]) / len(df_003)) * 100
            
            c1, c2 = st.columns([1, 2])
            with c1:
                st.plotly_chart(renderizar_velocimetro(perc_48h, "SLA AGENDAMENTO (48H)"))
            with c2:
                st.markdown(f"""
                ### Análise de Performance
                - **Status Atual**: {"🔴 CRÍTICO" if perc_48h < 50 else "🟢 OPERACIONAL"}
                - **Total de Pedidos 003**: {len(df_003)}
                - **Onde atacar**: {"O agendamento imediato está falhando. Verifique o gargalo na recepção." if perc_48h < 30 else "Manter fluxo de saída constante."}
                """)
        else:
            st.warning("Sem dados para calcular SLA 003.")

    # --- ABA 2: EFICIÊNCIA PRODUTOS ---
    with tab_produtos:
        st.subheader("Curva de Vendas por Tipo")
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Top 10 - Tipo 003 (Entrega)**")
            top003 = df[df['Tipo Venda'].str.contains('003', na=False)].groupby('Produto')['Qtd'].sum().nlargest(10)
            st.bar_chart(top003)
        with c2:
            st.write("**Top 10 - Tipo 004 (Encomenda)**")
            top004 = df[df['Tipo Venda'].str.contains('004', na=False)].groupby('Produto')['Qtd'].sum().nlargest(10, )
            st.bar_chart(top004, color="#3b82f6")

    # --- ABA 3: PROJEÇÃO DE COMPRAS (O CORAÇÃO DO SEU PEDIDO) ---
    with tab_projecao:
        st.header("📈 Planejamento de Demanda e Compras")
        
        lead_time = st.slider("Prazo de Entrega Fornecedor (Dias):", 1, 60, 25)
        
        # Filtramos apenas 004 (Encomenda) para a projeção de compra
        df_proj = df[df['Tipo Venda'].str.contains('004', na=False)].copy()
        
        if not df_proj.empty:
            # Agrupamento por Produto e Data para ver o dia a dia
            vendas_dia = df_proj.groupby(['Produto', df_proj['Data Emissão'].dt.date])['Qtd'].sum().reset_index()
            
            # Cálculo de Média nos últimos 90 dias (para ser realista)
            hoje = datetime.now().date()
            inicio_historico = hoje - timedelta(days=90)
            
            # Resumo por Produto
            resumo_compra = df_proj.groupby('Produto').agg(
                Vendido_Total=('Qtd', 'sum'),
                Primeira_Venda=('Data Emissão', 'min'),
                Ultima_Venda=('Data Emissão', 'max')
            ).reset_index()
            
            # Venda Média Diária (VMD)
            resumo_compra['Dias_Ativos'] = (resumo_compra['Ultima_Venda'] - resumo_compra['Primeira_Venda']).dt.days + 1
            resumo_compra['VMD'] = resumo_compra['Vendido_Total'] / resumo_compra['Dias_Ativos']
            
            # Projeção para Próximos 30 dias
            resumo_compra['Proj_30_Dias'] = (resumo_compra['VMD'] * 30).round(0)
            
            # Ponto de Encomenda (Estoque de Segurança para cobrir o Lead Time)
            resumo_compra['Solicitar_Agora'] = (resumo_compra['VMD'] * (30 + lead_time)).round(0)

            st.write(f"Considerando histórico de vendas e lead time de **{lead_time} dias**:")
            
            # Destaque em Tabela
            st.dataframe(
                resumo_compra[['Produto', 'Vendido_Total', 'VMD', 'Proj_30_Dias', 'Solicitar_Agora']]
                .sort_values(by='VMD', ascending=False),
                column_config={
                    "VMD": st.column_config.NumberColumn("Média/Dia", format="%.2f"),
                    "Proj_30_Dias": "Venda Prevista (30d)",
                    "Solicitar_Agora": "📦 Sugestão Compra (Total)"
                },
                use_container_width=True,
                hide_index=True
            )
            
            st.warning(f"🚨 **O que solicitar?**: A coluna 'Sugestão Compra' calcula o que você venderá nos próximos 30 dias somado ao que você precisa ter enquanto o fornecedor não entrega (Lead Time).")
        else:
            st.error("Sem dados de tipo '004-ENCOMENDA' para projetar.")

# Chamar a função
if __name__ == "__main__":
    exibir_manutencao()
