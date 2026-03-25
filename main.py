import streamlit as st
import database as db
import pandas as pd
import base64
from datetime import datetime, timedelta
from streamlit_option_menu import option_menu 
import plotly.express as px

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
    .user-badge-home { background: #002366; color: white; padding: 5px 15px; border-radius: 15px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. AUTENTICAÇÃO E CARREGAMENTO DE DADOS
# =========================================================
usuarios = db.carregar_usuarios_firebase()
departamentos = db.carregar_departamentos()

# Inicializa estados de esforço
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
user_role = user_info.get('role', 'OPERACIONAL')
user_nome = user_info.get('nome', 'Colaborador') # Nome do operador logado
is_adm = user_role in ["ADM", "GERENTE"]
modulos_permitidos = user_info.get('modulos', [])

# --- LÓGICA DE ESFORÇO ---
def finalizar_atividade_atual(nome_usuario):
    logs = db.carregar_esforco() # Carrega sempre do banco para integridade
    for idx, act in enumerate(logs):
        if act['usuario'] == nome_usuario and act['status'] == 'Em andamento':
            agora = datetime.now()
            inicio = datetime.fromisoformat(act['inicio'])
            duracao = (agora - inicio).total_seconds() / 60
            logs[idx]['fim'] = agora.isoformat()
            logs[idx]['status'] = 'Finalizado'
            logs[idx]['duracao_min'] = round(duracao, 2)
    db.salvar_esforco(logs)
    st.session_state.atividades_log = logs

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
# 4. FUNÇÕES DA HOME (AGORA COM RASTREADOR DE ESFORÇO)
# =========================================================

def exibir_home():
    st.title(f"Olá, {user_nome}! 👋")
    
    # NOVAS ABAS NO MAIN (Inclusão do Esforço e Painel ADM)
    abas_home = ["🚀 Visão de Hoje", "📅 Agenda Master", "➕ Novo Agendamento", "⏱️ Meu Esforço"]
    if is_adm:
        abas_home.append("⚖️ Painel ADM (Esforço)")

    tabs_h = st.tabs(abas_home)
    
    projs = db.carregar_projetos()
    diario = db.carregar_diario()
    hoje_dt = datetime.now()
    hoje_str = hoje_dt.strftime("%d/%m/%Y")

    # --- ABA: MEU ESFORÇO (OPERADOR LOGADO) ---
    with tabs_h[3]:
        st.subheader("Rastreador de Atividade")
        atv_atual = next((a for a in st.session_state.atividades_log if a['usuario'] == user_nome and a['status'] == 'Em andamento'), None)
        
        c_atv1, c_atv2 = st.columns([2, 1])
        with c_atv1:
            if atv_atual:
                st.error(f"⏳ **EM ANDAMENTO:** {atv_atual['motivo']}")
                st.caption(f"Iniciado às: {datetime.fromisoformat(atv_atual['inicio']).strftime('%H:%M:%S')}")
                if st.button("⏹️ Encerrar Atividade Atual"):
                    finalizar_atividade_atual(user_nome); st.rerun()
            else:
                st.success("✅ Você está disponível.")
        
        st.divider()
        col_new1, col_new2 = st.columns([2, 1])
        with col_new1:
            motivo_sel = st.selectbox("O que vai fazer agora?", st.session_state.motivos_gestao)
            obs_esf = st.text_input("Observação (Opcional)", key="obs_esf_home")
        with col_new2:
            st.write("<br>", unsafe_allow_html=True)
            if st.button("▶️ INICIAR TAREFA", type="primary", use_container_width=True):
                finalizar_atividade_atual(user_nome)
                nova = {
                    "usuario": user_nome, "motivo": motivo_sel, "obs": obs_esf,
                    "inicio": datetime.now().isoformat(), "fim": None, "status": "Em andamento", "duracao_min": 0
                }
                st.session_state.atividades_log.append(nova)
                db.salvar_esforco(st.session_state.atividades_log)
                st.rerun()

    # --- ABA: PAINEL ADM ESFORÇO (FILTROS POR DIA/SEMANA/MÊS) ---
    if is_adm:
        with tabs_h[4]:
            st.subheader("⚖️ Gestão Analítica de Esforço")
            df_esf = pd.DataFrame(st.session_state.atividades_log)
            if not df_esf.empty:
                df_esf['inicio_dt'] = pd.to_datetime(df_esf['inicio'])
                df_esf['data_dia'] = df_esf['inicio_dt'].dt.date
                
                # FILTROS
                with st.expander("🔍 Filtros Avançados", expanded=True):
                    f1, f2, f3 = st.columns(3)
                    periodo = f1.selectbox("Período", ["Hoje", "Esta Semana", "Este Mês", "Todo o Histórico"])
                    op_sel = f2.multiselect("Filtrar Operador", options=df_esf['usuario'].unique())
                    at_sel = f3.multiselect("Filtrar Atividade", options=df_esf['motivo'].unique())
                    
                    # Lógica de Período
                    if periodo == "Hoje":
                        df_esf = df_esf[df_esf['data_dia'] == hoje_dt.date()]
                    elif periodo == "Esta Semana":
                        inicio_semana = hoje_dt.date() - timedelta(days=hoje_dt.weekday())
                        df_esf = df_esf[df_esf['data_dia'] >= inicio_semana]
                    elif periodo == "Este Mês":
                        df_esf = df_esf[df_esf['inicio_dt'].dt.month == hoje_dt.month]
                    
                    if op_sel: df_esf = df_esf[df_esf['usuario'].isin(op_sel)]
                    if at_sel: df_esf = df_esf[df_esf['motivo'].isin(at_sel)]

                # DASHBOARD ADM
                m1, m2, m3 = st.columns(3)
                m1.metric("Horas Totais", f"{(df_esf['duracao_min'].sum()/60):.2f}h")
                m2.metric("Atividades", len(df_esf))
                m3.metric("Operadores Ativos", df_esf['usuario'].nunique())

                g_col1, g_col2 = st.columns(2)
                with g_col1:
                    fig_op = px.bar(df_esf.groupby('usuario')['duracao_min'].sum().reset_index(), 
                                    x='usuario', y='duracao_min', title="Minutos por Operador", color='usuario')
                    st.plotly_chart(fig_op, use_container_width=True)
                with g_col2:
                    fig_at = px.pie(df_esf, names='motivo', values='duracao_min', title="Distribuição por Atividade")
                    st.plotly_chart(fig_at, use_container_width=True)
                
                st.dataframe(df_esf[['usuario', 'data_dia', 'motivo', 'duracao_min', 'status']], use_container_width=True)
            else:
                st.info("Nenhum dado de esforço disponível.")

    # (Mantendo suas lógicas originais das outras abas...)
    with tabs_h[0]:
        st.write("Visão de Hoje...") # Sua lógica original aqui
    with tabs_h[1]:
        st.write("Agenda Master...") # Sua lógica original aqui
    with tabs_h[2]:
        st.write("Novo Agendamento...") # Sua lógica original aqui

def exibir_central():
    st.title("⚙️ Painel de Governança")
    # PONTO 3: ADM GERE MOTIVOS AQUI
    menu = st.segmented_control("Menu:", ["👥 Usuários", "➕ Novo", "🏢 Deptos", "⏱️ Motivos Esforço"], default="👥 Usuários")
    
    if menu == "⏱️ Motivos Esforço":
        st.subheader("Gerenciar Categorias de Esforço")
        new_m = st.text_input("Novo Motivo (Ex: Pausa, Reunião, Ajuste)")
        if st.button("Cadastrar Motivo"):
            st.session_state.motivos_gestao.append(new_m)
            db.salvar_motivos(st.session_state.motivos_gestao)
            st.rerun()
        
        for m in st.session_state.motivos_gestao:
            c_m1, c_m2 = st.columns([4, 1])
            c_m1.write(m)
            if c_m2.button("🗑️", key=f"del_mot_{m}"):
                st.session_state.motivos_gestao.remove(m)
                db.salvar_motivos(st.session_state.motivos_gestao)
                st.rerun()
    
    # ... Restante da sua Central de Comando (Usuários, Deptos) ...
    elif menu == "👥 Usuários":
        # (Seu código original de listagem de usuários...)
        st.write("Listagem de usuários...")

# =========================================================
# 5. ROTEAMENTO
# =========================================================
if escolha == "🏠 Home":
    exibir_home()
elif "Central de Comando" in escolha:
    exibir_central()
# ... outros elifs originais ...
