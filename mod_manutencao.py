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
        .metric-card { background: #f8fafc; padding: 15px; border-radius: 10px; border-top: 4px solid #002366; text-align: center; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; margin-right: 5px; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-green { background: #dcfce7; color: #166534; }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. MOTOR DE TRATAMENTO
# =========================================================
def tratar_dados_oficial(df):
    if df.empty:
        return df
    
    # Limpa nomes das colunas de espaços extras
    df.columns = [str(col).strip() for col in df.columns]
    
    # Mapeamento para tratar encoding do Protheus
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA',
        'Valor Venda': 'VALOR'
    }
    df = df.rename(columns=mapeamento)
    
    # Converte Datas com segurança
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # Cálculo de Re-trabalho (Sequência de pedidos por cliente)
    if 'Cliente' in df.columns and 'DATA_EMISSAO' in df.columns:
        df = df.sort_values(['Cliente', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    else:
        df['Seq_Pedido'] = 1
    
    # Cálculo de SLA 48h
    df['SLA_48H'] = "Pendente"
    if 'DATA_EMISSAO' in df.columns and 'DATA_ENTREGA' in df.columns:
        mask = df['DATA_ENTREGA'].notnull() & df['DATA_EMISSAO'].notnull()
        if mask.any():
            horas = (df.loc[mask, 'DATA_ENTREGA'] - df.loc[mask, 'DATA_EMISSAO']).dt.total_seconds() / 3600
            df.loc[mask, 'SLA_48H'] = horas.apply(lambda x: "Dentro 48h" if (0 <= x <= 48) else "Fora do Prazo")
            
    return df

# =========================================================
# 3. INTERFACE PRINCIPAL
# =========================================================
def main():
    aplicar_estilo()
    
    # Simulação de Role (Certifique-se que no seu main.py você define st.session_state.user_role)
    user_role = st.session_state.get("user_role", "ADM")
    
    st.title("🏗️ Manutenção e Eficiência King Star")

    # Inicialização das variáveis de estado (Banco de dados virtual)
    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    # Definição das Abas (A aba Configurações só aparece para ADM)
    abas_nomes = ["📊 Performance", "🔍 Auditoria", "📋 Relatório"]
    if user_role == "ADM":
        abas_nomes.append("⚙️ Configurações")
    
    tabs = st.tabs(abas_nomes)

    # --- ABA 1: PERFORMANCE ---
    with tabs[0]:
        df = st.session_state.base_mestra
        if not df.empty:
            df_entregas = df[df['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)].copy()
            c1, c2, c3 = st.columns(3)
            
            total = len(df_entregas)
            retrabalhos = len(df_entregas[df_entregas['Seq_Pedido'] > 1])
            qtd_48h = len(df_entregas[df_entregas['SLA_48H'] == "Dentro 48h"])
            
            c1.markdown(f"<div class='metric-card'>TOTAL ENTREGAS<h3>{total}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'>RE-TRABALHOS<h3>{retrabalhos}</h3></div>", unsafe_allow_html=True)
            perc = (qtd_48h / total * 100) if total > 0 else 0
            c3.markdown(f"<div class='metric-card'>AGILIDADE 48H<h3>{perc:.1f}%</h3></div>", unsafe_allow_html=True)

            if not df_entregas.empty:
                top_f = df_entregas[df_entregas['Seq_Pedido'] > 1]['Filial'].value_counts().head(10).reset_index()
                st.plotly_chart(px.bar(top_f, x='Filial', y='count', title="Top 10 Filiais (Re-trabalho)", color_discrete_sequence=['#ef4444']), use_container_width=True)
        else:
            st.info("Aguardando upload de dados na aba Configurações.")

    # --- ABA 2: AUDITORIA (CORREÇÃO DE DUPLICIDADE) ---
    with tabs[1]:
        df = st.session_state.base_mestra
        if not df.empty:
            df_audit = df[df['Seq_Pedido'] > 1].copy()
            st.write(f"Exibindo {len(df_audit.head(20))} casos críticos:")
            
            for idx, row in df_audit.head(20).iterrows():
                # CHAVE ÚNICA: ID do Pedido + Índice da Linha para evitar o erro de DuplicateKey
                key_id = f"sel_{row['Pedido']}_{idx}"
                
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <b>Filial: {row['Filial']} | Pedido: {row['Pedido']}</b><br>
                            Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    atual = st.session_state.classificacoes.get(str(row['Pedido']), {}).get('status', "Não Analisado")
                    
                    sel = st.selectbox("Causa:", opcoes, index=opcoes.index(atual), key=key_id)
                    if sel != "Não Analisado":
                        st.session_state.classificacoes[str(row['Pedido'])] = {
                            'status': sel, 'Filial': row['Filial'], 'Cliente': row['Cliente']
                        }
                    st.divider()

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
            resumo.columns = ['Pedido', 'Causa', 'Filial', 'Cliente']
            st.dataframe(resumo, use_container_width=True)
            st.download_button("Baixar Relatório", resumo.to_csv(index=False).encode('utf-8'), "auditoria.csv")
        else:
            st.info("Nenhuma auditoria realizada.")

    # --- ABA 4: CONFIGURAÇÕES (ADM APENAS) ---
    if user_role == "ADM":
        with tabs[3]:
            st.header("⚙️ Painel ADM")
            
            # 1. Upload
            st.subheader("📥 Upload de Dados")
            arq = st.file_uploader("Subir base CSV/Excel", type=['csv', 'xlsx'])
            if arq:
                df_new = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
                df_proc = tratar_dados_oficial(df_new)
                st.session_state.base_mestra = pd.concat([st.session_state.base_mestra, df_proc]).drop_duplicates()
                st.success("Dados carregados!")

            st.divider()
            
            # 2. Limpeza por Mês
            st.subheader("📅 Limpar Base por Mês")
            if not st.session_state.base_mestra.empty:
                df_temp = st.session_state.base_mestra.copy()
                df_temp['Mes_Ano'] = df_temp['DATA_EMISSAO'].dt.strftime('%m/%Y')
                opcoes_mes = df_temp['Mes_Ano'].dropna().unique()
                mes_sel = st.selectbox("Selecione o mês para apagar:", opcoes_mes)
                
                if st.button(f"🗑️ Excluir {mes_sel}"):
                    st.session_state.base_mestra = df_temp[df_temp['Mes_Ano'] != mes_sel].drop(columns=['Mes_Ano'])
                    st.success(f"Mês {mes_sel} apagado.")
                    st.rerun()

            st.divider()

            # 3. Reset Total
            st.subheader("🚨 Reset")
            if st.button("🔥 LIMPAR TODO O SISTEMA"):
                st.session_state.base_mestra = pd.DataFrame()
                st.session_state.classificacoes = {}
                st.rerun()

if __name__ == "__main__":
    main()
