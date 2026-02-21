import streamlit as st
import pandas as pd
from datetime import datetime

def exibir_tamagotchi(user_info):
    # --- ESTILIZAÇÃO CUSTOMIZADA (DASHBOARD DARK) ---
    st.markdown("""
        <style>
        .main { background-color: #1e293b; color: white; }
        div[data-testid="stMetricValue"] { color: #38bdf8; font-family: 'Courier New', monospace; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] {
            background-color: #334155;
            border-radius: 10px 10px 0px 0px;
            padding: 10px 20px;
            color: white;
        }
        .stTabs [aria-selected="true"] { background-color: #002366; border-bottom: 2px solid #38bdf8; }
        /* Estilo do Card de Saúde */
        .health-card {
            background: #0f172a;
            padding: 20px;
            border-radius: 15px;
            border: 1px solid #334155;
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("🚗 SpinGenius: Gestão Profissional")

    # --- LÓGICA DE SAÚDE (TERMÔMETRO) ---
    # Simulando que a saúde cai conforme o KM sobe
    km_atual = st.session_state.get('km_atual', 138000)
    proxima_revisao = 143000
    
    # Cálculo percentual (exemplo: óleo dura 5000km)
    km_rodados_desde_troca = km_atual - 138000
    saude_percent = max(0, 100 - (km_rodados_desde_troca / 50)) 
    
    # Cor do termômetro
    cor_saude = "#22c55e" if saude_percent > 70 else "#eab308" if saude_percent > 30 else "#ef4444"

    # --- DASHBOARD VISUAL (TERMÔMETROS) ---
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(f"""
            <div class="health-card">
                <p style="margin-bottom:5px;">Saúde do Carro</p>
                <h2 style="color:{cor_saude};">{int(saude_percent)}%</h2>
                <div style="background:#334155; border-radius:10px; height:15px;">
                    <div style="background:{cor_saude}; width:{saude_percent}%; height:100%; border-radius:10px;"></div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
            <div class="health-card">
                <p style="margin-bottom:5px;">Último Check-up</p>
                <h2 style="color:#38bdf8;">78%</h2>
                <p style="font-size:12px;">Estabilidade do Câmbio</p>
            </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
            <div class="health-card">
                <p style="margin-bottom:5px;">Próx. Óleo</p>
                <h2 style="color:#38bdf8;">{proxima_revisao - km_atual} KM</h2>
                <p style="font-size:12px;">Estimado: 143.000 KM</p>
            </div>
        """, unsafe_allow_html=True)

    st.divider()

    # --- ABAS DE NAVEGAÇÃO ---
    tab1, tab2, tab3 = st.tabs(["🚗 Dicas de Gênio", "📅 Plano 10 Anos", "🏆 Quiz Perito"])

    with tab1:
        st.subheader("💡 Dicas de Gênio")
        with st.container(border=True):
            st.markdown(f"**Olá, {user_info['nome']}!** Esta é uma análise de inteligência para sua Spin:")
            st.warning("⚠️ **ALERTA DE MANUTENÇÃO:** Sua saúde de motor está em 78%. O Jênio recomenda a troca imediata do óleo 5W30 Sintético.")
            
            if st.button("✅ Marcar Óleo como Trocado!"):
                st.success("Saúde restaurada para 100%! Registro enviado ao histórico.")
                st.balloons()
        
        st.info("ℹ️ **Dica de Gênio:** O câmbio GF6 da Spin 2013 prefere trocas de óleo parciais a cada 40 mil km para evitar trancos. Não acredite em 'fluido vitalício'.")

    with tab2:
        st.subheader("🗓️ Plano de Longevidade (10 Anos)")
        df_plano = pd.DataFrame({
            "Sistema": ["Motor", "Câmbio", "Arrefecimento", "Suspensão"],
            "Ação": ["Troca Óleo/Filtro", "Troca Parcial Fluido", "Limpeza/Aditivo", "Bieletas/Buchas"],
            "KM Alvo": ["143.000", "170.000", "150.000", "Sempre que bater"],
            "Urgência": ["Alta", "Média", "Média", "Crítica"]
        })
        st.table(df_plano)

    with tab3:
        st.subheader("🧠 Quiz Perito Spin")
        # Lógica simples de quiz sequencial
        if 'pergunta_atual' not in st.session_state: st.session_state.pergunta_atual = 1
        
        if st.session_state.pergunta_atual == 1:
            resp = st.radio("Qual o óleo recomendado no manual da Spin 2013?", ["10W40", "5W30 Sintético", "15W40 Mineral"])
            if st.button("Confirmar Resposta"):
                if resp == "5W30 Sintético":
                    st.success("Certo! Avançando para a próxima...")
                    st.session_state.pergunta_atual = 2
                    st.rerun()
        else:
            st.write("🎉 Você acertou a primeira! Em breve mais perguntas...")
            if st.button("Resetar Quiz"): 
                st.session_state.pergunta_atual = 1
                st.rerun()

    # --- HISTÓRICO COMPLETO ---
    st.divider()
    st.subheader("📑 Histórico Completo de Manutenção")
    # Exemplo de dados para a tabela
    hist_data = {
        "Data": ["20/02/2026", "10/01/2026"],
        "Serviço": ["Reparo de Câmbio (Parcial)", "Alinhamento/Balanceamento"],
        "KM": [128000, 125000],
        "Custo": ["R$ 4.500,00", "R$ 180,00"]
    }
    st.dataframe(pd.DataFrame(hist_data), use_container_width=True)
    st.button("📥 Exportar Relatório para Venda (PDF)")
