import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# --- 1. CONFIGURAÇÕES E ESTILO ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; color: #002366; }
        .metric-box h3 { margin: 5px 0; font-size: 1.8rem; font-weight: bold; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

# --- 2. UTILITÁRIOS DE TRATAMENTO DE DADOS ---
def normalizar_colunas(df, tipo="compras"):
    def limpar_texto(txt):
        if not isinstance(txt, str): return txt
        # Remove acentos e padroniza para MAIÚSCULAS com Underline
        txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
        return txt.strip().upper().replace(" ", "_").replace("-", "_")
    
    df.columns = [limpar_texto(c) for c in df.columns]

    if tipo == "picos":
        # Mapeamento para as 6 colunas específicas do seu relatório Zendesk/Whats
        mapeamento = {
            'CRIACAO_DO_TICKET_DATA': 'DATA_ENTRADA',
            'CRIACAO_DO_TICKET_DIA_DA_SEMANA': 'DIA_SEMANA',
            'CRIACAO_DO_TICKET_HORA': 'HORA',
            'CRIACAO_DO_TICKET_MES': 'MES',
            'CANAL_DO_TICKET': 'CANAL',
            'TICKETS': 'QTD_TICKETS'
        }
        df = df.rename(columns=mapeamento)
    return df

# --- 3. COMUNICAÇÃO COM FIREBASE ---
def carregar_dados_op(mes_ref):
    db = inicializar_db()
    doc = db.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "picos": []}

def salvar_dados_op(dados, mes_ref):
    db = inicializar_db()
    db.collection("operacoes_mensais").document(mes_ref).set(dados)

# --- 4. COMPONENTE: ANÁLISE DE PICOS (BI) ---
def aba_picos_demanda(df_picos):
    if df_picos.empty:
        st.info("💡 Nenhuma base de picos encontrada. Vá em Configurações.")
        return

    st.subheader("🔥 Inteligência de Demanda - WhatsApp")
    
    # KPIs Rápidos
    df_picos['QTD_TICKETS'] = pd.to_numeric(df_picos['QTD_TICKETS'], errors='coerce').fillna(0)
    total = df_picos['QTD_TICKETS'].sum()
    media_hora = df_picos.groupby('HORA')['QTD_TICKETS'].mean()
    pico_hora = media_hora.idxmax()
    
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"<div class='metric-box'><small>TOTAL MÊS</small><h3>{int(total)}</h3><p>Tickets</p></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-box'><small>HORA DE PICO</small><h3>{pico_hora}h</h3><p>Média Crítica</p></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-box'><small>DIA DE PICO</small><h3>{df_picos.groupby('DIA_SEMANA')['QTD_TICKETS'].sum().idxmax()}</h3><p>Maior Volume</p></div>", unsafe_allow_html=True)

    # Mapa de Calor (Heatmap)
    st.write("### 📅 Mapa de Calor: Horário vs Dia")
    dias_ordem = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    pivot = df_picos.pivot_table(index='HORA', columns='DIA_SEMANA', values='QTD_TICKETS', aggfunc='sum').fillna(0)
    pivot = pivot.reindex(columns=[d for d in dias_ordem if d in pivot.columns])
    
    fig = px.imshow(pivot, text_auto=True, aspect="auto", color_continuous_scale='Reds')
    st.plotly_chart(fig, use_container_width=True)

# --- 5. COMPONENTE: OPERAÇÃO DE COMPRAS ---
def aba_operacao_compras(df_atual, db_data, mes_ref):
    if df_atual.empty:
        st.warning("⚠️ Nenhuma base de compras carregada.")
        return

    # Filtros e métricas
    analisados = len(df_atual[df_atual['STATUS_COMPRA'] != "Pendente"])
    total_itens = len(df_atual)
    
    st.progress(analisados / total_itens)
    st.write(f"📊 **Progresso:** {analisados} de {total_itens} itens analisados.")

    # Esteira de Decisão
    pendentes = df_atual[df_atual['STATUS_COMPRA'] == "Pendente"]
    
    if not pendentes.empty:
        idx = pendentes.index[0]
        item = df_atual.loc[idx]
        
        with st.container():
            st.markdown("<div class='main-card'>", unsafe_allow_html=True)
            st.subheader(f"📦 {item['DESCRICAO']}")
            st.write(f"**Código:** {item['CODIGO']} | **Necessidade:** {item['QUANTIDADE']}")
            
            c_input, c_btn1, c_btn2 = st.columns([1,1,1])
            saldo = c_input.number_input("Estoque Real:", min_value=0, key=f"stock_{idx}")
            
            if c_btn1.button("✅ COMPRAR TOTAL", use_container_width=True):
                df_atual.at[idx, 'STATUS_COMPRA'] = "Total"
                df_atual.at[idx, 'QTD_SOLICITADA'] = item['QUANTIDADE']
                df_atual.at[idx, 'SALDO_FISICO'] = saldo
                db_data["analises"] = df_atual.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

            if c_btn2.button("❌ NÃO ENCOMENDAR", use_container_width=True):
                df_atual.at[idx, 'STATUS_COMPRA'] = "Não Efetuada"
                df_atual.at[idx, 'QTD_SOLICITADA'] = 0
                df_atual.at[idx, 'SALDO_FISICO'] = saldo
                db_data["analises"] = df_atual.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.success("✅ Todos os itens do mês foram processados!")

# --- 6. FUNÇÃO PRINCIPAL ---
def exibir_operacao_completa():
    aplicar_estilo_premium()
    
    # Sidebar - Gestão de Tempo
    st.sidebar.title("📅 Calendário Operacional")
    mes_sel = st.sidebar.selectbox("Mês de Referência", ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"])
    ano_sel = st.sidebar.selectbox("Ano", [2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    tab1, tab2, tab3 = st.tabs(["🛒 COMPRAS", "🔥 PICOS WHATSAPP", "⚙️ CONFIGURAÇÕES"])

    with tab1:
        aba_operacao_compras(pd.DataFrame(db_data["analises"]), db_data, mes_ref)

    with tab2:
        aba_picos_demanda(pd.DataFrame(db_data["picos"]))

    with tab3:
        st.header("⚙️ Configurações de Dados")
        
        col_up1, col_up2 = st.columns(2)
        
        with col_up1:
            st.subheader("Planilha de Compras")
            up_compra = st.file_uploader("Base (CODIGO, DESCRICAO, QUANTIDADE)", type="xlsx", key="c")
            if up_compra and st.button("Carregar Base Compras"):
                df = normalizar_colunas(pd.read_excel(up_compra), "compras")
                df['STATUS_COMPRA'] = "Pendente"
                db_data["analises"] = df.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

        with col_up2:
            st.subheader("Planilha de Picos")
            up_pico = st.file_uploader("Relatório Whats (6 colunas)", type="xlsx", key="p")
            if up_pico and st.button("Carregar Base Picos"):
                df = normalizar_colunas(pd.read_excel(up_pico), "picos")
                db_data["picos"] = df.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()
        
        st.divider()
        if st.button("🗑️ Resetar Mês Atual"):
            salvar_dados_op({"analises": [], "picos": []}, mes_ref); st.rerun()
