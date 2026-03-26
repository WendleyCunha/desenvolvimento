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

    # --- 3. CONFIGURAÇÕES TÉCNICAS (UPGRADE PERITO) ---
    # Referência: Revisão pesada feita aos 127k
    KM_REVISAO_GERAL = 127000 
    DATA_REVISAO_GERAL = datetime(2025, 1, 1, tzinfo=fuso_brasil)

    # REGRAS: [KM para Troca, Meses para Troca]
    REGRAS_MANUTENCAO = {
        "Óleo Motor (5W30)": [5000, 6],
        "Filtro de Óleo/Ar/Comb.": [10000, 12],
        "Velas de Ignição": [30000, 24],
        "Cabos de Vela": [40000, 36],
        "Correia Dentada/Tensor": [50000, 48],
        "Fluido de Câmbio (AT)": [40000, 24],
        "Líquido Arrefecimento": [30000, 24],
        "Fluido de Freio (DOT 4)": [20000, 12],
        "Pastilhas de Freio": [20000, 12],
        "Rodízio de Pneus": [10000, 12],
        "Amortecedores": [60000, 60],
        "Bateria": [0, 30] # Foco apenas em tempo
    }

    # --- 4. ESTILIZAÇÃO CSS AVANÇADA ---
    st.markdown(f"""
        <style>
        .relogio {{ background: #1e293b; padding: 12px; border-radius: 12px; text-align: right; font-family: 'Courier New', monospace; font-weight: bold; color: #60a5fa; margin-bottom: 25px; border: 1px solid #334155; }}
        .card-componente {{ padding: 15px; border-radius: 12px; margin-bottom: 12px; border: 1px solid #e2e8f0; background: white; }}
        .status-header {{ font-size: 0.85rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
        .progresso-bar {{ height: 8px; background: #f1f5f9; border-radius: 4px; margin-top: 8px; overflow: hidden; }}
        .progresso-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s ease-in-out; }}
        @keyframes pulse {{ 0% {{ box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }} 70% {{ box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }} 100% {{ box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }} }}
        .critico {{ border: 2px solid #ef4444 !important; animation: pulse 2s infinite; }}
        </style>
    """, unsafe_allow_html=True)

    st.markdown(f"<div class='relogio'>🛰️ TELEMETRIA SPIN | {data_hoje_str}</div>", unsafe_allow_html=True)

    CATEGORIAS = {
        "Manutenção: Motor": ["Óleo Motor (5W30)", "Filtro de Óleo/Ar/Comb.", "Velas de Ignição", "Cabos de Vela", "Líquido Arrefecimento", "Correia Dentada/Tensor"],
        "Manutenção: Chassi": ["Pastilhas de Freio", "Fluido de Freio (DOT 4)", "Amortecedores", "Rodízio de Pneus", "Suspensão/Buchas"],
        "Abastecimento": ["Gasolina", "Etanol", "GNV"],
        "Upgrade/Estética": ["Acessórios", "Lavagem", "Polimento"],
        "Documentação": ["IPVA", "Licenciamento", "Seguro"]
    }

    # --- 5. UI SIDEBAR ---
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/car-service.png", width=80)
        st.header("Painel de Controle")
        novo_km = st.number_input("Odômetro Atual:", value=km_atual, step=1)
        if novo_km != km_atual:
            st.session_state.dados_spin['km_atual'] = novo_km
            db.salvar_dados_spin(st.session_state.dados_spin)
            st.rerun()
        
        st.divider()
        st.info(f"**Meta:** Cuidar de cada parafuso da Spin 2013.")

    st.title("🚗 SpinGenius PRO")

    tab_registro, tab_saude, tab_eficiencia, tab_inspecao = st.tabs([
        "📝 Lançar Gasto", "🩺 Saúde da Spin", "📊 KM/L", "🔍 Checklist Perito"
    ])

    # --- ABA 1: REGISTRO ---
    with tab_registro:
        baixa_ativa = st.session_state.get('baixa_em_curso', None)
        if baixa_ativa: st.warning(f"Baixando item da inspeção: **{baixa_ativa['item']}**")
        
        col_cat, col_item = st.columns(2)
        tipo_selecionado = col_cat.selectbox("Categoria:", list(CATEGORIAS.keys()))
        itens_disponiveis = CATEGORIAS[tipo_selecionado]
        
        with st.form("form_registro", clear_on_submit=True):
            item_final = st.text_input("Item:", value=baixa_ativa['item']) if baixa_ativa else st.selectbox("Item:", itens_disponiveis)
            c1, c2, c3 = st.columns(3)
            v_real = c1.number_input("Valor Pago (R$)", min_value=0.0)
            km_reg = c2.number_input("KM na hora:", value=novo_km)
            litros = c3.number_input("Litros (se for posto):", min_value=0.0)

            if st.form_submit_button("💾 REGISTRAR NO HISTÓRICO", use_container_width=True):
                novo_dado = {
                    "Data": agora.strftime("%Y-%m-%d"), "Tipo": tipo_selecionado, "Item": item_final, 
                    "KM": km_reg, "Real": float(v_real), "Litros": float(litros)
                }
                st.session_state.dados_spin['historico'].append(novo_dado)
                if baixa_ativa: 
                    st.session_state.dados_spin['inspecoes'].pop(baixa_ativa['index'])
                    del st.session_state['baixa_em_curso']
                db.salvar_dados_spin(st.session_state.dados_spin)
                st.success("Dados salvos com sucesso!")
                st.rerun()

    # --- ABA 2: SAÚDE ---
    with tab_saude:
        df_h = pd.DataFrame(historico) if historico else pd.DataFrame()
        cols = st.columns(3)
        
        for idx, (peca, prazos) in enumerate(REGRAS_MANUTENCAO.items()):
            km_limite, meses_limite = prazos[0], prazos[1]
            km_ut, data_ut = KM_REVISAO_GERAL, DATA_REVISAO_GERAL
            
            if not df_h.empty and peca in df_h['Item'].values:
                h = df_h[df_h['Item'] == peca].sort_values('Data', ascending=False)
                km_ut = h['KM'].iloc[0]
                data_ut = datetime.strptime(h['Data'].iloc[0], "%Y-%m-%d").replace(tzinfo=fuso_brasil)
            
            # Cálculo de Saúde
            perc_km = 100 - ((km_atual - km_ut) / km_limite * 100) if km_limite > 0 else 100
            dias_uso = (agora - data_ut).days
            perc_tempo = 100 - (dias_uso / (meses_limite * 30) * 100)
            saude_final = max(0, min(perc_km, perc_tempo))
            
            # Definição de Cores
            cor = "#10b981" if saude_final > 50 else "#f59e0b" if saude_final > 20 else "#ef4444"
            is_critico = "critico" if saude_final <= 20 else ""
            
            prox_km = int(km_ut + km_limite) if km_limite > 0 else "N/A"

            with cols[idx % 3]:
                st.markdown(f"""
                    <div class='card-componente {is_critico}'>
                        <div class='status-header'>{peca}</div>
                        <div style='font-size: 1.5rem; font-weight: bold; color: {cor};'>{int(saude_final)}%</div>
                        <div class='progresso-bar'><div class='progresso-fill' style='width: {saude_final}%; background: {cor};'></div></div>
                        <div style='margin-top: 8px; font-size: 0.75rem; color: #64748b;'>
                            Próxima: <b>{prox_km} KM</b>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

    # --- ABA 3: EFICIÊNCIA ---
    with tab_eficiencia:
        if not df_h.empty and "Litros" in df_h.columns:
            df_fuel = df_h[df_h['Litros'] > 0].sort_values('KM').copy()
            if len(df_fuel) >= 2:
                df_fuel['KML'] = df_fuel['KM'].diff() / df_fuel['Litros']
                st.plotly_chart(px.area(df_fuel.dropna(subset=['KML']), x='Data', y='KML', title="Consumo Médio (km/l)", color_discrete_sequence=['#3b82f6']), use_container_width=True)
                st.metric("Eficiência Atual", f"{df_fuel['KML'].iloc[-1]:,.2f} km/l")
            else: st.info("Abasteça mais vezes para gerar o gráfico.")

    # --- ABA 4: INSPEÇÃO ---
    with tab_inspecao:
        st.subheader("Checklist de Perito")
        with st.expander("🔍 Nova Verificação"):
            with st.form("f_insp"):
                c1, c2 = st.columns(2)
                i_it = c1.text_input("O que está olhando?")
                i_st = c2.selectbox("Estado:", ["✅ Perfeito", "⚠️ Atenção", "🚨 Urgente"])
                i_obs = st.text_area("Detalhes (ex: barulho, vazamento, marca)")
                if st.form_submit_button("Registrar Inspeção"):
                    st.session_state.dados_spin['inspecoes'].append({"Data": agora.strftime("%d/%m/%Y"), "Item": i_it, "Status": i_st, "Obs": i_obs, "KM": km_atual})
                    db.salvar_dados_spin(st.session_state.dados_spin)
                    st.rerun()

        for i_idx, i in enumerate(reversed(inspecoes)):
            cor_s = {"✅ Perfeito": "green", "⚠️ Atenção": "orange", "🚨 Urgente": "red"}
            st.markdown(f"**{i['Item']}** - {i['Data']} | <span style='color:{cor_s[i['Status']]};'>{i['Status']}</span>", unsafe_allow_html=True)
            st.caption(f"Nota: {i['Obs']} | KM: {i['KM']}")
            if st.button("Baixar Manutenção", key=f"bx_{i_idx}"):
                st.session_state['baixa_em_curso'] = {'item': i['Item'], 'index': len(inspecoes)-1-i_idx}
                st.rerun()
            st.divider()
