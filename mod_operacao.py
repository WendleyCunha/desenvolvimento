import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime

# --- CONFIGURAÇÃO E DADOS ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        .search-box-rec { background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid #16a34a; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

def carregar_dados_op():
    fire = inicializar_db()
    doc = fire.collection("config").document("operacao_v2").get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados):
    fire = inicializar_db()
    fire.collection("config").document("operacao_v2").set(dados)

# --- [NOVA] FUNÇÃO DE TRATATIVA DE RECEBIMENTO ---
def renderizar_tratativa_recebimento(item, index, df_completo, db_data, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado na Encomenda: {item['QTD_SOLICITADA']}**")
    
    rc1, rc2, rc3 = st.columns(3)
    
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"
        df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data); st.rerun()

    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True

    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"
        df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data); st.rerun()

    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        qtd_r = rp1.number_input("Qtd Real Recebida:", min_value=0, max_value=int(item['QTD_SOLICITADA']), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"
            df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_rec_p_{index}_{key_suffix}"]
            salvar_dados_op(db_data); st.rerun()

# --- TRATATIVA DE COMPRA (MANTIDA) ---
def renderizar_tratativa_compra(item, index, df_completo, db_data, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"; df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data); st.rerun()

    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True

    if c3.button("❌ ZERAR", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Zerado"; df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data); st.rerun()

    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data); st.rerun()

# --- DASHBOARD ---
def renderizar_dashboard(df):
    if df.empty: return
    m1, m2, m3, m4 = st.columns(4)
    total_lista = df['QUANTIDADE'].sum()
    total_encomendado = df['QTD_SOLICITADA'].sum()
    total_recebido = df['QTD_RECEBIDA'].sum()
    total_estoque = df['SALDO_FISICO'].sum()
    m1.markdown(f"<div class='metric-box'><small>EM LISTA</small><h3>{total_lista}</h3></div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='metric-box'><small>SALDO FÍSICO</small><h3>{total_estoque}</h3></div>", unsafe_allow_html=True)
    m3.markdown(f"<div class='metric-box'><small>ENCOMENDADO</small><h3 style='color:#002366;'>{total_encomendado}</h3></div>", unsafe_allow_html=True)
    m4.markdown(f"<div class='metric-box'><small>RECEBIDO</small><h3 style='color:#16a34a;'>{total_recebido}</h3></div>", unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['CODIGO'][:15], y=df['QUANTIDADE'][:15], name='Lista', marker_color='#cbd5e1'))
    fig.add_trace(go.Bar(x=df['CODIGO'][:15], y=df['QTD_SOLICITADA'][:15], name='Encomendado', marker_color='#002366'))
    fig.add_trace(go.Bar(x=df['CODIGO'][:15], y=df['QTD_RECEBIDA'][:15], name='Recebido', marker_color='#16a34a'))
    fig.update_layout(barmode='group', title="Confronto Operacional", height=400)
    st.plotly_chart(fig, use_container_width=True)

# --- EXIBIÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    db_data = carregar_dados_op()
    tab1, tab2, tab3 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD"])

    # --- ABA 1: COMPRAS ---
    with tab1:
        if not db_data.get("analises"):
            up = st.file_uploader("Subir Planilha Base (Excel)", type="xlsx")
            if up:
                df_up = pd.read_excel(up)
                df_up['STATUS_COMPRA'] = "Pendente"; df_up['QTD_SOLICITADA'] = 0
                df_up['SALDO_FISICO'] = 0; df_up['QTD_RECEBIDA'] = 0; df_up['STATUS_RECEB'] = "Aguardando"
                db_data["analises"] = df_up.to_dict(orient='records'); salvar_dados_op(db_data); st.rerun()
            return
        df_c = pd.DataFrame(db_data["analises"])
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar Item na Compra (Cód/Desc):").upper()
        if q:
            it_b = df_c[df_c['CODIGO'].str.contains(q) | df_c['DESCRICAO'].str.contains(q)]
            for i, r in it_b.iterrows():
                with st.container(border=True): renderizar_tratativa_compra(r, i, df_c, db_data, "busca_c")
        st.markdown('</div>', unsafe_allow_html=True)
        idx_s = db_data.get("idx_solic", 0)
        while idx_s < len(df_c) and df_c.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
        db_data["idx_solic"] = idx_s
        if idx_s < len(df_c):
            st.subheader(f"🚀 Esteira Compra ({idx_s + 1}/{len(df_c)})")
            with st.container():
                st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                renderizar_tratativa_compra(df_c.iloc[idx_s], idx_s, df_c, db_data, "esteira_c")
                st.markdown("</div>", unsafe_allow_html=True)

    # --- ABA 2: RECEBIMENTO (COM BUSCA IDÊNTICA) ---
    with tab2:
        df_r = pd.DataFrame(db_data["analises"])
        
        # 1. BUSCA IDENTICA NO RECEBIMENTO
        st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
        q_rec = st.text_input("🔍 Localizar Item no Recebimento (Cód/Desc):").upper()
        if q_rec:
            # Filtra apenas itens que foram ENCOMENDADOS (Qtd_Solicitada > 0)
            it_b_rec = df_r[(df_r['QTD_SOLICITADA'] > 0) & (df_r['CODIGO'].str.contains(q_rec) | df_r['DESCRICAO'].str.contains(q_rec))]
            if it_b_rec.empty:
                st.warning("Nenhum item encomendado encontrado com esse termo.")
            for i, r in it_b_rec.iterrows():
                with st.container(border=True):
                    renderizar_tratativa_recebimento(r, i, df_r, db_data, "busca_r")
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. ESTEIRA DE RECEBIMENTO
        pendentes_rec = df_r[(df_r['QTD_SOLICITADA'] > 0) & (df_r['STATUS_RECEB'] == "Aguardando")].reset_index()
        if not pendentes_rec.empty:
            idx_r = db_data.get("idx_receb", 0)
            # Ajuste caso o índice se perca após uma busca
            if idx_r >= len(pendentes_rec): idx_r = 0 
            
            st.subheader(f"📥 Esteira Recebimento ({idx_r + 1}/{len(pendentes_rec)})")
            item_r = pendentes_rec.iloc[idx_r]
            orig_idx = item_r['index']
            with st.container():
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(item_r, orig_idx, df_r, db_data, "esteira_r")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.success("✅ Todo o recebimento foi conferido!")

    # --- ABA 3: DASHBOARD ---
    with tab3:
        renderizar_dashboard(pd.DataFrame(db_data["analises"]))
        if st.button("🗑️ RESETAR SISTEMA (Novo Lote)"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}); st.rerun()
