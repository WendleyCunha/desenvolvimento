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

    # --- 3. CONFIGURAÇÕES TÉCNICAS (NÍVEL PERITO) ---
    KM_REVISAO_GERAL = 127000 
    DATA_REVISAO_GERAL = datetime(2025, 1, 1, tzinfo=fuso_brasil)

    REGRAS_MANUTENCAO = {
        "Óleo do Motor (5W30)": [5000, 6], "Filtros (Ar/Comb/Óleo)": [10000, 12],
        "Velas e Cabos": [30000, 24], "Correia Dentada": [50000, 48],
        "Fluido de Câmbio (GF6)": [40000, 24], "Amortecedores": [60000, 60],
        "Bandejas e Buchas": [40000, 36], "Óleo de Direção": [40000, 24],
        "Fluido de Freio (DOT 4)": [20000, 12], "Arrefecimento": [30000, 24],
        "Pneus (Rodízio)": [10000, 6]
    }

    # --- 4. ESTILIZAÇÃO CSS ---
    st.markdown(f"""
        <style>
        .relogio {{ background: #1e293b; padding: 10px; border-radius: 10px; text-align: right; font-family: monospace; font-weight: bold; color: #60a5fa; margin-bottom: 20px; border: 1px solid #334155; }}
        .stTabs [data-baseweb="tab-list"] {{ gap: 8px; }}
        .card-componente {{ padding: 15px; border-radius: 12px; margin-bottom: 10px; border: 1px solid #e2e8f0; background: white; }}
        .critico {{ border: 2px solid #ef4444 !important; animation: blinker 1.5s linear infinite; }}
        .panel-financeiro {{ background: #f8fafc; padding: 20px; border-radius: 15px; border: 1px solid #e2e8f0; margin-bottom: 20px; }}
        @keyframes blinker {{ 50% {{ opacity: 0.5; }} }}
        </style>
    """, unsafe_allow_html=True)

    st.markdown(f"<div class='relogio'>🛠️ TELEMETRIA ATIVA: {data_hoje_str}</div>", unsafe_allow_html=True)

    CATEGORIAS = {
        "Abastecimento": ["Gasolina", "Etanol", "GNV"],
        "Manutenção (Peças/Mão de Obra)": list(REGRAS_MANUTENCAO.keys()) + ["Mão de Obra", "Outros"],
        "Documentação/Seguro": ["IPVA", "Licenciamento", "Seguro Auto"],
        "Estética/Upgrades": ["Lavagem", "Polimento", "Acessórios"]
    }

    # --- 5. UI SIDEBAR ---
    with st.sidebar:
        st.header("⚙️ Painel de Controle")
        novo_km = st.number_input("Odômetro Atual:", value=km_atual)
        if novo_km != km_atual:
            st.session_state.dados_spin['km_atual'] = novo_km
            db.salvar_dados_spin(st.session_state.dados_spin)
            st.rerun()
        st.info("Foco: Manutenção Preventiva e Custo Real.")

    st.title("🚗 SpinGenius PRO")

    tab_registro, tab_saude, tab_eficiencia, tab_inspecao, tab_financeiro = st.tabs([
        "📝 Lançar", "🩺 Saúde", "📊 Consumo", "🔍 Inspeção", "💸 Financeiro"
    ])

    # --- ABA 1: REGISTRO ---
    with tab_registro:
        baixa_ativa = st.session_state.get('baixa_em_curso', None)
        tipo_selecionado = st.selectbox("O que deseja registrar?", list(CATEGORIAS.keys()))
        
        with st.form("form_registro", clear_on_submit=True):
            item_final = st.text_input("Item:", value=baixa_ativa['item']) if baixa_ativa else st.selectbox("Item:", CATEGORIAS[tipo_selecionado])
            c1, c2 = st.columns(2)
            v_real = c1.number_input("Valor Pago (R$)", min_value=0.0)
            km_reg = c2.number_input("KM Atual:", value=novo_km)
            litros = st.number_input("Litros (apenas para abastecimento):", min_value=0.0, step=0.1)

            if st.form_submit_button("💾 SALVAR NO LIVRO DE BORDO", use_container_width=True):
                novo_dado = {
                    "Data": agora.strftime("%Y-%m-%d"), "Tipo": tipo_selecionado, "Item": item_final, 
                    "KM": km_reg, "Real": float(v_real), "Litros": float(litros)
                }
                st.session_state.dados_spin['historico'].append(novo_dado)
                if baixa_ativa: 
                    st.session_state.dados_spin['inspecoes'].pop(baixa_ativa['index'])
                    del st.session_state['baixa_em_curso']
                db.salvar_dados_spin(st.session_state.dados_spin)
                st.success("✅ Registro efetuado!")
                st.rerun()

    df_base = pd.DataFrame(historico) if historico else pd.DataFrame()

    # --- ABA 2: SAÚDE ---
    with tab_saude:
        st.subheader("Estado dos Componentes")
        cols = st.columns(3)
        for idx, (peca, prazos) in enumerate(REGRAS_MANUTENCAO.items()):
            km_ut, data_ut = KM_REVISAO_GERAL, DATA_REVISAO_GERAL
            if not df_base.empty and peca in df_base['Item'].values:
                h = df_base[df_base['Item'] == peca].sort_values('KM', ascending=False)
                km_ut, data_ut = h['KM'].iloc[0], datetime.strptime(h['Data'].iloc[0], "%Y-%m-%d").replace(tzinfo=fuso_brasil)
            
            s_km = max(0, 100 - ((km_atual - km_ut) / prazos[0] * 100))
            s_t = max(0, 100 - ((agora - data_ut).days / (prazos[1] * 30) * 100))
            s_f = min(s_km, s_t)
            cor = "#ef4444" if s_f <= 20 else "#f59e0b" if s_f <= 50 else "#10b981"
            
            with cols[idx % 3]:
                st.markdown(f"<div class='card-componente {'critico' if s_f <= 20 else ''}' style='border-left: 5px solid {cor};'><b>{peca}</b><br><span style='color:{cor}; font-size:1.5em; font-weight:bold;'>{int(s_f)}%</span><br><small>Troca: {int(km_ut + prazos[0]):,} KM</small></div>", unsafe_allow_html=True)

    # --- ABA 5: FINANCEIRO (REMODELADA) ---
    with tab_financeiro:
        if not df_base.empty:
            # 1. PAINEL DE MANUTENÇÃO
            st.markdown("### 🛠️ Painel de Manutenção")
            df_maint = df_base[df_base['Tipo'].str.contains("Manutenção|Estética|Documentação")]
            col_m1, col_m2 = st.columns([1, 2])
            with col_m1:
                st.metric("Total em Manutenção", f"R$ {df_maint['Real'].sum():,.2f}")
                st.write("**Últimas Intervenções:**")
                st.dataframe(df_maint[['Data', 'Item', 'Real']].sort_values('Data', ascending=False).head(5), hide_index=True)
            with col_m2:
                fig_m = px.pie(df_maint, values='Real', names='Tipo', hole=.4, title="Distribuição de Gastos Técnicos")
                st.plotly_chart(fig_m, use_container_width=True)

            st.divider()

            # 2. PAINEL DE COMBUSTÍVEL
            st.markdown("### ⛽ Painel de Combustível")
            df_fuel = df_base[df_base['Tipo'] == "Abastecimento"]
            col_f1, col_f2 = st.columns([1, 2])
            with col_f1:
                total_comb = df_fuel['Real'].sum()
                st.metric("Gasto com Combustível", f"R$ {total_comb:,.2f}")
                if not df_fuel.empty:
                    st.metric("Média por Abastecimento", f"R$ {df_fuel['Real'].mean():,.2f}")
            with col_f2:
                if len(df_fuel) > 1:
                    fig_f = px.bar(df_fuel, x='Data', y='Real', color='Item', title="Histórico de Abastecimentos")
                    st.plotly_chart(fig_f, use_container_width=True)
                else:
                    st.info("Dados insuficientes para gráfico de combustível.")

            if st.button("🗑️ Deletar Último Registro"):
                st.session_state.dados_spin['historico'].pop()
                db.salvar_dados_spin(st.session_state.dados_spin)
                st.rerun()
        else:
            st.warning("Nenhum dado financeiro registrado ainda.")

    # --- ABA 3: EFICIÊNCIA ---
    with tab_eficiencia:
        if not df_base.empty and "Litros" in df_base.columns:
            df_kml = df_base[df_base['Tipo'] == "Abastecimento"].sort_values('KM')
            if len(df_kml) >= 2:
                df_kml['KML'] = df_kml['KM'].diff() / df_kml['Litros']
                st.plotly_chart(px.line(df_kml.dropna(), x='Data', y='KML', markers=True, title="Eficiência (KM/L)"), use_container_width=True)
            else: st.info("Abasteça pelo menos 2 vezes.")

    # --- ABA 4: INSPEÇÃO ---
    with tab_inspecao:
        with st.form("f_insp"):
            c1, c2 = st.columns(2)
            i_it, i_st = c1.text_input("Componente:"), c2.selectbox("Status:", ["✅ Bom", "⚠️ Observar", "🚨 Trocar"])
            i_obs = st.text_area("Notas Técnicas:")
            if st.form_submit_button("Salvar Inspeção"):
                st.session_state.dados_spin['inspecoes'].append({"Data": agora.strftime("%d/%m/%Y"), "Item": i_it, "Status": i_st, "Obs": i_obs, "KM": km_atual})
                db.salvar_dados_spin(st.session_state.dados_spin); st.rerun()
        for idx, i in enumerate(reversed(inspecoes)):
            st.write(f"**{i['Item']}** - {i['Status']} ({i['KM']} KM)")
            if st.button("💸 Resolver/Baixar", key=f"bx_{idx}"):
                st.session_state['baixa_em_curso'] = {'item': i['Item'], 'index': len(inspecoes)-1-idx}
                st.rerun()
