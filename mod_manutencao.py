import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

def aplicar_estilo():
    st.markdown("""
        <style>
        .metric-card { background: #f8fafc; padding: 15px; border-radius: 10px; border-top: 4px solid #002366; text-align: center; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; margin-right: 5px; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-green { background: #dcfce7; color: #166534; }
        .badge-blue { background: #e0f2fe; color: #0369a1; }
        </style>
    """, unsafe_allow_html=True)

def tratar_dados_oficial(df):
    if df.empty: return df
    
    # 1. Limpeza rigorosa de nomes de colunas
    df.columns = [str(col).strip() for col in df.columns]
    
    # 2. Mapeamento para suportar erros de acentuação do Protheus
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA',
        'Data Entrega': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA',
        'Valor Venda': 'VALOR'
    }
    df = df.rename(columns=mapeamento)
    
    # 3. Conversão de Datas
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # 4. Sequência de Pedidos (Re-trabalho)
    if 'Cliente' in df.columns and 'DATA_EMISSAO' in df.columns:
        df = df.sort_values(['Cliente', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    else:
        df['Seq_Pedido'] = 1
        
    # 5. Cálculo do SLA 48h (Criação Segura da Coluna)
    df['SLA_48H'] = "Pendente" # Valor padrão para evitar KeyError
    if 'DATA_EMISSAO' in df.columns and 'DATA_ENTREGA' in df.columns:
        # Calcula apenas onde tem data de entrega preenchida
        mask = df['DATA_ENTREGA'].notnull() & df['DATA_EMISSAO'].notnull()
        horas = (df.loc[mask, 'DATA_ENTREGA'] - df.loc[mask, 'DATA_EMISSAO']).dt.total_seconds() / 3600
        df.loc[mask, 'SLA_48H'] = horas.apply(lambda x: "Dentro 48h" if (0 <= x <= 48) else "Fora do Prazo")
        
    return df

def main():
    aplicar_estilo()
    st.title("🏗️ Manutenção e Eficiência King Star")

    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    with st.sidebar:
        st.header("Upload")
        arquivo = st.file_uploader("Subir base oficial", type=['csv', 'xlsx'])
        if arquivo:
            try:
                # Tenta ler com diferentes encodings para evitar erro de leitura
                if arquivo.name.endswith('.csv'):
                    df_raw = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python')
                else:
                    df_raw = pd.read_excel(arquivo)
                
                st.session_state.base_mestra = tratar_dados_oficial(df_raw)
                st.success("Dados carregados!")
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    if 'base_mestra' in st.session_state:
        df = st.session_state.base_mestra
        
        # Segmentação
        df_entregas = df[df['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)].copy()
        df_002 = df[df['TIPO_VENDA'].astype(str).str.contains('002', na=False)].copy()

        tab1, tab2, tab3 = st.tabs(["📊 Performance", "🔍 Auditoria", "📋 Relatório"])

        with tab1:
            c1, c2, c3 = st.columns(3)
            total = len(df_entregas)
            
            # Cálculo seguro para evitar erro caso a coluna SLA_48H esteja vazia
            qtd_48h = len(df_entregas[df_entregas['SLA_48H'] == "Dentro 48h"]) if 'SLA_48H' in df_entregas.columns else 0
            retrabalhos = len(df_entregas[df_entregas['Seq_Pedido'] > 1]) if 'Seq_Pedido' in df_entregas.columns else 0
            
            c1.markdown(f"<div class='metric-card'>TOTAL ENTREGAS (003+004)<h3>{total}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'>RE-TRABALHOS<h3>{retrabalhos}</h3></div>", unsafe_allow_html=True)
            
            perc_agilidade = (qtd_48h / total * 100) if total > 0 else 0
            c3.markdown(f"<div class='metric-card'>EFICIÊNCIA 48H<h3>{perc_agilidade:.1f}%</h3></div>", unsafe_allow_html=True)

            g1, g2 = st.columns(2)
            with g1:
                st.plotly_chart(px.pie(df_entregas, names='TIPO_VENDA', title="Mix Entregas", hole=0.4, color_discrete_sequence=['#002366', '#3b82f6']), use_container_width=True)
            with g2:
                # Top Filial (Ponto 2 solicitado)
                if not df_entregas.empty:
                    top_f = df_entregas[df_entregas['Seq_Pedido'] > 1]['Filial'].value_counts().head(10).reset_index()
                    st.plotly_chart(px.bar(top_f, x='Filial', y='count', title="Top 10 Filiais (Re-trabalho)", color_discrete_sequence=['#ef4444']), use_container_width=True)

            st.divider()
            st.subheader("📦 Visão Tipo 002 (Retirada)")
            st.info(f"Total de registros 002: {len(df_002)}")

        with tab2:
            st.markdown("### 🔍 Esteira de Auditoria")
            q = st.text_input("Localizar Cliente ou Pedido").upper()
            
            view = df_entregas.copy()
            if q:
                view = view[view['Cliente'].astype(str).str.contains(q) | view['Pedido'].astype(str).str.contains(q)]
            
            # Ponto 1: Mostrar casos onde o cliente aparece mais de uma vez
            view = view[view['Seq_Pedido'] > 1]
            
            st.write(f"Exibindo {len(view.head(30))} casos de re-trabalho:")

            for _, row in view.head(30).iterrows():
                pid = str(row['Pedido'])
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <b>Filial: {row['Filial']} | Pedido: {pid}</b><br>
                            Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']}<br>
                            <span class='badge badge-red'>RE-TRABALHO (Vez: {row['Seq_Pedido']})</span>
                            <span class='badge badge-blue'>Tipo: {row['TIPO_VENDA']}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Ponto 2: Opções de classificação
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    atual = st.session_state.classificacoes.get(pid, {}).get('status', "Não Analisado")
                    
                    sel = st.selectbox("Classificar causa:", opcoes, index=opcoes.index(atual), key=f"sel_{pid}")
                    if sel != "Não Analisado":
                        st.session_state.classificacoes[pid] = {
                            'status': sel, 'Filial': row['Filial'], 'Cliente': row['Cliente'], 'Vendedor': row['Vendedor']
                        }
                    st.divider()

        with tab3:
            st.subheader("📋 Relatório de Auditoria")
            if st.session_state.classificacoes:
                dados_audit = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
                dados_audit.rename(columns={'index': 'Pedido'}, inplace=True)
                
                c1, c2 = st.columns([1, 2])
                c1.plotly_chart(px.pie(dados_audit, names='status', title="Causas Detectadas"), use_container_width=True)
                c2.write("Detalhes da Auditoria:")
                c2.dataframe(dados_audit, use_container_width=True)
                
                csv = dados_audit.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Baixar Relatório", csv, "auditoria_kingstar.csv", "text/csv")
            else:
                st.info("Nenhum pedido classificado na esteira ainda.")

    else:
        st.info("Suba a planilha no menu lateral para começar.")

if __name__ == "__main__":
    main()
