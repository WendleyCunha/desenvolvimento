import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime

# =========================================================
# 1. MOTOR DE TRATAMENTO (BLINDADO)
# =========================================================
def tratar_dados_oficial(df):
    if df.empty: return df
    
    # Limpeza de nomes de colunas
    df.columns = [str(col).strip() for col in df.columns]
    
    # Mapeamento exato conforme suas imagens
    mapeamento = {
        'Dt Emissão': 'DATA_EMISSAO',
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Data Entrega': 'DATA_ENTREGA',
        'Pedido': 'PEDIDO',
        'Tipo Venda': 'TIPO_VENDA',
        'Cliente': 'CLIENTE_BRUTO'
    }
    df = df.rename(columns=mapeamento)
    
    # Tratamento de Datas
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = df[col].astype(str).replace(['/ /', 'nan', 'NaT', '//', 'None'], np.nan)
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors='coerce')
    
    # Criação de colunas auxiliares
    if 'CLIENTE_BRUTO' in df.columns:
        df['Cliente_Limpo'] = df['CLIENTE_BRUTO'].astype(str).str.split('/').str[0].str.strip()
    
    if 'PEDIDO' in df.columns:
        df['PEDIDO'] = df['PEDIDO'].astype(str).str.strip()
        
    return df

def calcular_sla_48h(dt_emissao, dt_entrega):
    # Se qualquer uma das datas for nula, é "Sem Agenda"
    if pd.isna(dt_emissao) or pd.isna(dt_entrega): 
        return "Sem Agenda"
    
    try:
        # Cálculo usando dias úteis (Seg-Sex)
        d1 = np.datetime64(dt_emissao, 'D')
        d2 = np.datetime64(dt_entrega, 'D')
        dias_uteis = np.busday_count(d1, d2)
        
        return "Até 48h" if dias_uteis <= 2 else "Acima de 48h"
    except:
        return "Erro Data"

# =========================================================
# 2. INTERFACE PRINCIPAL
# =========================================================
def main():
    st.title("🏗️ Auditoria de Entregas King Star")

    if 'base_mestra' not in st.session_state: 
        st.session_state.base_mestra = pd.DataFrame()
    
    tabs = st.tabs(["📊 Dashboard", "🔄 Integrar Logística", "⚙️ Configurações"])
    df = st.session_state.base_mestra

    # --- ABA 1: DASHBOARD ---
    with tabs[0]:
        if not df.empty:
            # CHECAGEM DE SEGURANÇA: Só roda se as colunas mapeadas existirem
            if 'DATA_EMISSAO' in df.columns and 'DATA_ENTREGA' in df.columns:
                
                # Criamos o status apenas para exibição no gráfico
                df_view = df.copy()
                df_view['SLA_STATUS'] = df_view.apply(
                    lambda x: calcular_sla_48h(x['DATA_EMISSAO'], x['DATA_ENTREGA']), axis=1
                )
                
                st.subheader("📊 Resumo de Performance")
                c1, c2, c3 = st.columns(3)
                
                total = len(df_view)
                no_prazo = len(df_view[df_view['SLA_STATUS'] == "Até 48h"])
                atrasado = len(df_view[df_view['SLA_STATUS'] == "Acima de 48h"])
                sem_data = len(df_view[df_view['SLA_STATUS'] == "Sem Agenda"])
                
                c1.metric("Total Pedidos", total)
                c2.metric("No Prazo (48h Úteis)", no_prazo)
                c3.metric("Sem Agenda / Pendente", sem_data)
                
                fig = px.pie(df_view, names='SLA_STATUS', 
                             color='SLA_STATUS',
                             color_discrete_map={'Até 48h':'#2ecc71', 'Acima de 48h':'#e74c3c', 'Sem Agenda':'#bdc3c7'},
                             hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("⚠️ As colunas da planilha não foram reconhecidas. Verifique a aba Configurações.")
        else:
            st.info("💡 Por favor, carregue a Base de Vendas na aba 'Configurações'.")

    # --- ABA 2: INTEGRAR LOGÍSTICA ---
    with tabs[1]:
        st.subheader("🔄 Cruzamento com Relatório Logístico")
        if df.empty:
            st.error("Primeiro carregue a base de vendas na aba Configurações.")
        else:
            arq_log = st.file_uploader("Suba o Relatório de Logística (Carga/Pedido/Data Entrega)", type=['xlsx', 'csv'])
            if arq_log:
                df_log = pd.read_excel(arq_log) if arq_log.name.endswith('.xlsx') else pd.read_csv(arq_log, encoding='latin1', sep=None)
                df_log.columns = [str(c).strip() for c in df_log.columns]
                
                if st.button("Executar PROCV e Atualizar Dashboard"):
                    # Força Pedido para string em ambas as bases para não dar erro de match
                    mapa_entregas = df_log.set_index(df_log.columns[1])['Data Entrega'].to_dict() 
                    
                    def imputar_data(row):
                        # Se a data original estiver vazia, tenta buscar no mapa
                        if pd.isna(row['DATA_ENTREGA']):
                            ped = str(row['PEDIDO'])
                            if ped in mapa_entregas:
                                return pd.to_datetime(mapa_entregas[ped])
                        return row['DATA_ENTREGA']

                    df['DATA_ENTREGA'] = df.apply(imputar_data, axis=1)
                    st.session_state.base_mestra = df
                    st.success("Dados atualizados!")
                    st.rerun()

    # --- ABA 3: CONFIGURAÇÕES ---
    with tabs[2]:
        st.subheader("⚙️ Importação de Dados")
        arq = st.file_uploader("Upload Planilha de Vendas (Principal)", type=['csv', 'xlsx'])
        if arq:
            df_raw = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
            # Aqui aplicamos o tratamento que cria as colunas DATA_EMISSAO e DATA_ENTREGA
            st.session_state.base_mestra = tratar_dados_oficial(df_raw)
            st.success("Base de Vendas carregada com sucesso!")
            st.rerun()
        
        if st.button("🗑️ Resetar Tudo"):
            st.session_state.base_mestra = pd.DataFrame()
            st.rerun()
