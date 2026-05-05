import streamlit as st
import configuracao as config
from modulos import database as db
from views import home, login
from datetime import datetime

# --- 1. FUNÇÃO DE CACHE ---
# Otimizado: agora o cache limpa automaticamente se houver erro, evitando travar o app
@st.cache_data(ttl=600)
def obter_usuarios_cache():
    try:
        return db.carregar_usuarios_firebase()
    except Exception as e:
        st.error(f"Erro ao conectar com o banco de dados: {e}")
        return {}

# --- 2. CONFIGURAÇÃO INICIAL E ESTILO ---
config.configurar_pagina()

# CSS de Alta Prioridade - Mantida sua estilização Azul e Dourado
st.markdown("""
    <style>
        [data-testid="stSidebar"] {
            background-color: #4682B4 !important;
            background-image: linear-gradient(180deg, #4682B4 0%, #2c5270 100%) !important;
        }
        [data-testid="stSidebar"] > div:first-child,
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"],
        [data-testid="stSidebarNav"] {
            background-color: transparent !important;
        }
        [data-testid="stSidebar"] .stText, [data-testid="stSidebar"] label, 
        [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {
            color: #FFFFFF !important;
        }
        [data-testid="stSidebar"] svg { fill: #FFD700 !important; }
        
        [data-testid="stSidebarNavItems"] a {
            background-color: rgba(255, 255, 255, 0.05) !important;
            border-radius: 8px !important;
            margin: 4px 0px !important;
            border: 1px solid rgba(255, 215, 0, 0.1) !important;
            transition: all 0.3s ease;
        }
        [data-testid="stSidebarNavItems"] a[aria-current="page"] {
            background-color: #B8860B !important;
            color: #FFFFFF !important;
            border: 1px solid #FFD700 !important;
            font-weight: bold !important;
        }
        header[data-testid="stHeader"] { background-color: rgba(0,0,0,0) !important; }
    </style>
""", unsafe_allow_html=True)

# --- 3. INICIALIZAÇÃO DO SESSION STATE ---
# Centralizado para garantir que variáveis essenciais sempre existam
for key, default in {
    "autenticado": False, 
    "user_info": None, 
    "user_id": None,
    "pagina_atual": "Home"
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- 4. CARREGAMENTO DE USUÁRIOS ---
usuarios = obter_usuarios_cache()

# --- 5. LÓGICA DE LOGIN ---
if not st.session_state.autenticado:
    if not usuarios:
        st.error("Sistema offline. Verifique a conexão com Firebase.")
        st.stop()
    login.exibir_login(usuarios)
    st.stop() 

# --- 6. RECUPERAÇÃO SEGURA DO PERFIL ---
user_id = st.session_state.user_id
user_info = st.session_state.user_info

# Revalidação de segurança caso o cache expire ou mude
if not user_info and user_id in usuarios:
    user_info = usuarios.get(user_id)
    st.session_state.user_info = user_info

if not user_info:
    st.warning("⚠️ Perfil não identificado. Por favor, refaça o login.")
    if st.button("Sair"):
        st.session_state.autenticado = False
        st.rerun()
    st.stop()

# Definição de permissões
user_role = user_info.get('role', 'OPERACIONAL')
is_adm = (user_role == "ADM")
permissoes = user_info.get('modulos', [])

# --- 7. MONTAGEM DINÂMICA DO MENU ---
menu_options = ["Home"]
# Usa o MAPA_MODULOS_MESTRE definido no seu config.py
for label, id_modulo in getattr(config, 'MAPA_MODULOS_MESTRE', {}).items():
    if is_adm or id_modulo in permissoes:
        menu_options.append(label)

if is_adm: 
    menu_options.append("Central de Comando")

# Renderização da Sidebar e captura da escolha
escolha = config.desenhar_sidebar(user_info, menu_options)

# --- 8. ROTEADOR CENTRAL ---
# Encapsulado para capturar erros específicos de cada módulo
try:
    if escolha == "Home":
        home.exibir(user_info)
        
    elif "Manutenção" in escolha:
        from modulos import mod_manutencao
        mod_manutencao.main()
        
    elif "Minha Spin" in escolha:
        from modulos import mod_spin
        # Passando user_info para manter a personalização do SpinGenius
        mod_spin.exibir_tamagotchi(user_info)
        
    elif "RH Docs" in escolha or "Cartas" in escolha:
        from views import mod_cartas
        mod_cartas.exibir(user_role)
        
    elif "Processos" in escolha:
        from views import mod_processos
        mod_processos.exibir(user_role=user_role)
        
    elif "Central de Comando" in escolha:
        from views import central
        central.exibir(is_adm)

except Exception as e:
    st.error(f"Ocorreu um erro ao carregar o módulo: {escolha}")
    st.info("Tente atualizar a página ou contatar o administrador.")
    # Log interno para debug
    print(f"DEBUG: Erro no módulo {escolha}: {e}")
