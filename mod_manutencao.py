import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =========================================================
# 1. TRATAMENTO DE DADOS (SUA LÓGICA + BLINDAGEM DE UPLOAD)
# =========================================================
def tratar_dados(df):
    # Correção de Encoding e Nomes (Sua lógica)
    df.columns = [col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col for col in df.columns]
    mapeamento = {
        'Dt EmissÃ£o': 'Data Emissão', 'OrÃ§amento': 'Orçamento', 
        'Data Ent': 'Data Entrega', 'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # --- FIX CRÍTICO PARA UPLOAD ---
    # Forçamos Pedido e Orçamento para String para evitar erro de tipos mistos
    for c in ['Pedido', 'Orçamento']:
        if c in df.columns:
            df[c] = df[c].astype(str).replace(['nan', 'None', '/ /'], '')

    # Conversão de Datas
    for col in ['Data Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Tratamento Financeiro (Sua lógica)
    for col in ['Valor Venda', 'Custo', 'Qtd']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # ID Único Híbrido (Sua lógica preservada)
    df['ID_Hibrido'] = df['Pedido'].replace('', np.nan).fillna(df['Orçamento']).astype(str)
    return df

# =========================================================
# 2. COMPONENTES VISUAIS (SLA E PROJEÇÃO)
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
            ]
        }
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
    return fig

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def exibir_manutencao(user_role=None):
    st.sidebar.title("Configurações")
    if st.sidebar.button("🚨 Resetar Sistema"):
        st.session_state.clear()
        st.rerun()

    st.title("🏗️ Dashboard de Eficiência Operacional")
    
    tab_operacao, tab_projecao, tab_config = st.tabs([
        "📊 Operação & SLA", 
        "📈 Projeção de Compras",
        "⚙️ Configurações"
    ])

    with tab_config:
        st.subheader("Upload de Planilha")
        arquivo = st.file_uploader("Suba o arquivo Excel ou CSV", type=['xlsx', 'csv'])
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
                else:
                    df_raw = pd.read_excel(arquivo)
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("Dados processados!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro no processamento: {e}")

    if 'dados_vendas' not in st.session_state:
        st.info("Aguardando upload na aba Configurações.")
        return

    df = st.session_state['dados_vendas']

    with tab_operacao:
        # --- BLOCO DE CONFERÊNCIA (Sua lógica exata) ---
        pedidos_unicos = df[df['Pedido'] != '']['Pedido'].unique().size
        orcamentos_unicos = df[df['Orçamento'] != '']['Orçamento'].unique().size
        
        st.subheader("🔍 Conferência de Base")
        c1, c2 = st.columns(2)
        c1.metric("Pedidos Únicos (Planilha)", pedidos_unicos)
        c2.metric("Orçamentos Únicos (Planilha)", orcamentos_unicos)
        st.divider()

        df_unicos = df.drop_duplicates(subset=['ID_Hibrido'])
        total_geral = len(df_unicos)

        # --- ANÁLISE DO 003-ENTREGA (Sua lógica + Velocímetro) ---
        st.subheader("🚚 Foco: 003-ENTREGA (SLA vs Agendamento)")
        df_003 = df_unicos[df_unicos['Tipo Venda'].str.contains('003', na=False)].copy()
        df_003 = df_003.dropna(subset=['Data Emissão', 'Data Entrega'])
        
        if not df_003.empty:
            df_003['Dias_Uteis'] = np.busday_count(
                df_003['Data Emissão'].values.astype('datetime64[D]'), 
                df_003['Data Entrega'].values.astype('datetime64[D]')
            )
            
            no_prazo_48h = len(df_003[df_003['Dias_Uteis'] <= 2])
            agendado_cliente = len(df_003[df_003['Dias_Uteis'] > 2])
            p_48h = (no_prazo_48h / len(df_003) * 100)

            col_v, col_t = st.columns([1, 2])
            with col_v:
                st.plotly_chart(renderizar_velocimetro(p_48h, "EFICIÊNCIA 48H"))
            with col_t:
                st.info(f"**No Prazo (Até 48h):** {no_prazo_48h} pedidos")
                st.success(f"**Agendado (> 48h):** {agendado_cliente} pedidos")
        else:
            st.warning("Sem dados de entrega (003) para calcular SLA.")

    with tab_projecao:
        st.subheader("📈 Planejamento de Demanda (Tipo 004)")
        lead_time = st.slider("Lead Time (Dias):", 1, 60, 25)
        
        df_004 = df[df['Tipo Venda'].str.contains('004', na=False)].copy()
        if not df_004.empty:
            resumo = df_004.groupby('Produto').agg(
                Total=('Qtd', 'sum'),
                Inicio=('Data Emissão', 'min'),
                Fim=('Data Emissão', 'max')
            ).reset_index()
            
            resumo['Dias'] = (resumo['Fim'] - resumo['Inicio']).dt.days + 1
            resumo['VMD'] = resumo['Total'] / resumo['Dias']
            resumo['Sugestão_Compra'] = (resumo['VMD'] * (30 + lead_time)).round(0)
            
            st.dataframe(resumo[['Produto', 'Total', 'VMD', 'Sugestão_Compra']].sort_values('VMD', ascending=False), 
                         use_container_width=True, hide_index=True)
        else:
            st.warning("Sem dados de encomenda (004).")

if __name__ == "__main__":
    exibir_manutencao()
