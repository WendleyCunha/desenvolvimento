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
# 2. MOTOR DE TRATAMENTO E AUDITORIA AUTOMÁTICA
# =========================================================
def tratar_e_auditar_automatico(df_venda, df_agendados=None):
    if df_venda.empty: return df_venda
    
    # 1. Limpeza Inicial
    df_venda.columns = [str(col).strip() for col in df_venda.columns]
    mapeamento = {'Dt EmissÃ£o': 'DATA_EMISSAO', 'Dt Emissão': 'DATA_EMISSAO', 'Data Ent': 'DATA_ENTREGA', 
                  'Data Entrega': 'DATA_ENTREGA', 'Tipo Venda': 'TIPO_VENDA', 'Data Prevista': 'DATA_PREVISTA'}
    df_venda = df_venda.rename(columns=mapeamento)
    
    # Tratamento de datas e Cliente
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA', 'DATA_PREVISTA']:
        if col in df_venda.columns:
            df_venda[col] = pd.to_datetime(df_venda[col].astype(str).replace(['/ /', 'nan'], np.nan), errors='coerce')
    
    if 'Cliente' in df_venda.columns:
        df_venda['Cliente'] = df_venda['Cliente'].astype(str).str.split('/').str[0].str.strip()
        df_venda = df_venda.sort_values(['Cliente', 'DATA_EMISSAO'])
        df_venda['Seq_Pedido'] = df_venda.groupby('Cliente').cumcount() + 1

    # 2. Lógica de PROCV e Auditoria Automática
    if df_agendados is not None:
        df_agendados.columns = [str(col).strip() for col in df_agendados.columns]
        df_agendados['Ped. Venda'] = df_agendados['Ped. Venda'].astype(str).str.replace("'", "").str.strip()
        df_agendados['Previsão Ent.'] = pd.to_datetime(df_agendados['Previsão Ent.'], errors='coerce')
        
        # Filtramos o que já foi auditado manualmente para não sobrescrever
        pedidos_auditados = list(st.session_state.classificacoes.keys())
        
        # Identificamos quem precisa de data (Tipo 003 e Data Entrega Vazia)
        mask_vazio = (df_venda['TIPO_VENDA'].astype(str).str.contains('003')) & \
                     (df_venda['DATA_ENTREGA'].isna()) & \
                     (~df_venda['Pedido'].astype(str).isin(pedidos_auditados))
        
        # Fazemos o Merge (PROCV)
        df_venda['Pedido_Str'] = df_venda['Pedido'].astype(str).str.strip()
        agend_clean = df_agendados.drop_duplicates(subset=['Ped. Venda'])
        
        for idx, row in df_venda[mask_vazio].iterrows():
            match = agend_clean[agend_clean['Ped. Venda'] == row['Pedido_Str']]
            if not match.empty:
                nova_data = match.iloc[0]['Previsão Ent.']
                if pd.notnull(nova_data):
                    # Preenche na base
                    df_venda.at[idx, 'DATA_ENTREGA'] = nova_data
                    
                    # Calcula SLA
                    dif_h = (nova_data - row['DATA_EMISSAO']).total_seconds() / 3600
                    sla_f = "Dentro 48h" if (0 <= dif_h <= 48) else "Fora do Prazo"
                    df_venda.at[idx, 'SLA_48H'] = sla_f
                    
                    # Grava Automático no Histórico (Persistência)
                    pid = row['Pedido_Str']
                    registro = {
                        'Pedido': pid, 'Status_Auditoria': 'AGENDADO MANUALMENTE', 
                        'SLA_Final': sla_f, 'Data_Inserida': nova_data.strftime('%Y-%m-%d'),
                        'Filial': row['Filial'], 'Vendedor': row['Vendedor']
                    }
                    st.session_state.classificacoes[pid] = registro
                    pd.DataFrame([registro]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))

    # Finaliza calculando SLA para o restante
    mask_sla = df_venda['DATA_ENTREGA'].notnull() & df_venda['DATA_EMISSAO'].notnull()
    df_venda.loc[mask_sla, 'SLA_48H'] = (df_venda['DATA_ENTREGA'] - df_venda['DATA_EMISSAO']).dt.total_seconds() / 3600
    df_venda['SLA_48H'] = df_venda['SLA_48H'].apply(lambda x: "Dentro 48h" if (isinstance(x, float) and 0 <= x <= 48) else "Fora do Prazo" if isinstance(x, float) else "Pendente")
    
    return df_venda

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Performance e Auditoria King Star")

    if 'base_mestra' not in st.session_state: st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state: st.session_state.classificacoes = {}
    if 'motivos_extra' not in st.session_state: st.session_state.motivos_extra = []

    # Carregar histórico físico ao iniciar
    if os.path.exists('historico_auditoria.csv') and not st.session_state.classificacoes:
        try:
            h_df = pd.read_csv('historico_auditoria.csv')
            for _, r in h_df.iterrows():
                st.session_state.classificacoes[str(r['Pedido'])] = r.to_dict()
        except: pass

    tabs = st.tabs(["📊 Performance", "🔍 Auditoria", "📋 Relatório", "⚙️ Configurações"])
    df = st.session_state.base_mestra

    with tabs[0]: # PERFORMANCE
        if not df.empty:
            df_u = df.drop_duplicates(subset=['Pedido'])
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{len(df_u)}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>Total Clientes</p><p class='metric-value'>{df['Cliente'].nunique()}</p></div>", unsafe_allow_html=True)
            auditoria_pend = len(df[(df['TIPO_VENDA'].astype(str).str.contains('003')) & ((df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())) & (~df['Pedido'].astype(str).isin(st.session_state.classificacoes.keys()))])
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>Pendentes Auditoria</p><p class='metric-value'>{auditoria_pend}</p></div>", unsafe_allow_html=True)
            st.plotly_chart(px.pie(df_u, names='TIPO_VENDA', title="Mix de Vendas (%)", hole=0.4), use_container_width=True)
        else: st.info("Suba as bases na aba Configurações.")

    with tabs[1]: # AUDITORIA MANUAL
        if not df.empty:
            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)
            crit_erro = (df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())
            view = df[crit_venda & crit_erro].copy()
            view = view[~view['Pedido'].astype(str).isin(st.session_state.classificacoes.keys())]

            st.subheader(f"🔍 Esteira de Auditoria Manual: {len(view)} casos")
            motivos = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido"] + st.session_state.motivos_extra

            for idx, row in view.head(10).iterrows():
                pid = str(row['Pedido'])
                with st.container():
                    st.markdown(f"<div class='esteira-card'><div class='card-header'>FILIAL: {row['Filial']} | PEDIDO: {pid}</div><b>Cliente:</b> {row['Cliente']}<br><span class='badge badge-red'>Seq: {row['Seq_Pedido']}</span><span class='badge badge-blue'>Entrega: {row['DATA_ENTREGA'] if pd.notnull(row['DATA_ENTREGA']) else 'NÃO LOCALIZADO'}</span></div>", unsafe_allow_html=True)
                    c_col1, c_col2 = st.columns([2,1])
                    sel = c_col1.selectbox("Causa:", motivos, key=f"sel_{pid}_{idx}")
                    dt_man = row['DATA_PREVISTA']
                    if sel != "Não Analisado" and pd.isna(dt_man):
                        dt_man = c_col2.date_input("Data Real:", key=f"date_{pid}_{idx}")
                    if sel != "Não Analisado" and pd.notnull(dt_man):
                        if st.button(f"Confirmar {pid}", key=f"btn_{pid}_{idx}"):
                            dt_dt = pd.to_datetime(dt_man)
                            dif_h = (dt_dt - pd.to_datetime(row['DATA_EMISSAO'])).total_seconds() / 3600
                            sla_f = "Dentro 48h" if (0 <= dif_h <= 48) else "Fora do Prazo"
                            registro = {'Pedido': pid, 'Status_Auditoria': sel, 'SLA_Final': sla_f, 'Data_Inserida': dt_dt.strftime('%Y-%m-%d'), 'Filial': row['Filial'], 'Vendedor': row['Vendedor']}
                            st.session_state.classificacoes[pid] = registro
                            pd.DataFrame([registro]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                            st.rerun()

    with tabs[2]: # RELATÓRIO FINAL
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index(drop=True)
            st.dataframe(resumo, use_container_width=True)
            st.download_button("📥 Baixar Auditoria Completa", resumo.to_csv(index=False).encode('utf-8'), "auditoria_kingstar.csv")

    with tabs[3]: # CONFIGURAÇÕES
        st.subheader("⚙️ Importação de Dados")
        c1, c2 = st.columns(2)
        arq_v = c1.file_uploader("1. Base de Venda", type=['csv', 'xlsx'])
        arq_a = c2.file_uploader("2. Relatório de Agendados (Robô)", type=['csv', 'xlsx'])
        
        if st.button("🚀 PROCESSAR E AUDITAR"):
            if arq_v:
                df_v = pd.read_csv(arq_v, encoding='latin1', sep=None, engine='python') if arq_v.name.endswith('.csv') else pd.read_excel(arq_v)
                df_a = None
                if arq_a:
                    df_a = pd.read_csv(arq_a, encoding='latin1', sep=None, engine='python') if arq_a.name.endswith('.csv') else pd.read_excel(arq_a)
                st.session_state.base_mestra = tratar_e_auditar_automatico(df_v, df_a)
                st.success("Processamento concluído! Verifique os resultados na Performance e Auditoria.")
                st.rerun()
        
        if st.button("🔥 LIMPAR TUDO"):
            st.session_state.base_mestra = pd.DataFrame()
            st.session_state.classificacoes = {}
            st.rerun()

if __name__ == "__main__":
    main()
