import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime
import os

# =========================================================
# 1. ESTILO E INTERFACE
# =========================================================
def aplicar_estilo():
    st.markdown("""
        <style>
        .metric-card { background: #ffffff; padding: 15px; border-radius: 12px; border-left: 5px solid #002366; 
                       box-shadow: 2px 2px 8px rgba(0,0,0,0.08); text-align: center; }
        .metric-value { font-size: 24px; font-weight: bold; color: #002366; margin: 0; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; margin-right: 5px; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-blue { background: #e0f2fe; color: #0369a1; }
        .card-header { font-size: 14px; font-weight: bold; color: #1e293b; margin-bottom: 5px; border-bottom: 1px solid #f1f5f9; padding-bottom: 5px; }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE SLA (DIAS ÚTEIS)
# =========================================================
def calcular_sla_48h(dt_emissao, dt_entrega):
    if pd.isna(dt_emissao) or pd.isna(dt_entrega): 
        return "Sem Agenda"
    
    try:
        # np.busday_count calcula dias úteis (seg-sex)
        # d1 e d2 precisam ser do tipo datetime64[D]
        d1 = np.datetime64(dt_emissao, 'D')
        d2 = np.datetime64(dt_entrega, 'D')
        dias_uteis = np.busday_count(d1, d2)
        
        if dias_uteis <= 2:
            return "Até 48h"
        else:
            return "Acima de 48h"
    except:
        return "Erro Data"

def tratar_dados_oficial(df):
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    
    # Padronização conforme suas imagens
    mapeamento = {
        'Dt Emissão': 'DATA_EMISSAO',
        'Data Entrega': 'DATA_ENTREGA',
        'Pedido': 'PEDIDO',
        'Tipo Venda': 'TIPO_VENDA'
    }
    df = df.rename(columns=mapeamento)
    
    # Tratamento de datas e '//'
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = df[col].astype(str).replace(['/ /', 'nan', 'NaT', '//'], np.nan)
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors='coerce')
    
    # Identificação de duplicidade por cliente
    if 'Cliente' in df.columns:
        df['Cliente_Limpo'] = df['Cliente'].astype(str).str.split('/').str[0].str.strip()
        df = df.sort_values(['Cliente_Limpo', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente_Limpo').cumcount() + 1
    
    return df

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Auditoria de Entregas King Star")

    if 'base_mestra' not in st.session_state: st.session_state.base_mestra = pd.DataFrame()
    
    tabs = st.tabs(["📊 Dashboard", "🔄 Integrar Logística", "🔍 Auditoria Manual", "⚙️ Config"])
    df = st.session_state.base_mestra

    # --- ABA 1: PERFORMANCE ---
    with tabs[0]:
        if not df.empty:
            # Recalcula SLA para visualização
            df['SLA_STATUS'] = df.apply(lambda x: calcular_sla_48h(x['DATA_EMISSAO'], x['DATA_ENTREGA']), axis=1)
            
            st.subheader("📊 Resumo do Mês")
            c1, c2, c3 = st.columns(3)
            
            total = len(df)
            no_prazo = len(df[df['SLA_STATUS'] == "Até 48h"])
            sem_data = len(df[df['SLA_STATUS'] == "Sem Agenda"])
            
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{total}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>No Prazo (48h Úteis)</p><p class='metric-value'>{no_prazo}</p></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>Sem Agenda</p><p class='metric-value'>{sem_data}</p></div>", unsafe_allow_html=True)
            
            fig = px.pie(df, names='SLA_STATUS', color='SLA_STATUS',
                         color_discrete_map={'Até 48h':'#2ecc71', 'Acima de 48h':'#e74c3c', 'Sem Agenda':'#bdc3c7'},
                         hole=0.4, title="Distribuição de SLA")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Suba a base de Vendas nas Configurações.")

    # --- ABA 2: INTEGRAR LOGÍSTICA (O PULO DO GATO) ---
    with tabs[1]:
        st.subheader("🔄 Cruzamento de Dados (Logística)")
        st.write("Suba o segundo relatório para preencher as datas de entrega automaticamente.")
        
        arq_log = st.file_uploader("Upload Relatório Logística (Carga/Pedido/Data Entrega)", type=['xlsx', 'csv'])
        
        if arq_log and not df.empty:
            df_log = pd.read_excel(arq_log) if arq_log.name.endswith('.xlsx') else pd.read_csv(arq_log, encoding='latin1', sep=None)
            df_log.columns = [str(c).strip() for c in df_log.columns]
            
            if st.button("Executar PROCV Automático"):
                # Mapeia Pedido -> Data Entrega da logística
                mapa_entregas = df_log.set_index('Pedido')['Data Entrega'].to_dict()
                
                def preencher(row):
                    if pd.isna(row['DATA_ENTREGA']):
                        res = mapa_entregas.get(row['PEDIDO'] if isinstance(row['PEDIDO'], str) else str(row['PEDIDO']))
                        return pd.to_datetime(res) if res else row['DATA_ENTREGA']
                    return row['DATA_ENTREGA']
                
                df['DATA_ENTREGA'] = df.apply(preencher, axis=1)
                st.session_state.base_mestra = df
                st.success("Dados de logística integrados com sucesso!")
                st.rerun()

    # --- ABA 4: CONFIGURAÇÕES ---
    with tabs[3]:
        st.subheader("⚙️ Carregar Base de Vendas")
        arq = st.file_uploader("Upload Planilha Mestra (Vendas)", type=['csv', 'xlsx'])
        if arq:
            df_raw = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
            st.session_state.base_mestra = tratar_dados_oficial(df_raw)
            st.success("Base Mestra carregada!")
            st.rerun()
        
        if st.button("🔥 LIMPAR SISTEMA"):
            st.session_state.base_mestra = pd.DataFrame()
            st.rerun()

if __name__ == "__main__":
    main()
