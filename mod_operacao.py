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
        st.plotly_chart(px.pie(st_counts, values='Qtd', names='Status', title="Decisões", hole=0.4, color_discrete_sequence=PALETA), use_container_width=True)
    with c2:
        # Auditoria de Motivos
        df_nao = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
        fig_rup = go.Figure(data=[
            go.Bar(name='Com Estoque', x=['Não Efetuadas'], y=[len(df_nao[df_nao['SALDO_FISICO'] > 0])], marker_color='#16a34a'),
            go.Bar(name='Sem Estoque', x=['Não Efetuadas'], y=[len(df_nao[df_nao['SALDO_FISICO'] == 0])], marker_color='#ef4444')
        ])
        fig_rup.update_layout(barmode='group', height=350, title="Motivo Não Compra")
        st.plotly_chart(fig_rup, use_container_width=True)

# =========================================================
# 4. DASH OPERAÇÃO (PICOS, DIMENSIONAMENTO, ABS)
# =========================================================
def renderizar_picos_operacional(db_picos):
    if not db_picos:
        st.info("💡 Sem dados de picos."); return
    df = normalizar_picos(pd.DataFrame(db_picos))
    
    # Filtro de Dias (Restaurado)
    dias_disponiveis = sorted(df['DATA'].unique())
    if "todos_sel" not in st.session_state: st.session_state.todos_sel = True
    c_btn, c_sel = st.columns([1, 4])
    if c_btn.button("Marcar/Desmarcar Todos"): st.session_state.todos_sel = not st.session_state.todos_sel; st.rerun()
    dias_selecionados = c_sel.multiselect("Filtro de Dias:", dias_disponiveis, default=dias_disponiveis if st.session_state.todos_sel else [])
    
    if not dias_selecionados: return
    df_f = df[df['DATA'].isin(dias_selecionados)]
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    st.markdown("#### 🔥 Mapa de Calor")
    fig_heat = px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias}, color_continuous_scale=["#ADD8E6", "#FF4500"], text_auto=True)
    st.plotly_chart(fig_heat, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(px.bar(df_f.groupby('HORA')['TICKETS'].sum().reset_index(), x='HORA', y='TICKETS', title="Por Hora", text_auto=True), use_container_width=True)
    with col2:
        st.plotly_chart(px.bar(df_f.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna(), x='DIA_SEMANA', y='TICKETS', title="Por Dia", text_auto=True), use_container_width=True)

def renderizar_dimensionamento_abs(db_data, mes_ref):
    if "absenteismo" not in db_data: db_data["absenteismo"] = []
    with st.form("form_abs"):
        c1, c2, c3 = st.columns([2, 2, 1])
        dt = c1.date_input("Data")
        nome = c2.text_input("Colaborador")
        tp = c3.selectbox("Tipo", ["Falta", "Atraso", "Atestado"])
        if st.form_submit_button("Registrar Ocorrência"):
            db_data["absenteismo"].append({"DATA": dt.strftime("%d/%m/%Y"), "COLABORADOR": nome, "TIPO": tp})
            salvar_dados_op(db_data, mes_ref); st.rerun()
    if db_data["absenteismo"]:
        st.dataframe(pd.DataFrame(db_data["absenteismo"]), use_container_width=True)

# =========================================================
# 5. ESTRUTURA PRINCIPAL UNIFICADA
# =========================================================
def exibir_operacao_completa():
    aplicar_estilo_premium()
    st.sidebar.title("📅 Gestão Mensal")
    mes_sel = st.sidebar.selectbox("Mês", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"], index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    tab_compras, tab_operacao, tab_config = st.tabs(["🛒 COMPRAS", "📊 DASH OPERAÇÃO", "⚙️ CONFIGURAÇÕES"])

    with tab_compras:
        st.markdown(f"<div class='header-analise'>GESTÃO DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        tab1, tab2, tab3, tab4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 AUDITORIA"])
        
        with tab1: # Compras
            if df_atual.empty: st.warning("Sem dados.")
            else:
                q = st.text_input("🔍 Localizar Item:").upper()
                it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)] if q else df_atual.head(1)
                for i, r in it_b.iterrows():
                    with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "c")
        
        with tab2: # Recebimento
            pend = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
            if not pend.empty:
                renderizar_tratativa_recebimento(pend.iloc[0], pend.iloc[0]['index'], df_atual, db_data, mes_ref, "r")
            else: st.success("✅ Tudo recebido.")

        with tab3: # Dashboard
            renderizar_dashboards_compras_completo(df_atual)

        with tab4: # Auditoria (Funções Restauradas)
            if not df_atual.empty:
                itens_manuais = df_atual[df_atual.get('ORIGEM') == 'Manual']
                if not itens_manuais.empty: st.warning(f"🚩 {len(itens_manuais)} itens manuais identificados.")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    with st.expander("🟢 COM ESTOQUE (Estratégico)"):
                        st.dataframe(df_atual[df_atual['SALDO_FISICO'] > 0], use_container_width=True)
                with col_b:
                    with st.expander("🔴 SEM ESTOQUE (Ruptura)"):
                        st.dataframe(df_atual[df_atual['SALDO_FISICO'] == 0], use_container_width=True)
                
                st.download_button("📊 Exportar CSV", df_atual.to_csv(index=False).encode('utf-8'), "relatorio.csv")

    with tab_operacao:
        st.markdown(f"<div class='header-analise'>DASH OPERAÇÃO - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        sub1, sub2, sub3 = st.tabs(["🔥 Picos de Demanda", "📏 Dimensionamento", "🤒 ABS/Faltas"])
        with sub1: renderizar_picos_operacional(db_data.get("picos", []))
        with sub2:
            if db_data.get("picos"):
                prod = st.slider("Atendimentos/Hora", 1, 10, 4)
                df_p = normalizar_picos(pd.DataFrame(db_data["picos"]))
                df_dim = df_p.groupby('HORA')['TICKETS'].mean().reset_index()
                df_dim['Staff'] = (df_dim['TICKETS'] / prod).apply(np.ceil)
                st.plotly_chart(px.line(df_dim, x='HORA', y='Staff', title="Equipe Necessária", markers=True))
        with sub3: renderizar_dimensionamento_abs(db_data, mes_ref)

    with tab_config:
        st.subheader("⚙️ Configurações e Cadastro Manual")
        # Cadastro Manual Restaurado
        with st.form("cad_manual"):
            c1, c2, c3 = st.columns([1, 2, 1])
            c_cod = c1.text_input("Código")
            c_desc = c2.text_input("Descrição")
            c_qtd = c3.number_input("Qtd", 1)
            if st.form_submit_button("➕ Adicionar Manualmente"):
                novo = {"CODIGO": c_cod, "DESCRICAO": c_desc, "QUANTIDADE": c_qtd, "ORIGEM": "Manual", "STATUS_COMPRA": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "STATUS_RECEB": "Pendente", "QTD_RECEBIDA": 0}
                df_atual = pd.concat([df_atual, pd.DataFrame([novo])], ignore_index=True)
                db_data["analises"] = df_atual.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        c_up1, c_up2 = st.columns(2)
        with c_up1:
            up_c = st.file_uploader("Upload Compras", type="xlsx")
            if up_c and st.button("Salvar Compras"):
                df_n = pd.read_excel(up_c); df_n['ORIGEM'] = 'Planilha'
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'STATUS_RECEB', 'QTD_RECEBIDA']: df_n[c] = "Pendente" if "STATUS" in c else 0
                db_data["analises"] = df_n.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
        with c_up2:
            up_p = st.file_uploader("Upload Picos", type="xlsx")
            if up_p and st.button("Salvar Picos"):
                db_data["picos"] = pd.read_excel(up_p).to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
