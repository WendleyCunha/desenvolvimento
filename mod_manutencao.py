import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime
import os

# =========================================================
# 1. ESTILO E INTERFACE (O MELHOR DO VISUAL)
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
# 2. MOTOR DE CONFRONTO E TRATAMENTO
# =========================================================
def processar_bases(df_venda, df_agendados=None):
    if df_venda.empty: return df_venda
    
    # 1. Padronização rigorosa de nomes
    df_venda.columns = [str(col).strip() for col in df_venda.columns]
    
    # Mapeia colunas originais para o padrão do código
    mapeamento = {
        'Dt Emissão': 'DATA_EMISSAO', 
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Data Entrega': 'DATA_ENTREGA', 
        'Data Ent': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA',
        'Data Prevista': 'DATA_PREVISTA'
    }
    df_venda = df_venda.rename(columns=mapeamento)
    
    # Criar chave de pedido limpa (sem aspas)
    df_venda['Pedido_Limpo'] = df_venda['Pedido'].astype(str).str.replace("'", "").str.strip()
    
    # Converter Datas
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA', 'DATA_PREVISTA']:
        if col in df_venda.columns:
            df_venda[col] = pd.to_datetime(df_venda[col].astype(str).replace(['/ /', 'nan', 'None', 'NaT'], np.nan), errors='coerce')
    
    # Tratamento de Cliente e Sequência
    if 'Cliente' in df_venda.columns:
        df_venda['Cliente_Limpo'] = df_venda['Cliente'].astype(str).str.split('/').str[0].str.strip()
        df_venda = df_venda.sort_values(['Cliente_Limpo', 'DATA_EMISSAO'])
        df_venda['Seq_Pedido'] = df_venda.groupby('Cliente_Limpo').cumcount() + 1

    # 2. LÓGICA DE CONFRONTO AUTOMÁTICO (PROCV)
    if df_agendados is not None:
        df_agendados.columns = [str(col).strip() for col in df_agendados.columns]
        # Limpa o pedido do agendamento (remove aspas)
        ped_col_agend = 'Ped. Venda' if 'Ped. Venda' in df_agendados.columns else df_agendados.columns[1]
        data_col_agend = 'Previsão Ent.' if 'Previsão Ent.' in df_agendados.columns else df_agendados.columns[3]
        
        df_agendados['Ped_Limpo_Agend'] = df_agendados[ped_col_agend].astype(str).str.replace("'", "").str.strip()
        df_agendados['Data_Agend_DT'] = pd.to_datetime(df_agendados[data_col_agend], errors='coerce')
        
        # O PROCV:
        for idx, row in df_venda.iterrows():
            pid = row['Pedido_Limpo']
            # Regra: Se é 003 e está sem entrega
            if "003" in str(row.get('TIPO_VENDA', '')) and pd.isna(row['DATA_ENTREGA']):
                if pid not in st.session_state.classificacoes:
                    match = df_agendados[df_agendados['Ped_Limpo_Agend'] == pid]
                    if not match.empty:
                        nova_dt = match.iloc[0]['Data_Agend_DT']
                        if pd.notnull(nova_dt):
                            df_venda.at[idx, 'DATA_ENTREGA'] = nova_dt
                            dif_h = (nova_dt - row['DATA_EMISSAO']).total_seconds() / 3600
                            sla_f = "Dentro 48h" if (0 <= dif_h <= 48) else "Fora do Prazo"
                            
                            reg = {'Pedido': pid, 'Status_Auditoria': 'AGENDADO MANUALMENTE', 'SLA_Final': sla_f, 
                                   'Data_Inserida': nova_dt.strftime('%Y-%m-%d'), 'Filial': row.get('Filial','-'), 'Vendedor': row.get('Vendedor','-')}
                            st.session_state.classificacoes[pid] = reg
                            pd.DataFrame([reg]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))

    # Cálculo Final de SLA para o Dashboard
    df_venda['SLA_48H'] = "Pendente"
    if 'DATA_EMISSAO' in df_venda.columns and 'DATA_ENTREGA' in df_venda.columns:
        mask = df_venda['DATA_ENTREGA'].notnull() & df_venda['DATA_EMISSAO'].notnull()
        horas = (df_venda.loc[mask, 'DATA_ENTREGA'] - df_venda.loc[mask, 'DATA_EMISSAO']).dt.total_seconds() / 3600
        df_venda.loc[mask, 'SLA_48H'] = horas.apply(lambda x: "Dentro 48h" if (0 <= x <= 48) else "Fora do Prazo")
    
    return df_venda

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Auditoria King Star v2.0")

    if 'base_mestra' not in st.session_state: st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state: st.session_state.classificacoes = {}

    # Carregar histórico físico ao iniciar
    if os.path.exists('historico_auditoria.csv') and not st.session_state.classificacoes:
        try:
            h_df = pd.read_csv('historico_auditoria.csv')
            for _, r in h_df.iterrows():
                st.session_state.classificacoes[str(r['Pedido'])] = r.to_dict()
        except: pass

    tabs = st.tabs(["📊 Performance", "🔍 Esteira de Auditoria", "📋 Relatório", "⚙️ Configurações"])
    df = st.session_state.base_mestra

    # --- TAB 1: PERFORMANCE ---
    with tabs[0]:
        if not df.empty and 'TIPO_VENDA' in df.columns:
            df_u = df.drop_duplicates(subset=['Pedido_Limpo'])
            st.subheader("📊 Resumo da Base")
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{len(df_u)}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>Auditados (Total)</p><p class='metric-value'>{len(st.session_state.classificacoes)}</p></div>", unsafe_allow_html=True)
            
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)]
            sla_ok = len(df_003[df_003['SLA_48H'] == "Dentro 48h"])
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>SLA 48h (Tipo 003)</p><p class='metric-value'>{sla_ok}</p></div>", unsafe_allow_html=True)
            
            st.plotly_chart(px.pie(df_u, names='TIPO_VENDA', title="Mix de Vendas", hole=0.4), use_container_width=True)
        else:
            st.info("Aguardando processamento das bases na aba Configurações.")

    # --- TAB 2: ESTEIRA ---
    with tabs[1]:
        if not df.empty and 'TIPO_VENDA' in df.columns:
            pendentes = df[(df['TIPO_VENDA'].astype(str).str.contains('003')) & 
                           (df['DATA_ENTREGA'].isna()) & 
                           (~df['Pedido_Limpo'].isin(st.session_state.classificacoes.keys()))]
            
            st.subheader(f"🔍 Pendências Manuais ({len(pendentes)})")
            
            for idx, row in pendentes.head(10).iterrows():
                pid = row['Pedido_Limpo']
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <div class='card-header'>FILIAL: {row.get('Filial','-')} | PEDIDO: {pid}</div>
                            <b>Cliente:</b> {row.get('Cliente_Limpo','-')}<br>
                            <span class='badge badge-red'>Sequência: {row.get('Seq_Pedido', 1)}</span>
                            <span class='badge badge-blue'>Emissão: {row['DATA_EMISSAO'].strftime('%d/%m/%Y') if pd.notnull(row['DATA_EMISSAO']) else '-'}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    c_col1, c_col2 = st.columns([2,1])
                    motivo = c_col1.selectbox("Classificar:", ["Não Analisado", "Pedido Correto", "Duplicado", "Erro de Digitação"], key=f"m_{pid}_{idx}")
                    
                    if motivo != "Não Analisado":
                        dt_manual = c_col2.date_input("Data Entrega:", key=f"d_{pid}_{idx}")
                        if st.button(f"Salvar {pid}", key=f"b_{pid}_{idx}"):
                            dt_dt = pd.to_datetime(dt_manual)
                            dif_h = (dt_dt - row['DATA_EMISSAO']).total_seconds() / 3600
                            sla_f = "Dentro 48h" if (0 <= dif_h <= 48) else "Fora do Prazo"
                            
                            reg = {'Pedido': pid, 'Status_Auditoria': motivo, 'SLA_Final': sla_f, 
                                   'Data_Inserida': dt_dt.strftime('%Y-%m-%d'), 'Filial': row.get('Filial','-'), 'Vendedor': row.get('Vendedor','-')}
                            st.session_state.classificacoes[pid] = reg
                            pd.DataFrame([reg]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                            st.rerun()
        else:
            st.info("Suba a base de vendas para auditar.")

    # --- TAB 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            res_df = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index(drop=True)
            st.subheader("📋 Log de Auditoria")
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Baixar Auditoria", res_df.to_csv(index=False).encode('utf-8'), "auditoria_final.csv")

    # --- TAB 4: CONFIGURAÇÕES ---
    with tabs[3]:
        st.subheader("⚙️ Importação de Arquivos")
        c1, c2 = st.columns(2)
        v_file = c1.file_uploader("1. Base de Venda (Obrigatório)", type=['csv', 'xlsx'])
        a_file = c2.file_uploader("2. Relatório de Agendados (Opcional)", type=['csv', 'xlsx'])
        
        if st.button("🚀 PROCESSAR BASES"):
            if v_file:
                df_v = pd.read_csv(v_file, encoding='latin1', sep=None, engine='python') if v_file.name.endswith('.csv') else pd.read_excel(v_file)
                df_a = None
                if a_file:
                    df_a = pd.read_csv(a_file, encoding='latin1', sep=None, engine='python') if a_file.name.endswith('.csv') else pd.read_excel(a_file)
                
                # Executa o motor de tratamento e PROCV
                st.session_state.base_mestra = processar_bases(df_v, df_a)
                st.success("Bases processadas e auditadas automaticamente!")
                st.rerun()
        
        st.divider()
        if st.button("🔥 RESETAR SISTEMA"):
            st.session_state.base_mestra = pd.DataFrame()
            st.session_state.classificacoes = {}
            if os.path.exists('historico_auditoria.csv'):
                os.remove('historico_auditoria.csv')
            st.rerun()

if __name__ == "__main__":
    main()
