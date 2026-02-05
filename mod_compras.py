import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io

# --- CONFIGURAÇÃO E DADOS ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        .search-box-rec { background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid #16a34a; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

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

# --- TRATATIVAS ---
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

# --- DASHBOARDS ORIGINAIS RESTAURADOS ---
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

    st.markdown("### 🔍 Detalhamento de Auditoria")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        with st.expander("🟢 ITENS COM ESTOQUE (Estratégico)"):
            if not nao_efet_com_estoque.empty:
                st.download_button("📥 Baixar Estratégico", data=to_excel(nao_efet_com_estoque), file_name="estrategico.xlsx", key="dl_est")
                st.dataframe(nao_efet_com_estoque[['CODIGO', 'DESCRICAO', 'SALDO_FISICO']], use_container_width=True)
    with col_f2:
        with st.expander("🔴 ITENS SEM ESTOQUE (Ruptura)"):
            if not nao_efet_sem_estoque.empty:
                st.download_button("📥 Baixar Ruptura", data=to_excel(nao_efet_sem_estoque), file_name="ruptura.xlsx", key="dl_rup")
                st.dataframe(nao_efet_sem_estoque[['CODIGO', 'DESCRICAO']], use_container_width=True)

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

    fig_r = px.bar(df_rec, x='CODIGO', y=['QTD_SOLICITADA', 'QTD_RECEBIDA'], title="Solicitado vs Recebido", barmode='group', color_discrete_sequence=['#002366', '#16a34a'])
    st.plotly_chart(fig_r, use_container_width=True)

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
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 DASHBOARD RECEBIMENTO", "⚙️ CONFIGURAÇÕES"])

    with tab5:
        st.header(f"⚙️ Configuração: {mes_sel}/{ano_sel}")
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            st.subheader("📄 Planilha NOVA")
            up_nova = st.file_uploader("Base Crua", type="xlsx", key="up_n")
            if up_nova and st.button("🚀 Iniciar com esta Base"):
                df_n = pd.read_excel(up_nova)
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: df_n[c] = "Pendente" if "STATUS" in c else 0
                df_n['ORIGEM'] = "Planilha"
                salvar_dados_op({"analises": df_n.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}, mes_ref); st.rerun()
        with col_up2:
            st.subheader("📝 Planilha PREENCHIDA")
            up_pre = st.file_uploader("Base Analisada", type="xlsx", key="up_p")
            if up_pre and st.button("📥 Importar Análise"):
                df_p = pd.read_excel(up_pre)
                if 'ORIGEM' not in df_p.columns: df_p['ORIGEM'] = "Planilha"
                salvar_dados_op({"analises": df_p.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}, mes_ref); st.rerun()

        st.divider()
        st.subheader("🆕 Cadastro Manual")
        with st.form("f_manual", clear_on_submit=True):
            f1, f2 = st.columns(2)
            n_cod = f1.text_input("Código").upper()
            n_des = f2.text_input("Descrição")
            f3, f4, f5 = st.columns(3)
            n_forn = f3.text_input("Fornecedor")
            n_grp = f4.selectbox("Grupo", ["COLCHAO", "BOX", "TRAVESSEIRO", "PROTETOR", "OUTROS"])
            n_qtd = f5.number_input("Qtd", min_value=1, value=1)
            if st.form_submit_button("➕ Adicionar"):
                if n_cod and n_des:
                    novo = {"CODIGO": n_cod, "DESCRICAO": n_des, "FORNECEDOR": n_forn, "GRUPO": n_grp, "QUANTIDADE": n_qtd, "STATUS_COMPRA": "Pendente", "STATUS_RECEB": "Pendente", "QTD_SOLICITADA": 0, "QTD_RECEBIDA": 0, "SALDO_FISICO": 0, "ORIGEM": "Manual"}
                    db_data["analises"].append(novo); salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        if st.button("🗑️ RESETAR MÊS"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}, mes_ref); st.rerun()

    if not db_data.get("analises"):
        st.warning("⚠️ Sem dados. Vá em CONFIGURAÇÕES.")
        return

    df_atual = pd.DataFrame(db_data["analises"])

    with tab1:
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar:").upper()
        if q:
            it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
            for i, r in it_b.iterrows():
                with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "busca_c")
        st.markdown('</div>', unsafe_allow_html=True)
        idx_s = db_data.get("idx_solic", 0)
        while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
        db_data["idx_solic"] = idx_s
        if idx_s < len(df_atual):
            st.subheader(f"🚀 Esteira ({idx_s + 1}/{len(df_atual)})")
            with st.container():
                st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "esteira_c")
                st.markdown("</div>", unsafe_allow_html=True)

    with tab2:
        pendentes_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
        if not pendentes_rec.empty:
            st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
            q_r = st.text_input("🔍 Localizar Rec:").upper()
            if q_r:
                it_r = pendentes_rec[pendentes_rec['CODIGO'].astype(str).str.contains(q_r) | pendentes_rec['DESCRICAO'].astype(str).str.contains(q_r)]
                for _, r in it_r.iterrows():
                    with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "busca_r")
            st.markdown('</div>', unsafe_allow_html=True)
            idx_r = db_data.get("idx_receb", 0)
            if idx_r >= len(pendentes_rec): idx_r = 0
            st.subheader(f"📥 Recebimento ({idx_r + 1}/{len(pendentes_rec)})")
            with st.container():
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(pendentes_rec.iloc[idx_r], pendentes_rec.iloc[idx_r]['index'], df_atual, db_data, mes_ref, "esteira_r")
                st.markdown("</div>", unsafe_allow_html=True)
        else: st.success("✅ Tudo recebido!")

    with tab3:
        renderizar_dashboard_compras(df_atual)
        if 'ORIGEM' in df_atual.columns:
            manuais = df_atual[df_atual['ORIGEM'] == 'Manual']
            if not manuais.empty:
                st.divider()
                st.warning(f"🚩 ALERTA: {len(manuais)} itens manuais identificados.")
                with st.expander("🔍 Ver itens fora da planilha"):
                    st.table(manuais[['CODIGO', 'DESCRICAO', 'QUANTIDADE']])
        st.divider()
        st.download_button("📥 Baixar Relatório Geral Compras", to_excel(df_atual), f"compras_{mes_ref}.xlsx")

    with tab4:
        renderizar_dashboard_recebimento(df_atual)
        st.divider()
        st.download_button("📥 Baixar Relatório Geral Recebimento", to_excel(df_atual), f"recebimento_{mes_ref}.xlsx")
