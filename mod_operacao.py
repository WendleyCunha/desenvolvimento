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
    # O documento agora é nomeado com base no mês/ano selecionado
    doc = fire.collection("config").document(f"operacao_{mes_ref}").get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("config").document(f"operacao_{mes_ref}").set(dados)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# --- TRATATIVAS (Mantidas com adição do mes_ref) ---
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

def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"; df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"; df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# --- DASHBOARDS (Funções simplificadas para brevidade, mantêm lógica original) ---
def renderizar_dashboard_compras(df):
    if df.empty: 
        st.info("Sem dados para este mês.")
        return
    # ... (Restante da lógica de dash compras original se mantém aqui)
    st.subheader("📊 Performance de Compras")
    st.dataframe(df.head()) # Placeholder para o dash completo que você já tem

def renderizar_dashboard_recebimento(df):
    if df.empty: return
    # ... (Restante da lógica de dash recebimento original se mantém aqui)
    st.subheader("📊 Performance de Recebimento")

# --- EXIBIÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    
    # Seleção Global de Mês (Sempre visível ou na sidebar)
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_atual = meses[datetime.now().month - 1]
    
    st.sidebar.title("📅 Gestão Mensal")
    mes_sel = st.sidebar.selectbox("Mês de Referência", meses, index=meses.index(mes_atual))
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"

    db_data = carregar_dados_op(mes_ref)
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASH COMPRAS", "📈 DASH RECEBIMENTO", "⚙️ CONFIG"])

    with tab5:
        st.header("⚙️ Configurações e Upload")
        st.info(f"Gerenciando dados de: **{mes_sel}/{ano_sel}**")
        
        up = st.file_uploader(f"Subir Planilha para {mes_sel}", type=["xlsx", "csv"])
        if up:
            df_up = pd.read_excel(up) if up.name.endswith('xlsx') else pd.read_csv(up)
            
            # Garantir colunas necessárias se for planilha nova
            for col in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']:
                if col not in df_up.columns:
                    df_up[col] = "Pendente" if "STATUS" in col else 0
            
            if st.button("Confirmar Upload e Sobrescrever Mês"):
                db_data = {"analises": df_up.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}
                salvar_dados_op(db_data, mes_ref)
                st.success(f"Dados de {mes_ref} atualizados!")
                st.rerun()

        st.divider()
        if st.button("🗑️ RESETAR MÊS ATUAL"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}, mes_ref)
            st.rerun()

    with tab1:
        if not db_data.get("analises"):
            st.warning(f"Nenhum dado encontrado para {mes_sel}. Vá em Configurações e suba o arquivo.")
        else:
            df_c = pd.DataFrame(db_data["analises"])
            st.markdown('<div class="search-box">', unsafe_allow_html=True)
            q = st.text_input("🔍 Localizar Item:").upper()
            if q:
                it_b = df_c[df_c['CODIGO'].astype(str).str.contains(q) | df_c['DESCRICAO'].astype(str).str.contains(q)]
                for i, r in it_b.iterrows():
                    with st.container(border=True): renderizar_tratativa_compra(r, i, df_c, db_data, mes_ref, "busca_c")
            st.markdown('</div>', unsafe_allow_html=True)
            
            idx_s = db_data.get("idx_solic", 0)
            while idx_s < len(df_c) and df_c.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
            db_data["idx_solic"] = idx_s
            if idx_s < len(df_c):
                st.subheader(f"🚀 Esteira ({idx_s + 1}/{len(df_c)}) - {mes_sel}")
                with st.container():
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_c.iloc[idx_s], idx_s, df_c, db_data, mes_ref, "esteira_c")
                    st.markdown("</div>", unsafe_allow_html=True)

    with tab2:
        if db_data.get("analises"):
            df_r = pd.DataFrame(db_data["analises"])
            pendentes_rec = df_r[(df_r['QTD_SOLICITADA'] > 0) & (df_r['STATUS_RECEB'] == "Pendente")].reset_index()
            
            if not pendentes_rec.empty:
                st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
                q_rec = st.text_input("🔍 Localizar no Recebimento:").upper()
                if q_rec:
                    it_b_rec = pendentes_rec[pendentes_rec['CODIGO'].astype(str).str.contains(q_rec) | pendentes_rec['DESCRICAO'].astype(str).str.contains(q_rec)]
                    for _, r in it_b_rec.iterrows():
                        with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_r, db_data, mes_ref, "busca_r")
                st.markdown('</div>', unsafe_allow_html=True)

                idx_r = db_data.get("idx_receb", 0)
                if idx_r >= len(pendentes_rec): idx_r = 0
                
                st.subheader(f"📥 Recebimento ({idx_r + 1}/{len(pendentes_rec)})")
                item_r = pendentes_rec.iloc[idx_r]
                with st.container():
                    st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                    renderizar_tratativa_recebimento(item_r, item_r['index'], df_r, db_data, mes_ref, "esteira_r")
                    st.markdown("</div>", unsafe_allow_html=True)

    with tab3:
        renderizar_dashboard_compras(pd.DataFrame(db_data["analises"]))

    with tab4:
        renderizar_dashboard_recebimento(pd.DataFrame(db_data["analises"]))
