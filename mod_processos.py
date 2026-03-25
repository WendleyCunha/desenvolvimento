import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import plotly.express as px
import database as db
import time

# --- DIRETÓRIO DE ANEXOS ---
UPLOAD_DIR = "anexos_pqi"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- CONFIGURAÇÕES DO ROADMAP ---
ROADMAP = [
    {"id": 1, "nome": "Triagem & GUT"}, {"id": 2, "nome": "Escopo & Charter"},
    {"id": 3, "nome": "Autorização Sponsor"}, {"id": 4, "nome": "Coleta & Impedimentos"},
    {"id": 5, "nome": "Modelagem & Piloto"}, {"id": 6, "nome": "Migração (Go-Live)"},
    {"id": 7, "nome": "Acompanhamento/Ajuste"}, {"id": 8, "nome": "Padronização & POP"}
]

DEPARTAMENTOS = ["CX", "PQI","Compras", "Logística", "TI", "Financeiro", "RH", "Fiscal", "Operações", "Comercial", "Diretoria"]

def exibir(user_role="OPERACIONAL", user_name="Usuário"):
    # 1. ESTILO CSS
    st.markdown("""
    <style>
        .metric-card { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #ececec; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .ponto-regua { width: 30px; height: 30px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; font-size: 12px;}
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 8px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 9px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 25px; line-height: 1; }
        .timer-ativo { background-color: #f0fdf4; border: 1px solid #16a34a; padding: 10px; border-radius: 5px; color: #16a34a; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

    # 2. INICIALIZAÇÃO DE DADOS
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()
    if 'situacoes_diarias' not in st.session_state:
        st.session_state.situacoes_diarias = db.carregar_diario()
    if 'motivos_timer' not in st.session_state:
        st.session_state.motivos_timer = db.carregar_motivos()
    if 'historico_esforco' not in st.session_state:
        st.session_state.historico_esforco = db.carregar_esforco()

    def salvar_seguro():
        db.salvar_projetos(st.session_state.db_pqi)
        db.salvar_diario(st.session_state.situacoes_diarias)
        db.salvar_esforco(st.session_state.historico_esforco)

    # --- LÓGICA DO TIMER (ATIVIDADE EM ANDAMENTO) ---
    def finalizar_atividade_atual():
        for atv in st.session_state.historico_esforco:
            if atv['usuario'] == user_name and atv['status'] == 'Em andamento':
                atv['fim'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                atv['status'] = 'Finalizado'
                # Cálculo de duração em minutos
                inicio = datetime.strptime(atv['inicio'], "%d/%m/%Y %H:%M:%S")
                fim = datetime.now()
                atv['duracao_min'] = round((fim - inicio).total_seconds() / 60, 2)
        salvar_seguro()

    # --- DEFINIÇÃO DAS ABAS ---
    titulos = ["⏱️ MEU TIMER", "📊 DASHBOARD"]
    if user_role == "ADM":
        titulos.append("🛡️ PAINEL ADM")
    titulos.append("⚙️ GESTÃO")
    titulos.append("🚀 OPERAÇÃO PQI")

    tabs = st.tabs(titulos)
    
    # --- ABA 0: MEU TIMER (INDIVIDUAL) ---
    with tabs[0]:
        st.subheader(f"⏱️ Controle de Esforço: {user_name}")
        
        # Verificar se há atividade rodando
        atv_atual = next((a for a in st.session_state.historico_esforco if a['usuario'] == user_name and a['status'] == 'Em andamento'), None)
        
        if atv_atual:
            st.markdown(f"<div class='timer-ativo'>⏳ ATIVIDADE ATUAL: {atv_atual['motivo']} (Iniciada às {atv_atual['inicio']})</div>", unsafe_allow_html=True)
            if st.button("⏹️ Encerrar Atividade Atual", type="secondary"):
                finalizar_atividade_atual()
                st.rerun()
        else:
            st.info("Você não tem nenhuma atividade em andamento no momento.")

        st.divider()
        col_t1, col_t2 = st.columns(2)
        novo_motivo_timer = col_t1.selectbox("O que vai iniciar agora?", st.session_state.motivos_timer)
        obs_timer = col_t2.text_input("Observação (opcional)")
        
        if st.button("▶️ INICIAR NOVA ATIVIDADE", type="primary", use_container_width=True):
            finalizar_atividade_atual() # Interrompe a anterior se houver
            nova_atv = {
                "usuario": user_name,
                "motivo": novo_motivo_timer,
                "obs": obs_timer,
                "inicio": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "fim": None,
                "duracao_min": 0,
                "status": "Em andamento"
            }
            st.session_state.historico_esforco.append(nova_atv)
            salvar_seguro()
            st.rerun()

        st.markdown("### 📋 Meu Histórico de Hoje")
        meu_df = pd.DataFrame([a for a in st.session_state.historico_esforco if a['usuario'] == user_name])
        if not meu_df.empty:
            st.dataframe(meu_df.sort_values(by="inicio", ascending=False), use_container_width=True, hide_index=True)

    # --- ABA 1: DASHBOARD ---
    with tabs[1]:
        # Filtro individual no Dash (ADM vê tudo, Operacional vê só o dele)
        if user_role == "ADM":
            user_filter = st.multiselect("Filtrar Usuário:", list(set(a['usuario'] for a in st.session_state.historico_esforco)), default=None)
        else:
            user_filter = [user_name]

        df_esf_dash = pd.DataFrame(st.session_state.historico_esforco)
        if not df_esf_dash.empty:
            if user_filter:
                df_esf_dash = df_esf_dash[df_esf_dash['usuario'].isin(user_filter)]
            
            c1, c2 = st.columns(2)
            fig_esf = px.bar(df_esf_dash, x="usuario", y="duracao_min", color="motivo", title="Esforço Total (Minutos) por Usuário")
            c1.plotly_chart(fig_esf, use_container_width=True)
            
            fig_pizza = px.pie(df_esf_dash, values="duracao_min", names="motivo", title="Distribuição de Atividades")
            c2.plotly_chart(fig_pizza, use_container_width=True)

    # --- ABA 2: PAINEL ADM (SOMENTE ADM) ---
    if user_role == "ADM":
        with tabs[2]:
            st.subheader("🛡️ Gestão Administrativa")
            
            sub_adm1, sub_adm2 = st.tabs(["👥 Usuários Online", "🏷️ Gerenciar Motivos"])
            
            with sub_adm1:
                st.write("**Atividades em Andamento Agora:**")
                online = [a for a in st.session_state.historico_esforco if a['status'] == 'Em andamento']
                if online:
                    st.table(pd.DataFrame(online)[['usuario', 'motivo', 'inicio', 'obs']])
                else:
                    st.success("Nenhum colaborador com atividade pendente.")

            with sub_adm2:
                col_m1, col_m2 = st.columns([3, 1])
                novo_m = col_m1.text_input("Novo Motivo de Esforço")
                if col_m2.button("Adicionar"):
                    st.session_state.motivos_timer.append(novo_m)
                    db.salvar_motivos(st.session_state.motivos_timer)
                    st.rerun()
                
                st.write("---")
                for m in st.session_state.motivos_timer:
                    cm1, cm2 = st.columns([4, 1])
                    cm1.write(m)
                    if cm2.button("Deletar", key=f"del_{m}"):
                        st.session_state.motivos_timer.remove(m)
                        db.salvar_motivos(st.session_state.motivos_timer)
                        st.rerun()

    # --- ABA GESTÃO (Integrada com sua lógica anterior) ---
    # (Ajuste o índice das abas conforme o papel do usuário)
    idx_gestao = 3 if user_role == "ADM" else 2
    with tabs[idx_gestao]:
        st.write("Aqui fica a sua lógica de Criar/Deletar Projetos e o Diário de Situações...")
        # [MANTENHA AQUI O SEU CÓDIGO ORIGINAL DA ABA GESTÃO]

    # --- ABA OPERAÇÃO PQI ---
    idx_op = 4 if user_role == "ADM" else 3
    with tabs[idx_op]:
        st.write("Aqui fica o seu Roadmap, Dossiê e Histórico de notas do PQI...")
        # [MANTENHA AQUI O SEU CÓDIGO ORIGINAL DA ABA OPERAÇÃO PQI]

    # --- 3. OPERAÇÃO PQI ---
    with tab_operacao:
        st.subheader("🚀 Operação de Processos")
        projs = st.session_state.db_pqi
        if not projs:
            st.warning("Vá na aba GESTÃO e crie seu primeiro projeto.")
        else:
            c_f1, c_f2 = st.columns([1, 2])
            status_sel = c_f1.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
            map_status = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
            filtrados = [p for p in projs if p.get('status', 'Ativo') == map_status[status_sel]]
            
            if filtrados:
                escolha = c_f2.selectbox("Selecione o Projeto:", [p['titulo'] for p in filtrados])
                projeto = next(p for p in filtrados if p['titulo'] == escolha)
                
                st.write("")
                cols_r = st.columns(8)
                for i, etapa in enumerate(ROADMAP):
                    n, cl, txt = i+1, "ponto-regua", str(i+1)
                    if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                    elif n == projeto['fase']: cl += " ponto-atual"
                    cols_r[i].markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

                t_exec, t_dossie, t_esforco = st.tabs(["📝 Execução Diária", "📁 Dossiê & Arquivos", "📊 Análise de Esforço"])

                with t_exec:
                    col_e1, col_e2 = st.columns([2, 1])
                    with col_e1:
                        st.markdown(f"### Etapa {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                        with st.popover("➕ Adicionar Registro de Esforço", use_container_width=True):
                            c_p1, c_p2 = st.columns(2)
                            mot = c_p1.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                            dep = c_p2.selectbox("Departamento", DEPARTAMENTOS)
                            dsc = st.text_area("Descrição")
                            cl1, cl2 = st.columns(2)
                            dl = cl1.date_input("Data Lembrete", value=None, key=f"d_pqi_{projeto['titulo']}")
                            hl = cl2.time_input("Hora Lembrete", value=None, key=f"h_pqi_{projeto['titulo']}")
                            if st.button("Gravar no Banco", type="primary"):
                                if dl and hl:
                                    projeto.setdefault('lembretes', []).append({"id": datetime.now().timestamp(), "data_hora": f"{dl.strftime('%d/%m/%Y')} {hl.strftime('%H:%M')}", "texto": f"{projeto['titulo']}: {mot}"})
                                projeto['notas'].append({"motivo": mot, "depto": dep, "texto": dsc, "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "fase_origem": projeto['fase']})
                                salvar_seguro(); st.rerun()
                        st.divider()
                        notas_fase = [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]
                        for n in reversed(notas_fase):
                            with st.expander(f"📌 {n['motivo']} ({n.get('depto', 'Geral')}) - {n['data']}"): 
                                st.write(n['texto'])

                    with col_e2:
                        st.markdown("#### ⚙️ Controle")
                        if st.button("▶️ AVANÇAR", use_container_width=True, type="primary") and projeto['fase'] < 8:
                            projeto['fase'] += 1
                            salvar_seguro()
                            st.rerun()
                        
                        if st.button("⏪ RECUAR", use_container_width=True) and projeto['fase'] > 1:
                            projeto['fase'] -= 1
                            salvar_seguro()
                            st.rerun()

                        st.markdown("#### ⏰ Lembretes")
                        # .get([], []) garante que o código não quebre se a lista estiver vazia
                        lembretes_atuais = projeto.get('lembretes', [])
                        
                        for l_idx, l in enumerate(lembretes_atuais):
                            with st.container(border=True):
                                st.caption(f"📅 {l['data_hora']}")
                                st.write(l['texto'])
                                
                                # CORREÇÃO AQUI: l.get('id', l_idx) com ponto, não colchetes
                                if st.button("Concluir", key=f"done_pqi_{l.get('id', l_idx)}"): 
                                    projeto['lembretes'].pop(l_idx)
                                    salvar_seguro() # Isso grava as alterações no seu banco de dados
                                    st.success("Lembrete concluído!")
                                    st.rerun()

                with t_dossie:
                    sub_dos1, sub_dos2 = st.tabs(["📂 Pastas", "📜 Histórico"])
                    with sub_dos1:
                        with st.popover("➕ Criar Pasta"):
                            nome_pasta = st.text_input("Nome da Pasta")
                            if st.button("Salvar Pasta"):
                                projeto.setdefault('pastas_virtuais', {})[nome_pasta] = []
                                salvar_seguro(); st.rerun()
                        pastas = projeto.get('pastas_virtuais', {})
                        for p_nome in list(pastas.keys()):
                            with st.expander(f"📁 {p_nome}"):
                                c_rn1, c_rn2 = st.columns([3, 1])
                                novo_nome = c_rn1.text_input("Renomear", p_nome, key=f"r_{p_nome}_{projeto['titulo']}")
                                if novo_nome != p_nome:
                                    pastas[novo_nome] = pastas.pop(p_nome); salvar_seguro(); st.rerun()
                                if c_rn2.button("🗑️", key=f"d_{p_nome}"):
                                    del pastas[p_nome]; salvar_seguro(); st.rerun()
                                up_files = st.file_uploader("Anexar", accept_multiple_files=True, key=f"u_{p_nome}")
                                if st.button("Subir Arquivos", key=f"b_{p_nome}"):
                                    for a in up_files:
                                        path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{a.name}")
                                        with open(path, "wb") as f: f.write(a.getbuffer())
                                        pastas[p_nome].append({"nome": a.name, "path": path, "data": datetime.now().strftime("%d/%m/%Y")})
                                    salvar_seguro(); st.rerun()

                    with sub_dos2:
                        df_hist = pd.DataFrame(projeto.get('notas', []))
                        if not df_hist.empty: st.dataframe(df_hist, use_container_width=True, hide_index=True)

                with t_esforco:
                    df_esf = pd.DataFrame(projeto.get('notas', []))
                    if not df_esf.empty:
                        st.markdown(f"### Análise: {projeto['titulo']}")
                        c_esf1, c_esf2 = st.columns(2)
                        with c_esf1: st.bar_chart(df_esf['motivo'].value_counts())
                        with c_esf2:
                            df_p = df_esf['motivo'].value_counts().reset_index()
                            df_p.columns = ['Motivo', 'Qtd']
                            fig = px.pie(df_p, values='Qtd', names='Motivo', hole=0.4)
                            fig.update_layout(margin=dict(l=20,r=20,t=20,b=20), height=300)
                            st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhum projeto encontrado com este status.")
