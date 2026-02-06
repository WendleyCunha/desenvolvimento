import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata
import math

# =========================================================
# 1. CONFIGURAÇÕES, ESTILO E SUPORTE
# =========================================================
PALETA = ['#002366', '#3b82f6', '#16a34a', '#ef4444', '#facc15']

def aplicar_estilo_premium():
    st.markdown(f"""
        <style>
        .main-card {{ background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .metric-box {{ background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }}
        .metric-box h3 {{ margin: 5px 0; font-size: 1.8rem; font-weight: bold; color: {PALETA[0]}; }}
        .search-box {{ background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 20px; }}
        </style>
    """, unsafe_allow_html=True)

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    # Adicionado estrutura para 'abs' se não existir
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

# =========================================================
# 2. BLOCO: COMPRAS E RECEBIMENTO (INTEGRIDADE MANTIDA)
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

# =========================================================
# 3. BLOCO: DASH OPERAÇÃO E DIMENSIONAMENTO (NOVO!)
# =========================================================

def renderizar_picos_operacional(db_picos):
    if not db_picos:
        st.info("💡 Sem dados de picos. Importe a planilha em CONFIGURAÇÕES."); return
    
    df = normalizar_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    st.markdown("### 📅 Filtro de Dias")
    dias_disponiveis = sorted(df['DATA'].unique())
    dias_selecionados = st.multiselect("Selecione os dias para análise:", dias_disponiveis, default=dias_disponiveis)
    
    if not dias_selecionados: return
    df_f = df[df['DATA'].isin(dias_selecionados)]
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    # --- HEATMAP ---
    st.markdown("#### 🔥 Mapa de Calor (Temperatura de Chamados)")
    cores_suaves = ["#ADD8E6", "#FFFFE0", "#FFD700", "#FF8C00", "#FF4500"]
    fig_heat = px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias}, color_continuous_scale=cores_suaves, text_auto=True)
    st.plotly_chart(fig_heat, use_container_width=True)

    # --- DIMENSIONAMENTO ---
    st.divider()
    st.subheader("👥 Dimensionamento de Equipe")
    atend_hora = 4 # Regra solicitada
    
    # Médias por hora considerando os dias selecionados
    df_dim = df_f.groupby('HORA')['TICKETS'].mean().reset_index()
    df_dim['ATENDENTES_NECESSARIOS'] = df_dim['TICKETS'].apply(lambda x: math.ceil(x / atend_hora))
    
    col_dim1, col_dim2 = st.columns([2, 1])
    with col_dim1:
        fig_dim = px.line(df_dim, x='HORA', y='ATENDENTES_NECESSARIOS', title="Necessidade de Atendentes por Hora (Média)", markers=True, color_discrete_sequence=[PALETA[0]])
        st.plotly_chart(fig_dim, use_container_width=True)
    
    with col_dim2:
        st.markdown("**Sugestão de Pausas (Horários de Baixo Volume):**")
        # Identifica as 3 horas com menor volume de chamados
        pausas = df_dim.sort_values(by='TICKETS').head(3)['HORA'].tolist()
        for p in sorted(pausas):
            st.success(f"☕ Sugestão de Pausa: {p}h")
            
    st.dataframe(df_dim[['HORA', 'TICKETS', 'ATENDENTES_NECESSARIOS']].rename(columns={'TICKETS': 'Média Tickets', 'ATENDENTES_NECESSARIOS': 'Atendentes Necessários'}), use_container_width=True)

# =========================================================
# 4. ESTRUTURA UNIFICADA (MAIN)
# =========================================================

def exibir_operacao_completa():
    aplicar_estilo_premium()
    
    st.sidebar.title("📅 Gestão Mensal")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    tab_modulo_compras, tab_modulo_picos, tab_modulo_abs, tab_modulo_config = st.tabs([
        "🛒 COMPRAS", "📊 DASH OPERAÇÃO", "📉 REGISTRO ABS", "⚙️ CONFIGURAÇÕES"
    ])

    # --- ABA COMPRAS (MANTIDA) ---
    with tab_modulo_compras:
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 DASHBOARD RECEBIMENTO"])
        with t1:
            if df_atual.empty: st.warning("Vá em CONFIGURAÇÕES para importar os dados.")
            else:
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
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
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "main_r")
                st.markdown("</div>", unsafe_allow_html=True)
        with t3: renderizar_dashboards_compras_completo(df_atual)
        with t4:
            if not df_atual.empty:
                enc = df_atual[df_atual['QTD_SOLICITADA'] > 0]
                if not enc.empty:
                    df_rec = enc[enc['STATUS_RECEB'] != "Pendente"]
                    st.plotly_chart(px.bar(df_rec, x='CODIGO', y=['QTD_SOLICITADA', 'QTD_RECEBIDA'], barmode='group'), use_container_width=True)

    # --- ABA DASH OPERAÇÃO ---
    with tab_modulo_picos:
        st.markdown(f"<div class='header-analise'>DASH OPERAÇÃO & DIMENSIONAMENTO</div>", unsafe_allow_html=True)
        renderizar_picos_operacional(db_data.get("picos", []))

    # --- ABA REGISTRO ABS (NOVO!) ---
    with tab_modulo_abs:
        st.markdown(f"<div class='header-analise'>CONTROLE DE ABSENTEÍSMO E ATRASOS</div>", unsafe_allow_html=True)
        with st.form("form_abs"):
            c1, c2, c3 = st.columns(3)
            data_abs = c1.date_input("Data da Ocorrência")
            tipo_abs = c2.selectbox("Tipo", ["FALTA", "ATRASO", "SAÍDA ANTECIPADA", "ATESTADO"])
            colab_abs = c3.text_input("Nome do Colaborador")
            motivo_abs = st.text_area("Motivo/Observação")
            if st.form_submit_button("Registrar Ocorrência"):
                nova_ocorr = {"DATA": str(data_abs), "TIPO": tipo_abs, "NOME": colab_abs, "MOTIVO": motivo_abs}
                if "abs" not in db_data: db_data["abs"] = []
                db_data["abs"].append(nova_ocorr)
                salvar_dados_op(db_data, mes_ref)
                st.success("Registrado!")
                st.rerun()
        
        if db_data.get("abs"):
            st.divider()
            df_abs = pd.DataFrame(db_data["abs"])
            st.dataframe(df_abs, use_container_width=True)

    # --- ABA CONFIGURAÇÕES (NOVO!) ---
    with tab_modulo_config:
        st.markdown(f"<div class='header-analise'>GERENCIAMENTO DE BASES</div>", unsafe_allow_html=True)
        
        st.subheader("📥 Importação de Dados")
        c_up1, c_up2 = st.columns(2)
        with c_up1:
            up_c = st.file_uploader("Base Compras (Excel)", type="xlsx")
            if up_c and st.button("Salvar Base Compras"):
                df_n = pd.read_excel(up_c)
                df_n['ORIGEM'] = 'Planilha'
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: df_n[c] = "Pendente" if "STATUS" in c else 0
                db_data["analises"] = df_n.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
        with c_up2:
            up_p = st.file_uploader("Base Picos Zendesk (Excel)", type="xlsx")
            if up_p and st.button("Salvar Base Picos"):
                df_p = pd.read_excel(up_p)
                db_data["picos"] = df_p.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        st.subheader("🗑️ Resets Específicos")
        r1, r2, r3 = st.columns(3)
        if r1.button("Resetar apenas COMPRAS", type="primary", use_container_width=True):
            db_data["analises"] = []; salvar_dados_op(db_data, mes_ref); st.rerun()
        if r2.button("Resetar apenas PICOS", type="primary", use_container_width=True):
            db_data["picos"] = []; salvar_dados_op(db_data, mes_ref); st.rerun()
        if r3.button("LIMPAR MÊS COMPLETO", type="primary", use_container_width=True):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
