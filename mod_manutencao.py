import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =========================================================
# 1. TRATAMENTO DE DADOS (AJUSTADO PARA UPLOAD SEGURO)
# =========================================================
def tratar_dados(df):
    # 1.1 Limpeza de nomes e Encoding
    df.columns = [str(col).strip().encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else str(col) for col in df.columns]
    
    # 1.2 Mapeamento Inteligente
    mapeamento_alvo = {
        'DATA EMISSÃO': ['DT EMISS', 'DATA EMISSAO', 'DATA EMISSÃO'],
        'DATA ENTREGA': ['DATA ENT', 'DT ENT', 'DATA ENTREGA'],
        'ORÇAMENTO': ['ORÇAMENTO', 'ORCAMENTO', 'ORC'],
        'PEDIDO': ['PEDIDO', 'PED'],
        'TIPO VENDA': ['TIPO VENDA', 'TIPO'],
        'PRODUTO': ['PRODUTO', 'PROD'],
        'QTD': ['QTD', 'QUANTIDADE'],
        'VALOR VENDA': ['VALOR VENDA', 'VALOR'],
        'CUSTO': ['CUSTO']
    }
    
    renomear = {}
    for col in df.columns:
        c_up = col.upper()
        for oficial, variantes in mapeamento_alvo.items():
            if any(var in c_up for var in variantes):
                renomear[col] = oficial
    
    df.rename(columns=renomear, inplace=True)

    # 1.3 Forçar Tipos de Dados (Evita erro de Arrow e travamento no Upload)
    if 'ORÇAMENTO' in df.columns: df['ORÇAMENTO'] = df['ORÇAMENTO'].astype(str).replace('nan', '')
    if 'PEDIDO' in df.columns: df['PEDIDO'] = df['PEDIDO'].astype(str).replace('nan', '')
    if 'TIPO VENDA' in df.columns: df['TIPO VENDA'] = df['TIPO VENDA'].astype(str)
    if 'PRODUTO' in df.columns: df['PRODUTO'] = df['PRODUTO'].astype(str)

    # 1.4 Datas
    for col in ['DATA EMISSÃO', 'DATA ENTREGA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # 1.5 Números (Limpeza de R$ e vírgulas)
    for col in ['VALOR VENDA', 'CUSTO', 'QTD']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # 1.6 ID Único Híbrido
    df['ID_Hibrido'] = df.get('PEDIDO', df.get('ORÇAMENTO', 'SEM_ID')).astype(str)
    
    return df

# =========================================================
# 2. GRÁFICOS DE IMPACTO
# =========================================================
def renderizar_velocimetro(valor, titulo):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = valor,
        title = {'text': titulo, 'font': {'size': 18}},
        number = {'suffix': "%", 'font': {'size': 35}, 'valueformat': '.1f'},
        gauge = {
            'axis': {'range': [0, 100]},
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
    st.sidebar.title("Configurações do Sistema")
    if st.sidebar.button("🚨 RESETAR E LIMPAR CACHE"):
        st.session_state.clear()
        st.rerun()

    st.title("🚀 Hub de Inteligência e Projeção")

    tab_vendas, tab_produtos, tab_projecao, tab_config = st.tabs([
        "📊 Eficiência Vendas (SLA)", 
        "📦 Eficiência Produtos", 
        "📈 Projeção de Compras",
        "⚙️ Configurações"
    ])

    with tab_config:
        st.subheader("Importação de Dados")
        arquivo = st.file_uploader("Subir base Excel/CSV", type=['xlsx', 'csv', 'xls'])
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("✅ Base carregada com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")

    if 'dados_vendas' not in st.session_state:
        st.info("Aguardando upload na aba Configurações.")
        return

    df = st.session_state['dados_vendas']
    
    # --- ABA 1: EFICIÊNCIA VENDAS ---
    with tab_vendas:
        st.header("Análise de Entrega (SLA)")
        if 'TIPO VENDA' in df.columns and 'DATA EMISSÃO' in df.columns:
            df_unicos = df.drop_duplicates(subset=['ID_Hibrido'])
            df_003 = df_unicos[df_unicos['TIPO VENDA'].str.contains('003', na=False)].dropna(subset=['DATA EMISSÃO', 'DATA ENTREGA'])
            
            if not df_003.empty:
                df_003['Dias_Uteis'] = np.busday_count(df_003['DATA EMISSÃO'].values.astype('datetime64[D]'), 
                                                      df_003['DATA ENTREGA'].values.astype('datetime64[D]'))
                perc_48h = (len(df_003[df_003['Dias_Uteis'] <= 2]) / len(df_003)) * 100
                
                c1, col_metrica = st.columns([1, 2])
                with c1:
                    st.plotly_chart(renderizar_velocimetro(perc_48h, "SLA AGENDAMENTO (48H)"))
                with col_metrica:
                    st.metric("Total de Pedidos 003", len(df_003))
                    st.markdown(f"**Status Logístico:** {'🔴 CRÍTICO' if perc_48h < 50 else '🟢 OPERACIONAL'}")
            else:
                st.warning("Sem dados suficientes (Data Emissão/Entrega) para calcular SLA 003.")
        else:
            st.error("Colunas necessárias não encontradas para SLA.")

    # --- ABA 2: EFICIÊNCIA PRODUTOS ---
    with tab_produtos:
        st.subheader("Curva de Vendas por Tipo")
        if 'TIPO VENDA' in df.columns:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Top 10 - Tipo 003 (Entrega)**")
                top003 = df[df['TIPO VENDA'].str.contains('003', na=False)].groupby('PRODUTO')['QTD'].sum().nlargest(10)
                st.bar_chart(top003)
            with c2:
                st.write("**Top 10 - Tipo 004 (Encomenda)**")
                top004 = df[df['TIPO VENDA'].str.contains('004', na=False)].groupby('PRODUTO')['QTD'].sum().nlargest(10)
                st.bar_chart(top004, color="#3b82f6")

    # --- ABA 3: PROJEÇÃO DE COMPRAS ---
    with tab_projecao:
        st.header("📈 Planejamento de Demanda")
        lead_time = st.slider("Prazo de Entrega Fornecedor (Dias):", 1, 60, 25)
        
        if 'TIPO VENDA' in df.columns:
            df_proj = df[df['TIPO VENDA'].str.contains('004', na=False)].copy()
            
            if not df_proj.empty:
                resumo_compra = df_proj.groupby('PRODUTO').agg(
                    Vendido_Total=('QTD', 'sum'),
                    Primeira_Venda=('DATA EMISSÃO', 'min'),
                    Ultima_Venda=('DATA EMISSÃO', 'max')
                ).reset_index()
                
                resumo_compra['Dias_Ativos'] = (resumo_compra['Ultima_Venda'] - resumo_compra['Primeira_Venda']).dt.days + 1
                resumo_compra['VMD'] = resumo_compra['Vendido_Total'] / resumo_compra['Dias_Ativos']
                resumo_compra['Proj_30_Dias'] = (resumo_compra['VMD'] * 30).round(0)
                resumo_compra['Solicitar_Agora'] = (resumo_compra['VMD'] * (30 + lead_time)).round(0)

                st.dataframe(
                    resumo_compra[['PRODUTO', 'Vendido_Total', 'VMD', 'Proj_30_Dias', 'Solicitar_Agora']]
                    .sort_values(by='VMD', ascending=False),
                    column_config={
                        "VMD": st.column_config.NumberColumn("Média/Dia", format="%.2f"),
                        "Proj_30_Dias": "Previsão 30d",
                        "Solicitar_Agora": "📦 Compra Sugerida"
                    },
                    use_container_width=True, hide_index=True
                )
            else:
                st.warning("Sem dados de tipo '004' para projeção.")

# Chamar a função
if __name__ == "__main__":
    exibir_manutencao()
