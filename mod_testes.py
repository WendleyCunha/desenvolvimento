import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.title("📊 Indicadores 360º | Gestão de Tickets")
    st.markdown("---")

    # --- 1. ÁREA DE UPLOAD E PROCESSAMENTO ---
    with st.expander("📂 Importar Base de Dados (Excel/CSV)", expanded=True):
        uploaded_file = st.file_uploader("Arraste o relatório de tickets aqui", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                # Tratamento de Datas
                col_data = "Criação do ticket - Data" # Nome conforme sua imagem
                df[col_data] = pd.to_datetime(df[col_data])
                df['Dia_Semana'] = df[col_data].dt.day_name()
                df['Mes_Ano'] = df[col_data].dt.strftime('%Y-%m')
                
                st.success("Base carregada com sucesso!")
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")
                st.stop()
        else:
            st.info("Aguardando upload da base para gerar os indicadores.")
            st.stop()

    # --- 2. KPIS PRINCIPAIS (CARDS) ---
    total_tickets = len(df)
    fechados = len(df[df['Status do ticket'] == 'Closed'])
    taxa_resolucao = (fechados / total_tickets) * 100 if total_tickets > 0 else 0
    loja_critica = df['Nome do solicitante'].mode()[0]

    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown(f'<div style="background:#fff;padding:20px;border-radius:10px;border-left:5px solid #002366;box-shadow:2px 2px 5px #eee"><strong>TOTAL TICKETS</strong><br><span style="font-size:24px;font-weight:bold">{total_tickets}</span></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div style="background:#fff;padding:20px;border-radius:10px;border-left:5px solid #10b981;box-shadow:2px 2px 5px #eee"><strong>RESOLVIDOS (Closed)</strong><br><span style="font-size:24px;font-weight:bold">{fechados}</span></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div style="background:#fff;padding:20px;border-radius:10px;border-left:5px solid #f59e0b;box-shadow:2px 2px 5px #eee"><strong>TAXA SOLUÇÃO</strong><br><span style="font-size:24px;font-weight:bold">{taxa_resolucao:.1f}%</span></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div style="background:#fff;padding:20px;border-radius:10px;border-left:5px solid #ef4444;box-shadow:2px 2px 5px #eee"><strong>LOJA MAIS ATIVA</strong><br><span style="font-size:16px;font-weight:bold">{loja_critica}</span></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- 3. ANÁLISE PARETO (80/20) E RANKING ---
    col_esquerda, col_direita = st.columns(2)

    with col_esquerda:
        st.subheader("⚖️ Curva ABC: Motivos (Assunto CX)")
        df_motivo = df['Assunto CX:'].value_counts().reset_index()
        df_motivo.columns = ['Motivo', 'Qtd']
        df_motivo['Perc'] = (df_motivo['Qtd'] / df_motivo['Qtd'].sum() * 100).cumsum()
        
        fig_pareto = px.bar(df_motivo, x='Motivo', y='Qtd', color='Qtd', color_continuous_scale='Blues')
        fig_pareto.add_scatter(x=df_motivo['Motivo'], y=df_motivo['Perc'], name='% Acumulada', yaxis='y2', line=dict(color='#ef4444', width=3))
        fig_pareto.update_layout(yaxis2=dict(anchor='x', overlaying='y', side='right', range=[0, 110]), showlegend=False)
        st.plotly_chart(fig_pareto, use_container_width=True)

    with col_direita:
        st.subheader("🏪 Top 10 Lojas (Abertura)")
        df_lojas = df['Nome do solicitante'].value_counts().nlargest(10).reset_index()
        df_lojas.columns = ['Loja', 'Qtd']
        fig_lojas = px.bar(df_lojas, x='Qtd', y='Loja', orientation='h', color='Qtd', color_continuous_scale='Viridis')
        fig_lojas.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_lojas, use_container_width=True)

    # --- 4. SAZONALIDADE E CURVA DE ENTRADAS ---
    st.markdown("---")
    st.subheader("📅 Sazonalidade: Quando os tickets entram?")
    
    col_curva1, col_curva2 = st.columns([2, 1])

    with col_curva1:
        # Ordem dos dias da semana
        dias_ordem = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        df_dias = df['Dia_Semana'].value_counts().reindex(dias_ordem).reset_index()
        df_dias.columns = ['Dia', 'Qtd']
        # Tradução simples para o gráfico
        traducao = {'Monday':'Seg', 'Tuesday':'Ter', 'Wednesday':'Qua', 'Thursday':'Qui', 'Friday':'Sex', 'Saturday':'Sab', 'Sunday':'Dom'}
        df_dias['Dia'] = df_dias['Dia'].map(traducao)

        fig_linha = px.line(df_dias, x='Dia', y='Qtd', markers=True, title="Volume por Dia da Semana", line_shape="spline")
        fig_linha.update_traces(line_color='#002366', fill='tozeroy')
        st.plotly_chart(fig_linha, use_container_width=True)

    with col_curva2:
        st.write("**Distribuição por Status**")
        fig_pizza = px.pie(df, names='Status do ticket', hole=0.5, 
                           color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_pizza, use_container_width=True)

    # --- 5. TABELA DE CONSULTA RÁPIDA ---
    st.markdown("---")
    st.subheader("🔍 Detalhamento dos Dados")
    
    # Filtro Dinâmico
    lojas_filt = st.multiselect("Filtrar por Loja:", options=df['Nome do solicitante'].unique())
    df_final = df[df['Nome do solicitante'].isin(lojas_filt)] if lojas_filt else df
    
    st.dataframe(df_final[['Criação do ticket - Data', 'ID do ticket', 'Nome do solicitante', 'Assunto CX:', 'Status do ticket']], 
                 use_container_width=True, hide_index=True)

    # Botão de Exportação de análise tratada
    csv = df_final.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Baixar Relatório Tratado (CSV)", csv, "analise_tickets_360.csv", "text/csv")

if __name__ == "__main__":
    exibir_teste_planner()
