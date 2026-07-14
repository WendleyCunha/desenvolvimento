import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import os
import calendar
import io
import hashlib
import time
import base64

# ── Fuso horário de Brasília ──────────────────────────────────────────────────
FUSO_BR = ZoneInfo("America/Sao_Paulo")

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.utils import ImageReader

# Excel
import xlsxwriter

# ── Banco de dados Firestore ──────────────────────────────────────────────────
from database import (
    init_db, cfg_get, cfg_set,
    clientes_listar, clientes_inserir, clientes_atualizar, clientes_deletar,
    encomendas_listar, encomendas_inserir, encomendas_atualizar,
    encomendas_buscar, encomendas_cancelar, encomendas_deletar_completo,
    gastos_listar, gastos_inserir, gastos_atualizar, gastos_deletar, gastos_deletar_pagos,
    cronograma_listar, cronograma_inserir, cronograma_atualizar,
    cronograma_deletar, cronograma_com_cliente,
    campo_horas_listar, campo_horas_historico, campo_horas_inserir, campo_horas_deletar,
    peso_listar, peso_upsert,
)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Lila Closet Atelier",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════════
# CSS GLOBAL
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {
  background-color: #f4f1ee !important;
  font-family: 'Inter', sans-serif;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] {
  background: #111111 !important;
  border-right: 1px solid #2a2a2a !important;
}
[data-testid="stSidebar"] * { color: #cccccc !important; }
[data-testid="stSidebar"] .stButton > button {
  background: #c9a227 !important; color: #111 !important;
  border: none !important; border-radius: 8px !important;
  font-weight: 600 !important; width: 100%;
}

/* ── Hero header ── */
.hero-header {
  background: linear-gradient(135deg, #1a0f0a 0%, #3d1f10 50%, #6b3a22 100%);
  border-radius: 16px; padding: 1.5rem 2.25rem;
  margin-bottom: 1.5rem; display: flex; align-items: center; gap: 1.5rem;
  box-shadow: 0 8px 32px rgba(0,0,0,0.22);
}
.hero-logo { height: 68px; width: auto; border-radius: 10px; object-fit: contain; }
.hero-icon { font-size: 3rem; }
.hero-title {
  font-family: 'Playfair Display', serif; font-size: 1.9rem;
  font-weight: 700; color: #f5e6d3; margin: 0; line-height: 1.2;
}
.hero-subtitle { font-size: 0.8rem; color: #c9a882; letter-spacing: 2px;
  text-transform: uppercase; margin-top: 5px; }

/* ── Abas (nível 1 e 2) ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  background: white;
  border-radius: 14px;
  padding: 6px;
  gap: 6px;
  box-shadow: 0 4px 16px rgba(61,31,16,0.08);
  border: 1px solid #f0e6d8;
  flex-wrap: wrap;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  border-radius: 10px !important;
  font-weight: 600;
  font-size: 0.85rem;
  padding: 10px 18px !important;
  color: #8b7355;
  transition: all 0.2s ease;
  border: 1px solid transparent !important;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
  background: #faf5ec;
  color: #6b3a22;
  border: 1px solid #f0e2ca !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
  background: linear-gradient(135deg, #3d1f10, #6b3a22) !important;
  color: white !important;
  box-shadow: 0 3px 10px rgba(61,31,16,0.28);
}
[data-testid="stTabs"] [aria-selected="true"]:hover {
  color: white !important;
  border: 1px solid transparent !important;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { display: none; }
[data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }
[data-testid="stTabs"] [data-baseweb="tab-panel"] { padding-top: 1.1rem; }

/* ── Cards ── */
.kcard {
  background: white; border-radius: 14px; padding: 1.2rem 1.4rem;
  box-shadow: 0 2px 12px rgba(0,0,0,0.07); border-left: 4px solid #c9a227;
  margin-bottom: 0.75rem;
}
.kcard-title { font-family: 'Playfair Display', serif; font-size: 1rem; font-weight: 600; color: #1a0f0a; }
.kcard-sub { font-size: 0.78rem; color: #8b7355; margin-top: 3px; }

/* ── Progresso campo ── */
.campo-card {
  background: linear-gradient(135deg, #1a3a5c 0%, #1e5fa8 100%);
  border-radius: 14px; padding: 1.4rem 1.6rem; color: white;
  box-shadow: 0 4px 18px rgba(0,0,80,0.18); margin-bottom: 0.75rem;
}
.campo-title { font-family: 'Playfair Display', serif; font-size: 1.1rem; font-weight: 700; color: #ffe0b2; }
.campo-num { font-size: 2.5rem; font-weight: 800; color: white; line-height: 1; }
.campo-sub { font-size: 0.78rem; color: #bbdefb; margin-top: 4px; }

/* ── Emagrecimento card ── */
.peso-card {
  background: linear-gradient(135deg, #1b5e20 0%, #388e3c 100%);
  border-radius: 14px; padding: 1.4rem 1.6rem; color: white;
  box-shadow: 0 4px 18px rgba(0,80,0,0.18); margin-bottom: 0.75rem;
}
.peso-title { font-family: 'Playfair Display', serif; font-size: 1.1rem; font-weight: 700; color: #c8e6c9; }
.peso-num { font-size: 2.5rem; font-weight: 800; color: white; line-height: 1; }
.peso-sub { font-size: 0.78rem; color: #a5d6a7; margin-top: 4px; }

/* ── Badge ── */
.badge {
  display: inline-block; padding: 3px 9px; border-radius: 20px;
  font-size: 0.72rem; font-weight: 600;
}
.badge-gold   { background: #fff8e1; color: #8a6200; }
.badge-green  { background: #e8f5e9; color: #1e7e34; }
.badge-amber  { background: #fff3cd; color: #856404; }
.badge-red    { background: #ffeeee; color: #b03030; }
.badge-blue   { background: #e3f2fd; color: #1565c0; }
.badge-navy   { background: #e8eaf6; color: #283593; }

/* ── Stepper ── */
.step-bar { display: flex; align-items: center; gap: 0; }
.step-item { display: flex; flex-direction: column; align-items: center; flex: 1; position: relative; }
.step-item:not(:last-child)::after {
  content: ''; position: absolute; top: 14px; left: 55%; right: -45%;
  height: 2px; background: #ededed; z-index: 0;
}
.step-item.done:not(:last-child)::after { background: #c9a227; }
.step-dot {
  width: 28px; height: 28px; border-radius: 50%; border: 2px solid #ededed;
  background: white; display: flex; align-items: center; justify-content: center;
  z-index: 1; font-size: 0.7rem; font-weight: 700; color: #ccc;
}
.step-item.done  .step-dot { background: #c9a227; border-color: #c9a227; color: white; }
.step-item.active .step-dot { border-color: #c9a227; color: #c9a227; }
.step-lbl { font-size: 0.65rem; color: #888; margin-top: 5px; text-align: center; }
.step-item.done .step-lbl  { color: #333; }
.step-item.active .step-lbl { color: #c9a227; font-weight: 600; }

/* ── Métricas ── */
div[data-testid="metric-container"] {
  background: white; border: 1px solid #ededed; padding: 14px;
  border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

/* ── Alertas financeiros ── */
.fin-alerta {
  background: #fff8e1; border-left: 4px solid #c9a227; border-radius: 0 10px 10px 0;
  padding: 10px 14px; font-size: 0.82rem; color: #7a5c00; margin: 6px 0;
}
.fin-danger {
  background: #ffeeee; border-left: 4px solid #c0392b; border-radius: 0 10px 10px 0;
  padding: 10px 14px; font-size: 0.82rem; color: #7a1a1a; margin: 6px 0;
}
.fin-ok {
  background: #e8f5e9; border-left: 4px solid #2e7d32; border-radius: 0 10px 10px 0;
  padding: 10px 14px; font-size: 0.82rem; color: #1e5e22; margin: 6px 0;
}

/* ── Danger zone ── */
.danger-zone {
  background: #fff0f0; border: 2px solid #e53935; border-radius: 12px;
  padding: 1.2rem 1.4rem; margin-top: 0.5rem;
}

/* ── Separador pessoal ── */
.sep-pessoal {
  background: linear-gradient(90deg, #1a3a5c, #1e5fa8, #1a3a5c);
  height: 3px; border-radius: 2px; margin: 1.5rem 0;
}

/* ── Inputs ── */
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea {
  border-radius: 10px !important; border-color: #e0d5c9 !important;
}

/* ── Botões ── */
[data-testid="stButton"] > button { border-radius: 10px !important; font-weight: 500 !important; }
[data-testid="stButton"] > button[kind="primary"] {
  background: linear-gradient(135deg, #3d1f10, #6b3a22) !important;
  border: none !important; color: white !important;
}
[data-testid="stDownloadButton"] > button {
  background: linear-gradient(135deg, #1b5e20, #2e7d32) !important;
  color: white !important; border: none !important;
  border-radius: 10px !important; font-weight: 600 !important; width: 100%;
}
[data-testid="stLinkButton"] > a {
  background: linear-gradient(135deg, #1565c0, #1976d2) !important;
  color: white !important; border: none !important;
  border-radius: 10px !important; font-weight: 600 !important;
  text-decoration: none !important; display: block; text-align: center; padding: 8px 16px;
}

/* ── Card do dia no calendário (card único e integrado) ── */
div[class*="st-key-calcell_"] {
  background: #fff;
  border: 1px solid #ecdfc9;
  border-left: 4px solid #c9a227;
  border-radius: 12px;
  box-shadow: 0 2px 10px rgba(61,31,16,0.07);
  padding: 8px 8px 4px;
  margin-bottom: 10px;
  transition: box-shadow .15s ease, transform .15s ease;
}
div[class*="st-key-calcell_"]:hover {
  box-shadow: 0 8px 20px rgba(61,31,16,0.15);
  transform: translateY(-2px);
}
div[class*="st-key-calcell_hoje_"] {
  background: #fdf6ee;
  border-left: 4px solid #6b3a22;
  box-shadow: 0 4px 16px rgba(61,31,16,0.16);
}
.cal-day-inner { min-height: 58px; }
.cal-day-num { color: #3d1f10; font-size: 0.82rem; font-weight: 700; }
.cal-task-tag {
  font-size: 0.6rem; color: #8a6200; margin-top: 3px;
  background: #fff8e1; border-radius: 5px; padding: 2px 5px;
}
.cal-task-cliente { color: #3d1f10; font-weight: 700; font-size: 0.58rem; }

/* Botão "+" agora vive DENTRO do mesmo card, sem bordas próprias — parece um só elemento */
div[class*="st-key-calcell_"] div[data-testid="stButton"] {
  margin-top: 4px;
}
div[class*="st-key-calcell_"] div[data-testid="stButton"] button {
  padding: 2px 0 !important;
  min-height: 20px !important;
  font-size: 0.72rem !important;
  background: transparent !important;
  color: #8b7355 !important;
  border: none !important;
  border-top: 1px dashed #ecdfc9 !important;
  border-radius: 0 !important;
  margin-top: 2px !important;
  box-shadow: none !important;
}
div[class*="st-key-calcell_"] div[data-testid="stButton"] button:hover {
  color: #c9a227 !important;
  background: transparent !important;
}

/* ── Cards clicáveis (pedidos) que abrem popup de detalhes ── */
div[class*="st-key-pedcard_"] button {
  text-align: left !important; justify-content: flex-start !important;
  background: #fff !important; border: 1px solid #ecdfc9 !important;
  border-bottom: none !important; border-left: 4px solid #c9a227 !important;
  border-radius: 12px 12px 0 0 !important; color: #3d1f10 !important;
  font-weight: 700 !important; font-size: 0.88rem !important;
  padding: 12px 14px 8px !important; margin-bottom: 0 !important;
  transition: background .15s, box-shadow .15s;
}
div[class*="st-key-pedcard_"] button:hover {
  background: #faf5ec !important; border-color: #c9a227 !important;
}
.lila-cardbody {
  background: #fff; border: 1px solid #ecdfc9; border-top: none;
  border-left: 4px solid #c9a227; border-radius: 0 0 12px 12px;
  padding: 6px 14px 14px; margin: -10px 0 16px;
  box-shadow: 0 2px 10px rgba(61,31,16,0.06);
}
.lila-cardsub { font-size: 0.78rem; color: #8b7355; margin-bottom: 6px; }
.lila-bar { background: #f0e6d8; border-radius: 4px; height: 6px; margin: 6px 0 3px; }
.lila-bar > div { background: linear-gradient(90deg,#c9a227,#6b3a22); height: 6px; border-radius: 4px; }

/* ── KPI Cards (topo do sistema) ── */
.kpi-card {
  border-radius: 16px; padding: 18px 20px; margin-bottom: 4px;
  box-shadow: 0 6px 20px rgba(61,31,16,0.10);
  transition: transform .15s, box-shadow .15s;
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 10px 26px rgba(61,31,16,0.16); }
.kpi-label {
  font-size: 0.74rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.6px; opacity: 0.88;
}
.kpi-value { font-size: 2.1rem; font-weight: 800; line-height: 1.15; margin-top: 4px; }
.kpi-sub { font-size: 0.74rem; opacity: 0.85; margin-top: 5px; }
.kpi-bar { background: rgba(0,0,0,0.08); border-radius: 4px; height: 7px; margin: 8px 0 2px; }
.kpi-bar > div {
  background: linear-gradient(90deg,#c9a227,#6b3a22);
  height: 7px; border-radius: 4px; transition: width .3s ease;
}

.kpi-brown { background: linear-gradient(135deg,#3d1f10 0%,#6b3a22 100%); color: #f5e6d3; }
.kpi-brown .kpi-label, .kpi-brown .kpi-sub { color: #e8d4bc; }
.kpi-gold  { background: linear-gradient(135deg,#c9a227 0%,#8a6200 100%); color: #fff8e8; }
.kpi-gold  .kpi-label, .kpi-gold .kpi-sub { color: #fdf1d6; }
.kpi-cream { background: #fdf6ee; color: #3d1f10; border: 1px solid #ecdfc9;
  box-shadow: 0 2px 12px rgba(61,31,16,0.06); }
.kpi-cream .kpi-label, .kpi-cream .kpi-sub { color: #8b7355; }
.kpi-cream .kpi-bar { background: #f0e6d8; }
.kpi-green { background: linear-gradient(135deg,#1b5e20 0%,#2e7d32 100%); color: #e8f5e9; }
.kpi-green .kpi-label, .kpi-green .kpi-sub { color: #d4ecd6; }
.kpi-red   { background: linear-gradient(135deg,#7a1a1a 0%,#c0392b 100%); color: #ffeeee; }
.kpi-red   .kpi-label, .kpi-red .kpi-sub { color: #ffd9d9; }

hr { border-color: #e8dfd5 !important; }
[data-testid="stSuccess"], [data-testid="stInfo"],
[data-testid="stWarning"], [data-testid="stError"] { border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════════════════════
ETAPAS = {
    1: ("🤝", "Visita"),
    2: ("💰", "Sinal"),
    3: ("🛍️", "Tecidos"),
    4: ("🪡", "Confecção"),
    5: ("👗", "Prova"),
    6: ("🎁", "Entrega"),
    7: ("✅", "Concluído"),
}

DIC_MEDIDAS = {
    "Ombros":      "ombros",
    "Costas":      "costas",
    "Alt. Busto":  "alt_busto",
    "Alt. Frente": "alt_frente",
    "Busto":       "busto",
    "Cintura":     "cintura",
    "Quadril":     "quadril",
    "Larg. Braço": "larg_braco",
    "Comp. Braço": "comp_braco",
    "Comprimento": "comprimento",
    "Comp. Perna": "comp_perna",
    "Coxa":        "coxa",
    "Gancho":      "gancho",
    "Colarinho":   "colarinho",
}

CAT_GASTOS = [
    "Tecido", "Aviamentos/Linhas", "Zíper/Botões", "Transporte",
    "Manutenção de máquina", "Marketing/Redes Sociais",
    "Embalagem", "Água/Luz/Aluguel", "Impostos/Taxas", "Outros",
]

MESES_PT = [
    "Janeiro","Fevereiro","Março","Abril","Maio","Junho",
    "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro",
]

SENHA_DELETE = "Qmerd@10"

META_HORAS_CAMPO = 50.0
META_PESO_KG     = 57.0
PESO_INICIAL_KG  = 70.0

LOGO_PATH = "lila.png"

# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO DO BANCO
# ══════════════════════════════════════════════════════════════════════════════
init_db()

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def agora_br() -> datetime:
    """Data e hora atuais no fuso horário de Brasília (America/Sao_Paulo)."""
    return datetime.now(FUSO_BR)

def hoje_brasilia() -> date:
    """Data atual (apenas o dia) no fuso horário de Brasília."""
    return agora_br().date()

def converter_para_data(valor):
    if not valor or str(valor) in ("None", "NoneType", "", "nan"):
        return hoje_brasilia()
    try:
        if isinstance(valor, (date, datetime)):
            return valor if isinstance(valor, date) else valor.date()
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except Exception:
        return hoje_brasilia()

def formatar_data_br(data_iso):
    """Formata para o padrão brasileiro dd/mm/aaaa (somente data)."""
    try:
        if isinstance(data_iso, (date, datetime)):
            return data_iso.strftime("%d/%m/%Y")
        return datetime.strptime(str(data_iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(data_iso)

def formatar_data_hora_br(valor) -> str:
    """
    Formata um datetime (ou string ISO com data e hora) para o padrão
    brasileiro dd/mm/aaaa às HH:MM, sempre convertido para o horário de Brasília.
    Retorna '—' se o valor estiver vazio/ausente (ex: registros antigos sem hora salva).
    """
    if valor is None or str(valor).strip() in ("", "None", "NoneType", "nan", "NaT"):
        return "—"
    try:
        if isinstance(valor, datetime):
            dt = valor
        else:
            dt = datetime.fromisoformat(str(valor))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=FUSO_BR)
        else:
            dt = dt.astimezone(FUSO_BR)
        return dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return str(valor)

def brl(valor: float) -> str:
    if valor is None:
        valor = 0.0
    return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def pct_str(valor: float, total: float) -> str:
    if total <= 0:
        return "0%"
    return f"{(valor/total*100):.1f}%"

def get_logo_base64() -> str | None:
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

# ══════════════════════════════════════════════════════════════════════════════
# POPUP — NOVA ENCOMENDA RÁPIDA (a partir do calendário)
# ══════════════════════════════════════════════════════════════════════════════
@st.dialog("🛍️ Nova Encomenda Rápida", width="large")
def dialog_nova_encomenda(data_pre: date | None = None):
    # ── Estado "encomenda recém-criada" — mostra o resultado/contrato SEM fechar o popup ──
    resultado = st.session_state.get("_dlg_enc_resultado")
    if resultado:
        st.success(f"✅ Encomenda **{resultado['peca']}** criada para **{resultado['cliente']}**!")
        if resultado.get("pdf_bytes"):
            col_pdf, col_gov = st.columns(2)
            col_pdf.download_button(
                "📥 BAIXAR CONTRATO PDF", data=resultado["pdf_bytes"],
                file_name=f"Contrato_{resultado['cliente'].replace(' ','_')}.pdf",
                mime="application/pdf", use_container_width=True, key="dlg_dl_pdf_resultado",
            )
            col_gov.link_button("✍️ ASSINAR VIA GOV.BR",
                url="https://assinador.iti.br/assinatura/index.xhtml",
                use_container_width=True)
        else:
            st.info("💡 Preencha CPF e RG (seção Dados para Contrato) para gerar o contrato automaticamente.")
        if st.button("✅ Fechar", use_container_width=True, type="primary", key="dlg_btn_fechar_resultado"):
            del st.session_state["_dlg_enc_resultado"]
            st.rerun()
        return

    d_base = data_pre or hoje_brasilia()
    st.caption(f"📅 Data de referência: **{formatar_data_br(d_base)}**")

    df_clis_dlg = clientes_listar()
    clis_dlg = df_clis_dlg["nome"].tolist() if not df_clis_dlg.empty else []

    st.markdown("##### 👤 Cliente")
    modo_cli = st.radio(
        "Cliente", ["Selecionar existente", "Cadastrar nova"],
        horizontal=True, key="dlg_modo_cli", label_visibility="collapsed",
        index=0 if clis_dlg else 1,
    )

    cli_tel_dlg = ""
    if modo_cli == "Selecionar existente" and clis_dlg:
        cli_sel_dlg = st.selectbox("Cliente *", clis_dlg, key="dlg_cli_sel")
    else:
        col_cn1, col_cn2 = st.columns(2)
        cli_sel_dlg = col_cn1.text_input("Nome da nova cliente *", key="dlg_cli_novo")
        cli_tel_dlg = col_cn2.text_input("Telefone / WhatsApp", key="dlg_cli_tel")

    st.markdown("##### 🧵 Peça / Serviço")
    peca_dlg = st.text_input("Peça / Serviço *", placeholder="Ex: Vestido de festa…", key="dlg_peca")
    descricao_dlg = st.text_area("Descrição detalhada", key="dlg_descricao", height=70)

    st.markdown("##### 💰 Valores")
    col_v1, col_v2, col_v3 = st.columns(3)
    v_total_dlg = col_v1.number_input("Valor Total (R$)", min_value=0.0, step=50.0, format="%.2f", key="dlg_valor")
    v_sinal_dlg = col_v2.number_input("Sinal / Entrada (R$)", min_value=0.0, step=50.0, format="%.2f", key="dlg_sinal")
    forma_pag_dlg = col_v3.selectbox("Forma de Pagamento",
        ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"], key="dlg_forma_pag")

    st.markdown("##### 📅 Datas")

    d_encomenda_dlg = st.date_input(
        "🗓️ Data da Encomenda", value=d_base, key="dlg_encomenda", format="DD/MM/YYYY"
    )
    d_visita_dlg = st.date_input(
        "📏 Data Medidas", value=d_base, key="dlg_visita", format="DD/MM/YYYY"
    )
    d_confeccao_dlg = st.date_input(
        "🪡 Data da Confecção", value=d_visita_dlg + timedelta(days=7),
        key="dlg_confeccao", format="DD/MM/YYYY"
    )
    d_prova_dlg = st.date_input(
        "👗 Data da Prova", value=d_base + timedelta(days=25), key="dlg_prova", format="DD/MM/YYYY"
    )

    tem_prova2_dlg = st.checkbox("Precisa de uma segunda prova?", key="dlg_tem_prova2")
    d_prova2_dlg = None
    if tem_prova2_dlg:
        d_prova2_dlg = st.date_input(
            "👗 Data da 2ª Prova", value=d_prova_dlg + timedelta(days=7),
            key="dlg_prova2", format="DD/MM/YYYY",
        )

    precisa_tecido_dlg = st.checkbox("Precisa comprar tecido?", key="dlg_tecido")
    d_tecido_dlg = d_visita_dlg + timedelta(days=3)
    if precisa_tecido_dlg:
        d_tecido_dlg = st.date_input(
            "🛍️ Data Compra do Tecido", value=d_tecido_dlg, key="dlg_data_tecido", format="DD/MM/YYYY"
        )

    d_entrega_dlg = st.date_input(
        "🎁 Data de Entrega", value=d_base + timedelta(days=30), key="dlg_entrega", format="DD/MM/YYYY"
    )

    st.markdown("##### 📄 Dados para Contrato")
    st.caption("Preencha CPF e RG para o contrato ser gerado automaticamente assim que a encomenda for criada.")
    col_c1, col_c2 = st.columns(2)
    cpf_dlg = col_c1.text_input("CPF da cliente", placeholder="000.000.000-00", key="dlg_cpf")
    rg_dlg  = col_c2.text_input("RG da cliente",  placeholder="00.000.000-0", key="dlg_rg")
    obs_dlg = st.text_area("Observações", key="dlg_obs", height=68)

    st.markdown("")
    col_ok, col_cancel = st.columns(2)

    if col_ok.button("✅ Criar Encomenda", use_container_width=True, type="primary", key="dlg_btn_ok"):
        nome_final = cli_sel_dlg.strip() if isinstance(cli_sel_dlg, str) else cli_sel_dlg

        if not nome_final:
            st.error("Informe o nome da cliente.")
            return
        if not peca_dlg.strip():
            st.error("Informe a peça / serviço.")
            return

        if modo_cli != "Selecionar existente":
            clientes_inserir({
                "nome": nome_final, "telefone": cli_tel_dlg.strip(),
                "criado_em": agora_br().isoformat(),
            })

        e_id = encomendas_inserir({
            "cliente": nome_final, "peca": peca_dlg.strip(),
            "descricao": descricao_dlg.strip(), "valor_total": v_total_dlg, "sinal": v_sinal_dlg,
            "valor_recebido": v_sinal_dlg,
            "etapa": 1, "precisa_tecido": 1 if precisa_tecido_dlg else 0,
            "data_encomenda": d_encomenda_dlg.isoformat(),
            "data_visita":    d_visita_dlg.isoformat(),
            "data_tecido":    d_tecido_dlg.isoformat(),
            "data_confeccao": d_confeccao_dlg.isoformat(),
            "data_prova":     d_prova_dlg.isoformat(),
            "tem_prova2":     1 if tem_prova2_dlg else 0,
            "data_prova2":    d_prova2_dlg.isoformat() if d_prova2_dlg else "",
            "data_entrega":   d_entrega_dlg.isoformat(),
            "cpf_cliente": cpf_dlg.strip(), "rg_cliente": rg_dlg.strip(),
            "forma_pagamento": forma_pag_dlg, "observacoes": obs_dlg.strip(),
            "cancelado": 0,
            "criado_em": agora_br().isoformat(),
        })

        desc_dlg = f"{peca_dlg.strip()} ({nome_final})"
        tarefas_auto_dlg = [
            (f"📝 Encomenda: {desc_dlg}", "Costura", 0.5, d_encomenda_dlg.isoformat()),
            (f"📏 Medidas: {desc_dlg}",   "Costura", 1.0, d_visita_dlg.isoformat()),
        ]
        if precisa_tecido_dlg:
            tarefas_auto_dlg.append((f"🛍️ Tecido: {desc_dlg}", "Compras", 1.0, d_tecido_dlg.isoformat()))
        tarefas_auto_dlg.append((f"🪡 Confecção: {desc_dlg}", "Costura", 3.0, d_confeccao_dlg.isoformat()))
        tarefas_auto_dlg.append((f"👗 Prova: {desc_dlg}",     "Costura", 1.0, d_prova_dlg.isoformat()))
        if tem_prova2_dlg and d_prova2_dlg:
            tarefas_auto_dlg.append((f"👗 2ª Prova: {desc_dlg}", "Costura", 1.0, d_prova2_dlg.isoformat()))
        tarefas_auto_dlg.append((f"🎁 Entrega: {desc_dlg}",   "Costura", 0.5, d_entrega_dlg.isoformat()))

        for tarefa_a, cat_a, hrs_a, dt_a in tarefas_auto_dlg:
            cronograma_inserir({
                "tarefa": tarefa_a, "categoria": cat_a, "horas": hrs_a,
                "data": dt_a, "frequencia": "Pontual", "concluida": 0,
                "encomenda_id": e_id, "tipo_agenda": "Trabalho",
            })

        pdf_bytes_dlg = None
        if cpf_dlg.strip() and rg_dlg.strip():
            enc_dict_pdf = {
                "cliente": nome_final, "peca": peca_dlg.strip(),
                "descricao": descricao_dlg.strip(), "valor_total": v_total_dlg,
                "sinal": v_sinal_dlg, "forma_pagamento": forma_pag_dlg,
                "data_encomenda": d_encomenda_dlg.isoformat(),
                "data_visita": d_visita_dlg.isoformat(),
                "data_tecido": d_tecido_dlg.isoformat() if precisa_tecido_dlg else "",
                "data_confeccao": d_confeccao_dlg.isoformat(),
                "data_prova": d_prova_dlg.isoformat(),
                "data_prova2": d_prova2_dlg.isoformat() if d_prova2_dlg else "",
                "data_entrega": d_entrega_dlg.isoformat(),
                "precisa_tecido": 1 if precisa_tecido_dlg else 0,
                "observacoes": obs_dlg.strip(),
            }
            pdf_bytes_dlg = gerar_pdf_contrato(enc_dict_pdf, cpf_dlg.strip(), rg_dlg.strip())

        st.session_state["_dlg_enc_resultado"] = {
            "cliente": nome_final, "peca": peca_dlg.strip(), "pdf_bytes": pdf_bytes_dlg,
        }
        st.success(f"✅ Encomenda **{peca_dlg.strip()}** criada para **{nome_final}**!")
        if pdf_bytes_dlg:
            col_pdf, col_gov = st.columns(2)
            col_pdf.download_button(
                "📥 BAIXAR CONTRATO PDF", data=pdf_bytes_dlg,
                file_name=f"Contrato_{nome_final.replace(' ','_')}.pdf",
                mime="application/pdf", use_container_width=True, key="dlg_dl_pdf_imediato",
            )
            col_gov.link_button("✍️ ASSINAR VIA GOV.BR",
                url="https://assinador.iti.br/assinatura/index.xhtml",
                use_container_width=True)
        else:
            st.info("💡 Preencha CPF e RG para gerar o contrato automaticamente.")
        if st.button("✅ Fechar", use_container_width=True, type="primary", key="dlg_btn_fechar_imediato"):
            del st.session_state["_dlg_enc_resultado"]
            st.rerun()
        return

    if col_cancel.button("❌ Cancelar", use_container_width=True, key="dlg_btn_cancel"):
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO FIXA — NOVA ENCOMENDA (visível direto na aba ENCOMENDAS, sem popup)
# ══════════════════════════════════════════════════════════════════════════════
def secao_nova_encomenda_inline():
    """
    Mesma lógica do dialog_nova_encomenda, mas renderizada direto na página
    (sem st.dialog). Isso evita que o formulário "suma" no celular quando o
    usuário troca de aba/app e o Streamlit reconecta a sessão.
    """
    resultado = st.session_state.get("_ne_resultado")
    if resultado:
        st.success(f"✅ Encomenda **{resultado['peca']}** criada para **{resultado['cliente']}**!")
        if resultado.get("pdf_bytes"):
            col_pdf, col_gov = st.columns(2)
            col_pdf.download_button(
                "📥 BAIXAR CONTRATO PDF", data=resultado["pdf_bytes"],
                file_name=f"Contrato_{resultado['cliente'].replace(' ','_')}.pdf",
                mime="application/pdf", use_container_width=True, key="ne_dl_pdf_resultado",
            )
            col_gov.link_button("✍️ ASSINAR VIA GOV.BR",
                url="https://assinador.iti.br/assinatura/index.xhtml",
                use_container_width=True)
        else:
            st.info("💡 Preencha CPF e RG (seção Dados para Contrato) para gerar o contrato automaticamente.")
        if st.button("➕ Cadastrar Outra Encomenda", use_container_width=True, type="primary", key="ne_btn_outra"):
            for k in list(st.session_state.keys()):
                if k.startswith("ne_"):
                    del st.session_state[k]
            del st.session_state["_ne_resultado"]
            st.rerun()
        return

    d_base = hoje_brasilia()

    df_clis_dlg = clientes_listar()
    clis_dlg = df_clis_dlg["nome"].tolist() if not df_clis_dlg.empty else []

    st.markdown("##### 👤 Cliente")
    modo_cli = st.radio(
        "Cliente", ["Selecionar existente", "Cadastrar nova"],
        horizontal=True, key="ne_modo_cli", label_visibility="collapsed",
        index=0 if clis_dlg else 1,
    )

    cli_tel_dlg = ""
    if modo_cli == "Selecionar existente" and clis_dlg:
        cli_sel_dlg = st.selectbox("Cliente *", clis_dlg, key="ne_cli_sel")
    else:
        col_cn1, col_cn2 = st.columns(2)
        cli_sel_dlg = col_cn1.text_input("Nome da nova cliente *", key="ne_cli_novo")
        cli_tel_dlg = col_cn2.text_input("Telefone / WhatsApp", key="ne_cli_tel")

    st.markdown("##### 🧵 Peça / Serviço")
    peca_dlg = st.text_input("Peça / Serviço *", placeholder="Ex: Vestido de festa…", key="ne_peca")
    descricao_dlg = st.text_area("Descrição detalhada", key="ne_descricao", height=70)

    st.markdown("##### 💰 Valores")
    col_v1, col_v2, col_v3 = st.columns(3)
    v_total_dlg = col_v1.number_input("Valor Total (R$)", min_value=0.0, step=50.0, format="%.2f", key="ne_valor")
    v_sinal_dlg = col_v2.number_input("Sinal / Entrada (R$)", min_value=0.0, step=50.0, format="%.2f", key="ne_sinal")
    forma_pag_dlg = col_v3.selectbox("Forma de Pagamento",
        ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"], key="ne_forma_pag")

    st.markdown("##### 📅 Datas")

    d_encomenda_dlg = st.date_input(
        "🗓️ Data da Encomenda", value=d_base, key="ne_encomenda", format="DD/MM/YYYY"
    )
    d_visita_dlg = st.date_input(
        "📏 Data Medidas", value=d_base, key="ne_visita", format="DD/MM/YYYY"
    )
    d_confeccao_dlg = st.date_input(
        "🪡 Data da Confecção", value=d_visita_dlg + timedelta(days=7),
        key="ne_confeccao", format="DD/MM/YYYY"
    )
    d_prova_dlg = st.date_input(
        "👗 Data da Prova", value=d_base + timedelta(days=25), key="ne_prova", format="DD/MM/YYYY"
    )

    tem_prova2_dlg = st.checkbox("Precisa de uma segunda prova?", key="ne_tem_prova2")
    d_prova2_dlg = None
    if tem_prova2_dlg:
        d_prova2_dlg = st.date_input(
            "👗 Data da 2ª Prova", value=d_prova_dlg + timedelta(days=7),
            key="ne_prova2", format="DD/MM/YYYY",
        )

    precisa_tecido_dlg = st.checkbox("Precisa comprar tecido?", key="ne_tecido")
    d_tecido_dlg = d_visita_dlg + timedelta(days=3)
    if precisa_tecido_dlg:
        d_tecido_dlg = st.date_input(
            "🛍️ Data Compra do Tecido", value=d_tecido_dlg, key="ne_data_tecido", format="DD/MM/YYYY"
        )

    d_entrega_dlg = st.date_input(
        "🎁 Data de Entrega", value=d_base + timedelta(days=30), key="ne_entrega", format="DD/MM/YYYY"
    )

    st.markdown("##### 📄 Dados para Contrato")
    st.caption("Preencha CPF e RG para o contrato ser gerado automaticamente assim que a encomenda for criada.")
    col_c1, col_c2 = st.columns(2)
    cpf_dlg = col_c1.text_input("CPF da cliente", placeholder="000.000.000-00", key="ne_cpf")
    rg_dlg  = col_c2.text_input("RG da cliente",  placeholder="00.000.000-0", key="ne_rg")
    obs_dlg = st.text_area("Observações", key="ne_obs", height=68)

    st.markdown("")
    if st.button("✅ Criar Encomenda", use_container_width=True, type="primary", key="ne_btn_ok"):
        nome_final = cli_sel_dlg.strip() if isinstance(cli_sel_dlg, str) else cli_sel_dlg

        if not nome_final:
            st.error("Informe o nome da cliente.")
            return
        if not peca_dlg.strip():
            st.error("Informe a peça / serviço.")
            return

        if modo_cli != "Selecionar existente":
            clientes_inserir({
                "nome": nome_final, "telefone": cli_tel_dlg.strip(),
                "criado_em": agora_br().isoformat(),
            })

        e_id = encomendas_inserir({
            "cliente": nome_final, "peca": peca_dlg.strip(),
            "descricao": descricao_dlg.strip(), "valor_total": v_total_dlg, "sinal": v_sinal_dlg,
            "valor_recebido": v_sinal_dlg,
            "etapa": 1, "precisa_tecido": 1 if precisa_tecido_dlg else 0,
            "data_encomenda": d_encomenda_dlg.isoformat(),
            "data_visita":    d_visita_dlg.isoformat(),
            "data_tecido":    d_tecido_dlg.isoformat(),
            "data_confeccao": d_confeccao_dlg.isoformat(),
            "data_prova":     d_prova_dlg.isoformat(),
            "tem_prova2":     1 if tem_prova2_dlg else 0,
            "data_prova2":    d_prova2_dlg.isoformat() if d_prova2_dlg else "",
            "data_entrega":   d_entrega_dlg.isoformat(),
            "cpf_cliente": cpf_dlg.strip(), "rg_cliente": rg_dlg.strip(),
            "forma_pagamento": forma_pag_dlg, "observacoes": obs_dlg.strip(),
            "cancelado": 0,
            "criado_em": agora_br().isoformat(),
        })

        desc_dlg = f"{peca_dlg.strip()} ({nome_final})"
        tarefas_auto_dlg = [
            (f"📝 Encomenda: {desc_dlg}", "Costura", 0.5, d_encomenda_dlg.isoformat()),
            (f"📏 Medidas: {desc_dlg}",   "Costura", 1.0, d_visita_dlg.isoformat()),
        ]
        if precisa_tecido_dlg:
            tarefas_auto_dlg.append((f"🛍️ Tecido: {desc_dlg}", "Compras", 1.0, d_tecido_dlg.isoformat()))
        tarefas_auto_dlg.append((f"🪡 Confecção: {desc_dlg}", "Costura", 3.0, d_confeccao_dlg.isoformat()))
        tarefas_auto_dlg.append((f"👗 Prova: {desc_dlg}",     "Costura", 1.0, d_prova_dlg.isoformat()))
        if tem_prova2_dlg and d_prova2_dlg:
            tarefas_auto_dlg.append((f"👗 2ª Prova: {desc_dlg}", "Costura", 1.0, d_prova2_dlg.isoformat()))
        tarefas_auto_dlg.append((f"🎁 Entrega: {desc_dlg}",   "Costura", 0.5, d_entrega_dlg.isoformat()))

        for tarefa_a, cat_a, hrs_a, dt_a in tarefas_auto_dlg:
            cronograma_inserir({
                "tarefa": tarefa_a, "categoria": cat_a, "horas": hrs_a,
                "data": dt_a, "frequencia": "Pontual", "concluida": 0,
                "encomenda_id": e_id, "tipo_agenda": "Trabalho",
            })

        pdf_bytes_dlg = None
        if cpf_dlg.strip() and rg_dlg.strip():
            enc_dict_pdf = {
                "cliente": nome_final, "peca": peca_dlg.strip(),
                "descricao": descricao_dlg.strip(), "valor_total": v_total_dlg,
                "sinal": v_sinal_dlg, "forma_pagamento": forma_pag_dlg,
                "data_encomenda": d_encomenda_dlg.isoformat(),
                "data_visita": d_visita_dlg.isoformat(),
                "data_tecido": d_tecido_dlg.isoformat() if precisa_tecido_dlg else "",
                "data_confeccao": d_confeccao_dlg.isoformat(),
                "data_prova": d_prova_dlg.isoformat(),
                "data_prova2": d_prova2_dlg.isoformat() if d_prova2_dlg else "",
                "data_entrega": d_entrega_dlg.isoformat(),
                "precisa_tecido": 1 if precisa_tecido_dlg else 0,
                "observacoes": obs_dlg.strip(),
            }
            pdf_bytes_dlg = gerar_pdf_contrato(enc_dict_pdf, cpf_dlg.strip(), rg_dlg.strip())

        st.session_state["_ne_resultado"] = {
            "cliente": nome_final, "peca": peca_dlg.strip(), "pdf_bytes": pdf_bytes_dlg,
        }
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PDF — CONTRATO
# ══════════════════════════════════════════════════════════════════════════════
def _marrom():  return colors.HexColor("#3d1f10")
def _bege():    return colors.HexColor("#fdf6ee")
def _dourado(): return colors.HexColor("#c9a227")

def gerar_pdf_contrato(enc: dict, cpf: str, rg: str) -> bytes:
    buf = io.BytesIO()
    styles = getSampleStyleSheet()

    s_titulo = ParagraphStyle("titulo", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=15, textColor=_marrom(),
        alignment=TA_CENTER, spaceAfter=3)
    s_subtit = ParagraphStyle("subtit", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8, textColor=_dourado(),
        alignment=TA_CENTER, spaceAfter=10, leading=12)
    s_cls_tit = ParagraphStyle("clt", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=10, textColor=_marrom(),
        spaceBefore=10, spaceAfter=3, leading=13)
    s_body = ParagraphStyle("body", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9.5, textColor=colors.HexColor("#2d1f14"),
        leading=15, spaceAfter=5, alignment=TA_JUSTIFY)
    s_rodape = ParagraphStyle("rodape", parent=styles["Normal"],
        fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#9e8a78"),
        alignment=TA_CENTER)

    seed = f"{enc.get('cliente','')}{enc.get('peca','')}{time.time()}"
    num_contrato = hashlib.md5(seed.encode()).hexdigest()[:10].upper()
    emitido_em_str = agora_br().strftime("%d/%m/%Y às %H:%M")

    dt_visita  = formatar_data_br(enc.get("data_visita", ""))
    dt_prova   = formatar_data_br(enc.get("data_prova", ""))
    tem_prova2 = bool(str(enc.get("data_prova2") or "").strip())
    dt_prova2  = formatar_data_br(enc.get("data_prova2", "")) if tem_prova2 else ""
    dt_entrega = formatar_data_br(enc.get("data_entrega", ""))
    dt_tecido  = formatar_data_br(enc.get("data_tecido", "")) if enc.get("precisa_tecido") else "—"
    dt_confec  = formatar_data_br(enc.get("data_confeccao", ""))

    valor_total   = float(enc.get("valor_total", 0) or 0)
    sinal         = float(enc.get("sinal", 0) or 0)
    restante      = valor_total - sinal
    forma_pag     = enc.get("forma_pagamento", "A combinar")
    cliente_nome  = enc.get("cliente", "—")
    peca_nome     = enc.get("peca", "—")
    descricao     = enc.get("descricao", "") or ""
    obs           = enc.get("observacoes", "") or ""

    cnpj_val = cfg_get("cnpj")
    tel_val  = cfg_get("telefone")
    end_val  = cfg_get("endereco")

    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=2.0*cm, leftMargin=2.0*cm,
        topMargin=2.2*cm,   bottomMargin=2.2*cm)
    story = []

    s_hdr_empresa = ParagraphStyle("hdr_emp", fontName="Helvetica-Bold", fontSize=14,
        textColor=colors.white, alignment=TA_LEFT, leading=18)
    s_hdr_slogan = ParagraphStyle("hdr_slo", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#f5e6d3"), alignment=TA_LEFT, leading=11, spaceBefore=2)
    s_hdr_info = ParagraphStyle("hdr_inf", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#f5dfc0"), alignment=TA_RIGHT, leading=12)

    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=2.4*cm, height=2.4*cm)
        logo_cell = logo_img
    else:
        logo_cell = Paragraph("🧵", ParagraphStyle("lc", fontName="Helvetica-Bold",
            fontSize=28, textColor=colors.HexColor("#c9a227"), alignment=TA_CENTER))

    nome_empresa_cell = Table([
        [Paragraph("LILA CLOSET ATELIER", s_hdr_empresa)],
        [Paragraph("Costura sob medida com excelência", s_hdr_slogan)],
    ], colWidths=["100%"])
    nome_empresa_cell.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),1),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))

    left_cell = Table([[logo_cell, nome_empresa_cell]], colWidths=[2.8*cm, "100%"])
    left_cell.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),0),
        ("BOTTOMPADDING",(0,0),(-1,-1),0),("LEFTPADDING",(0,0),(-1,-1),0),
        ("RIGHTPADDING",(0,0),(0,-1),8),("RIGHTPADDING",(1,0),(1,-1),0),
    ]))

    right_cell = Paragraph(
        f"CNPJ: {cnpj_val}<br/>{end_val}<br/>Tel.: {tel_val}", s_hdr_info)

    hdr_table = Table([[left_cell, right_cell]], colWidths=["60%","40%"])
    hdr_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),_marrom()),
        ("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14),
        ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE COSTURA SOB MEDIDA", s_titulo))
    story.append(Paragraph(
        f"Contrato N.º <b>{num_contrato}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Emitido em: <b>{emitido_em_str}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Validade jurídica: Art. 421 CC/2002 e MP 2.200-2/2001", s_subtit))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_dourado()))
    story.append(Spacer(1, 6))

    story.append(Paragraph("CLÁUSULA 1ª – IDENTIFICAÇÃO DAS PARTES", s_cls_tit))
    s_ptab = ParagraphStyle("pt", fontName="Helvetica", fontSize=9, leading=14,
        textColor=colors.HexColor("#2d1f14"))
    s_ptab_hdr = ParagraphStyle("pth", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.white, alignment=TA_CENTER)
    partes_data = [
        [Paragraph("<b>CONTRATADA</b>", s_ptab_hdr), Paragraph("<b>CONTRATANTE</b>", s_ptab_hdr)],
        [
            Paragraph(f"<b>LILA CLOSET ATELIER</b><br/>CNPJ: {cnpj_val}<br/>Tel.: {tel_val}<br/>{end_val}", s_ptab),
            Paragraph(f"<b>{cliente_nome}</b><br/>CPF: {cpf}<br/>RG: {rg}", s_ptab),
        ],
    ]
    partes_t = Table(partes_data, colWidths=["50%","50%"])
    partes_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),_marrom()),
        ("TOPPADDING",(0,0),(-1,0),8),("BOTTOMPADDING",(0,0),(-1,0),8),
        ("BACKGROUND",(0,1),(-1,1),_bege()),
        ("TOPPADDING",(0,1),(-1,1),10),("BOTTOMPADDING",(0,1),(-1,1),10),
        ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
        ("BOX",(0,0),(-1,-1),1,_dourado()),("LINEAFTER",(0,0),(0,-1),1,_dourado()),
        ("VALIGN",(0,1),(-1,1),"TOP"),
    ]))
    story.append(partes_t)
    story.append(Spacer(1, 6))

    story.append(Paragraph("CLÁUSULA 2ª – DO OBJETO DO CONTRATO", s_cls_tit))
    obj_text = (f"O presente contrato tem por objeto a <b>confecção sob medida</b> da seguinte peça: "
                f"<b>{peca_nome}</b>.")
    if descricao:
        obj_text += f" Descrição adicional: {descricao}."
    obj_text += (" A execução será realizada conforme as medidas fornecidas pela CONTRATANTE, "
                 "com os ajustes necessários durante a etapa de prova.")
    story.append(Paragraph(obj_text, s_body))

    story.append(Paragraph("CLÁUSULA 3ª – DOS PRAZOS E CRONOGRAMA", s_cls_tit))
    story.append(Paragraph(
        "O início da produção fica condicionado ao recebimento do <b>sinal acordado</b>. "
        "Os prazos abaixo são estimativas e podem ser ajustados por mútuo acordo.", s_body))

    s_et_hdr = ParagraphStyle("eth", fontName="Helvetica-Bold", fontSize=8.5,
        textColor=colors.white, alignment=TA_CENTER)
    etapas_rows = [
        [Paragraph("<b>Etapa</b>", s_et_hdr), Paragraph("<b>Descrição</b>", s_et_hdr), Paragraph("<b>Data Prevista</b>", s_et_hdr)],
        ["🤝 Visita",    "Tomada de medidas, briefing e validação do modelo",   dt_visita],
        ["🛍️ Tecidos",  "Compra e separação dos tecidos e aviamentos",         dt_tecido],
        ["🪡 Confecção", "Início da produção da peça na medida solicitada",     dt_confec],
        ["👗 Prova",     "Prova com a cliente para ajustes finos e acabamentos", dt_prova],
    ]
    if tem_prova2:
        etapas_rows.append(["👗 2ª Prova", "Segunda prova para ajustes adicionais", dt_prova2])
    etapas_rows.append(["🎁 Entrega",   "Entrega final da peça pronta e devidamente embalada", dt_entrega])
    cron_t = Table(etapas_rows, colWidths=["22%","48%","30%"])
    cron_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),_marrom()),("FONTSIZE",(0,1),(-1,-1),9),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),("ALIGN",(2,1),(2,-1),"CENTER"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,_bege()]),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("BOX",(0,0),(-1,-1),1,_dourado()),
        ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(cron_t)
    story.append(Spacer(1, 6))

    story.append(Paragraph("CLÁUSULA 4ª – DO VALOR E FORMA DE PAGAMENTO", s_cls_tit))
    story.append(Paragraph(
        f"O valor total acordado é de <b>{brl(valor_total)}</b>, "
        f"sendo <b>{brl(sinal)}</b> como sinal no ato da contratação "
        f"e o saldo de <b>{brl(restante)}</b> na entrega. "
        f"Forma de pagamento: <b>{forma_pag}</b>.", s_body))

    s_fin_hdr = ParagraphStyle("fnh", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)
    s_fin_hdr_r = ParagraphStyle("fnhr", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.white, alignment=TA_RIGHT)
    fin_rows = [
        [Paragraph("<b>Descrição</b>", s_fin_hdr), Paragraph("<b>Valor</b>", s_fin_hdr_r)],
        ["Valor Total do Serviço", brl(valor_total)],
        ["Sinal / Entrada (pago no ato)", brl(sinal)],
        ["Saldo Restante (pago na entrega)", brl(restante)],
        [Paragraph(f"<b>Forma de Pagamento:</b> {forma_pag}", ParagraphStyle("fp",
            fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#2d1f14"))), ""],
    ]
    fin_t = Table(fin_rows, colWidths=["65%","35%"])
    fin_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),_marrom()),("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("FONTSIZE",(0,1),(-1,-1),9.5),("FONTNAME",(1,1),(1,-2),"Helvetica-Bold"),
        ("TEXTCOLOR",(1,2),(1,2),colors.HexColor("#c9a227")),
        ("TEXTCOLOR",(1,3),(1,3),colors.HexColor("#1b5e20")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,_bege()]),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
        ("BOX",(0,0),(-1,-1),1,_dourado()),
        ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ("SPAN",(0,4),(1,4)),
    ]))
    story.append(fin_t)
    story.append(Spacer(1, 6))

    story.append(Paragraph("CLÁUSULA 5ª – DO CANCELAMENTO E DESISTÊNCIA", s_cls_tit))
    story.append(Paragraph(
        "5.1 – Em caso de desistência pela CONTRATANTE após a assinatura, "
        "o <b>sinal não será devolvido</b>, pois cobre reserva de agenda e compra de materiais. "
        "<br/>5.2 – Cancelamento por responsabilidade da CONTRATADA enseja devolução integral dos valores pagos. "
        "<br/>5.3 – Peças com medidas confirmadas e em produção não permitem alterações de modelo sem custo adicional.",
        s_body))

    story.append(Paragraph("CLÁUSULA 6ª – DA GARANTIA DE SERVIÇO", s_cls_tit))
    story.append(Paragraph(
        "A CONTRATADA garante <b>30 dias</b> a partir da entrega para identificação de defeitos "
        "de costura ou acabamento, obrigando-se à correção sem custo. "
        "Avarias por uso inadequado ou lavagem incorreta estão excluídas desta garantia.", s_body))

    story.append(Paragraph("CLÁUSULA 7ª – PROTEÇÃO DE DADOS (LGPD – Lei 13.709/2018)", s_cls_tit))
    story.append(Paragraph(
        "Os dados pessoais coletados (nome, CPF, RG, medidas) são utilizados exclusivamente "
        "para execução dos serviços contratados e não serão compartilhados com terceiros.", s_body))

    story.append(Paragraph("CLÁUSULA 8ª – DO FORO E ASSINATURA DIGITAL", s_cls_tit))
    story.append(Paragraph(
        "Fica eleito o foro da Comarca de Embu das Artes – SP. "
        "Este instrumento pode ser assinado digitalmente via <b>GOV.BR</b> "
        "(assinador.iti.br), com validade jurídica pela MP 2.200-2/2001.", s_body))

    if obs:
        story.append(Paragraph("OBSERVAÇÕES ADICIONAIS", s_cls_tit))
        story.append(Paragraph(obs, s_body))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e0d5c9")))
    story.append(Spacer(1, 8))
    gov_data = [[Paragraph(
        "✅ <b>ASSINAR DIGITALMENTE VIA GOV.BR — assinador.iti.br/assinatura/index.xhtml</b>",
        ParagraphStyle("gov", fontName="Helvetica-Bold", fontSize=8.5,
            textColor=colors.HexColor("#1b5e20"), alignment=TA_CENTER, leading=13))]]
    gov_t = Table(gov_data, colWidths=["100%"])
    gov_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#e8f5e9")),
        ("BOX",(0,0),(-1,-1),1.5,colors.HexColor("#2e7d32")),
        ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),
    ]))
    story.append(gov_t)
    story.append(Spacer(1, 14))

    s_asn = ParagraphStyle("asn", fontName="Helvetica", fontSize=9,
        alignment=TA_CENTER, textColor=colors.HexColor("#2d1f14"), leading=14)
    asn_data = [
        [Paragraph("<br/><br/>________________________________________", s_asn),
         Paragraph("<br/><br/>________________________________________", s_asn)],
        [Paragraph(f"<b>{cliente_nome}</b><br/>CONTRATANTE<br/>CPF: {cpf}", s_asn),
         Paragraph(f"<b>Lila Closet Atelier</b><br/>CONTRATADA<br/>CNPJ: {cnpj_val}", s_asn)],
    ]
    asn_t = Table(asn_data, colWidths=["50%","50%"])
    asn_t.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LINEAFTER",(0,0),(0,-1),0.5,colors.HexColor("#e0d5c9")),
    ]))
    story.append(asn_t)
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0d5c9")))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"Lila Closet Atelier · {tel_val} | Contrato N.º {num_contrato} · {emitido_em_str}", s_rodape))

    doc.build(story)
    return buf.getvalue()

# ══════════════════════════════════════════════════════════════════════════════
# SINCRONIZAÇÃO DE LEMBRETES — mantém o cronograma/calendário alinhado
# com as datas do pedido sempre que ele é editado
# ══════════════════════════════════════════════════════════════════════════════
def _sincronizar_lembretes_pedido(
    enc_id: str, cliente: str, peca: str,
    d_encomenda: date, d_visita: date, precisa_tecido: bool, d_tecido: date,
    d_confeccao: date, d_prova: date, tem_prova2: bool, d_prova2,
    d_entrega: date,
):
    """
    Após editar um pedido, sincroniza as tarefas do cronograma vinculadas a
    essa encomenda para refletir as novas datas no Calendário e na aba Trabalho:
    - Atualiza a data (e o texto) das tarefas existentes
    - Cria a tarefa que estiver faltando (ex: 2ª Prova ou Tecido habilitados agora)
    - Remove a tarefa que não fizer mais sentido (ex: 2ª Prova ou Tecido desabilitados)
    Somente tarefas ainda PENDENTES são sincronizadas; tarefas já marcadas como
    concluídas são preservadas como histórico e não são alteradas.
    """
    desc = f"{peca} ({cliente})"

    df_crono = cronograma_listar(tipo_agenda="Trabalho", concluida=False)
    if df_crono is None or df_crono.empty or "encomenda_id" not in df_crono.columns:
        df_crono = pd.DataFrame(columns=["rowid", "tarefa", "encomenda_id"])
    else:
        df_crono = df_crono[df_crono["encomenda_id"].astype(str) == str(enc_id)]

    especificacoes = [
        ("📝 Encomenda:",   "Costura", 0.5, d_encomenda, True),
        ("📏 Medidas:",     "Costura", 1.0, d_visita, True),
        ("🛍️ Tecido:",     "Compras", 1.0, d_tecido, bool(precisa_tecido)),
        ("🪡 Confecção:",   "Costura", 3.0, d_confeccao, True),
        ("👗 2ª Prova:",    "Costura", 1.0, d_prova2, bool(tem_prova2) and d_prova2 is not None),
        ("👗 Prova:",       "Costura", 1.0, d_prova, True),
        ("🎁 Entrega:",     "Costura", 0.5, d_entrega, True),
    ]

    for prefixo, categoria, horas, data_val, deve_existir in especificacoes:
        linha_existente = None
        if not df_crono.empty:
            match = df_crono[df_crono["tarefa"].astype(str).str.startswith(prefixo)]
            if not match.empty:
                linha_existente = match.iloc[0]

        if not deve_existir:
            if linha_existente is not None:
                cronograma_deletar(str(linha_existente["rowid"]))
            continue

        if data_val is None:
            continue

        novo_texto = f"{prefixo} {desc}"
        if linha_existente is not None:
            cronograma_atualizar(str(linha_existente["rowid"]), {
                "tarefa": novo_texto,
                "data": data_val.isoformat(),
            })
        else:
            cronograma_inserir({
                "tarefa": novo_texto, "categoria": categoria, "horas": horas,
                "data": data_val.isoformat(), "frequencia": "Pontual", "concluida": 0,
                "encomenda_id": enc_id, "tipo_agenda": "Trabalho",
            })


# ══════════════════════════════════════════════════════════════════════════════
# CARDS DE PEDIDO — clique abre popup com todos os detalhes (estilo cards de motorista)
# ══════════════════════════════════════════════════════════════════════════════
def _conteudo_pedido(enc: dict, cancelado: bool):
    etapa_num  = int(enc.get("etapa", 1))
    restante_enc = float(enc.get("valor_total", 0) or 0) - float(enc.get("valor_recebido", 0) or 0)

    st.markdown(f"### 👤 {enc.get('cliente','—')} &nbsp;·&nbsp; 🧵 {enc.get('peca','—')}")
    st.caption(f"📝 Pedido registrado em {formatar_data_hora_br(enc.get('criado_em'))}")

    if not cancelado:
        steps_html = '<div class="step-bar">'
        for i in range(1, 8):
            ic, nm = ETAPAS[i]
            cls = "done" if i < etapa_num else ("active" if i == etapa_num else "")
            steps_html += f'<div class="step-item {cls}"><div class="step-dot">{ic}</div><div class="step-lbl">{nm}</div></div>'
        steps_html += "</div>"
        st.markdown(steps_html, unsafe_allow_html=True)
        st.markdown("")

    col_inf1, col_inf2, col_inf3, col_inf4 = st.columns(4)
    col_inf1.metric("Valor Total",    brl(float(enc.get("valor_total",0) or 0)))
    col_inf2.metric("Recebido",       brl(float(enc.get("valor_recebido",0) or 0)))
    col_inf3.metric("Saldo Restante", brl(max(restante_enc, 0)))
    col_inf4.metric("Entrega",        formatar_data_br(enc.get("data_entrega","")))

    prova2_txt = ""
    if str(enc.get("data_prova2") or "").strip():
        prova2_txt = f" &nbsp;|&nbsp; 👗 2ª Prova: **{formatar_data_br(enc.get('data_prova2'))}**"
    tecido_txt = ""
    if enc.get("precisa_tecido") and str(enc.get("data_tecido") or "").strip():
        tecido_txt = f" &nbsp;|&nbsp; 🛍️ Tecido: **{formatar_data_br(enc.get('data_tecido'))}**"
    st.caption(
        f"🗓️ Encomenda: **{formatar_data_br(enc.get('data_encomenda', enc.get('criado_em','')))}** "
        f"&nbsp;|&nbsp; 📏 Medidas: **{formatar_data_br(enc.get('data_visita',''))}** "
        f"&nbsp;|&nbsp; 🪡 Confecção: **{formatar_data_br(enc.get('data_confeccao',''))}** "
        f"&nbsp;|&nbsp; 👗 Prova: **{formatar_data_br(enc.get('data_prova',''))}**"
        f"{prova2_txt}{tecido_txt}"
    )

    st.markdown("##### 📄 Contrato")
    col_cpf, col_rg = st.columns(2)
    cpf_s = str(enc.get("cpf_cliente") or "")
    rg_s  = str(enc.get("rg_cliente") or "")
    v_cpf = col_cpf.text_input("CPF", value=cpf_s, key=f"cpf_{enc['rowid']}")
    v_rg  = col_rg.text_input("RG",   value=rg_s,  key=f"rg_{enc['rowid']}")

    if v_cpf != cpf_s or v_rg != rg_s:
        encomendas_atualizar(str(enc["rowid"]), {"cpf_cliente": v_cpf, "rg_cliente": v_rg})

    if v_cpf.strip() and v_rg.strip():
        pdf_bytes = gerar_pdf_contrato(dict(enc), v_cpf.strip(), v_rg.strip())
        col_dl1, col_dl2 = st.columns(2)
        col_dl1.download_button(
            "📥 BAIXAR CONTRATO PDF", data=pdf_bytes,
            file_name=f"Contrato_{enc['cliente'].replace(' ','_')}.pdf",
            mime="application/pdf", key=f"dl_{enc['rowid']}",
            use_container_width=True,
        )
        col_dl2.link_button("✍️ ASSINAR VIA GOV.BR",
            url="https://assinador.iti.br/assinatura/index.xhtml",
            use_container_width=True)
    else:
        st.info("💡 Preencha CPF e RG para habilitar o contrato.")

    st.markdown("##### ✏️ Editar Pedido")

    with st.expander("📏 Ver / Editar Medidas desta Cliente"):
        df_cli_medidas = clientes_listar()
        cli_row_medidas = None
        if not df_cli_medidas.empty:
            match_cli = df_cli_medidas[df_cli_medidas["nome"] == enc.get("cliente")]
            if not match_cli.empty:
                cli_row_medidas = match_cli.iloc[0]

        if cli_row_medidas is None:
            st.info("Cliente não encontrada no cadastro (pode ter sido removida).")
        else:
            with st.form(f"form_medidas_pedido_{enc['rowid']}"):
                colm1, colm2, colm3 = st.columns(3)
                novas_medidas = {}
                for i, (label, col_db) in enumerate(DIC_MEDIDAS.items()):
                    raw = cli_row_medidas.get(col_db, 0)
                    val_f = float(raw) if raw not in [None, "", "nan"] and pd.notna(raw) else 0.0
                    alvo = colm1 if i < 5 else (colm2 if i < 10 else colm3)
                    novas_medidas[col_db] = alvo.number_input(
                        f"{label} (cm)", value=val_f, format="%.1f", step=0.5,
                        key=f"med_{enc['rowid']}_{col_db}",
                    )
                obs_medidas = st.text_area(
                    "Observações de modelagem",
                    value=str(cli_row_medidas.get("outro") or ""),
                    key=f"med_obs_{enc['rowid']}",
                )
                if st.form_submit_button("💾 Salvar Medidas", use_container_width=True):
                    clientes_atualizar(str(cli_row_medidas["rowid"]), {**novas_medidas, "outro": obs_medidas})
                    st.success("✅ Medidas atualizadas!")
                    st.rerun()

    tem_prova2_atual = bool(int(enc.get("tem_prova2", 0) or 0)) or bool(str(enc.get("data_prova2") or "").strip())
    ed_tem_prova2 = st.checkbox("Precisa de uma segunda prova?", value=tem_prova2_atual, key=f"tp2_{enc['rowid']}")

    with st.form(f"edit_{enc['rowid']}"):
        ed_peca = st.text_input("Peça", value=str(enc.get("peca") or ""))
        ed_desc = st.text_area("Descrição", value=str(enc.get("descricao") or ""), height=60)
        col_f1e, col_f2e = st.columns(2)
        fpag_opts = ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"]
        fpag_cur  = enc.get("forma_pagamento","A combinar")
        fpag_idx  = fpag_opts.index(fpag_cur) if fpag_cur in fpag_opts else 4
        ed_fpag   = col_f1e.selectbox("Forma de Pagamento", fpag_opts, index=fpag_idx)
        ed_obs    = col_f2e.text_area("Observações", value=str(enc.get("observacoes") or ""), height=60)

        st.markdown("📅 Datas")
        d0, d1 = st.columns(2)
        ed_datenc = d0.date_input("🗓️ Data da Encomenda", value=converter_para_data(enc.get("data_encomenda")),
                                   key=f"denc_{enc['rowid']}", format="DD/MM/YYYY")
        ed_vis    = d1.date_input("📏 Data Medidas",      value=converter_para_data(enc.get("data_visita")),
                                   key=f"dv_{enc['rowid']}", format="DD/MM/YYYY")

        d2, d3 = st.columns(2)
        ed_conf = d2.date_input("🪡 Data da Confecção", value=converter_para_data(enc.get("data_confeccao")),
                                 key=f"dconf_{enc['rowid']}", format="DD/MM/YYYY")
        ed_pro = d3.date_input("👗 Data da Prova", value=converter_para_data(enc.get("data_prova")),
                                key=f"dp_{enc['rowid']}", format="DD/MM/YYYY")

        d4, d5 = st.columns(2)
        ed_pro2 = None
        if ed_tem_prova2:
            ed_pro2 = d4.date_input(
                "👗 Data da 2ª Prova",
                value=converter_para_data(enc.get("data_prova2")) if enc.get("data_prova2") else ed_pro + timedelta(days=7),
                key=f"dp2_{enc['rowid']}", format="DD/MM/YYYY",
            )

        d6, d7 = st.columns(2)
        ed_tec  = d6.date_input("🛍️ Data Compra do Tecido", value=converter_para_data(enc.get("data_tecido")),
                                 key=f"dt_{enc['rowid']}", format="DD/MM/YYYY")
        ed_ent  = d7.date_input("🎁 Data de Entrega", value=converter_para_data(enc.get("data_entrega")),
                                 key=f"de_{enc['rowid']}", format="DD/MM/YYYY")

        col_b1, col_b2, col_b3 = st.columns(3)
        if col_b1.form_submit_button("💾 Salvar", use_container_width=True):
            encomendas_atualizar(str(enc["rowid"]), {
                "peca": ed_peca, "descricao": ed_desc,
                "forma_pagamento": ed_fpag, "observacoes": ed_obs,
                "data_encomenda": ed_datenc.isoformat(),
                "data_visita": ed_vis.isoformat(),
                "data_tecido": ed_tec.isoformat(),
                "data_confeccao": ed_conf.isoformat(),
                "data_prova": ed_pro.isoformat(),
                "tem_prova2": 1 if ed_tem_prova2 else 0,
                "data_prova2": ed_pro2.isoformat() if ed_pro2 else "",
                "data_entrega": ed_ent.isoformat(),
            })
            _sincronizar_lembretes_pedido(
                enc_id=str(enc["rowid"]), cliente=enc.get("cliente",""), peca=ed_peca,
                d_encomenda=ed_datenc, d_visita=ed_vis,
                precisa_tecido=bool(int(enc.get("precisa_tecido", 0) or 0)), d_tecido=ed_tec,
                d_confeccao=ed_conf, d_prova=ed_pro,
                tem_prova2=ed_tem_prova2, d_prova2=ed_pro2,
                d_entrega=ed_ent,
            )
            st.success("✅ Pedido e lembretes atualizados!")
            st.rerun()

        if not cancelado:
            if col_b2.form_submit_button("✅ Marcar Concluído", use_container_width=True):
                encomendas_atualizar(str(enc["rowid"]), {"etapa": 7})
                st.rerun()
            if col_b3.form_submit_button("❌ Cancelar Pedido", use_container_width=True):
                encomendas_cancelar(str(enc["rowid"]))
                st.rerun()


def _abrir_popup_pedido(enc: dict, cancelado: bool):
    titulo = f"📦 {enc['cliente']} — {enc['peca']}"
    @st.dialog(titulo, width="large")
    def _p():
        _conteudo_pedido(enc, cancelado)
    _p()


def _dialog_editar_dia(dt_str: str, tasks_dia: pd.DataFrame):
    """
    Popup usado a partir do Calendário: mostra o(s) pedido(s) vinculados
    às tarefas daquele dia e permite editar diretamente (mesmo formulário
    usado em Gerenciar Pedidos), sem opção de criar nova encomenda.
    """
    encomenda_ids = []
    if tasks_dia is not None and not tasks_dia.empty and "encomenda_id" in tasks_dia.columns:
        encomenda_ids = [e for e in tasks_dia["encomenda_id"].dropna().unique().tolist() if str(e).strip()]

    @st.dialog(f"✏️ Editar pedidos — {formatar_data_br(dt_str)}", width="large")
    def _d():
        if not encomenda_ids:
            st.info("Nenhum pedido vinculado a esta data.")
            return

        encomendas_dia = []
        for eid in encomenda_ids:
            enc_d = encomendas_buscar(str(eid))
            if enc_d:
                encomendas_dia.append(enc_d)

        if not encomendas_dia:
            st.info("Nenhum pedido vinculado a esta data.")
            return

        if len(encomendas_dia) == 1:
            enc_d = encomendas_dia[0]
            cancelado_d = bool(int(enc_d.get("cancelado", 0) or 0))
            _conteudo_pedido(enc_d, cancelado_d)
        else:
            labels = [f"{e['cliente']} — {e['peca']}" for e in encomendas_dia]
            escolha = st.radio("Vários pedidos nesta data. Selecione qual editar:",
                                labels, key=f"sel_dia_{dt_str}")
            idx_sel = labels.index(escolha)
            enc_d = encomendas_dia[idx_sel]
            st.divider()
            cancelado_d = bool(int(enc_d.get("cancelado", 0) or 0))
            _conteudo_pedido(enc_d, cancelado_d)
    _d()


def _card_pedido(enc: dict, idx: int):
    etapa_num  = int(enc.get("etapa", 1))
    etapa_ic, etapa_nm = ETAPAS.get(etapa_num, ("📦", "–"))
    cancelado  = bool(int(enc.get("cancelado", 0) or 0))
    restante_enc = float(enc.get("valor_total", 0) or 0) - float(enc.get("valor_recebido", 0) or 0)
    pct = 0 if cancelado else round(min(etapa_num / 7, 1.0) * 100)
    badge_cls = "badge-red" if cancelado else "badge-gold"
    badge_txt = "❌ Cancelado" if cancelado else f"{etapa_ic} {etapa_nm}"

    if st.button(f"📦 {enc['cliente']} — {enc['peca']}",
                 key=f"pedcard_{idx}_{enc['rowid']}", use_container_width=True):
        _abrir_popup_pedido(enc, cancelado)

    saldo_badge = ""
    if not cancelado and restante_enc > 0.01:
        saldo_badge = f'&nbsp;<span class="badge badge-amber">Saldo {brl(restante_enc)}</span>'

    st.markdown(f"""
    <div class="lila-cardbody">
        <div class="lila-cardsub">💰 {brl(float(enc.get('valor_total',0) or 0))} &nbsp;·&nbsp; Entrega {formatar_data_br(enc.get('data_entrega',''))}</div>
        <div class="lila-bar"><div style="width:{pct}%;"></div></div>
        <div style="margin-top:6px;">
            <span class="badge {badge_cls}">{badge_txt}</span>
            &nbsp;<span class="badge badge-green">Recebido {brl(float(enc.get('valor_recebido',0) or 0))}</span>
            {saldo_badge}
        </div>
    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# CABEÇALHO DO SISTEMA
# ══════════════════════════════════════════════════════════════════════════════
logo_b64 = get_logo_base64()
logo_html = (f'<img src="data:image/png;base64,{logo_b64}" class="hero-logo" alt="Lila Logo">'
             if logo_b64 else '<div class="hero-icon">🧵</div>')

st.markdown(f"""
<div class="hero-header">
  {logo_html}
  <div>
    <div class="hero-title">Lila Closet Atelier</div>
    <div class="hero-subtitle">Sistema de Gestão Profissional · Costura sob medida</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MÉTRICAS DO TOPO
# ══════════════════════════════════════════════════════════════════════════════
hoje_dt = hoje_brasilia()

df_enc_all = encomendas_listar(cancelado=False)
enc_ativas = 0
if not df_enc_all.empty and "etapa" in df_enc_all.columns:
    enc_ativas = int((df_enc_all["etapa"].astype(int) < 7).sum())

meta_ped = int(cfg_get("meta_pedidos_mes") or 8)

mes_atual_str = hoje_dt.strftime("%Y-%m")
pedidos_mes = 0
if not df_enc_all.empty:
    col_data_ref = "data_encomenda" if "data_encomenda" in df_enc_all.columns else "criado_em"
    if col_data_ref in df_enc_all.columns:
        pedidos_mes = int(df_enc_all[col_data_ref].fillna("").astype(str).str.startswith(mes_atual_str).sum())
pct_meta = min(pedidos_mes / meta_ped * 100, 100) if meta_ped > 0 else 0

col_m1, col_m2, col_m3 = st.columns(3)
col_m1.markdown(f"""
<div class="kpi-card kpi-brown">
    <div class="kpi-label">🛍️ Pedidos Ativos</div>
    <div class="kpi-value">{enc_ativas}</div>
    <div class="kpi-sub">Em andamento agora</div>
</div>""", unsafe_allow_html=True)

col_m2.markdown(f"""
<div class="kpi-card kpi-gold">
    <div class="kpi-label">📋 Meta de Pedidos/mês</div>
    <div class="kpi-value">{meta_ped}</div>
    <div class="kpi-sub">Definida em Configurações</div>
</div>""", unsafe_allow_html=True)

col_m3.markdown(f"""
<div class="kpi-card kpi-cream">
    <div class="kpi-label">📊 Progresso da Meta</div>
    <div class="kpi-value">{pedidos_mes}<span style="font-size:1.1rem;color:#8b7355;"> / {meta_ped}</span></div>
    <div class="kpi-bar"><div style="width:{pct_meta:.0f}%;"></div></div>
    <div class="kpi-sub">{pct_meta:.0f}% da meta deste mês</div>
</div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ABAS PRINCIPAIS
# ══════════════════════════════════════════════════════════════════════════════
aba_enc, aba_agenda, aba_fin, aba_conf = st.tabs([
    "🛍️ ENCOMENDAS",
    "📅 AGENDA",
    "💰 FINANCEIRO",
    "⚙️ CONFIGURAÇÕES",
])

# ══════════════════════════════════════════════════════════════════════════════
# CONTEÚDO REAPROVEITADO DA ANTIGA ABA "HOJE"
# (agora vive dentro de AGENDA ▸ Calendário — topo e rodapé)
# ══════════════════════════════════════════════════════════════════════════════
def _secao_tarefas_e_entregas_hoje():
    st.markdown("### ⚡ Tarefas para Hoje")

    df_hoje = cronograma_com_cliente(
        tipo_agenda="Trabalho",
        concluida=False,
        ate_data=hoje_dt.isoformat(),
    )

    if df_hoje.empty:
        st.success("✅ Tudo em dia! Nenhuma tarefa pendente para hoje.")
    else:
        atrasadas = df_hoje[df_hoje["data"] < hoje_dt.isoformat()]
        if not atrasadas.empty:
            st.error(f"⚠️ **{len(atrasadas)} tarefa(s) atrasada(s)** — resolva assim que possível.")

        for _, row in df_hoje.iterrows():
            is_atrasado = row["data"] < hoje_dt.isoformat()
            badge_cls   = "badge-red" if is_atrasado else "badge-gold"
            badge_txt   = "⚠️ ATRASADO" if is_atrasado else "🔔 Pendente"
            cliente_txt = f" &nbsp;|&nbsp; 👤 {row['nome_cliente']}" if row.get("nome_cliente") else ""

            col_info, col_btn = st.columns([5, 1])
            with col_info:
                st.markdown(f"""
                <div class="kcard">
                  <div class="kcard-title">{row['tarefa']}</div>
                  <div class="kcard-sub">
                    📂 {row['categoria']} &nbsp;|&nbsp; ⏱️ {row['horas']}h &nbsp;|&nbsp;
                    📅 {formatar_data_br(row['data'])}{cliente_txt}
                    &nbsp;<span class="badge {badge_cls}">{badge_txt}</span>
                  </div>
                </div>""", unsafe_allow_html=True)
            with col_btn:
                st.write("")
                st.write("")
                if st.button("✅ Feito", key=f"hoje_{row['rowid']}"):
                    enc_id = row.get("encomenda_id")
                    if enc_id:
                        enc_data = encomendas_buscar(str(enc_id))
                        if enc_data:
                            prox = int(enc_data.get("etapa", 1)) + 1
                            if prox == 2: prox = 3
                            if prox == 3 and not enc_data.get("precisa_tecido"): prox = 4
                            if prox <= 7:
                                encomendas_atualizar(str(enc_id), {"etapa": prox})
                    cronograma_atualizar(str(row["rowid"]), {"concluida": 1})
                    st.rerun()

    st.divider()
    st.markdown("### 🎁 Entregas de Hoje")
    if not df_enc_all.empty:
        df_ent_hoje = df_enc_all[
            (df_enc_all.get("data_entrega", pd.Series(dtype=str)) == hoje_dt.isoformat()) &
            (df_enc_all["etapa"].astype(int) >= 6)
        ]
        if df_ent_hoje.empty:
            st.info("Nenhuma entrega programada para hoje.")
        else:
            for _, r in df_ent_hoje.iterrows():
                st.success(f"🎁 **{r['cliente']}** – {r['peca']} | {brl(float(r.get('valor_total', 0) or 0))}")
    else:
        st.info("Nenhuma entrega programada para hoje.")


def _secao_vida_pessoal():
    st.markdown('<div class="sep-pessoal"></div>', unsafe_allow_html=True)
    mostrar_vida_pessoal = st.toggle("🏠 Mostrar Vida Pessoal", value=False, key="tog_vida_pessoal_hoje")

    if mostrar_vida_pessoal:
        st.markdown("### 🏠 Vida Pessoal")

        col_add, col_list = st.columns(2)

        with col_add:
            st.markdown("#### ➕ Nova Atividade")
            with st.form("form_pessoal_hoje", clear_on_submit=True):
                desc_p  = st.text_input("O que precisa fazer?", key="desc_p_hoje")
                cat_p   = st.selectbox("Categoria", [
                    "Saúde/Médico","Exercícios","Atividades Domésticas",
                    "Compras","Lazer","Família","Outros"
                ], key="cat_p_hoje")
                data_p  = st.date_input("Data", hoje_brasilia(), key="data_p_hoje", format="DD/MM/YYYY")
                horas_p = st.number_input("Duração (h)", 0.5, 12.0, 1.0, step=0.5, key="horas_p_hoje")
                if st.form_submit_button("🗓️ Agendar", use_container_width=True):
                    if desc_p.strip():
                        cronograma_inserir({
                            "tarefa": desc_p.strip(), "categoria": cat_p,
                            "horas": horas_p, "data": data_p.isoformat(),
                            "frequencia": "Pontual", "concluida": 0,
                            "tipo_agenda": "Pessoal",
                        })
                        st.success("Agendado!")
                        st.rerun()

        with col_list:
            st.markdown("#### ⏳ Pendentes")
            df_p = cronograma_listar(tipo_agenda="Pessoal", concluida=False)
            if df_p.empty:
                st.info("Tudo em dia! ✅")
            else:
                for _, row in df_p.iterrows():
                    col_tx, col_bt = st.columns([4, 1])
                    col_tx.markdown(
                        f"**{formatar_data_br(row['data'])}** – {row['tarefa']} *(_{row['categoria']}_)*"
                    )
                    if col_bt.button("✅", key=f"pess_hoje_{row['rowid']}"):
                        cronograma_atualizar(str(row["rowid"]), {"concluida": 1})
                        st.rerun()

        st.markdown('<div class="sep-pessoal"></div>', unsafe_allow_html=True)

        col_tog1, col_tog2 = st.columns(2)
        mostrar_campo = col_tog1.toggle("📖 Mostrar Serviço de Campo", value=True, key="tog_campo_hoje")
        mostrar_peso  = col_tog2.toggle("⚖️ Mostrar Progresso de Peso",  value=True, key="tog_peso_hoje")

        # ── Serviço de Campo ──────────────────────────────────────────────
        if mostrar_campo:
            st.markdown("#### 📖 Serviço de Campo — Horas de Pregação")
            st.caption(f"Meta mensal: **{META_HORAS_CAMPO:.0f} horas**")

            col_cm1, col_cm2, _ = st.columns([2, 2, 4])
            mes_campo = col_cm1.selectbox(
                "Mês", list(range(1, 13)),
                format_func=lambda x: MESES_PT[x-1],
                index=hoje_dt.month - 1, key="mes_campo_sel_hoje",
            )
            ano_campo = col_cm2.number_input(
                "Ano", min_value=2020, max_value=2035,
                value=hoje_dt.year, key="ano_campo_sel_hoje",
            )
            mes_ano_campo = f"{ano_campo}-{mes_campo:02d}"

            with st.form("form_campo_horas_hoje", clear_on_submit=True):
                cc1, cc2, cc3 = st.columns([2, 1, 3])
                c_data  = cc1.date_input("Data da saída", hoje_brasilia(), key="c_data_hoje", format="DD/MM/YYYY")
                c_horas = cc2.number_input("Horas", 0.5, 24.0, 1.0, step=0.5, key="c_horas_hoje")
                c_desc  = cc3.text_input("Observação (opcional)", key="c_desc_hoje")
                if st.form_submit_button("➕ Lançar Horas", use_container_width=True):
                    campo_horas_inserir({
                        "data": c_data.isoformat(),
                        "horas": c_horas,
                        "descricao": c_desc.strip(),
                        "mes_ano": f"{c_data.year}-{c_data.month:02d}",
                        "criado_em": agora_br().isoformat(),
                    })
                    st.success(f"✅ {c_horas}h registradas!")
                    st.rerun()

            df_campo = campo_horas_listar(mes_ano=mes_ano_campo)
            horas_mes = float(df_campo["horas"].sum()) if not df_campo.empty else 0.0
            pct_campo = min(horas_mes / META_HORAS_CAMPO, 1.0) if META_HORAS_CAMPO > 0 else 0
            faltam    = max(META_HORAS_CAMPO - horas_mes, 0)

            st.markdown(f"""
            <div class="campo-card">
              <div class="campo-title">📖 {MESES_PT[mes_campo-1]} {ano_campo}</div>
              <div style="display:flex;align-items:flex-end;gap:12px;margin-top:8px;">
                <div><div class="campo-num">{horas_mes:.1f}h</div><div class="campo-sub">realizadas</div></div>
                <div><div class="campo-num" style="font-size:1.4rem;color:#bbdefb">/ {META_HORAS_CAMPO:.0f}h</div><div class="campo-sub">meta</div></div>
                <div><div class="campo-num" style="font-size:1.4rem;color:#ffe0b2">{faltam:.1f}h</div><div class="campo-sub">faltam</div></div>
              </div>
            </div>
            """, unsafe_allow_html=True)
            st.progress(pct_campo, text=f"{horas_mes:.1f}h de {META_HORAS_CAMPO:.0f}h — {pct_campo*100:.0f}%")

            df_campo_hist = campo_horas_historico()
            if not df_campo_hist.empty:
                st.markdown("**📊 Histórico de horas por mês:**")
                df_campo_hist["Mês"] = df_campo_hist["mes_ano"].apply(
                    lambda m: f"{MESES_PT[int(m[5:7])-1]} {m[:4]}"
                )
                df_campo_hist["Total"]  = df_campo_hist["total"].apply(lambda h: f"{h:.1f}h")
                df_campo_hist["✅ Meta?"] = df_campo_hist["total"].apply(
                    lambda h: "🏆 Sim" if h >= META_HORAS_CAMPO else f"⏳ Faltaram {META_HORAS_CAMPO-h:.1f}h"
                )
                st.dataframe(df_campo_hist[["Mês","Total","✅ Meta?"]], use_container_width=True, hide_index=True)

            if not df_campo.empty:
                with st.expander(f"📋 Lançamentos de {MESES_PT[mes_campo-1]} {ano_campo}"):
                    for _, row in df_campo.iterrows():
                        col_d, col_h, col_ds, col_del = st.columns([2, 1, 4, 1])
                        col_d.markdown(f"**{formatar_data_br(row['data'])}**")
                        col_h.markdown(f"⏱️ {row['horas']}h")
                        col_ds.markdown(row["descricao"] or "—")
                        if col_del.button("🗑️", key=f"del_campo_{row['rowid']}"):
                            campo_horas_deletar(str(row["rowid"]))
                            st.rerun()

        # ── Emagrecimento ─────────────────────────────────────────────────
        if mostrar_peso:
            st.markdown("#### ⚖️ Acompanhamento de Emagrecimento")
            st.caption(f"Meta: chegar a **{META_PESO_KG} kg** · Peso inicial: **{PESO_INICIAL_KG} kg**")

            col_pm1, col_pm2 = st.columns([3, 2])
            with col_pm1:
                with st.form("form_peso_hoje", clear_on_submit=True):
                    pc1, pc2 = st.columns(2)
                    p_data = pc1.date_input("Data da pesagem", hoje_brasilia(), key="p_data_hoje", format="DD/MM/YYYY")
                    p_peso = pc2.number_input("Peso atual (kg)", min_value=30.0, max_value=200.0,
                                               value=70.0, step=0.1, format="%.1f", key="p_peso_hoje")
                    if st.form_submit_button("📝 Registrar Peso", use_container_width=True):
                        mes_ano_p = f"{p_data.year}-{p_data.month:02d}"
                        peso_upsert(mes_ano_p, p_data.isoformat(), p_peso)
                        st.success(f"✅ Peso {p_peso:.1f} kg registrado!")
                        st.rerun()

            df_peso = peso_listar()

            with col_pm2:
                if not df_peso.empty:
                    peso_atual  = float(df_peso.iloc[-1]["peso_kg"])
                    perdido     = PESO_INICIAL_KG - peso_atual
                    falta_peso  = max(peso_atual - META_PESO_KG, 0)
                    total_perder = PESO_INICIAL_KG - META_PESO_KG
                    pct_peso    = min(perdido / total_perder, 1.0) if total_perder > 0 else 0

                    st.markdown(f"""
                    <div class="peso-card">
                      <div class="peso-title">⚖️ Progresso de Peso</div>
                      <div style="display:flex;align-items:flex-end;gap:12px;margin-top:8px;">
                        <div><div class="peso-num">{peso_atual:.1f}</div><div class="peso-sub">kg atual</div></div>
                        <div><div class="peso-num" style="font-size:1.4rem;color:#c8e6c9">-{perdido:.1f}</div><div class="peso-sub">kg perdidos</div></div>
                        <div><div class="peso-num" style="font-size:1.4rem;color:#a5d6a7">{falta_peso:.1f}</div><div class="peso-sub">kg até a meta</div></div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.progress(pct_peso, text=f"Meta: {META_PESO_KG} kg · {pct_peso*100:.0f}% do caminho")
                else:
                    st.info("Nenhum peso registrado ainda.")

            if not df_peso.empty:
                st.markdown("**📈 Evolução mensal do peso:**")
                df_peso["Mês"] = df_peso["mes_ano"].apply(
                    lambda m: f"{MESES_PT[int(m[5:7])-1]}/{m[:4]}"
                )
                st.line_chart(df_peso.set_index("Mês")[["peso_kg"]].rename(columns={"peso_kg": "Peso (kg)"}), height=180)

                df_peso_show = df_peso.copy()
                df_peso_show["Variação"] = df_peso_show["peso_kg"].diff().apply(
                    lambda x: (f"▼ {abs(x):.1f} kg" if x < 0 else (f"▲ {x:.1f} kg" if x > 0 else "—"))
                    if pd.notna(x) else "—"
                )
                df_peso_show["Mês/Ano"] = df_peso_show["mes_ano"].apply(
                    lambda m: f"{MESES_PT[int(m[5:7])-1]} {m[:4]}"
                )
                df_peso_show["Data"]  = df_peso_show["data"].apply(formatar_data_br)
                df_peso_show["Peso"]  = df_peso_show["peso_kg"].apply(lambda x: f"{x:.1f} kg")
                st.dataframe(
                    df_peso_show.sort_values("mes_ano", ascending=False)[["Mês/Ano","Data","Peso","Variação"]],
                    use_container_width=True, hide_index=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 – ENCOMENDAS
# ══════════════════════════════════════════════════════════════════════════════
with aba_enc:
    st.markdown("### 🆕 Nova Encomenda")
    st.caption(
        "Preencha os dados abaixo para cadastrar uma nova encomenda. "
        "Este formulário fica sempre visível nesta tela — inclusive se você trocar "
        "de aba ou de aplicativo no celular, os dados já digitados permanecem aqui."
    )
    with st.container(border=True):
        secao_nova_encomenda_inline()

    st.divider()

    t_medidas, t_gerenciar = st.tabs([
        "📏 Medidas & Clientes",
        "📋 Gerenciar Pedidos",
    ])

    # ── Medidas & Clientes ─────────────────────────────────────────────────
    with t_medidas:
        st.markdown("### 👥 Clientes Cadastradas")
        st.caption("Novas clientes são cadastradas direto na hora de criar uma encomenda "
                   "(seção **🆕 Nova Encomenda**, no topo desta aba).")
        df_clis_lista = clientes_listar()
        if not df_clis_lista.empty:
            cols_show = [c for c in ["nome","telefone","email","modelo_base"] if c in df_clis_lista.columns]
            df_show = df_clis_lista[cols_show].copy()
            df_show.columns = ["Nome","Telefone","E-mail","Modelo Base"][:len(cols_show)]
            if "criado_em" in df_clis_lista.columns:
                df_show["Cadastrada em"] = df_clis_lista["criado_em"].apply(formatar_data_hora_br)
            st.dataframe(df_show, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma cliente cadastrada ainda.")

        st.markdown("---")
        st.markdown("### 📏 Ficha de Medidas")
        df_c = clientes_listar()

        if df_c.empty:
            st.info("Nenhuma cliente cadastrada.")
        else:
            sel_cli = st.selectbox("Selecione a cliente", df_c["nome"].tolist(), key="sel_med")
            dados_cli = df_c[df_c["nome"] == sel_cli].iloc[0]

            with st.form(f"form_med_{sel_cli}"):
                col1, col2, col3 = st.columns(3)
                novos = {}
                for i, (label, col_db) in enumerate(DIC_MEDIDAS.items()):
                    raw = dados_cli.get(col_db, 0)
                    val_f = float(raw) if raw not in [None, "", "nan"] and pd.notna(raw) else 0.0
                    target = col1 if i < 5 else (col2 if i < 10 else col3)
                    novos[col_db] = target.number_input(f"{label} (cm)", value=val_f, format="%.1f", step=0.5)
                obs = st.text_area("Observações de modelagem", value=str(dados_cli.get("outro") or ""))

                if st.form_submit_button("💾 Salvar Medidas", use_container_width=True):
                    update_data = {**novos, "outro": obs}
                    clientes_atualizar(str(dados_cli["rowid"]), update_data)
                    st.success("✅ Medidas salvas!")
                    st.rerun()

    # ── Gerenciar Pedidos ────────────────────────────────────────────────
    with t_gerenciar:
        col_tit, col_novo = st.columns([4, 1.4])
        col_tit.markdown("### 📋 Todos os Pedidos")
        if col_novo.button("➕ Nova Encomenda", use_container_width=True, type="primary", key="btn_add_gerpedidos"):
            dialog_nova_encomenda()

        col_f1, col_f2 = st.columns([2, 1])
        filtro_status = col_f1.radio(
            "Filtrar:",
            ["Todos","Em andamento","Concluídos","Cancelados"],
            horizontal=True, key="filtro_ger",
        )
        filtro_cli = col_f2.text_input("🔍 Buscar cliente", key="busca_ger")

        df_e = encomendas_listar()

        if not df_e.empty:
            if filtro_status == "Em andamento":
                df_e = df_e[(df_e["etapa"].astype(int) < 7) & (df_e["cancelado"].astype(int) == 0)]
            elif filtro_status == "Concluídos":
                df_e = df_e[(df_e["etapa"].astype(int) == 7) & (df_e["cancelado"].astype(int) == 0)]
            elif filtro_status == "Cancelados":
                df_e = df_e[df_e["cancelado"].astype(int) == 1]
            else:
                pass  # Todos
            if filtro_cli.strip():
                df_e = df_e[df_e["cliente"].str.contains(filtro_cli, case=False, na=False)]

        if df_e.empty:
            st.info("Nenhum pedido encontrado com os filtros selecionados.")
        else:
            cols_ped = st.columns(2)
            for idx, (_, enc) in enumerate(df_e.iterrows()):
                with cols_ped[idx % 2]:
                    _card_pedido(enc, idx)

# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 – AGENDA
# ══════════════════════════════════════════════════════════════════════════════
with aba_agenda:
    sub_cal, sub_trabalho = st.tabs(["📅 Calendário", "🛠️ Trabalho"])

    with sub_trabalho:
        st.markdown("#### 🛠️ Agenda de Trabalho Pendente")
        df_t = cronograma_com_cliente(tipo_agenda="Trabalho", concluida=False)
        if df_t.empty:
            st.success("Nenhuma tarefa pendente!")
        else:
            for _, row in df_t.iterrows():
                is_atrasado = row["data"] < hoje_dt.isoformat()
                badge_cls   = "badge-red" if is_atrasado else "badge-gold"
                badge_txt   = "⚠️ ATRASADO" if is_atrasado else "🔔 Pendente"
                cliente_txt = f" &nbsp;|&nbsp; 👤 {row['nome_cliente']}" if row.get("nome_cliente") else ""

                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    st.markdown(f"""
                    <div class="kcard">
                      <div class="kcard-title">{row['tarefa']}</div>
                      <div class="kcard-sub">
                        📂 {row['categoria']} &nbsp;|&nbsp; ⏱️ {row['horas']}h &nbsp;|&nbsp;
                        📅 {formatar_data_br(row['data'])}{cliente_txt}
                        &nbsp;<span class="badge {badge_cls}">{badge_txt}</span>
                      </div>
                    </div>""", unsafe_allow_html=True)
                with col_btn:
                    st.write("")
                    enc_id_t = row.get("encomenda_id")
                    if enc_id_t and str(enc_id_t).strip():
                        if st.button("✏️ Editar", key=f"edit_trab_{row['rowid']}", use_container_width=True):
                            enc_data_t = encomendas_buscar(str(enc_id_t))
                            if enc_data_t:
                                cancelado_t = bool(int(enc_data_t.get("cancelado", 0) or 0))
                                _abrir_popup_pedido(enc_data_t, cancelado_t)

    with sub_cal:
        _secao_tarefas_e_entregas_hoje()

        st.divider()
        st.markdown("### 📅 Calendário")
        st.caption("💡 Clique em **✏️ editar** em qualquer dia com pedidos para abrir e editar aquela encomenda.")

        if "data_ref" not in st.session_state:
            st.session_state.data_ref = hoje_brasilia()

        nav1, nav_title, nav2 = st.columns([1, 4, 1])
        if nav1.button("◀ Anterior"):
            st.session_state.data_ref = (
                st.session_state.data_ref.replace(day=1) - timedelta(days=1))
            st.rerun()
        if nav2.button("Próximo ▶"):
            st.session_state.data_ref = (
                st.session_state.data_ref.replace(day=1) + timedelta(days=32))
            st.rerun()

        ref = st.session_state.data_ref
        nav_title.markdown(
            f"<h4 style='text-align:center;color:#6b3a22'>"
            f"{MESES_PT[ref.month-1]} {ref.year}</h4>",
            unsafe_allow_html=True,
        )

        df_all_cal = cronograma_com_cliente(tipo_agenda="Trabalho", concluida=False)

        col_heads = st.columns(7)
        for i, d in enumerate(["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]):
            col_heads[i].markdown(
                f"<center><b style='color:#c9a227;font-size:0.8rem'>{d}</b></center>",
                unsafe_allow_html=True,
            )

        for semana in calendar.monthcalendar(ref.year, ref.month):
            cols_s = st.columns(7)
            for i, dia in enumerate(semana):
                if dia == 0:
                    continue
                dt_str = f"{ref.year}-{ref.month:02d}-{dia:02d}"
                dt_obj_cal = date(ref.year, ref.month, dia)
                tasks  = df_all_cal[df_all_cal["data"] == dt_str] if not df_all_cal.empty else pd.DataFrame()
                is_hoje = dt_str == hoje_brasilia().isoformat()

                tarefas_html = ""
                for _, r in tasks.iterrows():
                    tipo_tarefa  = r["tarefa"].split(":")[0].strip() if ":" in r["tarefa"] else r["tarefa"][:16]
                    cliente_cal  = r.get("nome_cliente", "")
                    tarefas_html += (
                        f"<div class='cal-task-tag'>{tipo_tarefa}"
                        f"{'<br><span class=\"cal-task-cliente\">' + cliente_cal + '</span>' if cliente_cal else ''}"
                        f"</div>"
                    )

                cell_key = f"calcell_hoje_{dt_str}" if is_hoje else f"calcell_{dt_str}"
                tem_pedido_dia = (
                    not tasks.empty
                    and "encomenda_id" in tasks.columns
                    and tasks["encomenda_id"].notna().any()
                    and tasks["encomenda_id"].astype(str).str.strip().ne("").any()
                )

                with cols_s[i]:
                    with st.container(key=cell_key):
                        st.markdown(
                            f"<div class='cal-day-inner'>"
                            f"<span class='cal-day-num'>{dia}</span>"
                            f"{tarefas_html}</div>",
                            unsafe_allow_html=True,
                        )
                        if tem_pedido_dia:
                            if st.button("✏️ editar", key=f"edit_cal_{dt_str}", use_container_width=True,
                                         help=f"Editar pedidos de {formatar_data_br(dt_str)}"):
                                _dialog_editar_dia(dt_str, tasks)

        _secao_vida_pessoal()

# ══════════════════════════════════════════════════════════════════════════════
# ABA 4 – FINANCEIRO
# ══════════════════════════════════════════════════════════════════════════════
with aba_fin:
    st.markdown("### 💰 Controle Financeiro Profissional")

    df_enc_fin = encomendas_listar(cancelado=False)
    df_g_fin   = gastos_listar()

    def _flt(df, col, default=0.0):
        if df.empty or col not in df.columns:
            return default
        return float(df[col].fillna(0).astype(float).sum())

    receita_total    = _flt(df_enc_fin, "valor_recebido")
    receita_prevista = float(df_enc_fin[df_enc_fin["etapa"].astype(int) < 7]["valor_total"].fillna(0).astype(float).sum()) if not df_enc_fin.empty else 0.0
    gastos_pagos     = float(df_g_fin[df_g_fin["pago"].astype(int) == 1]["valor"].fillna(0).astype(float).sum()) if not df_g_fin.empty else 0.0
    gastos_previstos = float(df_g_fin[df_g_fin["pago"].astype(int) == 0]["valor"].fillna(0).astype(float).sum()) if not df_g_fin.empty else 0.0
    lucro_real       = receita_total - gastos_pagos
    lucro_previsto   = (receita_total + receita_prevista) - (gastos_pagos + gastos_previstos)

    pct_reserva   = int(cfg_get("reserva_emergencia_meses") or 3)
    pct_capital   = float(cfg_get("capital_giro_pct") or 20) / 100
    margem_min    = float(cfg_get("margem_minima_pct") or 30) / 100
    meta_fat_fin  = float(cfg_get("meta_faturamento") or 5000)

    reserva_sugerida = gastos_pagos * pct_reserva / 12 if gastos_pagos > 0 else gastos_previstos * pct_reserva
    capital_giro_sug = receita_total * pct_capital
    teto_gasto_mens  = (receita_total + receita_prevista) * (1 - margem_min) if (receita_total + receita_prevista) > 0 else 0

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    col_f1.metric("💰 Receita Recebida", brl(receita_total))
    col_f2.metric("📉 Gastos Pagos",     brl(gastos_pagos))
    col_f3.metric("✅ Lucro Real",        brl(lucro_real),
                  delta=f"{pct_str(lucro_real, receita_total)} de margem" if receita_total > 0 else "")
    col_f4.metric("🔮 Lucro Previsto",   brl(lucro_previsto))

    prog_fat = min(receita_total / meta_fat_fin, 1.0) if meta_fat_fin > 0 else 0
    st.progress(prog_fat, text=f"Faturamento: {brl(receita_total)} / {brl(meta_fat_fin)} (meta)")
    st.markdown("<br>", unsafe_allow_html=True)

    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        st.markdown("#### 💡 Capital de Giro")
        st.markdown(f'<div class="kcard"><div class="kcard-title">{brl(capital_giro_sug)}</div><div class="kcard-sub">Sugestão: manter {int(pct_capital*100)}% da receita disponível.</div></div>', unsafe_allow_html=True)
        saldo_capital = lucro_real - capital_giro_sug
        if saldo_capital >= 0:
            st.markdown(f'<div class="fin-ok">✅ Capital de giro adequado. Sobram {brl(saldo_capital)}.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="fin-danger">⚠️ Faltam {brl(abs(saldo_capital))} para o capital mínimo.</div>', unsafe_allow_html=True)

    with col_h2:
        st.markdown("#### 🛡️ Reserva de Emergência")
        st.markdown(f'<div class="kcard"><div class="kcard-title">{brl(reserva_sugerida)}</div><div class="kcard-sub">Sugestão: {pct_reserva} meses de custos guardados.</div></div>', unsafe_allow_html=True)
        if lucro_real >= reserva_sugerida:
            st.markdown(f'<div class="fin-ok">✅ Reserva coberta pelo lucro acumulado.</div>', unsafe_allow_html=True)
        else:
            falta = reserva_sugerida - lucro_real
            st.markdown(f'<div class="fin-alerta">⚠️ Faltam {brl(falta)} para a reserva ideal.</div>', unsafe_allow_html=True)

    with col_h3:
        st.markdown("#### 🎯 Teto de Gastos")
        st.markdown(f'<div class="kcard"><div class="kcard-title">{brl(teto_gasto_mens)}</div><div class="kcard-sub">Para margem mínima de {int(margem_min*100)}%.</div></div>', unsafe_allow_html=True)
        if gastos_pagos <= teto_gasto_mens:
            st.markdown(f'<div class="fin-ok">✅ Dentro do limite. Margem de {brl(teto_gasto_mens - gastos_pagos)}.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="fin-danger">🚨 Gastos {brl(gastos_pagos - teto_gasto_mens)} acima do teto!</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    f_dash, f_gastos, f_pedidos, f_relat = st.tabs([
        "📊 Dashboard", "📝 Lançar Gastos",
        "💳 Pagamentos por Pedido", "📋 Relatório Mensal",
    ])

    with f_dash:
        st.markdown("#### 📊 Visão Financeira Geral")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("**📥 Receitas por Status**")
            rec_pendente = (
                float(df_enc_fin[df_enc_fin["etapa"].astype(int) < 7]["valor_total"].fillna(0).astype(float).sum())
                - float(df_enc_fin[df_enc_fin["etapa"].astype(int) < 7]["valor_recebido"].fillna(0).astype(float).sum())
            ) if not df_enc_fin.empty else 0.0
            df_rec_chart = pd.DataFrame({
                "Categoria": ["Recebido", "Previsto (em andamento)", "A receber (saldo)"],
                "Valor": [receita_total, receita_prevista, rec_pendente],
            })
            st.bar_chart(df_rec_chart.set_index("Categoria"))

        with col_d2:
            st.markdown("**📤 Gastos por Categoria**")
            if not df_g_fin.empty and "categoria" in df_g_fin.columns:
                cat_group = df_g_fin.groupby("categoria")["valor"].sum().reset_index()
                cat_group.columns = ["Categoria","Valor"]
                st.bar_chart(cat_group.set_index("Categoria"))
            else:
                st.info("Nenhum gasto lançado.")

        st.markdown("---")
        st.markdown("**🔄 Fluxo de Caixa – Pedidos Ativos**")
        if not df_enc_fin.empty:
            pedidos_ativos = df_enc_fin[df_enc_fin["etapa"].astype(int) < 7].copy()
            if pedidos_ativos.empty:
                st.info("Nenhum pedido ativo.")
            else:
                pedidos_ativos["Saldo a Receber"] = pedidos_ativos["valor_total"].astype(float) - pedidos_ativos["valor_recebido"].astype(float)
                pedidos_ativos["Entrega"] = pedidos_ativos["data_entrega"].apply(formatar_data_br)
                df_fluxo = pedidos_ativos[["cliente","peca","valor_total","valor_recebido","Saldo a Receber","Entrega"]].copy()
                df_fluxo.columns = ["Cliente","Peça","Total","Recebido","A Receber","Entrega Prevista"]
                for c in ["Total","Recebido","A Receber"]:
                    df_fluxo[c] = df_fluxo[c].apply(lambda x: brl(float(x)))
                st.dataframe(df_fluxo, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("**📆 Contas a Pagar (em aberto)**")
        df_cp = df_g_fin[df_g_fin["pago"].astype(int) == 0].copy() if not df_g_fin.empty else pd.DataFrame()
        if df_cp.empty:
            st.success("✅ Nenhuma conta em aberto.")
        else:
            df_cp["Data"] = df_cp["data"].apply(formatar_data_br)
            df_cp_show = df_cp[["Data","descricao","categoria","valor"]].copy()
            df_cp_show.columns = ["Data","Descrição","Categoria","Valor"]
            df_cp_show["Valor"] = df_cp_show["Valor"].apply(lambda x: brl(float(x)))
            st.dataframe(df_cp_show, use_container_width=True, hide_index=True)
            st.markdown(f'<div class="fin-alerta">Total em aberto: <b>{brl(float(df_cp["valor"].sum()))}</b></div>', unsafe_allow_html=True)

    with f_gastos:
        st.markdown("#### 📝 Lançar Gasto ou Previsão")
        col_g1, col_g2 = st.columns([3, 2])
        with col_g1:
            with st.form("form_gasto_novo", clear_on_submit=True):
                c1, c2 = st.columns(2)
                g_desc = c1.text_input("Descrição do gasto *")
                g_val  = c2.number_input("Valor (R$) *", min_value=0.01, step=10.0, format="%.2f")
                c3, c4 = st.columns(2)
                g_cat  = c3.selectbox("Categoria", CAT_GASTOS)
                g_data = c4.date_input("Data", hoje_brasilia(), format="DD/MM/YYYY")
                c5, c6 = st.columns(2)
                g_pago  = c5.checkbox("Já foi pago?", value=True)
                g_recor = c6.checkbox("Gasto recorrente (mensal)?")

                df_enc_ativos = encomendas_listar(cancelado=False)
                enc_ativos_list = []
                if not df_enc_ativos.empty:
                    enc_ativos_list = [
                        (row["rowid"], f"#{row['rowid'][:6]} – {row['cliente']}: {row['peca']}")
                        for _, row in df_enc_ativos[df_enc_ativos["etapa"].astype(int) < 7].iterrows()
                    ]
                enc_list  = ["— Nenhum (custo fixo/geral) —"] + [e[1] for e in enc_ativos_list]
                g_enc_lbl = st.selectbox("Vincular a pedido? (opcional)", enc_list)
                g_enc_id  = None
                if g_enc_lbl != "— Nenhum (custo fixo/geral) —":
                    idx = enc_list.index(g_enc_lbl) - 1
                    g_enc_id = enc_ativos_list[idx][0]

                if st.form_submit_button("💾 Lançar Gasto", use_container_width=True, type="primary"):
                    if g_desc.strip() and g_val > 0:
                        gastos_inserir({
                            "encomenda_id": g_enc_id,
                            "descricao": g_desc.strip(), "valor": g_val,
                            "data": g_data.isoformat(), "categoria": g_cat,
                            "pago": 1 if g_pago else 0,
                            "recorrente": 1 if g_recor else 0,
                            "criado_em": agora_br().isoformat(),
                        })
                        st.success("✅ Gasto lançado!")
                        st.rerun()
                    else:
                        st.error("Preencha descrição e valor.")

        with col_g2:
            st.markdown("**📊 Resumo por Categoria**")
            if not df_g_fin.empty and "categoria" in df_g_fin.columns:
                df_cat_sum = df_g_fin.groupby("categoria")["valor"].sum().reset_index()
                df_cat_sum.columns = ["Categoria","Total"]
                df_cat_sum = df_cat_sum.sort_values("Total", ascending=False)
                df_cat_sum["Total"] = df_cat_sum["Total"].apply(lambda x: brl(float(x)))
                st.dataframe(df_cat_sum, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum gasto registrado.")

        st.markdown("---")
        st.markdown("#### 📋 Todos os Gastos")
        df_g_fin_fresh = gastos_listar()
        if df_g_fin_fresh.empty:
            st.info("Nenhum gasto registrado.")
        else:
            for _, g in df_g_fin_fresh.iterrows():
                status_g = "✅ Pago" if int(g.get("pago", 0) or 0) else "⏳ Em aberto"
                badge_g  = "badge-green" if int(g.get("pago", 0) or 0) else "badge-amber"
                lancado_em = g.get("criado_em")
                lancado_html = f" &nbsp;|&nbsp; 🕐 lançado em {formatar_data_hora_br(lancado_em)}" if lancado_em else ""
                col_gi, col_gb = st.columns([5, 1])
                col_gi.markdown(f"""
                <div class="kcard">
                  <div class="kcard-title">{g['descricao']} — <b>{brl(float(g.get('valor',0)))}</b></div>
                  <div class="kcard-sub">
                    📂 {g.get('categoria','')} &nbsp;|&nbsp; 📅 {formatar_data_br(g.get('data',''))}{lancado_html}
                    &nbsp;<span class="badge {badge_g}">{status_g}</span>
                    {"&nbsp;<span class='badge badge-blue'>🔁 Recorrente</span>" if int(g.get('recorrente', 0) or 0) else ""}
                  </div>
                </div>""", unsafe_allow_html=True)
                with col_gb:
                    st.write("")
                    if not int(g.get("pago", 0) or 0):
                        if st.button("💳 Quitar", key=f"qt_{g['rowid']}"):
                            gastos_atualizar(str(g["rowid"]), {"pago": 1})
                            st.rerun()
                    else:
                        if st.button("🗑️", key=f"del_g_{g['rowid']}", help="Remover"):
                            gastos_deletar(str(g["rowid"]))
                            st.rerun()

    with f_pedidos:
        st.markdown("#### 💳 Gestão de Pagamentos por Pedido")
        if df_enc_fin.empty:
            st.info("Nenhum pedido cadastrado.")
        else:
            for _, enc in df_enc_fin.iterrows():
                v_total_e  = float(enc.get("valor_total", 0) or 0)
                v_recebido = float(enc.get("valor_recebido", 0) or 0)
                v_restante = v_total_e - v_recebido

                gasto_enc = 0.0
                if not df_g_fin.empty and "encomenda_id" in df_g_fin.columns:
                    gasto_enc = float(df_g_fin[df_g_fin["encomenda_id"] == enc["rowid"]]["valor"].fillna(0).astype(float).sum())
                lucro_enc  = v_recebido - gasto_enc
                margem_enc = lucro_enc / v_recebido * 100 if v_recebido > 0 else 0
                margem_min_val = float(cfg_get("margem_minima_pct") or 30)

                with st.expander(
                    f"👗 {enc['cliente']} – {enc['peca']}  |  "
                    f"Recebido: {brl(v_recebido)} / {brl(v_total_e)}  |  Margem: {margem_enc:.0f}%"
                ):
                    col_pm1, col_pm2, col_pm3, col_pm4 = st.columns(4)
                    col_pm1.metric("Valor Total",  brl(v_total_e))
                    col_pm2.metric("Recebido",     brl(v_recebido))
                    col_pm3.metric("A Receber",    brl(max(v_restante, 0)))
                    col_pm4.metric("Custo Direto", brl(gasto_enc))

                    if margem_enc >= margem_min_val:
                        st.markdown(f'<div class="fin-ok">✅ Margem de <b>{margem_enc:.1f}%</b> — saudável.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="fin-danger">🚨 Margem de <b>{margem_enc:.1f}%</b> abaixo do mínimo ({margem_min_val:.0f}%).</div>', unsafe_allow_html=True)

                    if v_restante > 0.01:
                        col_rec1, col_rec2, col_rec3 = st.columns([2, 2, 1])
                        novo_val = col_rec1.number_input(
                            "Valor recebido (R$)",
                            min_value=0.01, max_value=float(v_restante + 0.01),
                            value=float(v_restante), step=10.0, format="%.2f",
                            key=f"rec_val_{enc['rowid']}",
                        )
                        col_rec2.metric("Saldo após:", brl(v_restante - novo_val))
                        if col_rec3.button("✅ Confirmar", key=f"rec_btn_{enc['rowid']}"):
                            novo_total = v_recebido + novo_val
                            encomendas_atualizar(str(enc["rowid"]), {"valor_recebido": novo_total})
                            st.success(f"✅ {brl(novo_val)} registrado!")
                            st.rerun()

                        if st.button(f"💰 Quitar saldo total ({brl(v_restante)})", key=f"quit_total_{enc['rowid']}"):
                            encomendas_atualizar(str(enc["rowid"]), {"valor_recebido": v_total_e})
                            st.rerun()
                    else:
                        st.markdown('<div class="fin-ok">✅ Pedido totalmente pago.</div>', unsafe_allow_html=True)

    with f_relat:
        st.markdown("#### 📋 Relatório Financeiro Mensal")
        col_rm1, col_rm2 = st.columns(2)
        mes_sel_fin = col_rm1.selectbox("Mês", list(range(1,13)),
            format_func=lambda x: MESES_PT[x-1], index=hoje_dt.month-1, key="mes_rel_fin")
        ano_sel_fin = col_rm2.number_input("Ano", min_value=2020, max_value=2030, value=hoje_dt.year)

        mes_str = f"{ano_sel_fin}-{mes_sel_fin:02d}"

        df_enc_mes = pd.DataFrame()
        if not df_enc_fin.empty and "data_entrega" in df_enc_fin.columns:
            df_enc_mes = df_enc_fin[df_enc_fin["data_entrega"].fillna("").str.startswith(mes_str)]

        df_g_mes = pd.DataFrame()
        if not df_g_fin.empty and "data" in df_g_fin.columns:
            df_g_mes = df_g_fin[df_g_fin["data"].fillna("").str.startswith(mes_str)]

        rec_mes   = float(df_enc_mes["valor_recebido"].fillna(0).astype(float).sum()) if not df_enc_mes.empty else 0.0
        gasto_mes = float(df_g_mes["valor"].fillna(0).astype(float).sum()) if not df_g_mes.empty else 0.0
        lucro_mes = rec_mes - gasto_mes
        margem_mes = lucro_mes / rec_mes * 100 if rec_mes > 0 else 0

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        col_r1.metric("Receita do Mês", brl(rec_mes))
        col_r2.metric("Gastos do Mês",  brl(gasto_mes))
        col_r3.metric("Lucro Líquido",  brl(lucro_mes))
        col_r4.metric("Margem",         f"{margem_mes:.1f}%")

        meta_fat_f = float(cfg_get("meta_faturamento") or 5000)
        if rec_mes >= meta_fat_f:
            st.markdown(f'<div class="fin-ok">🏆 Meta de {brl(meta_fat_f)} atingida!</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="fin-alerta">📌 Faltam {brl(meta_fat_f - rec_mes)} para a meta de {brl(meta_fat_f)}.</div>', unsafe_allow_html=True)

        st.markdown("---")
        col_rt1, col_rt2 = st.columns(2)
        with col_rt1:
            st.markdown("**Pedidos do mês**")
            if df_enc_mes.empty:
                st.info("Nenhum pedido com entrega neste mês.")
            else:
                df_em = df_enc_mes[["cliente","peca","valor_recebido","valor_total"]].copy()
                df_em.columns = ["Cliente","Peça","Recebido","Total"]
                df_em["Recebido"] = df_em["Recebido"].apply(lambda x: brl(float(x)))
                df_em["Total"]    = df_em["Total"].apply(lambda x: brl(float(x)))
                st.dataframe(df_em, use_container_width=True, hide_index=True)

        with col_rt2:
            st.markdown("**Gastos do mês**")
            if df_g_mes.empty:
                st.info("Nenhum gasto registrado neste mês.")
            else:
                df_gm = df_g_mes[["descricao","categoria","valor","pago"]].copy()
                df_gm.columns = ["Descrição","Categoria","Valor","Pago?"]
                df_gm["Valor"] = df_gm["Valor"].apply(lambda x: brl(float(x)))
                df_gm["Pago?"] = df_gm["Pago?"].apply(lambda x: "✅" if int(x or 0) else "⏳")
                st.dataframe(df_gm, use_container_width=True, hide_index=True)

        st.markdown("---")
        if st.button("📥 Exportar Relatório Mensal (Excel)", use_container_width=True):
            buf_xl = io.BytesIO()
            wb     = xlsxwriter.Workbook(buf_xl)
            fmt_h   = wb.add_format({"bold":True,"bg_color":"#3d1f10","font_color":"white","border":1})
            fmt_brl = wb.add_format({"num_format":"R$ #,##0.00","border":1})
            fmt_n   = wb.add_format({"border":1})

            ws1 = wb.add_worksheet("Receitas")
            for ci, h in enumerate(["Cliente","Peça","Total","Recebido","A Receber","Entrega"]):
                ws1.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_enc_mes.iterrows(), 1):
                ws1.write(ri, 0, row.get("cliente",""), fmt_n)
                ws1.write(ri, 1, row.get("peca",""), fmt_n)
                ws1.write(ri, 2, float(row.get("valor_total",0) or 0), fmt_brl)
                ws1.write(ri, 3, float(row.get("valor_recebido",0) or 0), fmt_brl)
                ws1.write(ri, 4, float(row.get("valor_total",0) or 0) - float(row.get("valor_recebido",0) or 0), fmt_brl)
                ws1.write(ri, 5, str(row.get("data_entrega","")), fmt_n)

            ws2 = wb.add_worksheet("Gastos")
            for ci, h in enumerate(["Data","Descrição","Categoria","Valor","Pago?"]):
                ws2.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_g_mes.iterrows(), 1):
                ws2.write(ri, 0, str(row.get("data","")), fmt_n)
                ws2.write(ri, 1, row.get("descricao",""), fmt_n)
                ws2.write(ri, 2, row.get("categoria",""), fmt_n)
                ws2.write(ri, 3, float(row.get("valor",0) or 0), fmt_brl)
                ws2.write(ri, 4, "Sim" if int(row.get("pago",0) or 0) else "Não", fmt_n)

            ws3 = wb.add_worksheet("Resumo")
            ws3.write(0, 0, f"Relatório – {MESES_PT[mes_sel_fin-1]} {ano_sel_fin}",
                      wb.add_format({"bold":True,"font_size":14,"font_color":"#3d1f10"}))
            fmt_key = wb.add_format({"bold":True})
            for ri, (k, v) in enumerate([("Receita Total", rec_mes),("Gastos Totais", gasto_mes),("Lucro Líquido", lucro_mes)], 2):
                ws3.write(ri, 0, k, fmt_key)
                ws3.write(ri, 1, v, fmt_brl)

            wb.close()
            buf_xl.seek(0)
            st.download_button(
                label=f"📥 Baixar Excel – {MESES_PT[mes_sel_fin-1]} {ano_sel_fin}",
                data=buf_xl,
                file_name=f"Lila_Financeiro_{mes_sel_fin:02d}_{ano_sel_fin}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

# ══════════════════════════════════════════════════════════════════════════════
# ABA 5 – CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════════════════════════
with aba_conf:
    st.markdown("### ⚙️ Configurações do Sistema")

    col_cfg1, col_cfg2 = st.columns(2)

    with col_cfg1:
        st.markdown("#### 🏢 Dados da Empresa")
        with st.form("form_empresa"):
            cfg_cnpj = st.text_input("CNPJ",     value=cfg_get("cnpj"))
            cfg_tel  = st.text_input("Telefone", value=cfg_get("telefone"))
            cfg_end  = st.text_input("Endereço", value=cfg_get("endereco"))
            if st.form_submit_button("💾 Salvar Dados da Empresa"):
                cfg_set("cnpj",     cfg_cnpj)
                cfg_set("telefone", cfg_tel)
                cfg_set("endereco", cfg_end)
                st.success("✅ Dados salvos!")

    with col_cfg2:
        st.markdown("#### 🎯 Metas e Parâmetros Financeiros")
        with st.form("form_metas"):
            cfg_meta_fat = st.number_input("Meta de Faturamento Mensal (R$)",
                min_value=0.0, value=float(cfg_get("meta_faturamento") or 5000), step=500.0, format="%.2f")
            cfg_meta_ped = st.number_input("Meta de Pedidos por Mês",
                min_value=1, value=int(cfg_get("meta_pedidos_mes") or 8))
            cfg_margem   = st.slider("Margem Mínima Desejada (%)",
                min_value=10, max_value=80, value=int(cfg_get("margem_minima_pct") or 30))
            cfg_reserva  = st.slider("Meses de Reserva de Emergência",
                min_value=1, max_value=12, value=int(cfg_get("reserva_emergencia_meses") or 3))
            cfg_capital  = st.slider("Capital de Giro (% da Receita)",
                min_value=5, max_value=50, value=int(cfg_get("capital_giro_pct") or 20))
            if st.form_submit_button("💾 Salvar Parâmetros"):
                cfg_set("meta_faturamento",        str(cfg_meta_fat))
                cfg_set("meta_pedidos_mes",        str(cfg_meta_ped))
                cfg_set("margem_minima_pct",       str(cfg_margem))
                cfg_set("reserva_emergencia_meses",str(cfg_reserva))
                cfg_set("capital_giro_pct",        str(cfg_capital))
                st.success("✅ Parâmetros salvos!")
                st.rerun()

    st.markdown("---")
    st.markdown("#### ℹ️ Parâmetros Financeiros")
    st.markdown("""
| Parâmetro | O que é | Referência |
|---|---|---|
| **Meta de Faturamento** | Quanto você quer receber por mês | Definida por você |
| **Margem Mínima** | % do preço que deve sobrar após os custos | 30-40% é saudável |
| **Capital de Giro** | Dinheiro disponível para manter o negócio | 15-25% da receita |
| **Reserva de Emergência** | Meses de custos guardados para imprevistos | Mínimo 3 meses |
""")

    st.markdown("---")
    st.markdown("#### 🗑️ Limpeza (Cuidado!)")
    if st.checkbox("Confirmar exclusão de todos os gastos pagos"):
        if st.button("🗑️ Excluir gastos pagos", use_container_width=True):
            gastos_deletar_pagos()
            st.success("Gastos pagos removidos.")
            st.rerun()

    # ── Exclusão Permanente de Pedido ─────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔐 Exclusão Permanente de Pedido")
    st.markdown(
        "<div class='danger-zone'>"
        "<b>⚠️ ATENÇÃO:</b> Esta operação apaga o pedido, todas as tarefas e gastos vinculados "
        "de forma <b>permanente e irreversível</b>. Necessária senha de administrador."
        "</div>", unsafe_allow_html=True,
    )
    st.markdown("")

    df_todos_pedidos = encomendas_listar()

    if df_todos_pedidos.empty:
        st.info("Nenhum pedido cadastrado.")
    else:
        opcoes_pedidos = {
            f"#{row['rowid'][:6]} – {row['cliente']} | {row['peca']}"
            f" {'[CANCELADO]' if int(row.get('cancelado',0) or 0) else ''}"
            f" [Etapa {row.get('etapa',1)}]": row["rowid"]
            for _, row in df_todos_pedidos.iterrows()
        }

        pedido_sel_label = st.selectbox(
            "Selecione o pedido para DELETAR permanentemente:",
            list(opcoes_pedidos.keys()), key="del_pedido_sel",
        )
        pedido_sel_id = opcoes_pedidos[pedido_sel_label]
        row_sel = df_todos_pedidos[df_todos_pedidos["rowid"] == pedido_sel_id].iloc[0]

        st.markdown(
            f"**Pedido selecionado:** {row_sel['cliente']} | {row_sel['peca']}"
        )

        col_senha, col_btn_del = st.columns([3, 1])
        senha_digitada = col_senha.text_input(
            "🔑 Senha de administrador:", type="password",
            placeholder="Digite a senha para liberar a exclusão",
            key="senha_del_pedido",
        )
        with col_btn_del:
            st.write("")
            st.write("")
            btn_deletar = st.button("🗑️ DELETAR AGORA", use_container_width=True, key="btn_deletar_pedido")

        if btn_deletar:
            if senha_digitada == SENHA_DELETE:
                encomendas_deletar_completo(str(pedido_sel_id))
                st.success(f"✅ Pedido removido permanentemente.")
                st.rerun()
            elif senha_digitada == "":
                st.error("❌ Digite a senha de administrador.")
            else:
                st.error("❌ Senha incorreta.")

    # ── Exclusão Permanente de Cliente ────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔐 Exclusão Permanente de Cadastro de Cliente")
    st.markdown(
        "<div class='danger-zone'>"
        "<b>⚠️ ATENÇÃO:</b> Esta operação apaga o cadastro da cliente (dados pessoais e medidas) "
        "de forma <b>permanente e irreversível</b>. Necessária senha de administrador. "
        "Pedidos já criados para essa cliente <b>não são apagados</b> — eles continuam no histórico, "
        "mas deixam de estar vinculados a uma ficha de cliente."
        "</div>", unsafe_allow_html=True,
    )
    st.markdown("")

    df_todas_clientes = clientes_listar()

    if df_todas_clientes.empty:
        st.info("Nenhuma cliente cadastrada.")
    else:
        opcoes_clientes = {
            f"{row['nome']}" + (f" · {row['telefone']}" if str(row.get('telefone') or '').strip() else ""): row["rowid"]
            for _, row in df_todas_clientes.iterrows()
        }

        cliente_sel_label = st.selectbox(
            "Selecione a cliente para DELETAR permanentemente:",
            list(opcoes_clientes.keys()), key="del_cliente_sel",
        )
        cliente_sel_id = opcoes_clientes[cliente_sel_label]
        row_cli_sel = df_todas_clientes[df_todas_clientes["rowid"] == cliente_sel_id].iloc[0]

        st.markdown(f"**Cliente selecionada:** {row_cli_sel['nome']}")

        col_senha_c, col_btn_del_c = st.columns([3, 1])
        senha_digitada_c = col_senha_c.text_input(
            "🔑 Senha de administrador:", type="password",
            placeholder="Digite a senha para liberar a exclusão",
            key="senha_del_cliente",
        )
        with col_btn_del_c:
            st.write("")
            st.write("")
            btn_deletar_c = st.button("🗑️ DELETAR AGORA", use_container_width=True, key="btn_deletar_cliente")

        if btn_deletar_c:
            if senha_digitada_c == SENHA_DELETE:
                clientes_deletar(str(cliente_sel_id))
                st.success("✅ Cadastro da cliente removido permanentemente.")
                st.rerun()
            elif senha_digitada_c == "":
                st.error("❌ Digite a senha de administrador.")
            else:
                st.error("❌ Senha incorreta.")

st.caption("v10.3.0 | Lila Closet Atelier | Firestore · Horário de Brasília · wendleydesenvolvimento")
