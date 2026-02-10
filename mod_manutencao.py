import streamlit as st
import pandas as pd
import numpy as np

def tratar_dados(df):
    # 1. Ajuste de Encoding e Nomes de Colunas
    df.columns = [
        col.encode('latin1').decode('utf-8', 'ignore') if isinstance(col, str) else col 
        for col in df.columns
    ]
    mapeamento = {
        'Dt Emissão': 'Data Emissão', 'Dt EmissÃ£o': 'Data Emissão',
        'OrÃ§amento': 'Orçamento', 'OrÂ§amento': 'Orçamento',
        'Data Ent': 'Data Entrega', 'Tipo Venda': 'Tipo Venda'
    }
    df.rename(columns=mapeamento, inplace=True)

    # 2. Lógica de ID Único (Prioriza Orçamento para 002-RETIRA)
    def definir_id(row):
        tipo = str(row.get('Tipo Venda', ''))
        id_ped = str(row.get('Pedido', '')).strip()
        id_orc = str(row.get('Orçamento', '')).strip()
        if "002" in tipo:
            return id_orc if id_orc not in ['nan', '', 'None'] else id_ped
        return id_ped if id_ped not in ['nan', '', 'None'] else id_orc

    df['ID_Unico'] = df.apply(definir_id, axis=1)

    # 3. Conversão de Datas
    for col in ['Data Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # 4. Tratamento Financeiro
    for col in ['Valor Venda', 'Custo']:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    df['Margem R$'] = df['Valor Venda'] - df['Custo']
    return df

def calcular_sla_detalhado(df_unicos):
    # Filtra apenas 003-ENTREGA com datas válidas
    df_e = df_unicos[
        (df_unicos['Tipo Venda'].str.contains('003', na=False)) & 
        (df_unicos['Data Emissão'].notna()) & 
        (df_unicos['Data Entrega'].notna())
    ].copy()
    
    if df_e.empty: return 0, 0, 0
    
    # Cálculo de Dias Úteis (Sáb/Dom fora)
    emissao = df_e['Data Emissão'].values.astype('datetime64[D]')
    entrega = df_e['Data Entrega'].values.astype('datetime64[D]')
    df_e['Dias_Uteis'] = np.busday_count(emissao, entrega)
    
    no_prazo = len(df_e[df_e['Dias_Uteis'] <= 2])
    total = len(df_e)
    percentual = (no_prazo / total * 100) if total > 0 else 0
    return no_prazo, total, percentual

def exibir_manutencao(user_role):
    st.title("🏗️ Gestão de Manutenção & Vendas")
    
    tab_dash, tab_config = st.tabs(["📊 Dashboard 360", "⚙️ Configurações"])

    with tab_config:
        arquivo = st.file_uploader("Subir base de vendas", type=['xlsx', 'csv', 'xls'])
        if arquivo:
            try:
                engine = 'xlrd' if arquivo.name.endswith('.xls') else 'openpyxl'
                df_raw = pd.read_excel(arquivo, engine=engine)
                st.session_state['dados_vendas'] = tratar_dados(df_raw)
                st.success("Dados processados!")
                st.rerun()
            except Exception as e: st.error(f"Erro: {e}")
        
        if st.button("LIMPAR DADOS"):
            if 'dados_vendas' in st.session_state: del st.session_state['dados_vendas']
            st.rerun()

    with tab_dash:
        if 'dados_vendas' in st.session_state:
            df = st.session_state['dados_vendas']
            df_unicos = df.drop_duplicates(subset=['ID_Unico']).copy()
            
            # --- DESTAQUE PRINCIPAL: SLA DE AGENDAMENTO ---
            qtd_p, total_e, perc_sla = calcular_sla_detalhado(df_unicos)
            
            st.error(f"### 🚨 ALERTA DE LOGÍSTICA: {perc_sla:.1f}% de Eficiência")
            col_met1, col_met2, col_met3 = st.columns(3)
            with col_met1:
                st.metric("Pedidos Agendados (48h)", f"{qtd_p}", delta=f"{perc_sla:.1f}%", delta_color="inverse")
            with col_met2:
                st.metric("Total de Entregas (003)", f"{total_e}")
            with col_met3:
                atrasados = total_e - qtd_p
                st.metric("Fora do Prazo Ideal", f"{atrasados}", "Crítico", delta_color="normal")
            
            st.progress(perc_sla / 100)
            st.markdown(f"**Análise:** Apenas **{perc_sla:.1f}%** das entregas nasceram com agendamento de até 2 dias úteis.")
            
            st.divider()

            # --- DEMAIS KPIs ---
            c1, c2, c3, c4 = st.columns(4)
            venda_t = df['Valor Venda'].sum()
            c1.metric("Vendas Totais", f"R$ {venda_t:,.2f}")
            c2.metric("Margem Bruta", f"R$ {df['Margem R$'].sum():,.2f}")
            c3.metric("Qtd Pedidos (ID)", f"{len(df_unicos)}")
            c4.metric("Ticket Médio", f"R$ {(venda_t/len(df_unicos)):,.2f}")

            st.divider()

            # --- DISTRIBUIÇÃO E PIZZA ---
            col_p1, col_p2 = st.columns([1, 1])
            with col_p1:
                st.subheader("🍕 Mix de Venda (Pedidos Únicos)")
                cont_tipo = df_unicos['Tipo Venda'].value_counts()
                st.plotly_chart({
                    "data": [{"values": cont_tipo.values, "labels": cont_tipo.index, "type": "pie", "hole": .4}],
                    "layout": {"height": 300, "margin": dict(l=0, r=0, t=0, b=0)}
                }, use_container_width=True)
            
            with col_p2:
                st.subheader("📍 Desempenho por Filial")
                venda_filial = df.groupby('Filial')['Valor Venda'].sum().sort_values()
                st.bar_chart(venda_filial, horizontal=True)

        else:
            st.info("Aguardando upload da planilha nas Configurações.")
