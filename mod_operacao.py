import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# --- FUNÇÕES DE UTILITÁRIOS E NORMALIZAÇÃO ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        .search-box-rec { background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid #16a34a; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

def normalizar_colunas(df):
    def limpar_texto(txt):
        if not isinstance(txt, str): return txt
        txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
        return txt.strip().upper().replace(" ", "_")
    df.columns = [limpar_texto(c) for c in df.columns]
    return df

# --- DATABASE ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# --- NOVO: ANÁLISE DE PICOS (BI) ---
def renderizar_analise_demanda(df):
    st.subheader("🔥 Análise de Picos de Demanda")
    
    # Verifica se as colunas de tickets existem (normalizadas)
    cols_necessarias = ['DATA_ENTRADA', 'HORA', 'TICKETS']
    if not all(c in df.columns for c in cols_necessarias):
        st.info("💡 Para visualizar picos, sua planilha deve conter: DATA ENTRADA, HORA e TICKETS.")
        return

    try:
        df['DATA_ENTRADA'] = pd.to_datetime(df['DATA_ENTRADA'])
        # Mapeamento de dias para Português
        dias_pt = {'Monday': 'Segunda', 'Tuesday': 'Terça', 'Wednesday': 'Quarta', 'Thursday': 'Quinta', 'Friday': 'Sexta', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
        df['DIA_SEMANA'] = df['DATA_ENTRADA'].dt.day_name().map(dias_pt)

        c1, c2, c3 = st.columns(3)
        
        # Cálculos
        pico_dia = df.groupby('DATA_ENTRADA')['TICKETS'].sum()
        pico_horario = df.groupby('HORA')['TICKETS'].mean()
        pico_semana = df.groupby('DIA_SEMANA')['TICKETS'].sum()

        c1.markdown(f"<div class='metric-box'><small>PICO DIÁRIO</small><h3>{pico_dia.max()}</h3><p>{pico_dia.idxmax().strftime('%d/%m')}</p></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-box'><small>PICO HORÁRIO (Méd)</small><h3>{pico_horario.idxmax()}h</h3><p>{pico_horario.max():.1f} tickets</p></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-box'><small>DIA DA SEMANA</small><h3>{pico_semana.idxmax()}</h3><p>Maior Demanda</p></div>", unsafe_allow_html=True)

        fig = px.line(pico_dia.reset_index(), x='DATA_ENTRADA', y='TICKETS', title="Fluxo de Demanda no Mês", line_shape="spline")
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao processar picos: {e}")

# --- TRATATIVAS (COMPRA E RECEBIMENTO) ---
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item.get('DESCRICAO', 'SEM DESCRICAO')}")
    st.caption(f"Cód: {item.get('CODIGO', 'N/A')} | Lista: {item.get('QUANTIDADE', 0)}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()
    
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
        
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item.get('DESCRICAO', 'SEM DESCRICAO')}")
    st.caption(f"Cód: {item.get('CODIGO', 'N/A')} | **Esperado: {item.get('QTD_SOLICITADA', 0)}**")
    rc1, rc2, rc3 = st.columns(3)
    
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"
        df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True

    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"
        df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=int(item['QTD_SOLICITADA']), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"
            df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# --- DASHBOARDS ---
def renderizar_dashboard_compras(df):
    if df.empty: return
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    st.subheader("📊 Performance de Compras")
    c1, c2 = st.columns(2)
    with c1:
        st_counts = df['STATUS_COMPRA'].value_counts().reset_index()
        fig = px.pie(st_counts, values='count', names='STATUS_COMPRA', title="Status de Compras", hole=0.4)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        # Gráfico Ruptura
        rup = df[df['STATUS_COMPRA'] == "Não Efetuada"]
        if not rup.empty:
            fig_rup = px.bar(rup, x='CODIGO', y='SALDO_FISICO', title="Estoque de Itens Não Comprados")
            st.plotly_chart(fig_rup, use_container_width=True)

# --- EXIBIÇÃO PRINCIPAL ---
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    
    # Sidebar
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=2)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    tab1, tab2, tab3, tab4, tab_picos, tab5 = st.tabs([
        "🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASH COMPRAS", "📉 DASH RECEBIMENTO", "🔥 ANALISE DE PICOS", "⚙️ CONFIGURAÇÕES"
    ])

    with tab5: # Configurações
        st.header("⚙️ Gestão de Dados")
        up_nova = st.file_uploader("Subir Nova Base", type="xlsx")
        if up_nova and st.button("🚀 Processar e Salvar"):
            df_n = pd.read_excel(up_nova)
            df_n = normalizar_colunas(df_n)
            
            # Validação
            if 'CODIGO' not in df_n.columns or 'DESCRICAO' not in df_n.columns:
                st.error("Planilha deve conter CODIGO e DESCRICAO!")
            else:
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']:
                    if c not in df_n.columns: df_n[c] = "Pendente" if "STATUS" in c else 0
                salvar_dados_op({"analises": df_n.to_dict(orient='records'), "idx_solic": 0, "idx_receb": 0}, mes_ref)
                st.success("Dados salvos!"); st.rerun()
        
        if st.button("🗑️ RESETAR MÊS ATUAL"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}, mes_ref); st.rerun()

    # Se não houver dados, para aqui
    if not db_data.get("analises"):
        st.warning("Aguardando importação de dados em Configurações.")
        return

    df_atual = pd.DataFrame(db_data["analises"])

    with tab1: # Compras
        q = st.text_input("🔍 Buscar Item (Código ou Nome):").upper()
        if q:
            busc = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
            for i, r in busc.iterrows():
                with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "b_c")
        else:
            # Esteira
            idx = db_data.get("idx_solic", 0)
            pendentes = df_atual[df_atual['STATUS_COMPRA'] == "Pendente"]
            if not pendentes.empty:
                # Pega o primeiro pendente real
                real_idx = pendentes.index[0]
                st.subheader(f"Esteira de Compras ({len(pendentes)} restantes)")
                with st.container():
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_atual.loc[real_idx], real_idx, df_atual, db_data, mes_ref, "est_c")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.success("Tudo processado por aqui!")

    with tab2: # Recebimento
        pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")]
        if not pend_rec.empty:
            st.subheader(f"Esteira de Recebimento ({len(pend_rec)} itens)")
            idx_r = pend_rec.index[0]
            with st.container():
                st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                renderizar_tratativa_recebimento(df_atual.loc[idx_r], idx_r, df_atual, db_data, mes_ref, "est_r")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.success("Nada para receber no momento.")

    with tab3: renderizar_dashboard_compras(df_atual)
    with tab_picos: renderizar_analise_demanda(df_atual)
