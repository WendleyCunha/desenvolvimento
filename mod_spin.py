import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def exibir_tamagotchi(user_info):
    # --- 1. BASE DE CONHECIMENTO MESTRE (REGRESTRAS TÉCNICAS) ---
    # Definição dos intervalos recomendados por especialistas e manual
    PLANO_MESTRE = {
        "Óleo do Motor (5W30)": {"km": 5000, "meses": 6, "critico": True},
        "Correia Dentada/Esticador": {"km": 50000, "meses": 36, "critico": True},
        "Fluido de Câmbio (GF6)": {"km": 40000, "meses": 48, "critico": True},
        "Fluido de Freio (DOT 4)": {"km": 20000, "meses": 24, "critico": False},
        "Líquido Arrefecimento": {"km": 30000, "meses": 24, "critico": True},
        "Velas e Cabos": {"km": 30000, "meses": 0, "critico": False},
        "Filtro de Combustível": {"km": 10000, "meses": 12, "critico": False}
    }

    # --- 2. GESTÃO DE ESTADO (PERSISTÊNCIA) ---
    if 'km_atual' not in st.session_state: st.session_state.km_atual = 138000
    if 'historico' not in st.session_state:
        # Simulando uma base inicial com a última troca de óleo
        st.session_state.historico = [
            {"Data": "01/01/2026", "KM": 138000, "Serviço": "Troca de Óleo e Filtros", "Custo": 280.00}
        ]

    # --- 3. CONFIGURAÇÃO DE INTERFACE ---
    with st.sidebar:
        st.header("⚙️ Configurações")
        modo_escuro = st.toggle("🌙 Modo Noturno", value=True)
        st.divider()
        st.subheader("📟 Atualizar Hodômetro")
        novo_km = st.number_input("KM Atual no Painel:", value=st.session_state.km_atual, step=10)
        if novo_km != st.session_state.km_atual:
            st.session_state.km_atual = novo_km
            st.rerun()

    # CSS Dinâmico conforme modo
    bg, card, txt, sub, brd, blue = ("#0f172a", "#1e293b", "#f1f5f9", "#94a3b8", "#334155", "#0ea5e9") if modo_escuro else ("#f8fafc", "#ffffff", "#1e293b", "#64748b", "#e2e8f0", "#2563eb")
    
    st.markdown(f"""<style>
        .stApp {{ background-color: {bg}; color: {txt}; }}
        .card-container {{ background: {card}; padding: 20px; border-radius: 15px; border: 1px solid {brd}; text-align: center; }}
        .thermo-container {{ width: 35px; height: 100px; background: {brd}; border-radius: 20px; margin: 0 auto; position: relative; overflow: hidden; }}
        .thermo-fill {{ position: absolute; bottom: 0; width: 100%; transition: height 0.5s; }}
    </style>""", unsafe_allow_html=True)

    # --- 4. CÁLCULO DE SAÚDE REAL ---
    # Analisamos o histórico para ver quando foi a última manutenção de cada item
    saude_itens = {}
    for item, regras in PLANO_MESTRE.items():
        # Busca a última vez que esse serviço foi feito no histórico
        ultima = next((h for h in reversed(st.session_state.historico) if item in h['Serviço']), None)
        
        if ultima:
            km_rodado = st.session_state.km_atual - ultima['KM']
            perc_km = max(0, 100 - (km_rodado / regras['km'] * 100))
            saude_itens[item] = perc_km
        else:
            saude_itens[item] = 0 # Nunca feito ou não registrado

    saude_geral = sum(saude_itens.values()) / len(saude_itens)
    cor_saude = "#22c55e" if saude_geral > 75 else "#eab308" if saude_geral > 40 else "#ef4444"

    # --- 5. DASHBOARD ---
    st.title("🚗 SpinGenius: Especialista")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="card-container"><p style="color:{sub};">Saúde Geral</p><h2 style="color:{cor_saude};">{int(saude_geral)}%</h2>'
                    f'<div style="background:{brd}; height:8px; width:100%; border-radius:10px;"><div style="background:{cor_saude}; width:{saude_geral}%; height:100%; border-radius:10px;"></div></div></div>', unsafe_allow_html=True)
    with c2:
        perc_cambio = saude_itens.get("Fluido de Câmbio (GF6)", 0)
        st.markdown(f'<div class="card-container"><p style="color:{sub};">Vida do Câmbio</p>'
                    f'<div class="thermo-container"><div class="thermo-fill" style="height:{perc_cambio}%; background:#3b82f6;"></div></div><h4 style="color:#3b82f6;">{int(perc_cambio)}%</h4></div>', unsafe_allow_html=True)
    with c3:
        perc_oleo = saude_itens.get("Óleo do Motor (5W30)", 0)
        st.markdown(f'<div class="card-container"><p style="color:{sub};">Vida do Óleo</p>'
                    f'<div class="thermo-container"><div class="thermo-fill" style="height:{perc_oleo}%; background:#22c55e;"></div></div><h4 style="color:#22c55e;">{int(perc_oleo)}%</h4></div>', unsafe_allow_html=True)

    # --- 6. O CÉREBRO: TAREFAS E PENDÊNCIAS ---
    t1, t2, t3 = st.tabs(["📋 Pendências Atuais", "📅 Cronograma 10 Anos", "🧞 Dicas de Gênio"])

    with t1:
        st.subheader("O que fazer agora?")
        pendencias = []
        for item, saude in saude_itens.items():
            if saude < 20:
                pendencias.append({"Prioridade": "🚨 CRÍTICA", "Tarefa": f"Trocar/Revisar {item}", "Motivo": "Prazo vencido ou próximo"})
            elif saude < 50:
                pendencias.append({"Prioridade": "⚠️ AVISO", "Tarefa": f"Providenciar {item}", "Motivo": "Metade da vida útil"})
        
        if pendencias:
            st.table(pd.DataFrame(pendencias))
        else:
            st.success("Tudo em dia! Nenhuma pendência crítica encontrada.")

    with t2:
        st.subheader("Plano Preventivo (Baseado em KM)")
        cronograma = []
        for item, regras in PLANO_MESTRE.items():
            ultima_km = next((h['KM'] for h in reversed(st.session_state.historico) if item in h['Serviço']), st.session_state.km_atual - regras['km'])
            proxima_km = ultima_km + regras['km']
            cronograma.append({
                "Item": item,
                "Última vez (KM)": ultima_km,
                "Próxima (KM)": proxima_km,
                "Faltam (KM)": proxima_km - st.session_state.km_atual
            })
        st.dataframe(pd.DataFrame(cronograma), use_container_width=True)

    with t3:
        st.markdown(f"### 🧞 Sabedoria para sua Spin 2013")
        with st.expander("📍 Sobre o Câmbio Automático"):
            st.write("Seu câmbio é o 6T30 (GF6). Ele não tolera óleo sujo. Se sentir um tranco da 2ª para a 3ª, não espere: faça a troca parcial de 4 ou 5 litros de Dexron VI.")
        with st.expander("📍 Sobre o Arrefecimento"):
            st.write("A tampa do reservatório de expansão deve ser original. Se ela falhar, a pressão sobe e estoura as mangueiras. Troque a tampa a cada 2 anos preventivamente.")
        with st.expander("📍 Barulhos na Suspensão"):
            st.write("Barulho de 'castanhola' em ruas irregulares? 90% de chance de serem as Bieletas. Peça barata e resolve o conforto na hora.")

    # --- 7. REGISTRO DE MANUTENÇÃO (O GATILHO) ---
    st.divider()
    st.subheader("📑 Registrar Nova Manutenção")
    with st.form("registro_servico"):
        c_a, c_b, c_c = st.columns([2, 1, 1])
        servico_nome = c_a.selectbox("Selecione o Item:", list(PLANO_MESTRE.keys()) + ["Outros/Reparo Extra"])
        valor = c_b.number_input("Custo (R$)", min_value=0.0)
        km_registro = c_c.number_input("KM no Painel:", value=st.session_state.km_atual)
        
        obs = st.text_input("Observações (ex: Marca das peças, nome da oficina)")
        
        if st.form_submit_button("💾 Salvar Manutenção e Atualizar Saúde"):
            novo_reg = {"Data": datetime.now().strftime("%d/%m/%Y"), "KM": km_registro, "Serviço": servico_nome, "Custo": valor, "Obs": obs}
            st.session_state.historico.append(novo_reg)
            st.session_state.km_atual = km_registro
            st.toast(f"Saúde do item {servico_nome} restaurada!", icon="🛠️")
            st.rerun()

    st.write("### Histórico Completo")
    st.dataframe(pd.DataFrame(st.session_state.historico), use_container_width=True)
