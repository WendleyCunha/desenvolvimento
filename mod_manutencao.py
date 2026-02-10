import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    """
    Limpa nomes de colunas e prepara a base com a lógica de IDs Únicos.
    """
    # 1. Ajuste de nomes e encoding
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]
    mapeamento = {
        'Dt EmissÃ£o': 'Data Emissão', 'Dt Emissão': 'Data Emissão',
        'OrÃ§amento': 'Orçamento', 'OrÂ§amento': 'Orçamento',
        'Data Ent': 'Data Entrega', 'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 2. Conversão de Datas (Trata '//' como nulo automaticamente)
    for col in ['Data Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # 3. Criação do ID Híbrido (Se não tem pedido, usa orçamento)
    # Isso garante que não perderemos os registros 002-RETIRA
    df['ID_Hibrido'] = df['Pedido'].fillna(df['Orçamento']).astype(str)

    # 4. Tratamento Financeiro
    for col in ['Valor Venda', 'Custo']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['Margem R$'] = df['Valor Venda'] - df['Custo']
    return df

def exibir_manutencao(user_role):
    st.title("🏗️ Dashboard 360 - Eficiência de Vendas")
    
    tab_dash, tab_config = st.tabs(["📊 Análise Operacional", "⚙️ Configurações"])

    with tab_config:
        arquivo = st.file_uploader("Subir planilha de vendas", type=['xlsx', 'csv', 'xls'])
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin1')
                else:
                    engine = 'xlrd' if arquivo.name.endswith('.xls') else 'openpyxl'
                    df_raw = pd.read_excel(arquivo, engine=engine)
                
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("Dados processados com sucesso! Vá para a aba Dashboard.")
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # --- SEÇÃO 1: CONFERÊNCIA DE BASE (ID ÚNICOS) ---
            # Aqui validamos os números que você notou (193 vs 205)
            pedidos_reais = df['Pedido'].dropna().nunique()
            orcamentos_reais = df['Orçamento'].dropna().nunique()
            
            st.subheader("🔍 Conferência de Identificadores")
            c_inf1, c_inf2, c_inf3 = st.columns(3)
            c_inf1.metric("Pedidos Únicos", f"{pedidos_reais}")
            c_inf2.metric("Orçamentos Únicos", f"{orcamentos_reais}")
            c_inf3.info("Nota: O tipo 002-RETIRA geralmente utiliza o número do Orçamento.")

            st.divider()

            # Base consolidada para análise de tipos (Usa o ID Híbrido)
            df_unicos = df.drop_duplicates(subset=['ID_Hibrido'])
            total_operacoes = len(df_unicos)

            # --- SEÇÃO 2: FOCO 004-ENCOMENDA ---
            st.subheader("📦 Volume de Encomendas (004)")
            df_004 = df_unicos[df_unicos['Tipo Venda'].str.contains('004', na=False)]
            qtd_004 = len(df_004)
            perc_004 = (qtd_004 / total_operacoes * 100) if total_operacoes > 0 else 0
            
            col_e1, col_e2 = st.columns(2)
            col_e1.metric("Qtd Encomendas", f"{qtd_004} pedidos")
            col_e2.metric("% do Total de Operações", f"{perc_004:.1f}%")

            st.divider()

            # --- SEÇÃO 3: FOCO 003-ENTREGA (SLA vs ESCOLHA CLIENTE) ---
            st.subheader("🚚 Eficiência de Entrega (003)")
            df_003 = df_unicos[df_unicos['Tipo Venda'].str.contains('003', na=False)].copy()
            
            # Removemos registros sem data para o cálculo de SLA ser real
            df_003 = df_003.dropna(subset=['Data Emissão', 'Data Entrega'])
            
            if not df_003.empty:
                # Cálculo de dias úteis (Exclui Sábado e Domingo)
                emissao = df_003['Data Emissão'].values.astype('datetime64[D]')
                entrega = df_003['Data Entrega'].values.astype('datetime64[D]')
                df_003['Dias_Uteis'] = np.busday_count(emissao, entrega)
                
                # Separação
                qtd_48h = len(df_003[df_003['Dias_Uteis'] <= 2])
                qtd_agendado = len(df_003[df_003['Dias_Uteis'] > 2])
                total_003 = len(df_003)
                
                p_48h = (qtd_48h / total_003 * 100)
                p_agendado = (qtd_agendado / total_003 * 100)

                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    st.metric("Padrão: Até 48h Úteis", f"{qtd_48h}", f"{p_48h:.1f}%")
                    st.caption("Pedidos que nasceram dentro da janela operacional ideal.")
                
                with col_s2:
                    st.metric("Agendados / Outros", f"{qtd_agendado}", f"{p_agendado:.1f}%", delta_color="off")
                    st.caption("Pedidos com prazos maiores (Escolha do cliente ou logística).")

                # Gráfico de Pizza exclusivo para o comportamento do 003
                st.write("#### Perfil de Agendamento do Cliente (Tipo 003)")
                st.plotly_chart({
                    "data": [{"values": [qtd_48h, qtd_agendado], "labels": ["Dentro 48h", "Agendado > 48h"], "type": "pie", "hole": .5, "marker": {"colors": ["#00CC96", "#636EFA"]}}],
                    "layout": {"height": 300, "margin": dict(l=0, r=0, t=30, b=0)}
                }, use_container_width=True)
            else:
                st.warning("Não há dados de 'Data Entrega' suficientes para analisar o SLA do Tipo 003.")

        else:
            st.info("Aguardando upload de dados na aba Configurações.")
