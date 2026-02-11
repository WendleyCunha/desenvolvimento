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
# 2. MOTOR DE CONFRONTO E TRATAMENTO (LÓGICA QUE FUNCIONOU)
# =========================================================
def processar_bases(df_venda, df_agendados=None):
    if df_venda.empty: return df_venda
    
    # Padronização da Base Venda
    df_venda.columns = [str(col).strip() for col in df_venda.columns]
    mapeamento = {'Dt Emissão': 'DATA_EMISSAO', 'Data Entrega': 'DATA_ENTREGA', 'Tipo Venda': 'TIPO_VENDA'}
    df_venda = df_venda.rename(columns=mapeamento)
    
    df_venda['Pedido_Limpo'] = df_venda['Pedido'].astype(str).str.replace("'", "").str.strip()
    
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA', 'Data Prevista']:
        if col in df_venda.columns:
            df_venda[col] = pd.to_datetime(df_venda[col].astype(str).replace(['/ /', 'nan'], np.nan), errors='coerce')
    
    if 'Cliente' in df_venda.columns:
        df_venda['Cliente_Limpo'] = df_venda['Cliente'].astype(str).str.split('/').str[0].str.strip()
        df_venda = df_venda.sort_values(['Cliente_Limpo', 'DATA_EMISSAO'])
        df_venda['Seq_Pedido'] = df_venda.groupby('Cliente_Limpo').cumcount() + 1

    # LÓGICA DE CONFRONTO AUTOMÁTICO (PROCV)
    if df_agendados is not None:
        df_agendados.columns = [str(col).strip() for col in df_agendados.columns]
        df_agendados['Ped_Limpo_Agend'] = df_agendados['Ped. Venda'].astype(str).str.replace("'", "").str.strip()
        df_agendados['Data_Agend_DT'] = pd.to_datetime(df_agendados['Previsão Ent.'], errors='coerce')
        
        for idx, row in df_venda.iterrows():
            pid = row['Pedido_Limpo']
            # Regra: Se é 003, está sem entrega e o Robô achou no agendamento
            if "003" in str(row['TIPO_VENDA']) and pd.isna(row['DATA_ENTREGA']):
                if pid not in st.session_state.classificacoes:
                    match = df_agendados[df_agendados['Ped_Limpo_Agend'] == pid]
                    if not match.empty:
                        nova_dt = match.iloc[0]['Data_Agend_DT']
                        if pd.notnull(nova_dt):
                            df_venda.at[idx, 'DATA_ENTREGA'] = nova_dt
                            dif_h = (nova_dt - row['DATA_EMISSAO']).total_seconds() / 3600
                            sla_f = "Dentro 48h" if (0 <= dif_h <= 48) else "Fora do Prazo"
                            
                            reg = {'Pedido': pid, 'Status_Auditoria': 'AGENDADO MANUALMENTE', 'SLA_Final': sla_f, 
                                   'Data_Inserida': nova_dt.strftime('%Y-%m-%d'), 'Filial': row['Filial'], 'Vendedor': row['Vendedor']}
                            st.session_state.classificacoes[pid] = reg
                            pd.DataFrame([reg]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))

    # Cálculo Final de SLA para o Dash
    mask = df_venda['DATA_ENTREGA'].notnull() & df_venda['DATA_EMISSAO'].notnull()
    df_venda['SLA_48H'] = "Pendente"
    horas = (df_venda.loc[mask, 'DATA_ENTREGA'] - df_venda.loc[mask, 'DATA_EMISSAO']).dt.total_seconds() / 3600
    df_venda.loc[mask, 'SLA_48H'] = horas.apply(lambda x: "Dentro 48h" if (0 <= x <= 48) else "Fora do Prazo")
    
    return df_venda

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ King Star: Auditoria & Performance")

    if 'base_mestra' not in st.session_state: st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state: st.session_state.classificacoes = {}

    # Carregar histórico físico
    if os.path.exists('historico_auditoria.csv') and not st.session_state.classificacoes:
        try:
            h_df = pd.read_csv('historico_auditoria.csv')
            for _, r in h_df.iterrows():
                st.session_state.classificacoes[str(r['Pedido'])] = r.to_dict()
        except: pass

    tabs = st.tabs(["📊 Performance", "🔍 Esteira de Auditoria", "📋 Relatório", "⚙️ Configurações"])
    df = st.session_state.base_mestra

    # --- TAB 1: PERFORMANCE (DASHES ANTIGOS) ---
    with tabs[0]:
        if not df.empty:
            df_u = df.drop_duplicates(subset=['Pedido_Limpo'])
            st.subheader("📊 Resumo Executivo")
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{len(df_u)}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>Tickets Auditados</p><p class='metric-value'>{len(st.session_state.classificacoes)}</p></div>", unsafe_allow_html=True)
            
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)]
            sla_ok = len(df_003[df_003['SLA_48H'] == "Dentro 48h"])
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>SLA 48h (003)</p><p class='metric-value'>{sla_ok}</p></div>", unsafe_allow_html=True)
            
            st.plotly_chart(px.pie(df_u, names='TIPO_VENDA', title="Mix de Vendas (Tipo)", hole=0.4), use_container_width=True)
        else:
            st.info("Suba as bases na aba Configurações.")

    # --- TAB 2: AUDITORIA (VISUAL BONITO) ---
    with tabs[1]:
        if not df.empty:
            pendentes = df[(df['TIPO_VENDA'].astype(str).str.contains('003')) & 
                           (df['DATA_ENTREGA'].isna()) & 
                           (~df['Pedido_Limpo'].isin(st.session_state.classificacoes.keys()))]
            
            st.subheader(f"🔍 Pendências para Auditoria Manual ({len(pendentes)})")
            
            for idx, row in pendentes.head(10).iterrows():
                pid = row['Pedido_Limpo']
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <div class='card-header'>FILIAL: {row['Filial']} | PEDIDO: {pid}</div>
                            <b>Cliente:</b> {row['Cliente_Limpo']}<br>
                            <b>Vendedor:</b> {row['Vendedor']}<br>
                            <span class='badge badge-red'>Sequência: {row['Seq_Pedido']}</span>
                            <span class='badge badge-blue'>Emissão: {row['DATA_EMISSAO'].strftime('%d/%m/%Y')}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    c_col1, c_col2 = st.columns([2,1])
                    motivo = c_col1.selectbox("Causa:", ["Não Analisado", "Pedido Correto", "Duplicado", "Erro de Digitação"], key=f"m_{pid}_{idx}")
                    
                    if motivo != "Não Analisado":
                        dt_manual = c_col2.date_input("Data Entrega:", key=f"d_{pid}_{idx}")
                        if st.button(f"Confirmar {pid}", key=f"b_{pid}_{idx}"):
                            dt_dt = pd.to_datetime(dt_manual)
                            dif_h = (dt_dt - row['DATA_EMISSAO']).total_seconds() / 3600
                            sla_f = "Dentro 48h" if (0 <= dif_h <= 48) else "Fora do Prazo"
                            
                            reg = {'Pedido': pid, 'Status_Auditoria': motivo, 'SLA_Final': sla_f, 
                                   'Data_Inserida': dt_dt.strftime('%Y-%m-%d'), 'Filial': row['Filial'], 'Vendedor': row['Vendedor']}
                            st.session_state.classificacoes[pid] = reg
                            pd.DataFrame([reg]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                            st.rerun()

    # --- TAB 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            res_df = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index(drop=True)
            st.dataframe(res_df, use_container_width=True)
            st.download_button("📥 Baixar Planilha de Auditoria", res_df.to_csv(index=False).encode('utf-8'), "auditoria_king.csv")

    # --- TAB 4: CONFIGURAÇÕES (UPLOAD E RESET) ---
    with tabs[3]:
        st.subheader("⚙️ Configurações de Dados")
        col1, col2 = st.columns(2)
        v_file = col1.file_uploader("1. Base Venda", type=['csv', 'xlsx'])
        a_file = col2.file_uploader("2. Relatório Agendados (Robô)", type=['csv', 'xlsx'])
        
        if st.button("🚀 PROCESSAR E CONFRONTAR"):
            if v_file:
                df_v = pd.read_csv(v_file, encoding='latin1', sep=None, engine='python') if v_file.name.endswith('.csv') else pd.read_excel(v_file)
                df_a = None
                if a_file:
                    df_a = pd.read_csv(a_file, encoding='latin1', sep=None, engine='python') if a_file.name.endswith('.csv') else pd.read_excel(a_file)
                
                st.session_state.base_mestra = processar_bases(df_v, df_a)
                st.success("Dados processados com sucesso!")
                st.rerun()
        
        st.divider()
        if st.button("🔥 RESETAR TUDO"):
            st.session_state.base_mestra = pd.DataFrame()
            st.session_state.classificacoes = {}
            if os.path.exists('historico_auditoria.csv'):
                os.remove('historico_auditoria.csv')
            st.rerun()

if __name__ == "__main__":
    main()
