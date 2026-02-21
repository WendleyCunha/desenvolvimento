import streamlit as st
import pandas as pd
import plotly.express as px # Para os gráficos financeiros
from datetime import datetime

def exibir_tamagotchi(user_info):
    # --- 1. CONFIGURAÇÃO DE ESTADO ---
    if 'km_atual' not in st.session_state: st.session_state.km_atual = 138000
    if 'historico' not in st.session_state:
        st.session_state.historico = [
            {"Data": "2024-01-10", "Tipo": "Manutenção", "Item": "Óleo do Motor (5W30)", "KM": 137000, "Custo": 250.0, "Litros": 0},
            {"Data": "2024-02-15", "Tipo": "Abastecimento", "Item": "Gasolina", "KM": 138000, "Custo": 200.0, "Litros": 40}
        ]

    # --- 2. REGRAS TÉCNICAS EXPANDIDAS (O MESTRE) ---
    PLANO_MESTRE = {
        "Óleo do Motor (5W30)": 5000,
        "Correia Dentada": 50000,
        "Fluido de Câmbio (GF6)": 40000,
        "Amortecedores (Kit 4)": 60000,
        "Óleo de Direção Hidráulica": 40000,
        "Bandejas e Buchas": 40000,
        "Fluido de Freio (DOT 4)": 20000,
        "Líquido Arrefecimento": 30000
    }

    # --- 3. SIDEBAR E ESTILO ---
    with st.sidebar:
        modo_escuro = st.toggle("🌙 Modo Noturno", value=True)
        st.subheader("📟 Atualizar Hodômetro")
        st.session_state.km_atual = st.number_input("KM Atual:", value=st.session_state.km_atual)

    bg, card, txt, sub, brd, blue = ("#0f172a", "#1e293b", "#f1f5f9", "#94a3b8", "#334155", "#0ea5e9") if modo_escuro else ("#f8fafc", "#ffffff", "#1e293b", "#64748b", "#e2e8f0", "#2563eb")
    
    st.markdown(f"<style>.stApp {{ background-color: {bg}; color: {txt}; }} .card-info {{ background: {card}; padding: 15px; border-radius: 10px; border: 1px solid {brd}; text-align: center; }}</style>", unsafe_allow_html=True)

    st.title("🚗 SpinGenius PRO: Gestão 360º")

    # --- 4. ABAS PRINCIPAIS ---
    tab_saude, tab_financas, tab_registro = st.tabs(["🩺 Saúde & KM", "💰 Painel Financeiro", "📝 Lançar Gasto"])

    # --- ABA 1: SAÚDE (TERMÔMETROS) ---
    with tab_saude:
        c1, c2, c3 = st.columns(3)
        # Lógica de cálculo simplificada para o exemplo
        for item, km_max in list(PLANO_MESTRE.items())[:3]: # Mostra os 3 principais no topo
            ultima = next((h for h in reversed(st.session_state.historico) if h['Item'] == item), None)
            km_rodado = st.session_state.km_atual - (ultima['KM'] if ultima else 0)
            perc = max(0, 100 - (km_rodado / km_max * 100))
            c1.markdown(f'<div class="card-info"><b>{item}</b><h2>{int(perc)}%</h2></div>', unsafe_allow_html=True)
        
        st.subheader("📋 Status Geral de Componentes")
        status_data = []
        for item, km_max in PLANO_MESTRE.items():
            ultima = next((h for h in reversed(st.session_state.historico) if h['Item'] == item), None)
            km_restante = km_max - (st.session_state.km_atual - (ultima['KM'] if ultima else 0))
            status_data.append({"Componente": item, "KM Restante": km_restante, "Status": "✅ OK" if km_restante > 1000 else "⚠️ Revisar"})
        st.table(pd.DataFrame(status_data))

    # --- ABA 2: FINANCEIRO (ONDE ESTÁ O DINHEIRO?) ---
    with tab_financas:
        df = pd.DataFrame(st.session_state.historico)
        df['Data'] = pd.to_datetime(df['Data'])
        
        col_f1, col_f2 = st.columns(2)
        total_gasto = df['Custo'].sum()
        col_f1.metric("Gasto Total Acumulado", f"R$ {total_gasto:,.2f}")
        
        # Gráfico de Pizza: Onde o dinheiro está indo
        fig_pizza = px.pie(df, values='Custo', names='Tipo', title="Distribuição de Gastos", hole=.4)
        st.plotly_chart(fig_pizza, use_container_width=True)
        
        st.subheader("📈 Gastos por Mês")
        df['Mes_Ano'] = df['Data'].dt.to_period('M').astype(str)
        gasto_mensal = df.groupby('Mes_Ano')['Custo'].sum().reset_index()
        fig_barra = px.bar(gasto_mensal, x='Mes_Ano', y='Custo', title="Evolução Mensal (R$)", color_discrete_sequence=[blue])
        st.plotly_chart(fig_barra, use_container_width=True)

    # --- ABA 3: REGISTRO (O GATILHO) ---
    with tab_registro:
        with st.form("novo_registro"):
            tipo = st.selectbox("Tipo de Gasto:", ["Manutenção", "Abastecimento", "Estética (Pintura/Polimento)", "Imposto/Seguro", "Outros"])
            
            if tipo == "Manutenção":
                item = st.selectbox("O que foi feito?", list(PLANO_MESTRE.keys()) + ["Outro Reparo"])
            else:
                item = st.text_input("Descrição (ex: Gasolina, Polimento Cristalizado, IPVA)")
            
            c_v, c_k, c_l = st.columns(3)
            valor = c_v.number_input("Valor Pago (R$)", min_value=0.0)
            km_no_ato = c_k.number_input("KM no Painel:", value=st.session_state.km_atual)
            litros = c_l.number_input("Litros (Só p/ Abastecimento)", min_value=0.0)
            
            if st.form_submit_button("Confirmar Lançamento"):
                # Lógica de Abastecimento (Calcula Consumo)
                if tipo == "Abastecimento" and litros > 0:
                    ultimo_km = next((h['KM'] for h in reversed(st.session_state.historico) if h['Tipo'] == 'Abastecimento'), km_no_ato)
                    distancia = km_no_ato - ultimo_km
                    if distancia > 0:
                        consumo = distancia / litros
                        st.toast(f"Consumo calculado: {consumo:.2f} km/l", icon="⛽")
                
                novo_reg = {
                    "Data": datetime.now().strftime("%Y-%m-%d"),
                    "Tipo": tipo,
                    "Item": item,
                    "KM": km_no_ato,
                    "Custo": valor,
                    "Litros": litros
                }
                st.session_state.historico.append(novo_reg)
                st.session_state.km_atual = km_no_ato
                st.success("Gasto registrado e dashboard atualizado!")
                st.rerun()

    # --- LISTAGEM FINAL ---
    st.divider()
    st.subheader("📋 Últimos Lançamentos")
    st.dataframe(pd.DataFrame(st.session_state.historico).sort_index(ascending=False), use_container_width=True)
