import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# =========================================================
# 1. NÚCLEO DE DADOS E ESTILO (Centralizado)
# =========================================================
def aplicar_estilo_premium():
    st.markdown("""
        <style>
        .main-card { background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid #002366; margin-bottom: 20px; }
        .metric-box { background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; color: #002366; }
        .metric-box h3 { margin: 5px 0; font-size: 1.8rem; font-weight: bold; }
        .search-box { background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; margin-bottom: 20px; }
        .search-box-rec { background: #f0fdf4; padding: 20px; border-radius: 15px; border-left: 5px solid #16a34a; margin-bottom: 20px; }
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
# 2. MÓDULO DE COMPRAS (Sua lógica de esteira mantida)
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
    if st.session_state.get(f"show_rec_p_{index}_{key_suffix}"):
        rp1, rp2 = st.columns([2, 1])
        qtd_r = rp1.number_input("Qtd Real:", min_value=0, max_value=int(item['QTD_SOLICITADA']), key=f"val_rec_{index}_{key_suffix}")
        if rp2.button("Confirmar", key=f"btn_rec_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_RECEB'] = "Recebido Parcial"
            df_completo.at[index, 'QTD_RECEBIDA'] = qtd_r
            db_data["analises"] = df_completo.to_dict(orient='records')
            del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

# =========================================================
# 3. MÓDULO DASHBOARD OPERACIONAL (PICOS)
# =========================================================
def renderizar_dash_operacional(db_data):
    st.header("🔥 Dashboard Operacional de Picos")
    if not db_data.get("picos"):
        st.info("💡 Nenhuma base de picos encontrada. Vá em CONFIGURAÇÕES.")
        return

    df = normalizar_cabecalhos_picos(pd.DataFrame(db_data["picos"]))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    # 1. Volume Hora a Hora
    st.markdown("### 1. Entradas por Hora (Picos)")
    df_h = df.groupby('HORA')['TICKETS'].sum().reset_index()
    p_h = df_h['TICKETS'].max()
    df_h['COR'] = ['#ef4444' if v == p_h else '#002366' for v in df_h['TICKETS']]
    fig_h = px.bar(df_h, x='HORA', y='TICKETS', color='COR', color_discrete_map="identity")
    st.plotly_chart(fig_h, use_container_width=True)

    # 2. Volume por Dia da Semana
    st.markdown("### 2. Volume por Dia da Semana")
    dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    df_d = df.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(dias).reset_index().dropna()
    p_d = df_d['TICKETS'].max()
    df_d['COR'] = ['#ef4444' if v == p_d else '#3b82f6' for v in df_d['TICKETS']]
    fig_d = px.bar(df_d, x='DIA_SEMANA', y='TICKETS', color='COR', color_discrete_map="identity")
    st.plotly_chart(fig_d, use_container_width=True)

    # 3. Mapa de Calor
    st.markdown("### 3. Mapa de Calor (Cruzamento)")
    pivot = df.pivot_table(index='HORA', columns='DIA_SEMANA', values='TICKETS', aggfunc='sum').fillna(0)
    pivot = pivot[[d for d in dias if d in pivot.columns]]
    fig_heat = px.imshow(pivot, text_auto=True, aspect="auto", color_continuous_scale='Reds')
    st.plotly_chart(fig_heat, use_container_width=True)

# =========================================================
# 4. EXIBIÇÃO PRINCIPAL (MAIN INTEGRADO)
# =========================================================
def exibir_operacao_completa():
    aplicar_estilo_premium()
    
    # Menu Lateral para Filtros
    st.sidebar.title("🛠️ Filtros")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    
    # AS DUAS GRANDES ÁREAS SOLICITADAS
    area = st.sidebar.radio("Selecione a Frente:", ["🛒 COMPRAS", "📊 DASH OPERACIONAL"])
    st.sidebar.divider()
    config_mode = st.sidebar.toggle("⚙️ Abrir Configurações")

    if config_mode:
        st.header("⚙️ Configurações de Base")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🛒 Base de Compras")
            up_c = st.file_uploader("Excel Compras", type="xlsx", key="up_c")
            if up_c and st.button("🚀 Processar Compras"):
                df_n = pd.read_excel(up_c)
                for c in ['STATUS_COMPRA', 'QTD_SOLICITADA', 'SALDO_FISICO', 'QTD_RECEBIDA', 'STATUS_RECEB']: df_n[c] = "Pendente" if "STATUS" in c else 0
                db_data["analises"] = df_n.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()
        with c2:
            st.subheader("🔥 Base de Picos")
            up_p = st.file_uploader("Excel Picos (WhatsApp)", type="xlsx", key="up_p")
            if up_p and st.button("📈 Processar Picos"):
                df_p = pd.read_excel(up_p)
                db_data["picos"] = df_p.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()
        
        if st.button("🗑️ Resetar Período"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": []}, mes_ref); st.rerun()
        st.divider()

    # --- RENDERIZAÇÃO DAS ÁREAS ---
    if area == "🛒 COMPRAS":
        if not db_data.get("analises"):
            st.warning("⚠️ Carregue a base de compras nas configurações.")
        else:
            tabs_c = st.tabs(["🚀 ESTEIRA COMPRA", "📥 RECEBIMENTO", "📉 DASH COMPRAS"])
            df_atual = pd.DataFrame(db_data["analises"])
            
            with tabs_c[0]:
                st.markdown('<div class="search-box">', unsafe_allow_html=True)
                q = st.text_input("🔍 Localizar Item:").upper()
                if q:
                    it_b = df_atual[df_atual['CODIGO'].astype(str).str.contains(q) | df_atual['DESCRICAO'].astype(str).str.contains(q)]
                    for i, r in it_b.iterrows():
                        with st.container(border=True): renderizar_tratativa_compra(r, i, df_atual, db_data, mes_ref, "bc")
                st.markdown('</div>', unsafe_allow_html=True)
                
                idx_s = db_data.get("idx_solic", 0)
                while idx_s < len(df_atual) and df_atual.iloc[idx_s]['STATUS_COMPRA'] != "Pendente": idx_s += 1
                db_data["idx_solic"] = idx_s
                if idx_s < len(df_atual):
                    st.subheader(f"Item Atual ({idx_s + 1}/{len(df_atual)})")
                    with st.markdown("<div class='main-card'>", unsafe_allow_html=True):
                        renderizar_tratativa_compra(df_atual.iloc[idx_s], idx_s, df_atual, db_data, mes_ref, "est_c")
                    st.markdown("</div>", unsafe_allow_html=True)

            with tabs_c[1]:
                # Lógica de Recebimento resumida
                pendentes_rec = df_atual[(df_atual['QTD_SOLICITADA'] > 0) & (df_atual['STATUS_RECEB'] == "Pendente")].reset_index()
                if not pendentes_rec.empty:
                    idx_r = db_data.get("idx_receb", 0)
                    if idx_r >= len(pendentes_rec): idx_r = 0
                    st.subheader(f"Recebimento ({idx_r + 1}/{len(pendentes_rec)})")
                    with st.markdown("<div class='main-card' style='border-top-color:#16a34a;'>", unsafe_allow_html=True):
                        renderizar_tratativa_recebimento(pendentes_rec.iloc[idx_r], pendentes_rec.iloc[idx_r]['index'], df_atual, db_data, mes_ref, "est_r")
                    st.markdown("</div>", unsafe_allow_html=True)

            with tabs_c[2]:
                # Seus Dashboards originais de performance
                from mod_compras import renderizar_dashboard_compras # Se tiver separado ou cole aqui a função
                renderizar_dashboard_compras(df_atual)

    elif area == "📊 DASH OPERACIONAL":
        renderizar_dash_operacional(db_data)

# Início
if __name__ == "__main__":
    exibir_operacao_completa()
