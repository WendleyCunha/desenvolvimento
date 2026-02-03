import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io

# =========================================================
# 1. FUNÇÕES DE BANCO DE DADOS (UPGRADE MENSAL)
# =========================================================
def carregar_dados_op(mes_referencia):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_referencia).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0}

def salvar_dados_op(dados, mes_referencia):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_referencia).set(dados)

def listar_meses_gravados():
    fire = inicializar_db()
    return [doc.id for doc in fire.collection("operacoes_mensais").stream()]

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

# =========================================================
# 2. COMPONENTES DE INTERFACE (TRATATIVAS)
# =========================================================
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    # Uso de .get() para evitar KeyError caso a coluna TIPO não exista em registros antigos
    tipo = "🆕 NOVO" if item.get('TIPO') == 'NOVO_DIRETORIA' else "📦 LISTA"
    st.caption(f"{tipo} | Cód: {item['CODIGO']} | Qtd: {item['QUANTIDADE']}")
    
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True

    if c3.button("❌ NÃO", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]
            salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Esperado: {item['QTD_SOLICITADA']}")
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"
        df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records')
        salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 3. DASHBOARDS
# =========================================================
def renderizar_dashboards(df):
    if df.empty:
        st.info("Sem dados para gerar gráficos.")
        return
    
    # KPIs Rápidos
    total_itens = len(df)
    conferidos = len(df[df['STATUS_COMPRA'] != "Pendente"])
    
    st.subheader("📊 Performance Mensal")
    k1, k2 = st.columns(2)
    k1.metric("Total de Itens", total_itens)
    k2.metric("Conferidos", f"{conferidos} ({ (conferidos/total_itens*100) if total_itens>0 else 0:.1f}%)")

    # Gráfico de Decisões
    st_counts = df['STATUS_COMPRA'].value_counts().reset_index()
    st_counts.columns = ['Status', 'Qtd']
    fig = px.pie(st_counts, values='Qtd', names='Status', hole=0.4, title="Status das Compras")
    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# 4. FUNÇÃO PRINCIPAL (EXIBIÇÃO)
# =========================================================
def exibir_operacao_completa(user_role):
    # Estilos CSS
    st.markdown("""<style>.main-card { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }</style>""", unsafe_allow_html=True)
    
    # 1. Gestão de Mês no Sidebar
    mes_atual_str = datetime.now().strftime("%Y-%m")
    with st.sidebar:
        st.divider()
        meses_dispo = listar_meses_gravados()
        if mes_atual_str not in meses_dispo: meses_dispo.append(mes_atual_str)
        mes_selecionado = st.selectbox("📅 Mês de Análise", sorted(meses_dispo, reverse=True))
    
    db_data = carregar_dados_op(mes_selecionado)
    
    # 2. Abas do Sistema
    tab_compra, tab_receb, tab_dash, tab_novo, tab_config = st.tabs([
        "🛒 COMPRAS", "📥 RECEBIMENTO", "📊 DASHBOARDS", "➕ NOVO ITEM", "⚙️ CONFIGURAÇÕES"
    ])

    with tab_compra:
        if not db_data.get("analises"):
            st.warning("Nenhum dado. Vá em CONFIGURAÇÕES e importe a planilha.")
        else:
            df_c = pd.DataFrame(db_data["analises"])
            q = st.text_input("🔍 Localizar Item:").upper()
            if q:
                it_b = df_c[df_c['CODIGO'].astype(str).str.contains(q) | df_c['DESCRICAO'].astype(str).str.contains(q)]
                for i, r in it_b.iterrows():
                    with st.container(border=True):
                        renderizar_tratativa_compra(r, i, df_c, db_data, mes_selecionado, "busca")
            
            idx_s = db_data.get("idx_solic", 0)
            # Avança o índice se o item já foi processado
            while idx_s < len(df_c) and df_c.iloc[idx_s]['STATUS_COMPRA'] != "Pendente":
                idx_s += 1
            
            db_data["idx_solic"] = idx_s
            
            if idx_s < len(df_c):
                st.subheader(f"🚀 Esteira de Compra ({idx_s + 1}/{len(df_c)})")
                with st.markdown("<div class='main-card'>", unsafe_allow_html=True):
                    renderizar_tratativa_compra(df_c.iloc[idx_s], idx_s, df_c, db_data, mes_selecionado, "esteira")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.success("✅ Todos os itens deste mês foram processados!")

    with tab_novo:
        st.subheader("➕ Novo Item para Projeção")
        with st.form("f_novo_item", clear_on_submit=True):
            c1, c2, c3 = st.columns([1, 2, 1])
            n_cod = c1.text_input("Código").upper()
            n_desc = c2.text_input("Descrição").upper()
            n_qtd = c3.number_input("Qtd", min_value=1)
            if st.form_submit_button("Adicionar Item"):
                if n_cod and n_desc:
                    novo = {"CODIGO": n_cod, "DESCRICAO": n_desc, "QUANTIDADE": n_qtd, "TIPO": "NOVO_DIRETORIA", 
                            "STATUS_COMPRA": "Pendente", "STATUS_RECEB": "Pendente", "QTD_SOLICITADA": 0, "SALDO_FISICO": 0, "QTD_RECEBIDA": 0}
                    db_data["analises"].append(novo)
                    salvar_dados_op(db_data, mes_selecionado)
                    st.success("Item adicionado!"); st.rerun()
                else:
                    st.error("Preencha Código e Descrição.")

    with tab_config:
        st.subheader("⚙️ Configurações de Dados")
        c_up, c_res = st.columns(2)
        with c_up:
            up = st.file_uploader("Importar Planilha Excel", type="xlsx")
            if up:
                df_up = pd.read_excel(up)
                for col in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']:
                    df_up[col] = "Pendente" if "STATUS" in col else 0
                # Adiciona a coluna TIPO por padrão na importação para evitar KeyError
                df_up['TIPO'] = 'LISTA_ESTOQUE'
                db_data["analises"] = df_up.to_dict(orient='records')
                db_data["idx_solic"] = 0
                db_data["idx_receb"] = 0
                salvar_dados_op(db_data, mes_selecionado)
                st.success("Importado com sucesso!"); st.rerun()
        with c_res:
            if st.button("🗑️ RESETAR ESTE MÊS"):
                salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0}, mes_selecionado)
                st.rerun()

    with tab_dash:
        df_dash = pd.DataFrame(db_data.get("analises", []))
        if not df_dash.empty:
            renderizar_dashboards(df_dash)
            # Filtro seguro para evitar KeyError caso a coluna TIPO falte em dados legados
            if 'TIPO' in df_dash.columns:
                novos = df_dash[df_dash['TIPO'] == 'NOVO_DIRETORIA']
                if not novos.empty:
                    with st.expander("📋 Itens Novos para Diretoria"):
                        st.table(novos[['CODIGO', 'DESCRICAO', 'QUANTIDADE']])
        else:
            st.info("Aguardando dados para exibir o Dashboard.")
