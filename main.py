import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, timedelta
import os
import calendar
import io
import hashlib
import time
import base64

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.utils import ImageReader

# Excel
import xlsxwriter

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
# LOGIN — AUTENTICAÇÃO SIMPLES
# ══════════════════════════════════════════════════════════════════════════════
USUARIOS_VALIDOS = {"Selma": "2061"}

def tela_login():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Inter:wght@300;400;500;600&display=swap');
    html, body, [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #1a0f0a 0%, #3d1f10 50%, #6b3a22 100%) !important;
        font-family: 'Inter', sans-serif;
    }
    [data-testid="stHeader"] { background: transparent !important; }
    .login-box {
        background: rgba(255,255,255,0.97); border-radius: 20px;
        padding: 2.8rem 2.5rem; max-width: 420px; margin: 80px auto 0;
        box-shadow: 0 24px 64px rgba(0,0,0,0.4);
    }
    .login-title {
        font-family: 'Playfair Display', serif; font-size: 1.9rem;
        font-weight: 700; color: #1a0f0a; text-align: center; margin-bottom: 4px;
    }
    .login-sub {
        font-size: 0.78rem; color: #c9a227; text-align: center;
        letter-spacing: 2px; text-transform: uppercase; margin-bottom: 2rem;
    }
    .login-icon { text-align: center; font-size: 3rem; margin-bottom: 0.5rem; }
    </style>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown("""
        <div class="login-box">
          <div class="login-icon">🧵</div>
          <div class="login-title">Lila Closet Atelier</div>
          <div class="login-sub">Acesso Restrito</div>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            st.markdown("<div style='max-width:420px;margin:0 auto;margin-top:-2rem;background:rgba(255,255,255,0.97);border-radius:0 0 20px 20px;padding:0 2.5rem 2.5rem;'>", unsafe_allow_html=True)
            usuario = st.text_input("👤 Usuário", placeholder="Digite seu usuário")
            senha   = st.text_input("🔑 Senha",   placeholder="Digite sua senha", type="password")

            if st.button("Entrar →", use_container_width=True, type="primary"):
                if usuario in USUARIOS_VALIDOS and USUARIOS_VALIDOS[usuario] == senha:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario"]     = usuario
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos.")
            st.markdown("</div>", unsafe_allow_html=True)

# Verificação de autenticação
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    tela_login()
    st.stop()

# ── Logo helper ──────────────────────────────────────────────────────────────
LOGO_PATH = "lila.png"

def get_logo_base64() -> str | None:
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

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
.hero-user { font-size: 0.75rem; color: #f0d090; margin-top: 8px; }

/* ── Abas ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  background: white; border-radius: 12px; padding: 4px;
  gap: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  border-radius: 10px !important; font-weight: 500; font-size: 0.82rem;
  padding: 8px 14px !important; color: #6b5744;
}
[data-testid="stTabs"] [aria-selected="true"] {
  background: linear-gradient(135deg, #3d1f10, #6b3a22) !important;
  color: white !important;
}

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

META_HORAS_CAMPO  = 50.0   # meta mensal de horas no serviço de campo
META_PESO_KG      = 57.0   # peso alvo
PESO_INICIAL_KG   = 70.0   # peso de partida

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def converter_para_data(valor):
    if not valor or str(valor) in ("None", "NoneType", "", "nan"):
        return date.today()
    try:
        if isinstance(valor, (date, datetime)):
            return valor if isinstance(valor, date) else valor.date()
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except Exception:
        return date.today()

def formatar_data_br(data_iso):
    try:
        if isinstance(data_iso, (date, datetime)):
            return data_iso.strftime("%d/%m/%Y")
        return datetime.strptime(str(data_iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(data_iso)

def brl(valor: float) -> str:
    if valor is None:
        valor = 0.0
    return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def pct_str(valor: float, total: float) -> str:
    if total <= 0:
        return "0%"
    return f"{(valor/total*100):.1f}%"

# ══════════════════════════════════════════════════════════════════════════════
# BANCO DE DADOS
# ══════════════════════════════════════════════════════════════════════════════
DB_PATH = "lila_closet.db"

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        # ── Clientes ─────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                nome TEXT, modelo_base TEXT,
                telefone TEXT DEFAULT '', email TEXT DEFAULT '', cpf TEXT DEFAULT '',
                ombros REAL, costas REAL, alt_busto REAL, alt_frente REAL,
                busto REAL, cintura REAL, quadril REAL, larg_braco REAL,
                comp_braco REAL, comprimento REAL, comp_perna REAL,
                coxa REAL, gancho REAL, colarinho REAL, outro TEXT
            )
        """)
        for col in ["telefone TEXT DEFAULT ''", "email TEXT DEFAULT ''", "cpf TEXT DEFAULT ''"]:
            try: c.execute(f"ALTER TABLE clientes ADD COLUMN {col}")
            except: pass

        # ── Encomendas ───────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS encomendas (
                cliente TEXT, peca TEXT, descricao TEXT DEFAULT '',
                valor_total REAL DEFAULT 0, sinal REAL DEFAULT 0,
                valor_recebido REAL DEFAULT 0,
                data_visita TEXT, data_tecido TEXT, data_confeccao TEXT,
                data_prova TEXT, data_entrega TEXT,
                etapa INTEGER DEFAULT 1,
                precisa_tecido INTEGER DEFAULT 0,
                cpf_cliente TEXT DEFAULT '', rg_cliente TEXT DEFAULT '',
                forma_pagamento TEXT DEFAULT 'A combinar',
                observacoes TEXT DEFAULT '',
                cancelado INTEGER DEFAULT 0
            )
        """)
        for col in [
            "descricao TEXT DEFAULT ''",
            "forma_pagamento TEXT DEFAULT 'A combinar'",
            "observacoes TEXT DEFAULT ''",
            "cancelado INTEGER DEFAULT 0",
        ]:
            try: c.execute(f"ALTER TABLE encomendas ADD COLUMN {col}")
            except: pass

        # ── Gastos ───────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS gastos (
                encomenda_id INTEGER DEFAULT NULL,
                descricao TEXT, valor REAL, data TEXT,
                categoria TEXT, pago INTEGER DEFAULT 0,
                recorrente INTEGER DEFAULT 0,
                dia_vencimento INTEGER DEFAULT NULL
            )
        """)
        for col in ["recorrente INTEGER DEFAULT 0", "dia_vencimento INTEGER DEFAULT NULL"]:
            try: c.execute(f"ALTER TABLE gastos ADD COLUMN {col}")
            except: pass

        # ── Cronograma / Agenda ──────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS cronograma (
                tarefa TEXT, categoria TEXT, horas REAL, data TEXT,
                frequencia TEXT, concluida INTEGER DEFAULT 0,
                encomenda_id INTEGER DEFAULT NULL, tipo_agenda TEXT DEFAULT 'Trabalho'
            )
        """)

        # ── Serviço de campo ─────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS campo_horas (
                data TEXT NOT NULL,
                horas REAL NOT NULL,
                descricao TEXT DEFAULT '',
                mes_ano TEXT NOT NULL
            )
        """)

        # ── Registro de peso ─────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS peso_registro (
                data TEXT NOT NULL,
                peso_kg REAL NOT NULL,
                mes_ano TEXT NOT NULL
            )
        """)

        # ── Config ───────────────────────────────────────────────────────
        c.execute("""
            CREATE TABLE IF NOT EXISTS config (
                chave TEXT PRIMARY KEY, valor TEXT
            )
        """)
        defaults = [
            ("meta_faturamento", "5000"),
            ("meta_pedidos_mes", "8"),
            ("margem_minima_pct", "30"),
            ("reserva_emergencia_meses", "3"),
            ("capital_giro_pct", "20"),
            ("cnpj", "40.717.967/0001-03"),
            ("telefone", "(11) 94600-6761"),
            ("endereco", "Embu das Artes – SP"),
        ]
        for k, v in defaults:
            c.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES (?,?)", (k, v))

        conn.commit()

init_db()

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG helpers
# ══════════════════════════════════════════════════════════════════════════════
def cfg_get(chave: str) -> str:
    with get_conn() as conn:
        r = conn.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
    return r[0] if r else ""

def cfg_set(chave: str, valor: str):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO config (chave,valor) VALUES (?,?)", (chave, valor))
        conn.commit()

# ══════════════════════════════════════════════════════════════════════════════
# DELETE / CANCELAR PEDIDO
# ══════════════════════════════════════════════════════════════════════════════
def deletar_pedido_completo(enc_rowid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM encomendas WHERE rowid=?",  (enc_rowid,))
        conn.execute("DELETE FROM cronograma  WHERE encomenda_id=?", (enc_rowid,))
        conn.execute("DELETE FROM gastos      WHERE encomenda_id=?", (enc_rowid,))
        conn.commit()

def cancelar_pedido(enc_rowid: int):
    with get_conn() as conn:
        conn.execute("""
            UPDATE encomendas SET
                cancelado=1, etapa=1, sinal=0, valor_recebido=0,
                data_tecido=NULL, data_confeccao=NULL,
                data_prova=NULL, data_entrega=NULL
            WHERE rowid=?
        """, (enc_rowid,))
        conn.execute("DELETE FROM cronograma WHERE encomenda_id=?", (enc_rowid,))
        conn.execute("DELETE FROM gastos WHERE encomenda_id=? AND pago=0", (enc_rowid,))
        conn.commit()

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
    hoje_br = date.today().strftime("%d/%m/%Y")

    dt_visita  = formatar_data_br(enc.get("data_visita", ""))
    dt_prova   = formatar_data_br(enc.get("data_prova", ""))
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

    cnpj_val  = cfg_get("cnpj")
    tel_val   = cfg_get("telefone")
    end_val   = cfg_get("endereco")

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
        f"Emitido em: <b>{hoje_br}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
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
        ["🎁 Entrega",   "Entrega final da peça pronta e devidamente embalada", dt_entrega],
    ]
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
        f"Lila Closet Atelier · {tel_val} | Contrato N.º {num_contrato} · {hoje_br}", s_rodape))

    doc.build(story)
    return buf.getvalue()

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
    <div class="hero-user">👤 Olá, {st.session_state.get("usuario", "")}!</div>
  </div>
</div>
""", unsafe_allow_html=True)

# Botão de logout no canto superior
col_logout_spacer, col_logout_btn = st.columns([6, 1])
with col_logout_btn:
    if st.button("🚪 Sair", key="btn_logout"):
        st.session_state["autenticado"] = False
        st.session_state["usuario"]     = ""
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# MÉTRICAS DO TOPO — apenas pedidos ativos e meta de pedidos
# ══════════════════════════════════════════════════════════════════════════════
hoje_dt = date.today()
mes_ini = hoje_dt.replace(day=1).isoformat()

with get_conn() as conn:
    df_enc_all = pd.read_sql_query("SELECT * FROM encomendas WHERE cancelado=0", conn)
    df_g_all   = pd.read_sql_query("SELECT * FROM gastos", conn)

enc_ativas = len(df_enc_all[df_enc_all["etapa"] < 7])
meta_ped   = int(cfg_get("meta_pedidos_mes") or 8)

col_m1, col_m2 = st.columns(2)
col_m1.metric("🛍️ Pedidos Ativos",     enc_ativas)
col_m2.metric("📋 Meta de Pedidos/mês", meta_ped)

st.markdown("<br>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ABAS PRINCIPAIS
# ══════════════════════════════════════════════════════════════════════════════
aba_hoje, aba_enc, aba_agenda, aba_fin, aba_conf = st.tabs([
    "⚡ HOJE",
    "🛍️ ENCOMENDAS",
    "📅 AGENDA",
    "💰 FINANCEIRO",
    "⚙️ CONFIGURAÇÕES",
])

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 – O QUE FAZER AGORA  +  VIDA PESSOAL (ocultável)
# ══════════════════════════════════════════════════════════════════════════════
with aba_hoje:
    st.markdown("### ⚡ Tarefas para Hoje e Atrasadas")

    with get_conn() as conn:
        df_hoje = pd.read_sql_query(
            """SELECT c.rowid, c.*, e.cliente as nome_cliente
               FROM cronograma c
               LEFT JOIN encomendas e ON c.encomenda_id = e.rowid
               WHERE c.data <= ? AND c.concluida = 0 AND c.tipo_agenda='Trabalho'
               ORDER BY c.data ASC""",
            conn, params=(hoje_dt.isoformat(),),
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
            cliente_txt = f" &nbsp;|&nbsp; 👤 {row['nome_cliente']}" if row.get('nome_cliente') else ""

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
                    with get_conn() as conn:
                        if row.get("encomenda_id"):
                            res = conn.execute(
                                "SELECT etapa, precisa_tecido FROM encomendas WHERE rowid=?",
                                (int(row["encomenda_id"]),),
                            ).fetchone()
                            if res:
                                prox = res[0] + 1
                                if prox == 2: prox = 3
                                if prox == 3 and res[1] == 0: prox = 4
                                if prox <= 7:
                                    conn.execute(
                                        "UPDATE encomendas SET etapa=? WHERE rowid=?",
                                        (prox, int(row["encomenda_id"])),
                                    )
                        conn.execute("UPDATE cronograma SET concluida=1 WHERE rowid=?", (int(row["rowid"]),))
                        conn.commit()
                    st.rerun()

    st.divider()
    st.markdown("### 📦 Pedidos Entregues Hoje")
    with get_conn() as conn:
        df_ent_hoje = pd.read_sql_query(
            "SELECT * FROM encomendas WHERE data_entrega=? AND etapa>=6 AND cancelado=0",
            conn, params=(hoje_dt.isoformat(),),
        )
    if df_ent_hoje.empty:
        st.info("Nenhuma entrega programada para hoje.")
    else:
        for _, r in df_ent_hoje.iterrows():
            st.success(f"🎁 **{r['cliente']}** – {r['peca']} | {brl(r['valor_total'])}")

    # ══════════════════════════════════════════════════════════════════════
    # VIDA PESSOAL — ocultável, dentro da aba HOJE
    # ══════════════════════════════════════════════════════════════════════
    st.divider()
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
                data_p  = st.date_input("Data", date.today(), key="data_p_hoje")
                horas_p = st.number_input("Duração (h)", 0.5, 12.0, 1.0, step=0.5, key="horas_p_hoje")
                if st.form_submit_button("🗓️ Agendar", use_container_width=True):
                    if desc_p.strip():
                        with get_conn() as conn:
                            conn.execute(
                                "INSERT INTO cronograma (tarefa,categoria,horas,data,frequencia,concluida,tipo_agenda) VALUES (?,?,?,?,?,0,?)",
                                (desc_p.strip(), cat_p, horas_p, data_p.isoformat(), "Pontual", "Pessoal"),
                            )
                            conn.commit()
                        st.success("Agendado!")
                        st.rerun()

        with col_list:
            st.markdown("#### ⏳ Pendentes")
            with get_conn() as conn:
                df_p = pd.read_sql_query(
                    "SELECT rowid, data, tarefa, categoria FROM cronograma WHERE tipo_agenda='Pessoal' AND concluida=0 ORDER BY data ASC",
                    conn,
                )
            if df_p.empty:
                st.info("Tudo em dia! ✅")
            else:
                for _, row in df_p.iterrows():
                    col_tx, col_bt = st.columns([4,1])
                    col_tx.markdown(
                        f"**{formatar_data_br(row['data'])}** – {row['tarefa']} *(_{row['categoria']}_)*"
                    )
                    if col_bt.button("✅", key=f"pess_hoje_{row['rowid']}"):
                        with get_conn() as conn:
                            conn.execute("UPDATE cronograma SET concluida=1 WHERE rowid=?", (row["rowid"],))
                            conn.commit()
                        st.rerun()

        st.markdown('<div class="sep-pessoal"></div>', unsafe_allow_html=True)

        col_tog1, col_tog2 = st.columns(2)
        mostrar_campo = col_tog1.toggle("📖 Mostrar Serviço de Campo", value=True, key="tog_campo_hoje")
        mostrar_peso  = col_tog2.toggle("⚖️ Mostrar Progresso de Peso",  value=True, key="tog_peso_hoje")

        # ── SERVIÇO DE CAMPO ─────────────────────────────────────────────
        if mostrar_campo:
            st.markdown("#### 📖 Serviço de Campo — Horas de Pregação")
            st.caption(f"Meta mensal: **{META_HORAS_CAMPO:.0f} horas**")

            col_cm1, col_cm2, _ = st.columns([2, 2, 4])
            mes_campo = col_cm1.selectbox(
                "Mês", list(range(1,13)),
                format_func=lambda x: MESES_PT[x-1],
                index=hoje_dt.month - 1,
                key="mes_campo_sel_hoje",
            )
            ano_campo = col_cm2.number_input("Ano", min_value=2020, max_value=2035,
                                              value=hoje_dt.year, key="ano_campo_sel_hoje")
            mes_ano_campo = f"{ano_campo}-{mes_campo:02d}"

            with st.form("form_campo_horas_hoje", clear_on_submit=True):
                cc1, cc2, cc3 = st.columns([2, 1, 3])
                c_data  = cc1.date_input("Data da saída", date.today(), key="c_data_hoje")
                c_horas = cc2.number_input("Horas", 0.5, 24.0, 1.0, step=0.5, key="c_horas_hoje")
                c_desc  = cc3.text_input("Observação (opcional)", placeholder="Ex: Território 5, porta a porta…", key="c_desc_hoje")
                if st.form_submit_button("➕ Lançar Horas", use_container_width=True):
                    with get_conn() as conn:
                        conn.execute(
                            "INSERT INTO campo_horas (data, horas, descricao, mes_ano) VALUES (?,?,?,?)",
                            (c_data.isoformat(), c_horas, c_desc.strip(),
                             f"{c_data.year}-{c_data.month:02d}"),
                        )
                        conn.commit()
                    st.success(f"✅ {c_horas}h registradas para {formatar_data_br(c_data)}!")
                    st.rerun()

            with get_conn() as conn:
                df_campo = pd.read_sql_query(
                    "SELECT * FROM campo_horas WHERE mes_ano=? ORDER BY data ASC",
                    conn, params=(mes_ano_campo,),
                )
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

            with get_conn() as conn:
                df_campo_hist = pd.read_sql_query(
                    "SELECT mes_ano, SUM(horas) as total FROM campo_horas GROUP BY mes_ano ORDER BY mes_ano DESC",
                    conn,
                )

            if not df_campo_hist.empty:
                st.markdown("**📊 Histórico de horas por mês:**")
                df_campo_hist["Mês"] = df_campo_hist["mes_ano"].apply(
                    lambda m: f"{MESES_PT[int(m[5:7])-1]} {m[:4]}"
                )
                df_campo_hist["Total"] = df_campo_hist["total"].apply(lambda h: f"{h:.1f}h")
                df_campo_hist["✅ Meta?"] = df_campo_hist["total"].apply(
                    lambda h: "🏆 Sim" if h >= META_HORAS_CAMPO else f"⏳ Faltaram {META_HORAS_CAMPO-h:.1f}h"
                )
                st.dataframe(
                    df_campo_hist[["Mês","Total","✅ Meta?"]],
                    use_container_width=True, hide_index=True,
                )

            if not df_campo.empty:
                with st.expander(f"📋 Lançamentos de {MESES_PT[mes_campo-1]} {ano_campo}"):
                    for _, row in df_campo.iterrows():
                        col_d, col_h, col_ds, col_del = st.columns([2, 1, 4, 1])
                        col_d.markdown(f"**{formatar_data_br(row['data'])}**")
                        col_h.markdown(f"⏱️ {row['horas']}h")
                        col_ds.markdown(row["descricao"] or "—")
                        if col_del.button("🗑️", key=f"del_campo_hoje_{row['rowid']}"):
                            with get_conn() as conn:
                                conn.execute("DELETE FROM campo_horas WHERE rowid=?", (row["rowid"],))
                                conn.commit()
                            st.rerun()

        # ── EMAGRECIMENTO ─────────────────────────────────────────────────
        if mostrar_peso:
            st.markdown("#### ⚖️ Acompanhamento de Emagrecimento")
            st.caption(f"Meta: chegar a **{META_PESO_KG} kg** · Peso inicial: **{PESO_INICIAL_KG} kg**")

            col_pm1, col_pm2 = st.columns([3, 2])
            with col_pm1:
                with st.form("form_peso_hoje", clear_on_submit=True):
                    pc1, pc2 = st.columns(2)
                    p_data = pc1.date_input("Data da pesagem", date.today(), key="p_data_hoje")
                    p_peso = pc2.number_input("Peso atual (kg)", min_value=30.0, max_value=200.0,
                                               value=70.0, step=0.1, format="%.1f", key="p_peso_hoje")
                    if st.form_submit_button("📝 Registrar Peso", use_container_width=True):
                        mes_ano_p = f"{p_data.year}-{p_data.month:02d}"
                        with get_conn() as conn:
                            existing = conn.execute(
                                "SELECT rowid FROM peso_registro WHERE mes_ano=?", (mes_ano_p,)
                            ).fetchone()
                            if existing:
                                conn.execute(
                                    "UPDATE peso_registro SET data=?, peso_kg=? WHERE rowid=?",
                                    (p_data.isoformat(), p_peso, existing[0]),
                                )
                            else:
                                conn.execute(
                                    "INSERT INTO peso_registro (data, peso_kg, mes_ano) VALUES (?,?,?)",
                                    (p_data.isoformat(), p_peso, mes_ano_p),
                                )
                            conn.commit()
                        st.success(f"✅ Peso {p_peso:.1f} kg registrado!")
                        st.rerun()

            with get_conn() as conn:
                df_peso = pd.read_sql_query(
                    "SELECT * FROM peso_registro ORDER BY mes_ano ASC", conn)

            with col_pm2:
                if not df_peso.empty:
                    peso_atual = float(df_peso.iloc[-1]["peso_kg"])
                    perdido    = PESO_INICIAL_KG - peso_atual
                    falta_peso = max(peso_atual - META_PESO_KG, 0)
                    total_perder = PESO_INICIAL_KG - META_PESO_KG
                    pct_peso   = min(perdido / total_perder, 1.0) if total_perder > 0 else 0

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
                    st.info("Nenhum peso registrado ainda. Faça o primeiro lançamento!")

            if not df_peso.empty:
                st.markdown("**📈 Evolução mensal do peso:**")
                df_peso["Mês"] = df_peso["mes_ano"].apply(
                    lambda m: f"{MESES_PT[int(m[5:7])-1]}/{m[:4]}"
                )
                df_peso["Peso (kg)"] = df_peso["peso_kg"]
                df_chart = df_peso[["Mês","Peso (kg)"]].set_index("Mês")
                st.line_chart(df_chart, height=180)

                # Tabela — FIX: mantém mes_ano como coluna separada para sort
                df_peso_show = df_peso.copy()
                df_peso_show["Variação"] = df_peso_show["peso_kg"].diff().apply(
                    lambda x: (f"▼ {abs(x):.1f} kg" if x < 0 else (f"▲ {x:.1f} kg" if x > 0 else "—"))
                    if pd.notna(x) else "—"
                )
                df_peso_show["Mês/Ano"] = df_peso_show["mes_ano"].apply(
                    lambda m: f"{MESES_PT[int(m[5:7])-1]} {m[:4]}"
                )
                df_peso_show["Data"]    = df_peso_show["data"].apply(formatar_data_br)
                df_peso_show["Peso"]    = df_peso_show["peso_kg"].apply(lambda x: f"{x:.1f} kg")
                df_peso_show_sorted = df_peso_show.sort_values("mes_ano", ascending=False)
                st.dataframe(
                    df_peso_show_sorted[["Mês/Ano","Data","Peso","Variação"]],
                    use_container_width=True, hide_index=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 – ENCOMENDAS
# ══════════════════════════════════════════════════════════════════════════════
with aba_enc:
    t_nova_cli, t_novo_ped, t_medidas, t_gerenciar = st.tabs([
        "👤 Nova Cliente",
        "🛍️ Novo Pedido",
        "📏 Medidas",
        "📋 Gerenciar Pedidos",
    ])

    # ── Nova Cliente ─────────────────────────────────────────────────────
    with t_nova_cli:
        st.markdown("### 👤 Cadastro de Nova Cliente")
        with st.form("cad_cliente", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            nc_nome = col_a.text_input("Nome completo *")
            nc_mod  = col_b.text_input("Modelo de referência")
            col_c, col_d, col_e = st.columns(3)
            nc_tel   = col_c.text_input("Telefone / WhatsApp")
            nc_email = col_d.text_input("E-mail")
            nc_cpf   = col_e.text_input("CPF")
            if st.form_submit_button("💾 Salvar Cliente", use_container_width=True):
                if nc_nome.strip():
                    with get_conn() as conn:
                        conn.execute(
                            "INSERT INTO clientes (nome, modelo_base, telefone, email, cpf) VALUES (?,?,?,?,?)",
                            (nc_nome.strip(), nc_mod.strip(), nc_tel.strip(), nc_email.strip(), nc_cpf.strip()),
                        )
                        conn.commit()
                    st.success(f"✅ Cliente **{nc_nome}** cadastrada!")
                    st.rerun()
                else:
                    st.error("Informe o nome da cliente.")

        st.markdown("---")
        st.markdown("#### 👥 Clientes Cadastradas")
        with get_conn() as conn:
            df_clis_lista = pd.read_sql_query(
                "SELECT rowid, nome, telefone, email, modelo_base FROM clientes ORDER BY nome", conn)
        if not df_clis_lista.empty:
            df_clis_lista.columns = ["ID","Nome","Telefone","E-mail","Modelo Base"]
            st.dataframe(df_clis_lista.drop(columns=["ID"]), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma cliente cadastrada ainda.")

    # ── Novo Pedido ──────────────────────────────────────────────────────
    with t_novo_ped:
        st.markdown("### 🛍️ Registrar Nova Encomenda")
        with get_conn() as conn:
            clis = pd.read_sql_query("SELECT nome FROM clientes ORDER BY nome", conn)["nome"].tolist()

        if not clis:
            st.info("Cadastre uma cliente primeiro na aba **👤 Nova Cliente**.")
        else:
            tem_tecido = st.radio(
                "Precisa comprar tecido?",
                ["Não – tecido já disponível", "Sim – precisa comprar"],
                horizontal=True,
            )
            precisa_tecido = 1 if "Sim" in tem_tecido else 0

            with st.form("novo_pedido", clear_on_submit=False):
                st.markdown("#### 🧵 Dados da Peça")
                col_p1, col_p2 = st.columns([2, 3])
                cli_sel  = col_p1.selectbox("Cliente *", clis)
                peca     = col_p2.text_input("Peça / Serviço *", placeholder="Ex: Vestido de festa, Calça social…")
                descricao_ped = st.text_area(
                    "Descrição detalhada (tecido, cor, modelo, referências…)",
                    placeholder="Vestido midi em crepe azul marinho, decote V, manga 3/4, saia evasê…",
                    height=80,
                )

                st.markdown("#### 💰 Valores")
                col_v1, col_v2, col_v3 = st.columns(3)
                v_total  = col_v1.number_input("Valor Total (R$) *", min_value=0.0, step=50.0, format="%.2f")
                v_sinal  = col_v2.number_input("Sinal / Entrada (R$)", min_value=0.0, step=50.0, format="%.2f")
                forma_pag = col_v3.selectbox(
                    "Forma de Pagamento",
                    ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"],
                )

                st.markdown("#### 📅 Cronograma")
                col_d1, col_d2 = st.columns(2)
                d_visita = col_d1.date_input("🤝 Visita / Medidas", value=date.today())
                d_tec    = col_d2.date_input("🛍️ Compra do Tecido", value=date.today() + timedelta(days=3)) if precisa_tecido else None

                col_d3, col_d4, col_d5 = st.columns(3)
                d_conf  = col_d3.date_input("🪡 Confecção",   value=date.today() + timedelta(days=7))
                d_prova = col_d4.date_input("👗 Prova",        value=date.today() + timedelta(days=25))
                d_ent   = col_d5.date_input("🎁 Entrega",      value=date.today() + timedelta(days=30))

                st.markdown("#### 📄 Dados para Contrato")
                col_c1, col_c2, col_c3 = st.columns(3)
                cpf_novo = col_c1.text_input("CPF da cliente", placeholder="000.000.000-00")
                rg_novo  = col_c2.text_input("RG da cliente",  placeholder="00.000.000-0")
                obs_ped  = col_c3.text_area("Observações", height=68)

                submitted = st.form_submit_button(
                    "🎯 CONFIRMAR ENCOMENDA E GERAR CONTRATO",
                    use_container_width=True, type="primary",
                )

            if submitted:
                if peca.strip() and cli_sel:
                    with get_conn() as conn:
                        cur = conn.cursor()
                        d_tec_str = d_tec.isoformat() if d_tec else d_conf.isoformat()
                        cur.execute(
                            """INSERT INTO encomendas
                               (cliente, peca, descricao, valor_total, sinal, valor_recebido,
                                etapa, precisa_tecido, data_visita, data_tecido, data_confeccao,
                                data_prova, data_entrega, cpf_cliente, rg_cliente,
                                forma_pagamento, observacoes)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (cli_sel, peca.strip(), descricao_ped.strip(),
                             v_total, v_sinal, v_sinal,
                             1, precisa_tecido,
                             d_visita.isoformat(), d_tec_str, d_conf.isoformat(),
                             d_prova.isoformat(), d_ent.isoformat(),
                             cpf_novo.strip(), rg_novo.strip(), forma_pag, obs_ped.strip()),
                        )
                        e_id = cur.lastrowid
                        desc = f"{peca.strip()} ({cli_sel})"

                        tarefas_auto = [
                            (f"🤝 Visita: {desc}",    "Costura", 1.0, d_visita.isoformat()),
                            (f"🪡 Confecção: {desc}", "Costura", 3.0, d_conf.isoformat()),
                            (f"👗 Prova: {desc}",     "Costura", 1.0, d_prova.isoformat()),
                            (f"🎁 Entrega: {desc}",   "Costura", 0.5, d_ent.isoformat()),
                        ]
                        if precisa_tecido and d_tec:
                            tarefas_auto.insert(1, (f"🛍️ Tecido: {desc}", "Compras", 1.0, d_tec.isoformat()))

                        for tarefa, cat, hrs, dt in tarefas_auto:
                            conn.execute(
                                "INSERT INTO cronograma VALUES (?,?,?,?,?,0,?,?)",
                                (tarefa, cat, hrs, dt, "Pontual", e_id, "Trabalho"),
                            )
                        conn.commit()

                    st.success(f"✅ Encomenda **{peca.strip()}** registrada para **{cli_sel}**!")

                    if cpf_novo.strip() and rg_novo.strip():
                        enc_dict = {
                            "cliente": cli_sel, "peca": peca.strip(),
                            "descricao": descricao_ped, "valor_total": v_total,
                            "sinal": v_sinal, "forma_pagamento": forma_pag,
                            "data_visita": d_visita.isoformat(),
                            "data_tecido": d_tec.isoformat() if d_tec else "",
                            "data_confeccao": d_conf.isoformat(),
                            "data_prova": d_prova.isoformat(),
                            "data_entrega": d_ent.isoformat(),
                            "precisa_tecido": precisa_tecido,
                            "observacoes": obs_ped,
                        }
                        pdf_bytes = gerar_pdf_contrato(enc_dict, cpf_novo.strip(), rg_novo.strip())
                        col_pdf, col_gov = st.columns(2)
                        col_pdf.download_button(
                            label="📥 BAIXAR CONTRATO PDF",
                            data=pdf_bytes,
                            file_name=f"Contrato_{cli_sel.replace(' ','_')}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                        col_gov.link_button(
                            "✍️ ASSINAR VIA GOV.BR",
                            url="https://assinador.iti.br/assinatura/index.xhtml",
                            use_container_width=True,
                        )
                    else:
                        st.info("💡 Preencha CPF e RG para gerar o contrato PDF.")
                else:
                    st.error("Preencha o nome da peça e selecione a cliente.")

    # ── Medidas ──────────────────────────────────────────────────────────
    with t_medidas:
        st.markdown("### 📏 Ficha de Medidas")
        with get_conn() as conn:
            df_c = pd.read_sql_query("SELECT rowid, * FROM clientes ORDER BY nome", conn)

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
                    val_f = float(raw) if raw not in [None, "", "nan"] else 0.0
                    target = col1 if i < 5 else (col2 if i < 10 else col3)
                    novos[col_db] = target.number_input(f"{label} (cm)", value=val_f, format="%.1f", step=0.5)
                obs = st.text_area("Observações de modelagem", value=str(dados_cli.get("outro") or ""))

                if st.form_submit_button("💾 Salvar Medidas", use_container_width=True):
                    with get_conn() as conn:
                        set_q = ", ".join([f"{c}=?" for c in novos])
                        conn.execute(
                            f"UPDATE clientes SET {set_q}, outro=? WHERE rowid=?",
                            list(novos.values()) + [obs, int(dados_cli["rowid"])],
                        )
                        conn.commit()
                    st.success("✅ Medidas salvas!")
                    st.rerun()

    # ── Gerenciar Pedidos ────────────────────────────────────────────────
    with t_gerenciar:
        st.markdown("### 📋 Todos os Pedidos")

        col_f1, col_f2 = st.columns([2,1])
        filtro_status = col_f1.radio(
            "Filtrar:",
            ["Todos","Em andamento","Concluídos","Cancelados"],
            horizontal=True, key="filtro_ger",
        )
        filtro_cli = col_f2.text_input("🔍 Buscar cliente", key="busca_ger")

        with get_conn() as conn:
            df_e = pd.read_sql_query("SELECT rowid, * FROM encomendas ORDER BY rowid DESC", conn)

        if not df_e.empty:
            if filtro_status == "Em andamento":
                df_e = df_e[(df_e["etapa"] < 7) & (df_e["cancelado"] == 0)]
            elif filtro_status == "Concluídos":
                df_e = df_e[(df_e["etapa"] == 7) & (df_e["cancelado"] == 0)]
            elif filtro_status == "Cancelados":
                df_e = df_e[df_e["cancelado"] == 1]
            if filtro_cli.strip():
                df_e = df_e[df_e["cliente"].str.contains(filtro_cli, case=False, na=False)]

        if df_e.empty:
            st.info("Nenhum pedido encontrado com os filtros selecionados.")
        else:
            for _, enc in df_e.iterrows():
                etapa_num = int(enc["etapa"])
                etapa_ic, etapa_nm = ETAPAS.get(etapa_num, ("📦","–"))
                status_label = etapa_ic + " " + etapa_nm
                cancelado    = bool(enc.get("cancelado", 0))
                restante_enc = float(enc.get("valor_total", 0) or 0) - float(enc.get("valor_recebido", 0) or 0)
                badge_txt    = "❌ Cancelado" if cancelado else status_label

                with st.expander(
                    f"{'~~' if cancelado else ''}📦 {enc['cliente']}  —  {enc['peca']}{'~~' if cancelado else ''}"
                    f"  |  {badge_txt}  |  💰 {brl(float(enc.get('valor_total',0) or 0))}"
                ):
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

                    st.markdown("##### 📄 Contrato")
                    col_cpf, col_rg = st.columns(2)
                    cpf_s = str(enc.get("cpf_cliente") or "")
                    rg_s  = str(enc.get("rg_cliente") or "")
                    v_cpf = col_cpf.text_input("CPF", value=cpf_s, key=f"cpf_{enc['rowid']}")
                    v_rg  = col_rg.text_input("RG",   value=rg_s,  key=f"rg_{enc['rowid']}")

                    if v_cpf != cpf_s or v_rg != rg_s:
                        with get_conn() as conn:
                            conn.execute(
                                "UPDATE encomendas SET cpf_cliente=?, rg_cliente=? WHERE rowid=?",
                                (v_cpf, v_rg, enc["rowid"]),
                            )
                            conn.commit()

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
                    with st.form(f"edit_{enc['rowid']}"):
                        ed_peca = st.text_input("Peça", value=str(enc.get("peca") or ""))
                        ed_desc = st.text_area("Descrição", value=str(enc.get("descricao") or ""), height=60)
                        col_f1e, col_f2e = st.columns(2)
                        ed_fpag = col_f1e.selectbox(
                            "Forma de Pagamento",
                            ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"],
                            index=["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"].index(
                                enc.get("forma_pagamento","A combinar")
                                if enc.get("forma_pagamento","") in ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"]
                                else "A combinar"
                            ),
                        )
                        ed_obs = col_f2e.text_area("Observações", value=str(enc.get("observacoes") or ""), height=60)

                        st.markdown("📅 Datas")
                        d1, d2, d3 = st.columns(3)
                        ed_vis  = d1.date_input("Visita",    value=converter_para_data(enc.get("data_visita")),    key=f"dv_{enc['rowid']}")
                        ed_tec  = d2.date_input("Tecido",    value=converter_para_data(enc.get("data_tecido")),    key=f"dt_{enc['rowid']}")
                        ed_conf = d3.date_input("Confecção", value=converter_para_data(enc.get("data_confeccao")), key=f"dc_{enc['rowid']}")
                        d4, d5 = st.columns(2)
                        ed_pro  = d4.date_input("Prova",   value=converter_para_data(enc.get("data_prova")),   key=f"dp_{enc['rowid']}")
                        ed_ent  = d5.date_input("Entrega", value=converter_para_data(enc.get("data_entrega")), key=f"de_{enc['rowid']}")

                        col_b1, col_b2, col_b3 = st.columns(3)
                        if col_b1.form_submit_button("💾 Salvar", use_container_width=True):
                            with get_conn() as conn:
                                conn.execute(
                                    """UPDATE encomendas SET peca=?, descricao=?, forma_pagamento=?,
                                       observacoes=?, data_visita=?, data_tecido=?,
                                       data_confeccao=?, data_prova=?, data_entrega=?
                                       WHERE rowid=?""",
                                    (ed_peca, ed_desc, ed_fpag, ed_obs,
                                     ed_vis.isoformat(), ed_tec.isoformat(), ed_conf.isoformat(),
                                     ed_pro.isoformat(), ed_ent.isoformat(), enc["rowid"]),
                                )
                                conn.commit()
                            st.rerun()

                        if not cancelado:
                            if col_b2.form_submit_button("✅ Marcar Concluído", use_container_width=True):
                                with get_conn() as conn:
                                    conn.execute("UPDATE encomendas SET etapa=7 WHERE rowid=?", (enc["rowid"],))
                                    conn.commit()
                                st.rerun()
                            if col_b3.form_submit_button("❌ Cancelar Pedido", use_container_width=True):
                                cancelar_pedido(int(enc["rowid"]))
                                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 – AGENDA
# ══════════════════════════════════════════════════════════════════════════════
with aba_agenda:
    sub_trabalho, sub_cal = st.tabs([
        "🛠️ Trabalho", "📅 Calendário",
    ])

    with sub_trabalho:
        st.markdown("#### 🛠️ Agenda de Trabalho Pendente")
        with get_conn() as conn:
            df_t = pd.read_sql_query(
                """SELECT c.data, c.tarefa, c.categoria, c.horas, e.cliente
                   FROM cronograma c
                   LEFT JOIN encomendas e ON c.encomenda_id=e.rowid
                   WHERE c.tipo_agenda='Trabalho' AND c.concluida=0
                   ORDER BY c.data ASC""",
                conn,
            )
        if df_t.empty:
            st.success("Nenhuma tarefa pendente!")
        else:
            df_t["Data"]     = df_t["data"].apply(formatar_data_br)
            df_t["Atrasada?"] = df_t["data"].apply(lambda d: "⚠️ Sim" if d < hoje_dt.isoformat() else "Não")
            df_show = df_t[["Data","tarefa","categoria","horas","cliente","Atrasada?"]].copy()
            df_show.columns = ["Data","Tarefa","Categoria","Horas","Cliente","Atrasada?"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

    # ── Calendário — nome COMPLETO do cliente ────────────────────────────
    with sub_cal:
        if "data_ref" not in st.session_state:
            st.session_state.data_ref = date.today()

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

        with get_conn() as conn:
            df_all_cal = pd.read_sql_query(
                """SELECT c.data, c.tarefa, c.tipo_agenda, c.horas,
                   COALESCE(e.cliente,'') AS cliente
                   FROM cronograma c
                   LEFT JOIN encomendas e ON c.encomenda_id=e.rowid
                   WHERE c.concluida=0 AND c.tipo_agenda='Trabalho'""",
                conn,
            )

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
                tasks  = df_all_cal[df_all_cal["data"] == dt_str]
                is_hoje = dt_str == date.today().isoformat()
                fundo   = "#fdf6ee" if is_hoje else "white"
                borda   = "2px solid #c9a227" if is_hoje else "1px solid #ede3d8"

                tarefas_html = ""
                for _, r in tasks.iterrows():
                    tarefa_txt  = r["tarefa"]
                    # Nome COMPLETO do cliente (sem cortar)
                    cliente_cal = r["cliente"]

                    # Tipo de tarefa (antes dos ":")
                    tipo_tarefa = tarefa_txt.split(":")[0].strip() if ":" in tarefa_txt else tarefa_txt[:16]

                    tarefas_html += (
                        f"<div style='font-size:0.6rem;color:#1565c0;margin-top:2px;"
                        f"background:#e3f2fd;border-radius:4px;padding:1px 4px;'>"
                        f"{tipo_tarefa}"
                        f"{'<br><span style=\"color:#3d1f10;font-weight:700;font-size:0.58rem\">' + cliente_cal + '</span>' if cliente_cal else ''}"
                        f"</div>"
                    )

                cols_s[i].markdown(
                    f"<div style='background:{fundo};border:{borda};border-radius:8px;"
                    f"padding:6px;min-height:76px;'>"
                    f"<b style='color:#3d1f10;font-size:0.8rem'>{dia}</b>"
                    f"{tarefas_html}</div>",
                    unsafe_allow_html=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# ABA 4 – FINANCEIRO COMPLETO
# ══════════════════════════════════════════════════════════════════════════════
with aba_fin:
    st.markdown("### 💰 Controle Financeiro Profissional")

    with get_conn() as conn:
        df_enc_fin = pd.read_sql_query("SELECT rowid, * FROM encomendas WHERE cancelado=0", conn)
        df_g_fin   = pd.read_sql_query("SELECT rowid, * FROM gastos", conn)

    receita_total   = float(df_enc_fin["valor_recebido"].sum() or 0)
    receita_prevista= float(df_enc_fin[df_enc_fin["etapa"] < 7]["valor_total"].sum() or 0)
    gastos_pagos    = float(df_g_fin[df_g_fin["pago"] == 1]["valor"].sum() or 0)
    gastos_previstos= float(df_g_fin[df_g_fin["pago"] == 0]["valor"].sum() or 0)
    lucro_real      = receita_total - gastos_pagos
    lucro_previsto  = (receita_total + receita_prevista) - (gastos_pagos + gastos_previstos)

    pct_reserva   = int(cfg_get("reserva_emergencia_meses") or 3)
    pct_capital   = float(cfg_get("capital_giro_pct") or 20) / 100
    margem_min    = float(cfg_get("margem_minima_pct") or 30) / 100
    meta_fat_fin  = float(cfg_get("meta_faturamento") or 5000)

    reserva_sugerida = gastos_pagos * pct_reserva / 12 if gastos_pagos > 0 else gastos_previstos * pct_reserva
    capital_giro_sug = receita_total * pct_capital
    teto_gasto_mens  = (receita_total + receita_prevista) * (1 - margem_min) if (receita_total + receita_prevista) > 0 else 0

    # Métricas financeiras completas na aba financeiro
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    col_f1.metric("💰 Receita Recebida",  brl(receita_total))
    col_f2.metric("📉 Gastos Pagos",      brl(gastos_pagos))
    col_f3.metric("✅ Lucro Real",         brl(lucro_real),
                  delta=f"{pct_str(lucro_real, receita_total)} de margem" if receita_total > 0 else "")
    col_f4.metric("🔮 Lucro Previsto",    brl(lucro_previsto))

    # Barra de meta de faturamento
    prog_fat = min(receita_total / meta_fat_fin, 1.0) if meta_fat_fin > 0 else 0
    st.progress(prog_fat, text=f"Faturamento: {brl(receita_total)} / {brl(meta_fat_fin)} (meta)")

    st.markdown("<br>", unsafe_allow_html=True)

    col_h1, col_h2, col_h3 = st.columns(3)

    with col_h1:
        st.markdown("#### 💡 Capital de Giro")
        st.markdown(f"""
        <div class="kcard">
          <div class="kcard-title">{brl(capital_giro_sug)}</div>
          <div class="kcard-sub">Sugestão: manter {int(pct_capital*100)}% da receita disponível como capital de giro para insumos e emergências.</div>
        </div>
        """, unsafe_allow_html=True)
        saldo_capital = lucro_real - capital_giro_sug
        if saldo_capital >= 0:
            st.markdown(f'<div class="fin-ok">✅ Capital de giro adequado. Você tem {brl(saldo_capital)} além do recomendado.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="fin-danger">⚠️ Faltam {brl(abs(saldo_capital))} para atingir o capital de giro mínimo recomendado.</div>', unsafe_allow_html=True)

    with col_h2:
        st.markdown("#### 🛡️ Reserva de Emergência")
        st.markdown(f"""
        <div class="kcard">
          <div class="kcard-title">{brl(reserva_sugerida)}</div>
          <div class="kcard-sub">Sugestão: {pct_reserva} meses de custos fixos guardados para imprevistos.</div>
        </div>
        """, unsafe_allow_html=True)
        if lucro_real >= reserva_sugerida:
            st.markdown(f'<div class="fin-ok">✅ Reserva de emergência coberta pelo lucro acumulado.</div>', unsafe_allow_html=True)
        else:
            falta = reserva_sugerida - lucro_real
            st.markdown(f'<div class="fin-alerta">⚠️ Faltam {brl(falta)} para a reserva de emergência ideal.</div>', unsafe_allow_html=True)

    with col_h3:
        st.markdown("#### 🎯 Teto de Gastos")
        st.markdown(f"""
        <div class="kcard">
          <div class="kcard-title">{brl(teto_gasto_mens)}</div>
          <div class="kcard-sub">Para manter margem mínima de {int(margem_min*100)}%, seus gastos totais não devem ultrapassar este valor.</div>
        </div>
        """, unsafe_allow_html=True)
        if gastos_pagos <= teto_gasto_mens:
            st.markdown(f'<div class="fin-ok">✅ Gastos dentro do limite. Sobra {brl(teto_gasto_mens - gastos_pagos)} de margem.</div>', unsafe_allow_html=True)
        else:
            excess = gastos_pagos - teto_gasto_mens
            st.markdown(f'<div class="fin-danger">🚨 Gastos {brl(excess)} acima do teto! Margem comprometida.</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    f_dash, f_gastos, f_pedidos, f_relat = st.tabs([
        "📊 Dashboard",
        "📝 Lançar Gastos",
        "💳 Pagamentos por Pedido",
        "📋 Relatório Mensal",
    ])

    with f_dash:
        st.markdown("#### 📊 Visão Financeira Geral")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("**📥 Receitas por Status**")
            rec_rec = receita_total
            rec_prev = receita_prevista
            rec_pendente = float(df_enc_fin[df_enc_fin["etapa"] < 7]["valor_total"].sum() or 0) - float(df_enc_fin[df_enc_fin["etapa"] < 7]["valor_recebido"].sum() or 0)
            df_rec_chart = pd.DataFrame({
                "Categoria": ["Recebido", "Previsto (em andamento)", "A receber (saldo)"],
                "Valor": [rec_rec, rec_prev, rec_pendente],
            })
            st.bar_chart(df_rec_chart.set_index("Categoria"))

        with col_d2:
            st.markdown("**📤 Gastos por Categoria**")
            if not df_g_fin.empty:
                cat_group = df_g_fin.groupby("categoria")["valor"].sum().reset_index()
                cat_group.columns = ["Categoria","Valor"]
                st.bar_chart(cat_group.set_index("Categoria"))
            else:
                st.info("Nenhum gasto lançado.")

        st.markdown("---")
        st.markdown("**🔄 Fluxo de Caixa – Pedidos Ativos**")
        pedidos_ativos = df_enc_fin[df_enc_fin["etapa"] < 7].copy()
        if pedidos_ativos.empty:
            st.info("Nenhum pedido ativo.")
        else:
            pedidos_ativos["Saldo a Receber"] = pedidos_ativos["valor_total"].astype(float) - pedidos_ativos["valor_recebido"].astype(float)
            pedidos_ativos["Entrega"] = pedidos_ativos["data_entrega"].apply(formatar_data_br)
            df_fluxo = pedidos_ativos[["cliente","peca","valor_total","valor_recebido","Saldo a Receber","Entrega"]].copy()
            df_fluxo.columns = ["Cliente","Peça","Total","Recebido","A Receber","Entrega Prevista"]
            df_fluxo["Total"]     = df_fluxo["Total"].apply(lambda x: brl(float(x)))
            df_fluxo["Recebido"]  = df_fluxo["Recebido"].apply(lambda x: brl(float(x)))
            df_fluxo["A Receber"] = df_fluxo["A Receber"].apply(lambda x: brl(float(x)))
            st.dataframe(df_fluxo, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("**📆 Contas a Pagar (em aberto)**")
        df_cp = df_g_fin[df_g_fin["pago"] == 0].copy()
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
                g_data = c4.date_input("Data", date.today())

                c5, c6 = st.columns(2)
                g_pago  = c5.checkbox("Já foi pago?", value=True)
                g_recor = c6.checkbox("Gasto recorrente (mensal)?")

                with get_conn() as conn:
                    enc_opts = pd.read_sql_query(
                        "SELECT rowid, cliente, peca FROM encomendas WHERE cancelado=0 AND etapa<7 ORDER BY rowid DESC", conn)
                enc_list = ["— Nenhum (custo fixo/geral) —"] + [
                    f"#{row['rowid']} – {row['cliente']}: {row['peca']}"
                    for _, row in enc_opts.iterrows()
                ]
                g_enc = st.selectbox("Vincular a pedido? (opcional)", enc_list)
                g_enc_id = None
                if g_enc != "— Nenhum (custo fixo/geral) —":
                    g_enc_id = int(g_enc.split("–")[0].replace("#","").strip())

                if st.form_submit_button("💾 Lançar Gasto", use_container_width=True, type="primary"):
                    if g_desc.strip() and g_val > 0:
                        with get_conn() as conn:
                            conn.execute(
                                "INSERT INTO gastos (encomenda_id, descricao, valor, data, categoria, pago, recorrente) VALUES (?,?,?,?,?,?,?)",
                                (g_enc_id, g_desc.strip(), g_val, g_data.isoformat(),
                                 g_cat, 1 if g_pago else 0, 1 if g_recor else 0),
                            )
                            conn.commit()
                        st.success("✅ Gasto lançado!")
                        st.rerun()
                    else:
                        st.error("Preencha descrição e valor.")

        with col_g2:
            st.markdown("**📊 Resumo de Gastos por Categoria**")
            if not df_g_fin.empty:
                df_cat_sum = df_g_fin.groupby("categoria")["valor"].sum().reset_index()
                df_cat_sum.columns = ["Categoria","Total"]
                df_cat_sum = df_cat_sum.sort_values("Total", ascending=False)
                df_cat_sum["Total"] = df_cat_sum["Total"].apply(lambda x: brl(float(x)))
                st.dataframe(df_cat_sum, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum gasto registrado.")

        st.markdown("---")
        st.markdown("#### 📋 Todos os Gastos")
        if df_g_fin.empty:
            st.info("Nenhum gasto registrado.")
        else:
            for _, g in df_g_fin.sort_values("data", ascending=False).iterrows():
                status_g = "✅ Pago" if g["pago"] else "⏳ Em aberto"
                badge_g  = "badge-green" if g["pago"] else "badge-amber"
                col_gi, col_gb = st.columns([5, 1])
                col_gi.markdown(f"""
                <div class="kcard">
                  <div class="kcard-title">{g['descricao']} — <b>{brl(float(g['valor']))}</b></div>
                  <div class="kcard-sub">
                    📂 {g['categoria']} &nbsp;|&nbsp; 📅 {formatar_data_br(g['data'])}
                    &nbsp;<span class="badge {badge_g}">{status_g}</span>
                    {"&nbsp;<span class='badge badge-blue'>🔁 Recorrente</span>" if g.get('recorrente') else ""}
                  </div>
                </div>""", unsafe_allow_html=True)
                with col_gb:
                    st.write("")
                    if not g["pago"]:
                        if st.button("💳 Quitar", key=f"qt_{g['rowid']}"):
                            with get_conn() as conn:
                                conn.execute("UPDATE gastos SET pago=1 WHERE rowid=?", (g["rowid"],))
                                conn.commit()
                            st.rerun()
                    else:
                        if st.button("🗑️", key=f"del_g_{g['rowid']}", help="Remover gasto"):
                            with get_conn() as conn:
                                conn.execute("DELETE FROM gastos WHERE rowid=?", (g["rowid"],))
                                conn.commit()
                            st.rerun()

    with f_pedidos:
        st.markdown("#### 💳 Gestão de Pagamentos por Pedido")

        if df_enc_fin.empty:
            st.info("Nenhum pedido cadastrado.")
        else:
            for _, enc in df_enc_fin.sort_values("rowid", ascending=False).iterrows():
                v_total_e  = float(enc.get("valor_total", 0) or 0)
                v_recebido = float(enc.get("valor_recebido", 0) or 0)
                v_restante = v_total_e - v_recebido

                gasto_enc  = float(df_g_fin[df_g_fin["encomenda_id"] == enc["rowid"]]["valor"].sum() or 0)
                lucro_enc  = v_recebido - gasto_enc
                margem_enc = lucro_enc / v_recebido * 100 if v_recebido > 0 else 0
                margem_min_val = float(cfg_get("margem_minima_pct") or 30)

                with st.expander(
                    f"👗 {enc['cliente']} – {enc['peca']}  |  "
                    f"Recebido: {brl(v_recebido)} / {brl(v_total_e)}  |  "
                    f"Margem: {margem_enc:.0f}%"
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
                        st.markdown("**Registrar recebimento:**")
                        col_rec1, col_rec2, col_rec3 = st.columns([2, 2, 1])
                        novo_val = col_rec1.number_input(
                            "Valor recebido (R$)",
                            min_value=0.01, max_value=float(v_restante + 0.01),
                            value=float(v_restante), step=10.0, format="%.2f",
                            key=f"rec_val_{enc['rowid']}",
                        )
                        col_rec2.metric("Saldo após:", brl(v_restante - novo_val))
                        if col_rec3.button("✅ Confirmar", key=f"rec_btn_{enc['rowid']}"):
                            with get_conn() as conn:
                                conn.execute(
                                    "UPDATE encomendas SET valor_recebido = valor_recebido + ? WHERE rowid=?",
                                    (novo_val, enc["rowid"]),
                                )
                                conn.commit()
                            st.success(f"✅ {brl(novo_val)} registrado!")
                            st.rerun()
                    else:
                        st.markdown('<div class="fin-ok">✅ Pedido totalmente pago.</div>', unsafe_allow_html=True)

                    if v_restante > 0.01:
                        if st.button(f"💰 Quitar saldo total ({brl(v_restante)})", key=f"quit_total_{enc['rowid']}"):
                            with get_conn() as conn:
                                conn.execute(
                                    "UPDATE encomendas SET valor_recebido=valor_total WHERE rowid=?",
                                    (enc["rowid"],),
                                )
                                conn.commit()
                            st.rerun()

    with f_relat:
        st.markdown("#### 📋 Relatório Financeiro Mensal")

        col_rm1, col_rm2 = st.columns(2)
        mes_sel_fin = col_rm1.selectbox(
            "Mês", list(range(1,13)),
            format_func=lambda x: MESES_PT[x-1],
            index=hoje_dt.month - 1, key="mes_rel_fin",
        )
        ano_sel_fin = col_rm2.number_input("Ano", min_value=2020, max_value=2030, value=hoje_dt.year)

        mes_str = f"{ano_sel_fin}-{mes_sel_fin:02d}"
        with get_conn() as conn:
            df_enc_mes = pd.read_sql_query(
                "SELECT * FROM encomendas WHERE data_entrega LIKE ? AND cancelado=0",
                conn, params=(f"{mes_str}%",),
            )
            df_g_mes = pd.read_sql_query(
                "SELECT * FROM gastos WHERE data LIKE ?",
                conn, params=(f"{mes_str}%",),
            )

        rec_mes   = float(df_enc_mes["valor_recebido"].sum() or 0)
        gasto_mes = float(df_g_mes["valor"].sum() or 0)
        lucro_mes = rec_mes - gasto_mes
        margem_mes = lucro_mes / rec_mes * 100 if rec_mes > 0 else 0

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        col_r1.metric("Receita do Mês",  brl(rec_mes))
        col_r2.metric("Gastos do Mês",   brl(gasto_mes))
        col_r3.metric("Lucro Líquido",   brl(lucro_mes))
        col_r4.metric("Margem",          f"{margem_mes:.1f}%")

        meta_fat_f = float(cfg_get("meta_faturamento") or 5000)
        if rec_mes >= meta_fat_f:
            st.markdown(f'<div class="fin-ok">🏆 Meta de faturamento de {brl(meta_fat_f)} atingida!</div>', unsafe_allow_html=True)
        else:
            falta_meta = meta_fat_f - rec_mes
            st.markdown(f'<div class="fin-alerta">📌 Faltam {brl(falta_meta)} para a meta de {brl(meta_fat_f)} em {MESES_PT[mes_sel_fin-1]}.</div>', unsafe_allow_html=True)

        if margem_mes > 0 and margem_mes < float(cfg_get("margem_minima_pct") or 30):
            st.markdown(f'<div class="fin-danger">⚠️ Margem do mês ({margem_mes:.1f}%) abaixo do mínimo recomendado ({cfg_get("margem_minima_pct")}%).</div>', unsafe_allow_html=True)

        st.markdown("---")
        col_rt1, col_rt2 = st.columns(2)

        with col_rt1:
            st.markdown("**Pedidos do mês**")
            if df_enc_mes.empty:
                st.info("Nenhum pedido com entrega neste mês.")
            else:
                df_enc_show = df_enc_mes[["cliente","peca","valor_recebido","valor_total"]].copy()
                df_enc_show.columns = ["Cliente","Peça","Recebido","Total"]
                df_enc_show["Recebido"] = df_enc_show["Recebido"].apply(lambda x: brl(float(x)))
                df_enc_show["Total"]    = df_enc_show["Total"].apply(lambda x: brl(float(x)))
                st.dataframe(df_enc_show, use_container_width=True, hide_index=True)

        with col_rt2:
            st.markdown("**Gastos do mês**")
            if df_g_mes.empty:
                st.info("Nenhum gasto registrado neste mês.")
            else:
                df_g_show = df_g_mes[["descricao","categoria","valor","pago"]].copy()
                df_g_show.columns = ["Descrição","Categoria","Valor","Pago?"]
                df_g_show["Valor"] = df_g_show["Valor"].apply(lambda x: brl(float(x)))
                df_g_show["Pago?"] = df_g_show["Pago?"].apply(lambda x: "✅" if x else "⏳")
                st.dataframe(df_g_show, use_container_width=True, hide_index=True)

        st.markdown("---")
        if st.button("📥 Exportar Relatório Mensal (Excel)", use_container_width=True):
            buf_xl = io.BytesIO()
            wb     = xlsxwriter.Workbook(buf_xl)

            fmt_h   = wb.add_format({"bold":True,"bg_color":"#3d1f10","font_color":"white","border":1})
            fmt_brl = wb.add_format({"num_format":"R$ #,##0.00","border":1})
            fmt_n   = wb.add_format({"border":1})

            ws1 = wb.add_worksheet("Receitas")
            headers1 = ["Cliente","Peça","Total","Recebido","A Receber","Entrega"]
            for ci, h in enumerate(headers1): ws1.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_enc_mes.iterrows(), start=1):
                ws1.write(ri, 0, row["cliente"], fmt_n)
                ws1.write(ri, 1, row["peca"], fmt_n)
                ws1.write(ri, 2, float(row.get("valor_total",0) or 0), fmt_brl)
                ws1.write(ri, 3, float(row.get("valor_recebido",0) or 0), fmt_brl)
                ws1.write(ri, 4, float(row.get("valor_total",0) or 0) - float(row.get("valor_recebido",0) or 0), fmt_brl)
                ws1.write(ri, 5, str(row.get("data_entrega","")), fmt_n)

            ws2 = wb.add_worksheet("Gastos")
            headers2 = ["Data","Descrição","Categoria","Valor","Pago?"]
            for ci, h in enumerate(headers2): ws2.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_g_mes.iterrows(), start=1):
                ws2.write(ri, 0, str(row.get("data","")), fmt_n)
                ws2.write(ri, 1, row["descricao"], fmt_n)
                ws2.write(ri, 2, row["categoria"], fmt_n)
                ws2.write(ri, 3, float(row.get("valor",0) or 0), fmt_brl)
                ws2.write(ri, 4, "Sim" if row.get("pago") else "Não", fmt_n)

            ws3 = wb.add_worksheet("Resumo")
            fmt_titulo = wb.add_format({"bold":True,"font_size":14,"font_color":"#3d1f10"})
            fmt_key    = wb.add_format({"bold":True})
            ws3.write(0, 0, f"Relatório – {MESES_PT[mes_sel_fin-1]} {ano_sel_fin}", fmt_titulo)
            resumo = [
                ("Receita Total", rec_mes),
                ("Gastos Totais", gasto_mes),
                ("Lucro Líquido", lucro_mes),
                (f"Margem ({margem_mes:.1f}%)", margem_mes / 100 if rec_mes > 0 else 0),
            ]
            for ri, (k, v) in enumerate(resumo, start=2):
                ws3.write(ri, 0, k, fmt_key)
                if ri < 5:
                    ws3.write(ri, 1, v, fmt_brl)
                else:
                    ws3.write(ri, 1, v, wb.add_format({"num_format":"0.00%","border":1}))

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
            cfg_meta_fat = st.number_input(
                "Meta de Faturamento Mensal (R$)",
                min_value=0.0, value=float(cfg_get("meta_faturamento") or 5000),
                step=500.0, format="%.2f",
            )
            cfg_meta_ped = st.number_input(
                "Meta de Pedidos por Mês", min_value=1, value=int(cfg_get("meta_pedidos_mes") or 8))
            cfg_margem = st.slider(
                "Margem Mínima Desejada (%)", min_value=10, max_value=80,
                value=int(cfg_get("margem_minima_pct") or 30))
            cfg_reserva = st.slider(
                "Meses de Reserva de Emergência", min_value=1, max_value=12,
                value=int(cfg_get("reserva_emergencia_meses") or 3))
            cfg_capital = st.slider(
                "Capital de Giro (% da Receita)", min_value=5, max_value=50,
                value=int(cfg_get("capital_giro_pct") or 20))
            if st.form_submit_button("💾 Salvar Parâmetros"):
                cfg_set("meta_faturamento",         str(cfg_meta_fat))
                cfg_set("meta_pedidos_mes",         str(cfg_meta_ped))
                cfg_set("margem_minima_pct",        str(cfg_margem))
                cfg_set("reserva_emergencia_meses", str(cfg_reserva))
                cfg_set("capital_giro_pct",         str(cfg_capital))
                st.success("✅ Parâmetros salvos! As sugestões financeiras foram atualizadas.")
                st.rerun()

    st.markdown("---")
    st.markdown("#### ℹ️ Explicação dos Parâmetros Financeiros")
    st.markdown("""
    | Parâmetro | O que é | Referência |
    |---|---|---|
    | **Meta de Faturamento** | Quanto você quer receber por mês | Definida por você |
    | **Margem Mínima** | % do preço que deve sobrar após os custos | 30-40% é saudável para costura |
    | **Capital de Giro** | Dinheiro disponível para manter o negócio rodando | 15-25% da receita |
    | **Reserva de Emergência** | Meses de custos guardados para imprevistos | Mínimo 3 meses recomendado |
    | **Teto de Gastos** | Calculado automaticamente pela margem mínima | Gerado pelo sistema |
    """)

    st.markdown("---")

    col_back1, col_back2 = st.columns(2)
    with col_back1:
        st.markdown("#### 💾 Backup do Banco de Dados")
        if st.button("📥 Gerar Backup", use_container_width=True):
            with open(DB_PATH, "rb") as f:
                db_bytes = f.read()
            st.download_button(
                "⬇️ Baixar lila_closet.db",
                data=db_bytes,
                file_name=f"backup_lila_{date.today().isoformat()}.db",
                mime="application/octet-stream",
                use_container_width=True,
            )

    with col_back2:
        st.markdown("#### 🗑️ Limpeza (Cuidado!)")
        if st.checkbox("Confirmar exclusão de todos os gastos pagos"):
            if st.button("🗑️ Excluir gastos pagos (arquivar)", use_container_width=True):
                with get_conn() as conn:
                    conn.execute("DELETE FROM gastos WHERE pago=1")
                    conn.commit()
                st.success("Gastos pagos removidos.")
                st.rerun()

    # ── Zona de perigo: deletar pedido ───────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔐 Exclusão Permanente de Pedido")
    st.markdown(
        "<div class='danger-zone'>"
        "<b>⚠️ ATENÇÃO:</b> Esta operação apaga o pedido, todas as tarefas de agenda e todos "
        "os gastos vinculados de forma <b>permanente e irreversível</b>. "
        "É necessária a senha de administrador para confirmar."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    with get_conn() as conn:
        df_todos_pedidos = pd.read_sql_query(
            "SELECT rowid, cliente, peca, cancelado, etapa FROM encomendas ORDER BY rowid DESC", conn)

    if df_todos_pedidos.empty:
        st.info("Nenhum pedido cadastrado.")
    else:
        opcoes_pedidos = {
            f"#{row['rowid']} – {row['cliente']} | {row['peca']}"
            f" {'[CANCELADO]' if row['cancelado'] else ''}"
            f" [Etapa {row['etapa']}]": row["rowid"]
            for _, row in df_todos_pedidos.iterrows()
        }

        pedido_sel_label = st.selectbox(
            "Selecione o pedido para DELETAR permanentemente:",
            list(opcoes_pedidos.keys()), key="del_pedido_sel",
        )
        pedido_sel_id = opcoes_pedidos[pedido_sel_label]

        row_sel = df_todos_pedidos[df_todos_pedidos["rowid"] == pedido_sel_id].iloc[0]
        with get_conn() as conn:
            n_tarefas = conn.execute("SELECT COUNT(*) FROM cronograma WHERE encomenda_id=?", (pedido_sel_id,)).fetchone()[0]
            n_gastos  = conn.execute("SELECT COUNT(*) FROM gastos WHERE encomenda_id=?",    (pedido_sel_id,)).fetchone()[0]

        st.markdown(
            f"**Pedido selecionado:** #{pedido_sel_id} — {row_sel['cliente']} | {row_sel['peca']}  \n"
            f"Serão removidos também: **{n_tarefas} tarefa(s)** na agenda e **{n_gastos} gasto(s)** vinculado(s)."
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
                deletar_pedido_completo(int(pedido_sel_id))
                st.success(
                    f"✅ Pedido #{pedido_sel_id} ({row_sel['cliente']} – {row_sel['peca']}) "
                    f"e todos os registros vinculados foram removidos permanentemente."
                )
                st.rerun()
            elif senha_digitada == "":
                st.error("❌ Digite a senha de administrador para confirmar a exclusão.")
            else:
                st.error("❌ Senha incorreta. Exclusão não realizada.")

st.caption("v8.1.0 | Lila Closet Atelier | Sistema de Gestão Completo")
