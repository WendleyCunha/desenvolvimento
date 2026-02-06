import streamlit as st
import pandas as pd
import numpy as np  # Necessário para os cálculos de dimensionamento
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
# 3. DASHBOARDS DE PERFORMANCE (COMPRAS)
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

# =========================================================
# 4. DASHBOARD DE PICOS E DIMENSIONAMENTO (COMPLETO)
# =========================================================

def renderizar_picos_operacional(db_picos):
    if not db_picos:
        st.info("💡 Sem dados de picos. Importe a planilha do Zendesk na aba CONFIGURAÇÕES."); return
    
    df = normalizar_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    st.markdown("### 📅 Filtro de Dias")
    dias_disponiveis = sorted(df['DATA'].unique())
    
    # Controle de seleção total
    if "todos_sel" not in st.session_state: st.session_state.todos_sel = True
    c_btn, c_sel = st.columns([1, 4])
    if c_btn.button("Marcar/Desmarcar Todos"): 
        st.session_state.todos_sel = not st.session_state.todos_sel
        st.rerun()
        
    dias_selecionados = c_sel.multiselect("Selecione os dias:", dias_disponiveis, 
                                          default=dias_disponiveis if st.session_state.todos_sel else [])
    
    if not dias_selecionados: return
    df_f = df[df['DATA'].isin(dias_selecionados)]
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    # --- 1. GRÁFICO DE TEMPERATURA (HEATMAP) ---
    st.markdown("#### 🔥 Mapa de Calor (Temperatura de Chamados)")
    cores_suaves = ["#ADD8E6", "#FFFFE0", "#FFD700", "#FF8C00", "#FF4500"]

    fig_heat = px.density_heatmap(
        df_f, 
        x="HORA", 
        y="DIA_SEMANA", 
        z="TICKETS", 
        category_orders={"DIA_SEMANA": ordem_dias},
        color_continuous_scale=cores_suaves, 
        text_auto=True,
        labels={'HORA': 'Hora do Dia', 'DIA_SEMANA': 'Dia da Semana', 'TICKETS': 'Volume'}
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # --- 2 e 3. GRÁFICOS DE BARRAS (DENTRO DA FUNÇÃO PICOS) ---
    col1, col2 = st.columns(2)
    with col1:
        df_h = df_f.groupby('HORA')['TICKETS'].sum().reset_index()
        fig_h = px.bar(df_h, x='HORA', y='TICKETS', title="Volume Total por Hora", text_auto=True, color_discrete_sequence=[PALETA[0]])
        fig_h.update_traces(textposition='outside')
        st.plotly_chart(fig_h, use_container_width=True, key="graf_hora_picos") # Key única
    with col2:
        df_d = df_f.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna()
        fig_d = px.bar(df_d, x='DIA_SEMANA', y='TICKETS', title="Volume Total por Dia", text_auto=True, color_discrete_sequence=[PALETA[1]])
        fig_d.update_traces(textposition='outside')
        st.plotly_chart(fig_d, use_container_width=True, key="graf_dia_picos") # Key única

def renderizar_dimensionamento_abs(db_data, mes_ref):
    # Esta função agora foca apenas no formulário para evitar duplicação de gráficos
    if "absenteismo" not in db_data: db_data["absenteismo"] = []
    
    st.markdown("#### 🤒 Registro de Ocorrências (Faltas/Atrasos)")
    with st.form("form_abs_unificado", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        dt = c1.date_input("Data")
        nome = c2.text_input("Colaborador")
        tp = c3.selectbox("Tipo", ["Falta", "Atraso", "Saída Antecipada", "Atestado"])
        obs = st.text_input("Observação")
        if st.form_submit_button("Registrar Ocorrência"):
            db_data["absenteismo"].append({
                "DATA": dt.strftime("%d/%m/%Y"), 
                "COLABORADOR": nome, 
                "TIPO": tp,
                "OBS": obs
            })
            salvar_dados_op(db_data, mes_ref)
            st.success("Registrado!")
            st.rerun()
    
    if db_data["absenteismo"]:
        st.write("#### Histórico")
        st.dataframe(pd.DataFrame(db_data["absenteismo"]), use_container_width=True, hide_index=True)

# =========================================================
# 5. ESTRUTURA UNIFICADA (VERSÃO COM CADASTRO MANUAL E AUDITORIA)
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    
    # Barra Lateral
    st.sidebar.title("📅 Gestão Mensal")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    # --- ABAS NÍVEL 1 ---
    tab_modulo_compras, tab_modulo_picos, tab_modulo_config = st.tabs([
        "🛒 COMPRAS", 
        "📊 DASH OPERAÇÃO", 
        "⚙️ CONFIGURAÇÕES"
    ])

    # --- ABA 1: COMPRAS ---
    with tab_modulo_compras:
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        tab1, tab2, tab3, tab4 = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARD COMPRAS", "📈 DASHBOARD RECEBIMENTO"])
        
        with tab1: # Processo de Compras
            if df_atual.empty: 
                st.warning("Sem dados. Vá na aba superior CONFIGURAÇÕES.")
            else:
                st.markdown('<div class="search-box">', unsafe_allow_html=True)
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq_c")
                st.markdown('</div>', unsafe_allow_html=True)
                
                idx_s = db_data.get("idx_solic", 0)
                while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
                if idx_s < len(df_atual):
                    st.subheader(f"🚀 Esteira ({idx_s + 1}/{len(df_atual)})")
                    with st.container():
                        st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                        renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "main_c")
                        st.markdown("</div>", unsafe_allow_html=True)

        with tab2: # Recebimento
            pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index() if not df_atual.empty else pd.DataFrame()
            if not pend_rec.empty:
                st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
                q_r = st.text_input("🔍 Localizar Recebimento:").upper()
                if q_r:
                    it_r = pend_rec[pend_rec['CODIGO'].astype(str).str.contains(q_r) | pend_rec['DESCRICAO'].astype(str).str.contains(q_r)]
                    for _, r in it_r.iterrows():
                        with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "bq_r")
                st.markdown('</div>', unsafe_allow_html=True)
                st.subheader(f"📥 Recebimento ({len(pend_rec)} pendentes)")
                with st.container():
                    st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                    renderizar_tratativa_recebimento(pend_rec.iloc[0], pend_rec.iloc[0]['index'], df_atual, db_data, mes_ref, "main_r")
                    st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Tudo recebido ou nada encomendado.")

        with tab3: # DASHBOARD COMPRAS (COM AUDITORIA)
            renderizar_dashboards_compras_completo(df_atual)
            
            if not df_atual.empty:
                st.divider()
                st.subheader("🔍 Detalhamento de Auditoria")
                
                # Identifica itens manuais para o ALERTA
                itens_manuais = df_atual[df_atual.get('ORIGEM') == 'Manual']
                if not itens_manuais.empty:
                    st.warning(f"🚩 ALERTA: {len(itens_manuais)} itens manuais identificados.")
                
                col_aud1, col_aud2 = st.columns(2)
                with col_aud1:
                    with st.expander("🟢 ITENS COM ESTOQUE (Estratégico)"):
                        estrat = df_atual[(df_atual['SALDO_FISICO'] > 0)]
                        st.dataframe(estrat, use_container_width=True)
                with col_aud2:
                    with st.expander("🔴 ITENS SEM ESTOQUE (Ruptura)"):
                        ruptura = df_atual[(df_atual['SALDO_FISICO'] <= 0)]
                        st.dataframe(ruptura, use_container_width=True)

                with st.expander("🔎 Ver itens fora da planilha"):
                    st.dataframe(itens_manuais, use_container_width=True)
                
                st.download_button("📊 Baixar Relatório Geral Compras", df_atual.to_csv(index=False).encode('utf-8'), f"Relatorio_{mes_ref}.csv", "text/csv", use_container_width=True)

        with tab4: # Dash Recebimento (Gráfico)
            if not df_atual.empty:
                encomendados = df_atual[df_atual['QTD_SOLICITADA'] > 0]
                if not encomendados.empty:
                    df_rec = encomendados[encomendados['STATUS_RECEB'] != "Pendente"]
                    st.subheader("📊 Performance de Recebimento")
                    # ... (mantém métricas de r1, r2, r3, r4)
                    st.plotly_chart(px.bar(df_rec, x='CODIGO', y=['QTD_SOLICITADA', 'QTD_RECEBIDA'], barmode='group'), use_container_width=True)

    # --- ABA 2: DASH OPERAÇÃO (PICOS) ---
    with tab_modulo_picos:
        st.markdown(f"<div class='header-analise'>DASH OPERAÇÃO (PICOS) - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        
        dados_picos = db_data.get("picos", [])
        
        if dados_picos:
            # 1. Criamos um DF temporário para garantir que as datas sejam lidas como datas
            df_temp = pd.DataFrame(dados_picos)
            
            # 2. Tentamos converter a coluna de data (ajuste o nome se for diferente na sua planilha)
            if 'DATA' in df_temp.columns:
                df_temp['DATA'] = pd.to_datetime(df_temp['DATA'])
            
            # 3. Enviamos de volta como lista tratada para a função
            renderizar_picos_operacional(df_temp.to_dict(orient='records'))
        else:
            st.info("📊 Sem dados de picos. Importe a base em CONFIGURAÇÕES.")

    # --- ABA 3: CONFIGURAÇÕES (CADASTRO MANUAL + UPLOAD) ---
    with tab_modulo_config:
        st.markdown(f"<div class='header-analise'>CONFIGURAÇÕES DO SISTEMA</div>", unsafe_allow_html=True)
        
        # NOVO: CADASTRO MANUAL
        with st.container(border=True):
            st.subheader("🆕 Cadastro Manual")
            with st.form("cad_manual_form", clear_on_submit=True):
                m1, m2 = st.columns(2)
                c_cod = m1.text_input("Código")
                c_desc = m2.text_input("Descrição")
                m3, m4, m5 = st.columns([2, 2, 1])
                c_forn = m3.text_input("Fornecedor")
                c_grupo = m4.selectbox("Grupo", ["COLCHAO", "ESTOFADO", "TRAVESSEIRO", "OUTROS"])
                c_qtd = m5.number_input("Qtd", min_value=1, value=1)
                
                if st.form_submit_button("➕ Adicionar"):
                    novo_item = {
                        "CODIGO": c_cod, "DESCRICAO": c_desc, "FORNECEDOR": c_forn, 
                        "GRUPO": c_grupo, "QUANTIDADE": c_qtd, "ORIGEM": "Manual",
                        "STATUS_COMPRA": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0,
                        "STATUS_RECEB": "Pendente", "QTD_RECEBIDA": 0
                    }
                    df_atual = pd.concat([df_atual, pd.DataFrame([novo_item])], ignore_index=True)
                    db_data["analises"] = df_atual.to_dict(orient='records')
                    salvar_dados_op(db_data, mes_ref)
                    st.success("Item adicionado com sucesso!")
                    st.rerun()

        st.divider()
        st.subheader("⚙️ Importação de Planilhas")
        c_up1, c_up2 = st.columns(2)
        with c_up1:
            up_c = st.file_uploader("Base Compras (Excel)", type="xlsx")
            if up_c and st.button("Salvar Base Compras"):
                df_n = pd.read_excel(up_c)
                df_n['ORIGEM'] = 'Planilha' # Marca origem para auditoria
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: 
                    df_n[c] = "Pendente" if "STATUS" in c else 0
                db_data["analises"] = df_n.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref)
                st.rerun()
        
        with c_up2:
            up_p = st.file_uploader("Base Picos Zendesk (Excel)", type="xlsx")
            if up_p and st.button("Salvar Base Picos"):
                df_p = pd.read_excel(up_p)
                db_data["picos"] = df_p.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref)
                st.rerun()
        
        st.divider()
        if st.button("🗑️ RESETAR MÊS ATUAL", type="primary"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}, mes_ref)
            st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
