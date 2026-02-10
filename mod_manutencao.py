import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# =========================================================
# 1. TRATAMENTO DE DADOS (COM BLINDAGEM DE COLUNAS)
# =========================================================
def tratar_dados(df):
    # 1.1 Limpeza agressiva de nomes de colunas (Remove espaços e caracteres ocultos)
    df.columns = [str(col).strip().encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else str(col).strip() for col in df.columns]
    
    # 1.2 Mapeamento flexível para evitar KeyError
    mapeamento = {
        'Dt EmissÃ£o': 'Data Emissão', 
        'Dt Emissao': 'Data Emissão',
        'OrÃ§amento': 'Orçamento', 
        'Orcamento': 'Orçamento',
        'Data Ent': 'Data Entrega', 
        'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 1.3 Verificação de colunas essenciais (Se não existirem, cria vazio para não travar)
    cols_necessarias = ['Data Emissão', 'Data Entrega', 'Tipo Venda', 'Pedido', 'Orçamento', 'Produto', 'Qtd', 'Valor Venda']
    for col in cols_necessarias:
        if col not in df.columns:
            df[col] = np.nan

    # 1.4 Limpeza de IDs e strings
    for c in ['Pedido', 'Orçamento', 'Produto']:
        df[c] = df[c].astype(str).replace(['nan', 'None', '/ /', ''], np.nan).str.strip()

    # 1.5 Conversão de Datas
    for col in ['Data Emissão', 'Data Entrega']:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    # 1.6 Tratamento Numérico (Qtd e Valores)
    for col in ['Valor Venda', 'Custo', 'Qtd']:
        if df[col].dtype == 'object':
            df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Lógica do ID Híbrido mantida
    df['ID_Hibrido'] = df['Pedido'].fillna(df['Orçamento']).astype(str)
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

    # Definição das Abas conforme solicitado
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
                    st.success(f"✅ Arquivo carregado com sucesso!")
                    st.rerun() # Atualiza para liberar as outras abas
                except Exception as e:
                    st.error(f"❌ Erro ao processar arquivo: {e}")

        with col_c2:
            st.subheader("Limpeza e Reset")
            st.write("Limpa o cache e os dados imputados.")
            if st.button("🚨 Resetar Sistema", use_container_width=True):
                st.session_state.clear()
                st.success("Sistema resetado com sucesso!")
                st.rerun()

    # Verificação: se não há dados, as abas operacionais ficam bloqueadas
    if 'dados_vendas' not in st.session_state:
        st.info("👋 Aguardando upload dos dados na aba **Configurações do Sistema**.")
        return

    df = st.session_state['dados_vendas']

    # --- ABA DASHBOARD OPERACIONAL ---
    with tab_dashboard:
        st.header("Análise de Pedidos e SLA")
        
        # Métricas
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Pedidos", df['ID_Hibrido'].nunique())
        m2.metric("Qtd Total Itens", int(df['Qtd'].sum()))
        m3.metric("Faturamento Bruto", f"R$ {df.drop_duplicates('ID_Hibrido')['Valor Venda'].sum():,.2f}")

        st.divider()

        # Analise SLA Entrega (003) - Com proteção contra colunas vazias
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
                st.error(f"Fora do Prazo: **{len(df_003[df_003['Dias_Uteis'] > 2])}**")
        else:
            st.warning("Sem dados suficientes de '003-ENTREGA' para calcular o SLA.")

    # --- ABA PLANEJAMENTO DE COMPRAS (ITENS 004) ---
    with tab_planejamento:
        st.header("📈 Planejamento de Compras (004)")
        st.write("Projeção baseada na Venda Média Diária (VMD) dos últimos 90 dias.")

        # Parâmetros
        c_p1, c_p2 = st.columns(2)
        dias_futuros = c_p1.slider("Projetar para quantos dias?", 25, 30, 25)
        margem_seg = c_p2.slider("Margem de Segurança (%)", 0, 100, 15)

        # Lógica de Projeção
        data_max = df['Data Emissão'].max()
        if pd.isna(data_max):
            st.error("Não há datas válidas para calcular a projeção.")
        else:
            data_corte = data_max - timedelta(days=90)
            df_proj = df[(df['Tipo Venda'].str.contains('004', na=False)) & (df['Data Emissão'] >= data_corte)].copy()

            if not df_proj.empty:
                resumo = df_proj.groupby('Produto').agg(Qtd_Total=('Qtd', 'sum')).reset_index()
                resumo['VMD'] = resumo['Qtd_Total'] / 90
                resumo['Sugerido'] = (resumo['VMD'] * dias_futuros * (1 + margem_seg/100)).apply(np.ceil).astype(int)

                st.subheader("Sugestão de Pedido")
                st.dataframe(
                    resumo.sort_values('Sugerido', ascending=False),
                    column_config={
                        "VMD": st.column_config.NumberColumn("Venda Média/Dia", format="%.2f"),
                        "Sugerido": st.column_config.NumberColumn("Qtd a Comprar", help="Projeção + Margem")
                    },
                    use_container_width=True, hide_index=True
                )
            else:
                st.warning("⚠️ Dados de '004-ENCOMENDA' não encontrados nos últimos 90 dias.")

if __name__ == "__main__":
    main()
