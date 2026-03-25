import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import plotly.express as px
import database as db # Certifique-se que database.py tenha: salvar_esforco, carregar_esforco, salvar_motivos, carregar_motivos

def exibir(user_role="OPERACIONAL", user_nome="Colaborador"):
    # 1. ESTILIZAÇÃO CSS (Foco em Profissionalismo e Leitura)
    st.markdown("""
        <style>
            .main { background-color: #f8f9fa; }
            .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
            .status-card { padding: 20px; border-radius: 10px; background: white; border-left: 5px solid #002366; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); }
            .user-badge { background-color: #002366; color: white; padding: 5px 15px; border-radius: 20px; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

    # 2. INICIALIZAÇÃO DE ESTADOS (Data Persistence)
    if 'atividades_log' not in st.session_state:
        st.session_state.atividades_log = db.carregar_esforco()
    if 'motivos_gestao' not in st.session_state:
        st.session_state.motivos_gestao = db.carregar_motivos()

    # --- LÓGICA DE TRANSIÇÃO DE ATIVIDADES ---
    def finalizar_atividade_atual(nome_usuario):
        for idx, act in enumerate(st.session_state.atividades_log):
            if act['usuario'] == nome_usuario and act['status'] == 'Em andamento':
                agora = datetime.now()
                inicio = datetime.fromisoformat(act['inicio'])
                duracao = (agora - inicio).total_seconds() / 60
                st.session_state.atividades_log[idx]['fim'] = agora.isoformat()
                st.session_state.atividades_log[idx]['status'] = 'Finalizado'
                st.session_state.atividades_log[idx]['duracao_min'] = round(duracao, 2)
        db.salvar_esforco(st.session_state.atividades_log)

    # --- CABEÇALHO DINÂMICO ---
    c_head1, c_head2 = st.columns([3, 1])
    with c_head1:
        st.title("🚀 Sistema de Gestão de Esforço")
    with c_head2:
        st.markdown(f"<br><span class='user-badge'>👤 {user_nome}</span>", unsafe_allow_html=True)

    # --- DEFINIÇÃO DE ABAS (PONTO 1: RESTRIÇÃO DE ACESSO AO ADM) ---
    menu = ["⏱️ MEU TRABALHO"]
    # Apenas aparece se não for operacional
    if user_role.upper() in ["ADM", "GERENTE", "PLENO"]: 
        menu.append("⚖️ PAINEL ADM (ESFORÇO)")
        menu.append("⚙️ CONFIGURAÇÕES")
    
    tabs = st.tabs(menu)

    # --- ABA 1: OPERACIONAL (INDIVIDUAL) ---
    with tabs[0]:
        st.subheader("Rastreador de Atividade em Tempo Real")
        
        # Verificar atividade ativa do usuário logado (PONTO 2)
        atv_atual = next((a for a in st.session_state.atividades_log if a['usuario'] == user_nome and a['status'] == 'Em andamento'), None)
        
        with st.container(border=True):
            if atv_atual:
                st.warning(f"### ⏳ Atividade Atual: **{atv_atual['motivo']}**")
                inicio_dt = datetime.fromisoformat(atv_atual['inicio'])
                decorrido = (datetime.now() - inicio_dt).seconds // 60
                st.write(f"Iniciado às: {inicio_dt.strftime('%H:%M:%S')} (Duração: {decorrido} min)")
                
                if st.button("⏹️ ENCERRAR ATIVIDADE", type="secondary"):
                    finalizar_atividade_atual(user_nome)
                    st.rerun()
            else:
                st.info("Você não tem nenhuma atividade iniciada no momento.")

        st.divider()
        st.markdown("#### Iniciar Nova Tarefa")
        col_in1, col_in2 = st.columns([2, 1])
        with col_in1:
            motivo_sel = st.selectbox("Selecione o Motivo", st.session_state.motivos_gestao)
            obs_atv = st.text_input("Observação / Ticket")
        with col_in2:
            st.write("<br>", unsafe_allow_html=True)
            if st.button("▶️ DAR PLAY", type="primary"):
                finalizar_atividade_atual(user_nome) # Garante que a anterior pare
                nova_atv = {
                    "usuario": user_nome,
                    "motivo": motivo_sel,
                    "obs": obs_atv,
                    "inicio": datetime.now().isoformat(),
                    "fim": None,
                    "status": "Em andamento",
                    "duracao_min": 0
                }
                st.session_state.atividades_log.append(nova_atv)
                db.salvar_esforco(st.session_state.atividades_log)
                st.rerun()

        # Histórico Individual do Dia
        st.markdown("---")
        st.markdown("#### 📅 Meu Resumo de Hoje")
        hoje_str = datetime.now().date().isoformat()
        meu_hist = [a for a in st.session_state.atividades_log if a['usuario'] == user_nome and a['inicio'].startswith(hoje_str)]
        if meu_hist:
            df_meu = pd.DataFrame(meu_hist)
            df_meu['inicio'] = pd.to_datetime(df_meu['inicio']).dt.strftime('%H:%M')
            st.table(df_meu[['inicio', 'motivo', 'duracao_min', 'status']])
        else:
            st.caption("Nenhuma atividade registrada hoje.")

    # --- ABA 2: PAINEL ADM (PONTO 3: FILTROS E ANALYTICS) ---
    if user_role.upper() in ["ADM", "GERENTE", "PLENO"]:
        with tabs[1]:
            st.subheader("Análise de Esforço da Equipe")
            
            # Preparação do DataFrame
            df_adm = pd.DataFrame(st.session_state.atividades_log)
            if not df_adm.empty:
                df_adm['data_dt'] = pd.to_datetime(df_adm['inicio'])
                df_adm['data_dia'] = df_adm['data_dt'].dt.date
                
                # Barra de Filtros
                with st.expander("🔍 Filtros de Relatório", expanded=True):
                    c_f1, c_f2, c_f3 = st.columns(3)
                    
                    periodo = c_f1.selectbox("Período", ["Hoje", "Últimos 7 Dias", "Mês Atual", "Todo o Histórico"])
                    f_operador = c_f2.multiselect("Filtrar Operador", options=df_adm['usuario'].unique())
                    f_atividade = c_f3.multiselect("Filtrar Atividade", options=df_adm['motivo'].unique())
                    
                    # Lógica de Datas
                    hoje = datetime.now().date()
                    if periodo == "Hoje":
                        df_adm = df_adm[df_adm['data_dia'] == hoje]
                    elif periodo == "Últimos 7 Dias":
                        df_adm = df_adm[df_adm['data_dia'] >= (hoje - timedelta(days=7))]
                    elif periodo == "Mês Atual":
                        df_adm = df_adm[df_adm['data_dt'].dt.month == hoje.month]
                    
                    # Filtros de Multiselect
                    if f_operador:
                        df_adm = df_adm[df_adm['usuario'].isin(f_operador)]
                    if f_atividade:
                        df_adm = df_adm[df_adm['motivo'].isin(f_atividade)]

                # KPIs
                total_horas = df_adm['duracao_min'].sum() / 60
                total_atividades = len(df_adm)
                
                k1, k2, k3 = st.columns(3)
                k1.metric("Total de Horas", f"{total_horas:.2f}h")
                k2.metric("Qtd Atividades", total_atividades)
                k3.metric("Tempo Médio/Atv", f"{(total_horas*60/total_atividades if total_atividades > 0 else 0):.1f} min")

                # Gráficos de Esforço
                st.divider()
                g1, g2 = st.columns(2)
                
                with g1:
                    st.markdown("**Esforço por Operador (Minutos)**")
                    fig_user = px.bar(df_adm.groupby('usuario')['duracao_min'].sum().reset_index(), 
                                      x='usuario', y='duracao_min', color='usuario', text_auto=True)
                    st.plotly_chart(fig_user, use_container_width=True)
                
                with g2:
                    st.markdown("**Volume por Atividade**")
                    fig_atv = px.pie(df_adm, names='motivo', values='duracao_min', hole=0.4)
                    st.plotly_chart(fig_atv, use_container_width=True)

                st.markdown("#### Detalhamento de Logs")
                st.dataframe(df_adm[['usuario', 'data_dia', 'motivo', 'obs', 'duracao_min', 'status']], use_container_width=True)
            else:
                st.info("Aguardando registros de esforço para gerar o painel.")

        # ABA 3: CONFIGURAÇÕES (CADASTRO/DELETE MOTIVOS)
        with tabs[2]:
            st.subheader("Configurações do Sistema")
            with st.container(border=True):
                st.markdown("#### Gerenciar Motivos de Esforço")
                c_mot1, c_mot2 = st.columns([3, 1])
                novo_motivo = c_mot1.text_input("Novo Motivo (Ex: Reunião de Feedback)")
                if c_mot2.button("ADICIONAR", use_container_width=True):
                    if novo_motivo and novo_motivo not in st.session_state.motivos_gestao:
                        st.session_state.motivos_gestao.append(novo_motivo)
                        db.salvar_motivos(st.session_state.motivos_gestao)
                        st.success("Motivo adicionado!")
                        st.rerun()
                
                st.write("Motivos Ativos:")
                for m in st.session_state.motivos_gestao:
                    cm1, cm2 = st.columns([4, 1])
                    cm1.write(f"- {m}")
                    if cm2.button("Deletar", key=f"del_{m}"):
                        st.session_state.motivos_gestao.remove(m)
                        db.salvar_motivos(st.session_state.motivos_gestao)
                        st.rerun()

    # Se o usuário for Operacional, as abas ADM e CONFIG nem chegam a ser renderizadas no menu.
