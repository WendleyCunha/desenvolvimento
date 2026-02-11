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
# 2. MOTOR DE TRATAMENTO E LÓGICA DE SLA
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
    
    # Limpeza de aspas e espaços no Pedido (Chave Primária)
    if 'Pedido' in df.columns:
        df['Pedido'] = df['Pedido'].astype(str).str.replace("'", "").str.strip()
    
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA', 'DATA_PREVISTA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace(['/ /', 'nan', 'None'], np.nan), errors='coerce')
    
    if 'Cliente' in df.columns:
        df['Cliente_Limpo'] = df['Cliente'].astype(str).str.split('/').str[0].str.strip()
        df = df.sort_values(['Cliente_Limpo', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente_Limpo').cumcount() + 1
    
    return df

def calcular_sla(dt_emissao, dt_entrega):
    if pd.isna(dt_emissao) or pd.isna(dt_entrega): return "Pendente"
    # Diferença em horas
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
    
    # Carregar histórico físico do CSV
    if os.path.exists('historico_auditoria.csv') and not st.session_state.classificacoes:
        try:
            h_df = pd.read_csv('historico_auditoria.csv')
            for _, r in h_df.iterrows():
                st.session_state.classificacoes[str(r['Pedido'])] = r.to_dict()
        except: pass

    tabs = st.tabs(["📊 Performance", "🔍 Auditoria Automática", "📋 Relatório Geral", "⚙️ Configurações"])
    
    # ---------------------------------------------------------
    # ABA 4: CONFIGURAÇÕES (CARGA INICIAL)
    # ---------------------------------------------------------
    with tabs[3]:
        st.subheader("Configuração da Base Mestra")
        arq = st.file_uploader("Upload da Base de Vendas (Arquivo Principal)", type=['csv', 'xlsx'])
        if arq:
            df_raw = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
            st.session_state.base_mestra = tratar_dados_oficial(df_raw)
            st.success("Base Mestra carregada e pronta!")

        st.divider()
        if st.button("🔥 RESETAR TUDO (Limpar Memória e Histórico)"):
            st.session_state.base_mestra = pd.DataFrame()
            st.session_state.classificacoes = {}
            if os.path.exists('historico_auditoria.csv'): os.remove('historico_auditoria.csv')
            st.rerun()

    # ---------------------------------------------------------
    # ABA 2: AUDITORIA AUTOMÁTICA (O NOVO CAMINHO)
    # ---------------------------------------------------------
    with tabs[1]:
        df = st.session_state.base_mestra
        if not df.empty:
            st.subheader("📥 Cruzamento com Relatório de Agendados")
            st.info("O sistema buscará o 'Ped. Venda' (B) e aplicará a 'Previsão Ent.' (D) nos pedidos sem data de entrega.")
            
            arq_agend = st.file_uploader("Upload Relatório de Agendados", type=['csv', 'xlsx'], key="agend_audit")
            
            if arq_agend:
                df_ag = pd.read_csv(arq_agend, encoding='latin1', sep=None, engine='python') if arq_agend.name.endswith('.csv') else pd.read_excel(arq_agend)
                
                if st.button("🚀 Executar Auditoria Automática"):
                    df_ag.columns = [str(c).strip() for c in df_ag.columns]
                    
                    # Colunas fixas conforme sua regra (B e D)
                    col_pv = 'Ped. Venda' 
                    col_ent = 'Previsão Ent.'
                    
                    if col_pv in df_ag.columns and col_ent in df_ag.columns:
                        df_ag[col_pv] = df_ag[col_pv].astype(str).str.replace("'", "").str.strip()
                        df_ag[col_ent] = pd.to_datetime(df_ag[col_ent], errors='coerce')
                        
                        sucessos = 0
                        for _, row_ag in df_ag.iterrows():
                            pv = row_ag[col_pv]
                            data_f = row_ag[col_ent]
                            
                            if pd.notnull(data_f):
                                # Procura na Mestra onde o pedido bate e a entrega está vazia ou é 003
                                mask = (df['Pedido'] == pv)
                                if mask.any():
                                    idx_mestra = df[mask].index[0]
                                    # Só atualiza se ainda estiver pendente ou se você quiser sobrescrever
                                    if pd.isna(df.at[idx_mestra, 'DATA_ENTREGA']):
                                        dt_emi = df.at[idx_mestra, 'DATA_EMISSAO']
                                        sla = calcular_sla(dt_emi, data_f)
                                        
                                        # Atualiza Dataframe em memória
                                        df.at[idx_mestra, 'DATA_ENTREGA'] = data_f
                                        df.at[idx_mestra, 'SLA_48H'] = sla
                                        
                                        # Registra no histórico
                                        registro = {
                                            'Pedido': pv, 'Status_Auditoria': 'AUTOMÁTICO (AGENDADOS)',
                                            'SLA_Final': sla, 'Data_Inserida': data_f.strftime('%Y-%m-%d'),
                                            'Filial': df.at[idx_mestra, 'Filial'], 'Vendedor': df.at[idx_mestra, 'Vendedor']
                                        }
                                        st.session_state.classificacoes[pv] = registro
                                        pd.DataFrame([registro]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                                        sucessos += 1
                        
                        st.success(f"Processo concluído! {sucessos} pedidos auditados automaticamente.")
                        st.rerun()
                    else:
                        st.error(f"Colunas '{col_pv}' ou '{col_ent}' não encontradas no arquivo.")

            st.divider()
            # Visualização do que ainda sobra (Manual)
            pendentes = df[(df['TIPO_VENDA'].astype(str).str.contains('003')) & (df['DATA_ENTREGA'].isna())]
            st.subheader(f"🔍 Pendências Restantes ({len(pendentes)})")
            if not pendentes.empty:
                for idx, r in pendentes.head(5).iterrows():
                    st.markdown(f"<div class='esteira-card'><b>PEDIDO: {r['Pedido']}</b> | Cliente: {r.get('Cliente_Limpo', 'N/A')}<br><small>Seq: {r.get('Seq_Pedido', '1')}</small></div>", unsafe_allow_html=True)
        else:
            st.warning("Por favor, carregue a Base Mestra na aba Configurações primeiro.")

    # ---------------------------------------------------------
    # ABA 1: PERFORMANCE (DASHBOARDS)
    # ---------------------------------------------------------
    with tabs[0]:
        if not df.empty:
            st.subheader("📊 Performance Consolidada")
            # Garante cálculo de SLA para o gráfico
            df['SLA_48H'] = df.apply(lambda x: calcular_sla(x['DATA_EMISSAO'], x['DATA_ENTREGA']), axis=1)
            
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)]
            
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{len(df)}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>Auditados</p><p class='metric-value'>{len(st.session_state.classificacoes)}</p></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>Dentro 48h (003)</p><p class='metric-value'>{len(df_003[df_003['SLA_48H'] == 'Dentro 48h'])}</p></div>", unsafe_allow_html=True)
            
            st.plotly_chart(px.pie(df_003, names='SLA_48H', title="SLA de Entregas (Tipo 003)", hole=0.4), use_container_width=True)
        else:
            st.info("Aguardando dados para gerar indicadores.")

    # ---------------------------------------------------------
    # ABA 3: RELATÓRIO
    # ---------------------------------------------------------
    with tabs[2]:
        if st.session_state.classificacoes:
            res_df = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index(drop=True)
            st.subheader("📋 Histórico de Auditoria (Automática + Manual)")
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Baixar Planilha de Auditoria", res_df.to_csv(index=False).encode('utf-8'), "relatorio_auditoria.csv")
        else:
            st.info("Nenhum pedido auditado no momento.")

if __name__ == "__main__":
    main()
