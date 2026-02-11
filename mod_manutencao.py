import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# =========================================================
# 1. ESTILO KING STAR
# =========================================================
def aplicar_estilo():
    st.markdown("""
        <style>
        .metric-card { background: #f8fafc; padding: 15px; border-radius: 10px; border-top: 4px solid #002366; text-align: center; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-green { background: #dcfce7; color: #166534; }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE TRATAMENTO BLINDADO
# =========================================================
def tratar_dados_oficial(df):
    if df.empty: return df
    
    # Limpeza de nomes de colunas (Remove espaços e caracteres zoados do Excel/CSV)
    df.columns = [str(col).strip() for col in df.columns]
    
    # Dicionário de Tradução (Garante que o código ache as colunas mesmo com erro de acento)
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA',
        'Valor Venda': 'VALOR'
    }
    df = df.rename(columns=mapeamento)
    
    # Converter Datas
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # Identificar Re-trabalho (Cliente com mais de um pedido)
    if 'Cliente' in df.columns and 'DATA_EMISSAO' in df.columns:
        df = df.sort_values(['Cliente', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    else:
        df['Seq_Pedido'] = 1
        
    # SLA 48h
    if 'DATA_EMISSAO' in df.columns and 'DATA_ENTREGA' in df.columns:
        df['Horas_Entrega'] = (df['DATA_ENTREGA'] - df['DATA_EMISSAO']).dt.total_seconds() / 3600
        df['SLA_48H'] = df['Horas_Entrega'].apply(lambda x: "Dentro 48h" if (x <= 48 and x >= 0) else "Fora do Prazo")
        
    return df

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    st.title("🏗️ Manutenção e Eficiência")

    # Inicialização de estados
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    with st.sidebar:
        st.header("Upload de Dados")
        arquivo = st.file_uploader("Arraste o arquivo aqui", type=['csv', 'xlsx'])
        if arquivo:
            try:
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                st.session_state.base_mestra = tratar_dados_oficial(df_raw)
                st.success("Dados carregados com sucesso!")
            except Exception as e:
                st.error(f"Erro na leitura: {e}")

    if 'base_mestra' in st.session_state:
        df = st.session_state.base_mestra
        
        # Filtros de Regra de Negócio (Separação 003+004 vs 002)
        df_entregas = df[df['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)].copy()
        df_002 = df[df['TIPO_VENDA'].astype(str).str.contains('002', na=False)].copy()

        tab1, tab2, tab3 = st.tabs(["📊 Performance", "🔍 Esteira de Auditoria", "📋 Relatórios"])

        with tab1:
            # KPIS
            c1, c2, c3 = st.columns(3)
            total = len(df_entregas)
            retrabalhos = len(df_entregas[df_entregas['Seq_Pedido'] > 1])
            agilidade = (len(df_entregas[df_entregas['SLA_48H'] == "Dentro 48h"]) / total * 100) if total > 0 else 0
            
            c1.markdown(f"<div class='metric-card'>TOTAL ENTREGAS (003+004)<h3>{total}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'>RE-TRABALHOS<h3>{retrabalhos}</h3></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'>EFICIÊNCIA 48H<h3>{agilidade:.1f}%</h3></div>", unsafe_allow_html=True)

            # Gráficos
            col_a, col_b = st.columns(2)
            with col_a:
                st.plotly_chart(px.pie(df_entregas, names='TIPO_VENDA', title="Mix Entregas", hole=0.4), use_container_width=True)
            with col_b:
                top_filiais = df_entregas[df_entregas['Seq_Pedido'] > 1]['Filial'].value_counts().head(10).reset_index()
                st.plotly_chart(px.bar(top_filiais, x='Filial', y='count', title="Top 10 Filiais (Re-trabalho)"), use_container_width=True)

            st.divider()
            st.subheader("📦 Visão Exclusiva - Tipo 002 (Retirada)")
            st.write(f"Total de retiradas em loja: **{len(df_002)}**")

        with tab2:
            st.markdown("### 🔍 Auditoria por Cliente")
            q = st.text_input("Buscar por Nome do Cliente ou Pedido")
            
            view = df_entregas.copy()
            if q:
                view = view[view['Cliente'].astype(str).str.contains(q, case=False) | view['Pedido'].astype(str).str.contains(q)]
            
            # Filtro para focar no problema
            apenas_problema = st.toggle("Ver apenas clientes com mais de 1 pedido", value=True)
            if apenas_problema:
                view = view[view['Seq_Pedido'] > 1]

            for _, row in view.head(25).iterrows():
                with st.container():
                    pid = str(row['Pedido'])
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <b>Filial: {row['Filial']} | Pedido: {pid}</b><br>
                            Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']}<br>
                            <span class='badge badge-red'>RE-TRABALHO (Vez: {row['Seq_Pedido']})</span>
                            {"<span class='badge badge-green'>SLA 48H OK</span>" if row['SLA_48H'] == 'Dentro 48h' else ""}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Sistema de Classificação
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    atual = st.session_state.classificacoes.get(pid, {}).get('status', "Não Analisado")
                    
                    sel = st.selectbox(f"Classificar erro do pedido {pid}:", opcoes, index=opcoes.index(atual), key=f"sel_{pid}")
                    if sel != "Não Analisado":
                        st.session_state.classificacoes[pid] = {'status': sel, 'Filial': row['Filial'], 'Cliente': row['Cliente']}

        with tab3:
            st.subheader("📋 Relatório Final")
            if st.session_state.classificacoes:
                dados_audit = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
                st.dataframe(dados_audit, use_container_width=True)
                st.download_button("Baixar CSV", dados_audit.to_csv(index=False).encode('utf-8'), "auditoria.csv")
            else:
                st.info("Nenhuma auditoria realizada.")
    else:
        st.info("Aguardando upload da planilha no menu lateral.")

if __name__ == "__main__":
    main()
