import streamlit as st
import pandas as pd
from datetime import datetime

def exibir_tamagotchi(user_info):
    # --- 1. GESTÃO DE ESTADO (KM E HISTÓRICO) ---
    # Simulando persistência de dados (O ideal é conectar ao seu database.db)
    if 'km_atual' not in st.session_state:
        st.session_state.km_atual = 138000
    
    if 'historico_spin' not in st.session_state:
        st.session_state.historico_spin = [
            {"Data": "10/01/2026", "KM": 137500, "Serviço": "Alinhamento", "Custo": 120.00},
        ]

    # --- 2. CONFIGURAÇÃO DE CORES (MODO DARK/LIGHT) ---
    with st.sidebar:
        st.header("⚙️ Ajustes")
        modo_escuro = st.toggle("🌙 Modo Noturno", value=True)
        st.divider()
        st.subheader("📟 Atualizar Painel")
        novo_km = st.number_input("KM Atual Manual:", value=st.session_state.km_atual, step=50)
        if novo_km != st.session_state.km_atual:
            st.session_state.km_atual = novo_km
            st.rerun()

    if modo_escuro:
        bg_app, bg_card, text_main, text_sub, border_color, accent_blue = "#0f172a", "#1e293b", "#f1f5f9", "#94a3b8", "#334155", "#0ea5e9"
    else:
        bg_app, bg_card, text_main, text_sub, border_color, accent_blue = "#f8fafc", "#ffffff", "#1e293b", "#64748b", "#e2e8f0", "#2563eb"

    st.markdown(f"""<style>
        .stApp {{ background-color: {bg_app}; color: {text_main}; }}
        .card-container {{ background: {bg_card}; padding: 25px; border-radius: 20px; border: 1px solid {border_color}; text-align: center; margin-bottom: 20px; }}
        .thermo-container {{ width: 40px; height: 120px; background: {border_color}; border-radius: 20px; margin: 0 auto; position: relative; overflow: hidden; }}
        .thermo-fill {{ position: absolute; bottom: 0; width: 100%; transition: height 0.5s ease-in-out; }}
        .stTabs [data-baseweb="tab"] {{ background-color: {bg_card} !important; color: {text_sub} !important; border: 1px solid {border_color} !important; border-radius: 10px 10px 0 0; }}
        .stTabs [aria-selected="true"] {{ background-color: {accent_blue} !important; color: white !important; }}
    </style>""", unsafe_allow_html=True)

    # --- 3. CÁLCULOS DINÂMICOS ---
    km_atual = st.session_state.km_atual
    km_proximo_oleo = 143000
    restante_oleo = max(0, km_proximo_oleo - km_atual)
    saude_percent = max(0, (restante_oleo / 5000) * 100)
    cor_saude = "#22c55e" if saude_percent > 70 else "#eab308" if saude_percent > 30 else "#ef4444"

    st.title("🚗 SpinGenius: Gestão Profissional")

    # --- 4. DASHBOARD VISUAL ---
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="card-container"><p style="color:{text_sub};">Saúde do Motor</p><h2 style="color:{cor_saude};">{int(saude_percent)}%</h2>'
                    f'<div style="background:{border_color}; border-radius:10px; height:10px; width:80%; margin:0 auto;">'
                    f'<div style="background:{cor_saude}; width:{saude_percent}%; height:100%; border-radius:10px;"></div></div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="card-container"><p style="color:{text_sub};">Estabilidade Câmbio</p>'
                    f'<div class="thermo-container"><div class="thermo-fill" style="height:78%; background:#3b82f6;"></div></div><h3 style="color:{accent_blue};">78%</h3></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="card-container"><p style="color:{text_sub};">Próx. Óleo</p><h2 style="color:{text_main};">{restante_oleo} <small>KM</small></h2>'
                    f'<div class="thermo-container"><div class="thermo-fill" style="height:{(restante_oleo/5000)*100}%; background:{cor_saude};"></div></div></div>', unsafe_allow_html=True)

    # --- 5. CONTEÚDO E TAREFAS ---
    t1, t2, t3 = st.tabs(["💡 Dicas de Gênio", "🗓️ Plano 10 Anos", "🏆 Quiz Perito"])

    with t1:
        if saude_percent < 20:
            st.error(f"🚨 **URGENTE:** {user_info['nome']}, você está a apenas {restante_oleo}km da revisão crítica!")
        elif saude_percent < 50:
            st.warning(f"⚠️ **AVISO:** Metade da vida útil do óleo já foi. Hora de orçar os filtros.")
        else:
            st.success(f"✅ **TUDO EM ORDEM:** Sua Spin está saudável. Continue monitorando!")
        
        st.info("**Dica de Gênio:** O reservatório de expansão da Spin costuma trincar na base. Olhe por baixo dele hoje!")

    with t2:
        st.subheader("🗓️ Cronograma Automático")
        # Plano recalcula baseado no KM atual
        plano_dinamico = [
            {"Item": "Correia Dentada", "KM Alvo": 180000, "Falta": 180000 - km_atual},
            {"Item": "Fluido Câmbio", "KM Alvo": 170000, "Falta": 170000 - km_atual},
            {"Item": "Velas/Cabos", "KM Alvo": 150000, "Falta": 150000 - km_atual},
        ]
        st.dataframe(pd.DataFrame(plano_dinamico), use_container_width=True)

    with t3:
        st.write("### Quiz do Especialista")
        pergunta = st.radio("Qual a folga das válvulas da Spin 1.8 8V?", ["É regulagem automática (Tucho Hidráulico)", "0.20mm Admissão", "0.25mm Escape"])
        if st.button("Validar"):
            if "automática" in pergunta: st.success("Certo! Menos uma preocupação na sua Spin.")
            else: st.error("Incorreto. A Spin usa tuchos hidráulicos!")

    # --- 6. LIVRO DE BORDO (O GATILHO) ---
    st.divider()
    st.subheader("📑 Livro de Bordo Digital")
    
    with st.expander("📝 Registrar Manutenção (Gatilho de KM)"):
        with st.form("form_registro"):
            col_a, col_b = st.columns(2)
            serv = col_a.text_input("O que foi feito?")
            valor_pago = col_b.number_input("Valor Pago (R$)", min_value=0.0)
            # O ponto chave: perguntar o KM no ato da manutenção
            km_no_ato = st.number_input("Qual o KM que está no painel agora?", value=st.session_state.km_atual)
            anexo = st.file_uploader("Anexar Nota ou Foto")
            
            if st.form_submit_button("Salvar e Atualizar Sistema"):
                # 1. Atualiza o KM global (O GATILHO)
                st.session_state.km_atual = km_no_ato
                # 2. Salva no histórico
                novo_item = {"Data": datetime.now().strftime("%d/%m/%Y"), "KM": km_no_ato, "Serviço": serv, "Custo": valor_pago}
                st.session_state.historico_spin.append(novo_item)
                
                st.toast("Dados sincronizados!", icon="🔄")
                st.rerun()

    st.write("### Histórico de Gastos")
    st.table(pd.DataFrame(st.session_state.historico_spin))
