import streamlit as st
import pandas as pd
import plotly.express as px
from database import inicializar_db

# --- CONFIGURAÇÃO FIREBASE ---
import streamlit as st
import pandas as pd
import plotly.express as px
from database import inicializar_db

# --- CONFIGURAÇÃO FIREBASE ---

def carregar_estoque_firebase():
    """Busca os dados no Firestore com tratamento de erros e integridade de chaves."""
    db = inicializar_db()
    if not db:
        return {"analises": [], "idx_atual": 0}
    try:
        doc = db.collection("config").document("operacao_armazem").get()
        if doc.exists:
            dados = doc.to_dict()
            # Garante que as chaves essenciais existam para não quebrar o código
            if "analises" not in dados: dados["analises"] = []
            if "idx_atual" not in dados: dados["idx_atual"] = 0
            return dados
        return {"analises": [], "idx_atual": 0}
    except Exception as e:
        st.error(f"Erro ao acessar Firebase: {e}")
        return {"analises": [], "idx_atual": 0}

def salvar_estoque_firebase(dados):
    """Salva o estado atual da operação no Firestore."""
    db = inicializar_db()
    if db:
        try:
            db.collection("config").document("operacao_armazem").set(dados)
        except Exception as e:
            st.error(f"Erro ao salvar no banco: {e}")

# --- INTERFACE PRINCIPAL ---

def exibir_estoque():
    db_data = carregar_estoque_firebase()
    
    # Estilização CSS para os Cards
    st.markdown("""
        <style>
            .metric-card {
                background: white; padding: 20px; border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-top: 4px solid #D4AF37;
                text-align: center; margin-bottom: 10px; color: #002366;
            }
            .metric-card h4 { margin: 0; color: #666; font-size: 0.9rem; }
            .metric-card h2 { margin: 10px 0 0 0; font-size: 1.8rem; }
        </style>
    """, unsafe_allow_html=True)

    # 1. ESTADO: Banco Vazio (Pede o Excel)
    if not db_data.get("analises") or len(db_data["analises"]) == 0:
        st.info("📦 **Armazém 41**: Aguardando carga de dados no Firebase.")
        arq = st.file_uploader("Subir Projeção Inicial (Excel)", type=["xlsx"], key="up_estoque_final")
        
        if arq:
            try:
                df_i = pd.read_excel(arq)
                # Padronização de Colunas
                df_i['SOLICITADO'] = df_i['QUANTIDADE'] if 'QUANTIDADE' in df_i.columns else 0
                
                cols_necessarias = ['STATUS', 'ANALISADO', 'QTD_COMPRADA', 'SALDO_VAL', 'STATUS_REC', 'QTD_RECEBIDA', 'CONFERIDO']
                for col in cols_necessarias:
                    if col not in df_i.columns:
                        df_i[col] = 0 if 'QTD' in col or 'VAL' in col else (False if col != 'STATUS_REC' else "Aguardando")
                
                df_i['STATUS'] = "Pendente"
                
                # Prepara o dicionário para o Firebase
                novo_db = {
                    "analises": df_i.to_dict(orient='records'),
                    "idx_atual": 0
                }
                salvar_estoque_firebase(novo_db)
                st.success("✅ Carga realizada com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao processar arquivo: {e}")
        return

    # 2. ESTADO: Com dados (Exibe Abas)
    df = pd.DataFrame(db_data["analises"])
    t_exec, t_dash, t_rel = st.tabs(["🚀 Execução", "📊 Dashboard", "📋 Relatório"])

    with t_exec:
        idx = int(db_data.get("idx_atual", 0))
        
        if idx < len(df):
            item = df.iloc[idx]
            st.subheader(f"Item {idx + 1} de {len(df)}")
            
            # Painel de Informação do Item
            st.warning(f"**Descrição:** {item.get('DESCRICAO', 'N/A')} | **Solicitado:** {item.get('SOLICITADO', 0)}")
            
            c1, c2, c3 = st.columns([1, 1, 1])
            
            with c1:
                saldo = st.number_input("Saldo em estoque:", min_value=0, key=f"input_sld_{idx}", help="Informe quanto foi encontrado fisicamente")
            
            with c2:
                st.write(" ") # Alinhamento
                if st.button("✅ COMPRA TOTAL", use_container_width=True):
                    df.at[idx, 'STATUS'] = "Compra Efetuada"
                    df.at[idx, 'QTD_COMPRADA'] = item['SOLICITADO']
                    df.at[idx, 'SALDO_VAL'] = saldo
                    df.at[idx, 'ANALISADO'] = True
                    db_data["idx_atual"] = idx + 1
                    db_data["analises"] = df.to_dict(orient='records')
                    salvar_estoque_firebase(db_data)
                    st.rerun()
            
            with c3:
                st.write(" ") # Alinhamento
                if st.button("🔍 SEM ENCOMENDA", use_container_width=True):
                    df.at[idx, 'STATUS'] = "Sem Encomenda"
                    df.at[idx, 'SALDO_VAL'] = saldo
                    df.at[idx, 'ANALISADO'] = True
                    db_data["idx_atual"] = idx + 1
                    db_data["analises"] = df.to_dict(orient='records')
                    salvar_estoque_firebase(db_data)
                    st.rerun()
        else:
            st.success("🎉 **Excelente!** Todas as análises deste lote foram concluídas.")
            if st.button("Reiniciar Processo (Voltar ao início)"):
                db_data["idx_atual"] = 0
                salvar_estoque_firebase(db_data)
                st.rerun()

    with t_dash:
        # Métricas de Performance
        m1, m2, m3 = st.columns(3)
        total_itens = len(df)
        analisados = len(df[df['ANALISADO'] == True])
        progresso = (analisados / total_itens)
        
        m1.markdown(f'<div class="metric-card"><h4>Total de Itens</h4><h2>{total_itens}</h2></div>', unsafe_allow_html=True)
        m2.markdown(f'<div class="metric-card"><h4>Analisados</h4><h2>{analisados}</h2></div>', unsafe_allow_html=True)
        m3.markdown(f'<div class="metric-card"><h4>Pendentes</h4><h2>{total_itens - analisados}</h2></div>', unsafe_allow_html=True)
        
        st.progress(progresso, text=f"Progresso da Operação: {int(progresso*100)}%")
        
        if analisados > 0:
            fig = px.pie(df, names='STATUS', title="Status das Tomadas de Decisão", hole=0.4, 
                         color_discrete_map={'Compra Efetuada':'#2ECC71', 'Sem Encomenda':'#E74C3C', 'Pendente':'#BDC3C7'})
            st.plotly_chart(fig, use_container_width=True)

    with t_rel:
        st.markdown("### 📋 Resumo da Projeção")
        # Filtro rápido
        mostrar_apenas = st.multiselect("Filtrar por Status:", options=df['STATUS'].unique(), default=df['STATUS'].unique())
        df_filt = df[df['STATUS'].isin(mostrar_apenas)]
        
        st.dataframe(df_filt[['CODIGO', 'DESCRICAO', 'SOLICITADO', 'STATUS', 'QTD_COMPRADA', 'SALDO_VAL']], use_container_width=True)
        
        st.divider()
        if st.button("🚨 LIMPAR TODOS OS DADOS", help="Isso apagará o banco de dados desta operação"):
            salvar_estoque_firebase({"analises": [], "idx_atual": 0})
            st.rerun()
def carregar_estoque_firebase():
    db = inicializar_db()
    if not db: return {"analises": [], "idx_atual": 0}
    try:
        doc = db.collection("config").document("operacao_armazem").get()
        if doc.exists:
            return doc.to_dict()
        return {"analises": [], "idx_atual": 0}
    except:
        return {"analises": [], "idx_atual": 0}

def salvar_estoque_firebase(dados):
    db = inicializar_db()
    if db:
        db.collection("config").document("operacao_armazem").set(dados)

def exibir_estoque():
    db_data = carregar_estoque_firebase()
    
    # Estilização CSS
    st.markdown("""
        <style>
            .metric-card {
                background: white; padding: 20px; border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-top: 4px solid #D4AF37;
                text-align: center; margin-bottom: 10px; color: #002366;
            }
        </style>
    """, unsafe_allow_html=True)

    # Verifica se há dados
    if not db_data.get("analises"):
        st.info("📦 Armazém 41: Aguardando carga de dados no Firebase.")
        arq = st.file_uploader("Subir Projeção Inicial (Excel)", type=["xlsx"])
        if arq:
            df_i = pd.read_excel(arq)
            df_i['SOLICITADO'] = df_i['QUANTIDADE'] if 'QUANTIDADE' in df_i.columns else 0
            cols_faltantes = ['STATUS', 'ANALISADO', 'QTD_COMPRADA', 'SALDO_VAL', 'STATUS_REC', 'QTD_RECEBIDA', 'CONFERIDO']
            for col in cols_faltantes:
                df_i[col] = 0 if 'QTD' in col or 'VAL' in col else (False if col != 'STATUS_REC' else "Aguardando")
            df_i['STATUS'] = "Pendente"
            
            db_data = {"analises": df_i.to_dict(orient='records'), "idx_atual": 0}
            salvar_estoque_firebase(db_data)
            st.rerun()
        return

    df = pd.DataFrame(db_data["analises"])
    t_exec, t_dash, t_rel = st.tabs(["🚀 Execução", "📊 Dashboard", "📋 Relatório"])

    with t_exec:
        idx = int(db_data.get("idx_atual", 0))
        if idx < len(df):
            item = df.iloc[idx]
            st.subheader(f"Item {idx+1} de {len(df)}")
            st.info(f"**Descrição:** {item.get('DESCRICAO', 'N/A')}")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                saldo = st.number_input("Saldo em estoque:", min_value=0, key=f"sld_{idx}")
            
            with c2:
                if st.button("✅ COMPRA TOTAL", use_container_width=True):
                    df.at[idx, 'STATUS'] = "Compra Efetuada"
                    df.at[idx, 'QTD_COMPRADA'] = item['SOLICITADO']
                    df.at[idx, 'SALDO_VAL'] = saldo
                    df.at[idx, 'ANALISADO'] = True
                    db_data["idx_atual"] = idx + 1
                    db_data["analises"] = df.to_dict(orient='records')
                    salvar_estoque_firebase(db_data)
                    st.rerun()
            
            with c3:
                if st.button("🔍 SEM ENCOMENDA", use_container_width=True):
                    df.at[idx, 'STATUS'] = "Sem Encomenda"
                    df.at[idx, 'SALDO_VAL'] = saldo
                    df.at[idx, 'ANALISADO'] = True
                    db_data["idx_atual"] = idx + 1
                    db_data["analises"] = df.to_dict(orient='records')
                    salvar_estoque_firebase(db_data)
                    st.rerun()
        else:
            st.success("✅ Todas as análises foram concluídas!")
            if st.button("Reiniciar Processo"):
                db_data["idx_atual"] = 0
                salvar_estoque_firebase(db_data)
                st.rerun()

    with t_dash:
        k1, k2, k3 = st.columns(3)
        total_itens = len(df)
        analisados = len(df[df['ANALISADO'] == True])
        
        k1.markdown(f'<div class="metric-card"><h4>Total Itens</h4><h2>{total_itens}</h2></div>', unsafe_allow_html=True)
        k2.markdown(f'<div class="metric-card"><h4>Analisados</h4><h2>{analisados}</h2></div>', unsafe_allow_html=True)
        k3.markdown(f'<div class="metric-card"><h4>Pendentes</h4><h2>{total_itens - analisados}</h2></div>', unsafe_allow_html=True)
        
        if analisados > 0:
            fig = px.pie(df, names='STATUS', title="Status das Operações", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

    with t_rel:
        st.dataframe(df[['CODIGO', 'DESCRICAO', 'SOLICITADO', 'STATUS', 'QTD_COMPRADA']], use_container_width=True)
        if st.button("Limpar Banco de Dados (CUIDADO)"):
            salvar_estoque_firebase({"analises": [], "idx_atual": 0})
            st.rerun()
