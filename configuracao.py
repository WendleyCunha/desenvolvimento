import streamlit as st
from streamlit_option_menu import option_menu
from datetime import datetime, timedelta
import pandas as pd

# --- SEU CÓDIGO ORIGINAL (INTEGRIDADE MANTIDA) ---

COLOR_BG = "#FFFFFF"           # Branco (Fundo principal)
COLOR_SIDEBAR = "#1A1C22"      # Grafite (Sidebar)
COLOR_GOLD = "#B8860B"         # Dourado
COLOR_TEXT = "#2D2E33"         # Cinza escuro (Texto)

CSS_ESTAVEL = f"""
<style>
    .stApp {{
        background-color: {COLOR_BG} !important;
        color: {COLOR_TEXT} !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {COLOR_SIDEBAR} !important;
    }}
    h1, h2, h3, p, span, label {{
        color: {COLOR_TEXT} !important;
    }}
    .profile-pic {{
        width: 100px; height: 100px; border-radius: 50%;
        object-fit: cover; border: 3px solid {COLOR_GOLD};
        margin: 0 auto 10px auto; display: block;
    }}
    .sb-nome {{ color: white !important; text-align: center; font-weight: 600; margin-bottom: 0; }}
    .sb-cargo {{ color: {COLOR_GOLD} !important; text-align: center; font-size: 0.8rem; margin-top: 0; font-weight: bold; }}
    .stAlert {{
        background-color: #F8F9FA !important;
        border: 1px solid #E9ECEF !important;
        color: {COLOR_TEXT} !important;
    }}
</style>
"""

MAPA_MODULOS_MESTRE = {
    "Manutenção": "manutencao", "Processos": "processos",
    "RH Docs": "rh", "Operação": "operacao",
    "Minha Spin": "spin", "Cartas": "cartas"
}

def configurar_pagina():
    st.set_page_config(page_title="Hub King Star", layout="wide", page_icon="👑")
    st.markdown(CSS_ESTAVEL, unsafe_allow_html=True)

def desenhar_sidebar(user_info, menu_options):
    mapa_icones = {
        "Home": "house",
        "Manutenção": "tools",
        "Processos": "diagram-3",
        "RH Docs": "file-text",
        "Operação": "box",
        "Minha Spin": "car",
        "Cartas": "envelope",
        "Central de Comando": "shield-lock"
    }
    icones_dinamicos = [mapa_icones.get(opt, "circle") for opt in menu_options]

    with st.sidebar:
        foto = user_info.get('foto') or 'https://www.w3schools.com/howto/img_avatar.png'
        st.markdown(f'<img src="{foto}" class="profile-pic">', unsafe_allow_html=True)
        st.markdown(f'<p class="sb-nome">{user_info.get("nome", "Usuário")}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="sb-cargo">{user_info.get("cargo", "Analista")}</p>', unsafe_allow_html=True)
        st.divider()
        escolha = option_menu(
            menu_title=None, 
            options=menu_options,
            icons=icones_dinamicos, 
            styles={
                "container": {"background-color": "transparent"},
                "nav-link": {"color": "#CCC", "font-size": "14px", "text-align": "left"},
                "nav-link-selected": {"background-color": COLOR_GOLD, "color": "white"}
            }
        )
        if st.button("Sair do Sistema"):
            st.session_state.autenticado = False
            st.rerun()
    return escolha

# --- LÓGICA DE DADOS E MONITORIA (NOVO) ---

def gerenciar_atividades():
    if 'atividades' not in st.session_state:
        # Mock de dados inicial
        st.session_state.atividades = [
            {"id": 1, "agente": "Agente 01", "tarefa": "Análise de Processo", "data": datetime.now().date()},
            {"id": 2, "agente": "Agente 01", "tarefa": "Checklist Manutenção", "data": datetime.now().date()},
            {"id": 3, "agente": "Agente 02", "tarefa": "RH Conferência", "data": datetime.now().date() - timedelta(days=1)}
        ]

def tela_central_comando():
    st.title("🛡️ Central de Comando")
    
    # --- FILTRO POR DATA (Para o Dashboard e Monitoria) ---
    with st.expander("🔍 Filtros de Período", expanded=True):
        col_f1, col_f2 = st.columns([1, 2])
        periodo_selecionado = col_f1.selectbox(
            "Selecione o Período",
            ["Hoje", "Últimos 7 dias", "Mês anterior", "Personalizado"]
        )
        
        hoje = datetime.now().date()
        data_inicio, data_fim = hoje, hoje

        if periodo_selecionado == "Últimos 7 dias":
            data_inicio = hoje - timedelta(days=7)
        elif periodo_selecionado == "Mês anterior":
            data_fim = hoje.replace(day=1) - timedelta(days=1)
            data_inicio = data_fim.replace(day=1)
        elif periodo_selecionado == "Personalizado":
            datas = col_f2.date_input("Intervalo", [hoje, hoje])
            if len(datas) == 2:
                data_inicio, data_fim = datas

    aba1, aba2 = st.tabs(["📊 Monitoria", "📈 Dashboard"])

    # Filtragem dos dados
    df = pd.DataFrame(st.session_state.atividades)
    df['data'] = pd.to_datetime(df['data']).dt.date
    df_filtrado = df[(df['data'] >= data_inicio) & (df['data'] <= data_fim)]

    with aba1:
        st.subheader("Atividades em Andamento")
        if df_filtrado.empty:
            st.info("Nenhuma atividade encontrada para este período.")
        else:
            for idx, row in df_filtrado.iterrows():
                with st.container():
                    c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
                    c1.write(f"ID: {row['id']}")
                    c2.write(f"**Agente:** {row['agente']}")
                    c3.write(f"**Tarefa:** {row['tarefa']}")
                    
                    # 1. ENCERRA UMA POR VEZ (Usando a Key única pelo ID)
                    if c4.button("Encerrar", key=f"btn_encerrar_{row['id']}"):
                        st.session_state.atividades = [a for a in st.session_state.atividades if a['id'] != row['id']]
                        st.toast(f"Atividade {row['id']} encerrada!")
                        st.rerun()
                    st.divider()

    with aba2:
        st.subheader("Análise de Produtividade")
        if not df_filtrado.empty:
            c_m1, c_m2 = st.columns(2)
            c_m1.metric("Total de Atividades", len(df_filtrado))
            c_m2.metric("Agentes Ativos", df_filtrado['agente'].nunique())
            
            st.markdown("### Volume por Data")
            st.bar_chart(df_filtrado['data'].value_counts())
        else:
            st.warning("Sem dados para o dashboard no período selecionado.")

# --- EXECUÇÃO PRINCIPAL ---

def main():
    configurar_pagina()
    gerenciar_atividades()
    
    # Simulando informações do usuário logado
    u_info = {"nome": "Wendley Cunha", "cargo": "Analista Jr.", "foto": None}
    opcoes = ["Home", "Central de Comando", "Manutenção", "Processos"]
    
    escolha = desenhar_sidebar(u_info, opcoes)
    
    if escolha == "Central de Comando":
        tela_central_comando()
    else:
        st.title(f"Módulo {escolha}")
        st.write("Conteúdo do módulo em desenvolvimento.")

if __name__ == "__main__":
    main()
