import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# =========================================================
# 1. FUNÇÕES DE TRATAMENTO (PADRONIZAÇÃO)
# =========================================================
def tratar_dados_oficial(df):
    if df.empty: return df
    
    # Limpa nomes de colunas (tira espaços e aspas)
    df.columns = [str(col).strip() for col in df.columns]
    
    # MAPEAMENTO INTELIGENTE (Baseado nos seus arquivos reais)
    # Aqui tratamos o 'Data Ent' da Venda e o 'Data Entrega' da DAI
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA',      # Nome no arquivo de Vendas
        'Data Entrega': 'DATA_ENTREGA',  # Nome no arquivo DAI
        'Pedido': 'PEDIDO'
    }
    df = df.rename(columns=mapeamento)
    
    # Garante que as colunas essenciais existam (mesmo que vazias)
    for col_essencial in ['DATA_EMISSAO', 'DATA_ENTREGA', 'PEDIDO']:
        if col_essencial not in df.columns:
            df[col_essencial] = np.nan

    # Tratamento de Datas
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        df[col] = df[col].astype(str).replace(['/ /', 'nan', 'NaT', '//', '', 'None'], np.nan)
        df[col] = pd.to_datetime(df[col], dayfirst=True, errors='coerce')
    
    # Limpa Pedido e REMOVE DUPLICADOS (Sua solicitação)
    # Um pedido com vários produtos vira apenas uma linha para o Dashboard
    if 'PEDIDO' in df.columns:
        df['PEDIDO'] = df['PEDIDO'].astype(str).str.replace('.0', '', regex=False).str.strip()
        df = df.drop_duplicates(subset=['PEDIDO'], keep='first')
        
    return df

def calcular_sla_48h(dt_emissao, dt_entrega):
    if pd.isna(dt_emissao) or pd.isna(dt_entrega): 
        return "Sem Agenda"
    try:
        # np.busday_count calcula dias úteis (Seg-Sex)
        d1 = np.datetime64(dt_emissao, 'D')
        d2 = np.datetime64(dt_entrega, 'D')
        dias_uteis = np.busday_count(d1, d2)
        return "Até 48h" if dias_uteis <= 2 else "Acima de 48h"
    except:
        return "Erro Data"

# =========================================================
# 2. MÓDULO PRINCIPAL (CHAMADO PELO SEU MAIN.PY)
# =========================================================
def main():
    st.subheader("🏗️ Auditoria de Performance e Prazos")

    # Inicializa a base na sessão se não existir
    if 'base_mestra' not in st.session_state: 
        st.session_state.base_mestra = pd.DataFrame()
    
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🔄 Integrar Logística (DAI)", "⚙️ Configurações"])
    
    # Atalho para a base
    df = st.session_state.base_mestra

    # --- ABA 1: DASHBOARD ---
    with tab1:
        if not df.empty:
            # Cálculo do Status de SLA
            df['SLA_STATUS'] = df.apply(lambda x: calcular_sla_48h(x['DATA_EMISSAO'], x['DATA_ENTREGA']), axis=1)
            
            c1, c2, c3 = st.columns(3)
            total = len(df)
            no_prazo = len(df[df['SLA_STATUS'] == "Até 48h"])
            atrasado = len(df[df['SLA_STATUS'] == "Acima de 48h"])
            sem_data = len(df[df['SLA_STATUS'] == "Sem Agenda"])
            
            c1.metric("Pedidos Únicos", total)
            c2.metric("No Prazo (48h Úteis)", no_prazo)
            c3.metric("Sem Agenda", sem_data)
            
            fig = px.pie(df, names='SLA_STATUS', hole=0.4,
                         color='SLA_STATUS',
                         color_discrete_map={'Até 48h':'#2ecc71', 'Acima de 48h':'#e74c3c', 'Sem Agenda':'#bdc3c7'},
                         title="Cumprimento de Prazo (Base Única)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("💡 Vá em 'Configurações' e carregue a Base de Vendas.")

    # --- ABA 2: O PULO DO GATO (CRUZAMENTO) ---
    with tab2:
        st.write("### Imputar Datas da Logística")
        if df.empty:
            st.warning("Carregue a base de vendas primeiro.")
        else:
            arq_dai = st.file_uploader("Upload Base DAI 01 2026", type=['csv', 'xlsx'])
            if arq_dai:
                # Lê e padroniza a DAI
                df_dai = pd.read_csv(arq_dai, encoding='latin-1', sep=None) if arq_dai.name.endswith('.csv') else pd.read_excel(arq_dai)
                df_dai = tratar_dados_oficial(df_dai)
                
                if st.button("Executar Cruzamento de Pedidos"):
                    # Mapa de Pedido -> Data Entrega vindo da DAI
                    mapa_dai = df_dai.set_index('PEDIDO')['DATA_ENTREGA'].to_dict()
                    
                    def atualizar_data(row):
                        # Só preenche se a data original na Venda for nula
                        if pd.isna(row['DATA_ENTREGA']):
                            return mapa_dai.get(row['PEDIDO'], row['DATA_ENTREGA'])
                        return row['DATA_ENTREGA']
                    
                    df['DATA_ENTREGA'] = df.apply(atualizar_data, axis=1)
                    st.session_state.base_mestra = df
                    st.success(f"Processado! Pedidos únicos atualizados.")
                    st.rerun()

    # --- ABA 3: CONFIGURAÇÕES ---
    with tab3:
        st.write("### Carregar Base Mestra")
        arq_vendas = st.file_uploader("Upload Base Vendas 01 2026", type=['csv', 'xlsx'])
        if arq_vendas:
            df_raw = pd.read_csv(arq_vendas, encoding='latin-1', sep=None, engine='python') if arq_vendas.name.endswith('.csv') else pd.read_excel(arq_vendas)
            st.session_state.base_mestra = tratar_dados_oficial(df_raw)
            st.success("Base de Vendas carregada e duplicados removidos!")
            st.rerun()
        
        if st.button("🗑️ Limpar Base Atual"):
            st.session_state.base_mestra = pd.DataFrame()
            st.rerun()
