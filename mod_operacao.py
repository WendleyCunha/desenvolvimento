import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime

# --- ESTILO E DADOS ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

def carregar_dados_op():
    fire = inicializar_db()
    doc = fire.collection("config").document("operacao_v2").get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados):
    fire = inicializar_db()
    fire.collection("config").document("operacao_v2").set(dados)

# --- TRATATIVA DE COMPRA (CORRIGIDA) ---
def renderizar_tratativa(item, index, df_completo, db_data, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Código: {item['CODIGO']} | Quantidade em Lista: {item['QUANTIDADE']}")
    
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, key=f"sld_{index}_{key_suffix}")
    
    c1, c2, c3 = st.columns(3)
    
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data); st.rerun()

    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True

    if c3.button("❌ ZERAR", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Zerado"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data); st.rerun()

    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]
            salvar_dados_op(db_data); st.rerun()

# --- ABA DASHBOARD (CORRIGIDA) ---
def renderizar_dashboard(df):
    if df.empty: 
        st.info("Aguardando dados para o Dashboard.")
        return

    st.markdown("### 📈 Confronto Operacional")
    
    # Métricas
    m1, m2, m3, m4 = st.columns(4)
    total_lista = df['QUANTIDADE'].sum()
    total_encomendado = df['QTD_SOLICITADA'].sum()
    total_recebido = df['QTD_RECEBIDA'].sum()
    total_estoque = df['SALDO_FISICO'].sum()

    m1.markdown(f"<div class='metric-box'><small>EM LISTA</small><h3>{total_lista}</h3></div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='metric-box'><small>SALDO FÍSICO</small><h3>{total_estoque}</h3></div>", unsafe_allow_html=True)
    m3.markdown(f"<div class='metric-box'><small>ENCOMENDADO</small><h3 style='color:#002366;'>{total_encomendado}</h3></div>", unsafe_allow_html=True)
    m4.markdown(f"<div class='metric-box'><small>RECEBIDO</small><h3 style='color:#16a34a;'>{total_recebido}</h3></div>", unsafe_allow_html=True)

    # Gráfico de Confronto
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['CODIGO'][:15], y=df['QUANTIDADE'][:15], name='Lista Original', marker_color='#cbd5e1'))
    fig.add_trace(go.Bar(x=df['CODIGO'][:15], y=df['SALDO_FISICO'][:15], name='Saldo Físico', marker_color='#94a3b8'))
    fig.add_trace(go.Bar(x=df['CODIGO'][:15], y=df['QTD_SOLICITADA'][:15], name='Encomenda', marker_color='#002366'))
    
    fig.update_layout(barmode='group', title="Top 15 Itens: Planejado vs Realidade", height=400)
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
                df_up['STATUS_COMPRA'] = "Pendente"
                df_up['QTD_SOLICITADA'] = 0
                df_up['SALDO_FISICO'] = 0
                df_up['QTD_RECEBIDA'] = 0
                df_up['STATUS_RECEB'] = "Aguardando"
                db_data["analises"] = df_up.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()
            return

        df_c = pd.DataFrame(db_data["analises"])

        # Busca Individual
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar Item (Código ou Descrição):").upper()
        if q:
            it_busca = df_c[df_c['CODIGO'].str.contains(q) | df_c['DESCRICAO'].str.contains(q)]
            for i, r in it_busca.iterrows():
                with st.container(border=True):
                    renderizar_tratativa(r, i, df_c, db_data, "busca")
        st.markdown('</div>', unsafe_allow_html=True)

        # Esteira
        idx_s = db_data.get("idx_solic", 0)
        # Pula itens já tratados
        while idx_s < len(df_c) and df_c.iloc[idx_s]['STATUS_COMPRA'] != "Pendente":
            idx_s += 1
        
        db_data["idx_solic"] = idx_s # Atualiza o ponteiro

        if idx_s < len(df_c):
            st.subheader(f"🚀 Esteira (Item {idx_s + 1} de {len(df_c)})")
            with st.container():
                st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                renderizar_tratativa(df_c.iloc[idx_s], idx_s, df_c, db_data, "esteira")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.success("Toda a lista de compras foi processada!")
            if st.button("Reiniciar Esteira"):
                db_data["idx_solic"] = 0; salvar_dados_op(db_data); st.rerun()

    # --- ABA 2: RECEBIMENTO ---
    with tab2:
        df_r = pd.DataFrame(db_data["analises"])
        # Apenas itens encomendados que ainda não foram recebidos totalmente
        pendentes_rec = df_r[(df_r['QTD_SOLICITADA'] > 0) & (df_r['STATUS_RECEB'] == "Aguardando")].reset_index()
        
        if not pendentes_rec.empty:
            idx_r = db_data.get("idx_receb", 0)
            if idx_r >= len(pendentes_rec): idx_r = 0 # Reset de segurança
            
            item_r = pendentes_rec.iloc[idx_r]
            orig_idx = item_r['index']

            st.markdown(f"""<div class='main-card' style='border-top-color:#16a34a;'>
                <h3>Conferindo: {item_r['DESCRICAO']}</h3>
                <p>Cód: {item_r['CODIGO']} | <b>Esperado: {item_r['QTD_SOLICITADA']}</b></p>
            </div>""", unsafe_allow_html=True)

            rc1, rc2, rc3 = st.columns(3)
            if rc1.button("🟢 RECEBIDO TOTAL", use_container_width=True):
                df_r.at[orig_idx, 'STATUS_RECEB'] = "Recebido Total"
                df_r.at[orig_idx, 'QTD_RECEBIDA'] = item_r['QTD_SOLICITADA']
                db_data["analises"] = df_r.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()

            if rc2.button("🟡 RECEBIDO PARCIAL", use_container_width=True):
                st.session_state[f"rec_p_{orig_idx}"] = True
            
            if rc3.button("🔴 NÃO RECEBIDO", use_container_width=True):
                df_r.at[orig_idx, 'STATUS_RECEB'] = "Faltou"
                df_r.at[orig_idx, 'QTD_RECEBIDA'] = 0
                db_data["analises"] = df_r.to_dict(orient='records')
                salvar_dados_op(db_data); st.rerun()

            if st.session_state.get(f"rec_p_{orig_idx}"):
                rqtd = st.number_input("Qtd Real Recebida:", min_value=0, max_value=int(item_r['QTD_SOLICITADA']))
                if st.button("Confirmar Recebimento"):
                    df_r.at[orig_idx, 'STATUS_RECEB'] = "Recebido Parcial"
                    df_r.at[orig_idx, 'QTD_RECEBIDA'] = rqtd
                    db_data["analises"] = df_r.to_dict(orient='records')
                    del st.session_state[f"rec_p_{orig_idx}"]
                    salvar_dados_op(db_data); st.rerun()
        else:
            st.info("Nenhum item pendente de recebimento no momento.")

    # --- ABA 3: DASHBOARD ---
    with tab3:
        renderizar_dashboard(pd.DataFrame(db_data["analises"]))
        if st.button("🗑️ LIMPAR TUDO (Novo Ciclo)"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0})
            st.rerun()
