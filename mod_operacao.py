import streamlit as st
import pandas as pd
import numpy as np
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
        .main-card {{ background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .metric-box {{ background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }}
        .metric-box h3 {{ margin: 5px 0; font-size: 1.8rem; font-weight: bold; color: {PALETA[0]}; }}
        .search-box {{ background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 20px; }}
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

# =========================================================
# 2. COMPONENTES DE TRATATIVA
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
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=int(item.get('QTD_SOLICITADA', 1)), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"; df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 3. ESTRUTURA PRINCIPAL
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    
    st.sidebar.title("📅 Gestão Mensal")
    mes_sel = st.sidebar.selectbox("Mês", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"], index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    # --- BLINDAGEM DO DATAFRAME (Resolve o KeyError) ---
    if db_data.get("analises"):
        df_atual = pd.DataFrame(db_data["analises"])
        colunas_necessarias = {
            'STATUS_COMPRA': 'Pendente',
            'QTD_SOLICITADA': 0,
            'SALDO_FISICO': 0,
            'STATUS_RECEB': 'Pendente',
            'QTD_RECEBIDA': 0,
            'ORIGEM': 'Planilha'
        }
        for col, default in colunas_necessarias.items():
            if col not in df_atual.columns:
                df_atual[col] = default
    else:
        df_atual = pd.DataFrame()

    tab_compras, tab_picos, tab_config = st.tabs(["🛒 COMPRAS", "📊 DASH OPERAÇÃO", "⚙️ CONFIGURAÇÕES"])

    # --- ABA 1: COMPRAS ---
    with tab_compras:
        st.markdown(f"<div class='header-analise'>COMPRAS E RECEBIMENTO - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 PERFORMANCE", "📈 AUDITORIA"])
        
        with t1: # Processo de Compras
            if df_atual.empty: st.info("Mês sem dados. Importe ou cadastre itens em Configurações.")
            else:
                q = st.text_input("🔍 Buscar Item:").upper()
                if q:
                    res = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in res.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "q")
                
                idx = 0
                while idx < len(df_atual) and df_atual.iloc[idx]['STATUS_COMPRA'] != "Pendente": idx += 1
                if idx < len(df_atual):
                    st.subheader(f"🚀 Próximo da Lista ({idx + 1}/{len(df_atual)})")
                    with st.container():
                        st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                        renderizar_tratativa_compra(df_atual.iloc[idx], idx, df_atual, db_data, mes_ref, "m")
                        st.markdown("</div>", unsafe_allow_html=True)

        with t2: # Recebimento
            if not df_atual.empty:
                pend = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
                if not pend.empty:
                    st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                    renderizar_tratativa_recebimento(pend.iloc[0], pend.iloc[0]['index'], df_atual, db_data, mes_ref, "rec")
                    st.markdown("</div>", unsafe_allow_html=True)
                else: st.success("✅ Nenhum recebimento pendente.")

        with t3: # Dash Compras
            if not df_atual.empty:
                df_p = df_atual[df_atual['STATUS_COMPRA'] != "Pendente"]
                k1, k2, k3 = st.columns(3)
                k1.metric("Itens Conferidos", len(df_p))
                k2.metric("Estratégico (Com Estoque)", len(df_p[df_p['SALDO_FISICO'] > 0]))
                k3.metric("Ruptura (Sem Estoque)", len(df_p[df_p['SALDO_FISICO'] == 0]))
                st.plotly_chart(px.pie(df_atual, names='STATUS_COMPRA', title="Status Geral", color_discrete_sequence=PALETA), use_container_width=True)

        with t4: # Auditoria (Restauração Completa)
            if not df_atual.empty:
                manuais = df_atual[df_atual['ORIGEM'] == 'Manual']
                if not manuais.empty: st.warning(f"🚩 Itens inseridos manualmente: {len(manuais)}")
                st.subheader("Planilha de Auditoria")
                st.dataframe(df_atual, use_container_width=True)
                st.download_button("📥 Baixar Relatório CSV", df_atual.to_csv(index=False).encode('utf-8'), "relatorio.csv")

    # --- ABA 2: PICOS (Restaurada) ---
    with tab_picos:
        if db_data.get("picos"):
            df_picos = normalizar_picos(pd.DataFrame(db_data["picos"]))
            st.plotly_chart(px.density_heatmap(df_picos, x="HORA", y="DIA_SEMANA", z="TICKETS", text_auto=True, title="Mapa de Calor de Chamados", color_continuous_scale="Viridis"), use_container_width=True)
        else: st.info("Importe a planilha do Zendesk nas Configurações.")

    # --- ABA 3: CONFIGURAÇÕES (Cadastro Manual Integrado) ---
    with tab_config:
        st.subheader("🆕 Cadastro Manual")
        with st.form("add_manual", clear_on_submit=True):
            c1, c2, c3 = st.columns([1, 2, 1])
            f_cod = c1.text_input("Código")
            f_des = c2.text_input("Descrição")
            f_qtd = c3.number_input("Qtd", 1)
            if st.form_submit_button("➕ Adicionar à Esteira"):
                novo = {"CODIGO": f_cod, "DESCRICAO": f_des, "QUANTIDADE": f_qtd, "ORIGEM": "Manual", "STATUS_COMPRA": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "STATUS_RECEB": "Pendente", "QTD_RECEBIDA": 0}
                df_atual = pd.concat([df_atual, pd.DataFrame([novo])], ignore_index=True)
                db_data["analises"] = df_atual.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        st.subheader("📂 Importação")
        up_c = st.file_uploader("Planilha Compras (Excel)", type="xlsx")
        if up_c and st.button("Salvar Compras"):
            df_n = pd.read_excel(up_c); df_n['ORIGEM'] = 'Planilha'
            db_data["analises"] = df_n.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
            
        up_p = st.file_uploader("Planilha Zendesk (Excel)", type="xlsx")
        if up_p and st.button("Salvar Picos"):
            db_data["picos"] = pd.read_excel(up_p).to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
