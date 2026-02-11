import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# =========================================================
# 1. ESTILO E PADRONIZAÇÃO
# =========================================================
def aplicar_estilo():
    st.markdown("""
        <style>
        .metric-card { background: #f8fafc; padding: 15px; border-radius: 10px; border-top: 4px solid #002366; text-align: center; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; margin-right: 5px; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-green { background: #dcfce7; color: #166534; }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE TRATAMENTO (ROBUSTO)
# =========================================================
def tratar_dados_oficial(df):
    if df.empty:
        return pd.DataFrame(columns=['Filial', 'DATA_EMISSAO', 'DATA_ENTREGA', 'Pedido', 'Vendedor', 'Cliente', 'TIPO_VENDA', 'VALOR', 'Seq_Pedido', 'SLA_48H'])
    
    # Limpa nomes das colunas
    df.columns = [str(col).strip() for col in df.columns]
    
    # Mapeamento para tratar o erro de encoding do Protheus (Ã£o, etc)
    mapeamento = {
        'Dt EmissÃ\x83Â£o': 'DATA_EMISSAO',
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA',
        'Data Entrega': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA',
        'Valor Venda': 'VALOR'
    }
    df = df.rename(columns=mapeamento)
    
    # Garante colunas essenciais
    cols_necessarias = ['DATA_EMISSAO', 'DATA_ENTREGA', 'TIPO_VENDA', 'Pedido', 'Cliente', 'Filial']
    for c in cols_necessarias:
        if c not in df.columns: df[c] = np.nan

    # Converte Datas
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # Cálculo de Re-trabalho
    df = df.sort_values(['Cliente', 'DATA_EMISSAO'])
    df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    
    # Cálculo de SLA 48h (Criação da coluna para evitar KeyError)
    df['SLA_48H'] = "Pendente"
    mask = df['DATA_ENTREGA'].notnull() & df['DATA_EMISSAO'].notnull()
    if mask.any():
        horas = (df.loc[mask, 'DATA_ENTREGA'] - df.loc[mask, 'DATA_EMISSAO']).dt.total_seconds() / 3600
        df.loc[mask, 'SLA_48H'] = horas.apply(lambda x: "Dentro 48h" if (0 <= x <= 48) else "Fora do Prazo")
        
    return df

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    
    # Recupera role do usuário (padrão ADM se não definido no main.py)
    user_role = st.session_state.get("user_role", "ADM")
    
    st.title("🏗️ Manutenção e Eficiência King Star")

    # Inicialização do Banco de Dados em Cache
    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    # Definição das Abas
    titulos_abas = ["📊 Performance", "🔍 Auditoria", "📋 Relatório"]
    if user_role == "ADM":
        titulos_abas.append("⚙️ Configurações")
    
    tabs = st.tabs(titulos_abas)

    # --- ABA 1: PERFORMANCE ---
    with tabs[0]:
        df = st.session_state.base_mestra
        if not df.empty and 'TIPO_VENDA' in df.columns:
            df_entregas = df[df['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)].copy()
            
            c1, c2, c3 = st.columns(3)
            total = len(df_entregas)
            # Uso de .get() ou verificação para evitar KeyError: 'SLA_48H'
            qtd_48h = len(df_entregas[df_entregas['SLA_48H'] == "Dentro 48h"]) if 'SLA_48H' in df_entregas.columns else 0
            retrabalhos = len(df_entregas[df_entregas['Seq_Pedido'] > 1]) if 'Seq_Pedido' in df_entregas.columns else 0
            
            c1.markdown(f"<div class='metric-card'>TOTAL ENTREGAS<h3>{total}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'>RE-TRABALHOS<h3>{retrabalhos}</h3></div>", unsafe_allow_html=True)
            agil = (qtd_48h / total * 100) if total > 0 else 0
            c3.markdown(f"<div class='metric-card'>AGILIDADE 48H<h3>{agil:.1f}%</h3></div>", unsafe_allow_html=True)

            if not df_entregas.empty:
                st.plotly_chart(px.bar(
                    df_entregas[df_entregas['Seq_Pedido'] > 1]['Filial'].value_counts().head(10).reset_index(),
                    x='Filial', y='count',
