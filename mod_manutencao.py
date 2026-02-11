import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados_expert(df):
    # Ajuste de Encoding e nomes (conforme sua imagem do Protheus)
    df.columns = [str(col).strip() for col in df.columns]
    
    # Mapeamento específico da sua imagem
    mapeamento = {
        'Dt EmissÃ£o': 'Dt_Emissao',
        'Data Ent': 'Dt_Entrega',
        'Tipo Venda': 'Tipo_Venda',
        'Cliente': 'ID_Cliente'
    }
    df.rename(columns=mapeamento, inplace=True)

    # Conversão de datas
    for col in ['Dt_Emissao', 'Dt_Entrega', 'Data Prev']:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    
    return df

def processar_analise_perita(df):
    # 3. Garantir Pedido Único para análise de fluxo (mantendo o de maior valor se houver duplicata)
    df_pedidos = df.sort_values('Valor Venda', ascending=False).drop_duplicates('Pedido').copy()
    
    # --- LOGICA 2: Verificação do SLA 48h (Dias Úteis) ---
    def verificar_sla(row):
        if '003' in str(row['Tipo_Venda']):
            if pd.notna(row['Dt_Emissao']) and pd.notna(row['Dt_Entrega']):
                # Calcula dias úteis entre emissão e entrega
                dias_uteis = np.busday_count(
                    row['Dt_Emissao'].values.astype('datetime64[D]'),
                    row['Dt_Entrega'].values.astype('datetime64[D]')
                )
                if dias_uteis > 2:
                    return "SLA Estourado (>48h)"
                return "SLA OK"
            else:
                return "Pendente de Entrega (Atenção)"
        return "Fluxo Encomenda/Retira"

    df_pedidos['Analise_SLA'] = df_pedidos.apply(verificar_sla, axis=1)

    # --- LOGICA 4: O Pulo do Gato (Cliente Recorrente com Novo Pedido) ---
    # Identifica se o cliente já teve um pedido anterior na mesma base
    df_pedidos = df_pedidos.sort_values(['ID_Cliente', 'Dt_Emissao'])
    df_pedidos['Pedido_Sequencial'] = df_pedidos.groupby('ID_Cliente').cumcount() + 1
    
    # --- ABA DE APURAÇÃO DE CASOS ---
    # Casos Críticos: SLA estourado OU Pedidos subsequentes do mesmo cliente (potencial re-envio)
    condicao_apuracao = (
        (df_pedidos['Analise_SLA'] == "SLA Estourado (>48h)") | 
        (df_pedidos['Pedido_Sequencial'] > 1) |
        (df_pedidos['Tipo_Venda'].str.contains('004')) # Encomendas são sempre pontos de atenção
    )
    
    df_apuracao = df_pedidos[condicao_apuracao].copy()
    
    return df_pedidos, df_apuracao

# --- Interface Streamlit ---
st.title("🔍 Sistema de Auditoria de Pedidos - Especialista")

# (Aqui entraria sua lógica de upload já existente...)
if 'dados_vendas' in st.session_state:
    df = st.session_state['dados_vendas']
    df_processado, df_apuracao = processar_analise_perita(df)

    tab1, tab2 = st.tabs(["📊 Visão Geral", "🚨 ABA DE APURAÇÃO DE CASOS"])

    with tab1:
        st.subheader("Performance de Vendas")
        # Mostrar o Pareto de Tipos de Venda
        contagem_tipo = df_processado['Tipo_Venda'].value_counts()
        st.bar_chart(contagem_tipo)

    with tab2:
        st.warning("Estes pedidos exigiram 'mão humana' ou falharam no fluxo automático.")
        
        # Filtro para o CEO ver o que é re-trabalho
        re_trabalho = df_apuracao[df_apuracao['Pedido_Sequencial'] > 1]
        st.write(f"Detectamos **{len(re_trabalho)}** pedidos que podem ser re-envios ou correções (Mesmo Cliente, Novo Pedido).")
        
        st.dataframe(df_apuracao[[
            'Pedido', 'ID_Cliente', 'Tipo_Venda', 'Dt_Emissao', 
            'Dt_Entrega', 'Analise_SLA', 'Pedido_Sequencial'
        ]])
