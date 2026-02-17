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
        .main-card {{ background: white; padding: 25_px; border-radius: 20_px; box-shadow: 0 10_px 25_px rgba(0,0,0,0.05); border-top: 5_px solid {PALETA[0]}; margin-bottom: 20_px; }}
        .metric-box {{ background: #f8fafc; padding: 15_px; border-radius: 12_px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }}
        .metric-box h3 {{ margin: 5_px 0; font-size: 1.8rem; font-weight: bold; color: {PALETA[0]}; }}
        .search-box {{ background: #f1f5f9; padding: 20_px; border-radius: 15_px; border-left: 5_px solid {PALETA[0]}; margin-bottom: 20_px; }}
        .search-box-rec {{ background: #f0fdf4; padding: 20_px; border-radius: 15_px; border-left: 5_px solid {PALETA[2]}; margin-bottom: 20_px; }}
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15_px; border-radius: 10_px; text-align: center; margin-bottom: 20_px; font-weight: bold; font-size: 20_px; }}
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    mapeamento = {
        'CRIACAO DO TICKET - DATA': 'DATA', 
        'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 
        'CRIACAO DO TICKET - HORA': 'HORA', 
        'TICKETS': 'TICKETS'
    }
    return df.rename(columns=mapeamento)

def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# --- NOVAS FUNÇÕES DE TICKETS ---

def carregar_tickets():
    fire = inicializar_db()
    docs = fire.collection("tickets_cx").stream()
    return [doc.to_dict() for doc in docs]

def salvar_tickets(lista_tickets):
    fire = inicializar_db()
    batch = fire.batch()
    for ticket in lista_tickets:
        # Usa o ID do ticket como chave única para evitar duplicatas
        doc_ref = fire.collection("tickets_cx").document(str(ticket['ID do ticket']))
        batch.set(doc_ref, ticket)
    batch.commit()
    return True

def renderizar_modulo_tickets():
    st.markdown("<div class='header-analise'>🎫 GESTÃO DE TICKETS - CX 360º</div>", unsafe_allow_html=True)
    dados = carregar_tickets()
    df = pd.DataFrame(dados) if dados else pd.DataFrame()

    if not df.empty:
        # Tratamento de datas para o filtro
        df['Criação do ticket - Data'] = pd.to_datetime(df['Criação do ticket - Data'], errors='coerce')
        df['Mes_Ano'] = df['Criação do ticket - Data'].dt.strftime('%m/%Y')
        
        mes_sel = st.selectbox("Filtrar Mês:", ["Todos"] + sorted(df['Mes_Ano'].unique().tolist(), reverse=True))
        df_v = df if mes_sel == "Todos" else df[df['Mes_Ano'] == mes_sel]
        
        # KPIs Rápidos
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Tickets", len(df_v))
        c2.metric("Resolvidos", len(df_v[df_v['Status do ticket'].isin(['Closed', 'Solved'])]))
        c3.metric("Lojas Ativas", df_v['Nome do solicitante'].nunique())

        # Gráficos de Análise
        g1, g2 = st.columns(2)
        with g1:
            st.plotly_chart(px.bar(df_v['Assunto CX:'].value_counts().head(10), title="Top 10 Motivos"), use_container_width=True)
        with g2:
            # Gráfico de pizza com os status
            st.plotly_chart(px.pie(df_v, names='Status do ticket', title="Status Geral", hole=0.4), use_container_width=True)
    else:
        st.info("Nenhum dado de ticket encontrado no banco. Vá na aba Configurações e faça o upload da base.")

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
# 3. NOVO: COMPONENTE DE AUDITORIA (COMPRAS / RECEBIMENTO)
# =========================================================
def renderizar_auditoria_sistema(df, tipo="COMPRAS"):
    st.markdown(f"### 🔍 Auditoria de {tipo}")
    
    if tipo == "COMPRAS":
        # Filtros para Compras
        df_estoque = df[df['SALDO_FISICO'] > 0]
        df_ruptura = df[(df['SALDO_FISICO'] == 0) & (df['STATUS_COMPRA'] != "Pendente")]
        df_manual = df[df['ORIGEM'] == 'Manual']
    else:
        # Filtros para Recebimento (Itens que foram solicitados)
        df_ref = df[df['QTD_SOLICITADA'] > 0]
        df_estoque = df_ref[df_ref['STATUS_RECEB'] == "Recebido Total"]
        df_ruptura = df_ref[df_ref['STATUS_RECEB'].isin(["Faltou", "Recebido Parcial"])]
        df_manual = df_ref[df_ref['ORIGEM'] == 'Manual']

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info("🟢 COM ESTOQUE / OK")
        st.dataframe(df_estoque[['GRUPO', 'DESCRICAO', 'SALDO_FISICO']], use_container_width=True, hide_index=True)
        st.download_button("📥 Baixar Excel", data=converter_para_excel(df_estoque), file_name=f"auditoria_{tipo.lower()}_estoque.xlsx", key=f"dl_est_{tipo}")

    with col2:
        st.error("🔴 RUPTURA")
        st.dataframe(df_ruptura[['GRUPO', 'DESCRICAO', 'STATUS_COMPRA' if tipo == "COMPRAS" else 'STATUS_RECEB']], use_container_width=True, hide_index=True)
        st.download_button("📥 Baixar Excel", data=converter_para_excel(df_ruptura), file_name=f"auditoria_{tipo.lower()}_ruptura.xlsx", key=f"dl_rup_{tipo}")

    with col3:
        st.warning("➕ MANUAL")
        st.dataframe(df_manual[['GRUPO', 'DESCRICAO', 'QUANTIDADE']], use_container_width=True, hide_index=True)
        st.download_button("📥 Baixar Excel", data=converter_para_excel(df_manual), file_name=f"auditoria_{tipo.lower()}_manual.xlsx", key=f"dl_man_{tipo}")

# =========================================================
# 4. DASHBOARDS DE PERFORMANCE
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
    
    # Adicionando Auditoria aqui
    st.divider()
    renderizar_auditoria_sistema(df, "COMPRAS")

def renderizar_dashboards_recebimento_ajustado(df):
    if df.empty: return
    df_f = df[df['QTD_SOLICITADA'] > 0]
    if df_f.empty:
        st.info("Nenhuma compra efetuada para analisar recebimento."); return

    total_pedidos = len(df_f)
    df_rec = df_f[df_f['STATUS_RECEB'] != "Pendente"]
    itens_processados = len(df_rec)
    rec_total = len(df_rec[df_rec['STATUS_RECEB'] == "Recebido Total"])
    perc_proc = (itens_processados / total_pedidos * 100) if total_pedidos > 0 else 0
    perc_efici = (rec_total / itens_processados * 100) if itens_processados > 0 else 0

    st.subheader("📥 Performance de Recebimento")
    rk1, rk2, rk3, rk4 = st.columns(4)
    rk1.markdown(f"<div class='metric-box'><small>PROCESSADO</small><h3>{itens_processados}</h3><p>{perc_proc:.1f}%</p></div>", unsafe_allow_html=True)
    rk2.markdown(f"<div class='metric-box'><small>REC. TOTAL</small><h3>{rec_total}</h3><p>{perc_efici:.1f}%</p></div>", unsafe_allow_html=True)
    falta_vol = df_f['QTD_SOLICITADA'].sum() - df_f['QTD_RECEBIDA'].sum()
    rk3.markdown(f"<div class='metric-box'><small>QTD FALTANTE</small><h3 style='color:#ef4444;'>{int(falta_vol)}</h3></div>", unsafe_allow_html=True)
    efi_vol = (df_f['QTD_RECEBIDA'].sum() / df_f['QTD_SOLICITADA'].sum() * 100) if df_f['QTD_SOLICITADA'].sum() > 0 else 0
    rk4.markdown(f"<div class='metric-box'><small>EFICIÊNCIA VOL.</small><h3 style='color:#16a34a;'>{efi_vol:.1f}%</h3></div>", unsafe_allow_html=True)

    rc1, rc2 = st.columns(2)
    with rc1:
        st_rec = df_f['STATUS_RECEB'].value_counts().reset_index()
        st_rec.columns = ['Status', 'Qtd']
        fig_r = px.pie(st_rec, values='Qtd', names='Status', title="Status de Recebimento", hole=0.4, color='Status', color_discrete_map={'Recebido Total': '#16a34a', 'Recebido Parcial': '#facc15', 'Faltou': '#ef4444', 'Pendente': '#cbd5e1'})
        st.plotly_chart(fig_r, use_container_width=True)
    with rc2:
        df_f['DIF'] = df_f['QTD_SOLICITADA'] - df_f['QTD_RECEBIDA']
        top_dif = df_f[df_f['DIF'] > 0].sort_values(by='DIF', ascending=False).head(10)
        fig_dif = px.bar(top_dif, x='CODIGO', y='DIF', title="Maiores Faltas por SKU", color_discrete_sequence=['#ef4444'], text_auto=True)
        st.plotly_chart(fig_dif, use_container_width=True)
    
    # Adicionando Auditoria aqui
    st.divider()
    renderizar_auditoria_sistema(df, "RECEBIMENTO")

# =========================================================
# 5. DASHBOARD DE PICOS E DIMENSIONAMENTO (OPERACIONAL)
# =========================================================
def renderizar_picos_operacional(db_picos, db_data, mes_ref):
    with st.expander("🛠️ RECUPERAÇÃO DE DADOS"):
        if st.button("🚨 LIMPAR TODOS OS PICOS DESTE MÊS", use_container_width=True):
            db_data["picos"] = []
            salvar_dados_op(db_data, mes_ref); st.success("Dados limpos!"); st.rerun()

    if not db_picos:
        st.info("💡 Sem dados de picos para este período.")
        return
    
    tab_picos, tab_dim, tab_abs = st.tabs(["🔥 MAPA DE CALOR", "👥 DIMENSIONAMENTO", "📝 REGISTRO ABS"])
    df = pd.DataFrame(db_picos)
    df = normalizar_picos(df)
    
    colunas_fatais = [c for c in ['DATA', 'TICKETS', 'HORA', 'DIA_SEMANA'] if c not in df.columns]
    if colunas_fatais:
        st.error(f"❌ Erro de Colunas: A planilha não possui {colunas_fatais}"); return

    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    st.markdown("### 📅 Filtro de Análise")
    dias_disponiveis = sorted(df['DATA'].unique()) 
    dias_selecionados = st.multiselect("Selecione os dias para compor a média:", dias_disponiveis, default=dias_disponiveis, key=f"filter_days_{mes_ref}")

    with tab_picos:
        if dias_selecionados:
            df_f = df[df['DATA'].isin(dias_selecionados)]
            fig_heat = px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias}, color_continuous_scale=["#ADD8E6", "#FFFFE0", "#FFD700", "#FF8C00", "#FF4500"], text_auto=True)
            st.plotly_chart(fig_heat, use_container_width=True)
            c1, c2 = st.columns(2)
            with c1:
                df_h = df_f.groupby('HORA')['TICKETS'].sum().reset_index()
                st.plotly_chart(px.bar(df_h, x='HORA', y='TICKETS', title="Volume por Hora", text_auto=True, color_discrete_sequence=[PALETA[0]]), use_container_width=True)
            with c2:
                df_d = df_f.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna()
                st.plotly_chart(px.bar(df_d, x='DIA_SEMANA', y='TICKETS', title="Volume por Dia", text_auto=True, color_discrete_sequence=[PALETA[1]]), use_container_width=True)

    with tab_dim:
        st.subheader("👥 Simulador de Dimensionamento Dinâmico")
        with st.container(border=True):
            col_sim1, col_sim2 = st.columns(2)
            meta_hora = col_sim1.slider("Capacidade: Atendimentos/Hora por Agente", 1, 15, 4, key=f"meta_{mes_ref}")
            agentes_reais = col_sim2.number_input("Equipe em Operação (Cenário Real)", min_value=1, value=5, key=f"ag_real_{mes_ref}")
        if dias_selecionados:
            df_dim = df[df['DATA'].isin(dias_selecionados)].groupby('HORA')['TICKETS'].mean().reset_index()
            df_dim['AGENTES_NECESSARIOS'] = (df_dim['TICKETS'] / meta_hora).apply(lambda x: int(x) + 1 if x % 1 > 0 else int(x))
            df_dim['CARGA_POR_AGENTE'] = (df_dim['TICKETS'] / agentes_reais).round(1)
            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(px.bar(df_dim, x='HORA', y='AGENTES_NECESSARIOS', title="Equipe Ideal", text_auto=True, color_discrete_sequence=[PALETA[0]]), use_container_width=True)
            with g2:
                fig_carga = px.line(df_dim, x='HORA', y='CARGA_POR_AGENTE', markers=True, title="Carga Real", color_discrete_sequence=['#ef4444'])
                fig_carga.add_hline(y=meta_hora, line_dash="dash", line_color="green", annotation_text="Teto da Meta")
                st.plotly_chart(fig_carga, use_container_width=True)

    with tab_abs:
        st.subheader("📝 Controle de ABS")
        with st.form(f"form_abs_{mes_ref}", clear_on_submit=True):
            ca1, ca2, ca3 = st.columns(3); d_abs = ca1.date_input("Data", value=datetime.now()); t_abs = ca2.selectbox("Tipo", ["Falta", "Atraso", "Saída Antecipada", "Atestado"]); n_abs = ca3.text_input("Nome do Colaborador")
            m_abs = st.text_area("Observação/Motivo")
            if st.form_submit_button("Registrar Ocorrência"):
                db_data.setdefault("abs", []).append({"data": str(d_abs), "tipo": t_abs, "nome": n_abs.upper(), "motivo": m_abs})
                salvar_dados_op(db_data, mes_ref); st.success("Registrado!"); st.rerun()
        if db_data.get("abs"): st.table(pd.DataFrame(db_data["abs"]))

# =========================================================
# 6. ESTRUTURA UNIFICADA
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    st.sidebar.title("💎 Sistema Premium")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    tab_modulo_compras, tab_modulo_picos, tab_modulo_tickets, tab_modulo_config = st.tabs([
        "🛒 COMPRAS", "📊 DASH OPERAÇÃO", "🎫 TICKETS 360º", "⚙️ CONFIGURAÇÕES"
    ])

    with tab_modulo_compras:
        col_m1, col_m2 = st.columns(2)
        mes_c = col_m1.selectbox("Selecione o Mês (COMPRAS)", meses_lista, index=datetime.now().month - 1, key="sel_mes_compras")
        ano_c = col_m2.selectbox("Selecione o Ano (COMPRAS)", [2024, 2025, 2026], index=1, key="sel_ano_compras")
        mes_ref_c = f"{mes_c}_{ano_c}"
        db_c = carregar_dados_op(mes_ref_c)
        df_c = pd.DataFrame(db_c["analises"]) if db_c.get("analises") else pd.DataFrame()

        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_c.upper()}</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 DASHBOARD RECEBIMENTO"])
        
        with t1:
            if df_c.empty: st.warning("Sem dados para este período.")
            else:
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_c[df_c['CODIGO'].astype(str).str.contains(q) | df_c['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_c, db_c, mes_ref_c, "bq_c")
                idx_s = db_c.get("idx_solic", 0)
                while idx_s < len(df_c) and df_c.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
                if idx_s < len(df_c):
                    st.subheader(f"🚀 Esteira ({idx_s + 1}/{len(df_c)})")
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_c.iloc[idx_s], idx_s, df_c, db_c, mes_ref_c, "main_c")
                    st.markdown("</div>", unsafe_allow_html=True)

        with t2:
            pend_rec = df_c[(df_c['QTD_SOLICITADA'] > 0) & (df_c['STATUS_RECEB'] == "Pendente")].reset_index() if not df_c.empty else pd.DataFrame()
            if not pend_rec.empty:
                st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
                q_r = st.text_input("🔍 Localizar Recebimento:").upper()
                if q_r:
                    it_r = pend_rec[pend_rec['CODIGO'].astype(str).str.contains(q_r) | pend_rec['DESCRICAO'].astype(str).str.contains(q_r)]
                    for _, r in it_r.iterrows():
                        with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_c, db_c, mes_ref_c, "bq_r")
                st.markdown('</div>', unsafe_allow_html=True)
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_c, db_c, mes_ref_c, "main_r")
                st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Tudo recebido ou nada encomendado.")

        with t3: renderizar_dashboards_compras_completo(df_c)
        with t4: renderizar_dashboards_recebimento_ajustado(df_c)

    with tab_modulo_picos:
        col_p1, col_p2 = st.columns(2)
        mes_p = col_p1.selectbox("Selecione o Mês (OPERAÇÃO)", meses_lista, index=datetime.now().month - 1, key="sel_mes_op")
        ano_p = col_p2.selectbox("Selecione o Ano (OPERAÇÃO)", [2024, 2025, 2026], index=1, key="sel_ano_op")
        mes_ref_p = f"{mes_p}_{ano_p}"
        db_p = carregar_dados_op(mes_ref_p)
        st.markdown(f"<div class='header-analise'>DASHBOARD OPERACIONAL - {mes_p.upper()}</div>", unsafe_allow_html=True)
        renderizar_picos_operacional(db_p.get("picos", []), db_p, mes_ref_p)

    with tab_modulo_tickets:
        renderizar_modulo_tickets()
        
    with tab_modulo_config:
        st.markdown(f"<div class='header-analise'>CONFIGURAÇÕES GERAIS</div>", unsafe_allow_html=True)
        c_ref1, c_ref2 = st.columns(2)
        mes_cfg = c_ref1.selectbox("Referência para Upload (Mês)", meses_lista, index=datetime.now().month - 1, key="cfg_mes")
        ano_cfg = c_ref2.selectbox("Referência para Upload (Ano)", [2024, 2025, 2026], index=1, key="cfg_ano")
        mes_ref_cfg = f"{mes_cfg}_{ano_cfg}"
        db_cfg = carregar_dados_op(mes_ref_cfg)
        df_cfg = pd.DataFrame(db_cfg["analises"]) if db_cfg.get("analises") else pd.DataFrame()

        with st.container(border=True):
            st.subheader(f"🆕 Cadastro Manual ({mes_ref_cfg})")
            with st.form("cad_manual_form", clear_on_submit=True):
                m1, m2 = st.columns(2); c_cod = m1.text_input("Código"); c_desc = m2.text_input("Descrição")
                m3, m4, m5 = st.columns([2, 2, 1]); c_forn = m3.text_input("Fornecedor"); c_grupo = m4.selectbox("Grupo", ["COLCHAO", "ESTOFADO", "OUTROS"]); c_qtd = m5.number_input("Qtd", min_value=1)
                if st.form_submit_button("➕ Adicionar"):
                    novo = {"CODIGO": c_cod, "DESCRICAO": c_desc, "FORNECEDOR": c_forn, "GRUPO": c_grupo, "QUANTIDADE": c_qtd, "ORIGEM": "Manual", "STATUS_COMPRA": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "STATUS_RECEB": "Pendente", "QTD_RECEBIDA": 0}
                    df_cfg = pd.concat([df_cfg, pd.DataFrame([novo])], ignore_index=True)
                    db_cfg["analises"] = df_cfg.to_dict(orient='records'); salvar_dados_op(db_cfg, mes_ref_cfg); st.rerun()

        st.divider()
        
        # Primeiro, o uploader de Tickets em largura total
        st.markdown(f"### 🎫 Base Tickets (Zendesk)")
        up_t = st.file_uploader("Upload Excel Tickets", type=["xlsx", "csv"], key="up_tickets_cx")
        if up_t and st.button("Gravar Base de Tickets"):
            df_t = pd.read_excel(up_t) if up_t.name.endswith('.xlsx') else pd.read_csv(up_t)
            if salvar_tickets(df_t.to_dict(orient='records')):
                st.success("Base de Tickets integrada!")
                st.rerun()

        st.divider()
                
        c_up1, c_up2 = st.columns(2)
        
        with c_up1:
            st.markdown(f"### 🛒 Base Compras ({mes_ref_cfg})")
                             
        with c_up2:
            st.markdown(f"### 📊 Base Picos ({mes_ref_cfg})")
            up_p = st.file_uploader("Upload Zendesk", type="xlsx", key="up_picos")
            if up_p and st.button("Salvar Picos"):
                db_cfg["picos"] = pd.read_excel(up_p).to_dict(orient='records'); salvar_dados_op(db_cfg, mes_ref_cfg); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
