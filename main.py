"""
main.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
ORQUESTRADOR do sistema. Monta o CSS global, a NAVEGAÇÃO LATERAL (sidebar,
estilo "sistema de verdade" — igual ao Painel KingStar) e delega cada área
para o seu BLOCO correspondente, todos dentro deste mesmo arquivo:

    BLOCO NOVA ENCOMENDA    → formulário fixo de cadastro de encomenda
    BLOCO AGENDA            → calendário mensal + agenda de trabalho + vida
                              pessoal (campo, peso) + alerta de entregas
                              urgentes
    BLOCO CONTRATOS         → lista de encomendas + painel de detalhe do
                              contrato ao lado (ver, editar, baixar PDF, GOV.BR)
    BLOCO MEDIDAS           → ficha de medidas das clientes (com busca)
    BLOCO GERENCIAR PEDIDOS → gerenciamento geral dos pedidos (cards + popup)
    BLOCO FINANCEIRO        → agora em modulos/mod_financeiro.py
    BLOCO CONFIGURAÇÕES     → dados da empresa, metas, alerta de entrega,
                              exclusões permanentes

  Ordem da sidebar (grupo "Operacional"):
      Nova Encomenda → Agenda → Contratos → Medidas → Gerenciar Pedidos
  Grupo "Gestão": Financeiro
  Grupo "Administração": Configurações

Histórico de versões (changelog):

  [v10] Estrutura original em abas no topo (Encomendas / Agenda /
        Financeiro / Configurações), formulário de nova encomenda sempre
        visível (evita perda de dados ao trocar de app no celular).

  [v11] NAVEGAÇÃO LATERAL (v11.0): as abas do topo viraram itens de uma
        sidebar de verdade (mesmo padrão visual do Painel KingStar:
        sidebar escura, botão dourado quando a seção está ativa). O
        cabeçalho (logo + nome) e os KPIs do topo continuam sempre
        visíveis, sejá qual for a seção selecionada.

  [v11] BLOCO CONTRATOS (novo): antes, "ver o contrato" só existia dentro
        do popup de um pedido (Gerenciar Pedidos → clique no card). Agora
        existe uma seção própria na sidebar — "📄 Contratos" — com uma
        lista de encomendas à esquerda (com busca) e, ao clicar no nome,
        o contrato completo abre ao lado: dados do pedido, edição de
        datas/valores, medidas da cliente, botão de baixar PDF e botão de
        assinatura via GOV.BR. Reaproveita 100% da função `_conteudo_pedido`
        já existente (mesma lógica usada nos popups de Encomendas/Agenda),
        então não há duplicação de regras de negócio — só um novo "container"
        para ela.

  [v11.1] O que antes era um único bloco "Encomendas" (com Nova Encomenda no
        topo + abas internas "Medidas & Clientes" e "Gerenciar Pedidos") virou
        TRÊS itens próprios na sidebar: 🆕 Nova Encomenda, 📏 Medidas e
        📋 Gerenciar Pedidos — cada um com sua função `renderizar_*` dedicada,
        sem abas internas escondendo conteúdo. Ordem final da sidebar:
        Nova Encomenda → Agenda → Contratos → Medidas → Gerenciar Pedidos →
        Financeiro → Configurações.

  [v11.2] CABEÇALHO FIXO: o cabeçalho (logo/nome) e os 3 KPIs do topo agora
        ficam FIXOS (position: sticky) no topo da área principal enquanto o
        conteúdo de cada seção rola por baixo — mais compactos e discretos.
        O logo foi removido da barra lateral (sidebar), que ficou mais limpa,
        mantendo apenas o título/subtítulo em texto.

  [v11.2] MODULARIZAÇÃO: o BLOCO FINANCEIRO foi extraído para
        `modulos/mod_financeiro.py` (primeiro módulo da série de refatoração
        que vai, aos poucos, reduzir este arquivo main.py). Os helpers
        (formatação de datas/moeda, fuso de Brasília, constantes de mês)
        também foram extraídos para `modulos/utils.py`, para que possam ser
        reaproveitados tanto pelo main.py quanto pelos novos módulos, sem
        import circular.

  [v12] SUPER AGENDA — regras novas de negócio, apoiadas por um novo módulo
        `modulos/regras_agenda.py` (funções puras de validação, sem Firestore
        nem Streamlit, reaproveitadas na criação E na edição de pedido):

        1) Removido o campo "Data da Encomenda" de todo o sistema (formulário
           de criação, edição de pedido, cronograma automático). Não é mais
           coletado nem exibido em nenhum lugar. A "Data Medidas" é o
           pontapé inicial de todo o fluxo.

        2) ALERTA DE ENTREGA URGENTE: pedidos cuja Data de Entrega esteja
           a N dias (configurável em ⚙️ Configurações, padrão 7, mas o
           Wendley pode ajustar para 30 etc.) aparecem em destaque vermelho
           no topo da Agenda, com prioridade máxima — visualmente diferente
           do aviso de "atrasado". Regra mantida intacta.

        3) Regra de exclusividade da Data da Confecção: o sistema nunca
           permite dois clientes com confecção na mesma data. Ao escolher a
           Data da Confecção (criação e edição), um mini-calendário do mês
           mostra 🔴 nos dias já ocupados e 🟡 nos dias já lotados de prova
           (ver regra 4), que por isso também ficam bloqueados para confecção.

        4) Regra de limite de provas: no máximo 3 provas (1ª ou 2ª, somando
           todos os pedidos ativos) no mesmo dia. Um dia com mais de 3
           provas marcadas fica automaticamente bloqueado para receber Data
           da Confecção.

        5) Campo "Cliente" agora é editável dentro do formulário de edição de
           pedido (usado por Gerenciar Pedidos, Contratos e Agenda), sem
           precisar apagar e recriar a encomenda.

  [v13] MEDIDAS ENXUTO: removida a listagem "Clientes Cadastradas" da tela
        de Medidas — agora a tela mostra direto a Ficha de Medidas, com uma
        barra de busca por nome para localizar a cliente rapidamente.

  [v13] GERENCIAR PEDIDOS: removido o botão "➕ Nova Encomenda" (a criação
        já existe em outras telas). Filtro padrão passou a ser
        "Em andamento" (antes era "Todos"). A busca ganhou mais destaque
        (linha própria, full width) e passou a buscar por cliente OU peça.
        A listagem agora é ordenada pela Data de Entrega mais próxima
        primeiro (pedidos sem data de entrega vão para o final).
"""

import streamlit as st
import pandas as pd
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
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.utils import ImageReader

# ── Helpers compartilhados (fuso de Brasília, formatação, constantes) ────────
from modulos.utils import (
    MESES_PT,
    agora_br, hoje_brasilia, converter_para_data,
    formatar_data_br, formatar_data_hora_br, brl,
)

# ── Módulos extraídos ─────────────────────────────────────────────────────────
from modulos.mod_financeiro import renderizar_financeiro
from modulos.regras_agenda import (
    validar_data_confeccao,
    dias_confeccao_ocupados, dias_com_provas_lotadas,
    pedidos_com_entrega_proxima, LIMITE_PROVAS_PARA_CONFECCAO,
)

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
    initial_sidebar_state="expanded",
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

/* ── Sidebar (navegação lateral — estilo "sistema de verdade") ── */
[data-testid="stSidebar"] {
  background: #17110b !important;
  border-right: 1px solid #2a2015 !important;
}
[data-testid="stSidebar"] * { color: #d9cdbb !important; }
[data-testid="stSidebar"] hr { border-color: #33281a !important; }

[data-testid="stSidebar"] .stButton > button {
  border-radius: 10px !important;
  font-weight: 600 !important;
  width: 100%;
  text-align: left !important;
  justify-content: flex-start !important;
  padding: 10px 14px !important;
  margin-bottom: 4px;
  transition: background .15s ease;
}
[data-testid="stSidebar"] button[kind="secondary"] {
  background: #241a10 !important; color: #d9cdbb !important;
  border: 1px solid #33281a !important;
}
[data-testid="stSidebar"] button[kind="secondary"]:hover {
  background: #332616 !important; color: #f5e6d3 !important;
  border-color: #6b3a22 !important;
}
[data-testid="stSidebar"] button[kind="primary"] {
  background: linear-gradient(135deg, #c9a227, #8a6200) !important;
  color: #1a0f0a !important; border: none !important;
  box-shadow: 0 3px 10px rgba(0,0,0,0.35);
}
.sb-titulo { font-family:'Playfair Display', serif; font-size:1.15rem; font-weight:700;
  color:#f5e6d3 !important; margin-top:6px; }
.sb-subtitulo { font-size:0.72rem; letter-spacing:1.5px; text-transform:uppercase;
  color:#a98c3d !important; margin-bottom:14px; }
.sb-secao-label { font-size:0.68rem; font-weight:700; letter-spacing:1.2px;
  text-transform:uppercase; color:#8a7355 !important; margin:14px 0 6px 4px; }

/* ── Topo fixo (cabeçalho + KPIs) — fica "grudado" no topo enquanto o
      conteúdo de cada seção rola por baixo ── */
div[class*="st-key-topo_fixo"] {
  position: sticky;
  top: 0;
  z-index: 999;
  background: #f4f1ee;
  padding-top: 0.4rem;
  padding-bottom: 0.4rem;
  margin-bottom: 0.4rem;
}

/* ── Hero header (compacto) ── */
.hero-header {
  background: linear-gradient(135deg, #1a0f0a 0%, #3d1f10 50%, #6b3a22 100%);
  border-radius: 12px; padding: 0.6rem 1.2rem;
  margin-bottom: 0.6rem; display: flex; align-items: center; gap: 0.9rem;
  box-shadow: 0 4px 16px rgba(0,0,0,0.18);
}
.hero-logo { height: 38px; width: auto; border-radius: 7px; object-fit: contain; }
.hero-icon { font-size: 1.7rem; }
.hero-title {
  font-family: 'Playfair Display', serif; font-size: 1.15rem;
  font-weight: 700; color: #f5e6d3; margin: 0; line-height: 1.15;
}
.hero-subtitle { font-size: 0.62rem; color: #c9a882; letter-spacing: 1.2px;
  text-transform: uppercase; margin-top: 2px; }

/* ── Abas internas (dentro de cada bloco) ── */
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

/* ── Alerta urgente de entrega (prioridade máxima) ── */
.entrega-urgente-zone {
  background: #fff0f0; border: 2px solid #c0392b; border-radius: 12px;
  padding: 1rem 1.3rem; margin-bottom: 0.9rem;
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

/* ── Botões (área principal) ── */
[data-testid="stMain"] [data-testid="stButton"] > button { border-radius: 10px !important; font-weight: 500 !important; }
[data-testid="stMain"] [data-testid="stButton"] > button[kind="primary"] {
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

/* ── KPI Cards (topo do sistema — compactos) ── */
.kpi-card {
  border-radius: 12px; padding: 10px 14px; margin-bottom: 0;
  box-shadow: 0 3px 12px rgba(61,31,16,0.10);
  transition: transform .15s, box-shadow .15s;
}
.kpi-card:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(61,31,16,0.16); }
.kpi-label {
  font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.5px; opacity: 0.88;
}
.kpi-value { font-size: 1.3rem; font-weight: 800; line-height: 1.1; margin-top: 2px; }
.kpi-sub { font-size: 0.62rem; opacity: 0.85; margin-top: 3px; }
.kpi-bar { background: rgba(0,0,0,0.08); border-radius: 4px; height: 5px; margin: 5px 0 1px; }
.kpi-bar > div {
  background: linear-gradient(90deg,#c9a227,#6b3a22);
  height: 5px; border-radius: 4px; transition: width .3s ease;
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

/* ══════════════════════════════════════════════════════════════
   BLOCO CONTRATOS — lista de encomendas (esquerda) + painel de
   detalhe do contrato (direita). Mesmo espírito do painel de
   Tickets do KingStar: coluna de lista rolando por dentro, sem
   empurrar a página toda, e cards clicáveis na lista.
   ══════════════════════════════════════════════════════════════ */
div[class*="st-key-ct_paineis"] div[data-testid="stColumn"]:first-child {
  max-height: calc(100vh - 300px);
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 8px;
}
div[class*="st-key-ct_paineis"] div[data-testid="stColumn"]:first-child::-webkit-scrollbar { width: 8px; }
div[class*="st-key-ct_paineis"] div[data-testid="stColumn"]:first-child::-webkit-scrollbar-track { background: transparent; }
div[class*="st-key-ct_paineis"] div[data-testid="stColumn"]:first-child::-webkit-scrollbar-thumb {
  background: #D8CBA0; border-radius: 4px;
}
div[class*="st-key-ctcard_"] button {
  text-align: left !important; justify-content: flex-start !important;
  border-radius: 10px !important; font-weight: 600 !important;
  font-size: 0.86rem !important; padding: 10px 12px !important;
  margin-bottom: 2px !important;
}
.ct-detalhe-vazio {
  background: #fdf6ee; border: 1.5px dashed #ecdfc9; border-radius: 14px;
  padding: 3rem 1.5rem; text-align: center; color: #8b7355;
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
# HELPERS (específicos do main.py — PDF de contrato e afins)
# ══════════════════════════════════════════════════════════════════════════════
def get_logo_base64() -> str | None:
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


# ══════════════════════════════════════════════════════════════════════════════
# MINI-CALENDÁRIO DE OCUPAÇÃO — Data da Confecção
# ══════════════════════════════════════════════════════════════════════════════
def _render_ocupacao_confeccao(df_enc: pd.DataFrame, ano: int, mes: int, excluir_id: str | None = None):
    """
    Mostra um mini-calendário do mês/ano informados, com legenda visual:
      🔴 dia já reservado para confecção de outro cliente (bloqueado)
      🟡 dia com mais de LIMITE_PROVAS_PARA_CONFECCAO provas marcadas
         (bloqueado para confecção, mas SEM limite de provas em si)
    Puramente informativo: a validação de verdade acontece ao salvar,
    usando as mesmas funções de `modulos/regras_agenda.py`.
    """
    ocupados = dias_confeccao_ocupados(df_enc, excluir_id)
    lotados_prova = dias_com_provas_lotadas(df_enc, excluir_id)

    st.caption(
        f"📌 Ocupação de **{MESES_PT[mes-1]}/{ano}** para a Data da Confecção — "
        f"🔴 já reservado por outro cliente &nbsp;·&nbsp; "
        f"🟡 mais de {LIMITE_PROVAS_PARA_CONFECCAO} provas nesse dia (bloqueado p/ confecção)"
    )
    cols_h = st.columns(7)
    for i, d in enumerate(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]):
        cols_h[i].markdown(
            f"<center style='font-size:0.65rem;color:#8b7355'><b>{d}</b></center>",
            unsafe_allow_html=True,
        )
    for semana in calendar.monthcalendar(ano, mes):
        cols_s = st.columns(7)
        for i, dia in enumerate(semana):
            if dia == 0:
                cols_s[i].markdown("&nbsp;", unsafe_allow_html=True)
                continue
            dt_obj = date(ano, mes, dia)
            marca = ""
            if dt_obj in ocupados:
                marca = " 🔴"
            elif dt_obj in lotados_prova:
                marca = " 🟡"
            cols_s[i].markdown(
                f"<center style='font-size:0.74rem;color:#3d1f10'>{dia}{marca}</center>",
                unsafe_allow_html=True,
            )


def _render_ocupacao_confeccao_navegavel(
    df_enc: pd.DataFrame, key_prefix: str, data_referencia: date, excluir_id: str | None = None,
):
    """
    Mesmo mini-calendário de ocupação da Confecção, mas com botões de
    navegação (◀ Anterior / Próximo ▶) para folhear os meses seguintes —
    útil para checar a agenda antes de decidir a Data da Confecção.
    O mês navegado fica guardado em session_state, então a navegação não
    "some" a cada rerun; para voltar ao mês da data já escolhida no
    formulário, use o botão "📍 Ir para o mês da data escolhida".
    """
    state_key = f"{key_prefix}_mes_ref_conf"
    if state_key not in st.session_state:
        st.session_state[state_key] = data_referencia.replace(day=1)

    ref = st.session_state[state_key]

    nav1, nav_tit, nav2, nav3 = st.columns([1, 2, 1, 2.4])
    if nav1.button("◀", key=f"{key_prefix}_conf_prev", use_container_width=True):
        st.session_state[state_key] = (ref.replace(day=1) - timedelta(days=1)).replace(day=1)
        st.rerun()
    if nav2.button("▶", key=f"{key_prefix}_conf_next", use_container_width=True):
        st.session_state[state_key] = (ref.replace(day=28) + timedelta(days=4)).replace(day=1)
        st.rerun()
    if nav3.button("📍 Ir para o mês da data escolhida", key=f"{key_prefix}_conf_ir_data", use_container_width=True):
        st.session_state[state_key] = data_referencia.replace(day=1)
        st.rerun()

    ref = st.session_state[state_key]
    nav_tit.markdown(
        f"<center style='color:#6b3a22;font-weight:700;'>{MESES_PT[ref.month-1]}/{ref.year}</center>",
        unsafe_allow_html=True,
    )

    _render_ocupacao_confeccao(df_enc, ref.year, ref.month, excluir_id=excluir_id)


# ══════════════════════════════════════════════════════════════════════════════
# PDF — CONTRATO  (usado pelo BLOCO CONTRATOS e também na criação de encomendas)
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
# COMPONENTES COMPARTILHADOS — usados pelos blocos CONTRATOS, ENCOMENDAS e AGENDA
# ══════════════════════════════════════════════════════════════════════════════

# ── Popup: Nova Encomenda Rápida (a partir do calendário) ─────────────────────
@st.dialog("🛍️ Nova Encomenda Rápida", width="large")
def dialog_nova_encomenda(data_pre: date | None = None):
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

    d_visita_dlg = st.date_input(
        "📏 Data Medidas", value=d_base, key="dlg_visita", format="DD/MM/YYYY"
    )
    d_confeccao_dlg = st.date_input(
        "🪡 Data da Confecção", value=d_visita_dlg + timedelta(days=7),
        key="dlg_confeccao", format="DD/MM/YYYY"
    )
    _render_ocupacao_confeccao_navegavel(df_enc_all, key_prefix="dlg", data_referencia=d_confeccao_dlg)

    d_prova_dlg = st.date_input(
        "👗 Data da Prova", value=d_base + timedelta(days=25), key="dlg_prova", format="DD/MM/YYYY"
    )
    st.caption(
        f"ℹ️ Não há limite de provas por dia. Mas se um dia passar de "
        f"{LIMITE_PROVAS_PARA_CONFECCAO} provas, ele fica bloqueado para receber Confecção (veja 🟡 acima)."
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

        # ── Validação de agenda (exclusividade da Data da Confecção) ──
        df_check_dlg = encomendas_listar(cancelado=False)
        ok_conf, msg_conf = validar_data_confeccao(df_check_dlg, d_confeccao_dlg)
        if not ok_conf:
            st.error(msg_conf)
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


# ── Formulário fixo de Nova Encomenda (sem popup — usado no bloco ENCOMENDAS) ──
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

    d_visita_dlg = st.date_input(
        "📏 Data Medidas", value=d_base, key="ne_visita", format="DD/MM/YYYY"
    )
    d_confeccao_dlg = st.date_input(
        "🪡 Data da Confecção", value=d_visita_dlg + timedelta(days=7),
        key="ne_confeccao", format="DD/MM/YYYY"
    )
    _render_ocupacao_confeccao_navegavel(df_enc_all, key_prefix="ne", data_referencia=d_confeccao_dlg)

    d_prova_dlg = st.date_input(
        "👗 Data da Prova", value=d_base + timedelta(days=25), key="ne_prova", format="DD/MM/YYYY"
    )
    st.caption(
        f"ℹ️ Não há limite de provas por dia. Mas se um dia passar de "
        f"{LIMITE_PROVAS_PARA_CONFECCAO} provas, ele fica bloqueado para receber Confecção (veja 🟡 acima)."
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

        # ── Validação de agenda (exclusividade da Data da Confecção) ──
        df_check_ne = encomendas_listar(cancelado=False)
        ok_conf, msg_conf = validar_data_confeccao(df_check_ne, d_confeccao_dlg)
        if not ok_conf:
            st.error(msg_conf)
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


# ── Sincronização de lembretes (cronograma) com as datas do pedido ────────────
def _sincronizar_lembretes_pedido(
    enc_id: str, cliente: str, peca: str,
    d_visita: date, precisa_tecido: bool, d_tecido: date,
    d_confeccao: date, d_prova: date, tem_prova2: bool, d_prova2,
    d_entrega: date,
):
    """
    Após editar um pedido, sincroniza as tarefas do cronograma vinculadas a
    essa encomenda para refletir as novas datas no Calendário e na aba Trabalho.
    Somente tarefas ainda PENDENTES são sincronizadas; tarefas já concluídas
    são preservadas como histórico.
    """
    desc = f"{peca} ({cliente})"

    df_crono = cronograma_listar(tipo_agenda="Trabalho", concluida=False)
    if df_crono is None or df_crono.empty or "encomenda_id" not in df_crono.columns:
        df_crono = pd.DataFrame(columns=["rowid", "tarefa", "encomenda_id"])
    else:
        df_crono = df_crono[df_crono["encomenda_id"].astype(str) == str(enc_id)]

    especificacoes = [
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


def _calcular_etapa_maxima_por_datas(
    hoje: date, d_visita: date, precisa_tecido: bool, d_tecido: date,
    d_confeccao: date, d_prova: date, d_entrega: date,
) -> int:
    """
    Calcula, comparando com a data de hoje, até qual etapa da régua as datas
    do pedido já justificam. Nunca retorna 7 (Concluído) — essa etapa continua
    sendo sempre uma confirmação manual.
    """
    etapa = 1
    if hoje >= d_visita:
        etapa = 3 if precisa_tecido else 4
    if precisa_tecido and hoje >= d_tecido:
        etapa = 4
    if hoje >= d_confeccao:
        etapa = 5
    if hoje >= d_prova:
        etapa = 6
    return etapa


def _reverter_lembretes_por_etapa(enc_id: str, etapa_atual: int, precisa_tecido: bool):
    """
    Mantém o cronograma coerente com a etapa atual do pedido: se a régua
    "voltou", marca de volta como PENDENTE qualquer tarefa cuja conclusão
    representaria uma etapa mais avançada do que a etapa_atual.
    """
    df_todas = cronograma_listar(tipo_agenda="Trabalho")
    if df_todas is None or df_todas.empty or "encomenda_id" not in df_todas.columns:
        return
    df_todas = df_todas[df_todas["encomenda_id"].astype(str) == str(enc_id)]
    if df_todas.empty:
        return

    medidas_etapa = 3 if precisa_tecido else 4
    mapa_etapas = [
        ("📏 Medidas:",   medidas_etapa),
        ("🛍️ Tecido:",   4),
        ("🪡 Confecção:", 5),
        ("👗 Prova:",     6),
        ("🎁 Entrega:",   7),
    ]

    for prefixo, etapa_gerada in mapa_etapas:
        match = df_todas[df_todas["tarefa"].astype(str).str.startswith(prefixo)]
        if match.empty:
            continue
        linha = match.iloc[0]
        deve_estar_concluida = etapa_gerada <= etapa_atual
        concluida_atual = bool(int(linha.get("concluida", 0) or 0))
        if concluida_atual != deve_estar_concluida:
            cronograma_atualizar(str(linha["rowid"]), {"concluida": 1 if deve_estar_concluida else 0})


# ── Corpo completo de um pedido: régua, valores, contrato, edição ─────────────
def _conteudo_pedido(enc: dict, cancelado: bool):
    """
    Renderiza o conteúdo COMPLETO de um pedido: régua de etapas, valores,
    datas, seção de contrato (CPF/RG + baixar PDF + assinar via GOV.BR),
    medidas da cliente e formulário de edição (incluindo o nome da cliente,
    editável). É o mesmo "miolo" usado tanto dentro de um popup
    (Encomendas/Agenda) quanto dentro do painel de detalhe do BLOCO
    CONTRATOS — a única diferença é o container que o envolve por fora.
    """
    enc_atualizado = encomendas_buscar(str(enc["rowid"]))
    if enc_atualizado:
        enc = enc_atualizado
        cancelado = bool(int(enc.get("cancelado", 0) or 0))

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
        f"📏 Medidas: **{formatar_data_br(enc.get('data_visita',''))}** "
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

    # ── Mini-calendário de ocupação da Data da Confecção (informativo,
    #    com navegação de mês — fica fora do st.form abaixo de propósito,
    #    já que dentro de um st.form não é permitido usar st.button comum) ──
    mes_ref_conf = converter_para_data(enc.get("data_confeccao")) or hoje_brasilia()
    df_check_edicao = encomendas_listar(cancelado=False)
    _render_ocupacao_confeccao_navegavel(
        df_check_edicao, key_prefix=f"cp_{enc['rowid']}",
        data_referencia=mes_ref_conf, excluir_id=str(enc["rowid"]),
    )

    with st.form(f"edit_{enc['rowid']}"):
        ed_cliente = st.text_input("Cliente", value=str(enc.get("cliente") or ""), key=f"cliente_{enc['rowid']}")
        ed_peca = st.text_input("Peça", value=str(enc.get("peca") or ""))
        ed_desc = st.text_area("Descrição", value=str(enc.get("descricao") or ""), height=60)
        col_f1e, col_f2e = st.columns(2)
        fpag_opts = ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"]
        fpag_cur  = enc.get("forma_pagamento","A combinar")
        fpag_idx  = fpag_opts.index(fpag_cur) if fpag_cur in fpag_opts else 4
        ed_fpag   = col_f1e.selectbox("Forma de Pagamento", fpag_opts, index=fpag_idx)
        ed_obs    = col_f2e.text_area("Observações", value=str(enc.get("observacoes") or ""), height=60)

        st.markdown("📅 Datas")
        d1, d2 = st.columns(2)
        ed_vis  = d1.date_input("📏 Data Medidas", value=converter_para_data(enc.get("data_visita")),
                                 key=f"dv_{enc['rowid']}", format="DD/MM/YYYY")
        ed_conf = d2.date_input("🪡 Data da Confecção", value=converter_para_data(enc.get("data_confeccao")),
                                 key=f"dconf_{enc['rowid']}", format="DD/MM/YYYY")

        d3, d4 = st.columns(2)
        ed_pro = d3.date_input("👗 Data da Prova", value=converter_para_data(enc.get("data_prova")),
                                key=f"dp_{enc['rowid']}", format="DD/MM/YYYY")
        ed_pro2 = None
        if ed_tem_prova2:
            ed_pro2 = d4.date_input(
                "👗 Data da 2ª Prova",
                value=converter_para_data(enc.get("data_prova2")) if enc.get("data_prova2") else ed_pro + timedelta(days=7),
                key=f"dp2_{enc['rowid']}", format="DD/MM/YYYY",
            )

        d5, d6 = st.columns(2)
        ed_tec  = d5.date_input("🛍️ Data Compra do Tecido", value=converter_para_data(enc.get("data_tecido")),
                                 key=f"dt_{enc['rowid']}", format="DD/MM/YYYY")
        ed_ent  = d6.date_input("🎁 Data de Entrega", value=converter_para_data(enc.get("data_entrega")),
                                 key=f"de_{enc['rowid']}", format="DD/MM/YYYY")

        col_b1, col_b2, col_b3 = st.columns(3)
        if col_b1.form_submit_button("💾 Salvar", use_container_width=True):
            if not ed_cliente.strip():
                st.error("Informe o nome da cliente.")
                return

            # ── Validação de agenda (exclusividade da Data da Confecção) ──
            df_check_save = encomendas_listar(cancelado=False)
            ok_conf, msg_conf = validar_data_confeccao(df_check_save, ed_conf, excluir_id=str(enc["rowid"]))
            if not ok_conf:
                st.error(msg_conf)
                return

            precisa_tecido_enc = bool(int(enc.get("precisa_tecido", 0) or 0))
            etapa_atual = int(enc.get("etapa", 1))
            cliente_final = ed_cliente.strip()

            dados_salvar = {
                "cliente": cliente_final,
                "peca": ed_peca, "descricao": ed_desc,
                "forma_pagamento": ed_fpag, "observacoes": ed_obs,
                "data_visita": ed_vis.isoformat(),
                "data_tecido": ed_tec.isoformat(),
                "data_confeccao": ed_conf.isoformat(),
                "data_prova": ed_pro.isoformat(),
                "tem_prova2": 1 if ed_tem_prova2 else 0,
                "data_prova2": ed_pro2.isoformat() if ed_pro2 else "",
                "data_entrega": ed_ent.isoformat(),
            }

            etapa_ajustada = False
            if not cancelado:
                etapa_max_datas = _calcular_etapa_maxima_por_datas(
                    hoje=hoje_brasilia(), d_visita=ed_vis,
                    precisa_tecido=precisa_tecido_enc, d_tecido=ed_tec,
                    d_confeccao=ed_conf, d_prova=ed_pro, d_entrega=ed_ent,
                )
                if etapa_max_datas < etapa_atual:
                    dados_salvar["etapa"] = etapa_max_datas
                    etapa_atual = etapa_max_datas
                    etapa_ajustada = True

            encomendas_atualizar(str(enc["rowid"]), dados_salvar)

            if etapa_ajustada:
                _reverter_lembretes_por_etapa(
                    enc_id=str(enc["rowid"]), etapa_atual=etapa_atual,
                    precisa_tecido=precisa_tecido_enc,
                )

            _sincronizar_lembretes_pedido(
                enc_id=str(enc["rowid"]), cliente=cliente_final, peca=ed_peca,
                d_visita=ed_vis,
                precisa_tecido=precisa_tecido_enc, d_tecido=ed_tec,
                d_confeccao=ed_conf, d_prova=ed_pro,
                tem_prova2=ed_tem_prova2, d_prova2=ed_pro2,
                d_entrega=ed_ent,
            )

            if etapa_ajustada:
                st.success(
                    f"✅ Pedido e lembretes atualizados! A régua foi ajustada automaticamente "
                    f"para **{ETAPAS[etapa_atual][1]}**, já que ainda há etapas com data futura."
                )
            else:
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
    às tarefas daquele dia e permite editar diretamente, sem opção de
    criar nova encomenda.
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


def _mapa_prefixo_campo_data():
    """
    Relaciona o prefixo do texto da tarefa (gerado automaticamente ao criar
    a encomenda) com o campo de data correspondente na encomenda.
    """
    return {
        "📏 Medidas:":    "data_visita",
        "🛍️ Tecido:":    "data_tecido",
        "🪡 Confecção:":  "data_confeccao",
        "👗 2ª Prova:":   "data_prova2",
        "👗 Prova:":      "data_prova",
        "🎁 Entrega:":    "data_entrega",
    }


@st.dialog("📅 Editar Data da Tarefa", width="small")
def _dialog_editar_data_tarefa(row):
    """
    Popup enxuto para alterar SOMENTE a data de uma tarefa/etapa pontual,
    sem abrir o formulário completo do pedido.
    """
    st.markdown(f"**{row['tarefa']}**")
    if row.get("nome_cliente"):
        st.caption(f"👤 {row['nome_cliente']}")
    st.caption("Isso altera apenas a data desta etapa — o restante do pedido permanece igual.")

    nova_data = st.date_input(
        "Nova data",
        value=converter_para_data(row["data"]),
        key=f"nova_data_{row['rowid']}",
        format="DD/MM/YYYY",
    )

    col_ok, col_cancel = st.columns(2)
    if col_ok.button("💾 Salvar", use_container_width=True, type="primary", key=f"salvar_data_{row['rowid']}"):
        # Se a tarefa for de Confecção, aplica a regra de exclusividade do dia.
        # Provas não têm limite, então não há validação para elas aqui.
        tarefa_txt_check = str(row["tarefa"])
        enc_id_check = row.get("encomenda_id")

        if tarefa_txt_check.startswith("🪡 Confecção:"):
            df_check_tarefa = encomendas_listar(cancelado=False)
            ok_c, msg_c = validar_data_confeccao(df_check_tarefa, nova_data, excluir_id=str(enc_id_check) if enc_id_check else None)
            if not ok_c:
                st.error(msg_c)
                return

        cronograma_atualizar(str(row["rowid"]), {"data": nova_data.isoformat()})

        if enc_id_check and str(enc_id_check).strip():
            for prefixo, campo_data in _mapa_prefixo_campo_data().items():
                if tarefa_txt_check.startswith(prefixo):
                    encomendas_atualizar(str(enc_id_check), {campo_data: nova_data.isoformat()})
                    break

        st.success("✅ Data atualizada!")
        st.rerun()

    if col_cancel.button("❌ Cancelar", use_container_width=True, key=f"cancelar_data_{row['rowid']}"):
        st.rerun()


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
# DADOS DE BASE (calculados uma vez por execução, usados por vários blocos)
# ══════════════════════════════════════════════════════════════════════════════
hoje_dt    = hoje_brasilia()
df_enc_all = encomendas_listar(cancelado=False)


# ══════════════════════════════════════════════════════════════════════════════
# ██████████████████████████  BLOCO: CONTRATOS  ████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════
def renderizar_contratos():
    """
    Lista de encomendas à esquerda (com busca) + painel de detalhe do
    contrato à direita. Clicar no nome da encomenda abre, ao lado, o
    contrato completo: dados, edição de datas/valores, medidas, botão de
    baixar PDF e botão de assinatura via GOV.BR — tudo reaproveitando
    `_conteudo_pedido`, sem duplicar regra de negócio nenhuma.
    """
    st.markdown("## 📄 Contratos")
    st.caption("Selecione uma encomenda na lista para ver, editar e assinar o contrato.")

    if "ct_selecionado" not in st.session_state:
        st.session_state.ct_selecionado = None

    df_ct_full = encomendas_listar()
    if df_ct_full.empty:
        st.info("Nenhuma encomenda cadastrada ainda. Crie a primeira em **🛍️ Encomendas**.")
        return

    with st.container(key="ct_paineis"):
        col_lista, col_detalhe = st.columns([1, 1.7])

        with col_lista:
            busca_ct = st.text_input("🔍 Buscar por cliente ou peça", key="ct_busca")
            df_ct = df_ct_full
            if busca_ct.strip():
                mask_ct = (
                    df_ct["cliente"].astype(str).str.contains(busca_ct, case=False, na=False) |
                    df_ct["peca"].astype(str).str.contains(busca_ct, case=False, na=False)
                )
                df_ct = df_ct[mask_ct]

            if "_criado_em" in df_ct.columns:
                df_ct = df_ct.sort_values("_criado_em", ascending=False)

            st.markdown(f"**{len(df_ct)} encomenda(s)**")

            if df_ct.empty:
                st.info("Nenhum resultado para essa busca.")
            else:
                for _, enc in df_ct.iterrows():
                    cancelado_ct = bool(int(enc.get("cancelado", 0) or 0))
                    etapa_ct = int(enc.get("etapa", 1))
                    etapa_ic, etapa_nm = ETAPAS.get(etapa_ct, ("📦", "–"))
                    selecionado = st.session_state.ct_selecionado == enc["rowid"]

                    if st.button(
                        f"{'📄' if selecionado else '🧵'} {enc['cliente']} — {enc['peca']}",
                        key=f"ctcard_{enc['rowid']}", use_container_width=True,
                        type="primary" if selecionado else "secondary",
                    ):
                        st.session_state.ct_selecionado = enc["rowid"]
                        st.rerun()

                    badge_txt_ct = "❌ Cancelado" if cancelado_ct else f"{etapa_ic} {etapa_nm}"
                    tem_contrato = bool(
                        str(enc.get("cpf_cliente") or "").strip()
                        and str(enc.get("rg_cliente") or "").strip()
                    )
                    st.caption(
                        f"{badge_txt_ct} &nbsp;·&nbsp; "
                        f"{'📄 Contrato pronto para baixar' if tem_contrato else '⏳ Falta CPF/RG'}"
                    )

        with col_detalhe:
            selecionado_id = st.session_state.ct_selecionado
            enc_sel = encomendas_buscar(str(selecionado_id)) if selecionado_id else None

            if not enc_sel:
                if selecionado_id:
                    st.session_state.ct_selecionado = None
                st.markdown(
                    '<div class="ct-detalhe-vazio">👈 Selecione uma encomenda na lista '
                    'ao lado para ver o contrato completo aqui.</div>',
                    unsafe_allow_html=True,
                )
            else:
                cancelado_sel = bool(int(enc_sel.get("cancelado", 0) or 0))
                _conteudo_pedido(enc_sel, cancelado_sel)


# ══════════════════════════════════════════════════════════════════════════════
# ████████████████████████████  BLOCO: NOVA ENCOMENDA  █████████████████████████
# ══════════════════════════════════════════════════════════════════════════════
def renderizar_nova_encomenda():
    st.markdown("## 🆕 Nova Encomenda")
    st.caption(
        "Preencha os dados abaixo para cadastrar uma nova encomenda. "
        "Este formulário fica sempre visível nesta tela — inclusive se você trocar "
        "de aba ou de aplicativo no celular, os dados já digitados permanecem aqui."
    )
    with st.container(border=True):
        secao_nova_encomenda_inline()


# ══════════════════════════════════════════════════════════════════════════════
# ██████████████████████████████  BLOCO: MEDIDAS  ██████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════
def renderizar_medidas():
    st.markdown("## 📏 Medidas")
    st.markdown("### 📏 Ficha de Medidas")

    df_c = clientes_listar()

    if df_c.empty:
        st.info(
            "Nenhuma cliente cadastrada ainda. Novas clientes são cadastradas direto "
            "na hora de criar uma encomenda (seção **🆕 Nova Encomenda**)."
        )
        return

    busca_med = st.text_input("🔍 Buscar cliente pelo nome", key="busca_med")
    df_c_filtrado = df_c
    if busca_med.strip():
        df_c_filtrado = df_c[df_c["nome"].str.contains(busca_med, case=False, na=False)]

    if df_c_filtrado.empty:
        st.info("Nenhuma cliente encontrada para essa busca.")
        return

    sel_cli = st.selectbox("Selecione a cliente", df_c_filtrado["nome"].tolist(), key="sel_med")
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


# ══════════════════════════════════════════════════════════════════════════════
# ██████████████████████████  BLOCO: GERENCIAR PEDIDOS  ████████████████████████
# ══════════════════════════════════════════════════════════════════════════════
def renderizar_gerenciar_pedidos():
    st.markdown("## 📋 Gerenciar Pedidos")
    st.caption("💡 Clique em um pedido para abrir os detalhes — o nome da cliente também pode ser editado ali, na seção **✏️ Editar Pedido**.")

    filtro_cli = st.text_input(
        "🔍 Buscar por cliente ou peça",
        key="busca_ger",
        placeholder="Digite o nome da cliente ou da peça...",
    )

    filtro_status = st.radio(
        "Filtrar por status:",
        ["Em andamento", "Todos", "Concluídos", "Cancelados"],
        horizontal=True, key="filtro_ger",
    )

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
            mask_busca = (
                df_e["cliente"].astype(str).str.contains(filtro_cli, case=False, na=False)
                | df_e["peca"].astype(str).str.contains(filtro_cli, case=False, na=False)
            )
            df_e = df_e[mask_busca]

        if "data_entrega" in df_e.columns:
            df_e = df_e.sort_values("data_entrega", ascending=True, na_position="last")

    if df_e.empty:
        st.info("Nenhum pedido encontrado com os filtros selecionados.")
    else:
        cols_ped = st.columns(2)
        for idx, (_, enc) in enumerate(df_e.iterrows()):
            with cols_ped[idx % 2]:
                _card_pedido(enc, idx)


# ══════════════════════════════════════════════════════════════════════════════
# ████████████████████████████  BLOCO: AGENDA  ███████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════
def _secao_alerta_entregas_urgentes():
    """
    Alerta VISUALMENTE DIFERENTE do aviso normal de "atrasado": mostra os
    pedidos cuja Data de Entrega esteja dentro da janela de antecedência
    configurada em ⚙️ Configurações (padrão: 7 dias) — sinal de "pare tudo
    e priorize".
    """
    dias_antecedencia = int(cfg_get("alerta_entrega_dias") or 7)
    df_urgentes = pedidos_com_entrega_proxima(df_enc_all, hoje_dt, dias_antecedencia)

    if df_urgentes.empty:
        return

    st.markdown(f"""
    <div class="entrega-urgente-zone">
        <b style="color:#7a1a1a;">🚨 ENTREGA(S) URGENTE(S) — PRIORIDADE MÁXIMA</b><br>
        <span style="font-size:0.8rem;color:#7a1a1a;">
        Aviso configurado para {dias_antecedencia} dia(s) de antecedência da Data de Entrega
        (ajustável em ⚙️ Configurações). Pare o que estiver fazendo e priorize estes pedidos.
        </span>
    </div>
    """, unsafe_allow_html=True)

    for _, r in df_urgentes.iterrows():
        dias_rest = int(r["_dias_restantes"])
        if dias_rest < 0:
            txt_prazo = f"⚠️ ATRASADO há {abs(dias_rest)} dia(s)"
        elif dias_rest == 0:
            txt_prazo = "🔥 ENTREGA É HOJE"
        else:
            txt_prazo = f"⏳ faltam {dias_rest} dia(s)"

        col_i, col_b = st.columns([4, 1])
        with col_i:
            st.markdown(f"""
            <div class="fin-danger">
                <b>{r['cliente']}</b> — {r['peca']} &nbsp;|&nbsp;
                🎁 Entrega: {formatar_data_br(r['data_entrega'])} &nbsp;|&nbsp; <b>{txt_prazo}</b>
            </div>""", unsafe_allow_html=True)
        with col_b:
            if st.button("👁️ Ver Pedido", key=f"ver_urgente_{r['rowid']}", use_container_width=True):
                cancelado_r = bool(int(r.get("cancelado", 0) or 0))
                _abrir_popup_pedido(dict(r), cancelado_r)

    st.divider()


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

            col_info, col_btn1, col_btn2 = st.columns([4, 1, 1])
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
            with col_btn1:
                st.write("")
                st.write("")
                if st.button("✅ Feito", key=f"hoje_{row['rowid']}", use_container_width=True):
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
            with col_btn2:
                st.write("")
                st.write("")
                if st.button("📅 Data", key=f"data_hoje_{row['rowid']}", use_container_width=True,
                             help="Editar apenas a data desta tarefa"):
                    _dialog_editar_data_tarefa(row)

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


def renderizar_agenda():
    st.markdown("## 📅 Agenda")
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
        _secao_alerta_entregas_urgentes()
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
# ████████████████████████████  BLOCO: CONFIGURAÇÕES  ██████████████████████████
# ══════════════════════════════════════════════════════════════════════════════
def renderizar_configuracoes():
    st.markdown("## ⚙️ Configurações")
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

        st.markdown("#### 🚨 Alerta de Entrega Urgente")
        st.caption(
            "Quantos dias ANTES da Data de Entrega o Painel deve mostrar o alerta "
            "vermelho de prioridade máxima na Agenda."
        )
        with st.form("form_alerta_entrega"):
            cfg_alerta_dias = st.number_input(
                "Dias de antecedência para o alerta urgente",
                min_value=1, max_value=180,
                value=int(cfg_get("alerta_entrega_dias") or 7),
                help="Ex.: 7 = avisa 1 semana antes da entrega. Pode ajustar para 30, 60 etc.",
            )
            if st.form_submit_button("💾 Salvar Alerta de Entrega"):
                cfg_set("alerta_entrega_dias", str(int(cfg_alerta_dias)))
                st.success("✅ Alerta de entrega atualizado!")
                st.rerun()

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
    st.markdown("#### 📏 Regras Fixas da Agenda")
    st.info(
        f"**Provas não têm limite** — você pode marcar quantas quiser no mesmo dia. "
        f"Mas um dia com **mais de {LIMITE_PROVAS_PARA_CONFECCAO} provas** fica "
        f"bloqueado para receber **Data da Confecção**, e a regra de "
        f"**nunca dois clientes com Confecção no mesmo dia** também é fixa. "
        f"Nenhuma das duas é ajustável por aqui — elas garantem que a produção "
        f"não fique sobrecarregada."
    )

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


# ══════════════════════════════════════════════════════════════════════════════
# CABEÇALHO DO SISTEMA (FIXO) + KPIs DO TOPO — sempre visíveis, qualquer que
# seja a seção selecionada. Fica "grudado" no topo (position: sticky) enquanto
# o conteúdo de cada bloco rola por baixo.
# ══════════════════════════════════════════════════════════════════════════════
with st.container(key="topo_fixo"):
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

    enc_ativas = 0
    if not df_enc_all.empty and "etapa" in df_enc_all.columns:
        enc_ativas = int((df_enc_all["etapa"].astype(int) < 7).sum())

    meta_ped = int(cfg_get("meta_pedidos_mes") or 8)

    mes_atual_str = hoje_dt.strftime("%Y-%m")
    pedidos_mes = 0
    if not df_enc_all.empty:
        col_data_ref = "criado_em" if "criado_em" in df_enc_all.columns else "_criado_em"
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
        <div class="kpi-value">{pedidos_mes}<span style="font-size:0.85rem;color:#8b7355;"> / {meta_ped}</span></div>
        <div class="kpi-bar"><div style="width:{pct_meta:.0f}%;"></div></div>
        <div class="kpi-sub">{pct_meta:.0f}% da meta deste mês</div>
    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# NAVEGAÇÃO LATERAL
# ══════════════════════════════════════════════════════════════════════════════
if "pagina" not in st.session_state:
    st.session_state.pagina = "nova_encomenda"

def _nav_btn(label: str, valor: str, icone: str):
    ativo = st.session_state.pagina == valor
    if st.button(f"{icone}  {label}", use_container_width=True,
                 type="primary" if ativo else "secondary", key=f"nav_{valor}"):
        st.session_state.pagina = valor
        st.rerun()

with st.sidebar:
    st.markdown('<div class="sb-titulo">🧵 Lila Closet</div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-subtitulo">Atelier de Costura</div>', unsafe_allow_html=True)

    st.markdown('<div class="sb-secao-label">Operacional</div>', unsafe_allow_html=True)
    _nav_btn("Nova Encomenda",    "nova_encomenda",     "🆕")
    _nav_btn("Agenda",            "agenda",             "📅")
    _nav_btn("Contratos",         "contratos",          "📄")
    _nav_btn("Medidas",           "medidas",            "📏")
    _nav_btn("Gerenciar Pedidos", "gerenciar_pedidos",  "📋")

    st.markdown('<div class="sb-secao-label">Gestão</div>', unsafe_allow_html=True)
    _nav_btn("Financeiro", "financeiro", "💰")

    st.markdown('<div class="sb-secao-label">Administração</div>', unsafe_allow_html=True)
    _nav_btn("Configurações", "configuracoes", "⚙️")

# ══════════════════════════════════════════════════════════════════════════════
# ROTEAMENTO — renderiza o bloco selecionado na sidebar
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.pagina == "nova_encomenda":
    renderizar_nova_encomenda()
elif st.session_state.pagina == "agenda":
    renderizar_agenda()
elif st.session_state.pagina == "contratos":
    renderizar_contratos()
elif st.session_state.pagina == "medidas":
    renderizar_medidas()
elif st.session_state.pagina == "gerenciar_pedidos":
    renderizar_gerenciar_pedidos()
elif st.session_state.pagina == "financeiro":
    renderizar_financeiro(df_enc_all, hoje_dt)
elif st.session_state.pagina == "configuracoes":
    renderizar_configuracoes()

st.caption("v13.0.0 | Lila Closet Atelier | Firestore · Horário de Brasília · wendleydesenvolvimento")
