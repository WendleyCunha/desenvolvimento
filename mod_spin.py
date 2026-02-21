import streamlit as st
import pandas as pd
from datetime import datetime

def exibir_tamagotchi(user_info):
    # --- INTERRUPTOR DE MODO (DARK/LIGHT) ---
    with st.sidebar:
        st.divider()
        modo_escuro = st.toggle("🌙 Modo Noturno (Dark)", value=True)

    # --- DEFINIÇÃO DE PALETA DE CORES DINÂMICA ---
    if modo_escuro:
        bg_app = "#0f172a"
        bg_card = "#1e293b"
        text_main = "#f1f5f9"
        text_sub = "#94a3b8"
        border_color = "#334155"
        accent_blue = "#0ea5e9"
    else:
        bg_app = "#f8fafc"
        bg_card = "#ffffff"
        text_main = "#1e293b"
        text_sub = "#64748b"
        border_color = "#e2e8f0"
        accent_blue = "#2563eb"

    # --- INJEÇÃO DE CSS DINÂMICO ---
    st.markdown(f"""
        <style>
        .stApp {{ background-color: {bg_app}; color: {text_main}; }}
        
        .card-container {{
            background: {bg_card};
            padding: 25px;
            border-radius: 20px;
            border: 1px solid {border_color};
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            text-align: center;
            margin-bottom: 20px;
        }}

        .thermo-container {{
            width: 40px; height: 120px;
            background: {border_color};
            border-radius: 20px;
            margin: 0 auto;
            position: relative;
            border: 2px solid {border_color};
            overflow: hidden;
        }}
        .thermo-fill {{
            position: absolute; bottom: 0; width: 100%;
            transition: height 0.5s ease-in-out;
        }}

        /* Ajuste das abas para o modo claro/escuro */
        .stTabs [data-baseweb="tab"] {{
            background-color: {bg_card} !important;
            color: {text_sub} !important;
            border: 1px solid {border_color} !important;
            margin-right: 10px;
            border-radius: 10px 10px 0 0;
        }}
        .stTabs [aria-selected="true"] {{
            background-color: {accent_blue} !important;
            color: white !important;
        }}
        </style>
    """, unsafe_allow_html=True)

    st.title("🚗 SpinGenius: Gestão Profissional")

    # --- LÓGICA DE SAÚDE ---
    km_atual = st.session_state.get('km_atual', 138000)
    restante_oleo = 143000 - km_atual
    saude_percent = max(0, (restante_oleo / 5000) * 100)
    
    # Cores do termômetro (sempre vibrantes)
    cor_saude = "#22c55e" if saude_percent > 70 else "#eab308" if saude_percent > 30 else "#ef4444"

    # --- DASHBOARD VISUAL ---
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(f"""
            <div class="card-container">
                <p style="color:{text_sub}; font-size:0.9rem;">Saúde do Carro</p>
                <h2 style="color:{cor_saude}; margin:10px 0;">{int(saude_percent)}%</h2>
                <div style="background:{border_color}; border-radius:10px; height:10px; width:80%; margin: 0 auto;">
                    <div style="background:{cor_saude}; width:{saude_percent}%; height:100%; border-radius:10px;"></div>
                </div>
                <p style="color:{text_sub}; font-size:0.8rem; margin-top:10px;">Status: {'Operacional' if saude_percent > 30 else 'Revisão Necessária'}</p>
            </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
            <div class="card-container">
                <p style="color:{text_sub}; font-size:0.9rem;">Estabilidade do Câmbio</p>
                <div class="thermo-container">
                    <div class="thermo-fill" style="height:78%; background:linear-gradient(to top, #3b82f6, {accent_blue});"></div>
                </div>
                <h3 style="color:{accent_blue}; margin-top:10px;">78%</h3>
            </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
            <div class="card-container">
                <p style="color:{text_sub}; font-size:0.9rem;">Próximo Óleo</p>
                <h2 style="color:{text_main}; margin:10px 0;">{restante_oleo} <small>KM</small></h2>
                <div class="thermo-container">
                    <div class="thermo-fill" style="height:{(restante_oleo/5000)*100}%; background:{cor_saude};"></div>
                </div>
                <p style="color:{text_sub}; font-size:0.8rem; margin-top:10px;">Alvo: 143.000 KM</p>
            </div>
        """, unsafe_allow_html=True)

    # --- CONTEÚDO ---
    t1, t2, t3 = st.tabs(["💡 Dicas de Gênio", "🗓️ Plano 10 Anos", "🏆 Quiz Perito"])

    with t1:
        st.info(f"**Dica de Gênio:** {user_info['nome']}, para manter a saúde em 100%, verifique o nível do arrefecimento toda segunda-feira de manhã.")
        if st.button("✅ Registrar Troca de Óleo"):
            st.success("Histórico atualizado!")
            st.balloons()

    with t2:
        st.write("### Cronograma de Longo Prazo")
        st.table(pd.DataFrame({
            "Item": ["Câmbio (Fluido)", "Velas e Cabos", "Líquido de Arrefecimento"],
            "Quando": ["170.000 KM", "150.000 KM", "Fevereiro/2027"],
            "Estimativa R$": ["R$ 800,00", "R$ 350,00", "R$ 200,00"]
        }))

    with t3:
        st.radio("Qual o sintoma de bieletas gastas na Spin?", ["Zunido no motor", "Estalos em terrenos irregulares", "Marcha lenta oscilando"])
        st.button("Validar Quiz")

    # --- LIVRO DE BORDO ---
    st.divider()
    st.subheader("📑 Livro de Bordo Digital")
    with st.expander("📝 Nova Entrada"):
        st.text_input("Serviço")
        st.number_input("Valor")
        st.file_uploader("Anexo")
        st.button("Salvar")
