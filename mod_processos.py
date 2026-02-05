import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# --- CONFIGURAÇÃO DE ESTILO ---
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; color: #002366; }
        .metric-box h3 { margin: 5px 0; font-size: 1.8rem; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

# --- UTILITÁRIOS ---
def normalizar_colunas(df):
    def limpar(txt):
        if not isinstance(txt, str): return txt
        txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
        return txt.strip().upper().replace(" ", "_")
    df.columns = [limpar(c) for c in df.columns]
    return df

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "picos": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

# --- COMPONENTE: ANÁLISE DE PICOS (BI) ---
def renderizar_analise_picos(df_picos):
    if df_picos.empty:
        st.info("💡 Nenhuma base de picos carregada para este mês.")
        return

    st.subheader("🔥 Inteligência de Demanda")
    
    # Tratamento de Datas
    df_picos['DATA_ENTRADA'] = pd.to_datetime(df_picos['DATA_ENTRADA'])
    dias_pt = {'Monday':'Segunda','Tuesday':'Terça','Wednesday':'Quarta','Thursday':'Quinta','Friday':'Sexta','Saturday':'Sábado','Sunday':'Domingo'}
    df_picos['DIA_SEMANA'] = df_picos['DATA_ENTRADA'].dt.day_name().map(dias_pt)

    c1, c2, c3 = st.columns(3)
    pico_dia = df_picos.groupby('DATA_ENTRADA')['TICKETS'].sum()
    pico_hora = df_picos.groupby('HORA')['TICKETS'].mean()
    
    c1.markdown(f"<div class='metric-box'><small>PICO DIÁRIO</small><h3>{pico_dia.max()}</h3><p>{pico_dia.idxmax().strftime('%d/%m')}</p></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-box'><small>HORÁRIO CRÍTICO</small><h3>{pico_hora.idxmax()}h</h3><p>Média de {pico_hora.max():.1f}</p></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-box'><small>VOLUME MENSAL</small><h3>{df_picos['TICKETS'].sum()}</h3><p>Total Tickets</p></div>", unsafe_allow_html=True)

    fig = px.area(pico_dia.reset_index(), x='DATA_ENTRADA', y='TICKETS', title="Fluxo de Volume Temporal", color_discrete_sequence=['#002366'])
    st.plotly_chart(fig, use_container_width=True)

# --- COMPONENTE: TRATATIVA DE COMPRAS ---
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Sugestão: {item['QUANTIDADE']}")
    
    saldo = st.number_input(f"Saldo Físico:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}")
    
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ COMPRA TOTAL", key=f"tot_{index}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if c3.button("❌ SEM ENCOMENDA", key=f"zer_{index}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

# --- FUNÇÃO PRINCIPAL ---
def exibir_operacao_completa():
    aplicar_estilo_premium()
    
    # Seleção de Período
    st.sidebar.title("📅 Gestão Mensal")
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    st.title("📊 Gestão Operacional Armazém")
    
    tabs = st.tabs(["🛒 Operação de Compras", "🔥 Análise de Picos", "⚙️ Configurações"])

    # --- TAB: COMPRAS ---
    with tabs[0]:
        if not db_data.get("analises"):
            st.warning("Aguardando carga da Planilha de Compras em Configurações.")
        else:
            df_atual = pd.DataFrame(db_data["analises"])
            
            # KPI Cards (Cartas)
            analisados = len(df_atual[df_atual['STATUS_COMPRA'] != "Pendente"])
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-box'><small>TOTAL ITENS</small><h3>{len(df_atual)}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-box'><small>ANALISADOS</small><h3>{analisados}</h3></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-box'><small>PENDENTES</small><h3>{len(df_atual)-analisados}</h3></div>", unsafe_allow_html=True)
            
            # Esteira de Decisão
            pendentes = df_atual[df_atual['STATUS_COMPRA'] == "Pendente"]
            if not pendentes.empty:
                st.divider()
                idx_foco = pendentes.index[0]
                st.subheader(f"🚀 Item em Análise ({analisados + 1}/{len(df_atual)})")
                with st.container():
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_atual.loc[idx_foco], idx_foco, df_atual, db_data, mes_ref)
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.success("✅ Todas as compras do mês foram processadas!")

    # --- TAB: PICOS ---
    with tabs[1]:
        if not db_data.get("picos"):
            st.info("Aguardando carga da Planilha de Picos em Configurações.")
        else:
            renderizar_analise_picos(pd.DataFrame(db_data["picos"]))

    # --- TAB: CONFIGURAÇÕES ---
    with tabs[2]:
        st.header("📤 Carga de Dados")
        
        # Diferenciação Clara de Subida
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🛒 Planilha de Compras")
            st.caption("Colunas: CODIGO, DESCRICAO, QUANTIDADE")
            up_compra = st.file_uploader("Subir Base de Compras", type="xlsx", key="up_c")
            if up_compra and st.button("Confirmar Base Compras"):
                df = normalizar_colunas(pd.read_excel(up_compra))
                df['STATUS_COMPRA'] = "Pendente"
                df['SALDO_FISICO'] = 0
                db_data["analises"] = df.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

        with col2:
            st.subheader("🔥 Planilha de Picos (BI)")
            st.caption("Colunas: DATA_ENTRADA, HORA, TICKETS")
            up_picos = st.file_uploader("Subir Base de Picos", type="xlsx", key="up_p")
            if up_picos and st.button("Confirmar Base Picos"):
                df = normalizar_colunas(pd.read_excel(up_picos))
                db_data["picos"] = df.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        if st.button("🗑️ Limpar Dados do Mês"):
            salvar_dados_op({"analises": [], "picos": []}, mes_ref); st.rerun()
