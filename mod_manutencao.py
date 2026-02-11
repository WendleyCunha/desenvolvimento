import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime

# =========================================================
# 1. ESTILO E INTERFACE
# =========================================================
def aplicar_estilo():
    st.markdown("""
        <style>
        .metric-card { background: #ffffff; padding: 15px; border-radius: 12px; border-left: 5px solid #002366; 
                       box-shadow: 2px 2px 8px rgba(0,0,0,0.08); text-align: center; }
        .metric-value { font-size: 24px; font-weight: bold; color: #002366; margin: 0; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; margin-right: 5px; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-blue { background: #e0f2fe; color: #0369a1; }
        .card-header { font-size: 14px; font-weight: bold; color: #1e293b; margin-bottom: 5px; border-bottom: 1px solid #f1f5f9; padding-bottom: 5px; }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE TRATAMENTO
# =========================================================
def tratar_dados_oficial(df):
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO', 'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA', 'Data Entrega': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA', 'Valor Venda': 'VALOR',
        'Data Prevista': 'DATA_PREVISTA'
    }
    df = df.rename(columns=mapeamento)
    
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA', 'DATA_PREVISTA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    df['MES_REF'] = df['DATA_EMISSAO'].dt.strftime('%m/%Y') if 'DATA_EMISSAO' in df.columns else "Indefinido"

    if 'Cliente' in df.columns:
        df = df.sort_values(['Cliente', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    
    df['SLA_48H'] = "Pendente"
    if 'DATA_EMISSAO' in df.columns and 'DATA_ENTREGA' in df.columns:
        mask = df['DATA_ENTREGA'].notnull() & df['DATA_EMISSAO'].notnull()
        horas = (df.loc[mask, 'DATA_ENTREGA'] - df.loc[mask, 'DATA_EMISSAO']).dt.total_seconds() / 3600
        df.loc[mask, 'SLA_48H'] = horas.apply(lambda x: "Dentro 48h" if (0 <= x <= 48) else "Fora do Prazo")
        
    return df

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    user_role = st.session_state.get("user_role", "ADM") 
    st.title("🏗️ Performance e Auditoria King Star")

    if 'base_mestra' not in st.session_state: st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state: st.session_state.classificacoes = {}
    if 'motivos_extra' not in st.session_state: st.session_state.motivos_extra = []

    tabs = st.tabs(["📊 Performance", "🔍 Auditoria", "📋 Relatório", "⚙️ Configurações"])
    df = st.session_state.base_mestra

    # --- PERFORMANCE ---
    with tabs[0]:
        if not df.empty:
            df_u = df.drop_duplicates(subset=['Pedido'])
            st.subheader("📊 Visão Geral")
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{len(df_u)}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>Total Clientes</p><p class='metric-value'>{df['Cliente'].nunique()}</p></div>", unsafe_allow_html=True)
            auditoria_universo = len(df_u[df_u['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)])
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>Auditoria (003+004)</p><p class='metric-value'>{auditoria_universo}</p></div>", unsafe_allow_html=True)
            
            st.plotly_chart(px.pie(df_u, names='TIPO_VENDA', title="Mix de Vendas (%)", hole=0.4), use_container_width=True)

            st.divider()
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)].copy()
            total_003 = df_003['Pedido'].nunique()
            if total_003 > 0:
                m1, m2 = st.columns(2)
                d48 = len(df_003[df_003['SLA_48H'] == "Dentro 48h"])
                a48 = len(df_003[df_003['SLA_48H'] == "Fora do Prazo"])
                m1.markdown(f"<div class='metric-card'><p class='metric-label'>003: Dentro 48h</p><p class='metric-value'>{d48}</p></div>", unsafe_allow_html=True)
                m2.markdown(f"<div class='metric-card'><p class='metric-label'>003: Fora do Prazo</p><p class='metric-value'>{a48}</p></div>", unsafe_allow_html=True)
        else: st.info("Suba a base nas configurações.")

    # --- AUDITORIA ---

    with tabs[1]:

        if not df.empty:

            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)

            crit_erro = (df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())

            view = df[crit_venda & crit_erro].copy()

            view = view[~view['Pedido'].astype(str).isin(st.session_state.classificacoes.keys())]



            st.subheader(f"🔍 Pendentes: {len(view)}")

            motivos = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido"] + st.session_state.motivos_extra



            for idx, row in view.head(10).iterrows():

                pid = str(row['Pedido'])

                with st.container():

                    st.markdown(f"<div class='esteira-card'><div class='card-header'>FILIAL: {row['Filial']} | PEDIDO: {pid}</div><b>Cliente:</b> {row['Cliente']} | <b>Vendedor:</b> {row['Vendedor']}</div>", unsafe_allow_html=True)

                    

                    c_col1, c_col2 = st.columns([2,1])

                    with c_col1:

                        sel = st.selectbox("Causa:", motivos, key=f"sel_{pid}_{idx}")

                    

                    data_final = row['DATA_PREVISTA']

                    

                    # Se não tem Data Prevista, abre o calendário

                    if sel != "Não Analisado" and pd.isna(data_final):

                        with c_col2:

                            data_final = st.date_input("Inserir Data Real:", key=f"date_{pid}_{idx}")

                            data_final = pd.to_datetime(data_final)



                    if sel != "Não Analisado" and pd.notnull(data_final):

                        if st.button(f"Confirmar {pid}", key=f"btn_{pid}"):

                            # CÁLCULO REAL DO SLA

                            dif_horas = (data_final - row['DATA_EMISSAO']).total_seconds() / 3600

                            novo_sla = "Dentro 48h" if (0 <= dif_horas <= 48) else "Fora do Prazo"

                            

                            # Atualiza Base Mestra

                            st.session_state.base_mestra.loc[st.session_state.base_mestra['Pedido'] == row['Pedido'], 'SLA_48H'] = novo_sla

                            st.session_state.base_mestra.loc[st.session_state.base_mestra['Pedido'] == row['Pedido'], 'DATA_ENTREGA'] = data_final

                            

                            # Grava Relatório

                            st.session_state.classificacoes[pid] = {

                                'Status_Auditoria': sel, 'SLA_Final': novo_sla, 

                                'Data_Inserida': data_final, 'Filial': row['Filial']

                            }

                            st.rerun()

        else: st.info("Aguardando base.")

    # --- RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index().rename(columns={'index': 'Pedido'})
            st.dataframe(resumo, use_container_width=True)
        else: st.info("Nenhum pedido auditado.")

    # --- CONFIGURAÇÕES ---
    with tabs[3]:
        st.subheader("📝 Motivos Customizados")
        n_motivo = st.text_input("Novo motivo:")
        if st.button("Adicionar"):
            if n_motivo: st.session_state.motivos_extra.append(n_motivo); st.rerun()
        
        st.divider()
        arq = st.file_uploader("Upload Base", type=['csv', 'xlsx'])
        if arq:
            df_raw = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
            st.session_state.base_mestra = tratar_dados_oficial(df_raw)
            st.rerun()
        
        if st.button("🔥 RESETAR TUDO"):
            st.session_state.base_mestra = pd.DataFrame(); st.session_state.classificacoes = {}; st.rerun()

if __name__ == "__main__":
    main()
