import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import plotly.express as px
import io

def exibir_painel_atendimento(demandas, user):
    # --- 1. CONFIGURAÇÕES ---
    COLOR_BLUE = "#002366"
    COLOR_GOLD = "#D4AF37"
    COLOR_BG = "#f0f2f6"
    DB_ATIVIDADES = "atividades_config.json"
    DB_LANCAMENTOS = "lancamentos_operacao.csv"

    # Nota: Removi o set_page_config daqui pois ele deve ficar apenas no main.py

    st.markdown(f"""
        <style>
        .stApp {{ background: radial-gradient(circle at top right, #ffffff, {COLOR_BG}); }}
        .card-moderno {{
            background: white; padding: 20px; border-radius: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.05);
            border-left: 8px solid {COLOR_BLUE}; margin-bottom: 15px;
        }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: {COLOR_BLUE}; }}
        .metric-label {{ font-size: 14px; color: #64748b; }}
        </style>
    """, unsafe_allow_html=True)

    # --- 2. FUNÇÕES INTERNAS DE DADOS ---
    def carregar_config():
        if os.path.exists(DB_ATIVIDADES):
            with open(DB_ATIVIDADES, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"colaboradores": {}}

    def salvar_config(config):
        with open(DB_ATIVIDADES, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    def carregar_dados():
        if os.path.exists(DB_LANCAMENTOS):
            try:
                df = pd.read_csv(DB_LANCAMENTOS)
                df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
                return df.dropna(subset=['Data'])
            except:
                return pd.DataFrame(columns=["Data", "Operador", "Setor", "Atividade", "Quantidade Entrada", "Quantidade Tratada"])
        return pd.DataFrame(columns=["Data", "Operador", "Setor", "Atividade", "Quantidade Entrada", "Quantidade Tratada"])

    def renderizar_painel_360(df_filtrado, contexto):
        total_in = df_filtrado['Quantidade Entrada'].sum()
        total_out = df_filtrado['Quantidade Tratada'].sum()
        eficiencia = (total_out / total_in * 100) if total_in > 0 else 0
        
        m1, m2, m3, m4 = st.columns(4)
        for col, lab, val in zip([m1, m2, m3, m4], 
                                  ["Volume Entrada", "Volume Tratado", "Pendente", "% Eficiência"],
                                  [total_in, total_out, total_in - total_out, f"{eficiencia:.1f}%"]):
            col.markdown(f"""<div class="card-moderno" style="text-align:center; padding:10px;">
                <div class="metric-label">{lab}</div><div class="metric-value">{val}</div></div>""", unsafe_allow_html=True)

        if not df_filtrado.empty:
            st.markdown(f"### 📊 Desempenho por Operador: {contexto}")
            df_g = df_filtrado.groupby("Operador").agg({'Quantidade Entrada':'sum', 'Quantidade Tratada':'sum'}).reset_index()
            df_melt = df_g.melt(id_vars=["Operador"], value_vars=["Quantidade Entrada", "Quantidade Tratada"], 
                                var_name="Tipo", value_name="Volume")
            
            fig_op = px.bar(df_melt, x="Operador", y="Volume", color="Tipo", 
                            barmode="group", text="Volume",
                            color_discrete_map={'Quantidade Entrada': COLOR_GOLD, 'Quantidade Tratada': COLOR_BLUE})
            fig_op.update_traces(textposition='outside')
            st.plotly_chart(fig_op, use_container_width=True, key=f"bar_op_{contexto}")

    # --- 3. ESTRUTURA PRINCIPAL ---
    if "config_painel" not in st.session_state:
        st.session_state.config_painel = carregar_config()

    st.title("👑 King Star | Governança Operacional")
    aba_lanc, aba_painel, aba_gestao = st.tabs(["📝 LANÇAMENTO", "📊 PAINEL 360º", "⚙️ CONFIGURAÇÕES"])

    # --- ABA 1: LANÇAMENTO ---
    with aba_lanc:
        st.markdown('<div class="card-moderno">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        data_reg = c1.date_input("Data", datetime.now())
        setores = sorted([s for s in st.session_state.config_painel.keys() if s != "colaboradores"])
        setor_sel = c3.selectbox("Setor", setores) if setores else c3.warning("Crie um setor em Configurações.")
        
        colabs = st.session_state.config_painel.get("colaboradores", {}).get(setor_sel, [])
        op_reg = c2.selectbox("Colaborador", sorted(colabs)) if colabs else c2.text_input("Nome do Colaborador")

        with st.form("form_reg", clear_on_submit=True):
            at_list = st.session_state.config_painel.get(setor_sel, [])
            at_sel = st.selectbox("Atividade", at_list)
            v1, v2 = st.columns(2)
            v_in = v1.number_input("Qtd Entrada", min_value=0, step=1)
            v_out = v2.number_input("Qtd Tratada", min_value=0, step=1)
            
            if st.form_submit_button("GRAVAR ATIVIDADE"):
                if setor_sel and at_sel:
                    novo = pd.DataFrame([{"Data": data_reg.strftime("%Y-%m-%d"), "Operador": op_reg.strip().upper(), 
                                          "Setor": setor_sel, "Atividade": at_sel, 
                                          "Quantidade Entrada": int(v_in), "Quantidade Tratada": int(v_out)}])
                    header = not os.path.exists(DB_LANCAMENTOS)
                    novo.to_csv(DB_LANCAMENTOS, mode='a', index=False, header=header, encoding='utf-8')
                    st.success("Lançamento realizado!")
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # --- ABA 2: PAINEL 360 ---
    with aba_painel:
        df = carregar_dados()
        if df.empty:
            st.info("Nenhum dado para exibir.")
        else:
            renderizar_painel_360(df, "Visão Geral")

    # --- ABA 3: CONFIGURAÇÕES (Apenas para ADM) ---
    with aba_gestao:
        if user.get('role') == "ADM":
            st.subheader("Configurações do Sistema")
            novo_set = st.text_input("Novo Setor")
            if st.button("Adicionar Setor"):
                st.session_state.config_painel[novo_set] = []
                st.session_state.config_painel.setdefault("colaboradores", {})[novo_set] = []
                salvar_config(st.session_state.config_painel)
                st.rerun()
        else:
            st.warning("Apenas administradores podem acessar esta aba.")
