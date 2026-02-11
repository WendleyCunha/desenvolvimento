import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados_oficiais(df):
    """Trata os dados com base nos nomes exatos fornecidos pelo usuário."""
    if df.empty:
        return df
    
    # 1. Padronização de nomes (Garante que espaços extras não quebrem o código)
    df.columns = [str(col).strip() for col in df.columns]
    
    # 2. Conversão de Datas (Trata o padrão '/ /' do Protheus como nulo)
    colunas_data = ['Dt Emissão', 'Dt Agendamento', 'Data Liberação', 'Data Prevista', 'Data Entrega']
    for col in colunas_data:
        if col in df.columns:
            # Transforma '/ /' em NaT (Not a Time) para não bugar cálculos
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # 3. Conversão Numérica (Valor Venda e Custo)
    for col in ['Valor Venda', 'Custo']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    return df

def processar_inteligencia_retrabalho(df_novo):
    """Acumula dados e identifica o re-trabalho por cliente."""
    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()

    if not df_novo.empty:
        base_total = pd.concat([st.session_state.base_mestra, df_novo], ignore_index=True)
        
        # Unicidade pelo número do Pedido
        if 'Pedido' in base_total.columns:
            base_total = base_total.drop_duplicates(subset=['Pedido'], keep='first')
        
        # Lógica de Sequência (Re-trabalho): Ordena por Cliente e Data de Emissão
        if 'Cliente' in base_total.columns and 'Dt Emissão' in base_total.columns:
            base_total = base_total.sort_values(['Cliente', 'Dt Emissão'])
            # 1 = Venda Original, >1 = Re-trabalho/Novo Pedido do mesmo cliente
            base_total['Seq_Pedido'] = base_total.groupby('Cliente').cumcount() + 1
            
        st.session_state.base_mestra = base_total
    
    return st.session_state.base_mestra

def main():
    st.title("🏗️ Módulo de Manutenção e Eficiência")

    with st.expander("📤 Upload da Planilha King Star", expanded=True):
        arquivo = st.file_uploader("Selecione o arquivo CSV ou Excel", type=['xlsx', 'csv'])
        
        if arquivo:
            try:
                # Carrega o arquivo
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo)
                else:
                    df_raw = pd.read_excel(arquivo)
                
                # Processa com os novos nomes de colunas
                df_limpo = tratar_dados_oficiais(df_raw)
                df_base = processar_inteligencia_retrabalho(df_limpo)
                st.success(f"✅ Sucesso! {len(df_base)} registros na base mestra.")
            except Exception as e:
                st.error(f"Erro ao processar títulos: {e}")

    # Visualização
    if 'base_mestra' in st.session_state and not st.session_state.base_mestra.empty:
        df = st.session_state.base_mestra
        
        tab1, tab2 = st.tabs(["📊 Painel CEO", "🚨 Apuração de Re-trabalho"])

        with tab1:
            # Define o que é re-trabalho (Seq_Pedido > 1)
            re_trabalho = df[df['Seq_Pedido'] > 1].copy()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total de Pedidos", len(df))
            c2.metric("Casos Re-trabalho", len(re_trabalho))
            
            valor_retrabalho = re_trabalho['Valor Venda'].sum() if 'Valor Venda' in re_trabalho.columns else 0
            c3.metric("Impacto Financeiro", f"R$ {valor_retrabalho:,.2f}")

            if not re_trabalho.empty:
                st.write("### Ofensores por Vendedor")
                st.bar_chart(re_trabalho['Vendedor'].value_counts())

        with tab2:
            st.subheader("🚨 Auditoria de Fluxos Repetidos")
            if not re_trabalho.empty:
                if 'Motivo' not in re_trabalho.columns:
                    re_trabalho['Motivo'] = "Análise Pendente"
                
                # Exibe colunas cruciais
                colunas_view = ['Pedido', 'Cliente', 'Dt Emissão', 'Tipo Venda', 'Valor Venda', 'Motivo']
                df_ed = st.data_editor(re_trabalho[colunas_view], use_container_width=True, key="editor_king")
                
                csv = df_ed.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 Exportar Relatório", csv, "retrabalho_pqi.csv", "text/csv")
            else:
                st.success("Nenhum re-trabalho identificado.")

if __name__ == "__main__":
    main()
