import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados_protheus(df):import streamlit as st
import pandas as pd
import numpy as np

def normalizar_colunas(df):
    """Remove acentos, espaços e caracteres especiais das colunas do Protheus."""
    if df.empty:
        return df
    
    # Limpeza profunda de encoding (Trata o Dt EmissÃ£o)
    df.columns = [
        str(col).strip().encode('latin1', 'ignore').decode('utf-8', 'ignore').upper() 
        for col in df.columns
    ]
    
    # Dicionário de sinônimos para garantir que o código ache o que precisa
    mapeamento = {
        'DT EMISSAO': 'DT_EMISSAO', 'DT EMISSAO': 'DT_EMISSAO',
        'DATA ENT': 'DT_ENTREGA', 'CLIENTE': 'ID_CLIENTE',
        'TIPO VENDA': 'TIPO_VENDA', 'VALOR VENDA': 'VALOR_VENDA',
        'PEDIDO': 'PEDIDO', 'VENDEDOR': 'VENDEDOR'
    }
    
    # Renomeia o que encontrar de compatível
    for col_original, col_nova in mapeamento.items():
        for col_df in df.columns:
            if col_original in col_df:
                df.rename(columns={col_df: col_nova}, inplace=True)
                
    return df

def processar_base_acumulada(df_novo):
    if 'base_acumulada' not in st.session_state:
        st.session_state.base_acumulada = pd.DataFrame()

    if not df_novo.empty:
        # 1. Combina bases
        base_combinada = pd.concat([st.session_state.base_acumulada, df_novo], ignore_index=True)
        
        # 2. Regra: Se o PEDIDO for igual, mantém o antigo (Desconsidera a linha nova)
        if 'PEDIDO' in base_combinada.columns:
            base_combinada = base_combinada.drop_duplicates(subset=['PEDIDO'], keep='first')
        
        # 3. Lógica do Re-trabalho: Se o CLIENTE aparece com novo PEDIDO
        if 'ID_CLIENTE' in base_combinada.columns and 'DT_EMISSAO' in base_combinada.columns:
            base_combinada = base_combinada.sort_values(['ID_CLIENTE', 'DT_EMISSAO'])
            base_combinada['SEQ_PEDIDO_CLIENTE'] = base_combinada.groupby('ID_CLIENTE').cumcount() + 1
            
        st.session_state.base_acumulada = base_combinada
    
    return st.session_state.base_acumulada

def main():
    st.title("🏗️ Módulo de Manutenção e Eficiência")
    
    with st.expander("📤 Upload de Planilha Protheus", expanded=True):
        arquivo = st.file_uploader("Selecione o arquivo", type=['xlsx', 'csv', 'xls'], key="up_v5")
        
        if arquivo:
            try:
                # Carregamento flexível
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                # Processamento
                df_limpo = normalizar_colunas(df_raw)
                df_final = processar_base_acumulada(df_limpo)
                st.success("✅ Dados integrados com sucesso!")
            except Exception as e:
                st.error(f"Erro no processamento: {e}")

    # Exibição segura dos dados
    if 'base_acumulada' in st.session_state and not st.session_state.base_acumulada.empty:
        df = st.session_state.base_acumulada
        
        # Só exibe se a coluna de sequência foi criada com sucesso
        if 'SEQ_PEDIDO_CLIENTE' in df.columns:
            tab1, tab2 = st.tabs(["📊 Dashboard CEO", "🚨 Apuração"])
            
            re_trabalho = df[df['SEQ_PEDIDO_CLIENTE'] > 1].copy()
            
            with tab1:
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Pedidos", len(df))
                c2.metric("Casos Re-trabalho", len(re_trabalho))
                
                # Conversão de valor para cálculo de impacto
                if 'VALOR_VENDA' in re_trabalho.columns:
                    if re_trabalho['VALOR_VENDA'].dtype == 'object':
                        re_trabalho['VALOR_VENDA'] = pd.to_numeric(re_trabalho['VALOR_VENDA'].astype(str).str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.'), errors='coerce')
                    
                    c3.metric("Impacto Financeiro", f"R$ {re_trabalho['VALOR_VENDA'].sum():,.2f}")
                
                if not re_trabalho.empty and 'VENDEDOR' in re_trabalho.columns:
                    st.write("### Ofensores por Vendedor")
                    st.bar_chart(re_trabalho['VENDEDOR'].value_counts())

            with tab2:
                st.subheader("🚨 Detalhamento de Re-trabalho")
                if 'MOTIVO' not in re_trabalho.columns:
                    re_trabalho['MOTIVO'] = "Inserir motivo..."
                
                # Editor interativo
                colunas_view = [c for c in ['PEDIDO', 'ID_CLIENTE', 'DT_EMISSAO', 'TIPO_VENDA', 'VALOR_VENDA', 'MOTIVO'] if c in re_trabalho.columns]
                df_editado = st.data_editor(re_trabalho[colunas_view], use_container_width=True, key="editor_v5")
                
                # Exportação
                csv = df_editado.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Exportar Relatório para CEO", csv, "apuracao_retrabalho.csv", "text/csv")
        else:
            st.warning("⚠️ Planilha carregada, mas as colunas 'CLIENTE' ou 'PEDIDO' não foram localizadas. Verifique o cabeçalho.")
    if df.empty:
        return df
    
    # 1. Limpeza Radical de Colunas: Remove espaços e trata o "Ã£" do Protheus
    df.columns = [
        str(col).strip().encode('latin1', 'ignore').decode('utf-8', 'ignore') 
        for col in df.columns
    ]
    
    # 2. Mapeamento Forçado (Garante que o código encontre as colunas da sua imagem)
    mapeamento = {
        'Dt EmissÃ£o': 'Dt_Emissao', 
        'Dt Emissao': 'Dt_Emissao',
        'Data Ent': 'Dt_Entrega', 
        'Cliente': 'ID_Cliente',
        'Tipo Venda': 'Tipo_Venda',
        'Valor Venda': 'Valor_Venda',
        'Pedido': 'Pedido',
        'Vendedor': 'Vendedor'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 3. Conversão de Datas e Valores
    for col in ['Dt_Emissao', 'Dt_Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    if 'Valor_Venda' in df.columns:
        if df['Valor_Venda'].dtype == 'object':
            df['Valor_Venda'] = df['Valor_Venda'].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
        df['Valor_Venda'] = pd.to_numeric(df['Valor_Venda'], errors='coerce').fillna(0)
        
    return df

def processar_calculo_retrabalho(df):
    # Só tenta calcular se as colunas essenciais existirem
    if not df.empty and 'ID_Cliente' in df.columns and 'Dt_Emissao' in df.columns:
        df = df.sort_values(['ID_Cliente', 'Dt_Emissao'])
        # AQUI É ONDE A COLUNA DO ERRO É CRIADA:
        df['Seq_Pedido_Cliente'] = df.groupby('ID_Cliente').cumcount() + 1
    return df

def main():
    st.title("🏗️ Módulo de Manutenção e Eficiência")
    
    # Inicializa a base na sessão se não existir
    if 'base_acumulada' not in st.session_state:
        st.session_state.base_acumulada = pd.DataFrame()

    with st.expander("📤 Upload de Planilha Protheus", expanded=True):
        # Aceita XLS, XLSX e CSV
        arquivo = st.file_uploader("Selecione o arquivo", type=['xlsx', 'csv', 'xls'], key="up_manut_v4")
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                df_limpo = tratar_dados_protheus(df_raw)
                
                # Une com a base existente e remove duplicados de PEDIDO
                base_atual = st.session_state.base_acumulada
                base_nova = pd.concat([base_atual, df_limpo], ignore_index=True)
                
                if 'Pedido' in base_nova.columns:
                    base_nova = base_nova.drop_duplicates(subset=['Pedido'], keep='first')
                
                # Recalcula a sequência (O Pulo do Gato)
                st.session_state.base_acumulada = processar_calculo_retrabalho(base_nova)
                st.success("✅ Dados integrados e analisados!")
            except Exception as e:
                st.error(f"❌ Erro: {e}")

    # EXIBIÇÃO: Só entra se a coluna 'Seq_Pedido_Cliente' realmente existir
    df = st.session_state.base_acumulada
    if not df.empty and 'Seq_Pedido_Cliente' in df.columns:
        
        tab1, tab2 = st.tabs(["📊 Visão CEO", "🚨 Apuração"])

        with tab1:
            # Filtro seguro para Re-trabalho
            re_trabalho = df[df['Seq_Pedido_Cliente'] > 1].copy()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total de Pedidos", len(df))
            c2.metric("Casos de Re-trabalho", len(re_trabalho))
            
            val = re_trabalho['Valor_Venda'].sum() if 'Valor_Venda' in re_trabalho.columns else 0
            c3.metric("Impacto Financeiro", f"R$ {val:,.2f}")

            if not re_trabalho.empty and 'Vendedor' in re_trabalho.columns:
                st.subheader("Ofensores por Vendedor")
                st.bar_chart(re_trabalho['Vendedor'].value_counts())

        with tab2:
            st.subheader("🚨 Pedidos para Auditoria (Re-trabalho)")
            if not re_trabalho.empty:
                if 'Motivo' not in re_trabalho.columns:
                    re_trabalho['Motivo'] = "Analisar"
                
                # Mostra apenas as colunas que interessam ao CEO
                cols_v = [c for c in ['Pedido', 'ID_Cliente', 'Dt_Emissao', 'Tipo_Venda', 'Valor_Venda', 'Motivo'] if c in re_trabalho.columns]
                
                df_ed = st.data_editor(re_trabalho[cols_v], use_container_width=True, key="ed_manut_final")
                
                csv = df_ed.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Baixar Relatório", csv, "apuracao_kingstar.csv", "text/csv")
            else:
                st.success("Nenhum re-trabalho detectado!")
    else:
        if not df.empty:
            st.warning("⚠️ Os dados foram carregados, mas as colunas 'Cliente' ou 'Pedido' não foram identificadas corretamente.")
        else:
            st.info("Suba a planilha do Protheus para iniciar.")
