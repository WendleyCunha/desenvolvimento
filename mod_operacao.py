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
        .search-box-rec {{ background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[2]}; margin-bottom: 20px; }}
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 20px; }}
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "absenteismo": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

# =========================================================
# 2. COMPONENTES DE TRATATIVA (COMPRAS/RECEBIMENTO)
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

# =========================================================
# 3. DASHBOARDS COMPRAS & AUDITORIA
# =========================================================
def renderizar_dashboards_compras_completo(df):
    if df.empty: return
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    itens_conferidos = len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    
    st.subheader("📊 Performance de Compras")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("CONFERÊNCIA", itens_conferidos)
    k2.metric("COMPRAS OK", compras_ok)
    k3.metric("ESTRATÉGICO", len(df_proc[df_proc['SALDO_FISICO'] > 0]))
    k4.metric("RUPTURA", len(df_proc[df_proc['SALDO_FISICO'] == 0]))

    c1, c2 = st.columns(2)
    with c1:
        st_counts = df['STATUS_COMPRA'].value_counts().reset_index()
        st_counts.columns = ['Status', 'Qtd']
        st.plotly_chart(px.pie(st_counts, values='Qtd', names='Status', title="Decisões de Compra", hole=0.4, color_discrete_sequence=PALETA), use_container_width=True)
    with c2:
        df_nao = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
        fig_rup = go.Figure(data=[
            go.Bar(name='Com Estoque', x=['Não Efetuadas'], y=[len(df_nao[df_nao['SALDO_FISICO'] > 0])], marker_color='#16a34a'),
            go.Bar(name='Sem Estoque', x=['Não Efetuadas'], y=[len(df_nao[df_nao['SALDO_FISICO'] == 0])], marker_color='#ef4444')
        ])
        fig_rup.update_layout(barmode='group', height=350, title="Motivo das Não Encomendas")
        st.plotly_chart(fig_rup, use_container_width=True)

# =========================================================
# 4. DASH OPERAÇÃO (PICOS & ABS)
# =========================================================
def renderizar_picos_operacional(db_picos):
    if not db_picos:
        st.info("💡 Sem dados de picos."); return
    df = normalizar_picos(pd.DataFrame(db_picos))
    
    dias_disponiveis = sorted(df['DATA'].unique())
    dias_selecionados = st.multiselect("Filtrar Dias:", dias_disponiveis, default=dias_disponiveis)
    
    if not dias_selecionados: return
    df_f = df[df['DATA'].isin(dias_selecionados)]
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    st.markdown("#### 🔥 Mapa de Calor (Temperatura de Chamados)")
    fig_heat = px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias}, color_continuous_scale=["#ADD8E6", "#FF4500"], text_auto=True)
    st.plotly_chart(fig_heat, use_container_width=True)

# =========================================================
# 5. ESTRUTURA UNIFICADA (CORRIGIDA)
# =========================================================
def exibir_operacao_completa(user_role=None): # user_role adicionado para evitar erro no main.py
    aplicar_estilo_premium()
    
    # Barra Lateral
    st.sidebar.title("📅 Gestão Mensal")
    mes_sel = st.sidebar.selectbox("Mês", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"], index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    tab_compras, tab_operacao, tab_config = st.tabs(["🛒 COMPRAS", "📊 DASH OPERAÇÃO", "⚙️ CONFIGURAÇÕES"])

    with tab_compras:
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD", "📈 AUDITORIA"])
        
        with t1: # Aba Compras (Esteira e Busca)
            if df_atual.empty: st.warning("Sem dados. Vá em CONFIGURAÇÕES.")
            else:
                st.markdown('<div class="search-box">', unsafe_allow_html=True)
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq")
                st.markdown('</div>', unsafe_allow_html=True)
                
                idx_s = 0
                while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
                if idx_s < len(df_atual):
                    st.subheader(f"🚀 Esteira ({idx_s + 1}/{len(df_atual)})")
                    with st.container():
                        st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                        renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "main")
                        st.markdown("</div>", unsafe_allow_html=True)

        with t2: # Recebimento
            pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
            if not pend_rec.empty:
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "main_r")
                st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Tudo recebido.")

        with t3: # Dashboard
            renderizar_dashboards_compras_completo(df_atual)

        with t4: # Auditoria e Exportação (FUNÇÕES RESTAURADAS)
            if not df_atual.empty:
                st.subheader("🔍 Detalhamento de Auditoria")
                itens_manuais = df_atual[df_atual.get('ORIGEM') == 'Manual']
                if not itens_manuais.empty: st.warning(f"🚩 ALERTA: {len(itens_manuais)} itens manuais identificados.")
                
                col1, col2 = st.columns(2)
                with col1:
                    with st.expander("🟢 ESTRATÉGICO (Com Estoque)"):
                        st.dataframe(df_atual[df_atual['SALDO_FISICO'] > 0], use_container_width=True)
                with col2:
                    with st.expander("🔴 RUPTURA (Sem Estoque)"):
                        st.dataframe(df_atual[df_atual['SALDO_FISICO'] <= 0], use_container_width=True)
                
                st.download_button("📊 Baixar Relatório", df_atual.to_csv(index=False).encode('utf-8'), f"Relatorio_{mes_ref}.csv")

    with tab_operacao:
        st.markdown(f"<div class='header-analise'>DASH OPERAÇÃO - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        renderizar_picos_operacional(db_data.get("picos", []))

    with tab_config:
        st.markdown("<div class='header-analise'>CONFIGURAÇÕES</div>", unsafe_allow_html=True)
        
        # CADASTRO MANUAL (RESTAURADO)
        with st.container(border=True):
            st.subheader("🆕 Cadastro Manual de Item")
            with st.form("form_manual", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 2, 1])
                f_cod = c1.text_input("Código")
                f_desc = c2.text_input("Descrição")
                f_qtd = c3.number_input("Qtd", 1)
                if st.form_submit_button("➕ Adicionar"):
                    novo = {"CODIGO": f_cod, "DESCRICAO": f_desc, "QUANTIDADE": f_qtd, "ORIGEM": "Manual", "STATUS_COMPRA": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "STATUS_RECEB": "Pendente", "QTD_RECEBIDA": 0}
                    df_atual = pd.concat([df_atual, pd.DataFrame([novo])], ignore_index=True)
                    db_data["analises"] = df_atual.to_dict(orient='records')
                    salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        # UPLOADS
        up_c = st.file_uploader("Importar Planilha Compras (Excel)", type="xlsx")
        if up_c and st.button("Salvar Base Compras"):
            df_n = pd.read_excel(up_c); df_n['ORIGEM'] = 'Planilha'
            for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'STATUS_RECEB', 'QTD_RECEBIDA']: df_n[c] = "Pendente" if "STATUS" in c else 0
            db_data["analises"] = df_n.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

        up_p = st.file_uploader("Importar Base Picos (Excel)", type="xlsx")
        if up_p and st.button("Salvar Base Picos"):
            db_data["picos"] = pd.read_excel(up_p).to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
