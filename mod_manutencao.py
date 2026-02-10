import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    """
    Limpa nomes de colunas e prepara a base de dados com inteligência de datas.
    """
    # 1. Corrigir nomes de colunas (Encoding ANSI/UTF-8)
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]

    # 2. Padronização de nomes (Conforme as imagens enviadas)
    mapeamento = {
        'Dt Emissão': 'Data Emissão',
        'Dt EmissÃ£o': 'Data Emissão',
        'Data Ent': 'Data Entrega',
        'Valor Venda': 'Valor Venda',
        'Custo': 'Custo',
        'Pedido': 'Pedido',
        'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 3. Conversão de Datas
    for col in ['Data Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # 4. Tratamento Numérico
    for col in ['Valor Venda', 'Custo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 5. Cálculo de Margem
    if 'Valor Venda' in df.columns and 'Custo' in df.columns:
        df['Margem R$'] = df['Valor Venda'] - df['Custo']
        
    return df

def calcular_sla_entregas(df_unicos):
    """
    Calcula quantos pedidos de entrega estão dentro do prazo de 2 dias úteis.
    """
    if 'Tipo Venda' not in df_unicos.columns or 'Data Entrega' not in df_unicos.columns:
        return 0, 0

    # Filtrar apenas o tipo 003-ENTREGA e que possuam ambas as datas
    df_entrega = df_unicos[
        (df_unicos['Tipo Venda'] == '003-ENTREGA') & 
        (df_unicos['Data Emissão'].notna()) & 
        (df_unicos['Data Entrega'].notna())
    ].copy()

    if df_entrega.empty:
        return 0, 0

    # Calcular dias úteis entre emissão e entrega (Ignora Sab/Dom)
    # np.busday_count espera objetos datetime64[D]
    emissao = df_entrega['Data Emissão'].values.astype('datetime64[D]')
    entrega = df_entrega['Data Entrega'].values.astype('datetime64[D]')
    
    # Calculamos a diferença. busday_count(inicio, fim)
    df_entrega['Dias_Uteis'] = np.busday_count(emissao, entrega)

    # Regra: Nasceu com 48h (até 2 dias úteis)
    dentro_prazo = df_entrega[df_entrega['Dias_Uteis'] <= 2]
    
    return len(dentro_prazo), len(df_entrega)

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    st.markdown("---")

    tab_dash, tab_config = st.tabs(["📊 Dashboard 360", "⚙️ Configurações"])

    with tab_config:
        st.subheader("Gerenciamento de Dados")
        arquivo = st.file_uploader("Subir planilha", type=['xlsx', 'csv', 'xls'])
        
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, sep=None, engine='python', encoding='latin1')
                else:
                    engine = 'xlrd' if arquivo.name.endswith('.xls') else 'openpyxl'
                    df_raw = pd.read_excel(arquivo, engine=engine)
                
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("Dados atualizados!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

        if st.button("RESETAR SISTEMA", type="primary"):
            if 'dados_vendas' in st.session_state:
                del st.session_state['dados_vendas']
            st.rerun()

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # Base de Pedidos Únicos para Contagens e Porcentagens
            df_pedidos_unicos = df.drop_duplicates(subset=['Pedido']).copy()
            qtd_pedidos = len(df_pedidos_unicos)

            # KPIs Superiores
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Vendas Totais", f"R$ {df['Valor Venda'].sum():,.2f}")
            c2.metric("Margem Bruta", f"R$ {df['Margem R$'].sum():,.2f}")
            c3.metric("Qtd Pedidos (Únicos)", f"{qtd_pedidos}")
            c4.metric("Ticket Médio", f"R$ {(df['Valor Venda'].sum()/qtd_pedidos):,.2f}" if qtd_pedidos > 0 else "0")
                
            st.divider()

            # --- SEÇÃO 1: SLA DE ENTREGAS (48H ÚTEIS) ---
            st.subheader("🚚 Eficiência de Logística (SLA 48h Úteis)")
            qtd_prazo, total_e = calcular_sla_entregas(df_pedidos_unicos)
            
            col_s1, col_s2 = st.columns(2)
            perc_sla = (qtd_prazo / total_e * 100) if total_e > 0 else 0
            
            col_s1.metric("Entregas em até 48h Úteis", f"{qtd_prazo}", f"{perc_sla:.1f}% do total entrega")
            col_s2.progress(perc_sla / 100)
            st.caption(f"Baseado em {total_e} pedidos totais do tipo '003-ENTREGA'. Sábados, domingos e feriados não contabilizados.")

            st.divider()
            
            # --- SEÇÃO 2: TIPO DE VENDA (PIZZA) ---
            st.subheader("🍕 Distribuição por Tipo de Venda")
            if 'Tipo Venda' in df_pedidos_unicos.columns:
                contagem_tipo = df_pedidos_unicos['Tipo Venda'].value_counts()
                
                col_p1, col_p2 = st.columns([1, 2])
                
                with col_p1:
                    # Exibição em métricas conforme solicitado
                    for nome in ["002-RETIRA", "003-ENTREGA", "004-ENCOMENDA"]:
                        valor = contagem_tipo.get(nome, 0)
                        perc = (valor / qtd_pedidos * 100) if qtd_pedidos > 0 else 0
                        st.write(f"**{nome}:** {perc:.2f}% ({valor} pedidos)")
                
                with col_p2:
                    # Gráfico de Pizza Nativo
                    st.plotly_chart({
                        "data": [{"values": contagem_tipo.values, "labels": contagem_tipo.index, "type": "pie", "hole": .4}],
                        "layout": {"margin": {"t": 0, "b": 0, "l": 0, "r": 0}, "height": 300}
                    }, use_container_width=True)

        else:
            st.info("Aguardando upload de dados.")
