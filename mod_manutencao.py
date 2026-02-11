import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

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
        'Tipo Venda': 'TIPO_VENDA', 'Valor Venda': 'VALOR'
    }
    df = df.rename(columns=mapeamento)
    
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # Coluna de Mês para ADM
    if 'DATA_EMISSAO' in df.columns:
        df['MES_REF'] = df['DATA_EMISSAO'].dt.strftime('%m/%Y')
    else:
        df['MES_REF'] = "Indefinido"

    # Sequência de Pedidos por Cliente
    if 'Cliente' in df.columns:
        df = df.sort_values(['Cliente', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    
    # SLA 48h
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

    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    abas_lista = ["📊 Performance", "🔍 Auditoria", "📋 Relatório"]
    if user_role == "ADM": abas_lista.append("⚙️ Configurações")
    tabs = st.tabs(abas_lista)

    df = st.session_state.base_mestra

    # --- ABA 1: PERFORMANCE (OS 6 INDICADORES) ---
    with tabs[0]:
        if not df.empty:
            df_u = df.drop_duplicates(subset=['Pedido'])
            
            # Linha 1: Gerais
            st.subheader("📊 Visão Geral")
            c1, c2, c3 = st.columns(3)
            total_pedidos = len(df_u)
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{total_pedidos}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>Total Clientes</p><p class='metric-value'>{df['Cliente'].nunique()}</p></div>", unsafe_allow_html=True)
            
            auditoria_universo = len(df_u[df_u['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)])
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>Auditoria (003+004)</p><p class='metric-value'>{auditoria_universo}</p></div>", unsafe_allow_html=True)

            # Linha 2: Mix de Vendas
            st.plotly_chart(px.pie(df_u, names='TIPO_VENDA', title="Mix de Vendas (%): 002, 003, 004", hole=0.4), use_container_width=True)

            # Linha 3: Específicos 003 SLA
            st.divider()
            st.subheader("🕒 SLA de Entregas (Apenas 003)")
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)].copy()
            total_003 = df_003['Pedido'].nunique()
            
            if total_003 > 0:
                m1, m2 = st.columns(2)
                d48 = df_003[df_003['SLA_48H'] == "Dentro 48h"]['Pedido'].nunique()
                a48 = df_003[df_003['SLA_48H'] == "Fora do Prazo"]['Pedido'].nunique()
                
                m1.markdown(f"<div class='metric-card'><p class='metric-label'>003: Nasceram p/ 48h</p><p class='metric-value'>{d48}</p><p style='color:green; font-size:12px;'>{(d48/total_003*100):.1f}%</p></div>", unsafe_allow_html=True)
                m2.markdown(f"<div class='metric-card'><p class='metric-label'>003: Nasceram Acima 48h</p><p class='metric-value'>{a48}</p><p style='color:red; font-size:12px;'>{(a48/total_003*100):.1f}%</p></div>", unsafe_allow_html=True)
        else:
            st.info("Suba a base nas configurações para visualizar o dashboard.")

    # --- ABA 2: AUDITORIA (DETALHADA: FILIAL, PEDIDO, VENDEDOR, CLIENTE) ---
    with tabs[1]:
        if not df.empty:
            # Filtros: Apenas 003 | Seq > 1 ou Sem Data Entrega
            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)
            crit_cliente = (df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())
            
            view = df[crit_venda & crit_cliente].copy()
            # Remove já classificados para sumir da tela
            view = view[~view['Pedido'].astype(str).isin(st.session_state.classificacoes.keys())]

            st.subheader(f"🔍 Esteira de Auditoria: {len(view)} pendentes")
            
            for idx, row in view.head(20).iterrows():
                pid = str(row['Pedido'])
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <div class='card-header'>FILIAL: {row['Filial']} | PEDIDO: {pid}</div>
                            <b>Vendedor:</b> {row['Vendedor']}<br>
                            <b>Cliente:</b> {row['Cliente']}<br>
                            <span class='badge badge-red'>Seq: {row['Seq_Pedido']}</span>
                            <span class='badge badge-blue'>Entrega: {row['DATA_ENTREGA'] if pd.notnull(row['DATA_ENTREGA']) else 'PENDENTE'}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    sel = st.selectbox("Classificar causa:", opcoes, key=f"sel_{pid}_{idx}")
                    
                    if sel != "Não Analisado":
                        # Se "Pedido correto", vira "Pedido Perfeito" no relatório
                        st.session_state.classificacoes[pid] = {
                            'Status_Auditoria': "Pedido Perfeito" if sel == "Pedido correto" else sel,
                            'Filial': row['Filial'],
                            'Vendedor': row['Vendedor'],
                            'Cliente': row['Cliente'],
                            'Data_Original': row['DATA_ENTREGA']
                        }
                        st.rerun() 
        else:
            st.info("Aguardando base de dados.")

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index().rename(columns={'index': 'Pedido'})
            st.subheader("📋 Pedidos Auditados")
            st.dataframe(resumo, use_container_width=True)
            st.download_button("📥 Exportar Relatório", resumo.to_csv(index=False).encode('utf-8'), "auditoria_kingstar.csv")
        else:
            st.info("Nenhum pedido auditado ainda.")

    # --- ABA 4: CONFIGURAÇÕES (ADM) ---
    if user_role == "ADM":
        with tabs[3]:
            st.header("⚙️ Configurações ADM")
            arq = st.file_uploader("Upload de Base (CSV/XLSX)", type=['csv', 'xlsx'])
            if arq:
                df_raw = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
                st.session_state.base_mestra = tratar_dados_oficial(df_raw)
                st.success("Base carregada com sucesso!")
                st.rerun()

            if not df.empty:
                st.divider()
                meses = df['MES_REF'].unique()
                mes_sel = st.selectbox("Selecione o mês para excluir:", meses)
                if st.button("Limpar Mês"):
                    st.session_state.base_mestra = df[df['MES_REF'] != mes_sel]
                    st.rerun()

            if st.button("🔥 RESETAR TUDO (Base e Auditoria)"):
                st.session_state.base_mestra = pd.DataFrame()
                st.session_state.classificacoes = {}
                st.rerun()

if __name__ == "__main__":
    main()
