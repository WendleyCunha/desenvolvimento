import streamlit as st
import pandas as pd
import numpy as np

# 1. Função de Limpeza (Trata o "Dt EmissÃ£o" da sua imagem)
def tratar_dados_protheus(df):
    if df.empty:
        return df
    
    # Limpa nomes das colunas de caracteres estranhos
    df.columns = [str(col).strip().encode('latin1', 'ignore').decode('utf-8', 'ignore') for col in df.columns]
    
    # Dicionário de tradução para bater com o seu Excel
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

    # Converte datas
    for col in ['Dt_Emissao', 'Dt_Entrega', 'Data Prev']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Limpa valores financeiros (Tira o R$ e pontos)
    if 'Valor_Venda' in df.columns:
        if df['Valor_Venda'].dtype == 'object':
            df['Valor_Venda'] = df['Valor_Venda'].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
        df['Valor_Venda'] = pd.to_numeric(df['Valor_Venda'], errors='coerce').fillna(0)
        
    return df

# 2. Função de Acúmulo e Re-trabalho
def processar_logica_retrabalho(df_novo=None):
    if 'base_acumulada' not in st.session_state:
        st.session_state.base_acumulada = pd.DataFrame()

    if df_novo is not None and not df_novo.empty:
        # Junta a base antiga com a nova
        base_total = pd.concat([st.session_state.base_acumulada, df_novo], ignore_index=True)
        # Se o número do PEDIDO for igual, mantém o primeiro e ignora o novo
        if 'Pedido' in base_total.columns:
            base_total = base_total.drop_duplicates(subset=['Pedido'], keep='first')
        st.session_state.base_acumulada = base_total

    df = st.session_state.base_acumulada

    # Identifica Re-trabalho (Novo Pedido para o mesmo Cliente)
    if not df.empty and 'ID_Cliente' in df.columns and 'Dt_Emissao' in df.columns:
        df = df.sort_values(['ID_Cliente', 'Dt_Emissao'])
        df['Seq_Pedido_Cliente'] = df.groupby('ID_Cliente').cumcount() + 1
        st.session_state.base_acumulada = df
    
    return df

# 3. Função Principal chamada pelo seu Main.py
def main():
    st.title("🏗️ Módulo de Manutenção e Eficiência")
    
    with st.expander("📤 Upload de Planilha Protheus", expanded=True):
        arquivo = st.file_uploader("Selecione o arquivo", type=['xlsx', 'csv', 'xls'], key="up_manut_v3")
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                df_limpo = tratar_dados_protheus(df_raw)
                processar_logica_retrabalho(df_limpo)
                st.success("✅ Dados integrados!")
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    # Exibição dos resultados
    if 'base_acumulada' in st.session_state and not st.session_state.base_acumulada.empty:
        df = st.session_state.base_acumulada
        
        # Garante que a coluna de sequência existe
        if 'Seq_Pedido_Cliente' not in df.columns:
            df = processar_logica_retrabalho()

        t1, t2 = st.tabs(["📊 Visão CEO", "🚨 Apuração"])

        with t1:
            re_trabalho = df[df['Seq_Pedido_Cliente'] > 1].copy()
            c1, c2, c3 = st.columns(3)
            c1.metric("Pedidos Totais", len(df))
            c2.metric("Casos Re-trabalho", len(re_trabalho))
            
            v_total = re_trabalho['Valor_Venda'].sum() if 'Valor_Venda' in re_trabalho.columns else 0
            c3.metric("Impacto Financeiro", f"R$ {v_total:,.2f}")

            if not re_trabalho.empty and 'Vendedor' in re_trabalho.columns:
                st.bar_chart(re_trabalho['Vendedor'].value_counts())

        with t2:
            st.subheader("🚨 Pedidos para Auditoria")
            if not re_trabalho.empty:
                if 'Motivo' not in re_trabalho.columns:
                    re_trabalho['Motivo'] = "Analisar"
                
                # Seleciona apenas colunas que existem para evitar erros
                cols = [c for c in ['Pedido', 'ID_Cliente', 'Dt_Emissao', 'Tipo_Venda', 'Valor_Venda', 'Motivo'] if c in re_trabalho.columns]
                
                df_ed = st.data_editor(re_trabalho[cols], use_container_width=True, key="ed_final")
                
                csv = df_ed.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Baixar Relatório", csv, "apuracao.csv", "text/csv")
            else:
                st.success("Tudo limpo! Nenhum re-trabalho detectado.")
    else:
        st.info("Aguardando planilha...")
