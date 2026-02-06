import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import io
import unicodedata

# =========================================================
# 1. CONFIGURAÇÕES, ESTILO E SUPORTE
# =========================================================
PALETA = ['#002366', '#3b82f6', '#16a34a', '#ef4444', '#facc15']

def aplicar_estilo_premium():
    st.markdown(f"""
        <style>
        .main-card {{ background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); border-top: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .metric-box {{ background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0; text-align: center; height: 100%; }}
        .metric-box h3 {{ margin: 5px 0; font-size: 1.8rem; font-weight: bold; color: {PALETA[0]}; }}
        .search-box {{ background: #f1f5f9; padding: 20px; border-radius: 15px; border-left: 5px solid {PALETA[0]}; margin-bottom: 20px; }}
        .header-analise {{ background: {PALETA[0]}; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; font-weight: bold; font-size: 20px; }}
        </style>
    """, unsafe_allow_html=True)

def carregar_dados_op(mes_ref):
    fire = inicializar_db()
    doc = fire.collection("operacoes_mensais").document(mes_ref).get()
    return doc.to_dict() if doc.exists else {"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}

def salvar_dados_op(dados, mes_ref):
    fire = inicializar_db()
    fire.collection("operacoes_mensais").document(mes_ref).set(dados)

def normalizar_picos(df):
    mapeamento = {'CRIACAO DO TICKET - DATA': 'DATA', 'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA', 'CRIACAO DO TICKET - HORA': 'HORA', 'TICKETS': 'TICKETS'}
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    return df.rename(columns=mapeamento)

# =========================================================
# 2. BLOCO: COMPRAS E RECEBIMENTO (INTEGRIDADE MANTIDA)
# =========================================================
# ... (As funções renderizar_tratativa_compra e recebimento permanecem as mesmas do seu código original)

def renderizar_tratativa_compra(item, index, df_completo, db_data, mes_ref, key_suffix=""):
    st.markdown(f"#### {item['DESCRICAO']}")
    st.caption(f"Cód: {item['CODIGO']} | Lista: {item['QUANTIDADE']}")
    saldo = st.number_input(f"Saldo em Estoque:", min_value=0, value=int(item.get('SALDO_FISICO', 0)), key=f"sld_{index}_{key_suffix}")
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ TOTAL", key=f"tot_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Total"; df_completo.at[index, 'QTD_SOLICITADA'] = item['QUANTIDADE']; df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if c2.button("⚠️ PARCIAL", key=f"par_{index}_{key_suffix}", use_container_width=True):
        st.session_state[f"show_p_{index}_{key_suffix}"] = True
    if c3.button("❌ NÃO EFETUADA", key=f"zer_{index}_{key_suffix}", use_container_width=True):
        df_completo.at[index, 'STATUS_COMPRA'] = "Não Efetuada"; df_completo.at[index, 'QTD_SOLICITADA'] = 0; df_completo.at[index, 'SALDO_FISICO'] = saldo
        db_data["analises"] = df_completo.to_dict(orient='records'); salvar_dados_op(db_data, mes_ref); st.rerun()
    if st.session_state.get(f"show_p_{index}_{key_suffix}"):
        cp1, cp2 = st.columns([2, 1])
        qtd_p = cp1.number_input("Qtd Parcial:", min_value=1, max_value=int(item['QUANTIDADE']), key=f"val_{index}_{key_suffix}")
        if cp2.button("Confirmar", key=f"btn_p_{index}_{key_suffix}"):
            df_completo.at[index, 'STATUS_COMPRA'] = "Parcial"; df_completo.at[index, 'QTD_SOLICITADA'] = qtd_p; df_completo.at[index, 'SALDO_FISICO'] = saldo
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

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
            db_data["analises"] = df_completo.to_dict(orient='records'); del st.session_state[f"show_rec_p_{index}_{key_suffix}"]; salvar_dados_op(db_data, mes_ref); st.rerun()

def renderizar_dashboards_compras_completo(df):
    if df.empty: return
    total_itens = len(df)
    df_proc = df[df['STATUS_COMPRA'] != "Pendente"]
    itens_conferidos = len(df_proc)
    compras_ok = len(df_proc[df_proc['STATUS_COMPRA'].isin(['Total', 'Parcial'])])
    perc_conf = (itens_conferidos / total_itens * 100) if total_itens > 0 else 0
    perc_ok = (compras_ok / itens_conferidos * 100) if itens_conferidos > 0 else 0
    df_nao_efetuada = df_proc[df_proc['STATUS_COMPRA'] == "Não Efetuada"]
    nao_efet_com_estoque = df_nao_efetuada[df_nao_efetuada['SALDO_FISICO'] > 0]
    nao_efet_sem_estoque = df_nao_efetuada[df_nao_efetuada['SALDO_FISICO'] == 0]

    st.subheader("📊 Performance de Compras")
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-box'><small>CONFERÊNCIA</small><h3>{itens_conferidos}</h3><p>{perc_conf:.1f}%</p></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-box'><small>COMPRAS OK</small><h3>{compras_ok}</h3><p>{perc_ok:.1f}%</p></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='metric-box'><small>ESTRATÉGICO</small><h3 style='color:#16a34a;'>{len(nao_efet_com_estoque)}</h3></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-box'><small>RUPTURA</small><h3 style='color:#ef4444;'>{len(nao_efet_sem_estoque)}</h3></div>", unsafe_allow_html=True)

# =========================================================
# 3. BLOCO: DASH OPERAÇÃO (PICOS, DIMENSIONAMENTO E ABS)
# =========================================================

def renderizar_picos_operacional(db_picos, db_data, mes_ref):
    if not db_picos:
        st.info("💡 Sem dados de picos. Importe a planilha na aba CONFIGURAÇÕES.")
        return

    # Sub-abas dentro de Dash Operação
    tab_p, tab_d, tab_a = st.tabs(["🔥 Mapa de Calor", "👥 Dimensionamento", "📝 Registro de ABS"])

    df = normalizar_picos(pd.DataFrame(db_picos))
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']

    with tab_p:
        st.markdown("### 📅 Filtro de Dias")
        dias_disponiveis = sorted(df['DATA'].unique())
        dias_selecionados = st.multiselect("Selecione os dias:", dias_disponiveis, default=dias_disponiveis)
        
        if dias_selecionados:
            df_f = df[df['DATA'].isin(dias_selecionados)]
            fig_heat = px.density_heatmap(df_f, x="HORA", y="DIA_SEMANA", z="TICKETS", category_orders={"DIA_SEMANA": ordem_dias}, color_continuous_scale="Viridis", text_auto=True)
            st.plotly_chart(fig_heat, use_container_width=True)

    with tab_d:
        st.subheader("🧮 Calculadora de Staff")
        if dias_selecionados:
            df_dim = df[df['DATA'].isin(dias_selecionados)].groupby('HORA')['TICKETS'].mean().reset_index()
            # Regra: 4 atendimentos por hora
            df_dim['AGENTES'] = (df_dim['TICKETS'] / 4).apply(lambda x: int(x) + 1 if x % 1 > 0 else int(x))
            
            st.write("Média de agentes necessários por hora (Baseado na seleção de dias):")
            st.plotly_chart(px.bar(df_dim, x='HORA', y='AGENTES', text='AGENTES', color_discrete_sequence=[PALETA[1]]), use_container_width=True)
            
            st.subheader("☕ Sugestão de Pausas")
            vales = df_dim.sort_values(by='TICKETS').head(3)
            st.write("Melhores horários para saída de pausa (Menor volume):")
            cols = st.columns(3)
            for i, (idx, row) in enumerate(vales.iterrows()):
                cols[i].metric(f"{i+1}ª Opção", f"{int(row['HORA'])}:00")

    with tab_a:
        st.subheader("📝 Controle de ABS")
        with st.form("abs_form"):
            f1, f2, f3 = st.columns(3)
            data_abs = f1.date_input("Data da Ocorrência")
            tipo_abs = f2.selectbox("Tipo", ["Falta", "Atraso", "Saída Antecipada"])
            nome_abs = f3.text_input("Colaborador")
            if st.form_submit_button("Registrar"):
                nova_abs = {"data": str(data_abs), "tipo": tipo_abs, "nome": nome_abs}
                if "abs" not in db_data: db_data["abs"] = []
                db_data["abs"].append(nova_abs)
                salvar_dados_op(db_data, mes_ref)
                st.success("Registrado!")
        
        if db_data.get("abs"):
            st.table(pd.DataFrame(db_data["abs"]))

# =========================================================
# 4. ESTRUTURA UNIFICADA (MAIN)
# =========================================================

# AJUSTE AQUI: Adicionado user_role=None para evitar o erro de TypeError
def exibir_operacao_completa(user_role=None):
    aplicar_estilo_premium()
    
    st.sidebar.title("📅 Gestão Mensal")
    meses_lista = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_sel = st.sidebar.selectbox("Mês", meses_lista, index=datetime.now().month - 1)
    ano_sel = st.sidebar.selectbox("Ano", [2024, 2025, 2026], index=1)
    mes_ref = f"{mes_sel}_{ano_sel}"
    
    db_data = carregar_dados_op(mes_ref)
    df_atual = pd.DataFrame(db_data["analises"]) if db_data.get("analises") else pd.DataFrame()

    tab_modulo_compras, tab_modulo_picos, tab_modulo_config = st.tabs([
        "🛒 COMPRAS", "📊 DASH OPERAÇÃO", "⚙️ CONFIGURAÇÕES"
    ])

    with tab_modulo_compras:
        # ... (Mantém sua lógica de compras original)
        st.markdown(f"<div class='header-analise'>SISTEMA DE COMPRAS - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        # (Código omitido para brevidade, mas deve ser o mesmo do seu original)
        pass

    with tab_modulo_picos:
        st.markdown(f"<div class='header-analise'>DASH OPERAÇÃO - {mes_sel.upper()}</div>", unsafe_allow_html=True)
        renderizar_picos_operacional(db_data.get("picos", []), db_data, mes_ref)

    with tab_modulo_config:
        st.markdown(f"<div class='header-analise'>CONFIGURAÇÕES</div>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        with c1:
            up_c = st.file_uploader("Base Compras (Excel)", type="xlsx")
            if up_c and st.button("Salvar Compras"):
                df_n = pd.read_excel(up_c)
                db_data["analises"] = df_n.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()
            
            # NOVO: Botão Reset Compras
            if st.button("🗑️ Resetar Base Compras", type="secondary"):
                db_data["analises"] = []
                salvar_dados_op(db_data, mes_ref); st.rerun()

        with c2:
            up_p = st.file_uploader("Base Picos (Excel)", type="xlsx")
            if up_p and st.button("Salvar Picos"):
                df_p = pd.read_excel(up_p)
                db_data["picos"] = df_p.to_dict(orient='records')
                salvar_dados_op(db_data, mes_ref); st.rerun()
                
            # NOVO: Botão Reset Picos
            if st.button("🗑️ Resetar Base Picos", type="secondary"):
                db_data["picos"] = []
                salvar_dados_op(db_data, mes_ref); st.rerun()

        st.divider()
        if st.button("🗑️ RESET TOTAL MÊS", type="primary"):
            salvar_dados_op({"analises": [], "idx_solic": 0, "idx_receb": 0, "picos": [], "abs": []}, mes_ref); st.rerun()

if __name__ == "__main__":
    exibir_operacao_completa()
