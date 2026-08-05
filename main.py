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
    BLOCO GERENCIAR PEDIDOS → gerenciamento geral dos pedidos (cards + popup)
                              — inclui tudo que "Contratos" fazia (ver PDF,
                              CPF/RG, GOV.BR), já que são a mesma tela
    BLOCO MEDIDAS           → ficha de medidas das clientes (com busca)
    BLOCO PROSPECT          → agora em modulos/mod_prospect.py
    BLOCO FINANCEIRO        → agora em modulos/mod_financeiro.py
    BLOCO CONFIGURAÇÕES     → dados da empresa, metas, alerta de entrega,
                              exclusões permanentes

  Ordem da sidebar (grupo "Operacional"):
      Prospect → Nova Encomenda → Agenda → Medidas → Gerenciar Pedidos
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

  [v11] BLOCO CONTRATOS (removido em v17 — ver changelog abaixo): antes,
        "ver o contrato" só existia dentro do popup de um pedido
        (Gerenciar Pedidos → clique no card). Passou a existir uma seção
        própria na sidebar — "📄 Contratos" — reaproveitando 100% da
        função `_conteudo_pedido` já existente.

  [v11.1] O que antes era um único bloco "Encomendas" (com Nova Encomenda no
        topo + abas internas "Medidas & Clientes" e "Gerenciar Pedidos") virou
        itens próprios na sidebar: 🆕 Nova Encomenda, 📏 Medidas e
        📋 Gerenciar Pedidos — cada um com sua função `renderizar_*` dedicada,
        sem abas internas escondendo conteúdo.

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
        nem Streamlit, reaproveitadas na criação E na edição de pedido).

  [v13] MEDIDAS ENXUTO / GERENCIAR PEDIDOS — ajustes de UX e filtros padrão.

  [v14] SENHA ADM PARA CONFLITO DE CONFECÇÃO.

  [v15] MODULARIZAÇÃO — BLOCO ENCOMENDAS extraído para
        `modulos/mod_encomendas.py`.

  [v16] (em modulos/mod_encomendas.py) Contratos e Gerenciar Pedidos
        unificados — `renderizar_contratos()` virou um ALIAS interno de
        `renderizar_gerenciar_pedidos()`.

  [v17] LIMPEZA DA DUPLICIDADE + PROSPECT: botão "📄 Contratos" removido da
        sidebar (alias duplicado); novo módulo `modulos/mod_prospect.py`
        plugado como "🌱 Prospect" na sidebar.

  [v18] CORREÇÃO DE BUGS — régua de etapas antiga (1-7) ainda espalhada
        pelo main.py, sobrevivendo à migração para a régua enxuta (1-4,
        feita em mod_encomendas.py v16). Isso causava três problemas reais:

        1) "✅ Feito" (Agenda → Tarefas para Hoje) usava a lógica de avanço
           de etapa ANTIGA (`prox+1`, com saltos manuais tipo "se prox==2,
           prox=3"). Na régua nova isso fazia o pedido pular direto para
           **Concluído (4)** sozinho, sem ninguém clicar em "✅ Marcar
           Concluído" — ou seja, pedidos "se fechavam sozinhos". Corrigido:
           agora o botão "✅ Feito" avança no MÁXIMO até a etapa 3
           (Entrega); a etapa 4 (Concluído) só é definida pelo humano,
           clicando em "✅ Marcar Concluído" dentro do pedido (isso nunca
           mudou — mod_encomendas.py já garantia isso corretamente).

        2) "🎁 Entregas de Hoje" filtrava por `etapa >= 6` (valor válido só
           na régua antiga de 7 etapas). Na régua nova (máximo 4), essa
           condição nunca era verdadeira — a seção sempre aparecia vazia,
           mesmo com entregas de verdade marcadas para hoje. Corrigido para
           `etapa >= 3` (Entrega ou Concluído).

        3) O KPI "🛍️ Pedidos Ativos" do topo contava `etapa < 7`, que na
           régua nova é SEMPRE verdadeiro (inclusive para pedidos já
           Concluídos) — o card contava pedidos concluídos como "ativos".
           Corrigido para `etapa < 4`.

        Além disso, o mesmo tipo de resquício foi corrigido em
        `modulos/regras_agenda.py` (`pedidos_com_entrega_proxima` filtrava
        por `etapa < 7`, fazendo pedidos já concluídos aparecerem para
        sempre no alerta de entrega urgente/atrasados da Agenda).

        4) SELEÇÃO DE CLIENTE EM MEDIDAS POR ROWID (não mais por nome): a
           tela "📏 Medidas" selecionava a cliente comparando o NOME digitado
           no dropdown com `df_c["nome"] == sel_cli`. Se duas clientes
           tivessem o mesmo nome cadastrado, a segunda nunca era alcançável
           — selecionar o nome dela sempre abria (e sobrescrevia, ao salvar)
           os dados da PRIMEIRA cliente com aquele nome. Corrigido: a lista
           agora é construída e selecionada por `rowid` (identificador único
           do Firestore), com o nome exibido como rótulo — e um sufixo
           discreto é adicionado automaticamente só quando há nomes
           duplicados, pra desambiguar sem poluir a tela no caso comum.
           (Também foi corrigido em `database.py`: `clientes_listar()` não
           usa mais `.order_by("nome")` do Firestore, que excluía
           silenciosamente qualquer cliente sem o campo "nome" preenchido.)

  [v18.1] CORREÇÃO DE COMPATIBILIDADE — f-string com barra invertida na
        parte {...} (montagem do HTML das tarefas do calendário) não é
        aceita pelo Python 3.11 (só passou a ser permitido a partir do
        Python 3.12). Corrigido calculando o HTML do "cliente" numa
        variável separada antes de montar a f-string final.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
import calendar
import base64

# ── Helpers compartilhados (fuso de Brasília, formatação, constantes) ────────
from modulos.utils import (
    MESES_PT,
    agora_br, hoje_brasilia,
    formatar_data_br, formatar_data_hora_br, brl,
)

# ── Módulos extraídos ─────────────────────────────────────────────────────────
from modulos.mod_financeiro import renderizar_financeiro
from modulos.mod_prospect import renderizar_prospects
from modulos.mod_encomendas import (
    DIC_MEDIDAS, SENHA_DELETE, LOGO_PATH,
    renderizar_nova_encomenda, renderizar_gerenciar_pedidos,
    _abrir_popup_pedido, _dialog_editar_dia, _dialog_editar_data_tarefa,
    _fmt_medida_para_texto,
)
from modulos.regras_agenda import (
    pedidos_com_entrega_proxima, LIMITE_PROVAS_PARA_CONFECCAO, ETAPA_CONCLUIDO,
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
   BLOCO GERENCIAR PEDIDOS — lista de encomendas (cards) + painel de
   detalhe do pedido em popup. Mesmo espírito do painel de
   Tickets do KingStar: cards clicáveis na lista.
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
# ETAPAS, DIC_MEDIDAS, SENHA_DELETE e LOGO_PATH agora vivem em
# modulos/mod_encomendas.py (fonte única) e são importados no topo deste
# arquivo — DIC_MEDIDAS é usada por renderizar_medidas(), SENHA_DELETE pelas
# exclusões permanentes em Configurações, e LOGO_PATH por get_logo_base64().
# ETAPA_CONCLUIDO (=4) vem de modulos/regras_agenda.py — última etapa da
# régua atual, usada para nunca mais espalhar um "7" ou "6" solto pelo
# código (foi exatamente isso que causou os bugs corrigidos no v18).
META_HORAS_CAMPO = 50.0
META_PESO_KG     = 57.0
PESO_INICIAL_KG  = 70.0

# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO DO BANCO
# ══════════════════════════════════════════════════════════════════════════════
init_db()

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS (específicos do main.py)
# ══════════════════════════════════════════════════════════════════════════════
def get_logo_base64() -> str | None:
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


# ══════════════════════════════════════════════════════════════════════════════
# DADOS DE BASE (calculados uma vez por execução, usados por vários blocos)
# ══════════════════════════════════════════════════════════════════════════════
hoje_dt    = hoje_brasilia()
df_enc_all = encomendas_listar(cancelado=False)






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
        df_c_filtrado = df_c[df_c["nome"].astype(str).str.contains(busca_med, case=False, na=False)]

    if df_c_filtrado.empty:
        st.info("Nenhuma cliente encontrada para essa busca.")
        return

    # ── [v18] Seleção por ROWID, nunca por nome ────────────────────────────
    # Antes, a cliente era localizada comparando `df_c["nome"] == sel_cli`.
    # Se duas clientes tivessem o MESMO nome cadastrado, a segunda nunca era
    # alcançável — selecionar o nome dela sempre abria (e salvava por cima)
    # os dados da PRIMEIRA cliente com aquele nome, dando a impressão de que
    # ela "não aparecia" para cadastrar medidas. Agora a lista é montada e
    # selecionada pelo `rowid` (único de verdade no Firestore); um sufixo
    # discreto só aparece quando dois nomes colidem, pra desambiguar sem
    # poluir a tela no caso comum (nomes únicos).
    df_c_filtrado = df_c_filtrado.sort_values(
        "nome", key=lambda s: s.fillna("").astype(str).str.lower()
    )
    opcoes_med: dict[str, str] = {}
    contagem_nomes: dict[str, int] = {}
    for _, row in df_c_filtrado.iterrows():
        nome_row = str(row.get("nome") or "—")
        contagem_nomes[nome_row] = contagem_nomes.get(nome_row, 0) + 1
        label = nome_row if contagem_nomes[nome_row] == 1 else f"{nome_row} ({str(row['rowid'])[:6]})"
        opcoes_med[label] = row["rowid"]

    sel_label = st.selectbox("Selecione a cliente", list(opcoes_med.keys()), key="sel_med")
    sel_rowid = opcoes_med[sel_label]
    dados_cli = df_c[df_c["rowid"] == sel_rowid].iloc[0]

    with st.form(f"form_med_{sel_rowid}"):
        col1, col2, col3 = st.columns(3)
        novos = {}
        for i, (label, col_db) in enumerate(DIC_MEDIDAS.items()):
            raw = dados_cli.get(col_db)
            val_txt = _fmt_medida_para_texto(raw)
            target = col1 if i < 5 else (col2 if i < 10 else col3)
            novos[col_db] = target.text_input(
                f"{label} (cm)", value=val_txt,
                key=f"med_{sel_rowid}_{col_db}",
                placeholder="Ex: 36 ou 25/33",
            )
        obs = st.text_area("Observações de modelagem", value=str(dados_cli.get("outro") or ""))

        if st.form_submit_button("💾 Salvar Medidas", use_container_width=True):
            update_data = {**novos, "outro": obs}
            clientes_atualizar(str(dados_cli["rowid"]), update_data)
            st.success("✅ Medidas salvas!")
            st.rerun()




# ══════════════════════════════════════════════════════════════════════════════
# ████████████████████████████  BLOCO: AGENDA  ███████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════
def _secao_alerta_entregas_urgentes():
    """
    Alerta VISUALMENTE DIFERENTE do aviso normal de "atrasado": mostra os
    pedidos cuja Data de Entrega esteja dentro da janela de antecedência
    configurada em ⚙️ Configurações (padrão: 7 dias) — sinal de "pare tudo
    e priorize". `pedidos_com_entrega_proxima` já exclui pedidos cancelados
    e (desde a correção do v18) pedidos já Concluídos (etapa 4).
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
                            # ── [v18 — CORREÇÃO DE BUG] ──────────────────────
                            # Antes: `prox = etapa+1`, com saltos manuais da
                            # régua ANTIGA (1-7) — na régua atual (1-4) isso
                            # fazia o pedido pular direto para "Concluído"
                            # (4) sozinho, sem nenhum humano confirmar.
                            # Agora: concluir uma tarefa do dia avança a
                            # régua em no MÁXIMO até a etapa 3 (Entrega).
                            # A etapa 4 (Concluído) É SEMPRE uma decisão
                            # manual — só é definida quando alguém clica em
                            # "✅ Marcar Concluído" dentro do próprio pedido
                            # (em mod_encomendas.py, nunca aqui).
                            etapa_atual_feito = int(enc_data.get("etapa", 1))
                            prox = min(etapa_atual_feito + 1, ETAPA_CONCLUIDO - 1)
                            if prox > etapa_atual_feito:
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
        # ── [v18 — CORREÇÃO DE BUG] ──────────────────────────────────────
        # Antes: filtrava por `etapa >= 6`, valor só válido na régua ANTIGA
        # de 7 etapas — na régua atual (máximo 4) essa condição nunca era
        # verdadeira, então esta seção ficava sempre vazia mesmo havendo
        # entregas de verdade marcadas para hoje. Corrigido para
        # `>= ETAPA_CONCLUIDO - 1` (etapa "Entrega" ou "Concluído") — usa a
        # constante nomeada em vez de um número solto, para nunca mais
        # ficar defasado se a régua mudar de novo no futuro.
        df_ent_hoje = df_enc_all[
            (df_enc_all.get("data_entrega", pd.Series(dtype=str)) == hoje_dt.isoformat()) &
            (df_enc_all["etapa"].astype(int) >= ETAPA_CONCLUIDO - 1)
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

                # ── [v18.1 — CORREÇÃO DE COMPATIBILIDADE] ────────────────────
                # Antes, o HTML do "cliente" era montado com uma expressão
                # condicional (com aspas escapadas \") DENTRO da parte {...}
                # de uma f-string. Isso só é aceito a partir do Python 3.12 —
                # no Python 3.11 dá SyntaxError: "f-string expression part
                # cannot include a backslash". Corrigido calculando o HTML do
                # cliente numa variável comum ANTES de montar a f-string.
                tarefas_html = ""
                for _, r in tasks.iterrows():
                    tipo_tarefa  = r["tarefa"].split(":")[0].strip() if ":" in r["tarefa"] else r["tarefa"][:16]
                    cliente_cal  = r.get("nome_cliente", "")
                    cliente_html = f'<br><span class="cal-task-cliente">{cliente_cal}</span>' if cliente_cal else ""
                    tarefas_html += f"<div class='cal-task-tag'>{tipo_tarefa}{cliente_html}</div>"

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
        f"bloqueado para receber **Data da Confecção**. A regra de **nunca dois "
        f"clientes com Confecção no mesmo dia** também é fixa, mas pode ser liberada "
        f"pontualmente com a senha de administrador (a mesma usada em Exclusão "
        f"Permanente) — sem a senha correta, o sistema não deixa salvar."
    )
    st.info(
        "🔒 **A etapa 'Concluído' só pode ser definida por um humano** — clicando em "
        "\"✅ Marcar Concluído\" dentro do próprio pedido. Marcar tarefas do dia como "
        "\"Feito\" na Agenda avança a régua no máximo até a etapa Entrega."
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
            f"{row['nome']}" + (f" · {row['telefone']}" if str(row.get('telefone') or '').strip() else "")
            + f" ({str(row['rowid'])[:6]})": row["rowid"]
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

    # ── [v18 — CORREÇÃO DE BUG] ──────────────────────────────────────────
    # Antes: `etapa < 7`, valor da régua ANTIGA de 7 etapas — na régua
    # atual (máximo 4) essa condição era SEMPRE verdadeira, contando até
    # pedidos já Concluídos como "ativos". Corrigido para `etapa < 4`.
    enc_ativas = 0
    if not df_enc_all.empty and "etapa" in df_enc_all.columns:
        enc_ativas = int((df_enc_all["etapa"].astype(int) < ETAPA_CONCLUIDO).sum())

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
    _nav_btn("Prospect",           "prospect",           "🌱")
    _nav_btn("Nova Encomenda",    "nova_encomenda",     "🆕")
    _nav_btn("Agenda",            "agenda",             "📅")
    _nav_btn("Medidas",           "medidas",            "📏")
    _nav_btn("Gerenciar Pedidos", "gerenciar_pedidos",  "📋")

    st.markdown('<div class="sb-secao-label">Gestão</div>', unsafe_allow_html=True)
    _nav_btn("Financeiro", "financeiro", "💰")

    st.markdown('<div class="sb-secao-label">Administração</div>', unsafe_allow_html=True)
    _nav_btn("Configurações", "configuracoes", "⚙️")

# ══════════════════════════════════════════════════════════════════════════════
# ROTEAMENTO — renderiza o bloco selecionado na sidebar
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.pagina == "prospect":
    renderizar_prospects()
elif st.session_state.pagina == "nova_encomenda":
    renderizar_nova_encomenda()
elif st.session_state.pagina == "agenda":
    renderizar_agenda()
elif st.session_state.pagina == "medidas":
    renderizar_medidas()
elif st.session_state.pagina == "gerenciar_pedidos":
    renderizar_gerenciar_pedidos()
elif st.session_state.pagina == "financeiro":
    renderizar_financeiro(df_enc_all, hoje_dt)
elif st.session_state.pagina == "configuracoes":
    renderizar_configuracoes()

st.caption("v18.1.0 | Lila Closet Atelier | Firestore · Horário de Brasília · wendleydesenvolvimento")
