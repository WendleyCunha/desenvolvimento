import streamlit as st
import pandas as pd
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
        /* Estilo para os headers de Auditoria */
        .status-header {{ padding: 10px; border-radius: 8px; font-weight: bold; color: white; margin-bottom: 10px; display: flex; align-items: center; gap: 10px; }}
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    return df.rename(columns=mapeamento)

def converter_para_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

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
# 3. DASHBOARDS DE PERFORMANCE
# =========================================================
def renderizar_dashboards_compras_completo(df):
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
        fig_p = px.pie(st_counts, values='Qtd', names='Status', title="Decisões de Compra", hole=0.4, color='Status', color_discrete_map={'Total': '#002366', 'Parcial': '#3b82f6', 'Não Efetuada': '#ef4444', 'Pendente': '#cbd5e1'})
        st.plotly_chart(fig_p, use_container_width=True)
    with c2:
        fig_rup = go.Figure(data=[go.Bar(name='Com Estoque', x=['Não Efetuadas'], y=[len(nao_efet_com_estoque)], marker_color='#16a34a'), go.Bar(name='Sem Estoque', x=['Não Efetuadas'], y=[len(nao_efet_sem_estoque)], marker_color='#ef4444')])
        fig_rup.update_layout(title="Motivo das Não Encomendas", barmode='group', height=400); st.plotly_chart(fig_rup, use_container_width=True)

def renderizar_dashboards_recebimento_ajustado(df):
    if df.empty: return
    df_f = df[df['QTD_SOLICITADA'] > 0]
    if df_f.empty:
        st.info("Nenhuma compra efetuada para analisar recebimento."); return
    total_pedidos = len(df_f)
    df_rec = df_f[df_f['STATUS_RECEB'] != "Pendente"]
    itens_processados = len(df_rec)
    rec_total = len(df_rec[df_rec['STATUS_RECEB'] == "Recebido Total"])
    perc_proc = (itens_processados / total_pedidos * 100) if total_pedidos > 0 else 0
    perc_efici = (rec_total / itens_processados * 100) if itens_processados > 0 else 0

    st.subheader("📥 Performance de Recebimento")
    rk1, rk2, rk3, rk4 = st.columns(4)
    rk1.markdown(f"<div class='metric-box'><small>PROCESSADO</small><h3>{itens_processados}</h3><p>{perc_proc:.1f}%</p></div>", unsafe_allow_html=True)
    rk2.markdown(f"<div class='metric-box'><small>REC. TOTAL</small><h3>{rec_total}</h3><p>{perc_efici:.1f}%</p></div>", unsafe_allow_html=True)
    falta_vol = df_f['QTD_SOLICITADA'].sum() - df_f['QTD_RECEBIDA'].sum()
    rk3.markdown(f"<div class='metric-box'><small>QTD FALTANTE</small><h3 style='color:#ef4444;'>{int(falta_vol)}</h3></div>", unsafe_allow_html=True)
    efi_vol = (df_f['QTD_RECEBIDA'].sum() / df_f['QTD_SOLICITADA'].sum() * 100) if df_f['QTD_SOLICITADA'].sum() > 0 else 0
    rk4.markdown(f"<div class='metric-box'><small>EFICIÊNCIA VOL.</small><h3 style='color:#16a34a;'>{efi_vol:.1f}%</h3></div>", unsafe_allow_html=True)

# =========================================================
# 4. ESTRUTURA UNIFICADA (FIXED AUDITORIA)
# =========================================================
def exibir_operacao_completa():
    aplicar_estilo_premium()
    st.sidebar.title("📅 Gestão Mensal")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=2) # 2026 fixado
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    tab_modulo_compras, tab_modulo_picos, tab_modulo_config = st.tabs(["🛒 COMPRAS", "📊 DASH OPERAÇÃO", "⚙️ CONFIGURAÇÕES"])

    with tab_modulo_compras:
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "🔍 AUDITORIA DE COMPRAS", "📈 DASHBOARD"])
        
        with t1: # Aba de Execução
            if df_atual.empty: st.warning("Sem dados.")
            else:
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq_c")
                
                idx_s = 0
                while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
                if idx_s < len(df_atual):
                    st.subheader(f"🚀 Esteira ({idx_s + 1}/{len(df_atual)})")
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "main_c")
                    st.markdown("</div>", unsafe_allow_html=True)

        with t2: # Aba Recebimento
            pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index() if not df_atual.empty else pd.DataFrame()
            if not pend_rec.empty:
                q_r = st.text_input("🔍 Localizar Recebimento:").upper()
                if q_r:
                    it_r = pend_rec[pend_rec['CODIGO'].astype(str).str.contains(q_r) | pend_rec['DESCRICAO'].astype(str).str.contains(q_r)]
                    for _, r in it_r.iterrows():
                        with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "bq_r")
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "main_r")
                st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Tudo recebido ou nada encomendado.")

        with t3: # ABA AUDITORIA (Ajustada conforme seu print)
            st.markdown("### 🔍 Auditoria de Estoque e Compras")
            if not df_atual.empty:
                # Colunas de exibição simplificada para auditoria
                cols_view = ['GRUPO', 'DESCRICAO', 'STATUS_COMPRA', 'SALDO_FISICO']
                
                c_aud1, c_aud2 = st.columns(2)
                
                with c_aud1:
                    st.markdown('<div class="status-header" style="background:#16a34a;">🟢 COM ESTOQUE</div>', unsafe_allow_html=True)
                    df_com_estoque = df_atual[df_atual['SALDO_FISICO'] > 0]
                    st.dataframe(df_com_estoque[cols_view], hide_index=False, use_container_width=True)
                
                with c_aud2:
                    st.markdown('<div class="status-header" style="background:#ef4444;">🔴 RUPTURA</div>', unsafe_allow_html=True)
                    df_ruptura = df_atual[df_atual['SALDO_FISICO'] <= 0]
                    st.dataframe(df_ruptura[cols_view], hide_index=False, use_container_width=True)
                
                st.divider()
                st.download_button("📥 Baixar Auditoria Completa", data=converter_para_excel(df_atual), file_name=f"Auditoria_{mes_ref}.xlsx")
            else:
                st.info("Carregue uma base para ver a auditoria.")

        with t4: # Dashboards
            renderizar_dashboards_compras_completo(df_atual)
            st.divider()
            renderizar_dashboards_recebimento_ajustado(df_atual)

    # ... (Restante do código de Picos e Configurações permanece o mesmo)
    # [Adicione aqui os blocos tab_modulo_picos e tab_modulo_config do código original]

if __name__ == "__main__":
    exibir_operacao_completa()
