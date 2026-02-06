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
        .search-box {{ background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .search-box-rec {{ background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[2]}; margin-bottom: 20px; }}
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 20px; }}
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    # Adicionado "abs" e "dimensionamento" à estrutura inicial
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Auditoria')
    return output.getvalue()

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
# 3. DASHBOARDS DE PERFORMANCE (COMPRAS)
# =========================================================
def renderizar_dashboards_compras_completo(df):
    if df.empty: return
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
    if df.empty:
        st.info("Aguardando dados para análise.")
        return

    df_rec = df[df['QTD_SOLICITADA'] > 0].copy()
    
    if df_rec.empty:
        st.warning("Nenhum item foi marcado como 'Comprado' ainda.")
        return

    total_pedidos = len(df_rec)
    recebidos_full = len(df_rec[df_rec['STATUS_RECEB'] == "Recebido Total"])
    recebidos_parc = len(df_rec[df_rec['STATUS_RECEB'] == "Recebido Parcial"])
    pendentes = len(df_rec[df_rec['STATUS_RECEB'] == "Pendente"])
    faltou = len(df_rec[df_rec['STATUS_RECEB'] == "Faltou"])

    st.subheader("📊 Performance de Recebimento")
    
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>PEDIDOS</small><h3>{total_pedidos}</h3></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>OK / PARCIAL</small><h3 style='color:{PALETA[2]};'>{recebidos_full + recebidos_parc}</h3></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>PENDENTES</small><h3 style='color:{PALETA[4]};'>{pendentes}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>DIVERGENTES</small><h3 style='color:{PALETA[3]};'>{faltou}</h3></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st_counts = df_rec['STATUS_RECEB'].value_counts().reset_index()
        st_counts.columns = ['Status', 'Qtd']
        fig_p = px.pie(st_counts, values='Qtd', names='Status', title="Status de Recebimento", hole=0.4,
                     color='Status', color_discrete_map={
                         'Recebido Total': '#16a34a', 
                         'Recebido Parcial': '#3b82f6', 
                         'Faltou': '#ef4444', 
                         'Pendente': '#cbd5e1'})
        st.plotly_chart(fig_p, use_container_width=True)
    
    with c2:
        fig_comp = px.bar(df_rec, x='CODIGO', y=['QTD_SOLICITADA', 'QTD_RECEBIDA'], 
                         barmode='group', title="Pedido vs Recebido",
                         color_discrete_sequence=[PALETA[0], PALETA[2]])
        st.plotly_chart(fig_comp, use_container_width=True)

    st.divider()
    st.subheader("🔍 Auditoria de Recebimento")
    
    escolha = st.radio("Filtrar lista para exportação:", 
                      ["Todos Encomendados", "Apenas Pendentes", "Divergências (Faltou)"], 
                      horizontal=True)
    
    df_export = df_rec.copy()
    if escolha == "Apenas Pendentes":
        df_export = df_rec[df_rec['STATUS_RECEB'] == "Pendente"]
    elif escolha == "Divergências (Faltou)":
        df_export = df_rec[df_rec['STATUS_RECEB'] == "Faltou"]

    st.dataframe(df_export, use_container_width=True)
    
    btn_xlsx = to_excel(df_export)
    st.download_button(label="📥 Exportar Lista (Excel)", 
                       data=btn_xlsx, 
                       file_name=f"auditoria_recebimento_{datetime.now().strftime('%d_%m')}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# =========================================================
# 4. DASHBOARD DE PICOS E DIMENSIONAMENTO (OPERACIONAL)
# =========================================================
def renderizar_picos_operacional(db_picos, db_data, mes_ref):
    if not db_picos:
        st.info("💡 Sem dados de picos. Importe a planilha do Zendesk na aba CONFIGURAÇÕES."); return
    
    # NOVAS SUB-ABAS DENTRO DE DASH OPERAÇÃO
    tab_picos, tab_dim, tab_abs = st.tabs(["🔥 MAPA DE CALOR", "👥 DIMENSIONAMENTO", "📝 REGISTRO ABS"])

    df = normalizar_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    with tab_picos:
        st.markdown("### 📅 Filtro de Dias")
        dias_disponiveis = sorted(df['DATA'].unique())
        if "todos_sel" not in st.session_state: st.session_state.todos_sel = True
        c_btn, c_sel = st.columns([1, 4])
        if c_btn.button("Marcar/Desmarcar Todos"): st.session_state.todos_sel = not st.session_state.todos_sel; st.rerun()
        dias_selecionados = c_sel.multiselect("Selecione os dias:", dias_disponiveis, default=dias_disponiveis if st.session_state.todos_sel else [])
        
        if dias_selecionados:
            df_f = df[df['DATA'].isin(dias_selecionados)]
            cores_suaves = ["#ADD8E6", "#FFFFE0", "#FFD700", "#FF8C00", "#FF4500"]
            fig_heat = px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias},
                                        color_continuous_scale=cores_suaves, text_auto=True)
            st.plotly_chart(fig_heat, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                df_h = df_f.groupby('HORA')['TICKETS'].sum().reset_index()
                st.plotly_chart(px.bar(df_h, x='HORA', y='TICKETS', title="Volume Total por Hora", text_auto=True, color_discrete_sequence=[PALETA[0]]), use_container_width=True)
            with col2:
                df_d = df_f.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna()
                st.plotly_chart(px.bar(df_d, x='DIA_SEMANA', y='TICKETS', title="Volume Total por Dia", text_auto=True, color_discrete_sequence=[PALETA[1]]), use_container_width=True)

    with tab_dim:
        st.subheader("👥 Cálculo de Dimensionamento")
        st.info("Regra aplicada: 4 Atendimentos por Hora/Colaborador")
        
        if dias_selecionados:
            df_dim = df[df['DATA'].isin(dias_selecionados)].groupby('HORA')['TICKETS'].mean().reset_index()
            # Cálculo de Agentes: Arredonda para cima pois não existe meio agente
            df_dim['AGENTES_NECESSARIOS'] = (df_dim['TICKETS'] / 4).apply(lambda x: int(x) + 1 if x % 1 > 0 else int(x))
            
            fig_dim = px.line(df_dim, x='HORA', y='AGENTES_NECESSARIOS', title="Necessidade de Staff por Hora (Média)", markers=True)
            fig_dim.add_bar(x=df_dim['HORA'], y=df_dim['AGENTES_NECESSARIOS'], name="Agentes")
            st.plotly_chart(fig_dim, use_container_width=True)

            st.divider()
            st.subheader("☕ Sugestão de Pausas")
            # Identifica os 3 horários com menor volume médio para sugerir saídas
            melhores_pausas = df_dim.sort_values(by='TICKETS').head(3)
            st.write("Baseado no menor volume médio, sugerimos saídas nos horários:")
            p_cols = st.columns(3)
            for i, (idx, row) in enumerate(melhores_pausas.iterrows()):
                p_cols[i].markdown(f"<div class='metric-box'><small>{i+1}ª OPÇÃO</small><h3>{int(row['HORA'])}:00</h3></div>", unsafe_allow_html=True)

    with tab_abs:
        st.subheader("📝 Controle de ABS (Faltas e Atrasos)")
        with st.form("form_abs", clear_on_submit=True):
            c_a1, c_a2, c_a3 = st.columns(3)
            data_abs = c_a1.date_input("Data", value=datetime.now())
            tipo_abs = c_a2.selectbox("Tipo", ["Falta", "Atraso", "Saída Antecipada", "Atestado"])
            nome_abs = c_a3.text_input("Nome do Colaborador")
            motivo_abs = st.text_area("Observação/Motivo")
            if st.form_submit_button("Registrar Ocorrência"):
                nova_ocorrencia = {
                    "data": str(data_abs), "tipo": tipo_abs, "nome": nome_abs.upper(), "motivo": motivo_abs
                }
                if "abs" not in db_data: db_data["abs"] = []
                db_data["abs"].append(nova_ocorrencia)
                salvar_dados_op(db_data, mes_ref)
                st.success("Registrado com sucesso!")
                st.rerun()
        
        if db_data.get("abs"):
            st.table(pd.DataFrame(db_data["abs"]))

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
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    tab_modulo_compras, tab_modulo_picos, tab_modulo_config = st.tabs([
        "🛒 COMPRAS", "📊 DASH OPERAÇÃO", "⚙️ CONFIGURAÇÕES"
    ])

    # --- ABA 1: COMPRAS (INTEGRAÇÃO TOTAL) ---
    with tab_modulo_compras:
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 DASHBOARD RECEBIMENTO"])
        
        with t1:
            if df_atual.empty: st.warning("Sem dados. Vá na aba superior CONFIGURAÇÕES.")
            else:
                st.markdown('<div class="search-box">', unsafe_allow_html=True)
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq_c")
                st.markdown('</div>', unsafe_allow_html=True)
                
                idx_s = db_data.get("idx_solic", 0)
                while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
                if idx_s < len(df_atual):
                    st.subheader(f"🚀 Esteira ({idx_s + 1}/{len(df_atual)})")
                    with st.container():
                        st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                        renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "main_c")
                        st.markdown("</div>", unsafe_allow_html=True)

        with t2:
            pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index() if not df_atual.empty else pd.DataFrame()
            if not pend_rec.empty:
                st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
                q_r = st.text_input("🔍 Localizar Recebimento:").upper()
                if q_r:
                    it_r = pend_rec[pend_rec['CODIGO'].astype(str).str.contains(q_r) | pend_rec['DESCRICAO'].astype(str).str.contains(q_r)]
                    for _, r in it_r.iterrows():
                        with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "bq_r")
                st.markdown('</div>', unsafe_allow_html=True)
                st.subheader(f"📥 Recebimento ({len(pend_rec)} pendentes)")
                with st.container():
                    st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                    renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "main_r")
                    st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Tudo recebido ou nada encomendado.")

        with t3: 
            renderizar_dashboards_compras_completo(df_atual)
            if not df_atual.empty:
                st.divider()
                st.subheader("🔍 Auditoria")
                itens_manuais = df_atual[df_atual.get('ORIGEM') == 'Manual']
                if not itens_manuais.empty: st.warning(f"🚩 {len(itens_manuais)} itens manuais.")
                c_aud1, c_aud2 = st.columns(2)
                with c_aud1:
                    with st.expander("🟢 COM ESTOQUE"): st.dataframe(df_atual[df_atual['SALDO_FISICO'] > 0], use_container_width=True)
                with c_aud2:
                    with st.expander("🔴 RUPTURA"): st.dataframe(df_atual[df_atual['SALDO_FISICO'] <= 0], use_container_width=True)

        with t4:
            # Chamando a nova função perita que acabamos de criar
            renderizar_dashboards_recebimento_completo(df_atual)
           
    # --- ABA 2: DASH OPERAÇÃO (PICOS, DIMENSIONAMENTO E ABS) ---
    with tab_modulo_picos:
        st.markdown(f"<div class='header-analise'>DASH OPERAÇÃO - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        renderizar_picos_operacional(db_data.get("picos", []), db_data, mes_ref)

    # --- ABA 3: CONFIGURAÇÕES (RESETS INDIVIDUAIS) ---
    with tab_modulo_config:
        st.markdown(f"<div class='header-analise'>CONFIGURAÇÕES</div>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.subheader("🆕 Cadastro Manual (Compras)")
            with st.form("cad_manual_form", clear_on_submit=True):
                m1, m2 = st.columns(2); c_cod = m1.text_input("Código"); c_desc = m2.text_input("Descrição")
                m3, m4, m5 = st.columns([2, 2, 1]); c_forn = m3.text_input("Fornecedor")
                c_grupo = m4.selectbox("Grupo", ["COLCHAO", "ESTOFADO", "TRAVESSEIRO", "OUTROS"]); c_qtd = m5.number_input("Qtd", min_value=1, value=1)
                if st.form_submit_button("➕ Adicionar"):
                    novo_item = {"CODIGO": c_cod, "DESCRICAO": c_desc, "FORNECEDOR": c_forn, "GRUPO": c_grupo, "QUANTIDADE": c_qtd, "ORIGEM": "Manual", "STATUS_COMPRA": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "STATUS_RECEB": "Pendente", "QTD_RECEBIDA": 0}
                    df_atual = pd.concat([df_atual, pd.DataFrame([novo_item])], ignore_index=True)
                    db_data["analises"] = df_atual.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.success("Adicionado!"); st.rerun()

        st.divider()
        st.subheader("⚙️ Importação e Resets Específicos")
        c_up1, c_up2 = st.columns(2)
        
        with c_up1:
            st.markdown("### 🛒 Base Compras")
            up_c = st.file_uploader("Upload Excel Compras", type="xlsx", key="up_compras")
            if up_c and st.button("Salvar Compras"):
                df_n = pd.read_excel(up_c)
                df_n['ORIGEM'] = 'Planilha'
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: df_n[c] = "Pendente" if "STATUS" in c else 0
                db_data["analises"] = df_n.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
            
            # REQUISITO 4: Reset Base Compras
            if st.button("🗑️ Resetar Apenas Compras", type="secondary"):
                db_data["analises"] = []; db_data["idx_solic"] = 0; db_data["idx_receb"] = 0
                salvar_dados_op(db_data, mes_ref); st.warning("Base de Compras limpa!"); st.rerun()

        with c_up2:
            st.markdown("### 📊 Base Picos (Zendesk)")
            up_p = st.file_uploader("Upload Excel Picos", type="xlsx", key="up_picos")
            if up_p and st.button("Salvar Picos"):
                df_p = pd.read_excel(up_p)
                db_data["picos"] = df_p.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
            
            # REQUISITO 4: Reset Base Picos
            if st.button("🗑️ Resetar Apenas Picos", type="secondary"):
                db_data["picos"] = []
                salvar_dados_op(db_data, mes_ref); st.warning("Base de Picos limpa!"); st.rerun()

        st.divider()
        if st.button("🗑️ RESET TOTAL DO MÊS (FULL)", type="primary"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}, mes_ref)
            st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
