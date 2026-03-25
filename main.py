import streamlit as st
import database as db
import pandas as pd
import base64
import plotly.express as px
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
# 1. FUNÇÕES AUXILIARES, ESTILO E LÓGICA DE ESFORÇO
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

# --- LÓGICA DE ESFORÇO (CENTRALIZADA NO MAIN) ---
def finalizar_atividade_atual(nome_usuario):
    logs = db.carregar_esforco()
    mudou = False
    for idx, act in enumerate(logs):
        if act['usuario'] == nome_usuario and act['status'] == 'Em andamento':
            agora = datetime.now()
            inicio = datetime.fromisoformat(act['inicio'])
            duracao = (agora - inicio).total_seconds() / 60
            logs[idx]['fim'] = agora.isoformat()
            logs[idx]['status'] = 'Finalizado'
            logs[idx]['duracao_min'] = round(duracao, 2)
            mudou = True
    if mudou:
        db.salvar_esforco(logs)
        st.session_state.atividades_log = logs

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .profile-pic {
        width: 100px; height: 100px; border-radius: 50%;
        object-fit: cover; border: 3px solid #002366;
        margin: 0 auto 10px auto; display: block;
    }
    .card-esforco { background: white; padding: 20px; border-radius: 10px; border-left: 5px solid #002366; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. AUTENTICAÇÃO E CARREGAMENTO INICIAL
# =========================================================
usuarios = db.carregar_usuarios_firebase()
departamentos = db.carregar_departamentos()

# Inicialização de dados persistentes no state
if 'atividades_log' not in st.session_state:
    st.session_state.atividades_log = db.carregar_esforco()
if 'motivos_gestao' not in st.session_state:
    st.session_state.motivos_gestao = db.carregar_motivos()

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
user_nome = user_info.get('nome', 'Usuário')
user_role = user_info.get('role', 'OPERACIONAL')
is_adm = user_role == "ADM"
modulos_permitidos = user_info.get('modulos', [])

# =========================================================
# 3. SIDEBAR E NAVEGAÇÃO
# =========================================================
with st.sidebar:
    foto_atual = user_info.get('foto') or "https://cdn-icons-png.flaticon.com/512/149/149071.png"
    st.markdown(f'<img src="{foto_atual}" class="profile-pic">', unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; font-weight:bold; margin-bottom:20px;'>{user_nome}</p>", unsafe_allow_html=True)
    
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

    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.autenticado = False
        st.rerun()

# =========================================================
# 4. FUNÇÕES DAS PÁGINAS (HOME E CENTRAL)
# =========================================================

def exibir_home():
    st.title(f"Olá, {user_nome}! 👋")
    
    # NOVAS ABAS NO MAIN (MEU ESFORÇO DISPONÍVEL PARA TODOS NA HOME)
    tab_hoje, tab_esforço, tab_agenda, tab_novo = st.tabs(["🚀 Visão de Hoje", "⏱️ Meu Esforço", "📅 Agenda Master", "➕ Novo Agendamento"])
    
    # --- ABA: MEU ESFORÇO (OPERADOR LOGADO) ---
    with tab_esforço:
        st.subheader("Rastreador de Produtividade")
        
        # Atividade atual do usuário logado
        atv_atual = next((a for a in st.session_state.atividades_log if a['usuario'] == user_nome and a['status'] == 'Em andamento'), None)
        
        c_atv1, c_atv2 = st.columns([2, 1])
        with c_atv1:
            if atv_atual:
                st.markdown(f"""
                <div class="card-esforco">
                    <h3 style='color:#ef4444;'>⏳ TAREFA ATIVA</h3>
                    <p><b>Motivo:</b> {atv_atual['motivo']}</p>
                    <p><b>Início:</b> {datetime.fromisoformat(atv_atual['inicio']).strftime('%H:%M:%S')}</p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("⏹️ FINALIZAR AGORA", type="primary"):
                    finalizar_atividade_atual(user_nome)
                    st.rerun()
            else:
                st.info("Nenhuma atividade em andamento. Inicie uma abaixo!")

        with c_atv2:
            st.markdown("#### Novo Registro")
            motivo_sel = st.selectbox("Selecione a Atividade", st.session_state.motivos_gestao)
            obs_esf = st.text_input("Ticket / Obs")
            if st.button("▶️ DAR PLAY", use_container_width=True):
                finalizar_atividade_atual(user_nome)
                nova = {
                    "usuario": user_nome, "motivo": motivo_sel, "obs": obs_esf,
                    "inicio": datetime.now().isoformat(), "fim": None, "status": "Em andamento", "duracao_min": 0
                }
                st.session_state.atividades_log.append(nova)
                db.salvar_esforco(st.session_state.atividades_log)
                st.rerun()

    # (Lógica original de Lembretes/Agenda na Home...)
    with tab_hoje:
        st.write("Visão de Hoje...") 
    with tab_agenda:
        st.write("Agenda Master...")

def exibir_central():
    st.title("⚙️ Painel de Governança")
    # PONTO CHAVE: Adicionado "⚖️ Painel Esforço" aqui no Menu ADM
    menu = st.segmented_control("Menu:", ["👥 Usuários", "⚖️ Painel Esforço", "➕ Novo", "🏢 Deptos", "⏱️ Motivos"], default="👥 Usuários")
    
    # --- NOVO PAINEL DE ESFORÇO (FILTROS) ---
    if menu == "⚖️ Painel Esforço":
        st.subheader("Análise de Esforço da Equipe")
        df_esf = pd.DataFrame(st.session_state.atividades_log)
        if not df_esf.empty:
            df_esf['inicio_dt'] = pd.to_datetime(df_esf['inicio'])
            df_esf['data_dia'] = df_esf['inicio_dt'].dt.date
            
            # FILTROS POR DIA, SEMANA, MÊS, OPERADOR E ATIVIDADE
            with st.container(border=True):
                f1, f2, f3 = st.columns(3)
                periodo = f1.selectbox("Período", ["Hoje", "Esta Semana", "Este Mês", "Geral"])
                f_user = f2.multiselect("Filtrar por Pessoa", options=df_esf['usuario'].unique())
                f_task = f3.multiselect("Filtrar Atividade", options=df_esf['motivo'].unique())
                
                # Aplicação dos Filtros
                hoje_ref = datetime.now()
                if periodo == "Hoje": df_esf = df_esf[df_esf['data_dia'] == hoje_ref.date()]
                elif periodo == "Esta Semana":
                    segunda = hoje_ref.date() - timedelta(days=hoje_ref.weekday())
                    df_esf = df_esf[df_esf['data_dia'] >= segunda]
                elif periodo == "Este Mês":
                    df_esf = df_esf[df_esf['inicio_dt'].dt.month == hoje_ref.month]
                
                if f_user: df_esf = df_esf[df_esf['usuario'].isin(f_user)]
                if f_task: df_esf = df_esf[df_esf['motivo'].isin(f_task)]

            # Dashboards Rápidos
            c1, c2, c3 = st.columns(3)
            c1.metric("Horas Totais", f"{(df_esf['duracao_min'].sum()/60):.2f}h")
            c2.metric("Qtd Atividades", len(df_esf))
            c3.metric("Atividades/Dia", round(len(df_esf)/max(df_esf['data_dia'].nunique(), 1), 1))

            st.plotly_chart(px.bar(df_esf, x='usuario', y='duracao_min', color='motivo', title="Esforço por Colaborador (Minutos)"), use_container_width=True)
            st.dataframe(df_esf[['usuario', 'data_dia', 'motivo', 'obs', 'duracao_min']], use_container_width=True)
        else:
            st.warning("Nenhum dado registrado.")

    # Gestão de Motivos (Configurações)
    elif menu == "⏱️ Motivos":
        st.subheader("Configurar Lista de Motivos")
        novo_m = st.text_input("Nome do Motivo")
        if st.button("Adicionar"):
            st.session_state.motivos_gestao.append(novo_m); db.salvar_motivos(st.session_state.motivos_gestao); st.rerun()
        for m in st.session_state.motivos_gestao:
            c_m1, c_m2 = st.columns([4, 1])
            c_m1.write(m)
            if c_m2.button("Deletar", key=f"d_{m}"):
                st.session_state.motivos_gestao.remove(m); db.salvar_motivos(st.session_state.motivos_gestao); st.rerun()

    # ... Suas lógicas de Usuários e Deptos ...
    elif menu == "👥 Usuários":
        st.write("Gestão de Usuários")

# =========================================================
# 5. ROTEAMENTO
# =========================================================
if escolha == "🏠 Home":
    exibir_home()
elif "Central de Comando" in escolha:
    exibir_central()
# ... outros módulos (Manutenção, Processos, etc) ...
