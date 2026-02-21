import streamlit as st
import pandas as pd
from datetime import datetime

def exibir_tamagotchi(user_info):
    # --- CSS DE ALTO NÍVEL PARA VISUAL DARK & GLOSSY ---
    st.markdown("""
        <style>
        /* Fundo principal e containers */
        .stApp { background-color: #0f172a; color: #f1f5f9; }
        [data-testid="stHeader"] { background: rgba(0,0,0,0); }
        
        /* Estilização dos Cards do Topo */
        .card-container {
            background: #1e293b;
            padding: 25px;
            border-radius: 20px;
            border: 1px solid #334155;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            text-align: center;
            margin-bottom: 20px;
        }

        /* O Termômetro Vertical */
        .thermo-container {
            width: 40px;
            height: 120px;
            background: #334155;
            border-radius: 20px;
            margin: 0 auto;
            position: relative;
            border: 2px solid #475569;
            overflow: hidden;
        }
        .thermo-fill {
            position: absolute;
            bottom: 0;
            width: 100%;
            transition: height 0.5s ease-in-out;
        }

        /* Customização de Tabs */
        .stTabs [data-baseweb="tab-list"] { gap: 15px; }
        .stTabs [data-baseweb="tab"] {
            background-color: #1e293b !important;
            border-radius: 10px 10px 0 0;
            padding: 10px 30px !important;
            color: #94a3b8 !important;
            border: 1px solid #334155 !important;
        }
        .stTabs [aria-selected="true"] {
            background-color: #0ea5e9 !important;
            color: white !important;
            border-bottom: 2px solid white !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("🚗 SpinGenius: Gestão Profissional")

    # --- LÓGICA DINÂMICA DE SAÚDE ---
    km_atual = st.session_state.get('km_atual', 138000)
    # Exemplo: O óleo vence com 5.000km rodados
    km_vencimento_oleo = 143000
    restante_oleo = km_vencimento_oleo - km_atual
    
    # Percentual de saúde baseado no óleo (pode ser expandido para outros itens)
    saude_percent = max(0, (restante_oleo / 5000) * 100)
    
    # Cores baseadas no estado
    if saude_percent > 70: cor_saude = "#22c55e" # Verde
    elif saude_percent > 30: cor_saude = "#eab308" # Amarelo
    else: cor_saude = "#ef4444" # Vermelho

    # --- DASHBOARD DE TERMÔMETROS (AQUELE VISUAL DA IMAGEM) ---
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(f"""
            <div class="card-container">
                <p style="color:#94a3b8; font-size:0.9rem;">Saúde do Carro</p>
                <h2 style="color:{cor_saude}; margin:10px 0;">{int(saude_percent)}%</h2>
                <div style="background:#334155; border-radius:10px; height:10px; width:80%; margin: 0 auto;">
                    <div style="background:{cor_saude}; width:{saude_percent}%; height:100%; border-radius:10px;"></div>
                </div>
                <p style="font-size:0.8rem; margin-top:10px;">Status: {'Operacional' if saude_percent > 30 else 'Manutenção Crítica'}</p>
            </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
            <div class="card-container">
                <p style="color:#94a3b8; font-size:0.9rem;">Estabilidade do Câmbio</p>
                <div class="thermo-container">
                    <div class="thermo-fill" style="height:78%; background:linear-gradient(to top, #3b82f6, #0ea5e9);"></div>
                </div>
                <h3 style="color:#0ea5e9; margin-top:10px;">78%</h3>
            </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
            <div class="card-container">
                <p style="color:#94a3b8; font-size:0.9rem;">Próximo Óleo</p>
                <h2 style="color:#f1f5f9; margin:10px 0;">{restante_oleo} <span style="font-size:0.8rem;">KM</span></h2>
                <div class="thermo-container">
                    <div class="thermo-fill" style="height:{(restante_oleo/5000)*100}%; background:{cor_saude};"></div>
                </div>
                <p style="font-size:0.8rem; margin-top:10px;">Alvo: 143.000 KM</p>
            </div>
        """, unsafe_allow_html=True)

    # --- SISTEMA DE ABAS ---
    t1, t2, t3 = st.tabs(["💡 Dicas de Gênio", "🗓️ Plano 10 Anos", "🏆 Quiz Perito"])

    with t1:
        st.markdown(f"### 🧞 Olá, {user_info['nome']}!")
        with st.container(border=True):
            st.warning(f"⚠️ **ANÁLISE DE GÊNIO:** Sua Spin está com {km_atual} KM. O motor 1.8 8V é robusto, mas o termômetro indica que você deve trocar o óleo em {restante_oleo} KM.")
            if st.button("✅ Marcar Manutenção como Executada"):
                st.balloons()
                st.success("Saúde restaurada! Não esqueça de anexar o comprovante abaixo.")

    with t2:
        st.write("### Cronograma de Longevidade")
        df = pd.DataFrame({
            "Componente": ["Correia Dentada", "Fluido Câmbio", "Arrefecimento", "Bieletas"],
            "Próxima Troca": ["178.000 KM", "168.000 KM", "Anual", "Preventiva"],
            "Urgência": ["MÁXIMA", "ALTA", "MÉDIA", "BAIXA"]
        })
        st.table(df)

    with t3:
        st.write("### Desafio Perito Spin")
        if 'p_idx' not in st.session_state: st.session_state.p_idx = 0
        perguntas = [
            {"p": "Qual a pressão ideal dos pneus (vazia)?", "o": ["28 PSI", "32 PSI", "35 PSI"], "r": "32 PSI"},
            {"p": "Qual o motor da Spin 2013?", "o": ["Ecotec 1.6", "Família I 1.8 8V", "Família II 2.0"], "r": "Família I 1.8 8V"}
        ]
        
        if st.session_state.p_idx < len(perguntas):
            atual = perguntas[st.session_state.p_idx]
            escolha = st.radio(atual["p"], atual["o"])
            if st.button("Verificar"):
                if escolha == atual["r"]:
                    st.success("Correto!")
                    st.session_state.p_idx += 1
                    st.rerun()
                else: st.error("Tente novamente!")
        else:
            st.success("🏆 Você é um mestre da Spin!")
            if st.button("Reiniciar Quiz"): 
                st.session_state.p_idx = 0
                st.rerun()

    # --- HISTÓRICO E GESTÃO ---
    st.divider()
    st.subheader("📑 Livro de Bordo Digital")
    
    with st.expander("📝 Registrar Gasto / Peça"):
        c_a, c_b = st.columns(2)
        c_a.text_input("Peça/Serviço")
        c_b.number_input("Valor (R$)", format="%.2f")
        st.file_uploader("Anexar Nota Fiscal (PDF/JPG)")
        st.button("Salvar Registro")

    # Exemplo de tabela de histórico
    st.dataframe(pd.DataFrame({
        "Data": ["21/02/2026", "15/01/2026"],
        "KM": [138000, 137500],
        "Serviço": ["Troca Óleo 5W30", "Alinhamento"],
        "Custo": ["R$ 280,00", "R$ 120,00"]
    }), use_container_width=True)
