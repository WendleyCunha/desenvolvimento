import streamlit as st

# 1. Configuração da Página para ocupar a tela toda
st.set_page_config(layout="wide", page_title="Teste Multi-Painel")

# --- DEFINIÇÃO DAS PÁGINAS (FUNÇÕES) ---

def render_home():
    st.subheader("🏠 Home - Visão Geral")
    st.info("Aqui ficaria o seu resumo de atividades e boas-vindas.")
    st.metric(label="Tarefas Pendentes", value=12, delta=-2)
    st.bar_chart({"Esforço": [10, 20, 15, 30, 25]})

def render_central_comando():
    st.subheader("🎮 Central de Comando")
    st.warning("Monitoramento de Operação em Tempo Real")
    # Simulação de um gráfico de fluxo
    st.area_chart({"Fluxo": [1, 5, 2, 6, 3, 7, 4]})

def render_rh_docs():
    st.subheader("📄 RH Docs")
    st.write("Gestão de Documentação e Painel Administrativo.")
    st.table({
        "Documento": ["Contrato_01.pdf", "Ferias_Wendley.pdf"],
        "Status": ["Assinado", "Pendente"]
    })

# --- SIDEBAR DE NAVEGAÇÃO ---

with st.sidebar:
    st.title("Sistema de Gestão")
    st.write(f"Usuário: **Wendley Cunha**")
    
    # O Pulo do Gato: Checkbox para ativar o modo dividido
    multi_view = st.toggle("📂 Ativar Modo Multi-Painel")
    
    st.divider()
    
    if not multi_view:
        # Navegação normal se o modo multi-painel estiver desligado
        page = st.radio("Ir para:", ["Home", "Central de Comando", "RH Docs"])
    else:
        st.write("**Modo Multi-Painel Ativo**")
        st.caption("A Home ficará fixa na esquerda.")
        segunda_janela = st.selectbox("Escolha o painel da direita:", ["Central de Comando", "RH Docs"])

# --- LÓGICA DE EXIBIÇÃO ---

if not multi_view:
    # Renderização Padrão (Uma por vez)
    if page == "Home":
        render_home()
    elif page == "Central de Comando":
        render_central_comando()
    else:
        render_rh_docs()
else:
    # Renderização em Colunas (Lado a Lado)
    col_esquerda, col_direita = st.columns(2)
    
    with col_esquerda:
        render_home()
        
    with col_direita:
        if segunda_janela == "Central de Comando":
            render_central_comando()
        else:
            render_rh_docs()
