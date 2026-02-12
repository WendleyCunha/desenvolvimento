import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime

# =========================================================
# 1. MOTOR DE TRATAMENTO (AJUSTADO PARA SEUS ARQUIVOS REAIS)
# =========================================================
def tratar_dados_oficial(df):
    if df.empty: return df
    
    # Limpa nomes de colunas (remove espaços e aspas)
    df.columns = [str(col).strip() for col in df.columns]
    
    # MAPEAMENTO EXATO COM BASE NOS SEUS ARQUIVOS ENVIADOS
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA',      # O seu arquivo de vendas usa 'Data Ent'
        'Data Entrega': 'DATA_ENTREGA',  # O seu arquivo DAI usa 'Data Entrega'
        'Pedido': 'PEDIDO',
        'Tipo Venda': 'TIPO_VENDA'
    }
    df = df.rename(columns=mapeamento)
    
    # Se 'DATA_ENTREGA' não existir após o rename, cria ela vazia para evitar erro
    if 'DATA_ENTREGA' not in df.columns:
        df['DATA_ENTREGA'] = np.nan

    # Tratamento de Datas
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = df[col].astype(str).replace(['/ /', 'nan', 'NaT', '//', '', 'None'], np.nan)
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Limpeza do Pedido (remove .0 de números)
    if 'PEDIDO' in df.columns:
        df['PEDIDO'] = df['PEDIDO'].astype(str).str.replace('.0', '', regex=False).str.strip()
        
    return df

def calcular_sla_48h(dt_emissao, dt_entrega):
    if pd.isna(dt_emissao) or pd.isna(dt_entrega): 
        return "Sem Agenda"
    try:
        # np.busday_count ignora sábados e domingos
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
    st.title("🏗️ Performance King Star")

    if 'base_mestra' not in st.session_state: 
        st.session_state.base_mestra = pd.DataFrame()
    
    tabs = st.tabs(["📊 Dashboard", "🔄 Integrar Logística (DAI)", "⚙️ Configurações"])
    df = st.session_state.base_mestra

    # --- ABA 1: DASHBOARD ---
    with tabs[0]:
        if not df.empty:
            # Recalcula status para o gráfico
            df['SLA_STATUS'] = df.apply(lambda x: calcular_sla_48h(x['DATA_EMISSAO'], x['DATA_ENTREGA']), axis=1)
            
            st.subheader("📊 Resumo de Entregas")
            c1, c2, c3 = st.columns(3)
            
            total = len(df)
            no_prazo = len(df[df['SLA_STATUS'] == "Até 48h"])
            pendente = len(df[df['SLA_STATUS'] == "Sem Agenda"])
            
            c1.metric("Total Pedidos", total)
            c2.metric("No Prazo (48h Úteis)", no_prazo)
            c3.metric("Sem Agenda", pendente)
            
            fig = px.pie(df, names='SLA_STATUS', hole=0.4,
                         color='SLA_STATUS',
                         color_discrete_map={'Até 48h':'#2ecc71', 'Acima de 48h':'#e74c3c', 'Sem Agenda':'#bdc3c7'})
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(df[['PEDIDO', 'DATA_EMISSAO', 'DATA_ENTREGA', 'SLA_STATUS']].head(20))
        else:
            st.info("Aguardando upload da Base de Vendas.")

    # --- ABA 2: INTEGRAR LOGÍSTICA ---
    with tabs[1]:
        st.subheader("🔄 Pulo do Gato: Cruzamento Vendas x DAI")
        if df.empty:
            st.warning("Carregue a base de vendas primeiro.")
        else:
            arq_dai = st.file_uploader("Upload Base DAI (Logística)", type=['csv', 'xlsx'])
            if arq_dai:
                df_dai = pd.read_csv(arq_dai, encoding='latin-1', sep=None) if arq_dai.name.endswith('.csv') else pd.read_excel(arq_dai)
                df_dai = tratar_dados_oficial(df_dai) # Usa o mesmo tratamento para padronizar colunas
                
                if st.button("Cruzar Dados"):
                    # Mapa: Pedido -> Data Entrega da DAI
                    mapa_dai = df_dai.set_index('PEDIDO')['DATA_ENTREGA'].to_dict()
                    
                    def atualizar(row):
                        # Se não tem data na base de vendas, busca na DAI
                        if pd.isna(row['DATA_ENTREGA']):
                            return mapa_dai.get(row['PEDIDO'], row['DATA_ENTREGA'])
                        return row['DATA_ENTREGA']
                    
                    df['DATA_ENTREGA'] = df.apply(atualizar, axis=1)
                    st.session_state.base_mestra = df
                    st.success("Data Entrega imputada com sucesso!")
                    st.rerun()

    # --- ABA 3: CONFIGURAÇÕES ---
    with tabs[2]:
        st.subheader("⚙️ Configurações de Dados")
        arq_vendas = st.file_uploader("Upload Base Vendas (01 2026)", type=['csv', 'xlsx'])
        if arq_vendas:
            # Tenta ler com encoding automático para evitar o erro de acento
            df_raw = pd.read_csv(arq_vendas, encoding='latin-1', sep=None, engine='python') if arq_vendas.name.endswith('.csv') else pd.read_excel(arq_vendas)
            st.session_state.base_mestra = tratar_dados_oficial(df_raw)
            st.success("Base de Vendas carregada!")
            st.rerun()

if __name__ == "__main__":
    main()
