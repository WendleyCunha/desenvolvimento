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
        </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE SUPORTE ---
def garantir_colunas(df):
    """Proteção contra KeyError: Garante que colunas essenciais existam"""
    colunas_padrao = {
        'STATUS_COMPRA': 'Pendente',
        'QTD_SOLICITADA': 0,
        'SALDO_FISICO': 0,
        'QTD_RECEBIDA': 0,
        'STATUS_RECEB': 'Pendente',
        'QUANTIDADE': 0,
        'CODIGO': 'S/C',
        'DESCRICAO': 'SEM DESCRIÇÃO'
    }
    for col, default in colunas_padrao.items():
        if col not in df.columns:
            df[col] = default
    return df

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

def gerar_excel_auditoria(df):
    output = io.BytesIO()
    # Correção: Use to_excel em vez de to_sheet
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df[df['SALDO_FISICO'] > 0].to_excel(writer, sheet_name='COM ESTOQUE', index=False)
        df[df['SALDO_FISICO'] <= 0].to_excel(writer, sheet_name='RUPTURA', index=False)
        if 'ORIGEM' in df.columns:
            df[df['ORIGEM'] == 'Manual'].to_excel(writer, sheet_name='ITENS MANUAIS', index=False)
    return output.getvalue()

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
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']) if int(item['QUANTIDADE']) > 0 else 1, key=f"val_{index}_{key_suffix}")
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
        max_r = int(item['QTD_SOLICITADA'])
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=max_r if max_r > 0 else 1, key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"; df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 3. DASHBOARDS
# =========================================================
def renderizar_dashboards_compras_completo(df):
    if df.empty: return
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    total_itens, itens_conf = len(df), len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    
    df_nao = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
    n_estoque = len(df_nao[df_nao['SALDO_FISICO'] > 0])
    n_ruptura = len(df_nao[df_nao['SALDO_FISICO'] == 0])

    st.subheader("📊 Performance de Compras")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conf}</h3><p>{(itens_conf/total_itens*100):.1f}%</p></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>COMPRAS OK</small><h3>{compras_ok}</h3></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>ESTRATÉGICO</small><h3 style='color:#16a34a;'>{n_estoque}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>RUPTURA</small><h3 style='color:#ef4444;'>{n_ruptura}</h3></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.pie(df, names='STATUS_COMPRA', title="Decisões de Compra", hole=0.4, color='STATUS_COMPRA', color_discrete_map={'Total': '#002366', 'Parcial': '#3b82f6', 'Não Efetuada': '#ef4444', 'Pendente': '#cbd5e1'})
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig_rup = go.Figure(data=[go.Bar(name='Com Estoque', x=['Não Efetuadas'], y=[n_estoque], marker_color='#16a34a'), go.Bar(name='Sem Estoque', x=['Não Efetuadas'], y=[n_ruptura], marker_color='#ef4444')])
        fig_rup.update_layout(title="Motivo das Não Encomendas", barmode='group'); st.plotly_chart(fig_rup, use_container_width=True)

def renderizar_dashboards_recebimento_completo(df):
    df_f = df[df['QTD_SOLICITADA'] > 0]
    if df_f.empty: st.info("Sem compras para receber."); return
    
    df_proc = df_f[df_f['STATUS_RECEB'] != "Pendente"]
    st.subheader("📊 Performance de Recebimento")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{len(df_proc)}</h3></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>TOTAL OK</small><h3 style='color:#16a34a;'>{len(df_proc[df_proc['STATUS_RECEB']=='Recebido Total'])}</h3></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>DIVERGENTES</small><h3 style='color:#ef4444;'>{len(df_proc[df_proc['STATUS_RECEB']!='Recebido Total'])}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>PENDENTES</small><h3>{len(df_f)-len(df_proc)}</h3></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.pie(df_f, names='STATUS_RECEB', title="Status", hole=0.4), use_container_width=True)
    with c2:
        fig_ac = go.Figure()
        fig_ac.add_trace(go.Bar(name='Solicitado', x=df_f['CODIGO'][:15], y=df_f['QTD_SOLICITADA'][:15], marker_color=PALETA[0]))
        fig_ac.add_trace(go.Bar(name='Recebido', x=df_f['CODIGO'][:15], y=df_f['QTD_RECEBIDA'][:15], marker_color=PALETA[2]))
        fig_ac.update_layout(title="Acuracidade (Top 15)", barmode='group'); st.plotly_chart(fig_ac, use_container_width=True)

# =========================================================
# 4. OPERACIONAL (PICOS)
# =========================================================
def renderizar_picos_operacional(db_picos, db_data, mes_ref):
    if not db_picos: st.info("💡 Sem dados de picos."); return
    tab_picos, tab_dim, tab_abs = st.tabs(["🔥 MAPA DE CALOR", "👥 DIMENSIONAMENTO", "📝 REGISTRO ABS"])
    
    df = normalizar_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    with tab_picos:
        dias_disponiveis = sorted(df['DATA'].unique())
        dias_sel = st.multiselect("Filtrar Dias:", dias_disponiveis, default=dias_disponiveis)
        if dias_sel:
            df_f = df[df['DATA'].isin(dias_sel)]
            fig_h = px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias}, color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_h, use_container_width=True)
            
            c1, c2 = st.columns(2)
            c1.plotly_chart(px.bar(df_f.groupby('HORA')['TICKETS'].sum().reset_index(), x='HORA', y='TICKETS', title="Volume/Hora"), use_container_width=True)
            c2.plotly_chart(px.bar(df_f.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index(), x='DIA_SEMANA', y='TICKETS', title="Volume/Dia"), use_container_width=True)

    with tab_dim:
        meta_hora = st.slider("Atendimentos/Hora por Agente:", 1, 20, 4)
        if dias_sel:
            df_dim = df[df['DATA'].isin(dias_sel)].groupby('HORA')['TICKETS'].mean().reset_index()
            df_dim['STAFF'] = (df_dim['TICKETS'] / meta_hora).apply(lambda x: int(x) + 1 if x % 1 > 0 else int(x))
            st.plotly_chart(px.line(df_dim, x='HORA', y='STAFF', title="Staff Necessário (Média)", markers=True), use_container_width=True)
            
            st.subheader("☕ Sugestão de Pausas")
            pausas = df_dim.sort_values(by='TICKETS').head(3)
            p_cols = st.columns(3)
            for i, (idx, row) in enumerate(pausas.iterrows()):
                p_cols[i].markdown(f"<div class='metric-box'><small>{i+1}ª Opção</small><h3>{int(row['HORA'])}h</h3></div>", unsafe_allow_html=True)

    with tab_abs:
        with st.form("form_abs", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            d_a = c1.date_input("Data"); t_a = c2.selectbox("Tipo", ["Falta", "Atraso", "Atestado"]); n_a = c3.text_input("Nome")
            if st.form_submit_button("Registrar"):
                if "abs" not in db_data: db_data["abs"] = []
                db_data["abs"].append({"data": str(d_a), "tipo": t_a, "nome": n_a.upper()})
                salvar_dados_op(db_data, mes_ref); st.rerun()
        if db_data.get("abs"): st.table(pd.DataFrame(db_data["abs"]))

# =========================================================
# 5. ESTRUTURA PRINCIPAL
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    st.sidebar.title("📅 Gestão")
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses, index=datetime.now().month-1)
    mes_ref = f"{mes_sel}_2025"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = garantir_colunas(pd.DataFrame(db_data["analises"])) if db_data.get("analises") else pd.DataFrame()

    t_compra, t_op, t_cfg = st.tabs(["🛒 COMPRAS", "📊 DASH OPERAÇÃO", "⚙️ CONFIGURAÇÕES"])

    with t_compra:
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        s1, s2, s3, s4 = st.tabs(["🛒 ESTEIRA", "📥 RECEBIMENTO", "📊 DASH COMPRAS", "📈 DASH RECEBIMENTO"])
        
        with s1:
            if df_atual.empty: st.warning("Sem dados.")
            else:
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows(): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "q")
                
                idx = 0
                while idx < len(df_atual) and df_atual.iloc[idx]['STATUS_COMPRA'] != "Pendente": idx += 1
                if idx < len(df_atual):
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_atual.iloc[idx], idx, df_atual, db_data, mes_ref, "m")
                    st.markdown("</div>", unsafe_allow_html=True)

        with s2:
            pend = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
            if not pend.empty:
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(pend.iloc[0], pend.iloc[0]['index'], df_atual, db_data, mes_ref, "r")
                st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("Tudo recebido!")

        with s3:
            renderizar_dashboards_compras_completo(df_atual)
            if not df_atual.empty:
                st.divider()
                st.download_button("📥 Baixar Auditoria Excel", gerar_excel_auditoria(df_atual), f"Auditoria_{mes_ref}.xlsx")
                c1, c2 = st.columns(2)
                c1.expander("🟢 COM ESTOQUE").dataframe(df_atual[df_atual['SALDO_FISICO']>0])
                c2.expander("🔴 RUPTURA").dataframe(df_atual[df_atual['SALDO_FISICO']<=0])

        with s4: renderizar_dashboards_recebimento_completo(df_atual)

    with t_op: renderizar_picos_operacional(db_data.get("picos", []), db_data, mes_ref)

    with t_cfg:
        st.subheader("🆕 Cadastro Manual")
        with st.form("cad"):
            m1, m2, m3 = st.columns([2,3,1])
            c_c = m1.text_input("Cód"); c_d = m2.text_input("Desc"); c_q = m3.number_input("Qtd", 1)
            if st.form_submit_button("Adicionar"):
                novo = {"CODIGO": c_c, "DESCRICAO": c_d, "QUANTIDADE": c_q, "STATUS_COMPRA": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "STATUS_RECEB": "Pendente", "QTD_RECEBIDA": 0, "ORIGEM": "Manual"}
                df_atual = pd.concat([df_atual, pd.DataFrame([novo])], ignore_index=True)
                db_data["analises"] = df_atual.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
        
        st.divider()
        up_c = st.file_uploader("Upload Compras", type="xlsx")
        if up_c and st.button("Salvar Planilha"):
            df_n = pd.read_excel(up_c)
            db_data["analises"] = garantir_colunas(df_n).to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
            
        up_p = st.file_uploader("Upload Picos", type="xlsx")
        if up_p and st.button("Salvar Zendesk"):
            db_data["picos"] = pd.read_excel(up_p).to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

        if st.button("🗑️ RESET TOTAL", type="primary"):
            salvar_dados_op({"analises":[], "picos":[], "abs":[]}, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
