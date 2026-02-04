import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io

# --- ESTILIZAÇÃO ---
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

# --- COMPONENTES DE INTERFACE (TRATATIVAS) ---
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True

    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]
            salvar_dados_op(db_data, mes_ref); st.rerun()

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
            del st.session_state[f"show_rec_p_{index}_{key_suffix}"]
            salvar_dados_op(db_data, mes_ref); st.rerun()

# --- FUNÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role="OPERACIONAL"):
    aplicar_estilo_premium()
    
    # 1. Gestão de Período
    st.sidebar.title("📅 Período")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    ano_hoje = datetime.now().year
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", list(range(ano_hoje - 1, ano_hoje + 3)), index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    # 2. Definição das Abas
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 DASHBOARD RECEBIMENTO", "⚙️ CONFIGURAÇÕES"])

    # --- TAB 5: CONFIGURAÇÕES (Upload e Manual) ---
    with tab5:
        st.header(f"⚙️ Configuração: {mes_sel}/{ano_sel}")
        c_up1, c_up2 = st.columns(2)
        with c_up1:
            st.subheader("📄 Nova Base")
            up_n = st.file_uploader("Upload Excel", type="xlsx", key="n")
            if up_n and st.button("🚀 Iniciar Mês"):
                df_n = pd.read_excel(up_n)
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']:
                    df_n[c] = "Pendente" if "STATUS" in c else 0
                df_n['ORIGEM'] = "Planilha"
                salvar_dados_op({"analises": df_n.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}, mes_ref)
                st.rerun()
        
        st.divider()
        st.subheader("🆕 Cadastro Manual")
        with st.form("f_manual", clear_on_submit=True):
            f1, f2, f3 = st.columns(3)
            c_cod = f1.text_input("Código").upper()
            c_des = f2.text_input("Descrição")
            c_qtd = f3.number_input("Qtd", min_value=1, value=1)
            if st.form_submit_button("➕ Adicionar"):
                if c_cod and c_des:
                    novo = {"CODIGO": c_cod, "DESCRICAO": c_des, "QUANTIDADE": c_qtd, "STATUS_COMPRA": "Pendente", "STATUS_RECEB": "Pendente", "ORIGEM": "Manual", "QTD_SOLICITADA": 0, "QTD_RECEBIDA": 0, "SALDO_FISICO": 0}
                    db_data["analises"].append(novo)
                    salvar_dados_op(db_data, mes_ref); st.rerun()

    if not db_data.get("analises"):
        st.warning(f"Aguardando dados para {mes_ref}.")
        return

    df_atual = pd.DataFrame(db_data["analises"])

    # --- TAB 1: ESTEIRA DE COMPRAS ---
    with tab1:
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar Item:").upper()
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

    # --- TAB 2: ESTEIRA DE RECEBIMENTO ---
    with tab2:
        pendentes_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
        if not pendentes_rec.empty:
            st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
            q_r = st.text_input("🔍 Buscar no Recebimento:").upper()
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
        else:
            st.success("✅ Tudo recebido!")

    # --- TAB 3: DASHBOARD COMPRAS (Com Ruptura e Planejamento) ---
    with tab3:
        df_proc = df_atual[df_atual['STATUS_COMPRA'] != "Pendente"]
        nao_efet = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
        ruptura = nao_efet[nao_efet['SALDO_FISICO'] == 0]
        estrategico = nao_efet[nao_efet['SALDO_FISICO'] > 0]
        manuais = df_atual[df_atual['ORIGEM'] == 'Manual']

        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"<div class='metric-box'><small>CONFERIDOS</small><h3>{len(df_proc)}</h3></div>", unsafe_allow_html=True)
        k2.markdown(f"<div class='metric-box'><small>RUPTURAS</small><h3 style='color:#ef4444;'>{len(ruptura)}</h3></div>", unsafe_allow_html=True)
        k3.markdown(f"<div class='metric-box'><small>ESTRATÉGICO</small><h3 style='color:#16a34a;'>{len(estrategico)}</h3></div>", unsafe_allow_html=True)
        k4.markdown(f"<div class='metric-box'><small>MANUAIS</small><h3 style='color:#3b82f6;'>{len(manuais)}</h3></div>", unsafe_allow_html=True)

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🔴 Itens em Ruptura (S/ Estoque)")
            if not ruptura.empty:
                st.table(ruptura[['CODIGO', 'DESCRICAO', 'QUANTIDADE']])
                st.download_button("📥 Baixar Ruptura", to_excel(ruptura), "ruptura.xlsx", key="dl_rup")
        with c2:
            st.subheader("🟢 Itens Planejados (C/ Estoque)")
            if not estrategico.empty:
                st.table(estrategico[['CODIGO', 'DESCRICAO', 'SALDO_FISICO']])
                st.download_button("📥 Baixar Planejados", to_excel(estrategico), "planejados.xlsx", key="dl_pla")
        
        if not manuais.empty:
            st.divider()
            st.warning(f"🚩 Foram identificados {len(manuais)} itens manuais nesta operação.")
            with st.expander("🔍 Detalhes dos Itens Manuais"):
                st.dataframe(manuais[['CODIGO', 'DESCRICAO', 'QUANTIDADE']], use_container_width=True)

    # --- TAB 4: DASHBOARD RECEBIMENTO ---
    with tab4:
        renderizar_dashboard_recebimento(df_atual)
        st.divider()
        st.download_button("📥 Baixar Relatório Geral", to_excel(df_atual), f"relatorio_{mes_ref}.xlsx")

# --- DASHBOARD REC AUXILIAR ---
def renderizar_dashboard_recebimento(df):
    encomendados = df[df['QTD_SOLICITADA'] > 0]
    if encomendados.empty:
        st.info("Nenhuma compra efetuada para gerar dados de recebimento.")
        return
    df_rec = encomendados[encomendados['STATUS_RECEB'] != "Pendente"]
    st.subheader("📊 Confronto de Recebimento")
    fig = px.bar(df_rec, x='CODIGO', y=['QTD_SOLICITADA', 'QTD_RECEBIDA'], barmode='group', color_discrete_sequence=['#002366', '#16a34a'])
    st.plotly_chart(fig, use_container_width=True)
