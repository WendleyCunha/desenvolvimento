import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

def aplicar_estilo():
    st.markdown("""
        <style>
        .metric-card { background: #f8fafc; padding: 15px; border-radius: 10px; border-top: 4px solid #002366; text-align: center; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; margin-right: 5px; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-green { background: #dcfce7; color: #166534; }
        .badge-blue { background: #e0f2fe; color: #0369a1; }
        </style>
    """, unsafe_allow_html=True)

def tratar_dados_oficial(df):
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO', 'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA', 'Data Entrega': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA', 'Valor Venda': 'VALOR'
    }
    df = df.rename(columns=mapeamento)
    
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # Criar coluna de Mês para as configurações
    df['MES_REF'] = df['DATA_EMISSAO'].dt.strftime('%m/%Y') if 'DATA_EMISSAO' in df.columns else "Sem Data"

    # Sequência de Pedidos por Cliente
    if 'Cliente' in df.columns:
        df = df.sort_values(['Cliente', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    
    # SLA 48h Original
    df['SLA_48H'] = "Pendente"
    if 'DATA_EMISSAO' in df.columns and 'DATA_ENTREGA' in df.columns:
        mask = df['DATA_ENTREGA'].notnull() & df['DATA_EMISSAO'].notnull()
        horas = (df.loc[mask, 'DATA_ENTREGA'] - df.loc[mask, 'DATA_EMISSAO']).dt.total_seconds() / 3600
        df.loc[mask, 'SLA_48H'] = horas.apply(lambda x: "Dentro 48h" if (0 <= x <= 48) else "Fora do Prazo")
        
    return df

def main():
    aplicar_estilo()
    user_role = st.session_state.get("user_role", "ADM") 
    st.title("🏗️ Manutenção e Eficiência King Star")

    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    abas = ["📊 Performance", "🔍 Auditoria", "📋 Relatório"]
    if user_role == "ADM": abas.append("⚙️ Configurações")
    tabs = st.tabs(abas)

    # --- ABA 1: PERFORMANCE ---
    with tabs[0]:
        df = st.session_state.base_mestra
        if not df.empty:
            # Universo apenas 003
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)].copy()
            
            c1, c2, c3 = st.columns(3)
            
            # Pedidos 003 Totais
            total_003 = len(df_003)
            # Pedidos com Data de Entrega (Coluna F preenchida)
            com_entrega = len(df_003[df_003['DATA_ENTREGA'].notnull()])
            # Pedidos dentro de 48h (SLA Original)
            dentro_48h = len(df_003[df_003['SLA_48H'] == "Dentro 48h"])
            
            c1.markdown(f"<div class='metric-card'>NASCERAM 003 (TOTAL)<h3>{total_003}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'>COM DATA ENTREGA (F)<h3>{com_entrega}</h3></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'>SLA 48H ORIGINAL<h3>{dentro_48h}</h3></div>", unsafe_allow_html=True)

            # Gráfico Pizza - Visibilidade da Coluna F
            status_f = ["Com Data" if pd.notnull(x) else "Sem Data" for x in df_003['DATA_ENTREGA']]
            df_003['Status_F'] = status_f
            
            st.plotly_chart(px.pie(df_003, names='Status_F', title="Conformidade de Preenchimento (Coluna F)", 
                                  hole=0.4, color_discrete_sequence=['#166534', '#ef4444']), use_container_width=True)
        else:
            st.info("Suba a base nas configurações.")

    # --- ABA 2: AUDITORIA ---
    with tabs[1]:
        df = st.session_state.base_mestra
        if not df.empty:
            # Filtro 003 com erro (Seq > 1 ou Sem Data F)
            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)
            crit_erro = (df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())
            view = df[crit_venda & crit_erro].copy()
            
            # Remove quem já foi auditado
            view = view[~view['Pedido'].astype(str).isin(st.session_state.classificacoes.keys())]

            st.subheader(f"Pedidos para Auditoria: {len(view)}")
            
            for idx, row in view.head(15).iterrows():
                pid = str(row['Pedido'])
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <b>Filial: {row['Filial']} | Pedido: {pid}</b><br>
                            Cliente: {row['Cliente']} | Seq: {row['Seq_Pedido']}<br>
                            Status Original: <span class='badge badge-red'>{'SEM DATA ENTREGA' if pd.isna(row['DATA_ENTREGA']) else 'RE-TRABALHO'}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    sel = st.selectbox("Classificar causa:", opcoes, key=f"audit_{pid}_{idx}")
                    
                    if sel != "Não Analisado":
                        # Se for "Pedido correto", simulamos que ele está perfeito no relatório
                        final_status = "Pedido Perfeito" if sel == "Pedido correto" else sel
                        st.session_state.classificacoes[pid] = {
                            'Classificação': final_status,
                            'Filial': row['Filial'],
                            'Vendedor': row['Vendedor'],
                            'Cliente': row['Cliente'],
                            'Data_F_Original': row['DATA_ENTREGA']
                        }
                        st.rerun()

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            res_df = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
            res_df.rename(columns={'index': 'Pedido'}, inplace=True)
            st.subheader("📋 Resultados da Auditoria")
            st.dataframe(res_df, use_container_width=True)
            st.download_button("Baixar Relatório", res_df.to_csv(index=False).encode('utf-8'), "auditoria_final.csv")
        else:
            st.info("Nenhum pedido auditado.")

    # --- ABA 4: CONFIGURAÇÕES (ADM) ---
    if user_role == "ADM":
        with tabs[3]:
            st.header("⚙️ Área Administrativa")
            up = st.file_uploader("Subir Nova Base", type=['csv', 'xlsx'])
            if up:
                df_raw = pd.read_csv(up, encoding='latin1', sep=None, engine='python') if up.name.endswith('.csv') else pd.read_excel(up)
                st.session_state.base_mestra = tratar_dados_oficial(df_raw)
                st.success("Dados carregados!")
                st.rerun()

            if not st.session_state.base_mestra.empty:
                st.divider()
                meses = st.session_state.base_mestra['MES_REF'].unique()
                m_sel = st.selectbox("Limpar mês:", meses)
                if st.button("Limpar Dados do Mês"):
                    st.session_state.base_mestra = st.session_state.base_mestra[st.session_state.base_mestra['MES_REF'] != m_sel]
                    st.rerun()

            if st.button("🔥 RESETAR TUDO"):
                st.session_state.base_mestra = pd.DataFrame()
                st.session_state.classificacoes = {}
                st.rerun()

if __name__ == "__main__":
    main()
