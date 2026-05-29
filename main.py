import streamlit as st
import pandas as pd
    
st.set_page_config(
    page_title="Admin Parque Aliança",
    layout="wide",
    page_icon="📊",
)

st.markdown("""
    <style>
    .card {
        background-color: #ffffff; padding: 15px; border-radius: 10px;
        margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 5px solid #002366;
    }
    .card-header { font-weight: bold; font-size: 1rem; color: #1e293b; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        height: 45px; background-color: #f0f2f6;
        border-radius: 10px 10px 0px 0px; padding: 0px 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #002366 !important; color: white !important;
    }
    div[data-testid="metric-container"] {
        background-color: white; border: 1px solid #e6e9ef;
        padding: 15px; border-radius: 12px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# ─── Auth ─────────────────────────────────────────────────────────────────────
from auth import login, tem_modulo, usuario_atual, logout, bootstrap_admin, ROLES

bootstrap_admin()   # ← REMOVA esta linha após o primeiro login bem-sucedido

usuario = login()

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    u         = usuario_atual()
    role_info = ROLES.get(u.get("role", "viewer"), ROLES["viewer"])
    st.markdown(f"**{role_info['icon']} {u.get('nome', u.get('email', ''))}**")
    st.caption(f"{u.get('email', '')} · {role_info['label']}")
    st.divider()
    if st.button("🚪 Sair", use_container_width=True):
        logout()

# ─── Dados globais ────────────────────────────────────────────────────────────
from db import carregar_membros, carregar_relatorios
from utils.normalizacao import normalizar_nome_no_banco, obter_mes_atual_str

membros_db        = carregar_membros()
relatorios_brutos = carregar_relatorios()

df = pd.DataFrame(relatorios_brutos) if relatorios_brutos else pd.DataFrame()
if not df.empty:
    df["horas"] = pd.to_numeric(df["horas"], errors="coerce").fillna(0)
    df["estudos_biblicos"] = pd.to_numeric(
        df.get("estudos_biblicos", 0), errors="coerce"
    ).fillna(0)

    def _validar_envio(row):
        nome_oficial = normalizar_nome_no_banco(row["nome"], membros_db.keys())
        if nome_oficial:
            dados_m      = membros_db[nome_oficial]
            cat_original = dados_m.get("categoria", "PUBLICADOR")
            cat_final    = (
                "PIONEIRO AUXILIAR"
                if cat_original == "PUBLICADOR" and row["horas"] >= 15
                else cat_original
            )
            return pd.Series([nome_oficial, cat_final, "IDENTIFICADO"])
        return pd.Series([row["nome"], "DESCONHECIDO", "TRIAGEM"])

    df[["nome_oficial", "cat_oficial", "status_validacao"]] = df.apply(
        _validar_envio, axis=1
    )
    df["mes_referencia"] = df["mes_referencia"].str.upper()

meses_disponiveis = (
    sorted(df["mes_referencia"].unique()) if not df.empty else [obter_mes_atual_str()]
)
mes_sel = st.sidebar.selectbox(
    "📅 Mês de Análise",
    meses_disponiveis,
    index=len(meses_disponiveis) - 1,
)
df_mes = df[df["mes_referencia"] == mes_sel] if not df.empty else pd.DataFrame()

# ─── Título ───────────────────────────────────────────────────────────────────
st.title("📊 Gestão Parque Aliança")

# ─── Abas principais ──────────────────────────────────────────────────────────
nomes_abas = [
    "📋 RELATÓRIOS",
    "⚠️ TRIAGEM",
    "📈 CONSOLIDADO",
    "📢 ANÚNCIOS",
    "⚙️ CONFIGURAÇÃO",
]
if tem_modulo("passagens"):
    nomes_abas.append("🚌 PASSAGENS")

tabs = st.tabs(nomes_abas)

with tabs[0]:
    relatorios.render(df, membros_db, mes_sel)

with tabs[1]:
    triagem.render(df, df_mes, membros_db)

with tabs[2]:
    consolidado.render(df, membros_db)

with tabs[3]:
    anuncios.render()

with tabs[4]:
    configuracao.render(df, membros_db, mes_sel)

if tem_modulo("passagens"):
    with tabs[5]:
        passagens.render()
        
st.caption("v5.0.0 | Parque Aliança | Gestão Modular")
