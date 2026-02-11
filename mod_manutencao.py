import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados_protheus(df):
    if df.empty:
        return df
        
    # Limpeza de nomes de colunas (Tratando o 'Ã£' e espaços)
    df.columns = [str(col).strip().encode('latin1').decode('utf-8', 'ignore') 
                  if isinstance(col, str) else str(col).strip() for col in df.columns]
    
    # Dicionário de tradução das colunas do Protheus para o sistema
    mapeamento = {
        'Dt EmissÃ£o': 'Dt_Emissao', 
        'Dt Emissao': 'Dt_Emissao',
        'Data Ent': 'Dt_Entrega', 
        'Cliente': 'ID_Cliente',
        'Tipo Venda': 'Tipo_Venda', 
        'Valor Venda': 'Valor_Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # Garante que as colunas existam antes de converter
    for col in ['Dt_Emissao', 'Dt_Entrega', 'Data Prev']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    if 'Valor_Venda' in df.columns:
        if df['Valor_Venda'].dtype == 'object':
            df['Valor_Venda'] = df['Valor_Venda'].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
        df['Valor_Venda'] = pd.to_numeric(df['Valor_Venda'], errors='coerce').fillna(0)
        
    return df

def processar_base_acumulada(df_novo):
    # Se recebemos um dataframe vazio e não temos base, não fazemos nada
    if df_novo.empty and 'base_acumulada' not in st.session_state:
        return pd.DataFrame()

    if 'base_acumulada' not in st.session_state:
        st.session_state.base_acumulada = df_novo
    elif not df_novo.empty:
        # Une a base existente com os novos dados
        base_total = pd.concat([st.session_state.base_acumulada, df_novo], ignore_index=True)
        # Remove duplicados pelo número do pedido
        base_total = base_total.drop_duplicates(subset=['Pedido'], keep='first')
        st.session_state.base_acumulada = base_total

    df = st.session_state.base_acumulada

    # Blindagem: Só ordena se as colunas necessárias existirem no DF
    if not df.empty and 'ID_Cliente' in df.columns and 'Dt_Emissao' in df.columns:
        df = df.sort_values(['ID_Cliente', 'Dt_Emissao'])
        df['Seq_Pedido_Cliente'] = df.groupby('ID_Cliente').cumcount() + 1
    
    return df

def main():
    st.title("🏗️ Módulo de Manutenção e Eficiência")
    
    with st.expander("📤 Upload de Planilha Protheus", expanded=True):
        arquivo = st.file_uploader("Selecione o arquivo (XLS, XLSX ou CSV)", type=['xlsx', 'csv', 'xls'], key="up_manut")
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                # 1. Trata os dados primeiro
                df_limpo = tratar_dados_protheus(df_raw)
                # 2. Processa o acúmulo e re-trabalho
                df_final = processar_base_acumulada(df_limpo)
                st.success(f"✅ Dados integrados!")
            except Exception as e:
                st.error(f"❌ Erro ao processar arquivo: {e}")

    # Verifica se existe base para exibir o Dashboard
    if 'base_acumulada' in st.session_state and not st.session_state.base_acumulada.empty:
        # Chamada segura para garantir que os cálculos de sequência estejam atualizados
        df = processar_base_acumulada(pd.DataFrame()) 

        tab1, tab2 = st.tabs(["📊 Visão CEO", "🚨 Apuração de Re-trabalho"])

        with tab1:
            # Filtros de visualização
            re_trabalho = df[df.get('Seq_Pedido_Cliente', 0) > 1]
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Pedidos", len(df))
            c2.metric("Casos Re-trabalho", len(re_trabalho))
            c3.metric("Custo Estimado", f"R$ {re_trabalho['Valor_Venda'].sum():,.2f}" if 'Valor_Venda' in re_trabalho.columns else "R$ 0,00")
            
            
            
            if not re_trabalho.empty and 'Vendedor' in re_trabalho.columns:
                st.subheader("Pareto de Re-trabalho (Por Vendedor)")
                st.bar_chart(re_trabalho['Vendedor'].value_counts())

        with tab2:
            st.subheader("🚨 Pedidos Identificados como Re-trabalho")
            if not re_trabalho.empty:
                df_audit = re_trabalho.copy()
                if 'Motivo' not in df_audit.columns:
                    df_audit['Motivo'] = "A analisar..."
                
                cols_visiveis = [c for c in ['Pedido', 'ID_Cliente', 'Dt_Emissao', 'Tipo_Venda', 'Valor_Venda', 'Motivo'] if c in df_audit.columns]
                
                df_editado = st.data_editor(df_audit[cols_visiveis], use_container_width=True, key="editor_manut_v2")
                
                csv = df_editado.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Baixar Provas para o CEO", csv, "apuracao.csv", "text/csv")
            else:
                st.success("Nenhum re-trabalho detectado.")
    else:
        st.info("Aguardando upload para análise.")

if __name__ == "__main__":
    main()
