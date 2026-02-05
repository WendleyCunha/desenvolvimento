import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# =========================================================
# 1. CONFIGURAÇÕES, ESTILO E BANCO DE DADOS
# =========================================================
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; color: #002366; }
        .metric-box h3 { margin: 5px 0; font-size: 1.8rem; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

def carregar_dados_op(mes_referencia):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_referencia).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}

def salvar_dados_op(dados, mes_referencia):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_referencia).set(dados)

def listar_meses_gravados():
    fire = inicializar_db()
    return [doc.id for doc in fire.collection("operacoes_mensais").stream()]

# =========================================================
# 2. TRATAMENTO ESPECÍFICO DA PLANILHA DE 6 COLUNAS
# =========================================================
def normalizar_cabecalhos_picos(df):
    # Converte os nomes longos do Zendesk/BI para nomes curtos de processamento
    mapeamento = {
        'CRIACAO DO TICKET - DATA': 'DATA',
        'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA',
        'CRIACAO DO TICKET - HORA': 'HORA',
        'TICKETS': 'TICKETS'
    }
    # Remove acentos e espaços extras para garantir o match
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    df = df.rename(columns=mapeamento)
    return df

# =========================================================
# 3. COMPONENTE DE PICOS (OS 3 GRÁFICOS SOLICITADOS)
# =========================================================
def renderizar_analise_picos(df_picos):
    if df_picos.empty:
        st.info("💡 Nenhuma base de picos encontrada. Suba o arquivo na aba CONFIG.")
        return

    df = normalizar_cabecalhos_picos(df_picos)
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    st.subheader("🔥 Inteligência de Canais e Picos")

    # --- GRÁFICO 1: PICO HORA A HORA ---
    st.markdown("### 1. Volume por Faixa Horária")
    df_hora = df.groupby('HORA')['TICKETS'].sum().reset_index()
    pico_hora_val = df_hora['TICKETS'].max()
    df_hora['COR'] = ['#ef4444' if v == pico_hora_val else '#002366' for v in df_hora['TICKETS']]
    
    fig_hora = px.bar(df_hora, x='HORA', y='TICKETS', color='COR', color_discrete_map="identity")
    fig_hora.update_layout(xaxis_type='category', showlegend=False)
    st.plotly_chart(fig_hora, use_container_width=True)

    # --- GRÁFICO 2: VOLUME POR DIA DA SEMANA ---
    st.markdown("### 2. Volume por Dia da Semana")
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    df_dia = df.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna()
    pico_dia_val = df_dia['TICKETS'].max()
    df_dia['COR'] = ['#ef4444' if v == pico_dia_val else '#3b82f6' for v in df_dia['TICKETS']]

    fig_dia = px.bar(df_dia, x='DIA_SEMANA', y='TICKETS', color='COR', color_discrete_map="identity")
    fig_dia.update_layout(showlegend=False)
    st.plotly_chart(fig_dia, use_container_width=True)

    # --- GRÁFICO 3: MAPA DE CALOR ---
    st.markdown("### 3. Mapa de Calor (Densidade)")
    pivot_picos = df.pivot_table(index='HORA', columns='DIA_SEMANA', values='TICKETS', aggfunc='sum').fillna(0)
    colunas_mapa = [d for d in ordem_dias if d in pivot_picos.columns]
    pivot_picos = pivot_picos[colunas_mapa]
    
    fig_heat = px.imshow(pivot_picos, text_auto=True, aspect="auto", color_continuous_scale='Reds')
    st.plotly_chart(fig_heat, use_container_width=True)

# =========================================================
# 4. FUNÇÃO PRINCIPAL DE INTERFACE
# =========================================================
def exibir_operacao_completa(user_role):
    aplicar_estilo_premium()
    st.title("📊 Gestão Operacional & Picos")
    
    # Sidebar - Seleção de Mês
    mes_atual = datetime.now().strftime("%Y-%m")
    with st.sidebar:
        meses_dispo = listar_meses_gravados()
        if mes_atual not in meses_dispo: meses_dispo.append(mes_atual)
        mes_sel = st.selectbox("Período de Referência", sorted(meses_dispo, reverse=True))
    
    db_data = carregar_dados_op(mes_sel)
    
    # Abas principais
    tabs = st.tabs(["🛒 COMPRAS", "📥 RECEBIMENTO", "🔥 PICOS WHATSAPP", "⚙️ CONFIG"])

    with tabs[0]: # Compras
        st.write("Lógica da Esteira de Compras (Itens Pendentes)...")
        # Aqui você insere sua lógica de renderizar_tratativa_compra

    with tabs[1]: # Recebimento
        st.write("Lógica da Esteira de Recebimento...")

    with tabs[2]: # Picos (A Mágica dos 3 Gráficos)
        renderizar_analise_picos(pd.DataFrame(db_data.get("picos", [])))

    with tabs[3]: # Configurações e Uploads
        st.subheader("📤 Upload de Arquivos")
        c1, c2 = st.columns(2)
        with c1:
            up_compra = st.file_uploader("Base Compras (Excel)", type="xlsx", key="up_c")
            if up_compra and st.button("Carregar Compras"):
                df_c = pd.read_excel(up_compra)
                # Adicionar colunas de controle
                for col in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO']: df_c[col] = 0
                db_data["analises"] = df_c.to_dict(orient='records')
                salvar_dados_op(db_data, mes_sel); st.rerun()
        
        with c2:
            up_pico = st.file_uploader("Relatório Whats (6 colunas)", type="xlsx", key="up_p")
            if up_pico and st.button("Carregar Picos"):
                df_p = pd.read_excel(up_pico)
                db_data["picos"] = df_p.to_dict(orient='records')
                salvar_dados_op(db_data, mes_sel); st.rerun()

        if st.button("🗑️ Resetar Tudo"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}, mes_sel); st.rerun()
