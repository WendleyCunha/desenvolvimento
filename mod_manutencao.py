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
# 2. MOTOR DE TRATAMENTO E SLA
# =========================================================
def tratar_dados_oficial(df):
    if df.empty: return df
    # Limpa nomes de colunas
    df.columns = [str(col).strip() for col in df.columns]
    
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO', 'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA', 'Data Entrega': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA', 'Valor Venda': 'VALOR',
        'Data Prevista': 'DATA_PREVISTA'
    }
    df = df.rename(columns=mapeamento)
    
    # Padroniza Pedido (remove aspas se houver)
    if 'Pedido' in df.columns:
        df['Pedido'] = df['Pedido'].astype(str).str.replace("'", "").str.strip()
    
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA', 'DATA_PREVISTA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace(['/ /', 'nan', 'NaT'], np.nan), errors='coerce')
    
    # Lógica de Sequência por Cliente
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
    if 'motivos_extra' not in st.session_state: st.session_state.motivos_extra = []

    # Carregar histórico físico do CSV
    if os.path.exists('historico_auditoria.csv') and not st.session_state.classificacoes:
        try:
            h_df = pd.read_csv('historico_auditoria.csv')
            for _, r in h_df.iterrows():
                st.session_state.classificacoes[str(r['Pedido'])] = r.to_dict()
        except: pass

    tabs = st.tabs(["📊 Performance", "🔍 Auditoria", "📋 Relatório", "⚙️ Configurações"])
    df = st.session_state.base_mestra

    # --- ABA 1: PERFORMANCE ---
    with tabs[0]:
        if not df.empty:
            df_u = df.drop_duplicates(subset=['Pedido'])
            st.subheader("📊 Visão Geral")
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{len(df_u)}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>Auditados</p><p class='metric-value'>{len(st.session_state.classificacoes)}</p></div>", unsafe_allow_html=True)
            
            # Cálculo de SLA em tempo real para o gráfico
            df['SLA_48H_REF'] = df.apply(lambda x: calcular_sla(x.get('DATA_EMISSAO'), x.get('DATA_ENTREGA')), axis=1)
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)]
            
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>SLA OK (003)</p><p class='metric-value'>{len(df_003[df_003['SLA_48H_REF'] == 'Dentro 48h'])}</p></div>", unsafe_allow_html=True)
            
            st.plotly_chart(px.pie(df_003, names='SLA_48H_REF', title="Status SLA 48h (Tipo 003)", hole=0.4), use_container_width=True)
        else:
            st.info("Suba a base nas configurações.")

   # --- ABA 2: AUDITORIA (Manual + Automática) ---
    with tabs[1]:
        if not df.empty:
            st.subheader("🚀 Auditoria Automática (PROCV)")
            with st.expander("Clique aqui para subir arquivo de Agendados e atualizar datas em massa"):
                arq_agend = st.file_uploader("Relatório de Agendados (Busca Coluna B e D)", type=['csv', 'xlsx'], key="auto_up")
                if arq_agend:
                    df_ag = pd.read_csv(arq_agend, encoding='latin1', sep=None, engine='python') if arq_agend.name.endswith('.csv') else pd.read_excel(arq_agend)
                    if st.button("Executar Cruzamento de Dados"):
                        df_ag.columns = [str(c).strip() for c in df_ag.columns]
                        col_p = 'Ped. Venda'
                        col_d = 'Previsão Ent.'
                        
                        if col_p in df_ag.columns and col_d in df_ag.columns:
                            df_ag[col_p] = df_ag[col_p].astype(str).str.replace("'", "").str.strip()
                            df_ag[col_d] = pd.to_datetime(df_ag[col_d], errors='coerce')
                            
                            sucessos = 0
                            for _, r_ag in df_ag.iterrows():
                                pid, nova_dt = r_ag[col_p], r_ag[col_d]
                                if pd.notnull(nova_dt) and pid not in st.session_state.classificacoes:
                                    mask = df['Pedido'] == pid
                                    if mask.any():
                                        dt_emi = df.loc[mask, 'DATA_EMISSAO'].iloc[0]
                                        sla = calcular_sla(dt_emi, nova_dt)
                                        df.loc[mask, 'DATA_ENTREGA'] = nova_dt
                                        reg = {
                                            'Pedido': pid, 'Status_Auditoria': 'AUTOMÁTICO', 
                                            'SLA_Final': sla, 'Data_Inserida': nova_dt.strftime('%Y-%m-%d'), 
                                            'Filial': df.loc[mask, 'Filial'].iloc[0], 
                                            'Vendedor': df.loc[mask, 'Vendedor'].iloc[0]
                                        }
                                        st.session_state.classificacoes[pid] = reg
                                        pd.DataFrame([reg]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                                        sucessos += 1
                            st.success(f"Pronto! {sucessos} pedidos atualizados automaticamente.")
                            st.rerun()

            st.divider()
            # Esteira Manual com Correção de Chaves Duplicadas
            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)
            crit_erro = (df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())
            view = df[crit_venda & crit_erro].copy()
            # Remove o que já foi auditado (seja automático ou manual)
            view = view[~view['Pedido'].isin(st.session_state.classificacoes.keys())]

            st.subheader(f"🔍 Pendências Manuais ({len(view)})")
            motivos = ["Não Analisado", "Pedido correto", "Pedido duplicado"] + st.session_state.motivos_extra

            for idx, row in view.head(10).iterrows():
                pid = str(row['Pedido'])
                # CHAVE ÚNICA: Combina o ID do pedido com o índice da linha para evitar erros
                chave_loop = f"{pid}_{idx}"
                
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <div class='card-header'>FILIAL: {row['Filial']} | PEDIDO: {pid}</div>
                            <b>Cliente:</b> {row.get('Cliente_Limpo', 'N/A')}<br>
                            <span class='badge badge-red'>Seq: {row['Seq_Pedido']}</span>
                            <span class='badge badge-blue'>Entrega: {row['DATA_ENTREGA'] if pd.notnull(row['DATA_ENTREGA']) else 'PENDENTE'}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    c_col1, c_col2 = st.columns([2,1])
                    # Aplicação das chaves exclusivas (chave_loop)
                    sel = c_col1.selectbox("Causa:", motivos, key=f"sel_{chave_loop}")
                    data_f = c_col2.date_input("Data Real:", key=f"dt_{chave_loop}") if sel != "Não Analisado" else None
                    
                    if sel != "Não Analisado" and st.button(f"Confirmar {pid}", key=f"btn_{chave_loop}"):
                        dt_dt = pd.to_datetime(data_f)
                        sla = calcular_sla(row['DATA_EMISSAO'], dt_dt)
                        reg = {
                            'Pedido': pid, 'Status_Auditoria': sel, 'SLA_Final': sla, 
                            'Data_Inserida': dt_dt.strftime('%Y-%m-%d'), 
                            'Filial': row['Filial'], 'Vendedor': row['Vendedor']
                        }
                        st.session_state.classificacoes[pid] = reg
                        pd.DataFrame([reg]).to_csv('historico_auditoria.csv', mode='a', index=False, header=not os.path.exists('historico_auditoria.csv'))
                        st.rerun()
        else:
            st.info("Aguardando base de dados.")

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index(drop=True)
            st.subheader("📋 Histórico Consolidado")
            st.dataframe(resumo, use_container_width=True)
            st.download_button("📥 Baixar Planilha", resumo.to_csv(index=False).encode('utf-8'), "auditoria_final.csv")

    # --- ABA 4: CONFIGURAÇÕES ---
    with tabs[3]:
        st.subheader("⚙️ Gestão de Dados")
        arq = st.file_uploader("Upload Base Venda", type=['csv', 'xlsx'])
        if arq:
            df_raw = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
            st.session_state.base_mestra = tratar_dados_oficial(df_raw)
            st.rerun()
        
        if st.button("🔥 RESETAR TUDO"):
            st.session_state.base_mestra = pd.DataFrame()
            st.session_state.classificacoes = {}
            if os.path.exists('historico_auditoria.csv'): os.remove('historico_auditoria.csv')
            st.rerun()

if __name__ == "__main__":
    main()
