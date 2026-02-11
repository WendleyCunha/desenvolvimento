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
        .metric-card {{ background: #f8fafc; padding: 20px; border-radius: 15px; border-top: 5px solid {PALETA[0]}; text-align: center; margin-bottom: 10px; }}
        .esteira-card {{ background: white; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 8px; box-shadow: 2px 2px 5px rgba(0,0,0,0.03); }}
        .badge-retrabalho {{ background: #fee2e2; color: #ef4444; padding: 3px 10px; border-radius: 15px; font-weight: bold; font-size: 11px; }}
        .badge-sla {{ background: #dcfce7; color: #166534; padding: 3px 10px; border-radius: 15px; font-weight: bold; font-size: 11px; }}
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE TRATAMENTO (NORMALIZAÇÃO AUTOMÁTICA)
# =========================================================
def tratar_dados_v5(df):
    if df.empty: return df
    
    # Normaliza nomes de colunas: remove espaços, acentos e padroniza
    df.columns = [
        str(col).strip().upper()
        .replace('Ã', 'A').replace('Õ', 'O').replace('Ç', 'C')
        .replace('Ê', 'E').replace('É', 'E').replace(' ', '_')
        for col in df.columns
    ]

    # Mapeamento de colunas cruciais (Baseado no seu log/planilha)
    # Procuramos os nomes normalizados: DT_EMISSAO, DATA_ENT, CLIENTE, PEDIDO, TIPO_VENDA
    
    # Datas
    col_emissao = 'DT_EMISSAO' if 'DT_EMISSAO' in df.columns else 'DT_EMISS_O'
    col_entrega = 'DATA_ENT' if 'DATA_ENT' in df.columns else 'DATA_ENTREGA'
    
    for col in [col_emissao, col_entrega]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')

    # Identificação de Re-trabalho (Seq > 1)
    if 'CLIENTE' in df.columns and col_emissao in df.columns:
        df = df.sort_values(['CLIENTE', col_emissao])
        df['SEQ_PEDIDO'] = df.groupby('CLIENTE').cumcount() + 1
    else:
        df['SEQ_PEDIDO'] = 1

    # Lógica SLA 48h
    if col_emissao in df.columns and col_entrega in df.columns:
        df['HORAS_ENTREGA'] = (df[col_entrega] - df[col_emissao]).dt.total_seconds() / 3600
        df['SLA_48H'] = df['HORAS_ENTREGA'].apply(
            lambda x: "Dentro 48h" if (pd.notnull(x) and x <= 48) 
            else ("Atrasado" if (pd.notnull(x) and x > 48) else "Pendente")
        )
    
    return df, col_emissao

# =========================================================
# 3. INTERFACE
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Gestão de Eficiência King Star")

    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    with st.sidebar:
        st.header("⚙️ Configurações")
        arquivo = st.file_uploader("Subir Base King Star (CSV ou Excel)", type=['csv', 'xlsx'])
        if arquivo:
            try:
                df_raw = pd.read_csv(arquivo) if arquivo.name.endswith('.csv') else pd.read_excel(arquivo)
                df_processado, col_data = tratar_dados_v5(df_raw)
                st.session_state.base_mestra = df_processado
                st.session_state.col_data = col_data
                st.success("Base carregada!")
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")

    if 'base_mestra' in st.session_state:
        df = st.session_state.base_mestra
        col_data = st.session_state.col_data
        
        # Filtros de Segmentação
        df_entregas = df[df['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)].copy()
        df_retira = df[df['TIPO_VENDA'].astype(str).str.contains('002', na=False)].copy()
        
        tab_geral, tab_esteira, tab_audit = st.tabs(["📊 Performance", "🔍 Esteira Auditoria", "📋 Relatório"])

        with tab_geral:
            c1, c2, c3 = st.columns(3)
            total = len(df_entregas)
            retrabalho_df = df_entregas[df_entregas['SEQ_PEDIDO'] > 1]
            
            c1.markdown(f"<div class='metric-card'>TOTAL ENTREGAS<h3>{total}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'>RE-TRABALHOS<h3>{len(retrabalho_df)}</h3></div>", unsafe_allow_html=True)
            
            # KPI 48H
            dentro_48 = len(df_entregas[df_entregas.get('SLA_48H') == "Dentro 48h"])
            perc = (dentro_48/total*100) if total > 0 else 0
            c3.markdown(f"<div class='metric-card'>AGILIDADE 48H<h3>{perc:.1f}%</h3></div>", unsafe_allow_html=True)

            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(px.pie(df_entregas, names='TIPO_VENDA', title="Mix 003 vs 004", hole=0.4, color_discrete_sequence=PALETA), use_container_width=True)
            with g2:
                # Top Filiais com Re-trabalho
                filiais = retrabalho_df['FILIAL'].value_counts().head(10).reset_index()
                st.plotly_chart(px.bar(filiais, x='FILIAL', y='count', title="Top 10 Filiais (Re-trabalho)", color_discrete_sequence=[PALETA[1]]), use_container_width=True)

        with tab_esteira:
            st.markdown("### 🔍 Auditoria de Pedidos")
            q = st.text_input("Filtrar por Pedido ou Cliente").upper()
            
            view = df_entregas.copy()
            if q:
                view = view[view['PEDIDO'].astype(str).str.contains(q) | view['CLIENTE'].astype(str).str.contains(q)]
            
            # Mostrar apenas casos de atenção por padrão
            so_retrabalho = st.checkbox("Mostrar apenas Re-trabalhos", value=True)
            if so_retrabalho:
                view = view[view['SEQ_PEDIDO'] > 1]

            for _, row in view.head(20).iterrows():
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <b>{row['FILIAL']} | Pedido: {row['PEDIDO']}</b><br>
                            <small>Cliente: {row['CLIENTE']} | Vendedor: {row['VENDEDOR']}</small><br>
                            {"<span class='badge-retrabalho'>RE-TRABALHO</span>" if row['SEQ_PEDIDO'] > 1 else ""}
                            {"<span class='badge-sla'>48H OK</span>" if row.get('SLA_48H') == 'Dentro 48h' else ""}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    c_sel, c_obs = st.columns([1, 2])
                    chave = str(row['PEDIDO'])
                    
                    status_atual = st.session_state.classificacoes.get(chave, {}).get('status', 'Não Analisado')
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    
                    novo_status = c_sel.selectbox("Motivo:", opcoes, index=opcoes.index(status_atual), key=f"s_{chave}")
                    nova_obs = c_obs.text_input("Observação:", value=st.session_state.classificacoes.get(chave, {}).get('obs', ''), key=f"o_{chave}")
                    
                    # Salva se houver alteração
                    st.session_state.classificacoes[chave] = {
                        'status': novo_status, 'obs': nova_obs, 'filial': row['FILIAL'], 'cliente': row['CLIENTE']
                    }

        with tab_audit:
            st.subheader("📋 Relatório Final de Auditoria")
            if st.session_state.classificacoes:
                resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
                resumo = resumo[resumo['status'] != 'Não Analisado']
                if not resumo.empty:
                    st.plotly_chart(px.bar(resumo['status'].value_counts().reset_index(), x='status', y='count', title="Causas Identificadas"), use_container_width=True)
                    st.dataframe(resumo, use_container_width=True)
                    st.download_button("Baixar Relatório CSV", resumo.to_csv(index=False).encode('utf-8'), "auditoria_kingstar.csv")
                else:
                    st.info("Nenhum pedido foi classificado ainda.")

if __name__ == "__main__":
    main()
