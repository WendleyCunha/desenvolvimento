import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Configurações iniciais
st.set_page_config(page_title="SpinGenius - O Jênio da Spin 2013", layout="wide")

# --- DATABASE SIMULADO (Pode ser um CSV depois) ---
if 'km_atual' not in st.session_state:
    st.session_state.km_atual = 138000
if 'saude_carro' not in st.session_state:
    st.session_state.saude_carro = 85 # Começa em 85% por ser 2013

# --- SIDEBAR (Entrada de Dados) ---
st.sidebar.header("📟 Painel de Controle")
st.session_state.km_atual = st.sidebar.number_input("Quilometragem Atual", value=st.session_state.km_atual)
manutencao_cambio = st.sidebar.date_input("Última revisão do câmbio (estimada)", datetime.now() - timedelta(days=180))

# --- TÍTULO ---
st.title("🧞‍♂️ SpinGenius: Seu Tutor 1.8 Automático")
st.subheader(f"Status Atual: {st.session_state.km_atual} KM")

# --- DASHBOARD DE SAÚDE ---
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Saúde Geral", f"{st.session_state.saude_carro}%", delta="-2% (Óleo Vencendo)")
    st.progress(st.session_state.saude_carro / 100)

with col2:
    st.metric("Próxima Troca de Óleo", "143.000 KM")

with col3:
    st.metric("Status do Câmbio", "Estável", help="Baseado no reparo feito há 10k km")

# --- ABAS ---
tab1, tab2, tab3 = st.tabs(["🧞 Tutor (Jênio)", "📝 Plano de 10 Anos", "🧠 Quiz do Especialista"])

with tab1:
    st.header("O que o Jênio sugere hoje?")
    if st.session_state.km_atual >= 138000:
        st.warning("🚨 **ALERTA DO JÊNIO:** Como você acabou de pegar o carro, a primeira coisa é trocar o óleo (5W30 Sintético) e o filtro. Verifique as **Bieletas**!")
    
    pergunta = st.text_input("Pergunte algo ao Tutor (Ex: 'O carro está vibrando em D'): ")
    if "vibrando" in pergunta.lower():
        st.info("Jênio diz: Verifique o calço (coxim) do motor e do câmbio. Na Spin 2013, o coxim hidráulico costuma arriar com essa quilometragem.")

with tab2:
    st.header("🗓️ Cronograma Mestre (Próximos 10 anos)")
    cronograma = {
        "Frequência": ["Diário", "Semanal", "Mensal", "A cada 10k KM", "A cada 40k KM", "A cada 2 anos"],
        "Tarefa": ["Verificar poças de óleo no chão", "Nível do Arrefecimento (Água)", "Calibragem dos Pneus (32 PSI)", "Troca de Óleo e Filtros", "Correia Dentada e Esticador", "Troca do Fluido de Freio DOT4"],
        "Importância": ["Alta", "Crítica", "Média", "Crítica", "MÁXIMA", "Média"]
    }
    st.table(pd.DataFrame(cronograma))

with tab3:
    st.header("🕹️ Quiz: Você conhece sua Spin?")
    pergunta_quiz = st.radio("Qual a principal causa de superaquecimento na Spin 2013?", 
                             ["Falta de gasolina", "Válvula termostática travada ou reservatório trincado", "Pneu murcho"])
    if st.button("Verificar"):
        if "Válvula" in pergunta_quiz:
            st.success("Correto! O sistema de arrefecimento é o coração da vida desse motor.")
        else:
            st.error("Errou! Fique atento ao ponteiro de temperatura!")
