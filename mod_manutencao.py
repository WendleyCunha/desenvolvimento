import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import timedelta

# =========================================================
# 1. CONFIGURAÇÕES E ESTILO
# =========================================================
PALETA = ['#002366', '#ef4444', '#16a34a', '#3b82f6', '#facc15']

def aplicar_estilo():
    st.markdown(f"""
        <style>
        .metric-card {{ background: #f8fafc; padding: 20px; border-radius: 15px; border-top: 5px solid {PALETA[0]}; text-align: center; }}
        .esteira-card {{ background: white; padding: 20px; border-radius: 15px; border: 1px solid #e2e8f0; margin-bottom: 10px; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); }}
        .badge-retrabalho {{ background: #fee2e2; color: #ef4444; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 12px; }}
        .badge-sla {{ background: #dcfce7; color: #166534; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 12px; }}
        .badge-atraso {{ background: #fef9c3; color: #854d0e; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 12px; }}
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. PROCESSAMENTO DE DADOS (COM LÓGICA DE 48H)
# =========================================================
def tratar_dados_v4(df):
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    
    # Datas
    for col in ['Dt Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # Identificação de Re-trabalho (Cliente com mais de 1 pedido)
    if 'Cliente' in df.columns and 'Dt Emissão' in df.columns:
        df = df.sort_values(['Cliente', 'Dt Emissão'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    
    # Lógica SLA 48h (Emissão até Entrega)
    if 'Dt Emissão' in df.columns and 'Data Entrega' in df.columns:
        # Calcula diferença em horas. Se não entregue, fica NaN
        df['Horas_Entrega'] = (df['Data Entrega'] - df['Dt Emissão']).dt.total_seconds() / 3600
        df['SLA_48H'] = df['Horas_Entrega'].apply(lambda x: "Dentro 48h" if x <= 48 else ("Atrasado" if x > 48 else "Pendente"))
        
    return df

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Gestão de Eficiência King Star")

    # Sidebar para Upload
    with st.sidebar:
        st.header("⚙️ Configurações")
        arquivo = st.file_uploader("Subir Base King Star", type=['csv', 'xlsx'])
        if arquivo:
            df_raw = pd.read_csv(arquivo) if arquivo.name.endswith('.csv') else pd.read_excel(arquivo)
            st.session_state.base_mestra = tratar_dados_v4(df_raw)
            # Inicializa dicionário de classificações se não existir
            if 'classificacoes' not in st.session_state:
                st.session_state.classificacoes = {}
            st.success("Base Carregada!")

    if 'base_mestra' in st.session_state:
        df = st.session_state.base_mestra
        
        # Filtros de Segmentação
        df_entregas = df[df['Tipo Venda'].astype(str).str.contains('003|004', na=False)].copy()
        df_retira = df[df['Tipo Venda'].astype(str).str.contains('002', na=False)].copy()
        
        # --- DASHBOARDS ---
        tab_geral, tab_esteira, tab_analise_audit = st.tabs(["📊 Performance Geral", "🔍 Esteira de Auditoria", "📋 Relatório de Classificação"])

        with tab_geral:
            # KPIS Principais
            c1, c2, c3, c4 = st.columns(4)
            total_100 = len(df_entregas)
            casos_retrabalho = len(df_entregas[df_entregas['Seq_Pedido'] > 1])
            dentro_48h = len(df_entregas[df_entregas['SLA_48H'] == "Dentro 48h"])
            perc_agilidade = (dentro_48h / total_100 * 100) if total_100 > 0 else 0

            c1.markdown(f"<div class='metric-card'>TOTAL (003+004)<h3>{total_100}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'>RE-TRABALHO<h3>{casos_retrabalho}</h3></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'>AGILIDADE 48H<h3>{perc_agilidade:.1f}%</h3></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='metric-card'>TOTAL 002<h3>{len(df_retira)}</h3></div>", unsafe_allow_html=True)

            st.divider()
            
            # Gráficos
            g1, g2 = st.columns(2)
            with g1:
                # Pizza do Mix (Conforme solicitado, mantendo o 002 isolado se quiser, ou junto)
                fig_mix = px.pie(df[df['Tipo Venda'].astype(str).str.contains('002|003|004')], 
                               names='Tipo Venda', title="Mix Total de Vendas", hole=0.4,
                               color_discrete_sequence=PALETA)
                st.plotly_chart(fig_mix, use_container_width=True)
            
            with g2:
                # Dashboard SLA 48h (Ponto 3)
                sla_counts = df_entregas['SLA_48H'].value_counts().reset_index()
                fig_sla = px.bar(sla_counts, x='SLA_48H', y='count', 
                                title="Eficiência de Entrega (Janela 48h)",
                                color='SLA_48H', color_discrete_map={"Dentro 48h": "#16a34a", "Atrasado": "#ef4444", "Pendente": "#cbd5e1"})
                st.plotly_chart(fig_sla, use_container_width=True)

            # TOP FILIAL
            st.subheader("Ineficiência por Filial")
            filiais = df_entregas[df_entregas['Seq_Pedido'] > 1]['Filial'].value_counts().reset_index()
            st.plotly_chart(px.bar(filiais, x='Filial', y='count', color_discrete_sequence=[PALETA[1]]), use_container_width=True)

        with tab_esteira:
            # --- PONTO 2: ESTEIRA COM CLASSIFICAÇÃO ---
            st.markdown("### 🔍 Esteira de Apuração de Re-trabalho")
            
            col_search, col_filter = st.columns([2, 1])
            q = col_search.text_input("Localizar Pedido ou Cliente", placeholder="Digite aqui...").upper()
            filtro_audit = col_filter.selectbox("Filtrar por Status", ["Todos", "Apenas Re-trabalho", "Pendente Auditoria"])
            
            df_esteira = df_entregas.copy()
            if q:
                df_esteira = df_esteira[df_esteira['Pedido'].astype(str).str.contains(q) | df_esteira['Cliente'].astype(str).str.contains(q)]
            
            if filtro_audit == "Apenas Re-trabalho":
                df_esteira = df_esteira[df_esteira['Seq_Pedido'] > 1]
            
            for i, row in df_esteira.head(30).iterrows():
                with st.container():
                    # Definição de Badges
                    badge_retrabalho = f"<span class='badge-retrabalho'>RE-TRABALHO (Seq: {row['Seq_Pedido']})</span>" if row['Seq_Pedido'] > 1 else ""
                    badge_sla = f"<span class='badge-sla'>48H OK</span>" if row['SLA_48H'] == "Dentro 48h" else (f"<span class='badge-atraso'>SLA ROMPIDO</span>" if row['SLA_48H'] == "Atrasado" else "")
                    
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <div style='display: flex; justify-content: space-between;'>
                                <b>{row['Filial']} | Pedido: {row['Pedido']}</b>
                                <div>{badge_retrabalho} {badge_sla}</div>
                            </div>
                            <small>Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']} | Tipo: {row['Tipo Venda']}</small>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # SISTEMA DE CLASSIFICAÇÃO (Ponto 2)
                    col_class, col_obs = st.columns([1, 2])
                    
                    # Recupera valor anterior se existir
                    current_val = st.session_state.classificacoes.get(row['Pedido'], {}).get('status', 'Não Analisado')
                    
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    idx_op = opcoes.index(current_val) if current_val in opcoes else 0
                    
                    status = col_class.selectbox("Classificação:", opcoes, index=idx_op, key=f"sel_{row['Pedido']}")
                    obs = col_obs.text_input("Observação interna:", value=st.session_state.classificacoes.get(row['Pedido'], {}).get('obs', ''), key=f"obs_{row['Pedido']}")
                    
                    # Salva no estado
                    st.session_state.classificacoes[row['Pedido']] = {
                        'status': status,
                        'obs': obs,
                        'Filial': row['Filial'],
                        'Cliente': row['Cliente'],
                        'Valor': row['Valor Venda']
                    }
                    st.divider()

        with tab_analise_audit:
            # --- ABA DE DASHBOARD DE AUDITORIA ---
            st.subheader("📊 Resultados da Auditoria")
            
            if st.session_state.classificacoes:
                df_audit = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
                df_audit.rename(columns={'index': 'Pedido'}, inplace=True)
                
                # Gráfico de Classificações
                df_audit_counts = df_audit[df_audit['status'] != 'Não Analisado']
                if not df_audit_counts.empty:
                    c1, c2 = st.columns(2)
                    with c1:
                        fig_audit = px.bar(df_audit_counts['status'].value_counts().reset_index(), 
                                         x='status', y='count', title="Causas de Re-trabalho",
                                         color_discrete_sequence=[PALETA[3]])
                        st.plotly_chart(fig_audit, use_container_width=True)
                    with c2:
                        st.write("📋 Tabela para Relatório")
                        st.dataframe(df_audit_counts, use_container_width=True)
                        
                        # Botão de Relatório
                        csv = df_audit_counts.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("📥 Baixar Relatório de Auditoria", csv, "relatorio_auditoria_kingstar.csv", "text/csv")
                else:
                    st.info("Classifique os pedidos na Esteira para gerar o gráfico de causas.")
            else:
                st.info("Nenhuma auditoria realizada ainda.")

if __name__ == "__main__":
    main()
