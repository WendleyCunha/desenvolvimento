import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# =========================================================
# 1. ESTILO E PADRONIZAÇÃO
# =========================================================
def aplicar_estilo():
    st.markdown("""
        <style>
        .metric-card { background: #ffffff; padding: 20px; border-radius: 12px; border-left: 5px solid #002366; 
                       box-shadow: 2px 2px 10px rgba(0,0,0,0.1); text-align: center; margin-bottom: 10px; }
        .metric-value { font-size: 26px; font-weight: bold; color: #002366; margin: 0; }
        .metric-label { font-size: 13px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; margin-right: 5px; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-blue { background: #e0f2fe; color: #0369a1; }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE PROCESSAMENTO
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
    
    df['MES_REF'] = df['DATA_EMISSAO'].dt.strftime('%m/%Y') if 'DATA_EMISSAO' in df.columns else "Sem Data"

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
    st.title("🏗️ Gestão de Eficiência King Star")

    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    abas_titulos = ["📊 Performance", "🔍 Auditoria", "📋 Relatório"]
    if user_role == "ADM": abas_titulos.append("⚙️ Configurações")
    tabs = st.tabs(abas_titulos)

    # --- ABA 1: PERFORMANCE (Os 6 Dashboards solicitados) ---
    with tabs[0]:
        df = st.session_state.base_mestra
        if not df.empty:
            df_u = df.drop_duplicates(subset=['Pedido'])
            
            # Métricas Gerais
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-card'><p class='metric-label'>Total Pedidos</p><p class='metric-value'>{len(df_u)}</p></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><p class='metric-label'>Total Clientes</p><p class='metric-value'>{df['Cliente'].nunique()}</p></div>", unsafe_allow_html=True)
            
            auditoria_count = len(df_u[df_u['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)])
            c3.markdown(f"<div class='metric-card'><p class='metric-label'>Universo Auditoria (003+004)</p><p class='metric-value'>{auditoria_count}</p></div>", unsafe_allow_html=True)

            # Mix de Vendas (%)
            st.plotly_chart(px.pie(df_u, names='TIPO_VENDA', title="Mix de Pedidos: 003 vs 004 vs 002", hole=0.4), use_container_width=True)

            # Métricas Específicas 003
            st.subheader("🎯 Indicadores Exclusivos Tipo 003")
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)].copy()
            total_003 = df_003['Pedido'].nunique()
            
            m1, m2 = st.columns(2)
            d_48 = df_003[df_003['SLA_48H'] == "Dentro 48h"]['Pedido'].nunique()
            a_48 = df_003[df_003['SLA_48H'] == "Fora do Prazo"]['Pedido'].nunique()
            
            m1.markdown(f"<div class='metric-card'><p class='metric-label'>003: Dentro 48h</p><p class='metric-value'>{d_48}</p><p style='color:green'>{(d_48/total_003*100 if total_003>0 else 0):.1f}%</p></div>", unsafe_allow_html=True)
            m2.markdown(f"<div class='metric-card'><p class='metric-label'>003: Acima 48h</p><p class='metric-value'>{a_48}</p><p style='color:red'>{(a_48/total_003*100 if total_003>0 else 0):.1f}%</p></div>", unsafe_allow_html=True)
        else:
            st.info("Aguardando upload de dados.")

    # --- ABA 2: AUDITORIA (Lógica: Classificou -> Somo) ---
    with tabs[1]:
        df = st.session_state.base_mestra
        if not df.empty:
            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)
            crit_erro = (df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())
            view = df[crit_venda & crit_erro].copy()
            # Filtro para sumir da lista
            view = view[~view['Pedido'].astype(str).isin(st.session_state.classificacoes.keys())]

            st.subheader(f"Pedidos Pendentes: {len(view)}")
            for idx, row in view.head(10).iterrows():
                pid = str(row['Pedido'])
                with st.container():
                    st.markdown(f"<div class='esteira-card'><b>Pedido: {pid}</b> | Cliente: {row['Cliente']}<br>Filial: {row['Filial']}</div>", unsafe_allow_html=True)
                    sel = st.selectbox("Classificar causa:", ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido"], key=f"at_{pid}_{idx}")
                    if sel != "Não Analisado":
                        st.session_state.classificacoes[pid] = {'Status': "Pedido Perfeito" if sel == "Pedido correto" else sel, 'Filial': row['Filial'], 'Cliente': row['Cliente']}
                        st.rerun()

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            res_df = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index().rename(columns={'index': 'Pedido'})
            st.dataframe(res_df, use_container_width=True)
            st.download_button("Baixar CSV", res_df.to_csv(index=False).encode('utf-8'), "relatorio.csv")

    # --- ABA 4: CONFIGURAÇÕES ---
    if user_role == "ADM":
        with tabs[3]:
            st.header("⚙️ ADM")
            up = st.file_uploader("Nova Base", type=['csv', 'xlsx'])
            if up:
                df_raw = pd.read_csv(up, encoding='latin1', sep=None, engine='python') if up.name.endswith('.csv') else pd.read_excel(up)
                st.session_state.base_mestra = tratar_dados_oficial(df_raw)
                st.rerun()
            if st.button("🔥 RESET TOTAL"):
                st.session_state.base_mestra = pd.DataFrame(); st.session_state.classificacoes = {}; st.rerun()

if __name__ == "__main__":
    main()
