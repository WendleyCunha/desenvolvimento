import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io

# --- CONFIGURAÇÃO E ESTILO ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        .search-box-rec { background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid #16a34a; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE DADOS ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# --- NOVO: ANÁLISE DE PICOS (BI) ---
def renderizar_analise_demanda(df):
    st.subheader("🔥 Análise de Picos de Demanda")
    
    # Validação de colunas necessárias para o BI
    cols_necessarias = ['DATA_ENTRADA', 'HORA', 'TICKETS']
    if not all(c in df.columns for c in cols_necessarias):
        st.info("Para ver os picos de demanda, certifique-se que sua planilha contém as colunas: DATA_ENTRADA, HORA e TICKETS.")
        return

    # Tratamento de dados
    df['DATA_ENTRADA'] = pd.to_datetime(df['DATA_ENTRADA'])
    df['DIA_SEMANA'] = df['DATA_ENTRADA'].dt.day_name()

    c1, c2, c3 = st.columns(3)

    # 1. Pico Dia
    pico_dia_val = df.groupby('DATA_ENTRADA')['TICKETS'].sum().max()
    pico_dia_data = df.groupby('DATA_ENTRADA')['TICKETS'].sum().idxmax().strftime('%d/%m')
    c1.markdown(f"<div class='metric-box'><small>PICO DIÁRIO</small><h3>{pico_dia_val}</h3><p>{pico_dia_data}</p></div>", unsafe_allow_html=True)

    # 2. Pico Horário
    pico_hora = df.groupby('HORA')['TICKETS'].mean().idxmax()
    pico_hora_val = df.groupby('HORA')['TICKETS'].mean().max()
    c2.markdown(f"<div class='metric-box'><small>PICO HORÁRIO (Méd)</small><h3>{pico_hora}h</h3><p>{pico_hora_val:.1f} tickets</p></div>", unsafe_allow_html=True)

    # 3. Pico Semana
    pico_sem = df.groupby('DIA_SEMANA')['TICKETS'].sum().idxmax()
    c3.markdown(f"<div class='metric-box'><small>DIA DA SEMANA</small><h3>{pico_sem}</h3><p>Maior Volume</p></div>", unsafe_allow_html=True)

    # Gráfico de Tendência
    fig_evolucao = px.line(df.groupby('DATA_ENTRADA')['TICKETS'].sum().reset_index(), 
                          x='DATA_ENTRADA', y='TICKETS', title="Evolução Diária de Entradas",
                          line_shape="spline", render_mode="svg")
    st.plotly_chart(fig_evolucao, use_container_width=True)

# --- RENDERIZAÇÃO DE INTERFACE (TRATATIVAS) ---
def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado: {item['QTD_SOLICITADA']}**")
    rc1, rc2, rc3 = st.columns(3)
    
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"
        df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()
        
    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True
        
    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"
        df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=int(item['QTD_SOLICITADA']), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"
            df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
        
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
        
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# --- DASHBOARDS ---
def renderizar_dashboard_compras(df):
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
        fig_p = px.pie(st_counts, values='Qtd', names='Status', title="Decisões de Compra", hole=0.4,
                       color='Status', color_discrete_map={'Total': '#002366', 'Parcial': '#3b82f6', 'Não Efetuada': '#ef4444', 'Pendente': '#cbd5e1'})
        st.plotly_chart(fig_p, use_container_width=True)
    with c2:
        fig_rup = go.Figure(data=[
            go.Bar(name='Com Estoque', x=['Não Efetuadas'], y=[len(nao_efet_com_estoque)], marker_color='#16a34a'),
            go.Bar(name='Sem Estoque', x=['Não Efetuadas'], y=[len(nao_efet_sem_estoque)], marker_color='#ef4444')
        ])
        fig_rup.update_layout(title="Motivo das Não Encomendas", barmode='group', height=400)
        st.plotly_chart(fig_rup, use_container_width=True)

def renderizar_dashboard_recebimento(df):
    if df.empty: return
    encomendados = df[df['QTD_SOLICITADA'] > 0]
    if encomendados.empty:
        st.warning("Sem encomendas realizadas.")
        return
    df_rec = encomendados[encomendados['STATUS_RECEB'] != "Pendente"]
    
    st.subheader("📊 Performance de Recebimento")
    r1, r2, r3, r4 = st.columns(4)
    r1.markdown(f"<div class='metric-box'><small>CONFERIDOS</small><h3>{len(df_rec)}/{len(encomendados)}</h3></div>", unsafe_allow_html=True)
    r2.markdown(f"<div class='metric-box'><small>REC. TOTAL</small><h3 style='color:#16a34a;'>{len(df_rec[df_rec['STATUS_RECEB'] == 'Recebido Total'])}</h3></div>", unsafe_allow_html=True)
    r3.markdown(f"<div class='metric-box'><small>REC. PARCIAL</small><h3 style='color:#facc15;'>{len(df_rec[df_rec['STATUS_RECEB'] == 'Recebido Parcial'])}</h3></div>", unsafe_allow_html=True)
    r4.markdown(f"<div class='metric-box'><small>FALTOU</small><h3 style='color:#ef4444;'>{len(df_rec[df_rec['STATUS_RECEB'] == 'Faltou'])}</h3></div>", unsafe_allow_html=True)

# --- EXIBIÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    st.sidebar.title("📅 Período")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    ano_hoje = datetime.now().year
    anos_dinamicos = list(range(ano_hoje - 1, ano_hoje + 3))
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", anos_dinamicos, index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    # Adicionada a aba "📈 ANALISE DE PICOS"
    tab1, tab2, tab3, tab4, tab_picos, tab5 = st.tabs([
        "🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASH COMPRAS", "📉 DASH RECEBIMENTO", "🔥 ANALISE DE PICOS", "⚙️ CONFIGURAÇÕES"
    ])

    # --- TAB CONFIGURAÇÕES (Mantida e ajustada) ---
    with tab5:
        st.header(f"⚙️ Configuração: {mes_sel}/{ano_sel}")
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            st.subheader("📄 Planilha NOVA")
            up_nova = st.file_uploader("Base Crua", type="xlsx", key="up_n")
            if up_nova and st.button("🚀 Iniciar com esta Base"):
                df_n = pd.read_excel(up_nova)
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: 
                    df_n[c] = "Pendente" if "STATUS" in c else 0
                df_n['ORIGEM'] = "Planilha"
                salvar_dados_op({"analises": df_n.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}, mes_ref); st.rerun()

    if not db_data.get("analises"):
        st.warning("⚠️ Sem dados. Vá em CONFIGURAÇÕES.")
        return

    df_atual = pd.DataFrame(db_data["analises"])

    # --- RENDERIZAÇÃO DAS TABS ---
    with tab1: # Compras
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar:").upper()
        if q:
            it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
            for i, r in it_b.iterrows():
                with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "busca_c")
        st.markdown('</div>', unsafe_allow_html=True)
        # Lógica da Esteira...
        idx_s = db_data.get("idx_solic", 0)
        while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
        if idx_s < len(df_atual):
            renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "esteira_c")

    with tab2: # Recebimento
        pendentes_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
        if not pendentes_rec.empty:
            idx_r = db_data.get("idx_receb", 0)
            renderizar_tratativa_recebimento(pendentes_rec.iloc[0], pendentes_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "esteira_r")
        else: st.success("✅ Tudo recebido!")

    with tab3: renderizar_dashboard_compras(df_atual)
    with tab4: renderizar_dashboard_recebimento(df_atual)
    
    with tab_picos: # Nova Aba de Picos
        renderizar_analise_demanda(df_atual)
