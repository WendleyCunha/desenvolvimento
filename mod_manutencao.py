import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

# =========================================================
# 1. ESTILO E CONFIGURAÇÃO
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
# 2. TRATAMENTO DE DADOS
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
    
    if 'Cliente' in df.columns and 'DATA_EMISSAO' in df.columns:
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
def main(user_role="ADM"): # Recebe o perfil do main.py
    aplicar_estilo()
    st.title("🏗️ Manutenção e Eficiência King Star")

    # Inicialização do Banco de Dados Virtual
    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    # Definição das Abas
    abas = ["📊 Performance", "🔍 Auditoria", "📋 Relatório"]
    if user_role == "ADM":
        abas.append("⚙️ Configurações")
    
    tabs = st.tabs(abas)

    # --- ABA 1: PERFORMANCE ---
    with tabs[0]:
        df = st.session_state.base_mestra
        if not df.empty:
            df_entregas = df[df['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)]
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Entregas", len(df_entregas))
            c2.metric("Re-trabalhos", len(df_entregas[df_entregas['Seq_Pedido'] > 1]))
            
            agil = (len(df_entregas[df_entregas['SLA_48H'] == "Dentro 48h"]) / len(df_entregas) * 100) if len(df_entregas) > 0 else 0
            c3.metric("Agilidade 48h", f"{agil:.1f}%")

            # Top Filial (Ajuste solicitado: Coluna A)
            top_f = df_entregas[df_entregas['Seq_Pedido'] > 1]['Filial'].value_counts().head(10).reset_index()
            st.plotly_chart(px.bar(top_f, x='Filial', y='count', title="Top 10 Filiais (Re-trabalho)"), use_container_width=True)
        else:
            st.warning("Nenhum dado carregado. Vá em Configurações.")

    # --- ABA 2: AUDITORIA (CORREÇÃO DO ERRO DE CHAVE DUPLICADA) ---
    with tabs[1]:
        df = st.session_state.base_mestra
        if not df.empty:
            df_audit = df[df['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)]
            df_audit = df_audit[df_audit['Seq_Pedido'] > 1]
            
            for idx, row in df_audit.head(30).iterrows():
                # CHAVE ÚNICA: Combinamos o Pedido com o índice da linha para evitar erro de duplicidade
                chave_unica = f"{row['Pedido']}_{idx}"
                
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <b>Filial: {row['Filial']} | Pedido: {row['Pedido']}</b><br>
                            Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    # Busca classificação anterior pelo Pedido (não pela chave única, para manter consistência)
                    atual = st.session_state.classificacoes.get(str(row['Pedido']), {}).get('status', "Não Analisado")
                    
                    sel = st.selectbox("Causa:", opcoes, index=opcoes.index(atual), key=f"sel_{chave_unica}")
                    if sel != "Não Analisado":
                        st.session_state.classificacoes[str(row['Pedido'])] = {'status': sel, 'Filial': row['Filial']}

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
            st.dataframe(resumo, use_container_width=True)
        else:
            st.info("Nenhuma auditoria pendente.")

    # --- ABA 4: CONFIGURAÇÕES (RESTRITA ADM) ---
    if user_role == "ADM":
        with tabs[3]:
            st.header("⚙️ Painel de Controle ADM")
            
            # 1. Upload
            st.subheader("📥 Upload de Dados")
            arquivo = st.file_uploader("Adicionar novos dados à base", type=['csv', 'xlsx'])
            if arquivo:
                df_new = pd.read_csv(arquivo, encoding='latin1', sep=None, engine='python') if arquivo.name.endswith('.csv') else pd.read_excel(arquivo)
                df_tratado = tratar_dados_oficial(df_new)
                # Acumula na base existente
                st.session_state.base_mestra = pd.concat([st.session_state.base_mestra, df_tratado]).drop_duplicates(subset=['Pedido', 'Cliente', 'Produto'])
                st.success("Dados integrados com sucesso!")

            st.divider()
            
            # 2. Limpeza por Mês
            st.subheader("📅 Limpeza por Período")
            if not st.session_state.base_mestra.empty:
                df_temp = st.session_state.base_mestra.copy()
                df_temp['Mes_Ano'] = df_temp['DATA_EMISSAO'].dt.strftime('%m/%Y')
                meses = df_temp['Mes_Ano'].unique()
                mes_para_limpar = st.selectbox("Selecione o mês para excluir:", meses)
                
                if st.button(f"🗑️ Limpar dados de {mes_para_limpar}"):
                    st.session_state.base_mestra = df_temp[df_temp['Mes_Ano'] != mes_para_limpar].drop(columns=['Mes_Ano'])
                    st.success(f"Dados de {mes_para_limpar} removidos!")
                    st.rerun()

            st.divider()

            # 3. Reset Total
            st.subheader("🚨 Zona de Perigo")
            if st.button("🔥 RESETAR SISTEMA INTEIRO"):
                st.session_state.base_mestra = pd.DataFrame()
                st.session_state.classificacoes = {}
                st.warning("Todos os dados e auditorias foram apagados.")
                st.rerun()

if __name__ == "__main__":
    # Simulação de role, no seu main.py você passa o user_role real
    main(user_role="ADM")
