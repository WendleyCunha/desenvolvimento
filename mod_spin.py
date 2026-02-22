import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

def exibir_tamagotchi(user_info):
    # --- 1. ESTADO DOS DADOS ---
    if 'km_atual' not in st.session_state: 
        st.session_state.km_atual = 138000
    if 'historico' not in st.session_state: 
        st.session_state.historico = []

    # --- 2. ESTRUTURA ---
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

    # --- 3. UI ---
    with st.sidebar:
        st.header("⚙️ Painel Spin")
        modo_escuro = st.toggle("🌙 Modo Noturno", value=True)
        st.session_state.km_atual = st.number_input("KM Atual no Painel:", value=st.session_state.km_atual)

    bg, card, txt, brd = ("#0f172a", "#1e293b", "#f1f5f9", "#334155") if modo_escuro else ("#f8fafc", "#ffffff", "#1e293b", "#e2e8f0")
    st.markdown(f"<style>.stApp {{ background-color: {bg}; color: {txt}; }} .card {{ background: {card}; padding: 15px; border-radius: 12px; border: 1px solid {brd}; margin-bottom: 10px; }}</style>", unsafe_allow_html=True)

    st.title("🚗 SpinGenius: Gestão de Custos Real")

    tab_registro, tab_saude, tab_financeiro = st.tabs(["📝 Lançar Gasto", "🩺 Saúde", "📊 Real vs. Previsto"])

    # --- ABA 1: REGISTRO ---
    with tab_registro:
        tipo_selecionado = st.selectbox("Tipo de Gasto:", list(CATEGORIAS.keys()))
        itens_disponiveis = CATEGORIAS[tipo_selecionado]
        
        with st.form("form_registro", clear_on_submit=True):
            item_final = st.selectbox("O que foi feito/comprado?", itens_disponiveis)
            c1, c2 = st.columns(2)
            v_prev = c1.number_input("Previsão (R$)", min_value=0.0)
            v_real = c2.number_input("Real Pago (R$)", min_value=0.0)
            
            c3, c4 = st.columns(2)
            km_reg = c3.number_input("KM no momento:", value=st.session_state.km_atual)
            litros = c4.number_input("Litros (se abastecimento):", min_value=0.0)

            if st.form_submit_button("Salvar no Livro de Bordo"):
                novo_dado = {
                    "Data": datetime.now().strftime("%Y-%m-%d"),
                    "Tipo": tipo_selecionado,
                    "Item": item_final,
                    "KM": km_reg,
                    "Previsto": float(v_prev),
                    "Real": float(v_real),
                    "Litros": float(litros),
                    "Economia": float(v_prev - v_real)
                }
                st.session_state.historico.append(novo_dado)
                st.session_state.km_atual = km_reg
                st.success("Salvo com sucesso!")
                st.rerun()

    # --- PROCESSAMENTO DOS DADOS (O Coração do Dashboard) ---
    # Criamos o DF aqui fora para garantir que todas as abas o vejam
    if len(st.session_state.historico) > 0:
        df_base = pd.DataFrame(st.session_state.historico)
        # Força conversão para garantir que números sejam números
        df_base['Real'] = pd.to_numeric(df_base['Real'])
        df_base['Previsto'] = pd.to_numeric(df_base['Previsto'])
    else:
        df_base = pd.DataFrame()

    # --- ABA 2: SAÚDE ---
    with tab_saude:
        if not df_base.empty:
            cols = st.columns(3)
            for idx, (peca, km_limite) in enumerate(PRAZOS_KM.items()):
                # Filtra o histórico por peça
                h_peca = df_base[df_base['Item'] == peca].sort_values('KM', ascending=False)
                km_ultima = h_peca['KM'].iloc[0] if not h_peca.empty else 0
                
                km_rodado = st.session_state.km_atual - km_ultima
                saude = max(0, 100 - (km_rodado / km_limite * 100))
                
                with cols[idx % 3]:
                    cor = "🟢" if saude > 70 else "🟡" if saude > 30 else "🔴"
                    st.markdown(f"<div class='card'>{cor} <b>{peca}</b><br><h2>{int(saude)}%</h2><small>Faltam {max(0, km_limite-km_rodado)} KM</small></div>", unsafe_allow_html=True)
        else:
            st.info("Lance uma 'Manutenção Corretiva/Preventiva' para ativar os termômetros.")

    # --- ABA 3: FINANCEIRO (Onde estava o erro) ---
    with tab_financeiro:
        if not df_base.empty:
            # Métricas
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Planejado", f"R$ {df_base['Previsto'].sum():,.2f}")
            m2.metric("Total Real", f"R$ {df_base['Real'].sum():,.2f}")
            m3.metric("Economia Total", f"R$ {df_base['Economia'].sum():,.2f}")

            # Gráfico
            st.subheader("Gráfico Real vs. Previsto")
            resumo = df_base.groupby('Tipo')[['Previsto', 'Real']].sum().reset_index()
            fig = px.bar(resumo, x='Tipo', y=['Previsto', 'Real'], barmode='group', 
                         color_discrete_map={"Previsto": "#94a3b8", "Real": "#0ea5e9"})
            st.plotly_chart(fig, use_container_width=True)

            # Tabela
            st.subheader("Histórico de Lançamentos")
            st.dataframe(df_base, use_container_width=True)

            # Deletar
            st.divider()
            with st.expander("🗑️ Excluir Lançamento"):
                idx_del = st.selectbox("Selecione a linha:", range(len(st.session_state.historico)), 
                                      format_func=lambda x: f"{st.session_state.historico[x]['Data']} - {st.session_state.historico[x]['Item']} (R$ {st.session_state.historico[x]['Real']})")
                if st.button("Confirmar Exclusão"):
                    st.session_state.historico.pop(idx_del)
                    st.rerun()
        else:
            st.warning("Nenhum dado encontrado. Faça um lançamento na primeira aba!")
