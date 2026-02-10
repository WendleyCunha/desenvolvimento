import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    """
    Limpa nomes de colunas e aplica a lógica de ID Único (Pedido vs Orçamento).
    """
    # 1. Corrigir nomes de colunas (Encoding)
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]

    # 2. Padronização de nomes
    mapeamento = {
        'Dt Emissão': 'Data Emissão',
        'Dt EmissÃ£o': 'Data Emissão',
        'OrÃ§amento': 'Orçamento',
        'OrÂ§amento': 'Orçamento',
        'Data Ent': 'Data Entrega',
        'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 3. LÓGICA DO AJUSTE: Identificador Único Híbrido
    # Se for 002 e Pedido estiver vazio, usa Orçamento.
    def definir_id(row):
        tipo = str(row.get('Tipo Venda', ''))
        id_pedido = str(row.get('Pedido', ''))
        id_orcamento = str(row.get('Orçamento', ''))
        
        if "002" in tipo:
            # Para Retira, o Orçamento é o nosso ID principal
            return id_orcamento if id_orcamento not in ['nan', '', 'None'] else id_pedido
        else:
            # Para Entrega e Encomenda, usamos o Pedido
            return id_pedido if id_pedido not in ['nan', '', 'None'] else id_orcamento

    df['ID_Unico'] = df.apply(definir_id, axis=1)

    # 4. Conversão de Datas e Números
    for col in ['Data Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    for col in ['Valor Venda', 'Custo']:
        if col in df.columns:
            # Remove R$ e limpa formatação brasileira se necessário
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace('R$', '').str.replace('.', '').str.replace(',', '.').strip()
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    if 'Valor Venda' in df.columns and 'Custo' in df.columns:
        df['Margem R$'] = df['Valor Venda'] - df['Custo']
        
    return df

def calcular_sla_entregas(df_unicos):
    if 'Tipo Venda' not in df_unicos.columns or 'Data Entrega' not in df_unicos.columns:
        return 0, 0
    
    df_entrega = df_unicos[
        (df_unicos['Tipo Venda'].str.contains('003', na=False)) & 
        (df_unicos['Data Emissão'].notna()) & 
        (df_unicos['Data Entrega'].notna())
    ].copy()

    if df_entrega.empty: return 0, 0

    emissao = df_entrega['Data Emissão'].values.astype('datetime64[D]')
    entrega = df_entrega['Data Entrega'].values.astype('datetime64[D]')
    df_entrega['Dias_Uteis'] = np.busday_count(emissao, entrega)
    
    qtd_prazo = len(df_entrega[df_entrega['Dias_Uteis'] <= 2])
    return qtd_prazo, len(df_entrega)

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    
    tab_dash, tab_config = st.tabs(["📊 Dashboard 360", "⚙️ Configurações"])

    with tab_config:
        arquivo = st.file_uploader("Subir planilha", type=['xlsx', 'csv', 'xls'])
        if arquivo:
            try:
                engine = 'xlrd' if arquivo.name.endswith('.xls') else 'openpyxl'
                df_raw = pd.read_excel(arquivo, engine=engine)
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("Dados processados com a nova lógica de ID!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
        
        if st.button("RESETAR SISTEMA"):
            if 'dados_vendas' in st.session_state: del st.session_state['dados_vendas']
            st.rerun()

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            
            # Base de IDs Únicos (Híbrida: Pedido ou Orçamento)
            df_unicos = df.drop_duplicates(subset=['ID_Unico']).copy()
            qtd_total_pedidos = len(df_unicos)

            # KPIs
            venda_total = df['Valor Venda'].sum()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Vendas Totais", f"R$ {venda_total:,.2f}")
            c2.metric("Margem Bruta", f"R$ {df['Margem R$'].sum():,.2f}")
            c3.metric("Qtd Pedidos (IDs Reais)", f"{qtd_total_pedidos}")
            c4.metric("Ticket Médio", f"R$ {(venda_total/qtd_total_pedidos):,.2f}" if qtd_total_pedidos > 0 else "0")

            st.divider()

            # SLA 48h
            st.subheader("🚚 Eficiência de Logística (SLA 48h Úteis)")
            qtd_p, total_e = calcular_sla_entregas(df_unicos)
            perc_sla = (qtd_p / total_e * 100) if total_e > 0 else 0
            st.metric("Entregas em até 48h Úteis", f"{qtd_p}", f"{perc_sla:.1f}% das entregas")
            st.progress(perc_sla / 100)

            st.divider()

            # Pizza com a nova contagem
            st.subheader("🍕 Distribuição por Tipo de Venda")
            contagem_tipo = df_unicos['Tipo Venda'].value_counts()
            
            col_p1, col_p2 = st.columns([1, 2])
            with col_p1:
                for nome in ["002-RETIRA", "003-ENTREGA", "004-ENCOMENDA"]:
                    qtd = contagem_tipo.get(nome, 0)
                    p = (qtd / qtd_total_pedidos * 100) if qtd_total_pedidos > 0 else 0
                    st.write(f"**{nome}:** {p:.2f}% ({qtd})")
            
            with col_p2:
                st.plotly_chart({
                    "data": [{"values": contagem_tipo.values, "labels": contagem_tipo.index, "type": "pie", "hole": .4}],
                    "layout": {"height": 300, "margin": dict(l=0, r=0, t=0, b=0)}
                }, use_container_width=True)
        else:
            st.info("Suba a planilha nas Configurações.")
