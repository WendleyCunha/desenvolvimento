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
# 2. MOTOR DE TRATAMENTO E CONFRONTO
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
    
    # Garantir que Pedido seja String para o confronto
    if 'Pedido' in df.columns:
        df['Pedido'] = df['Pedido'].astype(str).str.replace("'", "").str.strip()
    
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA', 'DATA_PREVISTA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace(['/ /', 'nan'], np.nan), errors='coerce')
    
    if 'Cliente' in df.columns:
        df['Cliente_Limpo'] = df['Cliente'].astype(str).str.split('/').str[0].str.strip()
        df = df.sort_values(['Cliente_Limpo', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente_Limpo').cumcount() + 1
    
    return df

def calcular_sla(dt_emissao, dt_entrega):
    if pd.isna(dt_emissao) or pd.isna(dt_entrega): return "Pendente"
    horas = (dt_entrega - dt_emissao).total_seconds() / 3600
    return "Dentro 48h" if (0 <= horas <= 48) else "Fora do Prazo"

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Performance e Auditoria King Star")

    if 'base_mestra' not in st.session_state: st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state: st.session_state.classificacoes = {}
    
    # --- BARRA LATERAL (OPCIONAL) OU TABS ---
    tabs = st.tabs(["📊 Performance", "🔍 Auditoria Automática", "📋 Relatório Geral", "⚙️ Configurações"])
    
    # ---------------------------------------------------------
    # ABA CONFIGURAÇÕES (CARGA INICIAL)
    # ---------------------------------------------------------
    with tabs[3]:
        st.subheader("1. Subir Base de Vendas (Mestra)")
        arq = st.file_uploader("Upload Base Venda", type=['csv', 'xlsx'], key="mestra")
        if arq:
            df_raw = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
            st.session_state.base_mestra = tratar_dados_oficial(df_raw)
            st.success("Base Mestra Carregada!")

        if st.button("🔥 RESETAR TUDO"):
            st.session_state.base_mestra = pd.DataFrame()
            st.session_state.classificacoes = {}
            if os.path.exists('historico_auditoria.csv'): os.remove('historico_auditoria.csv')
            st.rerun()

    # ---------------------------------------------------------
    # ABA AUDITORIA (LOGICA DE CONFRONTO SOLICITADA)
    # ---------------------------------------------------------
    with tabs[1]:
        df = st.session_state.base_mestra
        if not df.empty:
            st.subheader("🚀 Confronto Automático de Agendados")
            col_up1, col_up2 = st.columns([2,1])
            
            with col_up1:
                arq_agend = st.file_uploader("Subir Planilha de Agendados (Coluna B e D)", type=['csv', 'xlsx'])
            
            if arq_agend:
                df_ag = pd.read_csv(arq_agend, encoding='latin1', sep=None, engine='python') if arq_agend.name.endswith('.csv') else pd.read_excel(arq_agend)
                
                if st.button("Executar Cruzamento de Dados"):
                    # Padronizar colunas do agendado
                    df_ag.columns = [str(c).strip() for c in df_ag.columns]
                    # Ped. Venda (B) e Previsão Ent. (D) - usando nomes ou índices
                    col_pv = 'Ped. Venda' 
                    col_ent = 'Previsão Ent.'
                    
                    df_ag[col_pv] = df_ag[col_pv].astype(str).str.replace("'", "").str.strip()
                    df_ag[col_ent] = pd.to_datetime(df_ag[col_ent], errors='coerce')
                    
                    cont_sucesso = 0
                    
                    # Loop de cruzamento
                    for idx, row_ag in df_ag.iterrows():
                        pv = row_ag[col_pv]
                        data_nova = row_ag[col_ent]
                        
                        if pd.notnull(data_nova):
                            # Acha na base mestra onde o pedido coincide e a entrega está vazia
                            mask = (df['Pedido'] == pv) & (df['DATA_ENTREGA'].isna())
                            if mask.any():
                                dt_emissao = df.loc[mask, 'DATA_EMISSAO'].iloc[0]
                                sla = calcular_sla(dt_emissao, data_nova)
                                
                                # Atualiza a memória
                                df.loc[mask, 'DATA_ENTREGA'] = data_nova
                                df.loc[mask, 'SLA_48H'] = sla
                                
                                # Salva no histórico
                                registro = {
                                    'Pedido': pv, 'Status_Auditoria': 'AGENDAMENTO AUTOMÁTICO',
                                    'SLA_Final': sla, 'Data_Inserida': data_nova.strftime('%Y-%m-%d'),
                                    'Filial': df.loc[mask, 'Filial'].iloc[0], 'Vendedor': df.loc[mask, 'Vendedor'].iloc[0]
                                }
                                st.session_state.classificacoes[pv] = registro
                                pd.DataFrame([registro]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                                cont_sucesso += 1
                    
                    st.success(f"Confronto finalizado! {cont_sucesso} pedidos atualizados automaticamente.")
                    st.rerun()

            st.divider()
            
            # FILTRO PARA O QUE SOBROU (MANUAL)
            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)
            crit_pendente = df['DATA_ENTREGA'].isna()
            view = df[crit_venda & crit_pendente].copy()
            view = view[~view['Pedido'].isin(st.session_state.classificacoes.keys())]

            st.subheader(f"🔍 Pendências Manuais: {len(view)}")
            # ... (Restante do código de visualização de cards que você já possui)
            for idx, row in view.head(5).iterrows():
                with st.container():
                    st.markdown(f"<div class='esteira-card'><b>PEDIDO: {row['Pedido']}</b> | {row['Cliente_Limpo']}</div>", unsafe_allow_html=True)
                    # Opção de marcar manual aqui se necessário

    # ---------------------------------------------------------
    # ABA PERFORMANCE (DASHBOARD)
    # ---------------------------------------------------------
    with tabs[0]:
        if not df.empty:
            st.subheader("📊 Performance de Entregas")
            # Recalcula SLA para garantir que o automático apareça no gráfico
            df['SLA_48H'] = df.apply(lambda x: calcular_sla(x['DATA_EMISSAO'], x['DATA_ENTREGA']), axis=1)
            
            c1, c2 = st.columns(2)
            fig_pie = px.pie(df[df['TIPO_VENDA'].astype(str).str.contains('003')], names='SLA_48H', title="SLA 48h (Tipo 003)")
            c1.plotly_chart(fig_pie, use_container_width=True)
            
            fig_bar = px.bar(df.groupby('Filial')['Pedido'].count().reset_index(), x='Filial', y='Pedido', title="Pedidos por Filial")
            c2.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Carregue a base nas configurações.")

    # ---------------------------------------------------------
    # ABA RELATÓRIO
    # ---------------------------------------------------------
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index(drop=True)
            st.dataframe(resumo, use_container_width=True)
            st.download_button("📥 Baixar Relatório Consolidado", resumo.to_csv(index=False).encode('utf-8'), "auditoria_king.csv")

if __name__ == "__main__":
    main()
