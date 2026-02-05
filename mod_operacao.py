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
        .metric-box h3 { margin: 5px 0; font-size: 1.8rem; color: #002366; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        </style>
    """, unsafe_allow_html=True)

# --- UTILITÁRIOS DE DADOS ---
def normalizar_colunas(df, tipo_planilha="compras"):
    def limpar(txt):
        if not isinstance(txt, str): return txt
        txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
        return txt.strip().upper().replace(" ", "_")
    
    df.columns = [limpar(c) for c in df.columns]

    # Mapeamento específico para a sua planilha de 6 colunas (Picos)
    if tipo_planilha == "picos":
        mapeamento = {
            'CRIACAO_DO_TICKET_-_DATA': 'DATA_ENTRADA',
            'CRIACAO_DO_TICKET_-_DIA_DA_SEMANA': 'DIA_SEMANA_ORIGINAL',
            'CRIACAO_DO_TICKET_-_HORA': 'HORA',
            'CRIACAO_DO_TICKET_-_MES': 'MES_NOME',
            'CANAL_DO_TICKET': 'CANAL',
            'TICKETS': 'TICKETS'
        }
        df = df.rename(columns=mapeamento)
    return df

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "picos": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

# --- COMPONENTE: ANÁLISE DE PICOS (6 COLUNAS) ---
def renderizar_analise_picos(df_picos):
    if df_picos.empty:
        st.info("💡 Nenhuma base de picos carregada.")
        return

    st.subheader("🔥 Inteligência de Demanda (WhatsApp/Tickets)")
    
    # Garantir que TICKETS é numérico
    df_picos['TICKETS'] = pd.to_numeric(df_picos['TICKETS'], errors='coerce').fillna(0)
    
    c1, c2, c3 = st.columns(3)
    
    # Cálculos de Performance
    total_mensal = df_picos['TICKETS'].sum()
    pico_horario_row = df_picos.groupby('HORA')['TICKETS'].mean().idxmax()
    pico_valor_hora = df_picos.groupby('HORA')['TICKETS'].mean().max()
    dia_mais_movimentado = df_picos.groupby('DIA_SEMANA_ORIGINAL')['TICKETS'].sum().idxmax()

    c1.markdown(f"<div class='metric-box'><small>VOLUME TOTAL</small><h3>{int(total_mensal)}</h3><p>Tickets no Mês</p></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-box'><small>PICO MÉDIO</small><h3>{pico_horario_row}h</h3><p>Média {pico_valor_hora:.1f} tickets</p></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-box'><small>DIA CRÍTICO</small><h3>{dia_mais_movimentado}</h3><p>Maior demanda</p></div>", unsafe_allow_html=True)

    # Gráfico de Calor (Horário x Dia da Semana)
    st.markdown("### 🗓️ Distribuição de Carga Horária")
    pivot_picos = df_picos.pivot_table(index='HORA', columns='DIA_SEMANA_ORIGINAL', values='TICKETS', aggfunc='mean').fillna(0)
    # Reordenar dias para lógica humana
    dias_ordem = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    pivot_picos = pivot_picos.reindex(columns=[d for d in dias_ordem if d in pivot_picos.columns])
    
    fig_heat = px.imshow(pivot_picos, text_auto=True, aspect="auto", color_continuous_scale='Blues', title="Média de Tickets por Hora/Dia")
    st.plotly_chart(fig_heat, use_container_width=True)

# --- COMPONENTE: TRATATIVA DE COMPRAS ---
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref):
    st.markdown(f"#### {item.get('DESCRICAO', 'Item sem Descrição')}")
    st.caption(f"Cód: {item.get('CODIGO', 'N/A')} | Sugestão: {item.get('QUANTIDADE', 0)}")
    
    col_input, col_btns = st.columns([1, 2])
    with col_input:
        saldo = st.number_input(f"Estoque Real:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}")
    
    with col_btns:
        st.write("") # Alinhamento
        bc1, bc2 = st.columns(2)
        if bc1.button("✅ COMPRAR", key=f"tot_{index}", use_container_width=True):
            df_completo.at[index, 'STATUS_COMPRA'] = "Total"
            df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            salvar_dados_op(db_data, mes_ref); st.rerun()

        if bc2.button("❌ PULAR", key=f"zer_{index}", use_container_width=True):
            df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
            df_completo.at[index, 'QTD_SOLICITADA'] = 0
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            salvar_dados_op(db_data, mes_ref); st.rerun()

# --- INTERFACE PRINCIPAL ---
def exibir_operacao_completa():
    aplicar_estilo_premium()
    
    # Sidebar - Período
    st.sidebar.title("📅 Período")
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    tab_op, tab_picos, tab_cfg = st.tabs(["🛒 OPERAÇÃO", "🔥 PICOS DE DEMANDA", "⚙️ CONFIGURAÇÕES"])

    with tab_op:
        if not db_data.get("analises"):
            st.info("Aguardando planilha de compras...")
        else:
            df_atual = pd.DataFrame(db_data["analises"])
            analisados = len(df_atual[df_atual['STATUS_COMPRA'] != "Pendente"])
            
            # Cartas de Resumo
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-box'><small>ITENS</small><h3>{len(df_atual)}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-box'><small>CONCLUÍDO</small><h3>{analisados}</h3></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-box'><small>RESTANTE</small><h3>{len(df_atual)-analisados}</h3></div>", unsafe_allow_html=True)
            
            # Esteira
            pendentes = df_atual[df_atual['STATUS_COMPRA'] == "Pendente"]
            if not pendentes.empty:
                idx = pendentes.index[0]
                st.divider()
                st.subheader(f"Análise Atual: {analisados + 1} de {len(df_atual)}")
                with st.container():
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_atual.loc[idx], idx, df_atual, db_data, mes_ref)
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.success("🎉 Tudo pronto! Todos os itens foram analisados.")

    with tab_picos:
        if not db_data.get("picos"):
            st.warning("Suba o 'Relatório Whats dia hora' em Configurações.")
        else:
            renderizar_analise_picos(pd.DataFrame(db_data["picos"]))

    with tab_cfg:
        st.header("📤 Importação de Dados")
        c_up1, c_up2 = st.columns(2)
        
        with c_up1:
            st.subheader("🛒 Compras")
            up_c = st.file_uploader("Base de Compras", type="xlsx", key="uc")
            if up_c and st.button("Carregar Compras"):
                df = normalizar_colunas(pd.read_excel(up_c), "compras")
                df['STATUS_COMPRA'] = "Pendente"
                db_data["analises"] = df.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

        with c_up2:
            st.subheader("🔥 Picos (6 colunas)")
            up_p = st.file_uploader("Relatório Whats", type="xlsx", key="up")
            if up_p and st.button("Carregar Picos"):
                # Lê a planilha e aplica o mapeamento das 6 colunas
                df_p = normalizar_colunas(pd.read_excel(up_p), "picos")
                db_data["picos"] = df_p.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        if st.button("🗑️ Resetar Tudo (Mês Atual)"):
            salvar_dados_op({"analises":[], "picos":[]}, mes_ref); st.rerun()
