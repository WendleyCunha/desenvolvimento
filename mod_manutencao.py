import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    # Correção de Encoding e Nomes
    df.columns = [col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col for col in df.columns]
    mapeamento = {
        'Dt EmissÃ£o': 'Data Emissão', 'OrÃ§amento': 'Orçamento', 
        'Data Ent': 'Data Entrega', 'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # Conversão de Datas
    for col in ['Data Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # Tratamento Financeiro
    for col in ['Valor Venda', 'Custo']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # ID Único Híbrido para não perder os dados do 002
    df['ID_Hibrido'] = df['Pedido'].fillna(df['Orçamento']).astype(str)
    return df

def exibir_manutencao(user_role):
    st.title("🏗️ Dashboard de Eficiência Operacional")
    
    if 'dados_vendas' in st.session_state:
        df = st.session_state['dados_vendas']
        
        # --- BLOCO DE CONFERÊNCIA (Os números que você notou) ---
        pedidos_unicos = df['Pedido'].dropna().unique().size # Deve bater ~193/194
        orcamentos_unicos = df['Orçamento'].dropna().unique().size # Deve bater ~205
        
        st.subheader("🔍 Conferência de Base")
        c1, c2 = st.columns(2)
        c1.metric("Pedidos Únicos (Planilha)", pedidos_unicos)
        c2.metric("Orçamentos Únicos (Planilha)", orcamentos_unicos)
        st.divider()

        # Criando base de IDs Únicos para análise de tipos
        df_unicos = df.drop_duplicates(subset=['ID_Hibrido'])
        total_geral = len(df_unicos)

        # --- ANÁLISE DO 004-ENCOMENDA ---
        st.subheader("📦 Foco: 004-ENCOMENDA")
        df_004 = df_unicos[df_unicos['Tipo Venda'].str.contains('004', na=False)]
        qtd_004 = len(df_004)
        perc_004 = (qtd_004 / total_geral * 100) if total_geral > 0 else 0
        
        col_enc1, col_enc2 = st.columns(2)
        col_enc1.metric("Qtd Pedidos Encomenda", f"{qtd_004}")
        col_enc2.metric("% Sobre o Total", f"{perc_004:.1f}%")

        st.divider()

        # --- ANÁLISE DO 003-ENTREGA (Lógica de 48h vs Agendado) ---
        st.subheader("🚚 Foco: 003-ENTREGA (SLA vs Agendamento)")
        df_003 = df_unicos[df_unicos['Tipo Venda'].str.contains('003', na=False)].copy()
        df_003 = df_003.dropna(subset=['Data Emissão', 'Data Entrega'])
        
        if not df_003.empty:
            # Cálculo de dias úteis
            emissao = df_003['Data Emissão'].values.astype('datetime64[D]')
            entrega = df_003['Data Entrega'].values.astype('datetime64[D]')
            df_003['Dias_Uteis'] = np.busday_count(emissao, entrega)
            
            # Divisão
            no_prazo_48h = len(df_003[df_003['Dias_Uteis'] <= 2])
            agendado_cliente = len(df_003[df_003['Dias_Uteis'] > 2])
            total_003 = len(df_003)
            
            p_48h = (no_prazo_48h / total_003 * 100)
            p_agendado = (agendado_cliente / total_003 * 100)

            col_sla1, col_sla2 = st.columns(2)
            col_sla1.info(f"**Atendimento 48h Úteis**\n\n{no_prazo_48h} pedidos ({p_48h:.1f}%)")
            col_sla2.success(f"**Agendado / Outros Prazos**\n\n{agendado_cliente} pedidos ({p_agendado:.1f}%)")
            
            # Gráfico de Pizza exclusivo para o Comportamento do 003
            st.write("#### Comportamento das Entregas")
            st.plotly_chart({
                "data": [{"values": [no_prazo_48h, agendado_cliente], "labels": ["Até 48h", "Agendado > 48h"], "type": "pie", "hole": .4}],
                "layout": {"height": 300, "margin": dict(l=0, r=0, t=20, b=0)}
            }, use_container_width=True)
        else:
            st.warning("Sem dados de entrega (003) para calcular SLA.")

    else:
        st.info("Vá em Configurações e suba a planilha para processar.")
