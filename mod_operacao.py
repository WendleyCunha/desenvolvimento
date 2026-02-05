import streamlit as st
import pandas as pd
import numpy as np  # Necessário para os cálculos de dimensionamento
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# =========================================================
# 1. CONFIGURAÇÕES E ESTILO
# =========================================================
PALETA = ['#002366', '#3b82f6', '#16a34a', '#ef4444', '#facc15']

def aplicar_estilo_premium():
    st.markdown(f"""
        <style>
        .main-card {{ background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .metric-box {{ background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }}
        .metric-box h3 {{ margin: 5px 0; font-size: 1.8rem; font-weight: bold; color: {PALETA[0]}; }}
        .search-box {{ background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .search-box-rec {{ background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[2]}; margin-bottom: 20px; }}
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 20px; }}
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "absenteismo": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

# =========================================================
# 2. COMPONENTES DE TRATATIVA (COMPRAS/RECEBIMENTO)
# =========================================================
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"; df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']; df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"; df_completo.at[index, 'QTD_SOLICITADA'] = 0; df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p; df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado: {item['QTD_SOLICITADA']}**")
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"; df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True
    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"; df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=int(item['QTD_SOLICITADA']), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"; df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 3. DASHBOARDS DE PERFORMANCE
# =========================================================
def renderizar_dashboards_compras_completo(df):
    if df.empty: return
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    itens_conferidos = len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    
    st.subheader("📊 Performance de Compras")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conferidos}</h3></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>COMPRAS OK</small><h3>{compras_ok}</h3></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st_counts = df['STATUS_COMPRA'].value_counts().reset_index()
        fig_p = px.pie(st_counts, values='count', names='STATUS_COMPRA', title="Decisões de Compra", hole=0.4)
        st.plotly_chart(fig_p, use_container_width=True)

# =========================================================
# 4. DASHBOARD DE PICOS E DIMENSIONAMENTO (COMPLETO)
# =========================================================

def renderizar_picos_operacional(db_picos):
    if not db_picos:
        st.info("💡 Sem dados de picos. Importe a planilha do Zendesk na aba CONFIGURAÇÕES."); return
    
    df = normalizar_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    st.markdown("### 📅 Filtro de Dias")
    dias_disponiveis = sorted(df['DATA'].unique())
    
    # Controle de seleção total
    if "todos_sel" not in st.session_state: st.session_state.todos_sel = True
    c_btn, c_sel = st.columns([1, 4])
    if c_btn.button("Marcar/Desmarcar Todos"): 
        st.session_state.todos_sel = not st.session_state.todos_sel
        st.rerun()
        
    dias_selecionados = c_sel.multiselect("Selecione os dias:", dias_disponiveis, 
                                          default=dias_disponiveis if st.session_state.todos_sel else [])
    
    if not dias_selecionados: return
    df_f = df[df['DATA'].isin(dias_selecionados)]
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    # --- 1. GRÁFICO DE TEMPERATURA (HEATMAP) ---
    st.markdown("#### 🔥 Mapa de Calor (Temperatura de Chamados)")
    cores_suaves = ["#ADD8E6", "#FFFFE0", "#FFD700", "#FF8C00", "#FF4500"]

    fig_heat = px.density_heatmap(
        df_f, 
        x="HORA", 
        y="DIA_SEMANA", 
        z="TICKETS", 
        category_orders={"DIA_SEMANA": ordem_dias},
        color_continuous_scale=cores_suaves, 
        text_auto=True,
        labels={'HORA': 'Hora do Dia', 'DIA_SEMANA': 'Dia da Semana', 'TICKETS': 'Volume'}
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # --- 2 e 3. GRÁFICOS DE BARRAS ---
    col1, col2 = st.columns(2)
    with col1:
        df_h = df_f.groupby('HORA')['TICKETS'].sum().reset_index()
        fig_h = px.bar(df_h, x='HORA', y='TICKETS', title="Volume Total por Hora", text_auto=True, color_discrete_sequence=[PALETA[0]])
        fig_h.update_traces(textposition='outside')
        st.plotly_chart(fig_h, use_container_width=True)
    with col2:
        df_d = df_f.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna()
        fig_d = px.bar(df_d, x='DIA_SEMANA', y='TICKETS', title="Volume Total por Dia", text_auto=True, color_discrete_sequence=[PALETA[1]])
        fig_d.update_traces(textposition='outside')
        st.plotly_chart(fig_d, use_container_width=True)

def renderizar_dimensionamento_abs(db_data, mes_ref):
    st.subheader("📏 Planejamento de Capacidade e ABS")
    t1, t2, t3 = st.tabs(["👥 Dimensionamento", "☕ Sugestão de Pausas", "🤒 Registro de ABS"])
    
    with t1:
        if not db_data.get("picos"):
            st.info("Importe a base de picos nas Configurações.")
        else:
            df_p = normalizar_picos(pd.DataFrame(db_data["picos"]))
            produtividade = st.number_input("Tickets por Atendente/Hora:", min_value=1, value=4)
            df_dim = df_p.groupby('HORA')['TICKETS'].mean().reset_index()
            # np.ceil garante que 1.1 atendentes vire 2
            df_dim['Atendentes Necessários'] = (df_dim['TICKETS'] / produtividade).apply(lambda x: int(np.ceil(x)))
            
            fig_dim = px.line(df_dim, x='HORA', y='Atendentes Necessários', text='Atendentes Necessários', title="Média de Staff Necessário por Hora", markers=True)
            st.plotly_chart(fig_dim, use_container_width=True)
            st.dataframe(df_dim, use_container_width=True, hide_index=True)

    with t2:
        if db_data.get("picos"):
            st.write("#### 💡 Horários Recomendados para Pausas")
            df_p = normalizar_picos(pd.DataFrame(db_data["picos"]))
            melhores_horas = df_p.groupby('HORA')['TICKETS'].mean().sort_values().head(4).index.tolist()
            cols = st.columns(len(melhores_horas))
            for i, hora in enumerate(melhores_horas):
                cols[i].success(f"🕒 {hora}:00")
        else: st.info("Dados de picos necessários.")

    with t3:
        if "absenteismo" not in db_data: db_data["absenteismo"] = []
        with st.form("form_abs", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 2, 1])
            dt = c1.date_input("Data")
            nome = c2.text_input("Colaborador")
            tp = c3.selectbox("Tipo", ["Falta", "Atraso", "Saída Antecipada", "Atestado"])
            obs = st.text_input("Observação")
            if st.form_submit_button("Registrar Ocorrência"):
                db_data["absenteismo"].append({
                    "DATA": dt.strftime("%d/%m/%Y"), 
                    "COLABORADOR": nome, 
                    "TIPO": tp,
                    "OBS": obs
                })
                salvar_dados_op(db_data, mes_ref)
                st.success("Registrado!")
                st.rerun()
        
        if db_data["absenteismo"]:
            st.write("#### Histórico")
            st.dataframe(pd.DataFrame(db_data["absenteismo"]), use_container_width=True)
            
# =========================================================
# 5. FUNÇÃO PRINCIPAL UNIFICADA
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    st.sidebar.title("📅 Gestão Mensal")
    mes_sel = st.sidebar.selectbox("Mês", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"], index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    # --- ABAS INTEGRADAS ---
    tab_compras, tab_picos, tab_dim, tab_config = st.tabs([
        "🛒 COMPRAS", "📊 DASH OPERAÇÃO", "📏 DIMENSIONAMENTO & ABS", "⚙️ CONFIGURAÇÕES"
    ])

    with tab_compras:
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        t_c1, t_c2, t_c3 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD"])
        with t_c1:
            if df_atual.empty: st.warning("Sem dados.")
            else:
                q = st.text_input("🔍 Localizar:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq_c")

        with t_c2:
            pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index() if not df_atual.empty else pd.DataFrame()
            if not pend_rec.empty:
                renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "main_r")
            else: st.success("✅ Tudo recebido.")

        with t_c3: renderizar_dashboards_compras_completo(df_atual)

    with tab_picos:
        renderizar_picos_operacional(db_data.get("picos", []))

    with tab_dim:
        renderizar_dimensionamento_abs(db_data, mes_ref)

    with tab_config:
        st.subheader("⚙️ Importação")
        up_c = st.file_uploader("Base Compras", type="xlsx")
        if up_c and st.button("Salvar Compras"):
            df_n = pd.read_excel(up_c)
            for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: df_n[c] = "Pendente" if "STATUS" in c else 0
            db_data["analises"] = df_n.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
            
        up_p = st.file_uploader("Base Picos", type="xlsx")
        if up_p and st.button("Salvar Picos"):
            db_data["picos"] = pd.read_excel(up_p).to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
