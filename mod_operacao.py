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
# =========================
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
def garantir_colunas(df):
    """Garante que o DataFrame possua todas as colunas necessárias para evitar KeyErrors"""
    cols_obrigatorias = {
        'STATUS_COMPRA': 'Pendente', 
        'QTD_SOLICITADA': 0, 
        'SALDO_FISICO': 0, 
        'QTD_RECEBIDA': 0, 
        'STATUS_RECEB': 'Pendente',
        'ORIGEM': 'Planilha',
        'CODIGO': 'S/C',
        'DESCRICAO': 'S/D'
    }
    for col, default in cols_obrigatorias.items():
        if col not in df.columns:
            df[col] = default
    return df

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    dados = doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}
    return dados

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

# --- FUNÇÃO PARA EXPORTAR EXCEL (AUDITORIA) ---
def gerar_excel_auditoria(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df[df['SALDO_FISICO'] > 0].to_excel(writer, sheet_name='COM ESTOQUE', index=False)
        df[df['SALDO_FISICO'] <= 0].to_excel(writer, sheet_name='RUPTURA', index=False)
        df[df.get('ORIGEM') == 'Manual'].to_excel(writer, sheet_name='ITENS MANUAIS', index=False)
    return output.getvalue()

# =========================================================
# 2. COMPONENTES DE TRATATIVA (COMPRAS/RECEBIMENTO)
# =========================================================
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item.get('QUANTIDADE', 0)}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"; df_completo.at[index, 'QTD_SOLICITADA'] = item.get('QUANTIDADE', 0); df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"; df_completo.at[index, 'QTD_SOLICITADA'] = 0; df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        max_v = int(item.get('QUANTIDADE', 1))
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=max_v if max_v > 0 else 1, key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p; df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado: {item.get('QTD_SOLICITADA', 0)}**")
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"; df_completo.at[index, 'QTD_RECEBIDA'] = item.get('QTD_SOLICITADA', 0)
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True
    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"; df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        max_r = int(item.get('QTD_SOLICITADA', 0))
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=max_r if max_r > 0 else 1, key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"; df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 3. DASHBOARDS DE PERFORMANCE (COMPRAS E RECEBIMENTO)
# =========================================================
def renderizar_dashboards_compras_completo(df):
    if df.empty or 'STATUS_COMPRA' not in df.columns: return
    total_itens = len(df)
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    itens_conferidos = len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    perc_conf = (itens_conferidos / total_itens * 100) if total_itens > 0 else 0
    perc_ok = (compras_ok / itens_conferidos * 100) if itens_conferidos > 0 else 0
    df_nao_efetuada = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
    nao_efet_com_estoque = df_nao_efetuada[df_nao_efetuada['SALDO_FISICO'] > 0]
    nao_efet_sem_estoque = df_nao_efetuada[df_nao_efetuada['SALDO_FISICO'] == 0]

    st.subheader("📊 Performance de Compras")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conferidos}</h3><p>{perc_conf:.1f}%</p></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>COMPRAS OK</small><h3>{compras_ok}</h3><p>{perc_ok:.1f}%</p></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>ESTRATÉGICO</small><h3 style='color:#16a34a;'>{len(nao_efet_com_estoque)}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>RUPTURA</small><h3 style='color:#ef4444;'>{len(nao_efet_sem_estoque)}</h3></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st_counts = df['STATUS_COMPRA'].value_counts().reset_index()
        st_counts.columns = ['Status', 'Qtd']
        fig_p = px.pie(st_counts, values='Qtd', names='Status', title="Decisões de Compra", hole=0.4, color='Status', color_discrete_map={'Total': '#002366', 'Parcial': '#3b82f6', 'Não Efetuada': '#ef4444', 'Pendente': '#cbd5e1'})
        st.plotly_chart(fig_p, use_container_width=True)
    with c2:
        fig_rup = go.Figure(data=[go.Bar(name='Com Estoque', x=['Não Efetuadas'], y=[len(nao_efet_com_estoque)], marker_color='#16a34a'), go.Bar(name='Sem Estoque', x=['Não Efetuadas'], y=[len(nao_efet_sem_estoque)], marker_color='#ef4444')])
        fig_rup.update_layout(title="Motivo das Não Encomendas", barmode='group', height=400); st.plotly_chart(fig_rup, use_container_width=True)

def renderizar_dashboards_recebimento_completo(df):
    if df.empty or 'QTD_SOLICITADA' not in df.columns: return
    df_f = df[df['QTD_SOLICITADA'] > 0]
    if df_f.empty: 
        st.info("Nenhuma compra aguardando recebimento."); return
    
    total_pedidos = len(df_f)
    df_proc = df_f[df_f['STATUS_RECEB'] != "Pendente"]
    itens_conf = len(df_proc)
    rec_total = len(df_proc[df_proc['STATUS_RECEB'] == "Recebido Total"])
    rec_parcial = len(df_proc[df_proc['STATUS_RECEB'].isin(["Recebido Parcial", "Faltou"])])
    perc_conf = (itens_conf / total_pedidos * 100) if total_pedidos > 0 else 0

    st.subheader("📊 Performance de Recebimento")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conf}</h3><p>{perc_conf:.1f}%</p></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>TOTAL OK</small><h3 style='color:#16a34a;'>{rec_total}</h3></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>DIVERGENTES</small><h3 style='color:#ef4444;'>{rec_parcial}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>PENDENTES</small><h3>{total_pedidos - itens_conf}</h3></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.pie(df_f, names='STATUS_RECEB', title="Status de Recebimento", hole=0.4, color='STATUS_RECEB', color_discrete_map={'Recebido Total': '#16a34a', 'Recebido Parcial': '#facc15', 'Faltou': '#ef4444', 'Pendente': '#cbd5e1'}), use_container_width=True)
    with c2:
        fig_ac = go.Figure()
        fig_ac.add_trace(go.Bar(name='Solicitado', x=df_f['CODIGO'][:15], y=df_f['QTD_SOLICITADA'][:15], marker_color=PALETA[0]))
        fig_ac.add_trace(go.Bar(name='Recebido', x=df_f['CODIGO'][:15], y=df_f['QTD_RECEBIDA'][:15], marker_color=PALETA[2]))
        fig_ac.update_layout(title="Acuracidade (Top 15 Itens)", barmode='group'); st.plotly_chart(fig_ac, use_container_width=True)

# =========================================================
# 4. DASHBOARD DE PICOS E DIMENSIONAMENTO (OPERACIONAL)
# =========================================================
def renderizar_picos_operacional(db_picos, db_data, mes_ref):
    if not db_picos:
        st.info("💡 Sem dados de picos. Importe a planilha do Zendesk na aba CONFIGURAÇÕES."); return
    
    tab_picos, tab_dim, tab_abs = st.tabs(["🔥 MAPA DE CALOR", "👥 DIMENSIONAMENTO", "📝 REGISTRO ABS"])
    df = normalizar_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    with tab_picos:
        dias_disponiveis = sorted(df['DATA'].unique())
        if "todos_sel" not in st.session_state: st.session_state.todos_sel = True
        c_btn, c_sel = st.columns([1, 4])
        if c_btn.button("Marcar/Desmarcar Todos"): st.session_state.todos_sel = not st.session_state.todos_sel; st.rerun()
        dias_selecionados = c_sel.multiselect("Selecione os dias:", dias_disponiveis, default=dias_disponiveis if st.session_state.todos_sel else [])
        
        if dias_selecionados:
            df_f = df[df['DATA'].isin(dias_selecionados)]
            fig_heat = px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias}, color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_heat, use_container_width=True)

    with tab_dim:
        st.subheader("👥 Cálculo de Dimensionamento")
        meta_hora = st.slider("Meta de Atendimentos por Hora/Colaborador:", min_value=1, max_value=20, value=4)
        if dias_selecionados:
            df_dim = df[df['DATA'].isin(dias_selecionados)].groupby('HORA')['TICKETS'].mean().reset_index()
            df_dim['STAFF'] = (df_dim['TICKETS'] / meta_hora).apply(lambda x: int(x) + 1 if x % 1 > 0 else int(x))
            st.plotly_chart(px.bar(df_dim, x='HORA', y='STAFF', title=f"Agentes Necessários (Meta: {meta_hora})", text_auto=True), use_container_width=True)

    with tab_abs:
        with st.form("form_abs", clear_on_submit=True):
            c_a1, c_a2, c_a3 = st.columns(3)
            if st.form_submit_button("Registrar Ocorrência"):
                # Lógica de salvar aqui...
                st.success("Registrado!"); st.rerun()
        if db_data.get("abs"): st.table(pd.DataFrame(db_data["abs"]))

# =========================================================
# 5. ESTRUTURA UNIFICADA
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    st.sidebar.title("📅 Gestão Mensal")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    # PROTEÇÃO: Garante que o DataFrame tenha as colunas necessárias ao carregar
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()
    df_atual = garantir_colunas(df_atual)

    tab_modulo_compras, tab_modulo_picos, tab_modulo_config = st.tabs(["🛒 COMPRAS", "📊 DASH OPERAÇÃO", "⚙️ CONFIGURAÇÕES"])

    with tab_modulo_compras:
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 DASHBOARD RECEBIMENTO"])
        
        with t1:
            if df_atual.empty: st.warning("Sem dados.")
            else:
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq_c")
                idx_s = db_data.get("idx_solic", 0)
                while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
                if idx_s < len(df_atual):
                    with st.container():
                        st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                        renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "main_c")
                        st.markdown("</div>", unsafe_allow_html=True)

        with t2:
            pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index() if not df_atual.empty else pd.DataFrame()
            if not pend_rec.empty:
                q_r = st.text_input("🔍 Localizar Recebimento:").upper()
                if q_r:
                    it_r = pend_rec[pend_rec['CODIGO'].astype(str).str.contains(q_r) | pend_rec['DESCRICAO'].astype(str).str.contains(q_r)]
                    for _, r in it_r.iterrows():
                        with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "bq_r")
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "main_r")
                st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Tudo recebido.")

        with t3: 
            renderizar_dashboards_compras_completo(df_atual)
            if not df_atual.empty:
                st.divider()
                st.subheader("🔍 Auditoria")
                excel_data = gerar_excel_auditoria(df_atual)
                st.download_button(label="📥 Baixar Excel da Auditoria", data=excel_data, file_name=f"Auditoria_{mes_ref}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                c_aud1, c_aud2 = st.columns(2)
                with c_aud1:
                    with st.expander("🟢 COM ESTOQUE"): st.dataframe(df_atual[df_atual['SALDO_FISICO'] > 0], use_container_width=True)
                with c_aud2:
                    with st.expander("🔴 RUPTURA"): st.dataframe(df_atual[df_atual['SALDO_FISICO'] <= 0], use_container_width=True)

        with t4: renderizar_dashboards_recebimento_completo(df_atual)

    with tab_modulo_picos: renderizar_picos_operacional(db_data.get("picos", []), db_data, mes_ref)

    with tab_modulo_config:
        st.subheader("⚙️ Importação e Resets")
        c_up1, c_up2 = st.columns(2)
        with c_up1:
            up_c = st.file_uploader("Upload Excel Compras", type="xlsx")
            if up_c and st.button("Salvar Compras"):
                df_n = pd.read_excel(up_c)
                df_n['ORIGEM'] = 'Planilha'
                db_data["analises"] = df_n.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
            if st.button("🗑️ Resetar Compras"):
                db_data["analises"] = []; db_data["idx_solic"] = 0; salvar_dados_op(db_data, mes_ref); st.rerun()
        with c_up2:
            up_p = st.file_uploader("Upload Excel Picos", type="xlsx")
            if up_p and st.button("Salvar Picos"):
                df_p = pd.read_excel(up_p)
                db_data["picos"] = df_p.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
