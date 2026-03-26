import streamlit as st
import database as db
import pandas as pd
import base64
from datetime import datetime, timedelta
import plotly.express as px
from streamlit_option_menu import option_menu 

# =========================================================
# 0. CONFIGURAÇÕES E MAPAS
# =========================================================
st.set_page_config(page_title="Hub King Star | Master", layout="wide", page_icon="👑")

MAPA_MODULOS_MESTRE = {
    "🏗️ Manutenção": "manutencao",
    "🎯 Processos": "processos",
    "📄 RH Docs": "rh",
    "📊 Operação": "operacao",
    "🚗 Minha Spin": "spin",
    "🚌 Passagens": "passagens",
}

ICON_MAP = {
    "🏠 Home": "house",
    "🏗️ Manutenção": "tools",
    "🎯 Processos": "diagram-3",
    "📄 RH Docs": "file-earmark-text",
    "📊 Operação": "box-seam",
    "🚗 Minha Spin": "car-front-fill",
    "🚌 Passagens": "bus-front",
    "⚙️ Central de Comando": "shield-lock"
}

# =========================================================
# 1. FUNÇÕES AUXILIARES, ESTILO E ESFORÇO
# =========================================================
def processar_foto(arquivo_subido):
    if arquivo_subido is not None:
        try:
            bytes_data = arquivo_subido.getvalue()
            base64_img = base64.b64encode(bytes_data).decode()
            return f"data:image/png;base64,{base64_img}"
        except Exception as e:
            st.error(f"Erro ao processar imagem: {e}")
    return None

def finalizar_atividade_atual(nome_usuario):
    logs = db.carregar_esforco()
    houve_alteracao = False
    agora = datetime.now()
    for idx, act in enumerate(logs):
        if act['usuario'] == nome_usuario and act['status'] == 'Em andamento':
            logs[idx]['fim'] = agora.isoformat()
            logs[idx]['status'] = 'Finalizado'
            inicio = datetime.fromisoformat(act['inicio'])
            duracao = (agora - inicio).total_seconds() / 60
            logs[idx]['duracao_min'] = round(duracao, 2)
            houve_alteracao = True
    if houve_alteracao:
        db.salvar_esforco(logs)

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .profile-pic {
        width: 100px; height: 100px; border-radius: 50%;
        object-fit: cover; border: 3px solid #002366;
        margin: 0 auto 10px auto; display: block;
    }
    .reminder-card {
        background: white; padding: 15px; border-radius: 10px;
        border-left: 5px solid #ef4444; margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .diary-card {
        background: white; padding: 15px; border-radius: 10px;
        border-left: 5px solid #3b82f6; margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .status-online { color: #10b981; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)
# =========================================================
# 2. AUTENTICAÇÃO
# =========================================================
usuarios = db.carregar_usuarios_firebase()
departamentos = db.carregar_departamentos()

# --- BLOCO DE EMERGÊNCIA (Simulação na Memória) ---
if not usuarios:
    # Se o Firebase falhar ou estiver vazio, criamos um acesso temporário
    usuarios = {
        'admin': {
            "nome": "Wendley Admin",
            "senha": "123",
            "role": "ADM",
            "depto": "DIRETORIA",
            "modulos": ["manutencao", "processos", "rh", "operacao", "spin", "passagens"]
        }
    }
# --------------------------------------------------

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center;'>Wendley Portal</h1>", unsafe_allow_html=True)
        u = st.text_input("Usuário").lower().strip()
        p = st.text_input("Senha", type="password")
        if st.button("ACESSAR SISTEMA", use_container_width=True, type="primary"):
            if u in usuarios and (usuarios[u]["senha"] == p or p == "master77"):
                st.session_state.autenticado = True
                st.session_state.user_id = u
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    st.stop()

user_id = st.session_state.user_id
user_info = usuarios.get(user_id)
user_role = user_info.get('role', 'OPERACIONAL')
is_adm = user_role == "ADM"
modulos_permitidos = user_info.get('modulos', [])

# =========================================================
# 3. SIDEBAR E NAVEGAÇÃO
# =========================================================
with st.sidebar:
    foto_atual = user_info.get('foto') or "https://cdn-icons-png.flaticon.com/512/149/149071.png"
    st.markdown(f'<img src="{foto_atual}" class="profile-pic">', unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; font-weight:bold; margin-bottom:20px;'>{user_info['nome']}</p>", unsafe_allow_html=True)
    
    # Montagem dinâmica do menu
    menu_options = ["🏠 Home"]
    
    # 1. Adiciona módulos permitidos ou se for ADM
    for nome, mid in MAPA_MODULOS_MESTRE.items():
        if is_adm or mid in modulos_permitidos:
            menu_options.append(nome)
    
    # 2. LIBERAÇÃO DA CENTRAL: Agora inclui o perfil GERENTE
    if is_adm or user_role == "GERENTE":
        menu_options.append("⚙️ Central de Comando")

    # Renderização do menu lateral
    escolha = option_menu(
        None, 
        menu_options,
        icons=[ICON_MAP.get(opt, "circle") for opt in menu_options],
        menu_icon="cast", 
        default_index=0,
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#002366", "font-size": "18px"}, 
            "nav-link": {"font-size": "14px", "text-align": "left", "margin":"5px", "--hover-color": "#e2e8f0"},
            "nav-link-selected": {"background-color": "#002366", "color": "white"},
        }
    )

    st.markdown("<br>" * 2, unsafe_allow_html=True)
    
    # --- Cronômetro de Esforço na Sidebar ---
    atividades_log = db.carregar_esforco()
    atv_atual = next((a for a in atividades_log if a['usuario'] == user_info['nome'] and a['status'] == 'Em andamento'), None)
    
    with st.container(border=True):
        if atv_atual:
            st.caption(f"⏳ Ativo: {atv_atual['motivo']}")
            if st.button("⏹️ Parar Cronômetro", key="side_stop"):
                finalizar_atividade_atual(user_info['nome'])
                st.rerun()
        else:
            st.caption("⏸️ Em Pausa / Disponível")

    with st.expander("👤 Meu Perfil"):
        up_f = st.file_uploader("Trocar Foto", type=['jpg', 'png'])
        nova_senha_user = st.text_input("Nova Senha", type="password")
        confirma_senha_user = st.text_input("Confirmar Senha", type="password")
        if st.button("Salvar Alterações"):
            atualizacoes = {}
            if up_f: atualizacoes['foto'] = processar_foto(up_f)
            if nova_senha_user and nova_senha_user == confirma_senha_user:
                atualizacoes['senha'] = nova_senha_user
            if atualizacoes:
                db.salvar_usuario(user_id, atualizacoes)
                st.success("Atualizado!"); st.rerun()

    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.autenticado = False
        st.rerun()

# =========================================================
# 4. FUNÇÕES DA HOME E CENTRAL
# =========================================================

def exibir_home():
    st.title(f"Olá, {user_info['nome']}! 👋")
    
    tab_esforco, tab_hoje, tab_agenda, tab_novo = st.tabs(["⚡ MEU ESFORÇO", "🚀 Visão de Hoje", "📅 Agenda Master", "➕ Novo Agendamento"])
    
    projs = db.carregar_projetos()
    diario = db.carregar_diario()
    atividades_log = db.carregar_esforco()
    motivos_gestao = db.carregar_motivos()
    hoje_str = datetime.now().strftime("%d/%m/%Y")

    with tab_esforco:
        atv_ativa = next((a for a in atividades_log if a['usuario'] == user_info['nome'] and a['status'] == 'Em andamento'), None)
        
        c1, c2 = st.columns([1, 1])
        with c1:
            if atv_ativa:
                st.info(f"🚀 **Atividade Atual:** {atv_ativa['motivo']}")
                inicio_dt = datetime.fromisoformat(atv_ativa['inicio'])
                decorrido = datetime.now() - inicio_dt
                st.write(f"Iniciado às {inicio_dt.strftime('%H:%M')} ({decorrido.seconds // 60} min decorridos)")
                if st.button("Finalizar Agora", type="secondary", use_container_width=True):
                    finalizar_atividade_atual(user_info['nome'])
                    st.rerun()
            else:
                st.success("Tudo pronto para começar uma nova tarefa!")

        with c2:
            motivo_sel = st.selectbox("O que vai fazer agora?", motivos_gestao)
            detalhes = st.text_input("Obs/Ticket")
            if st.button("INICIAR TAREFA", type="primary", use_container_width=True):
                # AJUSTE 1: FINALIZAÇÃO AUTOMÁTICA DA ANTERIOR
                finalizar_atividade_atual(user_info['nome'])
                
                # Recarrega logs para garantir integridade após fechar a anterior
                logs_atualizados = db.carregar_esforco()
                nova_atv = {
                    "usuario": user_info['nome'], "motivo": motivo_sel, "detalhes": detalhes,
                    "inicio": datetime.now().isoformat(), "fim": None,
                    "status": "Em andamento", "duracao_min": 0
                }
                logs_atualizados.append(nova_atv)
                db.salvar_esforco(logs_atualizados)
                st.rerun()
        
        st.divider()
        st.subheader("Minhas Atividades de Hoje")
        meu_hist = [a for a in atividades_log if a['usuario'] == user_info['nome'] and a['inicio'].startswith(datetime.now().date().isoformat())]
        if meu_hist:
            df_meu = pd.DataFrame(meu_hist)
            df_meu['inicio'] = pd.to_datetime(df_meu['inicio']).dt.strftime('%H:%M')
            # AJUSTE 2: OBS/TICKET NA LISTA
            st.dataframe(df_meu[['inicio', 'motivo', 'detalhes', 'status', 'duracao_min']], use_container_width=True)

    with tab_hoje:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📌 Processos (PQI)")
            tem_pqi = False
            for p_idx, p in enumerate(projs):
                if 'lembretes' in p:
                    for l_idx, l in enumerate(p['lembretes']):
                        if hoje_str in l['data_hora']:
                            tem_pqi = True
                            with st.container(border=True):
                                st.markdown(f'<div class="reminder-card"><small style="color:red;">⏰ HOJE</small><br><strong>Projeto:</strong> {p["titulo"]}<br><strong>Tarefa:</strong> {l["texto"]}</div>', unsafe_allow_html=True)
                                if st.button(f"Concluir PQI", key=f"main_pqi_{p_idx}_{l_idx}"):
                                    p['lembretes'].pop(l_idx)
                                    db.salvar_projetos(projs)
                                    st.toast("Concluído!"); st.rerun()
            if not tem_pqi: st.success("Sem PQIs hoje!")
        with col2:
            st.subheader("📓 Diário")
            tem_dir = False
            for idx, sit in enumerate(diario):
                if sit.get('status') == "Pendente" and sit.get('lembrete') != "N/A":
                    if hoje_str in sit['lembrete']:
                        tem_dir = True
                        with st.container(border=True):
                            st.markdown(f'<div class="diary-card"><small style="color:#3b82f6;">📅 AGENDADO</small><br><strong>Solicitação:</strong> {sit["solicitacao"]}<br><strong>Depto:</strong> {sit["depto"]}</div>', unsafe_allow_html=True)
                            if st.button(f"Executado", key=f"main_dir_{idx}"):
                                sit['status'] = "Executado"
                                db.salvar_diario(diario)
                                st.toast("Atualizado!"); st.rerun()
            if not tem_dir: st.info("Diário limpo hoje.")

    with tab_agenda:
        st.subheader("🗓️ Próximos Compromissos")
        agenda_data = []
        for p in projs:
            for l in p.get('lembretes', []):
                data_limpa = l['data_hora'].split(" ")[0]
                if data_limpa > hoje_str:
                    agenda_data.append({"Data": data_limpa, "Origem": f"PQI: {p['titulo']}", "Descrição": l['texto']})
        for sit in diario:
            if sit.get('status') == "Pendente" and sit.get('lembrete') != "N/A":
                data_limpa = sit['lembrete'].split(" ")[0]
                if data_limpa > hoje_str:
                    agenda_data.append({"Data": data_limpa, "Origem": f"DIÁRIO: {sit['depto']}", "Descrição": sit['solicitacao']})
        if agenda_data:
            df_agenda = pd.DataFrame(agenda_data).sort_values(by="Data")
            st.dataframe(df_agenda, use_container_width=True, hide_index=True)
        else:
            st.write("Nenhum compromisso para os próximos dias.")

    with tab_novo:
        st.subheader("🎯 Criar Agendamento Direto")
        with st.form("form_novo_lembrete_main"):
            tipo = st.radio("Vincular a:", ["Processos (PQI)", "Situações Diárias (Diário)"], horizontal=True)
            txt_lembrete = st.text_input("O que precisa ser feito?")
            c_data, c_hora = st.columns(2)
            d_agendada = c_data.date_input("Data do Lembrete")
            h_agendada = c_hora.time_input("Hora do Lembrete")
            projeto_vinculo = None
            if tipo == "Processos (PQI)":
                projeto_vinculo = st.selectbox("Selecione o Projeto:", [p['titulo'] for p in projs])
            if st.form_submit_button("Gerar Lembrete Monstro 🚀", use_container_width=True):
                data_final = f"{d_agendada.strftime('%d/%m/%Y')} {h_agendada.strftime('%H:%M')}"
                if tipo == "Processos (PQI)":
                    for p in projs:
                        if p['titulo'] == projeto_vinculo:
                            p.setdefault('lembretes', []).append({"id": datetime.now().timestamp(), "data_hora": data_final, "texto": txt_lembrete})
                            db.salvar_projetos(projs)
                else:
                    diario.append({"id": datetime.now().timestamp(), "data_reg": datetime.now().strftime("%d/%m/%Y %H:%M"), "solicitacao": txt_lembrete, "depto": "GERAL", "detalhes": "Criado via Atalho Home", "lembrete": data_final, "status": "Pendente", "obs_final": ""})
                    db.salvar_diario(diario)
                st.success("Lembrete Gerado!"); st.rerun()

def exibir_central():
    st.title("⚙️ Painel de Governança")
    
    # 1. DEFINIÇÃO DINÂMICA DO MENU POR PERFIL
    if user_role == "ADM":
        opcoes_central = ["🔴 MONITOR ONLINE", "📊 BUSCA & DASHBOARD", "👥 Usuários", "🏢 Deptos", "⚙️ MOTIVOS"]
    elif user_role == "GERENTE":
        opcoes_central = ["🔴 MONITOR ONLINE", "📊 BUSCA & DASHBOARD"]
    else:
        st.error("Acesso restrito.")
        st.stop()

    menu = st.segmented_control("Menu:", opcoes_central, default="🔴 MONITOR ONLINE")
    logs = db.carregar_esforco()

    # --- ABA 1: MONITOR (ADM e GERENTE VEEM) ---
    if menu == "🔴 MONITOR ONLINE":
        st.subheader("Monitoramento em Tempo Real")
        ativos = [a for a in logs if a['status'] == 'Em andamento']
        if ativos:
            for atv in ativos:
                with st.container(border=True):
                    # Dividimos em 4 colunas agora para caber o botão de ação
                    c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
                    
                    c1.markdown(f"👤 **{atv['usuario']}**")
                    c2.markdown(f"📌 {atv['motivo']} <br><small>Obs: {atv['detalhes']}</small>", unsafe_allow_html=True)
                    
                    # Cálculo do tempo
                    inicio_atv = datetime.fromisoformat(atv['inicio'])
                    tempo_total = (datetime.now() - inicio_atv).seconds // 60
                    c3.metric("Tempo", f"{tempo_total} min")
                    
                    # BOTÃO DE FINALIZAÇÃO FORÇADA
                    # Criamos uma chave (key) única usando o nome do usuário para não dar erro no Streamlit
                    if c4.button("⏹️ Finalizar", key=f"force_stop_{atv['usuario']}", type="secondary", help="Encerra a atividade deste colaborador agora."):
                        finalizar_atividade_atual(atv['usuario'])
                        st.success(f"Atividade de {atv['usuario']} encerrada!")
                        st.rerun()
        else:
            st.info("Ninguém ativo no momento.")

    # --- ABA 2: DASHBOARD (ADM e GERENTE VEEM) ---
    elif menu == "📊 BUSCA & DASHBOARD":
        st.subheader("Filtro Geral de Atividades")
        df_logs = pd.DataFrame(logs)
        if not df_logs.empty:
            df_logs['inicio_dt'] = pd.to_datetime(df_logs['inicio'])
            with st.expander("🔍 Filtros de Busca", expanded=True):
                f_col1, f_col2, f_col3 = st.columns(3)
                periodo = f_col1.selectbox("Período", ["Hoje", "Últimos 7 dias", "Mês Atual", "Todo o Histórico"])
                f_user = f_col2.multiselect("Filtrar Usuário", options=sorted(df_logs['usuario'].unique()))
                f_motivo = f_col3.multiselect("Filtrar Atividade", options=sorted(df_logs['motivo'].unique()))

            hoje = datetime.now()
            if periodo == "Hoje": df_filtro = df_logs[df_logs['inicio_dt'].dt.date == hoje.date()]
            elif periodo == "Últimos 7 dias": df_filtro = df_logs[df_logs['inicio_dt'] >= (hoje - timedelta(days=7))]
            elif periodo == "Mês Atual": df_filtro = df_logs[df_logs['inicio_dt'].dt.month == hoje.month]
            else: df_filtro = df_logs.copy()

            if f_user: df_filtro = df_filtro[df_filtro['usuario'].isin(f_user)]
            if f_motivo: df_filtro = df_filtro[df_filtro['motivo'].isin(f_motivo)]

            if not df_filtro.empty:
                c1, c2 = st.columns([2, 1])
                with c1:
                    fig_user = px.bar(df_filtro.groupby('usuario')['duracao_min'].sum().reset_index(), x='usuario', y='duracao_min', color='usuario', text_auto=True)
                    st.plotly_chart(fig_user, use_container_width=True)
                with c2:
                    fig_pie = px.pie(df_filtro, names='motivo', values='duracao_min', hole=.4)
                    st.plotly_chart(fig_pie, use_container_width=True)
                st.dataframe(df_filtro.sort_values(by='inicio', ascending=False), use_container_width=True)

    # --- ABA 3: MOTIVOS (APENAS ADM) ---
    elif menu == "⚙️ MOTIVOS" and is_adm:
        st.subheader("Gerenciar Motivos")
        motivos = db.carregar_motivos()
        novo = st.text_input("Novo Motivo")
        if st.button("Adicionar"):
            motivos.append(novo); db.salvar_motivos(motivos); st.rerun()
        for m in motivos:
            col_m1, col_m2 = st.columns([4, 1])
            col_m1.write(m)
            if col_m2.button("🗑️", key=f"del_m_{m}"):
                motivos.remove(m); db.salvar_motivos(motivos); st.rerun()

    # --- ABA 4: USUÁRIOS (APENAS ADM) ---
    elif menu == "👥 Usuários" and is_adm:
        # 1. FORMULÁRIO PARA CRIAR NOVO USUÁRIO
        with st.expander("➕ Cadastrar Novo Colaborador", expanded=False):
            with st.form("form_novo_usuario"):
                c1, c2 = st.columns(2)
                novo_id = c1.text_input("ID de Acesso (Login)", placeholder="ex: joao.silva").lower().strip()
                novo_nome = c1.text_input("Nome Completo")
                nova_senha = c2.text_input("Senha Inicial", type="password")
                novo_depto = c2.selectbox("Vincular ao Departamento", departamentos)
                nova_alcada = st.selectbox("Nível de Alçada", ["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"])
                
                st.write("Módulos Permitidos:")
                cols_m = st.columns(3)
                mods_selecionados = []
                for i, (nome_pt, id_ref) in enumerate(MAPA_MODULOS_MESTRE.items()):
                    if cols_m[i % 3].checkbox(nome_pt, key=f"new_mod_{id_ref}"):
                        mods_selecionados.append(id_ref)
                
                if st.form_submit_button("CRIAR USUÁRIO", use_container_width=True):
                    if novo_id and novo_nome and nova_senha:
                        if novo_id not in usuarios:
                            dados_novo = {
                                "nome": novo_nome,
                                "senha": nova_senha,
                                "depto": novo_depto,
                                "role": nova_alcada,
                                "modulos": mods_selecionados,
                                "foto": None
                            }
                            db.salvar_usuario(novo_id, dados_novo)
                            st.success(f"Usuário {novo_nome} cadastrado com sucesso!")
                            st.rerun()
                        else:
                            st.error("Este ID de usuário já existe no sistema.")
                    else:
                        st.warning("Por favor, preencha Login, Nome e Senha.")

        st.divider()

        # 2. LISTAGEM DOS USUÁRIOS EXISTENTES
        tabs_d = st.tabs(departamentos)
        for idx, d_nome in enumerate(departamentos):
            with tabs_d[idx]:
                u_dept = {uid: info for uid, info in usuarios.items() if info.get('depto') == d_nome}
                if not u_dept:
                    st.info(f"Nenhum colaborador cadastrado no setor {d_nome}")
                
                for uid, info in u_dept.items():
                    with st.container(border=True):
                        col_f, col_t, col_b = st.columns([1, 4, 2])
                        f_u = info.get('foto') or "https://cdn-icons-png.flaticon.com/512/149/149071.png"
                        col_f.markdown(f'<img src="{f_u}" style="width:45px; height:45px; border-radius:50%; object-fit:cover;">', unsafe_allow_html=True)
                        col_t.markdown(f"**{info['nome']}** (`{uid}`)<br><small>Alçada: {info.get('role', 'OPERACIONAL')}</small>", unsafe_allow_html=True)
                        
                        c_ed, c_de = col_b.columns(2)
                        if c_ed.button("✏️", key=f"e_{uid}"): 
                            st.session_state.edit_id = uid
                            st.rerun()
                        if c_de.button("🗑️", key=f"d_{uid}"): 
                            db.deletar_usuario(uid)
                            st.rerun()

    # --- ABA 5: DEPTOS (APENAS ADM) ---
    elif menu == "🏢 Deptos" and is_adm:
        c_a, c_r = st.columns(2)
        with c_a:
            nd = st.text_input("Nome Depto").upper()
            if st.button("Adicionar Setor"):
                departamentos.append(nd); db.salvar_departamentos(departamentos); st.rerun()
        with c_r:
            rd = st.selectbox("Escolha", [""] + departamentos)
            if st.button("🗑️ Deletar Setor"):
                departamentos.remove(rd); db.salvar_departamentos(departamentos); st.rerun()

# =========================================================
# 5. ROTEAMENTO
# =========================================================
if escolha == "🏠 Home":
    exibir_home()
elif "Manutenção" in escolha:
    import mod_manutencao
    mod_manutencao.main()
elif "Processos" in escolha:
    import mod_processos
    mod_processos.exibir(user_role=user_role)
elif "RH Docs" in escolha:
    import mod_cartas
    mod_cartas.exibir(user_role=user_role)
elif "Operação" in escolha:
    import mod_operacao
    mod_operacao.exibir_operacao_completa(user_role=user_role)
elif "Minha Spin" in escolha:
    import mod_spin
    mod_spin.exibir_tamagotchi(user_info)
elif escolha == "🚌 Passagens":
    import passagens
    passagens.exibir_modulo_passagens()
elif "Central de Comando" in escolha:
    exibir_central()

# Edição ADM
if "edit_id" in st.session_state and escolha == "⚙️ Central de Comando":
    eid = st.session_state.edit_id
    einfo = usuarios[eid]
    st.divider()
    st.subheader(f"Editando: {einfo['nome']}")
    with st.container(border=True):
        c_edit1, c_edit2 = st.columns(2)
        enome = c_edit1.text_input("Nome", einfo['nome'])
        erole = c_edit1.selectbox("Alçada", ["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"], index=["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"].index(einfo.get('role', 'OPERACIONAL')))
        edept = c_edit2.selectbox("Depto", departamentos, index=departamentos.index(einfo['depto']) if einfo['depto'] in departamentos else 0)
        esenha = c_edit2.text_input("Resetar Senha", type="password")
        acessos_atuais = einfo.get('modulos', [])
        novos_mods = []
        cols_chk = st.columns(3)
        for idx_m, (nome_exibicao, id_interno) in enumerate(MAPA_MODULOS_MESTRE.items()):
            if cols_chk[idx_m % 3].checkbox(nome_exibicao, value=(id_interno in acessos_atuais), key=f"chk_{id_interno}_{eid}"):
                novos_mods.append(id_interno)
        if st.button("Salvar Alterações"):
            dados_update = {"nome": enome, "role": erole, "depto": edept, "modulos": novos_mods}
            if esenha: dados_update["senha"] = esenha
            db.salvar_usuario(eid, dados_update)
            del st.session_state.edit_id
            st.rerun()
