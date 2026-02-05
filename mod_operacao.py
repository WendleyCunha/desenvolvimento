import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# =========================================================
# 1. CONFIGURAÇÕES, ESTILO E BANCO DE DADOS
# =========================================================
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; color: #1e293b; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; color: #002366; }
        .metric-box h3 { margin: 5px 0; font-size: 1.8rem; font-weight: bold; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        .search-box-rec { background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid #16a34a; margin-bottom: 20px; }
        .header-analise { background: #002366; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatorio')
    return output.getvalue()

def normalizar_cabecalhos_picos(df):
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
# 2. TRATATIVAS DE COMPRAS (INTEGRAL)
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
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"
            df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p
            df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_tratativa_recebimento(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | **Esperado: {item['QTD_SOLICITADA']}**")
    rc1, rc2, rc3 = st.columns(3)
    if rc1.button("🟢 TOTAL", key=f"rec_tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Recebido Total"
        df_completo.at[index, 'QTD_RECEBIDA'] = item['QTD_SOLICITADA']
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if rc2.button("🟡 PARCIAL", key=f"rec_par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_rec_p_{index}_{key_suffix}"] = True
    if rc3.button("🔴 FALTOU", key=f"rec_fal_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_RECEB'] = "Faltou"
        df_completo.at[index, 'QTD_RECEBIDA'] = 0
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 3. DASHBOARDS E PICOS
# =========================================================
def renderizar_picos_operacional(db_picos):
    if not db_picos:
        st.info("💡 Sem dados de picos para este período.")
        return
    df = normalizar_cabecalhos_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    st.subheader("🔥 Inteligência de Canais")
    
    col1, col2 = st.columns(2)
    with col1:
        df_h = df.groupby('HORA')['TICKETS'].sum().reset_index()
        fig_h = px.bar(df_h, x='HORA', y='TICKETS', title="Picos por Hora", color_discrete_sequence=['#002366'])
        st.plotly_chart(fig_h, use_container_width=True)
    with col2:
        dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
        df_d = df.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(dias).reset_index().dropna()
        fig_d = px.bar(df_d, x='DIA_SEMANA', y='TICKETS', title="Picos por Dia", color_discrete_sequence=['#3b82f6'])
        st.plotly_chart(fig_d, use_container_width=True)

    pivot = df.pivot_table(index='HORA', columns='DIA_SEMANA', values='TICKETS', aggfunc='sum').fillna(0)
    st.plotly_chart(px.imshow(pivot, text_auto=True, title="Mapa de Calor de Atendimento", color_continuous_scale='Reds'), use_container_width=True)

# =========================================================
# 4. FUNÇÃO PRINCIPAL: EXIBIR OPERAÇÃO COMPLETA
# =========================================================
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    
    # --- CABEÇALHO DE SELEÇÃO (ITEM 2 e 3) ---
    with st.container():
        c_mes, c_ano, c_status = st.columns([2, 1, 3])
        meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        mes_sel = c_mes.selectbox("Mês de Referência", meses, index=datetime.now().month - 1)
        ano_sel = c_ano.selectbox("Ano", [2024, 2025, 2026], index=1)
        mes_ref = f"{mes_sel}_{ano_sel}"
        
        c_status.markdown(f"""
            <div class='header-analise'>
                📅 ANALISANDO: {mes_sel.upper()} / {ano_sel}
            </div>
        """, unsafe_allow_html=True)

    db_data = carregar_dados_op(mes_ref)
    
    # --- ABAS DE OPERAÇÕES (ITEM 1) ---
    tabs_main = st.tabs(["🛒 COMPRAS & ESTEIRA", "📥 RECEBIMENTO", "📊 DASH OPERACIONAL (PICOS)", "⚙️ CONFIGURAÇÕES"])

    # --- ABA 1: COMPRAS ---
    with tabs_main[0]:
        if not db_data.get("analises"):
            st.warning("⚠️ Base de compras não encontrada para este mês.")
        else:
            df_atual = pd.DataFrame(db_data["analises"])
            st.markdown('<div class="search-box">', unsafe_allow_html=True)
            q = st.text_input("🔍 Localizar Item na Lista:").upper()
            if q:
                it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                for i, r in it_b.iterrows():
                    with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bq")
            st.markdown('</div>', unsafe_allow_html=True)
            
            idx = db_data.get("idx_solic", 0)
            while idx < len(df_atual) and df_atual.iloc[idx]['STATUS_COMPRA'] != "Pendente": idx += 1
            if idx < len(df_atual):
                st.subheader(f"🚀 Esteira de Compras ({idx + 1}/{len(df_atual)})")
                with st.markdown("<div class='main-card'>", unsafe_allow_html=True):
                    renderizar_tratativa_compra(df_atual.iloc[idx], idx, df_atual, db_data, mes_ref, "est_c")
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.success("✅ Todas as compras do mês foram processadas!")

    # --- ABA 2: RECEBIMENTO ---
    with tabs_main[1]:
        if db_data.get("analises"):
            df_atual = pd.DataFrame(db_data["analises"])
            pendentes = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
            if not pendentes.empty:
                st.subheader(f"📥 Itens Aguardando Chegada ({len(pendentes)})")
                idx_r = 0 # Foca sempre no primeiro da fila de pendentes
                with st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True):
                    renderizar_tratativa_recebimento(pendentes.iloc[idx_r], pendentes.iloc[idx_r]['index'], df_atual, db_data, mes_ref, "est_r")
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.success("✅ Tudo o que foi comprado já foi recebido.")

    # --- ABA 3: DASH OPERACIONAL / PICOS ---
    with tabs_main[2]:
        renderizar_picos_operacional(db_data.get("picos", []))

    # --- ABA 4: CONFIGURAÇÕES ---
    with tabs_main[3]:
        st.subheader("📤 Importação de Dados")
        col_a, col_b = st.columns(2)
        with col_a:
            up_c = st.file_uploader("Planilha de Compras", type="xlsx", key="up_compras")
            if up_c and st.button("Importar Compras"):
                df_n = pd.read_excel(up_c)
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: 
                    df_n[c] = "Pendente" if "STATUS" in c else 0
                db_data["analises"] = df_n.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()
        
        with col_b:
            up_p = st.file_uploader("Relatório de Picos (Zendesk)", type="xlsx", key="up_picos")
            if up_p and st.button("Importar Picos"):
                df_p = pd.read_excel(up_p)
                db_data["picos"] = df_p.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        if st.button("🗑️ RESETAR DADOS DE " + mes_sel.upper()):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}, mes_ref); st.rerun()

# Execução (apenas para teste direto ou importação)
if __name__ == "__main__":
    exibir_operacao_completa()
