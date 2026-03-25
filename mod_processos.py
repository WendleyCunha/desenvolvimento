import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import plotly.express as px
import database as db  # Certifique-se de que database.py suporte todas as funções de save/load

# --- CONFIGURAÇÕES TÉCNICAS E DIRETÓRIOS ---
UPLOAD_DIR = "anexos_pqi"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

ROADMAP = [
    {"id": 1, "nome": "Triagem & GUT"}, {"id": 2, "nome": "Escopo & Charter"},
    {"id": 3, "nome": "Autorização Sponsor"}, {"id": 4, "nome": "Coleta & Impedimentos"},
    {"id": 5, "nome": "Modelagem & Piloto"}, {"id": 6, "nome": "Migração (Go-Live)"},
    {"id": 7, "nome": "Acompanhamento/Ajuste"}, {"id": 8, "nome": "Padronização & POP"}
]

MOTIVOS_PADRAO = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna"]
DEPARTAMENTOS = ["CX", "PQI","Compras", "Logística", "TI", "Financeiro", "RH", "Fiscal", "Operações", "Comercial", "Diretoria"]

def exibir(user_role="OPERACIONAL", user_nome="Colaborador"):
    # 1. ESTILIZAÇÃO CSS UNIFICADA
    st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .metric-card { background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #ececec; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .ponto-regua { width: 30px; height: 30px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; font-size: 12px;}
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 8px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 9px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 25px; line-height: 1; }
    </style>
    """, unsafe_allow_html=True)

    # 2. INICIALIZAÇÃO DE ESTADOS (SESSÃO)
    if 'atividades_log' not in st.session_state:
        st.session_state.atividades_log = db.carregar_esforco()
    if 'motivos_gestao' not in st.session_state:
        st.session_state.motivos_gestao = db.carregar_motivos()
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()
    if 'situacoes_diarias' not in st.session_state:
        st.session_state.situacoes_diarias = db.carregar_diario()

    # --- FUNÇÕES DE PERSISTÊNCIA ---
    def salvar_tudo():
        db.salvar_esforco(st.session_state.atividades_log)
        db.salvar_projetos(st.session_state.db_pqi)
        db.salvar_diario(st.session_state.situacoes_diarias)

    def finalizar_timer(nome_usuario):
        for idx, act in enumerate(st.session_state.atividades_log):
            if act['usuario'] == nome_usuario and act['status'] == 'Em andamento':
                st.session_state.atividades_log[idx]['fim'] = datetime.now().isoformat()
                st.session_state.atividades_log[idx]['status'] = 'Finalizado'
                inicio = datetime.fromisoformat(act['inicio'])
                duracao = (datetime.now() - inicio).total_seconds() / 60
                st.session_state.atividades_log[idx]['duracao_min'] = round(duracao, 2)
        db.salvar_esforco(st.session_state.atividades_log)

    # --- MENU DE NAVEGAÇÃO ---
    menu = ["📊 DASHBOARD", "🚀 MEU TRABALHO (TIMER)", "📈 OPERAÇÃO PQI"]
    if user_role in ["ADM", "GERENTE"]:
        menu.insert(2, "⚖️ GESTÃO & DIÁRIO")
    
    tabs = st.tabs(menu)

    # --- ABA 1: DASHBOARD GERAL ---
    with tabs[0]:
        st.subheader("Painel de Controle Unificado")
        c1, c2, c3 = st.columns(3)
        ativos = [p for p in st.session_state.db_pqi if p.get('status') != "Concluído"]
        c1.markdown(f'<div class="metric-card"><div class="metric-label">Projetos Ativos</div><div class="metric-value">{len(ativos)}</div></div>', unsafe_allow_html=True)
        
        # Timer Ativo agora
        em_curso = len([a for a in st.session_state.atividades_log if a['status'] == 'Em andamento'])
        c2.markdown(f'<div class="metric-card"><div class="metric-label">Colaboradores Online</div><div class="metric-value">{em_curso}</div></div>', unsafe_allow_html=True)
        
        # Pendências Diário
        pendentes = len([s for s in st.session_state.situacoes_diarias if s['status'] == "Pendente"])
        c3.markdown(f'<div class="metric-card"><div class="metric-label">Pendências Diário</div><div class="metric-value">{pendentes}</div></div>', unsafe_allow_html=True)

        st.write("---")
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("##### ⏱️ Esforço por Usuário (Timer)")
            df_timer = pd.DataFrame(st.session_state.atividades_log)
            if not df_timer.empty:
                df_sum = df_timer.groupby('usuario')['duracao_min'].sum().reset_index()
                st.plotly_chart(px.bar(df_sum, x='usuario', y='duracao_min', color='usuario'), use_container_width=True)
        with col_g2:
            st.markdown("##### 🍕 Distribuição de Projetos")
            if ativos:
                df_p = pd.DataFrame([{"Projeto": p['titulo'], "Ações": len(p.get('notas', []))} for p in ativos])
                st.plotly_chart(px.pie(df_p, values='Ações', names='Projeto', hole=0.4), use_container_width=True)

    # --- ABA 2: MEU TRABALHO (TIMER) ---
    with tabs[1]:
        st.subheader(f"Rastreador de Tempo: {user_nome}")
        atv_atual = next((a for a in st.session_state.atividades_log if a['usuario'] == user_nome and a['status'] == 'Em andamento'), None)
        
        with st.container(border=True):
            if atv_atual:
                st.error(f"⏳ **EM ANDAMENTO:** {atv_atual['motivo']}")
                if st.button("⏹️ Encerrar Agora"):
                    finalizar_timer(user_nome)
                    st.rerun()
            else:
                st.success("✅ Disponível")
                c_t1, c_t2 = st.columns([2,1])
                motivo_sel = c_t1.selectbox("O que vai fazer?", st.session_state.motivos_gestao)
                if c_t2.button("▶️ INICIAR", type="primary", use_container_width=True):
                    nova_atv = {"usuario": user_nome, "motivo": motivo_sel, "inicio": datetime.now().isoformat(), "status": "Em andamento", "duracao_min": 0}
                    st.session_state.atividades_log.append(nova_atv)
                    db.salvar_esforco(st.session_state.atividades_log)
                    st.rerun()

    # --- ABA GESTÃO (CONDICIONAL) ---
    idx_pqi = 2
    if user_role in ["ADM", "GERENTE"]:
        with tabs[2]:
            sub_g1, sub_g2 = st.tabs(["⚙️ Config Projetos", "📝 Diário de Bordo"])
            with sub_g1:
                if st.button("➕ Novo Projeto PQI"):
                    st.session_state.db_pqi.append({"titulo": "Novo Projeto", "fase": 1, "status": "Ativo", "notas": [], "lembretes": []})
                    salvar_tudo(); st.rerun()
                # Listagem de gestão (simplificada para o exemplo)
                st.write("Gerencie os nomes e status na aba Operação.")
            with sub_g2:
                # Lógica do Diário (conforme seu código de upgrade)
                st.write("Registro de demandas rápidas e solicitações de outros departamentos.")
                # ... (resto da sua lógica de Diário aqui)
        idx_pqi = 3

    # --- ABA OPERAÇÃO PQI ---
    with tabs[idx_pqi]:
        st.subheader("🚀 Roadmap de Processos")
        projs = [p for p in st.session_state.db_pqi if p['status'] == "Ativo"]
        if projs:
            sel_p = st.selectbox("Selecione o Projeto PQI", [p['titulo'] for p in projs])
            projeto = next(p for p in projs if p['titulo'] == sel_p)
            
            # Régua de Roadmap
            cols_r = st.columns(8)
            for i, etapa in enumerate(ROADMAP):
                cl = "ponto-regua"
                if i+1 < projeto['fase']: cl += " ponto-check"
                elif i+1 == projeto['fase']: cl += " ponto-atual"
                cols_r[i].markdown(f'<div class="{cl}">{i+1}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)
            
            # Detalhes do Projeto
            t_exec, t_arquivos = st.tabs(["📝 Notas de Execução", "📁 Dossiê"])
            with t_exec:
                with st.popover("➕ Registrar Ação"):
                    mot = st.selectbox("Motivo", MOTIVOS_PADRAO)
                    dep = st.selectbox("Depto Impactado", DEPARTAMENTOS)
                    txt = st.text_area("O que foi feito?")
                    if st.button("Salvar Nota"):
                        projeto['notas'].append({"motivo": mot, "depto": dep, "texto": txt, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase']})
                        salvar_tudo(); st.rerun()
                
                for n in reversed(projeto['notas']):
                    st.info(f"**{n['data']} - {n['motivo']} ({n['depto']})**: {n['texto']}")

    # Rodapé de salvamento manual se necessário
    if st.sidebar.button("💾 Forçar Backup Geral"):
        salvar_tudo()
        st.sidebar.success("Dados sincronizados!")
