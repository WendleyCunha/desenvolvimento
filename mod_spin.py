import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

def exibir_tamagotchi(user_info):
    # --- 1. CONFIGURAÇÃO DE ESTADO ---
    if 'km_atual' not in st.session_state: 
        st.session_state.km_atual = 138000
    if 'historico' not in st.session_state: 
        st.session_state.historico = []

    # --- 2. ESTRUTURA DE DADOS ---
    CATEGORIAS = {
        "Manutenção Corretiva/Preventiva": [
            "Óleo do Motor (5W30)", "Correia Dentada", "Fluido de Câmbio (GF6)", 
            "Amortecedores", "Bandejas e Buchas", "Óleo de Direção Hidráulica", 
            "Fluido de Freio (DOT 4)", "Líquido Arrefecimento", "Velas e Cabos", "Pneus"
        ],
        "Abastecimento": ["Gasolina", "Etanol", "GNV", "Diesel"],
        "Estética": ["Polimento", "Lavagem Completa", "Pintura/Funilaria", "Higienização Interna"],
        "Documentação": ["IPVA", "Licenciamento", "Seguro Auto", "Multas"],
        "Acessórios/Upgrade": ["Som/Multimídia", "Lâmpadas LED", "Insulfilm"]
    }

    PRAZOS_KM = {
        "Óleo do Motor (5W30)": 5000, "Correia Dentada": 50000, "Fluido de Câmbio (GF6)": 40000,
        "Amortecedores": 60000, "Óleo de Direção Hidráulica": 40000, "Bandejas e Buchas": 40000
    }

    # --- 3. SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Painel Spin")
        modo_escuro = st.toggle("🌙 Modo Noturno", value=True)
        st.session_state.km_atual = st.number_input("KM Atual no Painel:", value=st.session_state.km_atual)

    bg, card, txt, brd = ("#0f172a", "#1e293b", "#f1f5f9", "#334155") if modo_escuro else ("#f8fafc", "#ffffff", "#1e293b", "#e2e8f0")
    st.markdown(f"<style>.stApp {{ background-color: {bg}; color: {txt}; }} .card {{ background: {card}; padding: 15px; border-radius: 12px; border: 1px solid {brd}; margin-bottom: 10px; }}</style>", unsafe_allow_html=True)

    st.title("🚗 SpinGenius: Gestão de Custos Real")

    # --- 4. ABAS ---
    tab_registro, tab_saude, tab_financeiro = st.tabs(["📝 Lançar Gasto/Previsão", "🩺 Saúde do Carro", "📊 Real vs. Previsto"])

    # --- ABA 1: LANÇAMENTO (REATIVIDADE CORRIGIDA) ---
    with tab_registro:
        st.subheader("Novo Registro")
        # Criamos o selectbox de tipo FORA do form para garantir reatividade imediata na lista de itens
        tipo_selecionado = st.selectbox("Tipo de Gasto:", list(CATEGORIAS.keys()), key="tipo_gasto_select")
        
        with st.form("form_registro", clear_on_submit=True):
            itens_disponiveis = CATEGORIAS[tipo_selecionado]
            item_final = st.selectbox("O que foi feito/comprado?", itens_disponiveis)
            
            c1, c2 = st.columns(2)
            valor_previsto = c1.number_input("Previsão de Gasto (R$)", min_value=0.0)
            valor_real = c2.number_input("Valor Real Pago (R$)", min_value=0.0)
            
            c3, c4 = st.columns(2)
            km_registro = c3.number_input("KM no momento:", value=st.session_state.km_atual)
            litros = c4.number_input("Litros (se abastecimento):", min_value=0.0)

            if st.form_submit_button("Salvar no Livro de Bordo"):
                novo_dado = {
                    "Data": datetime.now().strftime("%Y-%m-%d"),
                    "Tipo": tipo_selecionado,
                    "Item": item_final,
                    "KM": km_registro,
                    "Previsto": valor_previsto,
                    "Real": valor_real,
                    "Litros": litros,
                    "Economia": valor_previsto - valor_real if valor_previsto > 0 else 0
                }
                st.session_state.historico.append(novo_dado)
                st.session_state.km_atual = km_registro
                st.success(f"Registro de {item_final} salvo!")
                st.rerun()

    # DataFrame mestre para as outras abas
    df_base = pd.DataFrame(st.session_state.historico) if st.session_state.historico else pd.DataFrame(columns=["Data", "Tipo", "Item", "KM", "Previsto", "Real", "Litros", "Economia"])

    # --- ABA 2: SAÚDE ---
    with tab_saude:
        st.subheader("Termômetro de Manutenção")
        if not df_base.empty:
            cols = st.columns(3)
            for idx, (peca, km_limite) in enumerate(PRAZOS_KM.items()):
                # Filtra apenas manutenções para calcular a saúde
                ultima = df_base[(df_base['Item'] == peca) & (df_base['Tipo'] == "Manutenção Corretiva/Preventiva")].sort_values('KM', ascending=False)
                km_rodado = st.session_state.km_atual - (ultima['KM'].iloc[0] if not ultima.empty else 0)
                saude = max(0, 100 - (km_rodado / km_limite * 100))
                with cols[idx % 3]:
                    cor = "🟢" if saude > 70 else "🟡" if saude > 30 else "🔴"
                    st.markdown(f"<div class='card'>{cor} <b>{peca}</b><br><h2 style='margin:0;'>{int(saude)}%</h2><small>Faltam {max(0, km_limite-km_rodado)} KM</small></div>", unsafe_allow_html=True)
        else:
            st
