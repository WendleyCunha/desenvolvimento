import streamlit as st
import pandas as pd
import numpy as np

# =========================================================
# 1. TRATAMENTO DE DADOS (PROTEÇÃO PROTHEUS)
# =========================================================
def tratar_dados_protheus(df):
    # Trata o erro de encoding do Protheus (Ã£)
    df.columns = [str(col).strip().encode('latin1').decode('utf-8', 'ignore') 
                  if isinstance(col, str) else str(col).strip() for col in df.columns]
    
    mapeamento = {
        'Dt EmissÃ£o': 'Dt_Emissao', 'Dt Emissao': 'Dt_Emissao',
        'Data Ent': 'Dt_Entrega', 'Cliente': 'ID_Cliente',
        'Tipo Venda': 'Tipo_Venda', 'Valor Venda': 'Valor_Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # Conversão de Datas
    for col in ['Dt_Emissao', 'Dt_Entrega', 'Data Prev']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Conversão Numérica
    if 'Valor_Venda' in df.columns:
        if df['Valor_Venda'].dtype == 'object':
            df['Valor_Venda'] = df['Valor_Venda'].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
        df['Valor_Venda'] = pd.to_numeric(df['Valor_Venda'], errors='coerce').fillna(0)
        
    return df

# =========================================================
# 2. LÓGICA DE COMPLEMENTAR E IDENTIFICAR RE-TRABALHO
# =========================================================
def processar_base_acumulada(df_novo):
    # Se for o primeiro upload da sessão
    if 'base_acumulada' not in st.session_state:
        st.session_state.base_acumulada = df_novo
    else:
        # Complementa: Junta a antiga com a nova
        base_total = pd.concat([st.session_state.base_acumulada, df_novo], ignore_index=True)
        # Regra: Se o Pedido for o mesmo, mantém o que já existia
        base_total = base_total.drop_duplicates(subset=['Pedido'], keep='first')
        st.session_state.base_acumulada = base_total

    df = st.session_state.base_acumulada
    
    # IDENTIFICAÇÃO DO PULO DO GATO (RE-TRABALHO)
    # Ordena para rastrear a linha do tempo do cliente
    df = df.sort_values(['ID_Cliente', 'Dt_Emissao'])
    # Marca se é o 1º, 2º ou 3º pedido daquele cliente na história
    df['Seq_Pedido_Cliente'] = df.groupby('ID_Cliente').cumcount() + 1
    
    return df

# =========================================================
# 3. FUNÇÃO CHAMADA PELO MAIN.PY
# =========================================================
def main():
    st.header("🏗️ Módulo de Manutenção e Eficiência")
    
    # Upload Centralizado
    with st.expander("📤 Upload de Planilha Protheus", expanded=True):
        arquivo = st.file_uploader("Selecione o Excel ou CSV", type=['xlsx', 'csv'], key="up_manut")
        if arquivo:
            try:
                df_raw = pd.read_excel(arquivo) if arquivo.name.endswith('.xlsx') else pd.read_csv(arquivo, encoding='latin1')
                df_limpo = tratar_dados_protheus(df_raw)
                df_final = processar_base_acumulada(df_limpo)
                st.success("Dados processados e integrados com sucesso!")
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    if 'base_acumulada' in st.session_state:
        df = processar_base_acumulada(pd.DataFrame()) # Apenas para atualizar cálculos

        tab1, tab2 = st.tabs(["📊 Visão CEO", "🚨 Apuração de Re-trabalho"])

        with tab1:
            # KPIs de Green Belt
            c1, c2, c3 = st.columns(3)
            pedidos_reais = df[df['Seq_Pedido_Cliente'] == 1]
            re_trabalho = df[df['Seq_Pedido_Cliente'] > 1]
            
            c1.metric("Vendas Originais", len(pedidos_reais))
            c2.metric("Casos de Re-trabalho", len(re_trabalho))
            c3.metric("Impacto Financeiro Re-trabalho", f"R$ {re_trabalho['Valor_Venda'].sum():,.2f}")

            st.divider()
            st.write("### Ofensores de Re-trabalho por Vendedor")
            if not re_trabalho.empty:
                st.bar_chart(re_trabalho['Vendedor'].value_counts())

        with tab2:
            st.subheader("Pedidos que geraram novos fluxos (PV Y)")
            st.warning("Estes pedidos indicam que o cliente teve que comprar novamente ou houve erro no primeiro PV.")
            
            df_audit = re_trabalho.copy()
            if not df_audit.empty:
                # Campo para você preencher o motivo direto na tabela
                if 'Motivo' not in df_audit.columns:
                    df_audit['Motivo'] = "Analisar..."
                
                editado = st.data_editor(
                    df_audit[['Pedido', 'ID_Cliente', 'Dt_Emissao', 'Tipo_Venda', 'Valor_Venda', 'Motivo']],
                    use_container_width=True,
                    key="editor_apuracao_manut"
                )
                
                # Exportação para sua prova técnica
                csv = editado.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Baixar Relatório de Provas (Excel)", csv, "apuracao.csv", "text/csv")

    else:
        st.info("Suba uma planilha para ativar a análise de re-trabalho.")
