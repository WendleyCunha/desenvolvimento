import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# =========================================================
# 1. CONFIGURAÇÕES DE ESTILO E PALETA PREMIUM
# =========================================================
PALETA = ['#002366', '#3b82f6', '#16a34a', '#ef4444', '#facc15']

def aplicar_estilo_premium():
    st.markdown(f"""
        <style>
        .main-card {{ background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid {PALETA[0]}; margin-bottom: 20px; color: #1e293b; }}
        .metric-box {{ background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; color: {PALETA[0]}; }}
        .metric-box h3 {{ margin: 5px 0; font-size: 1.8rem; font-weight: bold; }}
        .search-box {{ background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .search-box-rec {{ background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[2]}; margin-bottom: 20px; }}
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 22px; }}
        </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. FUNÇÕES DE BANCO DE DADOS E SUPORTE
# =========================================================
def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    # Adicionado campo 'picos' para garantir que a aba de dashboard tenha onde ler
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

def normalizar_cabecalhos(df):
    mapeamento = {
        'CRIACAO DO TICKET - DATA': 'DATA',
        'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA',
        'CRIACAO DO TICKET - HORA': 'HORA',
        'TICKETS': 'TICKETS'
    }
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    df = df.rename(columns=mapeamento)
    return df

# =========================================================
# 3. TRATATIVAS VISUAIS (ESTEIRA)
# =========================================================
def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"
        df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"
        df_completo.at[index, 'QTD_SOLICITADA'] = 0
        df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo; db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado: {item['QTD_SOLICITADA']}**")
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"; df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True
    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"; df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=int(item['QTD_SOLICITADA']), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"; df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 4. ABA: DASHBOARD OPERACIONAL (INTEGRADA)
# =========================================================
def renderizar_picos_operacional(db_picos):
    if not db_picos:
        st.info("💡 Sem dados de picos. Importe a planilha do Zendesk em CONFIGURAÇÕES.")
        return
    
    df = normalizar_cabecalhos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    st.subheader("🔥 Inteligência de Canais & Picos")
    
    # Filtro de Calendário
    dias_disponiveis = sorted(df['DATA'].unique())
    col_btn, col_sel = st.columns([1, 4])
    
    if "todos_selecionados" not in st.session_state: st.session_state.todos_selecionados = True
    if col_btn.button("Marcar/Desmarcar Todos"):
        st.session_state.todos_selecionados = not st.session_state.todos_selecionados
        st.rerun()
    
    dias_selecionados = col_sel.multiselect("Dias para análise:", dias_disponiveis, 
                                           default=dias_disponiveis if st.session_state.todos_selecionados else [])
    
    if not dias_selecionados: return

    df_f = df[df['DATA'].isin(dias_selecionados)]
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    c1, c2 = st.columns(2)
    with c1:
        df_h = df_f.groupby('HORA')['TICKETS'].sum().reset_index()
        fig_h = px.bar(df_h, x='HORA', y='TICKETS', title="Volume por Hora", text_auto=True, color_discrete_sequence=[PALETA[0]])
        fig_h.update_traces(textposition='outside')
        st.plotly_chart(fig_h, use_container_width=True)
    with c2:
        df_d = df_f.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna()
        fig_d = px.bar(df_d, x='DIA_SEMANA', y='TICKETS', title="Volume por Dia", text_auto=True, color_discrete_sequence=[PALETA[1]])
        fig_d.update_traces(textposition='outside')
        st.plotly_chart(fig_d, use_container_width=True)

    pivot = df_f.pivot_table(index='HORA', columns='DIA_SEMANA', values='TICKETS', aggfunc='sum').fillna(0)
    pivot = pivot[[d for d in ordem_dias if d in pivot.columns]]
    st.plotly_chart(px.imshow(pivot, text_auto=True, title="Mapa de Calor", color_continuous_scale='Reds'), use_container_width=True)

# =========================================================
# 5. EXIBIÇÃO PRINCIPAL (SISTEMA UNIFICADO)
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    
    # ITEM 2 e 3: Período e Identificação clara no topo
    with st.container():
        c_mes, c_ano, c_status = st.columns([2, 1, 3])
        meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_sel = c_mes.selectbox("Mês de Referência", meses_lista, index=datetime.now().month - 1)
        ano_sel = c_ano.selectbox("Ano de Referência", [2024, 2025, 2026], index=1)
        mes_ref = f"{mes_sel}_{ano_sel}"
        c_status.markdown(f"<div class='header-analise'>📅 ANALISANDO: {mes_sel.upper()} / {ano_sel}</div>", unsafe_allow_html=True)

    db_data = carregar_dados_op(mes_ref)
    
    # ITEM 1: Controle por ABAS dentro de Operações
    tab_compra, tab_receb, tab_dash_picos, tab_config = st.tabs([
        "🛒 COMPRA & ESTEIRA", "📥 RECEBIMENTO", "📊 DASH OPERACIONAL (PICOS)", "⚙️ CONFIGURAÇÕES"
    ])

    # --- LOGICA DA ABA COMPRA ---
    with tab_compra:
        if not db_data.get("analises"):
            st.warning("⚠️ Nenhuma base de compras carregada.")
        else:
            df_atual = pd.DataFrame(db_data["analises"])
            st.markdown('<div class="search-box">', unsafe_allow_html=True)
            q = st.text_input("🔍 Localizar Item (Cód ou Desc):").upper()
            if q:
                it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                for i, r in it_b.iterrows():
                    with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq")
            st.markdown('</div>', unsafe_allow_html=True)
            
            idx_s = db_data.get("idx_solic", 0)
            while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
            db_data["idx_solic"] = idx_s
            if idx_s < len(df_atual):
                st.subheader(f"🚀 Esteira de Compras ({idx_s + 1}/{len(df_atual)})")
                with st.container():
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "est_c")
                    st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Todas as compras do mês concluídas!")

    # --- LOGICA DA ABA RECEBIMENTO ---
    with tab_receb:
        if db_data.get("analises"):
            df_atual = pd.DataFrame(db_data["analises"])
            pend_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
            if not pend_rec.empty:
                st.markdown('<div class="search-box-rec">', unsafe_allow_html=True)
                q_r = st.text_input("🔍 Localizar no Recebimento:").upper()
                if q_r:
                    it_r = pend_rec[pend_rec['CODIGO'].astype(str).str.contains(q_r) | pend_rec['DESCRICAO'].astype(str).str.contains(q_r)]
                    for _, r in it_r.iterrows():
                        with st.container(border=True): renderizar_tratativa_recebimento(r, r['index'], df_atual, db_data, mes_ref, "br")
                st.markdown('</div>', unsafe_allow_html=True)
                
                idx_r = db_data.get("idx_receb", 0)
                if idx_r >= len(pend_rec): idx_r = 0
                st.subheader(f"📥 Recebimento ({idx_r + 1}/{len(pend_rec)})")
                with st.container():
                    st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True)
                    renderizar_tratativa_recebimento(pend_rec.iloc[idx_r], pend_rec.iloc[idx_r]['index'], df_atual, db_data, mes_ref, "est_r")
                    st.markdown("</div>", unsafe_allow_html=True)
            else: st.success("✅ Tudo recebido!")

    # --- LOGICA DA ABA DASHBOARD PICOS ---
    with tab_dash_picos:
        renderizar_picos_operacional(db_data.get("picos", []))

    # --- LOGICA DA ABA CONFIGURAÇÕES ---
    with tab_config:
        st.header(f"⚙️ Configuração: {mes_sel}/{ano_sel}")
        c1, c2 = st.columns(2)
        with c1:
            up_compra = st.file_uploader("Upload Base Compras (Excel)", type="xlsx", key="up_c")
            if up_compra and st.button("🚀 Iniciar Mês com esta Base"):
                df_n = pd.read_excel(up_compra)
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: df_n[c] = "Pendente" if "STATUS" in c else 0
                db_data["analises"] = df_n.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
        with c2:
            up_pico = st.file_uploader("Upload Base Picos Zendesk (Excel)", type="xlsx", key="up_p")
            if up_pico and st.button("📥 Importar Dados de Picos"):
                df_p = pd.read_excel(up_pico)
                db_data["picos"] = df_p.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        if st.button("🗑️ RESETAR TODOS OS DADOS DO MÊS"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}, mes_ref); st.rerun()

# Execução direta para testes
if __name__ == "__main__":
    exibir_operacao_completa()
