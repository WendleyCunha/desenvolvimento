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

def carregar_dados_op():
    fire = inicializar_db()
    doc = fire.collection("config").document("operacao_v2").get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados):
    fire = inicializar_db()
    fire.collection("config").document("operacao_v2").set(dados)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# --- TRATATIVAS ---
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
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"; df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data); st.rerun()

# --- DASHBOARD INTEGRADO ---
def renderizar_dashboard(df):
    if df.empty: return
    
    # KPIs de Compra
    total_itens = len(df)
    proc = df[df['STATUS_COMPRA'] != "Pendente"]
    nao_efet_est = proc[(proc['STATUS_COMPRA'] == "Não Efetuada") & (proc['SALDO_FISICO'] > 0)]
    nao_efet_rup = proc[(proc['STATUS_COMPRA'] == "Não Efetuada") & (proc['SALDO_FISICO'] == 0)]
    
    st.subheader("🛒 Performance de Compras")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{len(proc)}/{total_itens}</h3></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-box'><small>ESTRATÉGICO (C/ ESTOQUE)</small><h3 style='color:#16a34a;'>{len(nao_efet_est)} itens</h3></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-box'><small>RUPTURA (S/ ESTOQUE)</small><h3 style='color:#ef4444;'>{len(nao_efet_rup)} itens</h3></div>", unsafe_allow_html=True)

    # Botões de Exportação Específicos
    e1, e2 = st.columns(2)
    if not nao_efet_est.empty:
        e1.download_button("📥 Baixar Lista Estratégica", data=to_excel(nao_efet_est), file_name="estrategico_estoque.xlsx", use_container_width=True)
    if not nao_efet_rup.empty:
        e2.download_button("📥 Baixar Lista Ruptura", data=to_excel(nao_efet_rup), file_name="alerta_ruptura.xlsx", use_container_width=True)

    st.divider()

    # KPIs de Recebimento
    st.subheader("📥 Eficiência de Recebimento")
    encomendados = df[df['QTD_SOLICITADA'] > 0]
    rec_ok = encomendados[encomendados['STATUS_RECEB'].str.contains("Recebido", na=False)]
    
    r1, r2, r3 = st.columns(3)
    r1.markdown(f"<div class='metric-box'><small>TOTAL ENCOMENDADO</small><h3>{encomendados['QTD_SOLICITADA'].sum()} un</h3></div>", unsafe_allow_html=True)
    r2.markdown(f"<div class='metric-box'><small>TOTAL RECEBIDO</small><h3 style='color:#16a34a;'>{encomendados['QTD_RECEBIDA'].sum()} un</h3></div>", unsafe_allow_html=True)
    
    quebra = encomendados['QTD_SOLICITADA'].sum() - encomendados['QTD_RECEBIDA'].sum()
    r3.markdown(f"<div class='metric-box'><small>QUEBRA (NÃO ENTREGUE)</small><h3 style='color:#ef4444;'>{quebra} un</h3></div>", unsafe_allow_html=True)

    # Gráfico de Funil Operacional
    fig = go.Figure(go.Funnel(
        y = ["Lista Inicial", "Encomendado", "Recebido"],
        x = [df['QUANTIDADE'].sum(), encomendados['QTD_SOLICITADA'].sum(), encomendados['QTD_RECEBIDA'].sum()],
        textinfo = "value+percent initial",
        marker = {"color": ["#cbd5e1", "#002366", "#16a34a"]}
    ))
    fig.update_layout(title="Fluxo de Mercadoria: Da Lista ao Estoque Real")
    st.plotly_chart(fig, use_container_width=True)

# --- EXIBIÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    db_data = carregar_dados_op()
    tab1, tab2, tab3 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD"])

    with tab1: # ABA COMPRAS (Igual anterior com nome corrigido)
        if not db_data.get("analises"):
            up = st.file_uploader("Subir Planilha Base", type="xlsx")
            if up:
                df_up = pd.read_excel(up)
                df_up['STATUS_COMPRA'] = "Pendente"; df_up['QTD_SOLICITADA'] = 0
                df_up['SALDO_FISICO'] = 0; df_up['QTD_RECEBIDA'] = 0; df_up['STATUS_RECEB'] = "Aguardando"
                db_data["analises"] = df_up.to_dict(orient='records'); salvar_dados_op(db_data); st.rerun()
            return
        
        df_c = pd.DataFrame(db_data["analises"])
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar Item na Compra:").upper()
        if q:
            it_b = df_c[df_c['CODIGO'].astype(str).str.contains(q) | df_c['DESCRICAO'].astype(str).str.contains(q)]
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

    with tab2: # ABA RECEBIMENTO (Agora em formato Esteira)
        df_r = pd.DataFrame(db_data["analises"])
        
        # Filtra apenas o que foi efetivamente encomendado e ainda está aguardando
        pendentes_rec = df_r[(df_r['QTD_SOLICITADA'] > 0) & (df_r['STATUS_RECEB'] == "Aguardando")].reset_index()
        
        if not pendentes_rec.empty:
            idx_r = db_data.get("idx_receb", 0)
            if idx_r >= len(pendentes_rec): idx_r = 0
            
            st.subheader(f"📥 Esteira Recebimento ({idx_r + 1}/{len(pendentes_rec)})")
            item_r = pendentes_rec.iloc[idx_r]
            with st.container():
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(item_r, item_r['index'], df_r, db_data, "esteira_r")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.success("✅ Tudo o que foi encomendado já foi conferido no recebimento!")

    with tab3:
        renderizar_dashboard(pd.DataFrame(db_data["analises"]))
        if st.button("🗑️ RESETAR SISTEMA"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}); st.rerun()
