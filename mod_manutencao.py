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
        .metric-card { background: #f8fafc; padding: 15px; border-radius: 10px; border-top: 4px solid #002366; text-align: center; }
        .esteira-card { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 10px; }
        .badge { padding: 4px 10px; border-radius: 15px; font-size: 11px; font-weight: bold; margin-right: 5px; }
        .badge-red { background: #fee2e2; color: #ef4444; }
        .badge-blue { background: #e0f2fe; color: #0369a1; }
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
    
    # Criar coluna de Mês para evitar KeyError nas configurações
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
    user_role = st.session_state.get("user_role", "ADM") 
    st.title("🏗️ Manutenção e Eficiência King Star")

    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    abas_lista = ["📊 Performance", "🔍 Auditoria", "📋 Relatório"]
    if user_role == "ADM": abas_lista.append("⚙️ Configurações")
    tabs = st.tabs(abas_lista)

    # --- ABA 1: PERFORMANCE ---
    with tabs[0]:
        df = st.session_state.base_mestra
        if not df.empty:
            # Filtro solicitado: Apenas 003
            df_003 = df[df['TIPO_VENDA'].astype(str).str.contains('003', na=False)].copy()
            
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div class='metric-card'>TOTAL ENTREGAS (003)<h3>{len(df_003)}</h3></div>", unsafe_allow_html=True)
            
            # Re-trabalhos classificados (Status inserido)
            auditados = len(st.session_state.classificacoes)
            c2.markdown(f"<div class='metric-card'>PEDIDOS AUDITADOS<h3>{auditados}</h3></div>", unsafe_allow_html=True)
            
            # Pizza retorna aqui
            if not df_003.empty:
                st.plotly_chart(px.pie(df_003, names='SLA_48H', title="Status de Entrega (SLA 48h)", hole=0.4, 
                                      color_discrete_sequence=['#002366', '#ef4444', '#cbd5e1']), use_container_width=True)
        else:
            st.info("Suba a base nas configurações.")

    # --- ABA 2: AUDITORIA (LÓGICA DE FILTRO DINÂMICO) ---
    with tabs[1]:
        df = st.session_state.base_mestra
        if not df.empty:
            # REGRAS SOLICITADAS: 
            # 1. Apenas 003
            # 2. Cliente com mais de um pedido OU sem data de entrega
            # 3. Que ainda NÃO foram classificados (para sumir da lista)
            
            crit_venda = df['TIPO_VENDA'].astype(str).str.contains('003', na=False)
            crit_cliente = (df['Seq_Pedido'] > 1) | (df['DATA_ENTREGA'].isna())
            
            view = df[crit_venda & crit_cliente].copy()
            
            # Filtra para REMOVER quem já foi classificado
            view = view[~view['Pedido'].astype(str).isin(st.session_state.classificacoes.keys())]

            st.subheader(f"Pedidos Pendentes de Análise: {len(view)}")
            
            for idx, row in view.head(20).iterrows():
                pid = str(row['Pedido'])
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <b>Filial: {row['Filial']} | Pedido: {pid}</b><br>
                            Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']}<br>
                            <span class='badge badge-red'>Seq: {row['Seq_Pedido']}</span>
                            <span class='badge badge-blue'>Entrega: {row['DATA_ENTREGA'] if pd.notnull(row['DATA_ENTREGA']) else 'NÃO ENTREGUE'}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    sel = st.selectbox("Classificar causa:", opcoes, key=f"sel_{pid}_{idx}")
                    
                    if sel != "Não Analisado":
                        st.session_state.classificacoes[pid] = {
                            'Status': sel, 'Filial': row['Filial'], 'Cliente': row['Cliente'], 
                            'Vendedor': row['Vendedor'], 'Data_Emissao': row['DATA_EMISSAO']
                        }
                        st.rerun() # Faz o pedido "sumir" imediatamente ao classificar

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
            resumo.rename(columns={'index': 'Pedido'}, inplace=True)
            st.dataframe(resumo, use_container_width=True)
            st.download_button("Exportar CSV", resumo.to_csv(index=False).encode('utf-8'), "relatorio_manutencao.csv")
        else:
            st.info("Nenhum pedido classificado ainda.")

    # --- ABA 4: CONFIGURAÇÕES (ADM) ---
    if user_role == "ADM":
        with tabs[3]:
            st.header("⚙️ Configurações de Sistema")
            
            # 1. Upload
            arq = st.file_uploader("Upload de Base", type=['csv', 'xlsx'])
            if arq:
                df_raw = pd.read_csv(arq, encoding='latin1', sep=None, engine='python') if arq.name.endswith('.csv') else pd.read_excel(arq)
                st.session_state.base_mestra = tratar_dados_oficial(df_raw)
                st.success("Dados carregados!")
                st.rerun()

            st.divider()
            # 2. Limpeza Mensal
            if not st.session_state.base_mestra.empty:
                meses = st.session_state.base_mestra['MES_REF'].unique()
                mes_sel = st.selectbox("Limpar mês específico:", meses)
                if st.button("Limpar Mês"):
                    st.session_state.base_mestra = st.session_state.base_mestra[st.session_state.base_mestra['MES_REF'] != mes_sel]
                    st.success(f"Mês {mes_sel} removido.")
                    st.rerun()

            # 3. Reset Total
            if st.button("🔥 RESETAR SISTEMA INTEIRO"):
                st.session_state.base_mestra = pd.DataFrame()
                st.session_state.classificacoes = {}
                st.rerun()

if __name__ == "__main__":
    main()
