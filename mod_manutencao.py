import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# =========================================================
# 1. ESTILO E CONFIGURAÇÃO DE CORES
# =========================================================
PALETA_KING = ['#002366', '#ef4444', '#16a34a', '#3b82f6', '#f59e0b']

def aplicar_estilo_premium():
    st.markdown(f"""
        <style>
        .metric-card {{ background: #f8fafc; padding: 20px; border-radius: 15px; border-top: 5px solid {PALETA_KING[0]}; text-align: center; }}
        .esteira-card {{ background: white; padding: 20px; border-radius: 15px; border: 1px solid #e2e8f0; margin-bottom: 12px; box-shadow: 2px 2px 8px rgba(0,0,0,0.05); }}
        .badge-retrabalho {{ background: #fee2e2; color: #ef4444; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 12px; }}
        .badge-002 {{ background: #e0f2fe; color: #0369a1; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 12px; }}
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE TRATAMENTO DE DADOS
# =========================================================
def tratar_base_oficial(df):
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    
    # Tratamento de Datas
    for col in ['Dt Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # Identificação de Re-trabalho (Seq_Pedido)
    if 'Cliente' in df.columns and 'Dt Emissão' in df.columns:
        df = df.sort_values(['Cliente', 'Dt Emissão'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    
    return df

# =========================================================
# 3. INTERFACE E DASHBOARDS
# =========================================================
def main():
    aplicar_estilo_premium()
    st.title("🏗️ Manutenção e Eficiência Operacional")

    if 'base_mestra' not in st.session_state:
        st.sidebar.warning("Aguardando upload no menu lateral.")
        # Simulação para desenvolvimento ou sidebar de upload
        with st.sidebar:
            arquivo = st.file_uploader("Upload Base Protheus", type=['csv', 'xlsx'])
            if arquivo:
                df_raw = pd.read_csv(arquivo) if arquivo.name.endswith('.csv') else pd.read_excel(arquivo)
                st.session_state.base_mestra = tratar_base_oficial(df_raw)
                st.rerun()

    if 'base_mestra' in st.session_state:
        df = st.session_state.base_mestra
        
        # --- SEGMENTAÇÃO DAS BASES ---
        # Base Eficiência (Apenas 003 e 004)
        df_eficiencia = df[df['Tipo Venda'].astype(str).str.contains('003|004', na=False)].copy()
        # Base Retirada (Apenas 002)
        df_retira = df[df['Tipo Venda'].astype(str).str.contains('002', na=False)].copy()
        
        # Cálculos de KPI
        total_entregas = len(df_eficiencia)
        retrabalho_entregas = df_eficiencia[df_eficiencia['Seq_Pedido'] > 1]
        qtd_retrabalho = len(retrabalho_entregas)
        taxa_erro = (qtd_retrabalho / total_entregas * 100) if total_entregas > 0 else 0

        # --- HEADLINE METRICS ---
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"<div class='metric-card'>TOTAL ENTREGAS (003+004)<h3>{total_entregas}</h3></div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='metric-card'>CASOS RE-TRABALHO<h3>{qtd_retrabalho}</h3></div>", unsafe_allow_html=True)
        with c3:
            color = "#ef4444" if taxa_erro > 5 else "#16a34a"
            st.markdown(f"<div class='metric-card'>% INEFICIÊNCIA<h3 style='color:{color}'>{taxa_erro:.1f}%</h3></div>", unsafe_allow_html=True)

        tab_dash, tab_esteira = st.tabs(["📊 Performance por Filial", "🔍 Esteira de Apuração"])

        with tab_dash:
            # --- LINHA 1: MIX E TOP FILIAIS ---
            col_mix, col_filial = st.columns(2)
            
            with col_mix:
                # Mix de Vendas (Sem o 002)
                mix_counts = df_eficiencia['Tipo Venda'].value_counts().reset_index()
                fig_mix = px.pie(mix_counts, values='count', names='Tipo Venda', 
                                title="Mix de Vendas (003 vs 004)",
                                hole=0.4, color_discrete_sequence=[PALETA_KING[0], PALETA_KING[3]])
                st.plotly_chart(fig_mix, use_container_width=True)
            
            with col_filial:
                # TOP 10 FILIAL (Ponto 2)
                filial_retrabalho = retrabalho_entregas['Filial'].value_counts().head(10).reset_index()
                fig_filial = px.bar(filial_retrabalho, x='Filial', y='count', 
                                   title="Top 10 Filiais com Re-trabalho",
                                   color_discrete_sequence=[PALETA_KING[1]])
                st.plotly_chart(fig_filial, use_container_width=True)

            # --- LINHA 2: DASHBOARD EXCLUSIVO 002 (Ponto 3) ---
            st.divider()
            st.subheader("📦 Fluxo de Retirada (Tipo 002)")
            r1, r2 = st.columns([1, 2])
            with r1:
                st.markdown(f"<div class='metric-card' style='border-top-color:{PALETA_KING[3]}'>TOTAL 002 (RETIRA)<h3>{len(df_retira)}</h3></div>", unsafe_allow_html=True)
            with r2:
                retira_filial = df_retira['Filial'].value_counts().head(5).reset_index()
                fig_retira = px.bar(retira_filial, x='count', y='Filial', orientation='h',
                                   title="Top 5 Filiais - Volume de Retirada",
                                   color_discrete_sequence=[PALETA_KING[3]])
                st.plotly_chart(fig_retira, use_container_width=True)

        with tab_esteira:
            # --- ESTEIRA COM BUSCA ---
            st.markdown("### 🔍 Busca na Esteira")
            q = st.text_input("Filtrar por Pedido ou Cliente:", placeholder="Ex: 651253 ou 173XVS").upper()
            
            # Filtro de visualização na esteira
            df_view = df_eficiencia.copy()
            if q:
                df_view = df_view[df_view['Pedido'].astype(str).str.contains(q) | 
                                 df_view['Cliente'].astype(str).str.contains(q)]
            
            st.write(f"Mostrando {len(df_view.head(20))} pedidos recentes de entregas:")
            
            for _, row in df_view.head(20).iterrows():
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <div style='display: flex; justify-content: space-between;'>
                                <b>Filial: {row['Filial']} | Pedido: {row['Pedido']}</b>
                                {"<span class='badge-retrabalho'>RE-TRABALHO</span>" if row['Seq_Pedido'] > 1 else ""}
                            </div>
                            <small>Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']}</small><br>
                            <small>Tipo: {row['Tipo Venda']} | Emissão: {row['Dt Emissão'].strftime('%d/%m/%Y') if pd.notnull(row['Dt Emissão']) else 'N/A'}</small>
                        </div>
                    """, unsafe_allow_html=True)

    else:
        st.info("Suba a planilha no menu lateral para carregar os Dashboards.")

if __name__ == "__main__":
    main()
