import streamlit as st
import pandas as pd
import numpy as np

# =========================================================
# 1. TRATAMENTO ROBUSTO DE COLUNAS
# =========================================================
def tratar_dados_protheus(df):
    if df.empty:
        return df
    
    # Limpeza profunda: remove espaços, trata encoding e remove caracteres especiais
    df.columns = [
        str(col).strip().encode('latin1', errors='ignore').decode('utf-8', errors='ignore') 
        for col in df.columns
    ]
    
    # Mapeamento exato baseado na sua imagem do Protheus
    mapeamento = {
        'Dt EmissÃ£o': 'Dt_Emissao', 
        'Dt Emissao': 'Dt_Emissao',
        'Data Ent': 'Dt_Entrega', 
        'Cliente': 'ID_Cliente',
        'Tipo Venda': 'Tipo_Venda',
        'Valor Venda': 'Valor_Venda',
        'Pedido': 'Pedido'
    }
    df.rename(columns=mapeamento, inplace=True)

    # Conversão de datas (importante para o sort_values posterior)
    for col in ['Dt_Emissao', 'Dt_Entrega', 'Data Prev']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Tratamento de valores financeiros
    if 'Valor_Venda' in df.columns:
        if df['Valor_Venda'].dtype == 'object':
            df['Valor_Venda'] = df['Valor_Venda'].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
        df['Valor_Venda'] = pd.to_numeric(df['Valor_Venda'], errors='coerce').fillna(0)
        
    return df

# =========================================================
# 2. GESTÃO DE BASE MESTRA E RE-TRABALHO
# =========================================================
def processar_base_e_retrabalho(df_novo=None):
    # Inicializa a base na sessão se não existir
    if 'base_acumulada' not in st.session_state:
        st.session_state.base_acumulada = pd.DataFrame()

    # Se houver dados novos, anexa e remove duplicados de PEDIDO
    if df_novo is not None and not df_novo.empty:
        base_total = pd.concat([st.session_state.base_acumulada, df_novo], ignore_index=True)
        # Mantém apenas a primeira ocorrência do pedido (Ponto 3 do seu objetivo)
        if 'Pedido' in base_total.columns:
            base_total = base_total.drop_duplicates(subset=['Pedido'], keep='first')
        st.session_state.base_acumulada = base_total

    df = st.session_state.base_acumulada

    # CÁLCULO DO "PULO DO GATO" (Ponto 4: Novo Pedido para mesmo Cliente)
    if not df.empty and 'ID_Cliente' in df.columns and 'Dt_Emissao' in df.columns:
        df = df.sort_values(['ID_Cliente', 'Dt_Emissao'])
        # Cria a coluna que o seu erro indicou como faltante
        df['Seq_Pedido_Cliente'] = df.groupby('ID_Cliente').cumcount() + 1
        st.session_state.base_acumulada = df
    
    return df

# =========================================================
# 3. INTERFACE (CHAMADA PELO MAIN.PY)
# =========================================================
def main():
    st.title("🏗️ Módulo de Manutenção e Eficiência")
    
    # Container de Upload com suporte a XLS
    with st.expander("📤 Upload de Planilha Protheus", expanded=True):
        arquivo = st.file_uploader("Selecione o arquivo", type=['xlsx', 'csv', 'xls'], key="up_manut")
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='
