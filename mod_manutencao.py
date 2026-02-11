import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados_protheus(df):
    # Correção de encoding para colunas como "Dt EmissÃ£o"
    df.columns = [str(col).strip().encode('latin1').decode('utf-8', 'ignore') 
                  if isinstance(col, str) else str(col).strip() for col in df.columns]
    
    mapeamento = {
        'Dt EmissÃ£o': 'Dt_Emissao', 'Dt Emissao': 'Dt_Emissao',
        'Data Ent': 'Dt_Entrega', 'Cliente': 'ID_Cliente',
        'Tipo Venda': 'Tipo_Venda', 'Valor Venda': 'Valor_Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    for col in ['Dt_Emissao', 'Dt_Entrega', 'Data Prev']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    if 'Valor_Venda' in df.columns:
        if df['Valor_Venda'].dtype == 'object':
            df['Valor_Venda'] = df['Valor_Venda'].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
        df['Valor_Venda'] = pd.to_numeric(df['Valor_Venda'], errors='coerce').fillna(0)
        
    return df

def processar_base_acumulada(df_novo):
    if 'base_acumulada' not in st.session_state:
        st.session_state.base_acumulada = df_novo
    else:
        base_total = pd.concat([st.session_state.base_acumulada, df_novo], ignore_index=True)
        # Regra: Se o número do PEDIDO for igual, mantém o antigo e ignora o novo
        base_total = base_total.drop_duplicates(subset=['Pedido'], keep='first')
        st.session_state.base_acumulada = base_total

    df = st.session_state.base_acumulada
    
    # Lógica do Re-trabalho: Se o Cliente (Coluna J) aparece com um NOVO Pedido
    df = df.sort_values(['ID_Cliente', 'Dt_Emissao'])
    df['Seq_Pedido_Cliente'] = df.groupby('ID_Cliente').cumcount() + 1
    
    return df

def main():
    st.title("🏗️ Módulo de Manutenção e Eficiência")
    
    with st.expander("📤 Upload de Planilha Protheus", expanded=True):
        # ADICIONADO 'xls' na lista de tipos aceitos
        arquivo = st.file_uploader("Selecione o arquivo (XLS, XLSX ou CSV)", type=['xlsx', 'csv', 'xls'], key="up_manut")
        
        if arquivo:
            try:
                # Lógica para ler diferentes formatos
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1')
                else:
                    # 'xlrd' é necessário para arquivos .xls antigos
                    df_raw = pd.read_excel(arquivo)
                
                df_limpo = tratar_dados_protheus(df_raw)
                df_final = processar_base_acumulada(df_limpo)
                st.success(f"✅ Arquivo '{arquivo.name}' integrado com sucesso!")
            except Exception as e:
                st.error(f"❌ Erro ao processar: {e}. Verifique se o arquivo não está corrompido.")

    if 'base_acumulada' in st.session_state and not st.session_state.base_acumulada.empty:
        df = st.session_state.base_acumulada
        # Recalcula a sequência para garantir que novos uploads ativem a apuração
        df = df.sort_values(['ID_Cliente', 'Dt_Emissao'])
        df['Seq_Pedido_Cliente'] = df.groupby('ID_Cliente').cumcount() + 1

        tab1, tab2 = st.tabs(["📊 Dashboard CEO", "🚨 Apuração de Re-trabalho"])

        with tab1:
            re_trabalho = df[df['Seq_Pedido_Cliente'] > 1]
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Pedidos", len(df))
            c2.metric("Casos Re-trabalho", len(re_trabalho))
            c3.metric("Custo Estimado", f"R$ {re_trabalho['Valor_Venda'].sum():,.2f}")
            
            if not re_trabalho.empty:
                st.subheader("Pareto de Re-trabalho (Por Vendedor)")
                st.bar_chart(re_trabalho['Vendedor'].value_counts())

        with tab2:
            st.subheader("🚨 Pedidos Identificados como Re-trabalho")
            df_audit = re_trabalho.copy()
            
            if not df_audit.empty:
                if 'Motivo' not in df_audit.columns:
                    df_audit['Motivo'] = "Aguardando análise..."
                
                # Editor interativo para você preencher os motivos
                df_editado = st.data_editor(
                    df_audit[['Pedido', 'ID_Cliente', 'Dt_Emissao', 'Tipo_Venda', 'Valor_Venda', 'Motivo']],
                    use_container_width=True,
                    key="editor_apuracao_final"
                )
                
                # Botão para baixar o Excel com seus comentários para o CEO
                csv = df_editado.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Baixar Relatório para Reunião", csv, "apuracao_retrabalho.csv", "text/csv")
    else:
        st.info("Suba uma planilha para iniciar a análise perita de re-trabalho.")

# Se você rodar este arquivo sozinho para teste, ele funciona:
if __name__ == "__main__":
    main()
