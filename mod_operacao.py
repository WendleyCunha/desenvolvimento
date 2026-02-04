import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io

# --- CONFIGURAÇÃO DE ESTILO ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        .search-box-rec { background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid #16a34a; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE BANCO DE DADOS ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
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

# --- TRATATIVAS (COMPRA E RECEBIMENTO) ---
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
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

# --- DASHBOARDS ---
def renderizar_dashboard_compras(df):
    if df.empty or 'STATUS_COMPRA' not in df.columns:
        st.info("Aguardando dados de análise de compras.")
        return
    
    total_itens = len(df)
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    itens_conferidos = len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    
    st.subheader("📊 Performance de Compras")
    k1, k2, k3 = st.columns(3)
    k1.metric("Itens na Lista", total_itens)
    k2.metric("Conferidos", f"{itens_conferidos} ({ (itens_conferidos/total_itens*100) if total_itens>0 else 0:.1f}%)")
    k3.metric("Efetivados", compras_ok)

    fig = px.pie(df, names='STATUS_COMPRA', title="Status das Compras", hole=0.4,
                 color='STATUS_COMPRA', color_discrete_map={'Total': '#002366', 'Parcial': '#3b82f6', 'Não Efetuada': '#ef4444', 'Pendente': '#cbd5e1'})
    st.plotly_chart(fig, use_container_width=True)

def renderizar_dashboard_recebimento(df):
    if df.empty or 'STATUS_RECEB' not in df.columns:
        st.info("Aguardando dados de recebimento.")
        return
    
    df_rec = df[df['QTD_SOLICITADA'] > 0]
    if df_rec.empty:
        st.warning("Nenhum item foi solicitado para compra ainda.")
        return

    st.subheader("📊 Performance de Recebimento")
    fig_r = px.bar(df_rec, x='CODIGO', y=['QTD_SOLICITADA', 'QTD_RECEBIDA'], 
                   title="Solicitado vs Recebido", barmode='group',
                   color_discrete_sequence=['#002366', '#16a34a'])
    st.plotly_chart(fig_r, use_container_width=True)

# --- INTERFACE PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    
    # Gerenciamento de Meses na Sidebar
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    st.sidebar.title("📅 Gestão")
    mes_sel = st.sidebar.selectbox("Mês", meses, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"

    db_data = carregar_dados_op(mes_ref)
    
    tabs = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARDS", "⚙️ CONFIGURAÇÕES"])

    with tabs[3]: # Aba Configurações
        st.header("⚙️ Configurações de Dados")
        st.write(f"Trabalhando com: **{mes_ref}**")
        
        up = st.file_uploader("Subir Planilha (Nova ou Analisada)", type=["xlsx"])
        if up:
            df_up = pd.read_excel(up)
            # Lista de colunas obrigatórias para o sistema funcionar
            colunas_sistema = {
                'STATUS_COMPRA': 'Pendente',
                'QTD_SOLICITADA': 0,
                'SALDO_FISICO': 0,
                'QTD_RECEBIDA': 0,
                'STATUS_RECEB': 'Pendente'
            }
            # Se a coluna não existir na planilha subida, ela é criada com o valor padrão
            for col, default in colunas_sistema.items():
                if col not in df_up.columns:
                    df_up[col] = default
            
            if st.button("Salvar e Aplicar Planilha"):
                db_data = {"analises": df_up.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}
                salvar_dados_op(db_data, mes_ref)
                st.success("Planilha processada com sucesso!")
                st.rerun()
        
        st.divider()
        if st.button("🗑️ RESETAR MÊS ATUAL"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}, mes_ref)
            st.rerun()

    if not db_data.get("analises"):
        st.warning("⚠️ Nenhuma planilha carregada para este mês. Vá em 'Configurações'.")
        return

    df_atual = pd.DataFrame(db_data["analises"])

    with tabs[0]: # Compras
        st.markdown('<div class="search-box">', unsafe_allow_html=True)
        q = st.text_input("🔍 Localizar Item (Compra):").upper()
        if q:
            it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
            for i, r in it_b.iterrows():
                with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "b_c")
        st.markdown('</div>', unsafe_allow_html=True)

        idx_s = db_data.get("idx_solic", 0)
        while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
        db_data["idx_solic"] = idx_s
        if idx_s < len(df_atual):
            st.subheader(f"🚀 Esteira de Compra ({idx_s + 1}/{len(df_atual)})")
            with st.container():
                st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "est_c")
                st.markdown("</div>", unsafe_allow_html=True)

    with tabs[1]: # Recebimento
        pendentes_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
        if not pendentes_rec.empty:
            q_rec = st.text_input("🔍 Localizar no Recebimento:").upper()
            if q_rec:
                it_b_rec = pendentes_rec[pendentes_rec['CODIGO'].astype(str).str.contains(q_rec) | pendentes_rec['DESCRICAO'].astype(str).str.contains(q_rec)]
                for _, r in it_b_rec.iterrows():
                    with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "b_r")
            
            idx_r = db_data.get("idx_receb", 0)
            if idx_r >= len(pendentes_rec): idx_r = 0
            st.subheader(f"📥 Recebimento ({idx_r + 1}/{len(pendentes_rec)})")
            renderizar_tratativa_recebimento(pendentes_rec.iloc[idx_r], pendentes_rec.iloc[idx_r]['index'], df_atual, db_data, mes_ref, "est_r")
        else:
            st.success("Tudo recebido!")

    with tabs[2]: # Dashboards
        c1, c2 = st.columns(2)
        with c1: renderizar_dashboard_compras(df_atual)
        with c2: renderizar_dashboard_recebimento(df_atual)
        st.divider()
        st.download_button("📥 Baixar Relatório Atualizado", data=to_excel(df_atual), file_name=f"conferencia_{mes_ref}.xlsx")
