import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# =========================================================
# 1. ESTILO E CORES
# =========================================================
PALETA_CORES = ['#002366', '#3b82f6', '#16a34a', '#ef4444', '#facc15']

def aplicar_estilo_premium():
    st.markdown(f"""
        <style>
        .main-card {{ background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid {PALETA_CORES[0]}; margin-bottom: 20px; color: #1e293b; }}
        .metric-box {{ background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; color: {PALETA_CORES[0]}; }}
        .metric-box h3 {{ margin: 5px 0; font-size: 1.8rem; font-weight: bold; }}
        .header-analise {{ background: {PALETA_CORES[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 20px; }}
        </style>
    """, unsafe_allow_html=True)

# --- Funções de Apoio ---
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_cabecalhos_picos(df):
    mapeamento = {
        'CRIACAO DO TICKET - DATA': 'DATA',
        'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA',
        'CRIACAO DO TICKET - HORA': 'HORA',
        'TICKETS': 'TICKETS'
    }
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    df = df.rename(columns=mapeamento)
    if 'DATA' in df.columns:
        df['DATA'] = pd.to_datetime(df['DATA']).dt.strftime('%d/%m/%Y')
    return df

# =========================================================
# 2. DASHBOARD OPERACIONAL (COM CALENDÁRIO E MARCAR TODOS)
# =========================================================
def renderizar_picos_operacional(db_picos):
    if not db_picos:
        st.info("💡 Sem dados de picos para este período. Vá em CONFIGURAÇÕES e importe a base do Zendesk.")
        return
    
    # Normalização e preparação dos dados
    df = normalizar_cabecalhos_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    st.subheader("🔥 Inteligência de Canais & Picos")

    # --- SISTEMA DE SELEÇÃO DE DIAS (CALENDÁRIO + MARCAR TODOS) ---
    dias_disponiveis = sorted(df['DATA'].unique(), key=lambda x: datetime.strptime(x, '%d/%m/%Y'))
    
    st.markdown("### 📅 Filtro de Dias")
    c_btn1, c_btn2 = st.columns([1, 4])
    
    # Lógica do Botão Marcar/Desmarcar Todos
    if "todos_selecionados" not in st.session_state:
        st.session_state.todos_selecionados = True

    if c_btn1.button("✅ Marcar Todos" if not st.session_state.todos_selecionados else "🔲 Desmarcar Todos"):
        st.session_state.todos_selecionados = not st.session_state.todos_selecionados
        st.rerun()

    default_dias = dias_disponiveis if st.session_state.todos_selecionados else []
    
    dias_selecionados = st.multiselect(
        "Selecione os dias para análise detalhada:",
        options=dias_disponiveis,
        default=default_dias,
        help="Remova ou adicione dias para ver o comportamento da operação em datas específicas."
    )
    
    if not dias_selecionados:
        st.warning("Selecione pelo menos um dia no calendário acima para visualizar os gráficos.")
        return

    df_filtrado = df[df['DATA'].isin(dias_selecionados)]

    # --- ORDENAÇÃO DIA DA SEMANA ---
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    # --- GRÁFICOS COM DADOS VISÍVEIS ---
    col1, col2 = st.columns(2)
    
    with col1:
        # Picos por Hora
        df_h = df_filtrado.groupby('HORA')['TICKETS'].sum().reset_index()
        fig_h = px.bar(df_h, x='HORA', y='TICKETS', title="Volume por Hora (Total Acumulado)", 
                       text_auto='.0f', color_discrete_sequence=[PALETA_CORES[0]])
        fig_h.update_traces(textposition='outside', textfont_size=12)
        fig_h.update_layout(yaxis={'visible': False}, height=400) # Remove eixo Y para limpar visual, já que o dado está na barra
        st.plotly_chart(fig_h, use_container_width=True)

    with col2:
        # Picos por Dia da Semana
        df_d = df_filtrado.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna()
        fig_d = px.bar(df_d, x='DIA_SEMANA', y='TICKETS', title="Volume por Dia da Semana",
                       text_auto='.0f', color_discrete_sequence=[PALETA_CORES[1]])
        fig_d.update_traces(textposition='outside', textfont_size=14)
        fig_d.update_layout(yaxis={'visible': False}, height=400)
        st.plotly_chart(fig_d, use_container_width=True)

    # --- MAPA DE CALOR ---
    st.markdown("### 🌡️ Densidade de Atendimento (Dia vs Hora)")
    pivot = df_filtrado.pivot_table(index='HORA', columns='DIA_SEMANA', values='TICKETS', aggfunc='sum').fillna(0)
    colunas_pivot = [d for d in ordem_dias if d in pivot.columns]
    pivot = pivot[colunas_pivot]
    
    fig_heat = px.imshow(pivot, text_auto=True, color_continuous_scale='Reds', aspect="auto")
    fig_heat.update_layout(xaxis_title="Dia da Semana", yaxis_title="Hora do Dia")
    st.plotly_chart(fig_heat, use_container_width=True)

    # Resumo Estatístico em Cards
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    total_tickets = df_filtrado['TICKETS'].sum()
    media_diaria = total_tickets / len(dias_selecionados) if dias_selecionados else 0
    pico_hora = df_h.loc[df_h['TICKETS'].idxmax(), 'HORA'] if not df_h.empty else 0
    
    m1.markdown(f"<div class='metric-box'><small>TOTAL DE TICKETS</small><h3>{int(total_tickets)}</h3></div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='metric-box'><small>MÉDIA POR DIA</small><h3>{media_diaria:.1f}</h3></div>", unsafe_allow_html=True)
    m3.markdown(f"<div class='metric-box'><small>HORÁRIO DE PICO</small><h3>{pico_hora}h</h3></div>", unsafe_allow_html=True)

# =========================================================
# 3. MÓDULO DE COMPRAS (MANTIDO ÍNTEGRO)
# =========================================================
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 4. EXIBIÇÃO PRINCIPAL
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    
    # Seletor de Período no topo
    with st.container():
        c_mes, c_ano, c_status = st.columns([2, 1, 3])
        meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_sel = c_mes.selectbox("Mês", meses, index=datetime.now().month - 1)
        ano_sel = c_ano.selectbox("Ano", [2024, 2025, 2026], index=1)
        mes_ref = f"{mes_sel}_{ano_sel}"
        
        c_status.markdown(f"<div class='header-analise'>📊 ANALISANDO: {mes_sel.upper()} / {ano_sel}</div>", unsafe_allow_html=True)

    db_data = carregar_dados_op(mes_ref)
    
    tab_compra, tab_receb, tab_dash_op, tab_config = st.tabs([
        "🛒 COMPRAS & ESTEIRA", "📥 RECEBIMENTO", "📊 DASH OPERACIONAL", "⚙️ CONFIGURAÇÕES"
    ])

    with tab_compra:
        if db_data.get("analises"):
            df_atual = pd.DataFrame(db_data["analises"])
            st.markdown('<div class="search-box">', unsafe_allow_html=True)
            q = st.text_input("🔍 Localizar Item:").upper()
            if q:
                it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                for i, r in it_b.iterrows():
                    with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq")
            st.markdown('</div>', unsafe_allow_html=True)
            
            idx = db_data.get("idx_solic", 0)
            while idx < len(df_atual) and df_atual.iloc[idx]['STATUS_COMPRA'] != "Pendente": idx += 1
            if idx < len(df_atual):
                st.subheader(f"🚀 Esteira ({idx + 1}/{len(df_atual)})")
                with st.markdown("<div class='main-card'>", unsafe_allow_html=True):
                    renderizar_tratativa_compra(df_atual.iloc[idx], idx, df_atual, db_data, mes_ref, "main_c")
                st.markdown("</div>", unsafe_allow_html=True)

    with tab_dash_op:
        renderizar_picos_operacional(db_data.get("picos", []))

    with tab_config:
        st.subheader("📥 Importação de Planilhas")
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            up_c = st.file_uploader("Base Compras (Excel)", type="xlsx")
            if up_c and st.button("Salvar Base Compras"):
                df_c = pd.read_excel(up_c)
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: df_c[c] = "Pendente" if "STATUS" in c else 0
                db_data["analises"] = df_c.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()
        with col_up2:
            up_p = st.file_uploader("Base Picos (Excel)", type="xlsx")
            if up_p and st.button("Salvar Base Picos"):
                df_p = pd.read_excel(up_p)
                db_data["picos"] = df_p.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
