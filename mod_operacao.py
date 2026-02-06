import streamlit as st
import pandas as pd
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
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 20px; }}
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    dados = doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}
    return garantir_colunas(dados)

def garantir_colunas(dados):
    colunas_obrigatorias = {
        'STATUS_COMPRA': 'Pendente', 'QTD_SOLICITADA': 0, 'SALDO_FISICO': 0,
        'STATUS_RECEB': 'Pendente', 'QTD_RECEBIDA': 0, 'ORIGEM': 'Planilha'
    }
    if dados.get("analises"):
        df = pd.DataFrame(dados["analises"])
        for col, default in colunas_obrigatorias.items():
            if col not in df.columns: df[col] = default
        dados["analises"] = df.to_dict(orient='records')
    return dados

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

# =========================================================
# 2. COMPONENTES DE TRATATIVA
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
# 3. DASHBOARDS (SIMÉTRICOS)
# =========================================================
def renderizar_dashboards_compras_completo(df):
    if df.empty: return
    total_itens = len(df)
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    itens_conf = len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    perc_conf = (itens_conf / total_itens * 100) if total_itens > 0 else 0
    df_nao = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
    
    st.subheader("📊 Performance de Compras")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conf}</h3><p>{perc_conf:.1f}%</p></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>COMPRAS OK</small><h3>{compras_ok}</h3></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>ESTRATEGICO</small><h3 style='color:#16a34a;'>{len(df_nao[df_nao['SALDO_FISICO'] > 0])}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>RUPTURA</small><h3 style='color:#ef4444;'>{len(df_nao[df_nao['SALDO_FISICO'] <= 0])}</h3></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.pie(df, names='STATUS_COMPRA', title="Decisões de Compra", hole=0.4, color='STATUS_COMPRA', color_discrete_map={'Total': '#002366', 'Parcial': '#3b82f6', 'Não Efetuada': '#ef4444', 'Pendente': '#cbd5e1'}), use_container_width=True)
    with c2:
        fig_rup = go.Figure(data=[go.Bar(name='Com Estoque', x=['Não Efetuadas'], y=[len(df_nao[df_nao['SALDO_FISICO'] > 0])], marker_color='#16a34a'), go.Bar(name='Sem Estoque', x=['Não Efetuadas'], y=[len(df_nao[df_nao['SALDO_FISICO'] <= 0])], marker_color='#ef4444')])
        fig_rup.update_layout(title="Motivo das Não Encomendas", barmode='group'); st.plotly_chart(fig_rup, use_container_width=True)

def renderizar_dashboards_recebimento_completo(df):
    # Filtra apenas o que foi solicitado na compra (solicitada > 0)
    df_f = df[df['QTD_SOLICITADA'] > 0]
    if df_f.empty: 
        st.info("Nenhuma compra solicitada para este mês."); return
    
    total_pedidos = len(df_f)
    df_proc = df_f[df_f['STATUS_RECEB'] != "Pendente"]
    itens_conferidos = len(df_proc)
    recebidos_ok = len(df_proc[df_proc['STATUS_RECEB'] == "Recebido Total"])
    divergentes = len(df_proc[df_proc['STATUS_RECEB'].isin(["Recebido Parcial", "Faltou"])])
    perc_conf = (itens_conferidos / total_pedidos * 100) if total_pedidos > 0 else 0
    
    st.subheader("📊 Performance de Recebimento")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conferidos}</h3><p>{perc_conf:.1f}%</p></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>TOTAL OK</small><h3 style='color:#16a34a;'>{recebidos_ok}</h3></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>DIVERGENTES</small><h3 style='color:#ef4444;'>{divergentes}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>PENDENTES</small><h3>{total_pedidos - itens_conferidos}</h3></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.pie(df_f, names='STATUS_RECEB', title="Status de Recebimento", hole=0.4, color='STATUS_RECEB', color_discrete_map={'Recebido Total': '#16a34a', 'Recebido Parcial': '#facc15', 'Faltou': '#ef4444', 'Pendente': '#cbd5e1'}), use_container_width=True)
    with c2:
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(name='Solicitado', x=df_f['CODIGO'][:15], y=df_f['QTD_SOLICITADA'][:15], marker_color=PALETA[0]))
        fig_comp.add_trace(go.Bar(name='Recebido', x=df_f['CODIGO'][:15], y=df_f['QTD_RECEBIDA'][:15], marker_color=PALETA[2]))
        fig_comp.update_layout(title="Acuracidade (Top 15 Itens)", barmode='group'); st.plotly_chart(fig_comp, use_container_width=True)

# =========================================================
# 4. DASH OPERAÇÃO
# =========================================================
def renderizar_picos_operacional(db_picos, db_data, mes_ref):
    if not db_picos: st.info("💡 Sem dados de picos."); return
    tab_picos, tab_dim, tab_abs = st.tabs(["🔥 MAPA DE CALOR", "👥 DIMENSIONAMENTO", "📝 REGISTRO ABS"])
    df = normalizar_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    with tab_picos:
        dias_sel = st.multiselect("Dias:", sorted(df['DATA'].unique()), default=sorted(df['DATA'].unique()))
        if dias_sel:
            df_f = df[df['DATA'].isin(dias_sel)]
            st.plotly_chart(px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias}, color_continuous_scale="Viridis", text_auto=True), use_container_width=True)
            c1, c2 = st.columns(2)
            c1.plotly_chart(px.bar(df_f.groupby('HORA')['TICKETS'].sum().reset_index(), x='HORA', y='TICKETS', title="Por Hora", color_discrete_sequence=[PALETA[0]]), use_container_width=True)
            c2.plotly_chart(px.bar(df_f.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna(), x='DIA_SEMANA', y='TICKETS', title="Por Dia", color_discrete_sequence=[PALETA[1]]), use_container_width=True)

    with tab_dim:
        meta = st.slider("Atendimentos por Hora/Colaborador:", 1, 20, 4)
        if dias_sel:
            df_dim = df[df['DATA'].isin(dias_sel)].groupby('HORA')['TICKETS'].mean().reset_index()
            df_dim['STAFF'] = (df_dim['TICKETS'] / meta).apply(lambda x: int(x) + 1 if x % 1 > 0 else int(x))
            st.plotly_chart(px.bar(df_dim, x='HORA', y='STAFF', text='STAFF', title=f"Necessidade de Staff (Meta: {meta})", color_discrete_sequence=[PALETA[1]]), use_container_width=True)

    with tab_abs:
        with st.form("abs_f"):
            ca1, ca2, ca3 = st.columns(3)
            d_abs, t_abs, n_abs = ca1.date_input("Data"), ca2.selectbox("Tipo", ["Falta", "Atraso", "Atestado"]), ca3.text_input("Nome")
            if st.form_submit_button("Registrar"):
                if "abs" not in db_data: db_data["abs"] = []
                db_data["abs"].append({"data": str(d_abs), "tipo": t_abs, "nome": n_abs.upper()})
                salvar_dados_op(db_data, mes_ref); st.rerun()
        if db_data.get("abs"): st.table(pd.DataFrame(db_data["abs"]))

# =========================================================
# 5. ESTRUTURA MAIN
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    st.sidebar.title("📅 Gestão")
    mes_sel = st.sidebar.selectbox("Mês", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"], index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    tab_compras, tab_opera, tab_config = st.tabs(["🛒 COMPRAS/REC", "📊 OPERAÇÃO", "⚙️ CONFIG"])

    with tab_compras:
        st.markdown(f"<div class='header-analise'>FLUXO DE MERCADORIAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASH COMPRAS", "📈 DASH RECEBIMENTO"])
        
        with t1:
            if df_atual.empty: st.warning("Sem dados.")
            else:
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    for i, r in df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)].iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq_c")
                idx_s = db_data.get("idx_solic", 0)
                while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
                if idx_s < len(df_atual):
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "main_c")
                    st.markdown("</div>", unsafe_allow_html=True)

        with t2:
            pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index() if not df_atual.empty else pd.DataFrame()
            if not pend_rec.empty:
                q_r = st.text_input("🔍 Localizar Receb:").upper()
                if q_r:
                    for _, r in pend_rec[pend_rec['CODIGO'].astype(str).str.contains(q_r) | pend_rec['DESCRICAO'].astype(str).str.contains(q_r)].iterrows():
                        with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "bq_r")
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "main_r")
                st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Tudo recebido.")

        with t3: renderizar_dashboards_compras_completo(df_atual)
        with t4: renderizar_dashboards_recebimento_completo(df_atual)

    with tab_opera: renderizar_picos_operacional(db_data.get("picos", []), db_data, mes_ref)

    with tab_config:
        with st.container(border=True):
            st.subheader("🆕 Cadastro Manual")
            with st.form("cad_m"):
                m1, m2, m3 = st.columns([1,2,1])
                c_cod = m1.text_input("Cód"); c_des = m2.text_input("Desc"); c_qtd = m3.number_input("Qtd", 1)
                if st.form_submit_button("Adicionar"):
                    novo = {"CODIGO": c_cod, "DESCRICAO": c_des, "QUANTIDADE": c_qtd, "ORIGEM": "Manual", "STATUS_COMPRA": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "STATUS_RECEB": "Pendente", "QTD_RECEBIDA": 0}
                    df_atual = pd.concat([df_atual, pd.DataFrame([novo])], ignore_index=True)
                    db_data["analises"] = df_atual.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            up_c = st.file_uploader("Excel Compras", type="xlsx")
            if up_c and st.button("Salvar Compras"):
                df_n = pd.read_excel(up_c); df_n['ORIGEM'] = 'Planilha'
                db_data["analises"] = df_n.to_dict(orient='records'); db_data = garantir_colunas(db_data); salvar_dados_op(db_data, mes_ref); st.rerun()
            if st.button("🗑️ Reset Compras"): db_data["analises"] = []; salvar_dados_op(db_data, mes_ref); st.rerun()
        with c2:
            up_p = st.file_uploader("Excel Picos", type="xlsx")
            if up_p and st.button("Salvar Picos"):
                db_data["picos"] = pd.read_excel(up_p).to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
            if st.button("🗑️ Reset Picos"): db_data["picos"] = []; salvar_dados_op(db_data, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
