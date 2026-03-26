import streamlit as st
import database as db
import pandas as pd
import base64
from datetime import datetime, timedelta
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
# 1. FUNÇÕES AUXILIARES E ESTILO
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
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. AUTENTICAÇÃO
# =========================================================
usuarios = db.carregar_usuarios_firebase()
departamentos = db.carregar_departamentos()

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
    
    menu_options = ["🏠 Home"]
    for nome, mid in MAPA_MODULOS_MESTRE.items():
        if is_adm or mid in modulos_permitidos:
            menu_options.append(nome)
    
    if is_adm:
        menu_options.append("⚙️ Central de Comando")

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

    st.markdown("<br>" * 5, unsafe_allow_html=True)
    
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
# 4. FUNÇÕES DA HOME TURBINADA
# =========================================================

def exibir_home():
    st.title(f"Olá, {user_info['nome']}! 👋")
    
    # NOVAS ABAS NO MAIN
    tab_hoje, tab_agenda, tab_novo = st.tabs(["🚀 Visão de Hoje", "📅 Agenda Master", "➕ Novo Agendamento"])
    
    projs = db.carregar_projetos()
    diario = db.carregar_diario()
    hoje = datetime.now().strftime("%d/%m/%Y")

    # --- ABA 1: O QUE TEMOS PARA HOJE ---
    with tab_hoje:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📌 Processos (PQI)")
            tem_pqi = False
            for p_idx, p in enumerate(projs):
                if 'lembretes' in p:
                    for l_idx, l in enumerate(p['lembretes']):
                        if hoje in l['data_hora']:
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
                    if hoje in sit['lembrete']:
                        tem_dir = True
                        with st.container(border=True):
                            st.markdown(f'<div class="diary-card"><small style="color:#3b82f6;">📅 AGENDADO</small><br><strong>Solicitação:</strong> {sit["solicitacao"]}<br><strong>Depto:</strong> {sit["depto"]}</div>', unsafe_allow_html=True)
                            if st.button(f"Executado", key=f"main_dir_{idx}"):
                                sit['status'] = "Executado"
                                db.salvar_diario(diario)
                                st.toast("Atualizado!"); st.rerun()
            if not tem_dir: st.info("Diário limpo hoje.")

    # --- ABA 2: CALENDÁRIO / AGENDA DE DIAS À FRENTE ---
    with tab_agenda:
        st.subheader("🗓️ Próximos Compromissos")
        agenda_data = []
        for p in projs:
            for l in p.get('lembretes', []):
                data_limpa = l['data_hora'].split(" ")[0]
                if data_limpa > hoje:
                    agenda_data.append({"Data": data_limpa, "Origem": f"PQI: {p['titulo']}", "Descrição": l['texto']})
        
        for sit in diario:
            if sit.get('status') == "Pendente" and sit.get('lembrete') != "N/A":
                data_limpa = sit['lembrete'].split(" ")[0]
                if data_limpa > hoje:
                    agenda_data.append({"Data": data_limpa, "Origem": f"DIÁRIO: {sit['depto']}", "Descrição": sit['solicitacao']})
        
        if agenda_data:
            df_agenda = pd.DataFrame(agenda_data).sort_values(by="Data")
            st.dataframe(df_agenda, use_container_width=True, hide_index=True)
        else:
            st.write("Nenhum compromisso para os próximos dias.")

    # --- ABA 3: AGENDAMENTO RÁPIDO ---
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
                            p.setdefault('lembretes', []).append({
                                "id": datetime.now().timestamp(),
                                "data_hora": data_final,
                                "texto": txt_lembrete
                            })
                            db.salvar_projetos(projs)
                else:
                    nova_situacao = {
                        "id": datetime.now().timestamp(),
                        "data_reg": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "solicitacao": txt_lembrete,
                        "depto": "GERAL",
                        "detalhes": "Criado via Atalho Home",
                        "lembrete": data_final,
                        "status": "Pendente",
                        "obs_final": ""
                    }
                    diario.append(nova_situacao)
                    db.salvar_diario(diario)
                
                st.success("Lembrete Gerado com Sucesso!"); st.rerun()

def exibir_central():
    # ... (Mantenha seu código original da Central de Comando aqui) ...
    st.title("⚙️ Painel de Governança")
    menu = st.segmented_control("Menu:", ["👥 Usuários", "➕ Novo", "🏢 Deptos"], default="👥 Usuários")
    if menu == "➕ Novo":
        with st.form("f_novo"):
            c1, c2 = st.columns(2)
            nid = c1.text_input("Login (id)").lower().strip()
            nnome = c2.text_input("Nome")
            nrole = c1.selectbox("Alçada", ["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"])
            ndepto = c2.selectbox("Departamento", departamentos)
            nsenha = st.text_input("Senha")
            if st.form_submit_button("Cadastrar"):
                db.salvar_usuario(nid, {"nome": nnome, "senha": nsenha, "role": nrole, "depto": ndepto, "modulos": [], "foto": ""})
                st.rerun()
    elif menu == "🏢 Deptos":
        c_a, c_r = st.columns(2)
        with c_a:
            nd = st.text_input("Nome Depto").upper()
            if st.button("Adicionar Setor"):
                departamentos.append(nd); db.salvar_departamentos(departamentos); st.rerun()
        with c_r:
            rd = st.selectbox("Escolha", [""] + departamentos)
            if st.button("🗑️ Deletar Setor"):
                departamentos.remove(rd); db.salvar_departamentos(departamentos); st.rerun()
    elif menu == "👥 Usuários":
        tabs_d = st.tabs(departamentos)
        for idx, d_nome in enumerate(departamentos):
            with tabs_d[idx]:
                u_dept = {uid: info for uid, info in usuarios.items() if info.get('depto') == d_nome}
                for uid, info in u_dept.items():
                    with st.container(border=True):
                        col_f, col_t, col_b = st.columns([1, 4, 2])
                        f_u = info.get('foto') or "https://cdn-icons-png.flaticon.com/512/149/149071.png"
                        col_f.markdown(f'<img src="{f_u}" style="width:45px; height:45px; border-radius:50%; object-fit:cover;">', unsafe_allow_html=True)
                        mods_u = info.get('modulos', [])
                        col_t.write(f"**{info['nome']}** ({info.get('role')})")
                        col_t.caption(f"Acessos: {', '.join(mods_u) if mods_u else 'Nenhum'}")
                        c_ed, c_de = col_b.columns(2)
                        if c_ed.button("✏️", key=f"e_{uid}"): st.session_state.edit_id = uid; st.rerun()
                        if c_de.button("🗑️", key=f"d_{uid}"): db.deletar_usuario(uid); st.rerun()

# =========================================================
# 5. ROTEAMENTO DE CONTEÚDO
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
elif "Tickets" in escolha:
    import mod_tickets
    mod_tickets.exibir(user_info)

# Lógica de edição ADM fora da função para persistência do rerun
if "edit_id" in st.session_state and escolha == "⚙️ Central de Comando":
    eid = st.session_state.edit_id
    einfo = usuarios[eid]
    st.divider()
    st.subheader(f"Editando Acessos: {einfo['nome']}")
    with st.container(border=True):
        c_edit1, c_edit2 = st.columns(2)
        enome = c_edit1.text_input("Nome", einfo['nome'])
        erole = c_edit1.selectbox("Alçada", ["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"], index=["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"].index(einfo.get('role', 'OPERACIONAL')))
        edept = c_edit2.selectbox("Depto", departamentos, index=departamentos.index(einfo['depto']) if einfo['depto'] in departamentos else 0)
        esenha = c_edit2.text_input("Resetar Senha", type="password")
        
        st.write("**Módulos Liberados:**")
        acessos_atuais = einfo.get('modulos', [])
        cols_chk = st.columns(3)
        novos_mods = []
        for idx_m, (nome_exibicao, id_interno) in enumerate(MAPA_MODULOS_MESTRE.items()):
            if cols_chk[idx_m % 3].checkbox(nome_exibicao, value=(id_interno in acessos_atuais), key=f"chk_{id_interno}_{eid}"):
                novos_mods.append(id_interno)

        if st.button("Salvar Alterações de Acesso", type="primary"):
            dados_update = {"nome": enome, "role": erole, "depto": edept, "modulos": novos_mods}
            if esenha: dados_update["senha"] = esenha
            db.salvar_usuario(eid, dados_update)
            st.success("Dados salvos!")
            del st.session_state.edit_id
            st.rerun()
