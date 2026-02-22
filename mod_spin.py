import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

def exibir_tamagotchi(user_info):
    # --- 1. CONFIGURAÇÃO DE ESTADO ---
    if 'km_atual' not in st.session_state: 
        st.session_state.km_atual = 138000
    
    # Inicializa o histórico como uma lista vazia se não existir
    if 'historico' not in st.session_state: 
        st.session_state.historico = []

    # --- 2. ESTRUTURA DE DADOS INTELIGENTE ---
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

    # --- 3. ESTILIZAÇÃO ---
    with st.sidebar:
        st.header("⚙️ Painel de Controle")
        modo_escuro = st.toggle("🌙 Modo Noturno", value=True)
        st.session_state.km_atual = st.number_input("KM Atual no Painel:", value=st.session_state.km_atual)
        st.divider()
        st.info(f"Veículo: Chevrolet Spin 2013\nUsuário: {user_info.get('nome', 'Piloto')}")

    bg, card, txt, brd = ("#0f172a", "#1e293b", "#f1f5f9", "#334155") if modo_escuro else ("#f8fafc", "#ffffff", "#1e293b", "#e2e8f0")
    
    st.markdown(f"""<style>
        .stApp {{ background-color: {bg}; color: {txt}; }}
        .card {{ background: {card}; padding: 15px; border-radius: 12px; border: 1px solid {brd}; margin-bottom: 10px; }}
    </style>""", unsafe_allow_html=True)

    st.title("🚗 SpinGenius: Gestão de Custos Real")

    # --- 4. ABAS ---
    tab_registro, tab_saude, tab_financeiro = st.tabs(["📝 Lançar Gasto/Previsão", "🩺 Saúde do Carro", "📊 Real vs. Previsto"])

    # --- ABA 1: LANÇAMENTO ---
    with tab_registro:
        st.subheader("Novo Registro")
        with st.form("form_registro"):
            tipo_selecionado = st.selectbox("Tipo de Gasto:", list(CATEGORIAS.keys()))
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

    # Criar um DataFrame seguro para as próximas abas
    if st.session_state.historico:
        df_base = pd.DataFrame(st.session_state.historico)
    else:
        # Colunas vazias para evitar KeyError
        df_base = pd.DataFrame(columns=["Data", "Tipo", "Item", "KM", "Previsto", "Real", "Litros", "Economia"])

    # --- ABA 2: SAÚDE ---
    with tab_saude:
        st.subheader("Termômetro de Manutenção")
        if not df_base.empty:
            cols = st.columns(3)
            for idx, (peca, km_limite) in enumerate(PRAZOS_KM.items()):
                ultima = df_base[df_base['Item'] == peca].sort_values('KM', ascending=False)
                km_rodado = st.session_state.km_atual - (ultima['KM'].iloc[0] if not ultima.empty else 0)
                saude = max(0, 100 - (km_rodado / km_limite * 100))
                
                with cols[idx % 3]:
                    cor = "🟢" if saude > 70 else "🟡" if saude > 30 else "🔴"
                    st.markdown(f"""<div class='card'>{cor} <b>{peca}</b><br>
                                <h2 style='margin:0;'>{int(saude)}%</h2>
                                <small>Faltam {max(0, km_limite-km_rodado)} KM</small></div>""", unsafe_allow_html=True)
        else:
            st.info("Aguardando o primeiro registro de manutenção para calcular a saúde.")

    # --- ABA 3: FINANCEIRO ---
    with tab_financeiro:
        if not df_base.empty:
            m1, m2, m3 = st.columns(3)
            # Conversão para garantir que valores vazios sejam zero
            total_prev = pd.to_numeric(df_base['Previsto']).sum()
            total_real = pd.to_numeric(df_base['Real']).sum()
            
            m1.metric("Total Planejado", f"R$ {total_prev:,.2f}")
            m2.metric("Total Real Gasto", f"R$ {total_real:,.2f}", 
                      delta=f"{total_prev - total_real:,.2f} economizados", delta_color="normal")
            m3.metric("KM Atual", f"{st.session_state.km_atual}")

            st.subheader("Planejado vs. Real por Categoria")
            df_chart = df_base.groupby('Tipo')[['Previsto', 'Real']].sum().reset_index()
            fig = px.bar(df_chart, x='Tipo', y=['Previsto', 'Real'], barmode='group',
                         color_discrete_map={"Previsto": "#94a3b8", "Real": "#0ea5e9"})
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("Histórico Completo")
            st.dataframe(df_base, use_container_width=True)
        else:
            st.warning("Nenhum dado financeiro disponível. Comece registrando um gasto ou abastecimento.")
