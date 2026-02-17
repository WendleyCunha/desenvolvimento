import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import database as db  # Importa o seu database.py que ajustamos para Firestore

def exibir_teste_planner(user_role="OPERACIONAL"):
    st.title("📊 Indicadores 360º | Inteligência King Star")
    st.markdown("---")

    # --- 1. CARREGAMENTO DE DADOS DO BANCO (PERSISTÊNCIA) ---
    try:
        dados_banco = db.carregar_tickets()
        if dados_banco:
            df_base = pd.DataFrame(dados_banco)
            # Normalização de tipos para garantir a comparação
            df_base['ID do ticket'] = df_base['ID do ticket'].astype(str)
            df_base['Criação do ticket - Data'] = pd.to_datetime(df_base['Criação do ticket - Data'], errors='coerce')
        else:
            df_base = pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao conectar ao banco: {e}")
        df_base = pd.DataFrame()

    # --- 2. ÁREA DE ALIMENTAÇÃO (BARRA LATERAL) ---
    with st.sidebar:
        st.header("📥 Alimentar Base")
        uploaded_file = st.file_uploader("Subir nova planilha", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                # Leitura do arquivo
                df_upload = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                df_upload['ID do ticket'] = df_upload['ID do ticket'].astype(str)
                
                st.info(f"📂 {len(df_upload)} registros lidos no arquivo.")
                
                if st.button("🚀 GRAVAR NOVOS DADOS", use_container_width=True, type="primary"):
                    # Lógica de Deduplicação pelo ID do Ticket
                    if not df_base.empty:
                        ids_existentes = set(df_base['ID do ticket'])
                        df_filtrado = df_upload[~df_upload['ID do ticket'].isin(ids_existentes)]
                    else:
                        df_filtrado = df_upload
                    
                    if not df_filtrado.empty:
                        # Prepara para o Firebase (converte datas para string)
                        df_para_gravar = df_filtrado.copy()
                        if 'Criação do ticket - Data' in df_para_gravar.columns:
                            df_para_gravar['Criação do ticket - Data'] = df_para_gravar['Criação do ticket - Data'].astype(str)
                        
                        registros = df_para_gravar.to_dict('records')
                        if db.salvar_tickets(registros):
                            st.balloons()
                            st.success(f"Sucesso! {len(df_filtrado)} novos tickets gravados.")
                            st.rerun()
                    else:
                        st.warning("Todos os tickets deste arquivo já constam no banco.")
            except Exception as e:
                st.error(f"Erro no processamento: {e}")

    # Se não houver nada no banco, para aqui
    if df_base.empty:
        st.info("👋 O banco de dados está vazio. Suba uma planilha na lateral para começar.")
        st.stop()

    # --- 3. FILTROS DE ANÁLISE ---
    df_base['Mes_Ano'] = df_base['Criação do ticket - Data'].dt.strftime('%m/%Y')
    
    with st.sidebar:
        st.divider()
        st.header("🔍 Filtros de Análise")
        meses_disp = sorted(df_base['Mes_Ano'].dropna().unique(), reverse=True)
        mes_sel = st.selectbox("Escolha o Mês:", ["Todos"] + meses_disp)

    # Filtragem dos dados para visualização
    df_view = df_base if mes_sel == "Todos" else df_base[df_base['Mes_Ano'] == mes_sel]

    # --- 4. DASHBOARD VISUAL (TAB 1) E DETALHAMENTO (TAB 2) ---
    tab_dash, tab_detalhes = st.tabs(["📊 Visão 360º", "📋 Detalhamento dos Dados"])

    with tab_dash:
        # --- KPIS PRINCIPAIS ---
        total_tickets = len(df_view)
        fechados = len(df_view[df_view['Status do ticket'] == 'Closed'])
        taxa_resolucao = (fechados / total_tickets) * 100 if total_tickets > 0 else 0
        loja_critica = df_view['Nome do solicitante'].mode()[0] if not df_view.empty else "N/A"

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div style="background:#fff;padding:20px;border-radius:10px;border-left:5px solid #002366;box-shadow:2px 2px 5px #eee"><strong>TOTAL TICKETS</strong><br><span style="font-size:24px;font-weight:bold">{total_tickets}</span></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div style="background:#fff;padding:20px;border-radius:10px;border-left:5px solid #10b981;box-shadow:2px 2px 5px #eee"><strong>RESOLVIDOS</strong><br><span style="font-size:24px;font-weight:bold">{fechados}</span></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div style="background:#fff;padding:20px;border-radius:10px;border-left:5px solid #f59e0b;box-shadow:2px 2px 5px #eee"><strong>TAXA SOLUÇÃO</strong><br><span style="font-size:24px;font-weight:bold">{taxa_resolucao:.1f}%</span></div>', unsafe_allow_html=True)
        with c4:
            st.markdown(f'<div style="background:#fff;padding:20px;border-radius:10px;border-left:5px solid #ef4444;box-shadow:2px 2px 5px #eee"><strong>LOJA + ATIVA</strong><br><span style="font-size:16px;font-weight:bold">{loja_critica}</span></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # --- GRÁFICOS PARETO E RANKING ---
        col_esquerda, col_direita = st.columns(2)
        with col_esquerda:
            st.subheader("⚖️ Curva ABC: Motivos")
            df_motivo = df_view['Assunto CX:'].value_counts().reset_index()
            df_motivo.columns = ['Motivo', 'Qtd']
            df_motivo['Perc'] = (df_motivo['Qtd'] / df_motivo['Qtd'].sum() * 100).cumsum()
            
            fig_pareto = px.bar(df_motivo.head(10), x='Motivo', y='Qtd', color='Qtd', color_continuous_scale='Blues')
            fig_pareto.add_scatter(x=df_motivo['Motivo'], y=df_motivo['Perc'], name='% Acumulada', yaxis='y2', line=dict(color='#ef4444', width=3))
            fig_pareto.update_layout(yaxis2=dict(anchor='x', overlaying='y', side='right', range=[0, 110]), showlegend=False)
            st.plotly_chart(fig_pareto, use_container_width=True)

        with col_direita:
            st.subheader("🏪 Top 10 Lojas")
            df_lojas = df_view['Nome do solicitante'].value_counts().nlargest(10).reset_index()
            df_lojas.columns = ['Loja', 'Qtd']
            fig_lojas = px.bar(df_lojas, x='Qtd', y='Loja', orientation='h', color='Qtd', color_continuous_scale='Viridis')
            fig_lojas.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_lojas, use_container_width=True)

        # --- SAZONALIDADE E STATUS ---
        st.markdown("---")
        c_curva1, c_curva2 = st.columns([2, 1])
        with c_curva1:
            st.subheader("📅 Volume por Dia da Semana")
            df_view['Dia_Semana'] = df_view['Criação do ticket - Data'].dt.day_name()
            dias_ordem = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            traducao = {'Monday':'Seg', 'Tuesday':'Ter', 'Wednesday':'Qua', 'Thursday':'Qui', 'Friday':'Sex', 'Saturday':'Sab', 'Sunday':'Dom'}
            
            df_dias = df_view['Dia_Semana'].value_counts().reindex(dias_ordem).reset_index()
            df_dias.columns = ['Dia', 'Qtd']
            df_dias['Dia'] = df_dias['Dia'].map(traducao)
            
            fig_linha = px.line(df_dias, x='Dia', y='Qtd', markers=True, line_shape="spline")
            fig_linha.update_traces(line_color='#002366', fill='tozeroy')
            st.plotly_chart(fig_linha, use_container_width=True)

        with c_curva2:
            st.subheader("📌 Status")
            fig_pizza = px.pie(df_view, names='Status do ticket', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pizza, use_container_width=True)

    with tab_detalhes:
        st.subheader("🔍 Filtros de Tabela")
        f_lojas = st.multiselect("Filtrar Lojas:", options=df_view['Nome do solicitante'].unique())
        
        df_final = df_view.copy()
        if f_lojas:
            df_final = df_final[df_final['Nome do solicitante'].isin(f_lojas)]
        
        st.dataframe(df_final[['Criação do ticket - Data', 'ID do ticket', 'Nome do solicitante', 'Assunto CX:', 'Status do ticket']], 
                     use_container_width=True, hide_index=True)
        
        csv = df_final.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Baixar Relatório Tratado (CSV)", csv, f"tickets_{mes_sel}.csv", "text/csv")

if __name__ == "__main__":
    exibir_teste_planner()
