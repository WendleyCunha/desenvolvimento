import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime
import os

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
# 2. MOTOR DE TRATAMENTO (ATUALIZADO PARA CRUZAMENTO)
# =========================================================
def tratar_dados_oficial(df, df_agendados=None):
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO', 'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA', 'Data Entrega': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA', 'Valor Venda': 'VALOR',
        'Data Prevista': 'DATA_PREVISTA'
    }
    df = df.rename(columns=mapeamento)

    # TRATAMENTO DO RELATÓRIO 2 (AGENDADOS)
    if df_agendados is not None:
        df_agendados.columns = [str(col).strip() for col in df_agendados.columns]
        # Limpa aspas e lixo do Pedido e Data
        df_agendados['Ped. Venda'] = df_agendados['Ped. Venda'].astype(str).str.replace("'", "").str.strip()
        
        # PROCV: Traz a Previsão Ent. para a base principal
        df['Pedido'] = df['Pedido'].astype(str).str.strip()
        df = pd.merge(df, df_agendados[['Ped. Venda', 'Previsão Ent.']], left_on='Pedido', right_on='Ped. Venda', how='left')
        
        # Se Data Entrega for vazia (/ /), usa a Previsão do Agendado
        df['DATA_ENTREGA'] = df['DATA_ENTREGA'].replace('/ /', np.nan)
        df['DATA_ENTREGA'] = df['DATA_ENTREGA'].fillna(df['Previsão Ent.'])
        df.drop(columns=['Ped. Venda', 'Previsão Ent.'], inplace=True, errors='ignore')
    
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA', 'DATA_PREVISTA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace(['/ /', 'nan', 'NaT'], np.nan), errors='coerce')
    
    df['MES_REF'] = df['DATA_EMISSAO'].dt.strftime('%m/%Y') if 'DATA_EMISSAO' in df.columns else "Indefinido"

    if 'Cliente' in df.columns:
        # Limpa o /99 do cliente para a lógica de Seq_Pedido funcionar
        df['Cliente'] = df['Cliente'].astype(str).str.split('/').str[0].str.strip()
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
    st.title("🏗️ Performance e Auditoria King Star")

    if 'base_mestra' not in st.session_state: st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state: st.session_state.classificacoes = {}
    if 'motivos_extra' not in st.session_state: st.session_state.motivos_extra = []

    tabs = st.tabs(["📊 Performance", "🔍 Auditoria", "📋 Relatório", "⚙️ Configurações"])
    df = st.session_state.base_mestra

    # --- ABA 1: PERFORMANCE ---
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
        else: st.info("Suba a base nas configurações.")

    # --- ABA 2: AUDITORIA ---
    with tabs[1]:
        if not df.empty:
            if os.path.exists('historico_auditoria.csv'):
                try:
                    hist_df = pd.read_csv('historico_auditoria.csv')
                    for _, r in hist_df.iterrows():
                        pid_str = str(r['Pedido'])
                        if pid_str not in st.session_state.classificacoes:
                            st.session_state.classificacoes[pid_str] = r.to_dict()
                except: pass

            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)
            crit_erro = (df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())
            view = df[crit_venda & crit_erro].copy()
            view = view[~view['Pedido'].astype(str).isin(st.session_state.classificacoes.keys())]

            st.subheader(f"🔍 Esteira de Auditoria: {len(view)} pendentes")
            motivos = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido"] + st.session_state.motivos_extra

            for idx, row in view.head(10).iterrows():
                pid = str(row['Pedido'])
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <div class='card-header'>FILIAL: {row['Filial']} | PEDIDO: {pid}</div>
                            <b>Vendedor:</b> {row['Vendedor']} | <b>Cliente:</b> {row['Cliente']}<br>
                            <span class='badge badge-red'>Seq: {row['Seq_Pedido']}</span>
                            <span class='badge badge-blue'>Entrega: {row['DATA_ENTREGA'] if pd.notnull(row['DATA_ENTREGA']) else 'AGUARDANDO AGENDAMENTO'}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    c_col1, c_col2 = st.columns([2,1])
                    with c_col1: sel = st.selectbox("Causa:", motivos, key=f"sel_{pid}")
                    data_final = row['DATA_PREVISTA']
                    if sel != "Não Analisado" and pd.isna(data_final):
                        with c_col2: data_final = pd.to_datetime(st.date_input("Data Real:", key=f"date_{pid}"))

                    if sel != "Não Analisado" and pd.notnull(data_final):
                        if st.button(f"Confirmar {pid}", key=f"btn_{pid}"):
                            dif_horas = (pd.to_datetime(data_final) - pd.to_datetime(row['DATA_EMISSAO'])).total_seconds() / 3600
                            novo_sla = "Dentro 48h" if (0 <= dif_horas <= 48) else "Fora do Prazo"
                            st.session_state.base_mestra.loc[st.session_state.base_mestra['Pedido'] == row['Pedido'], ['SLA_48H', 'DATA_ENTREGA']] = [novo_sla, data_final]
                            registro = {'Pedido': pid, 'Status_Auditoria': sel, 'SLA_Final': novo_sla, 'Data_Inserida': pd.to_datetime(data_final).strftime('%Y-%m-%d'), 'Filial': row['Filial'], 'Vendedor': row['Vendedor']}
                            pd.DataFrame([registro]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                            st.session_state.classificacoes[pid] = registro
                            st.rerun()
        else: st.info("Aguardando base de dados.")

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index(drop=True)
            st.subheader("📋 Histórico de Auditoria")
            st.dataframe(resumo, use_container_width=True)
            st.download_button("📥 Baixar Planilha", resumo.to_csv(index=False).encode('utf-8'), "auditoria_final.csv")
        else: st.info("Nenhum pedido auditado.")

    # --- ABA 4: CONFIGURAÇÕES ---
    with tabs[3]:
        st.subheader("⚙️ Configurações de Dados")
        col1, col2 = st.columns(2)
        with col1: arq_v = st.file_uploader("1. Base Venda (xlsx/csv)", type=['csv', 'xlsx'])
        with col2: arq_a = st.file_uploader("2. Relatório Agendados (opcional)", type=['csv', 'xlsx'])
        
        if st.button("🚀 PROCESSAR BASES"):
            if arq_v:
                df_v = pd.read_csv(arq_v, encoding='latin1', sep=None, engine='python') if arq_v.name.endswith('.csv') else pd.read_excel(arq_v)
                df_a = None
                if arq_a:
                    df_a = pd.read_csv(arq_a, encoding='latin1', sep=None, engine='python') if arq_a.name.endswith('.csv') else pd.read_excel(arq_a)
                st.session_state.base_mestra = tratar_dados_oficial(df_v, df_a)
                st.success("Dados cruzados com sucesso!")
                st.rerun()

        st.divider()
        if st.button("🔥 RESETAR SISTEMA"):
            st.session_state.base_mestra = pd.DataFrame()
            st.session_state.classificacoes = {}
            st.rerun()

if __name__ == "__main__":
    main()
