import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import database as db
import pytz

def exibir_tamagotchi(user_info):
    # --- 1. CONFIGURAÇÃO DE TEMPO E FUSO ---
    fuso_brasil = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso_brasil)
    data_hoje_str = agora.strftime("%d/%m/%Y %H:%M")

    # --- 2. CARREGAMENTO PERSISTENTE ---
    if 'dados_spin' not in st.session_state:
        st.session_state.dados_spin = db.carregar_dados_spin()

    km_atual = st.session_state.dados_spin.get('km_atual', 138000)
    historico = st.session_state.dados_spin.get('historico', [])
    inspecoes = st.session_state.dados_spin.get('inspecoes', [])

    # --- 3. CONFIGURAÇÕES DE MANUTENÇÃO ---
    KM_REVISAO_GERAL = 127000 
    DATA_REVISAO_GERAL = datetime(2025, 1, 1, tzinfo=fuso_brasil)

    REGRAS_MANUTENCAO = {
        "Óleo do Motor (5W30)": [5000, 6], "Correia Dentada": [50000, 48],
        "Fluido de Câmbio (GF6)": [40000, 24], "Amortecedores": [60000, 60],
        "Bandejas e Buchas": [40000, 36], "Óleo de Direção Hidráulica": [40000, 24],
        "Fluido de Freio (DOT 4)": [20000, 12], "Líquido Arrefecimento": [30000, 24],
        "Velas e Cabos": [30000, 24], "Pneus": [50000, 60]
    }

    # --- 4. ESTILIZAÇÃO CSS ---
    st.markdown(f"""
        <style>
        .relogio {{ background: rgba(0,0,0,0.05); padding: 10px; border-radius: 10px; text-align: right; font-family: monospace; font-weight: bold; color: #3b82f6; margin-bottom: 20px; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 10px; }}
        .stTabs [data-baseweb="tab"] {{ padding: 10px 20px; border-radius: 10px 10px 0 0; font-weight: bold; }}
        @keyframes blinker {{ 50% {{ opacity: 0.3; transform: scale(1.02); }} }}
        .critico {{ background: rgba(239, 68, 68, 0.1) !important; border: 2px solid #ef4444 !important; animation: blinker 1.5s linear infinite; }}
        .card-componente {{ padding: 20px; border-radius: 15px; margin-bottom: 15px; border: 1px solid #e2e8f0; transition: 0.3s; }}
        </style>
    """, unsafe_allow_html=True)

    st.markdown(f"<div class='relogio'>🕒 Brasília: {data_hoje_str}</div>", unsafe_allow_html=True)

    CATEGORIAS = {
        "Abastecimento": ["Gasolina", "Etanol", "GNV", "Diesel"],
        "Manutenção Corretiva/Preventiva": list(REGRAS_MANUTENCAO.keys()),
        "Estética": ["Polimento", "Lavagem Completa", "Pintura/Funilaria"],
        "Documentação": ["IPVA", "Licenciamento", "Seguro Auto"],
        "Acessórios/Upgrade": ["Som/Multimídia", "Lâmpadas LED", "Insulfilm"]
    }

    # --- 5. UI SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Painel Spin")
        novo_km = st.number_input("KM Atual no Painel:", value=km_atual)
        if novo_km != km_atual:
            st.session_state.dados_spin['km_atual'] = novo_km
            db.salvar_dados_spin(st.session_state.dados_spin)
            st.rerun()

    st.title("🚗 SpinGenius: Gestão Inteligente")

    tab_registro, tab_saude, tab_eficiencia, tab_inspecao, tab_financeiro = st.tabs([
        "📝 Lançar Gasto", "🩺 Saúde", "📊 KM/L", "🔍 Inspeção", "💸 Financeiro"
    ])

    # --- ABA 1: REGISTRO ---
    with tab_registro:
        st.subheader("Registrar Novo Evento")
        baixa_ativa = st.session_state.get('baixa_em_curso', None)
        if baixa_ativa: st.warning(f"Finalizando inspeção: **{baixa_ativa['item']}**")
        tipo_selecionado = st.selectbox("Categoria:", list(CATEGORIAS.keys()))
        itens_disponiveis = CATEGORIAS[tipo_selecionado]
        
        with st.form("form_registro", clear_on_submit=True):
            item_final = st.text_input("Item:", value=baixa_ativa['item']) if baixa_ativa else st.selectbox("Item:", itens_disponiveis)
            c1, c2 = st.columns(2)
            v_prev = c1.number_input("Previsão (R$)", min_value=0.0)
            v_real = c2.number_input("Real Pago (R$)", min_value=0.0)
            c3, c4 = st.columns(2)
            km_reg = c3.number_input("KM Registrado:", value=novo_km)
            litros = c4.number_input("Litros (Abastecimento):", min_value=0.0, step=0.1)

            if st.form_submit_button("💾 SALVAR NO LIVRO DE BORDO", use_container_width=True):
                novo_dado = {
                    "Data": agora.strftime("%Y-%m-%d"), "Tipo": tipo_selecionado, "Item": item_final, 
                    "KM": km_reg, "Previsto": float(v_prev), "Real": float(v_real),
                    "Litros": float(litros), "Economia": float(v_prev - v_real)
                }
                st.session_state.dados_spin['historico'].append(novo_dado)
                if baixa_ativa: st.session_state.dados_spin['inspecoes'].pop(baixa_ativa['index']); del st.session_state['baixa_em_curso']
                db.salvar_dados_spin(st.session_state.dados_spin); st.success("✅ Lançado!"); st.rerun()
        if baixa_ativa and st.button("Cancelar Baixa"): del st.session_state['baixa_em_curso']; st.rerun()

    df_base = pd.DataFrame(historico) if historico else pd.DataFrame()

    # --- ABA 2: SAÚDE ---
    with tab_saude:
        st.subheader("Estado de Conservação")
        cols = st.columns(3)
        for idx, (peca, prazos) in enumerate(REGRAS_MANUTENCAO.items()):
            km_limite, meses_limite = prazos[0], prazos[1]
            km_ut, data_ut = KM_REVISAO_GERAL, DATA_REVISAO_GERAL
            if not df_base.empty:
                h = df_base[df_base['Item'] == peca].sort_values('Data', ascending=False)
                if not h.empty:
                    km_ut = h['KM'].iloc[0]
                    data_ut = datetime.strptime(h['Data'].iloc[0], "%Y-%m-%d").replace(tzinfo=fuso_brasil)
            km_rodado = km_atual - km_ut
            s_km = max(0, 100 - (km_rodado / km_limite * 100))
            dias = (agora - data_ut).days
            s_t = max(0, 100 - (dias / (meses_limite * 30) * 100))
            s_f = min(s_km, s_t)
            cor = "#ef4444" if s_f <= 20 else "#f59e0b" if s_f <= 50 else "#10b981"
            with cols[idx % 3]:
                st.markdown(f"<div class='card-componente {'critico' if s_f <= 20 else ''}' style='border-left: 5px solid {cor};'><b style='font-size: 0.9em;'>{peca}</b><h2 style='color: {cor}; margin: 5px 0;'>{int(s_f)}%</h2><small>Troca: {int(km_ut + km_limite):,} KM</small></div>", unsafe_allow_html=True)

    # --- ABA 3: EFICIÊNCIA (KM/L) ---
    with tab_eficiencia:
        if not df_base.empty and "Litros" in df_base.columns:
            df_fuel = df_base[df_base['Tipo'] == "Abastecimento"].sort_values('KM').copy()
            if len(df_fuel) >= 2:
                df_fuel['KML'] = df_fuel['KM'].diff() / df_fuel['Litros']
                st.plotly_chart(px.line(df_fuel.dropna(subset=['KML']), x='Data', y='KML', title="KM/L ao Longo do Tempo", markers=True), use_container_width=True)
                m1, m2 = st.columns(2)
                m1.metric("Média Geral", f"{df_fuel['KML'].mean():,.2f} km/l")
                m2.metric("Último KM/L", f"{df_fuel['KML'].iloc[-1]:,.2f} km/l")
            else: st.info("Registre pelo menos 2 abastecimentos.")

    # --- ABA 4: INSPEÇÃO ---
    with tab_inspecao:
        with st.form("f_insp"):
            c1, c2 = st.columns(2)
            i_it, i_st = c1.text_input("Item:"), c2.selectbox("Estado:", ["✅ Bom", "⚠️ Observar", "🚨 Trocar"])
            i_obs = st.text_area("Notas:")
            if st.form_submit_button("Salvar"):
                st.session_state.dados_spin['inspecoes'].append({"Data": agora.strftime("%d/%m/%Y"), "Item": i_it, "Status": i_st, "Obs": i_obs, "KM": km_atual})
                db.salvar_dados_spin(st.session_state.dados_spin); st.rerun()
        for i_idx, i in enumerate(reversed(inspecoes)):
            r_idx = len(inspecoes) - 1 - i_idx
            cor_s = {"✅ Bom": "green", "⚠️ Observar": "orange", "🚨 Trocar": "red"}
            c_inf, c_ac = st.columns([0.7, 0.3])
            c_inf.markdown(f"**{i['Item']}** ({i['KM']:,} KM)\n<span style='color:{cor_s[i['Status']]}; font-weight:bold;'>{i['Status']}</span> - {i['Obs']}", unsafe_allow_html=True)
            if c_ac.button("💸 Baixa", key=f"bx_{r_idx}"): st.session_state['baixa_em_curso'] = {'item': i['Item'], 'index': r_idx}; st.rerun()

    # --- ABA 5: FINANCEIRO ---
    with tab_financeiro:
        if not df_base.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Pago", f"R$ {df_base['Real'].sum():,.2f}")
            c2.metric("Abastecimento", f"R$ {df_base[df_base['Tipo']=='Abastecimento']['Real'].sum():,.2f}")
            c3.metric("Economia", f"R$ {df_base['Economia'].sum():,.2f}")
            st.dataframe(df_base.sort_values('Data', ascending=False), use_container_width=True)
            if st.button("🗑️ Deletar Último"): st.session_state.dados_spin['historico'].pop(); db.salvar_dados_spin(st.session_state.dados_spin); st.rerun()
