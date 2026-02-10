import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =========================================================
# 1. TRATAMENTO DE DADOS (LOGICA REFINADA)
# =========================================================
def tratar_dados(df):
    # Correção de Encoding nas colunas
    df.columns = [col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col for col in df.columns]
    
    mapeamento = {
        'Dt EmissÃ£o': 'Data Emissão', 'OrÃ§amento': 'Orçamento', 
        'Data Ent': 'Data Entrega', 'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # Limpeza de IDs e strings
    for c in ['Pedido', 'Orçamento', 'Produto']:
        if c in df.columns:
            df[c] = df[c].astype(str).replace(['nan', 'None', '/ /'], '').str.strip()

    # Conversão de Datas
    for col in ['Data Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Tratamento Numérico (Qtd e Valores)
    for col in ['Valor Venda', 'Custo', 'Qtd']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['ID_Hibrido'] = df['Pedido'].replace('', np.nan).fillna(df['Orçamento']).astype(str)
    return df

# =========================================================
# 2. COMPONENTES VISUAIS
# =========================================================
def renderizar_velocimetro(valor, titulo):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = valor,
        title = {'text': titulo, 'font': {'size': 20}},
        number = {'suffix': "%", 'font': {'size': 40}},
        gauge = {
            'axis': {'range': [0, 100]},
            'bar': {'color': "#2c3e50"},
            'steps': [
                {'range': [0, 50], 'color': "#ff4b4b"},
                {'range': [50, 85], 'color': "#ffa500"},
                {'range': [85, 100], 'color': "#28a745"}
            ]
        }
    ))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor="rgba(0,0,0,0)")
    return fig

# =========================================================
# 3. FUNÇÃO PRINCIPAL (MAIN)
# =========================================================
def main():
    st.title("🚀 Dashboard de Gestão Operacional")

    # Definição das Abas
    tab_dashboard, tab_planejamento, tab_config = st.tabs([
        "📊 Dashboard Operacional", 
        "📈 Planejamento de Compras (004)", 
        "⚙️ Configurações do Sistema"
    ])

    # --- ABA CONFIGURAÇÕES (Reset e Upload) ---
    with tab_config:
        st.header("⚙️ Gestão de Dados")
        
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            st.subheader("Upload de Base")
            arquivo = st.file_uploader("Suba o arquivo Excel ou CSV", type=['xlsx', 'csv'], key="uploader_principal")
            
            if arquivo:
                try:
                    if arquivo.name.endswith('.csv'):
                        df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
                    else:
                        df_raw = pd.read_excel(arquivo)
                    
                    st.session_state['dados_vendas'] = tratar_dados(df_raw)
                    st.success(f"✅ Arquivo '{arquivo.name}' carregado com sucesso!")
                except Exception as e:
                    st.error(f"❌ Erro ao processar arquivo: {e}")

        with col_c2:
            st.subheader("Limpeza de Banco")
            st.write("Use o botão abaixo para limpar todos os dados carregados e resetar as análises.")
            if st.button("🚨 Resetar Banco de Dados", use_container_width=True):
                st.session_state.clear()
                st.success("Sistema resetado!")
                st.rerun()

    # Verificação de segurança: se não há dados, para aqui
    if 'dados_vendas' not in st.session_state:
        st.info("👋 Bem-vindo! Vá até a aba **Configurações do Sistema** para carregar sua planilha.")
        return

    df = st.session_state['dados_vendas']

    # --- ABA DASHBOARD OPERACIONAL ---
    with tab_dashboard:
        st.header("Análise de Pedidos e SLA")
        
        # Métricas de Cabeçalho
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Pedidos", df['ID_Hibrido'].nunique())
        m2.metric("Qtd Total Itens", int(df['Qtd'].sum()))
        m3.metric("Faturamento Bruto", f"R$ {df.drop_duplicates('ID_Hibrido')['Valor Venda'].sum():,.2f}")
        m4.metric("Ticket Médio", f"R$ {df.drop_duplicates('ID_Hibrido')['Valor Venda'].mean():,.2f}")

        st.divider()

        # Analise SLA Entrega (003)
        df_003 = df[df['Tipo Venda'].str.contains('003', na=False)].drop_duplicates('ID_Hibrido').copy()
        df_003 = df_003.dropna(subset=['Data Emissão', 'Data Entrega'])

        if not df_003.empty:
            df_003['Dias_Uteis'] = np.busday_count(
                df_003['Data Emissão'].values.astype('datetime64[D]'), 
                df_003['Data Entrega'].values.astype('datetime64[D]')
            )
            p_48h = (len(df_003[df_003['Dias_Uteis'] <= 2]) / len(df_003)) * 100
            
            c_gauge, c_info = st.columns([1, 1])
            with c_gauge:
                st.plotly_chart(renderizar_velocimetro(p_48h, "SLA de Entrega (48h)"), use_container_width=True)
            with c_info:
                st.write("### Detalhes do Prazo")
                st.success(f"No Prazo (Até 2 dias úteis): **{len(df_003[df_003['Dias_Uteis'] <= 2])}**")
                st.error(f"Acima do Prazo / Agendado: **{len(df_003[df_003['Dias_Uteis'] > 2])}**")
                
                fig_hist = px.histogram(df_003, x='Dias_Uteis', title="Distribuição de Dias para Entrega")
                st.plotly_chart(fig_hist, use_container_width=True)

    # --- ABA PLANEJAMENTO DE COMPRAS (O CORAÇÃO DA SUA SOLICITAÇÃO) ---
    with tab_planejamento:
        st.header("📈 Planejamento de Compras (Itens 004)")
        st.write("Base de cálculo: Últimos 90 dias de histórico para projeção de demanda.")

        # Parâmetros de Projeção
        c_p1, c_p2 = st.columns(2)
        dias_futuros = c_p1.slider("Projetar para quantos dias?", 25, 30, 25)
        margem_seg = c_p2.slider("Margem de Segurança (%)", 0, 100, 15)

        # Lógica de Datas (Últimos 90 dias)
        data_referencia = df['Data Emissão'].max()
        data_corte = data_referencia - timedelta(days=90)
        
        # Filtro: Somente 004 nos últimos 90 dias
        df_proj = df[(df['Tipo Venda'].str.contains('004', na=False)) & (df['Data Emissão'] >= data_corte)].copy()

        if not df_proj.empty:
            # Agrupar por produto
            planejamento = df_proj.groupby('Produto').agg(
                Qtd_90d=('Qtd', 'sum'),
                Ultima_Venda=('Data Emissão', 'max')
            ).reset_index()

            # Venda Média Diária (VMD) baseada no trimestre
            planejamento['VMD'] = planejamento['Qtd_90d'] / 90
            
            # Cálculo de Necessidade: (VMD * Dias Projetados) + Margem
            planejamento['Necessidade_Base'] = planejamento['VMD'] * dias_futuros
            planejamento['Qtd_Sugerida'] = (planejamento['Necessidade_Base'] * (1 + margem_seg/100)).apply(np.ceil).astype(int)

            # Visualização da Tabela
            st.subheader("Sugestão de Pedido de Compra")
            
            # Destacar itens críticos
            st.dataframe(
                planejamento.sort_values('Qtd_Sugerida', ascending=False),
                column_config={
                    "Produto": "Descrição do Item",
                    "Qtd_90d": "Venda Total (90 dias)",
                    "VMD": st.column_config.NumberColumn("VMD (Venda Média Diária)", format="%.2f"),
                    "Qtd_Sugerida": st.column_config.NumberColumn("Sugestão de Compra (Qtd)", help="Baseado na VMD + Margem")
                },
                use_container_width=True, hide_index=True
            )
            
            # Gráfico de Necessidade
            fig_bar = px.bar(planejamento.sort_values('Qtd_Sugerida', ascending=False).head(15), 
                             x='Produto', y='Qtd_Sugerida', 
                             title=f"Top 15 Itens com maior demanda para {dias_futuros} dias",
                             color='Qtd_Sugerida', color_continuous_scale='Blues')
            st.plotly_chart(fig_bar, use_container_width=True)
            
        else:
            st.warning("⚠️ Não foram encontrados itens do tipo '004-ENCOMENDA' nos últimos 90 dias da base carregada.")

if __name__ == "__main__":
    main()
