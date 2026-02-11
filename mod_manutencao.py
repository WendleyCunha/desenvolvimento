import streamlit as st
import pandas as pd
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
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE AUDITORIA AUTOMÁTICA (PROCV)
# =========================================================
def tratar_e_auditar_automatico(df_venda, df_agendados=None):
    if df_venda.empty: return df_venda
    
    # Padronização de Colunas da Base Venda
    df_venda.columns = [str(col).strip() for col in df_venda.columns]
    df_venda['Pedido_Limpo'] = df_venda['Pedido'].astype(str).str.replace("'", "").str.strip()
    
    # Tratamento de Datas
    for col in ['Dt Emissão', 'Data Entrega', 'Data Prevista']:
        if col in df_venda.columns:
            df_venda[col] = pd.to_datetime(df_venda[col].astype(str).replace(['/ /', 'nan'], np.nan), errors='coerce')
    
    # Limpeza de Cliente (/99)
    if 'Cliente' in df_venda.columns:
        df_venda['Cliente_Limpo'] = df_venda['Cliente'].astype(str).str.split('/').str[0].str.strip()
        df_venda = df_venda.sort_values(['Cliente_Limpo', 'Dt Emissão'])
        df_venda['Seq_Pedido'] = df_venda.groupby('Cliente_Limpo').cumcount() + 1

    # ROBÔ DE AUDITORIA (PROCV AUTOMÁTICO)
    if df_agendados is not None:
        df_agendados.columns = [str(col).strip() for col in df_agendados.columns]
        # Limpa o Pedido (remove aspas: '652549 -> 652549)
        df_agendados['Ped_Limpo_Agend'] = df_agendados['Ped. Venda'].astype(str).str.replace("'", "").str.strip()
        df_agendados['Data_Agend_DT'] = pd.to_datetime(df_agendados['Previsão Ent.'], errors='coerce')
        
        # Cruzamento
        for idx, row in df_venda.iterrows():
            pid = row['Pedido_Limpo']
            
            # Só audita se: For 003, estiver sem data de entrega e não estiver no histórico
            if "003" in str(row['Tipo Venda']) and pd.isna(row['Data Entrega']):
                if pid not in st.session_state.classificacoes:
                    
                    # Procura no relatório de Agendados
                    match = df_agendados[df_agendados['Ped_Limpo_Agend'] == pid]
                    
                    if not match.empty:
                        nova_dt = match.iloc[0]['Data_Agend_DT']
                        if pd.notnull(nova_dt):
                            # Atualiza a linha na memória
                            df_venda.at[idx, 'Data Entrega'] = nova_dt
                            
                            # Calcula SLA
                            dif_h = (nova_dt - row['Dt Emissão']).total_seconds() / 3600
                            sla_f = "Dentro 48h" if (0 <= dif_h <= 48) else "Fora do Prazo"
                            
                            # Registra no Histórico Permanente
                            registro = {
                                'Pedido': pid, 
                                'Status_Auditoria': 'AGENDADO MANUALMENTE', 
                                'SLA_Final': sla_f, 
                                'Data_Inserida': nova_dt.strftime('%Y-%m-%d'),
                                'Filial': row['Filial'], 
                                'Vendedor': row['Vendedor']
                            }
                            st.session_state.classificacoes[pid] = registro
                            pd.DataFrame([registro]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))

    return df_venda

# =========================================================
# 3. INTERFACE STREAMLIT
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Auditoria Inteligente King Star")

    if 'base_mestra' not in st.session_state: st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state: st.session_state.classificacoes = {}

    # Carrega histórico salvo no PC/Servidor
    if os.path.exists('historico_auditoria.csv') and not st.session_state.classificacoes:
        try:
            h_df = pd.read_csv('historico_auditoria.csv')
            for _, r in h_df.iterrows():
                st.session_state.classificacoes[str(r['Pedido'])] = r.to_dict()
        except: pass

    tabs = st.tabs(["📊 Dashboard", "🔍 Esteira de Auditoria", "📋 Relatório Geral", "⚙️ Configuração"])

    with tabs[3]: # CONFIGURAÇÃO
        st.subheader("Suba os arquivos diários")
        c1, c2 = st.columns(2)
        venda_file = c1.file_uploader("Base Venda (Excel/CSV)", type=['csv', 'xlsx'])
        agend_file = c2.file_uploader("Agendados (Relatório 2)", type=['csv', 'xlsx'])
        
        if st.button("🚀 Executar Auditoria"):
            if venda_file:
                df_v = pd.read_csv(venda_file, encoding='latin1', sep=None, engine='python') if venda_file.name.endswith('.csv') else pd.read_excel(venda_file)
                df_a = None
                if agend_file:
                    df_a = pd.read_csv(agend_file, encoding='latin1', sep=None, engine='python') if agend_file.name.endswith('.csv') else pd.read_excel(agend_file)
                
                st.session_state.base_mestra = tratar_e_auditar_automatico(df_v, df_a)
                st.success("Auditoria concluída!")
                st.rerun()

    with tabs[1]: # ESTEIRA (O que sobrou que o robô não achou)
        df = st.session_state.base_mestra
        if not df.empty:
            # Filtra o que o robô NÃO conseguiu auditar sozinho
            pendentes = df[(df['Tipo Venda'].astype(str).str.contains('003')) & 
                           (df['Data Entrega'].isna()) & 
                           (~df['Pedido_Limpo'].isin(st.session_state.classificacoes.keys()))]
            
            st.subheader(f"Pendências Manuais: {len(pendentes)}")
            
            for idx, row in pendentes.head(10).iterrows():
                pid = row['Pedido_Limpo']
                with st.container():
                    st.markdown(f"<div class='esteira-card'><b>PEDIDO: {pid}</b> | Cliente: {row['Cliente_Limpo']}<br>Emissão: {row['Dt Emissão']}</div>", unsafe_allow_html=True)
                    motivo = st.selectbox("Resultado:", ["Não Analisado", "Pedido Correto", "Duplicado"], key=f"m_{pid}_{idx}")
                    if motivo != "Não Analisado":
                        dt_input = st.date_input("Data Real de Entrega:", key=f"d_{pid}_{idx}")
                        if st.button(f"Confirmar {pid}", key=f"b_{pid}_{idx}"):
                            # Salva manual
                            dt_dt = pd.to_datetime(dt_input)
                            dif_h = (dt_dt - pd.to_datetime(row['Dt Emissão'])).total_seconds() / 3600
                            sla_f = "Dentro 48h" if (0 <= dif_h <= 48) else "Fora do Prazo"
                            reg = {'Pedido': pid, 'Status_Auditoria': motivo, 'SLA_Final': sla_f, 'Data_Inserida': dt_dt.strftime('%Y-%m-%d'), 'Filial': row['Filial'], 'Vendedor': row['Vendedor']}
                            st.session_state.classificacoes[pid] = reg
                            pd.DataFrame([reg]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                            st.rerun()
        else:
            st.info("Aguardando importação de dados.")

    with tabs[2]: # RELATÓRIO
        if st.session_state.classificacoes:
            res_df = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index(drop=True)
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Baixar CSV", res_df.to_csv(index=False).encode('utf-8'), "auditoria_final.csv")

if __name__ == "__main__":
    main()
