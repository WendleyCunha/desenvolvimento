import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# =========================================================
# 1. ESTILO E CORES (PADRÃO KING STAR)
# =========================================================
PALETA = ['#002366', '#ef4444', '#16a34a', '#3b82f6']

def aplicar_estilo():
    st.markdown(f"""
        <style>
        .metric-card {{ background: #f8fafc; padding: 20px; border-radius: 15px; border-top: 5px solid {PALETA[0]}; text-align: center; }}
        .esteira-card {{ background: white; padding: 20px; border-radius: 15px; border: 1px solid #e2e8f0; margin-bottom: 10px; box-shadow: 2px 2px 10px rgba(0,0,0,0.05); }}
        .badge-retrabalho {{ background: #fee2e2; color: #ef4444; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 12px; }}
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. PROCESSAMENTO DE DADOS
# =========================================================
def tratar_dados(df):
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    
    # Tratamento de Datas e Tipos
    for col in ['Dt Emissão', 'Data Entrega']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    if 'Valor Venda' in df.columns:
        df['Valor Venda'] = pd.to_numeric(df['Valor Venda'].astype(str).str.replace(r'[R\$\.\s]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0)
    
    # Identificação de Re-trabalho (Seq > 1)
    if 'Cliente' in df.columns and 'Dt Emissão' in df.columns:
        df = df.sort_values(['Cliente', 'Dt Emissão'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    
    return df

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Manutenção e Eficiência Operacional")

    # Upload e Persistência
    with st.sidebar:
        st.header("Configurações")
        arquivo = st.file_uploader("Subir Base King Star", type=['csv', 'xlsx'])
        if arquivo:
            df_raw = pd.read_csv(arquivo) if arquivo.name.endswith('.csv') else pd.read_excel(arquivo)
            st.session_state.base_mestra = tratar_dados(df_raw)
            st.success("Base Carregada!")

    if 'base_mestra' in st.session_state:
        df = st.session_state.base_mestra
        
        # --- PONTO 3: CÁLCULO DE EFICIÊNCIA ---
        # Filtramos apenas os tipos desejados
        df_tipos = df[df['Tipo Venda'].astype(str).str.contains('002|003|004', na=False)].copy()
        
        # Base 100% (003 + 004)
        df_100 = df_tipos[df_tipos['Tipo Venda'].astype(str).str.contains('003|004', na=False)]
        total_100 = len(df_100)
        
        # Pedidos com Ineficiência (Seq > 1 dentro da base 100%)
        re_trabalho_100 = df_100[df_100['Seq_Pedido'] > 1]
        qtd_retrabalho = len(re_trabalho_100)
        taxa_erro = (qtd_retrabalho / total_100 * 100) if total_100 > 0 else 0

        # --- DASHBOARDS ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"<div class='metric-card'>TOTAL (003+004)<h3>{total_100}</h3></div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='metric-card'>RE-TRABALHO<h3>{qtd_retrabalho}</h3></div>", unsafe_allow_html=True)
        with col3:
            color = "#ef4444" if taxa_erro > 5 else "#16a34a"
            st.markdown(f"<div class='metric-card'>TAXA INEFICIENTE<h3 style='color:{color}'>{taxa_erro:.1f}%</h3></div>", unsafe_allow_html=True)
        with col4:
            val_total = re_trabalho_100['Valor Venda'].sum()
            st.markdown(f"<div class='metric-card'>PERDA ESTIMADA<h3>R$ {val_total:,.0f}</h3></div>", unsafe_allow_html=True)

        tab_dash, tab_esteira = st.tabs(["📊 Dashboards de Performance", "🔍 Esteira de Apuração"])

        with tab_dash:
            c1, c2 = st.columns(2)
            with c1:
                # --- PONTO 1: GRÁFICO DE PIZZA ---
                tipo_counts = df_tipos['Tipo Venda'].value_counts().reset_index()
                fig_pizza = px.pie(tipo_counts, values='count', names='Tipo Venda', 
                                 title="Mix de Vendas (002, 003, 004)",
                                 hole=0.4, color_discrete_sequence=PALETA)
                st.plotly_chart(fig_pizza, use_container_width=True)
            
            with c2:
                # Eficiência por Vendedor
                vend_retrabalho = re_trabalho_100['Vendedor'].value_counts().head(10).reset_index()
                fig_bar = px.bar(vend_retrabalho, x='Vendedor', y='count', 
                               title="Top 10 Vendedores (Re-trabalho)",
                               color_discrete_sequence=[PALETA[1]])
                st.plotly_chart(fig_bar, use_container_width=True)

        with tab_esteira:
            # --- PONTO 2: ESTEIRA COM BUSCA ---
            st.markdown("### 🔍 Busca Rápida")
            q = st.text_input("Localizar por N° Pedido ou ID Cliente", placeholder="Digite aqui...").upper()
            
            df_view = df_tipos.copy()
            if q:
                df_view = df_view[df_view['Pedido'].astype(str).str.contains(q) | 
                                 df_view['Cliente'].astype(str).str.contains(q)]
            
            # Mostra apenas re-trabalho ou todos? Filtro rápido
            so_retrabalho = st.toggle("Mostrar apenas Re-trabalho", value=True)
            if so_retrabalho:
                df_view = df_view[df_view['Seq_Pedido'] > 1]

            st.write(f"Exibindo {len(df_view)} registros:")
            
            for _, row in df_view.head(50).iterrows(): # Limitado a 50 para performance
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <div style='display: flex; justify-content: space-between;'>
                                <b>Pedido: {row['Pedido']}</b>
                                {"<span class='badge-retrabalho'>RE-TRABALHO</span>" if row['Seq_Pedido'] > 1 else ""}
                            </div>
                            <small>Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']}</small><br>
                            <small>Tipo: {row['Tipo Venda']} | Valor: R$ {row['Valor Venda']:,.2f} | Emissão: {row['Dt Emissão'].strftime('%d/%m/%Y') if pd.notnull(row['Dt Emissão']) else 'N/A'}</small>
                        </div>
                    """, unsafe_allow_html=True)
                    if row['Seq_Pedido'] > 1:
                        st.text_area("Notas de Auditoria", key=f"note_{row['Pedido']}", placeholder="Por que este pedido foi gerado novamente?")
    else:
        st.info("Aguardando upload da base oficial para gerar a esteira de eficiência.")

if __name__ == "__main__":
    main()
