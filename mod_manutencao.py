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
        .badge-green { background: #dcfce7; color: #166534; }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. PROCESSAMENTO DE DADOS (BLINDADO)
# =========================================================
def tratar_dados_oficial(df):
    if df.empty:
        return df
    
    # Limpeza de nomes de colunas (Remove espaços e caracteres especiais do Protheus)
    df.columns = [str(col).strip() for col in df.columns]
    
    # Mapeamento de colunas para nomes padrão
    mapeamento = {
        'Dt EmissÃ£o': 'DATA_EMISSAO',
        'Dt Emissão': 'DATA_EMISSAO',
        'Data Ent': 'DATA_ENTREGA',
        'Tipo Venda': 'TIPO_VENDA',
        'Valor Venda': 'VALOR'
    }
    df = df.rename(columns=mapeamento)
    
    # Conversão de Datas
    for col in ['DATA_EMISSAO', 'DATA_ENTREGA']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('/ /', np.nan), errors='coerce')
    
    # Criação da coluna de Mês para limpeza posterior
    if 'DATA_EMISSAO' in df.columns:
        df['MES_REF'] = df['DATA_EMISSAO'].dt.strftime('%m/%Y')

    # Identificação de Re-trabalho (Seq_Pedido)
    if 'Cliente' in df.columns and 'DATA_EMISSAO' in df.columns:
        df = df.sort_values(['Cliente', 'DATA_EMISSAO'])
        df['Seq_Pedido'] = df.groupby('Cliente').cumcount() + 1
    else:
        df['Seq_Pedido'] = 1
        
    # Cálculo de SLA 48h - CRIANDO A COLUNA ANTES DE QUALQUER FILTRO
    df['SLA_48H'] = "Pendente"
    if 'DATA_EMISSAO' in df.columns and 'DATA_ENTREGA' in df.columns:
        mask = df['DATA_ENTREGA'].notnull() & df['DATA_EMISSAO'].notnull()
        if mask.any():
            horas = (df.loc[mask, 'DATA_ENTREGA'] - df.loc[mask, 'DATA_EMISSAO']).dt.total_seconds() / 3600
            df.loc[mask, 'SLA_48H'] = horas.apply(lambda x: "Dentro 48h" if (0 <= x <= 48) else "Fora do Prazo")
        
    return df

# =========================================================
# 3. NÚCLEO DO MÓDULO
# =========================================================
def main():
    aplicar_estilo()
    
    # Perfil de acesso (Pode ser integrado ao seu sistema de login)
    user_role = st.session_state.get("perfil", "ADM") 
    
    st.title("🏗️ Manutenção e Eficiência King Star")

    # Inicialização do Banco de Dados Virtual (Session State)
    if 'base_mestra' not in st.session_state:
        st.session_state.base_mestra = pd.DataFrame()
    if 'classificacoes' not in st.session_state:
        st.session_state.classificacoes = {}

    # Configuração das Abas
    titulos = ["📊 Performance", "🔍 Auditoria", "📋 Relatório"]
    if user_role == "ADM":
        titulos.append("⚙️ Configurações")
    
    tabs = st.tabs(titulos)

    # --- ABA 1: PERFORMANCE ---
    with tabs[0]:
        df = st.session_state.base_mestra
        if not df.empty:
            # Filtro fixo de Regra de Negócio
            df_entregas = df[df['TIPO_VENDA'].astype(str).str.contains('003|004', na=False)].copy()
            
            c1, c2, c3 = st.columns(3)
            total = len(df_entregas)
            # Verificação de segurança para evitar KeyError
            col_sla = 'SLA_48H' if 'SLA_48H' in df_entregas.columns else None
            
            qtd_48h = len(df_entregas[df_entregas[col_sla] == "Dentro 48h"]) if col_sla else 0
            retrabalhos = len(df_entregas[df_entregas['Seq_Pedido'] > 1])
            
            c1.markdown(f"<div class='metric-card'>TOTAL ENTREGAS<h3>{total}</h3></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'>RE-TRABALHOS<h3>{retrabalhos}</h3></div>", unsafe_allow_html=True)
            agilidade = (qtd_48h / total * 100) if total > 0 else 0
            c3.markdown(f"<div class='metric-card'>EFICIÊNCIA 48H<h3>{agilidade:.1f}%</h3></div>", unsafe_allow_html=True)

            if not df_entregas.empty:
                st.plotly_chart(px.bar(
                    df_entregas[df_entregas['Seq_Pedido'] > 1]['Filial'].value_counts().head(10).reset_index(),
                    x='Filial', y='count', title="Top 10 Filiais com Mais Re-trabalho",
                    color_discrete_sequence=['#002366']
                ), use_container_width=True)
        else:
            st.info("💡 Nenhum dado carregado. Use a aba de Configurações para subir arquivos.")

    # --- ABA 2: AUDITORIA (CORREÇÃO DUPLICATE KEY) ---
    with tabs[1]:
        df = st.session_state.base_mestra
        if not df.empty:
            # Mostra apenas clientes com mais de 1 pedido (re-trabalho)
            df_audit = df[df['Seq_Pedido'] > 1].copy()
            st.subheader(f"🔍 Casos Identificados: {len(df_audit)}")
            
            # Para evitar erro de duplicidade, usamos o INDEX da linha na chave
            for idx, row in df_audit.head(40).iterrows():
                pedido_id = str(row['Pedido'])
                # CHAVE ÚNICA: Pedido + Index da Linha
                key_widget = f"causa_{pedido_id}_{idx}"
                
                with st.container():
                    st.markdown(f"""
                        <div class='esteira-card'>
                            <b>Filial: {row['Filial']} | Pedido: {pedido_id}</b><br>
                            Cliente: {row['Cliente']} | Vendedor: {row['Vendedor']}<br>
                            <span class='badge badge-red'>Seq: {row['Seq_Pedido']}</span>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    opcoes = ["Não Analisado", "Pedido correto", "Pedido duplicado", "Alteração de pedido", "Correção de pedido"]
                    # Recupera status anterior se existir
                    atual = st.session_state.classificacoes.get(pedido_id, {}).get('status', "Não Analisado")
                    
                    sel = st.selectbox("Classificar causa do erro:", opcoes, index=opcoes.index(atual), key=key_widget)
                    if sel != "Não Analisado":
                        st.session_state.classificacoes[pedido_id] = {
                            'status': sel, 'Filial': row['Filial'], 'Cliente': row['Cliente']
                        }
                    st.divider()
        else:
            st.info("Aguardando base de dados.")

    # --- ABA 3: RELATÓRIO ---
    with tabs[2]:
        if st.session_state.classificacoes:
            resumo = pd.DataFrame.from_dict(st.session_state.classificacoes, orient='index').reset_index()
            resumo.columns = ['Pedido', 'Motivo', 'Filial', 'Cliente']
            st.subheader("📋 Auditoria Finalizada")
            st.dataframe(resumo, use_container_width=True)
            st.download_button("Baixar CSV Auditoria", resumo.to_csv(index=False).encode('utf-8'), "auditoria_kingstar.csv")
        else:
            st.info("Nenhum pedido classificado na esteira de auditoria.")

    # --- ABA 4: CONFIGURAÇÕES (ADM ONLY) ---
    if user_role == "ADM":
        with tabs[3]:
            st.header("⚙️ Gerenciamento do Sistema")
            
            # Upload
            st.subheader("📥 Upload de Dados")
            upload = st.file_uploader("Adicionar novos dados (CSV ou XLSX)", type=['csv', 'xlsx'])
            if upload:
                try:
                    df_new = pd.read_csv(upload, encoding='latin1', sep=None, engine='python') if upload.name.endswith('.csv') else pd.read_excel(upload)
                    df_tratado = tratar_dados_oficial(df_new)
                    # Concatena com o que já existe
                    st.session_state.base_mestra = pd.concat([st.session_state.base_mestra, df_tratado]).drop_duplicates()
                    st.success("Dados carregados e integrados com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao processar: {e}")

            st.divider()

            # Limpeza Mensal
            st.subheader("📅 Limpeza por Mês")
            if not st.session_state.base_mestra.empty:
                meses = st.session_state.base_mestra['MES_REF'].dropna().unique()
                mes_del = st.selectbox("Selecione o mês para excluir da base:", meses)
                if st.button(f"🗑️ Excluir dados de {mes_del}"):
                    st.session_state.base_mestra = st.session_state.base_mestra[st.session_state.base_mestra['MES_REF'] != mes_del]
                    st.success(f"Dados de {mes_sel} apagados!")
                    st.rerun()

            st.divider()

            # Reset Total
            st.subheader("🚨 Zona de Perigo")
            if st.button("🔥 RESETAR TODO O SISTEMA"):
                st.session_state.base_mestra = pd.DataFrame()
                st.session_state.classificacoes = {}
                st.warning("O sistema foi limpo completamente.")
                st.rerun()

if __name__ == "__main__":
    main()
