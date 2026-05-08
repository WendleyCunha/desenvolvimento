import streamlit as st

# 1. Configuração da Página para aproveitar o máximo de espaço
st.set_page_config(layout="wide", page_title="King Star - Quad View Test")

# --- FUNÇÕES DE RENDERIZAÇÃO COM ABAS INTERNAS ---

def render_modulo(nome, cor):
    st.markdown(f"### {nome}")
    # Abas internas para simular seus códigos reais
    tab1, tab2, tab3 = st.tabs(["📊 Dash", "⚙️ Opções", "📝 Docs"])
    
    with tab1:
        st.write(f"Monitoramento do {nome}")
        st.area_chart([10, 25, 15, cor, 20])
        
    with tab2:
        st.selectbox(f"Selecione o filtro ({nome})", ["Geral", "Por Setor", "Por Analista"], key=f"sel_{nome}")
        st.checkbox("Atualização Automática", key=f"check_{nome}")
        
    with tab3:
        st.info(f"Instruções e logs do módulo {nome}.")

# --- SIDEBAR E CONFIGURAÇÃO DO GRID ---

with st.sidebar:
    st.title("🚀 Central de Comando")
    st.write("Usuário: **Wendley Cunha**")
    
    st.divider()
    
    st.subheader("Configuração do Layout")
    num_paineis = st.slider("Quantidade de painéis simultâneos:", 1, 4, 2)
    
    st.divider()
    
    # Seleção dinâmica dos módulos para cada "slot"
    opcoes_modulos = ["Home", "Central de Comando", "RH Docs", "Manutenção", "Processos", "Operação"]
    
    escolhidos = []
    for i in range(num_paineis):
        escolha = st.selectbox(f"Painel {i+1}:", opcoes_modulos, index=i % len(opcoes_modulos), key=f"p{i}")
        escolhidos.append(escolha)

# --- LÓGICA DE GRID DINÂMICO ---

# Definindo cores fictícias para os gráficos dos painéis
cores = [40, 10, 80, 50]

if num_paineis == 1:
    render_modulo(escolhidos[0], cores[0])

elif num_paineis == 2:
    col1, col2 = st.columns(2)
    with col1: render_modulo(escolhidos[0], cores[0])
    with col2: render_modulo(escolhidos[1], cores[1])

elif num_paineis == 3:
    col1, col2 = st.columns(2)
    with col1: render_modulo(escolhidos[0], cores[0])
    with col2: render_modulo(escolhidos[1], cores[1])
    st.divider()
    col3, _ = st.columns(2) # Terceiro painel na linha de baixo
    with col3: render_modulo(escolhidos[2], cores[2])

else: # 4 Painéis (Grid 2x2)
    col1, col2 = st.columns(2)
    with col1: render_modulo(escolhidos[0], cores[0])
    with col2: render_modulo(escolhidos[1], cores[1])
    
    st.divider()
    
    col3, col4 = st.columns(2)
    with col3: render_modulo(escolhidos[2], cores[2])
    with col4: render_modulo(escolhidos[3], cores[3])
