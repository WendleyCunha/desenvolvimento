"""
modulos/mod_financeiro.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
BLOCO FINANCEIRO — v19 (Resumo do Fechamento reestruturado + PDF oficial).

[v19] AJUSTES NA ABA "🔒 Fechamento & Conciliação" (a pedido do Wendley,
      usando como referência a estrutura oficial da Folha de Contas (S-26)
      e do Relatório Mensal de Contas (S-30) — SEM a parte de "Anúncio
      Mensal", que não se aplica aqui):

  1) NOVO "📋 Resumo do Fechamento" — passou a ser a PRIMEIRA coisa exibida
     na aba (antes da conferência lançamento por lançamento), com a mesma
     estrutura oficial:
         Saldo do Mês Anterior
       + Total das Entradas
       – Total das Despesas
       = Saldo do Mês (Positivo/Negativo)
       = Saldo Disponível no Final do Mês (sempre transportado
         automaticamente para o mês seguinte)
     Nenhum cálculo mudou — é o mesmo `saldo_inicial`, `receitas_mes`,
     `despesas_mes`, `lucro_real_mes`, `saldo_teorico` de sempre, só
     exibidos de forma mais clara e na ordem oficial, logo no topo.

  2) NOVO PDF DE FECHAMENTO (`gerar_pdf_fechamento`) — ao lado do Excel que
     já existia, um botão "📄 Baixar PDF de Fechamento" gera um documento
     no mesmo padrão visual do contrato (marrom/dourado), com: Resumo do
     Mês, Entradas do Mês (detalhado), Despesas do Mês (detalhado), Grandes
     Despesas Previstas (se houver) e Confronto com o Extrato Bancário (se
     informado). Se o mês ainda não foi fechado, o PDF sai com um selo
     "⏳ PRÉVIA" (os valores podem mudar até o fechamento oficial); se já
     foi fechado, sai com "🔒 FECHADO em dd/mm/aaaa às hh:mm" e usa os
     valores OFICIAIS gravados no fechamento (não recalculados).

  3) Extrato do mês (conferência lançamento por lançamento) continua
     exatamente igual — só mudou de posição (agora vem logo depois do
     Resumo, antes de Grandes Despesas). Nenhuma lógica de edição/exclusão/
     conciliação foi tocada.

  Nada na aba 📈 Projeção ou 📑 Receb./Despe. foi alterado.

HISTÓRICO ANTERIOR (mantido para referência):

  [v15] NOVO KPI "🔮 Lucro Previsto (mês)" no topo: soma o Lucro Real
     (histórico, já recebido/pago) + apenas o SALDO que ainda falta
     receber (valor_total - valor_recebido, nunca o bruto) de pedidos com
     Data de Entrega dentro do mês atual.

  [v16] "Visão Geral" (Saldo, Alertas, KPIs) passou a viver dentro de um
     expander recolhido por padrão — nada foi removido, só a exibição
     ficou oculta até o usuário clicar para expandir.

  [v17] "Recebimentos e Despesas" (pedidos com saldo pendente) também
     passou a viver dentro de um expander recolhido, mesmo padrão do v16.

  [v18] O "Relatório Financeiro Mensal" (antes uma aba própria) foi movido
     para dentro da aba "📑 Receb. / Despe.", logo abaixo do Novo
     Lançamento.

PRINCÍPIO GERAL DESTE ARQUIVO: toda projeção lê, AO VIVO, a Data de
Entrega dos pedidos e o vencimento das despesas em aberto. Se você mudar a
agenda de um pedido (adiar a entrega, por exemplo), a próxima renderização
desta tela já reflete isso automaticamente — não existe nenhum valor
travado ou cacheado incorretamente.

Requisitos em database.py — inalterados (recebimentos_*, gastos_*,
fechamento_*, fechamentos_listar).

Ponto de entrada: `renderizar_financeiro(df_enc_all, hoje_dt)`
  - df_enc_all: DataFrame de encomendas ativas (não canceladas).
  - hoje_dt: data de hoje (date), no fuso de Brasília.
"""

import io
import os
from datetime import date

import pandas as pd
import streamlit as st
import xlsxwriter

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# LOGO_PATH vem de mod_encomendas (fonte única — mesmo padrão já usado em
# main.py). Nenhuma regra de negócio de encomendas é importada aqui, só o
# caminho do arquivo do logo, para o cabeçalho do PDF de fechamento ficar
# visualmente igual ao PDF de contrato.
from modulos.mod_encomendas import LOGO_PATH

from database import (
    cfg_get,
    encomendas_atualizar,
    encomendas_listar,
    fechamento_buscar,
    fechamento_salvar,
    fechamentos_listar,
    gastos_atualizar,
    gastos_deletar,
    gastos_inserir,
    gastos_listar,
    recebimentos_atualizar,
    recebimentos_deletar,
    recebimentos_inserir,
    recebimentos_listar,
)
from modulos.utils import (
    CAT_GASTOS,
    MESES_PT,
    agora_br,
    brl,
    formatar_data_br,
    formatar_data_hora_br,
    hoje_brasilia,
    pct_str,
)

CAT_RECEITAS = ["Venda de peça", "Sinal/Entrada", "Aula/Consultoria", "Reembolso recebido", "Outro"]
FORMAS_PAGAMENTO = ["Pix", "Dinheiro", "Cartão de Débito", "Cartão de Crédito", "Transferência", "Boleto"]

_COLS_RECEBIMENTOS = [
    "rowid", "data", "descricao", "valor", "categoria",
    "forma_pagamento", "conciliado", "encomenda_id", "_criado_em",
]
_COLS_GASTOS = [
    "rowid", "data", "descricao", "valor", "categoria", "pago",
    "recorrente", "grande_despesa_prevista", "conciliado",
    "encomenda_id", "_criado_em",
]


# ══════════════════════════════════════════════════════════════════════════
# HELPERS DE DATA/DINHEIRO — base de tudo que este módulo calcula
# ══════════════════════════════════════════════════════════════════════════

def _flt(df, col, default=0.0):
    if df.empty or col not in df.columns:
        return default
    return float(df[col].fillna(0).astype(float).sum())


def _mes_de(data_iso: str) -> str:
    """Extrai 'YYYY-MM' de uma string de data isoformat. String vazia/None -> ''."""
    if not data_iso:
        return ""
    return str(data_iso)[:7]


def _to_date_seguro(valor):
    """Converte string ISO em date. Retorna None se vazio/inválido — nunca lança exceção."""
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _df_vazio_receb() -> pd.DataFrame:
    return pd.DataFrame(columns=_COLS_RECEBIMENTOS)


def _df_vazio_gastos() -> pd.DataFrame:
    return pd.DataFrame(columns=_COLS_GASTOS)


def _ultimo_fechamento(df_fech: pd.DataFrame):
    """Retorna (dict do último mês FECHADO, ou None)."""
    if df_fech.empty or "fechado" not in df_fech.columns:
        return None
    fechados = df_fech[df_fech["fechado"].astype(int) == 1].copy()
    if fechados.empty:
        return None
    fechados = fechados.sort_values("mes", ascending=False)
    return fechados.iloc[0].to_dict()


def _mes_seguinte(mes_str: str) -> str:
    """'2026-03' -> '2026-04'."""
    ts = pd.Timestamp(f"{mes_str}-01") + pd.DateOffset(months=1)
    return ts.strftime("%Y-%m")


def _grandes_despesas_previstas(df_gastos: pd.DataFrame) -> pd.DataFrame:
    """
    Despesas grandes já esperadas, ainda não pagas, com fundos reservados.
    Não são filtradas por mês — ficam "rolando" de um mês para o outro até
    serem pagas.
    """
    if df_gastos.empty or "grande_despesa_prevista" not in df_gastos.columns:
        return _df_vazio_gastos()
    df = df_gastos[
        (df_gastos["pago"].astype(int) == 0)
        & (df_gastos["grande_despesa_prevista"].fillna(0).astype(int) == 1)
    ].copy()
    return df


def _saldo_em_caixa(df_receb: pd.DataFrame, df_gastos: pd.DataFrame, df_fech: pd.DataFrame):
    """
    Saldo real de caixa hoje = saldo herdado do último mês fechado
    + recebimentos posteriores a esse fechamento
    - gastos pagos posteriores a esse fechamento.

    Se nunca houve fechamento, considera o histórico completo (saldo herdado = 0).
    Este cálculo é sobre DINHEIRO REAL JÁ MOVIMENTADO — nunca inclui nada
    "a receber" ou "a pagar" que ainda não aconteceu.
    """
    ult = _ultimo_fechamento(df_fech)
    mes_corte = ult["mes"] if ult else None
    saldo_herdado = float(ult["saldo_final"]) if ult else 0.0

    if not df_receb.empty:
        receb_pos = df_receb[df_receb["data"].apply(_mes_de) > mes_corte] if mes_corte else df_receb
        total_receb_pos = _flt(receb_pos, "valor")
    else:
        total_receb_pos = 0.0

    if not df_gastos.empty:
        pagos = df_gastos[df_gastos["pago"].astype(int) == 1]
        pagos_pos = pagos[pagos["data"].apply(_mes_de) > mes_corte] if mes_corte else pagos
        total_gastos_pos = _flt(pagos_pos, "valor")
    else:
        total_gastos_pos = 0.0

    saldo_atual = saldo_herdado + total_receb_pos - total_gastos_pos
    return saldo_atual, mes_corte, saldo_herdado


# ══════════════════════════════════════════════════════════════════════════
# HELPERS DE RECEBÍVEIS/DESPESAS — SEMPRE lêem a agenda ao vivo
# (data_entrega dos pedidos, data de vencimento das despesas em aberto)
# ══════════════════════════════════════════════════════════════════════════

def _pedidos_com_saldo_pendente(df_enc: pd.DataFrame) -> pd.DataFrame:
    """
    Pedidos ativos (não cancelados — já vem filtrado assim de
    encomendas_listar(cancelado=False)) que ainda têm saldo a receber,
    independente da etapa (um pedido "Concluído" que não foi totalmente
    pago CONTINUA tendo saldo pendente — não escondemos isso).

    Nunca soma valor_total bruto: sempre valor_total - valor_recebido,
    nunca negativo.
    """
    if df_enc is None or df_enc.empty:
        return df_enc.iloc[0:0] if df_enc is not None else pd.DataFrame()
    if "valor_total" not in df_enc.columns or "valor_recebido" not in df_enc.columns:
        return df_enc.iloc[0:0]
    df = df_enc.copy()
    df["_saldo_pendente"] = (
        df["valor_total"].fillna(0).astype(float) - df["valor_recebido"].fillna(0).astype(float)
    ).clip(lower=0)
    return df[df["_saldo_pendente"] > 0.01]


def _receber_do_mes(df_enc: pd.DataFrame, mes_str: str) -> pd.DataFrame:
    """Pedidos com saldo pendente cuja Data de Entrega caia no mês informado (lida ao vivo)."""
    df = _pedidos_com_saldo_pendente(df_enc)
    if df.empty or "data_entrega" not in df.columns:
        return df.iloc[0:0]
    return df[df["data_entrega"].fillna("").apply(_mes_de) == mes_str]


def _receber_atrasado(df_enc: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """
    Pedidos com saldo pendente cuja Data de Entrega já passou — independente
    do mês em que o usuário está navegando. Nunca fica escondido.
    """
    df = _pedidos_com_saldo_pendente(df_enc)
    if df.empty or "data_entrega" not in df.columns:
        return df.iloc[0:0]
    def _venceu(v):
        d = _to_date_seguro(v)
        return d is not None and d < hoje
    return df[df["data_entrega"].apply(_venceu)]


def _despesas_abertas_do_mes(df_gastos: pd.DataFrame, mes_str: str) -> pd.DataFrame:
    """Despesas ainda não pagas com vencimento (campo 'data') no mês informado."""
    if df_gastos is None or df_gastos.empty:
        return _df_vazio_gastos()
    df = df_gastos[df_gastos["pago"].astype(int) == 0]
    if df.empty:
        return df
    return df[df["data"].fillna("").apply(_mes_de) == mes_str]


def _despesas_abertas_atrasadas(df_gastos: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """Despesas ainda não pagas cujo vencimento já passou — nunca fica escondido."""
    if df_gastos is None or df_gastos.empty:
        return _df_vazio_gastos()
    df = df_gastos[df_gastos["pago"].astype(int) == 0]
    if df.empty:
        return df
    def _venceu(v):
        d = _to_date_seguro(v)
        return d is not None and d < hoje
    return df[df["data"].apply(_venceu)]


def _status_pagamento_badge(v_recebido: float, v_total: float) -> str:
    """Selo visual de status de pagamento de um pedido — reutilizado nas listagens."""
    saldo = v_total - v_recebido
    if saldo <= 0.01:
        return '<span class="badge badge-green">✅ Quitado</span>'
    elif v_recebido > 0.01:
        return '<span class="badge badge-amber">🟡 Parcial</span>'
    else:
        return '<span class="badge badge-red">🔴 Sem pagamento</span>'


@st.dialog("💵 Recebimento Parcial")
def _dialog_recebimento_parcial(enc_id: str, cliente: str, peca: str,
                                 v_total_e: float, v_recebido: float, v_restante: float):
    """
    Popup dedicado para registrar um recebimento PARCIAL de um pedido — em
    vez do "Quitar saldo total" (que zera o saldo de uma vez), aqui o
    usuário informa exatamente quanto está entrando agora.

    A gravação usa EXATAMENTE o mesmo caminho de dados do resto do sistema
    (recebimentos_inserir + encomendas_atualizar), então tudo que lê esses
    dados — Lucro Real, Lucro Previsto, A Receber do mês, Projeção, Extrato
    do mês, Relatório Mensal — se ajusta sozinho na próxima renderização.
    Não existe cálculo paralelo nem valor duplicado: é a mesma fonte de
    verdade de sempre, só que alimentada por um popup mais direto.
    """
    st.markdown(f"**{cliente}** — {peca}")
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Valor Total", brl(v_total_e))
    col_m2.metric("Já Recebido", brl(v_recebido))
    col_m3.metric("Saldo Restante", brl(v_restante))

    st.markdown("")
    valor_parcial = st.number_input(
        "Quanto vai receber agora? (R$)",
        min_value=0.01, max_value=float(v_restante),
        value=float(v_restante), step=10.0, format="%.2f",
        key=f"parcial_val_{enc_id}",
        help="Pode ser qualquer valor até o saldo restante — o que sobrar continua pendente.",
    )
    forma_parcial = st.selectbox("Forma de pagamento", FORMAS_PAGAMENTO, key=f"parcial_forma_{enc_id}")

    saldo_depois = max(v_restante - valor_parcial, 0.0)
    st.caption(f"💡 Depois deste recebimento, o saldo pendente deste pedido passa a ser **{brl(saldo_depois)}**.")

    col_ok, col_cancel = st.columns(2)
    if col_ok.button("✅ Confirmar Recebimento", use_container_width=True, type="primary", key=f"parcial_confirmar_{enc_id}"):
        recebimentos_inserir({
            "encomenda_id": str(enc_id),
            "descricao": f"Pagamento parcial – {cliente}: {peca}",
            "valor": valor_parcial,
            "categoria": "Venda de peça",
            "data": hoje_brasilia().isoformat(),
            "forma_pagamento": forma_parcial,
            "conciliado": 0,
            "criado_em": agora_br().isoformat(),
        })
        novo_total = v_recebido + valor_parcial
        encomendas_atualizar(str(enc_id), {"valor_recebido": novo_total})
        st.success(f"✅ {brl(valor_parcial)} registrado para {cliente}! Saldo restante: {brl(saldo_depois)}.")
        st.rerun()
    if col_cancel.button("❌ Cancelar", use_container_width=True, key=f"parcial_cancelar_{enc_id}"):
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# PDF — FECHAMENTO DE CAIXA MENSAL  [v19]
# ══════════════════════════════════════════════════════════════════════════
# Segue a MESMA estrutura oficial do Relatório Mensal de Contas (S-30) /
# Folha de Contas (S-26): Saldo do Mês Anterior + Entradas − Despesas =
# Saldo Disponível no Final do Mês (sempre transportado para o mês
# seguinte). NÃO inclui a parte de "Anúncio Mensal" — isso não existe no
# contexto do Lila Closet Atelier, é um documento interno de conferência.
#
# Mesmo padrão visual do PDF de contrato (marrom/dourado, cabeçalho com
# logo), mas mais enxuto — é um relatório interno de fechamento, não um
# instrumento jurídico.

def _marrom_fin():  return colors.HexColor("#3d1f10")
def _bege_fin():    return colors.HexColor("#fdf6ee")
def _dourado_fin(): return colors.HexColor("#c9a227")


def gerar_pdf_fechamento(
    mes_str: str,
    saldo_inicial: float,
    df_r_mes: pd.DataFrame,
    df_g_mes: pd.DataFrame,
    receitas_mes: float,
    despesas_mes: float,
    lucro_real_mes: float,
    saldo_final: float,
    df_grandes: pd.DataFrame,
    total_grandes: float,
    fundos_disponiveis: float,
    saldo_extrato: float | None = None,
    diferenca: float | None = None,
    observacoes: str = "",
    fechado: bool = False,
    data_fechamento: str | None = None,
) -> bytes:
    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    mes_num, ano_num = int(mes_str[5:7]), int(mes_str[:4])
    mes_nome = MESES_PT[mes_num - 1]

    s_titulo = ParagraphStyle("titulo_fech", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=15, textColor=_marrom_fin(),
        alignment=TA_CENTER, spaceAfter=3)
    s_subtit = ParagraphStyle("subtit_fech", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8.5, textColor=_dourado_fin(),
        alignment=TA_CENTER, spaceAfter=8, leading=12)
    s_cls_tit = ParagraphStyle("clt_fech", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=10.5, textColor=_marrom_fin(),
        spaceBefore=12, spaceAfter=4, leading=13)
    s_rodape = ParagraphStyle("rodape_fech", parent=styles["Normal"],
        fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#9e8a78"),
        alignment=TA_CENTER)

    cnpj_val = cfg_get("cnpj")
    tel_val  = cfg_get("telefone")
    end_val  = cfg_get("endereco")
    emitido_em_str = agora_br().strftime("%d/%m/%Y às %H:%M")

    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=2.0*cm, leftMargin=2.0*cm,
        topMargin=2.0*cm, bottomMargin=2.0*cm)
    story = []

    # ── Cabeçalho (mesmo padrão visual do contrato) ──
    s_hdr_empresa = ParagraphStyle("hdr_emp_fech", fontName="Helvetica-Bold", fontSize=13,
        textColor=colors.white, alignment=TA_LEFT, leading=17)
    s_hdr_slogan = ParagraphStyle("hdr_slo_fech", fontName="Helvetica", fontSize=7.5,
        textColor=colors.HexColor("#f5e6d3"), alignment=TA_LEFT, leading=10, spaceBefore=2)
    s_hdr_info = ParagraphStyle("hdr_inf_fech", fontName="Helvetica", fontSize=7.5,
        textColor=colors.HexColor("#f5dfc0"), alignment=TA_RIGHT, leading=11)

    if os.path.exists(LOGO_PATH):
        logo_cell = RLImage(LOGO_PATH, width=2.1*cm, height=2.1*cm)
    else:
        logo_cell = Paragraph("🧵", ParagraphStyle("lc_fech", fontName="Helvetica-Bold",
            fontSize=24, textColor=colors.HexColor("#c9a227"), alignment=TA_CENTER))

    nome_empresa_cell = Table([
        [Paragraph("LILA CLOSET ATELIER", s_hdr_empresa)],
        [Paragraph("Fechamento de Caixa Mensal", s_hdr_slogan)],
    ], colWidths=["100%"])
    nome_empresa_cell.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),1),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))
    left_cell = Table([[logo_cell, nome_empresa_cell]], colWidths=[2.5*cm, "100%"])
    left_cell.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),0),
        ("BOTTOMPADDING",(0,0),(-1,-1),0),("LEFTPADDING",(0,0),(-1,-1),0),
        ("RIGHTPADDING",(0,0),(0,-1),8),("RIGHTPADDING",(1,0),(1,-1),0),
    ]))
    right_cell = Paragraph(f"CNPJ: {cnpj_val}<br/>{end_val}<br/>Tel.: {tel_val}", s_hdr_info)
    hdr_table = Table([[left_cell, right_cell]], colWidths=["60%","40%"])
    hdr_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),_marrom_fin()),
        ("TOPPADDING",(0,0),(-1,-1),12),("BOTTOMPADDING",(0,0),(-1,-1),12),
        ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph(f"FECHAMENTO DE CAIXA — {mes_nome.upper()} DE {ano_num}", s_titulo))
    status_txt = (
        f"🔒 Mês FECHADO em {formatar_data_hora_br(data_fechamento)}" if fechado
        else "⏳ PRÉVIA — mês ainda em conferência, valores podem mudar até o fechamento oficial"
    )
    story.append(Paragraph(f"{status_txt} &nbsp;|&nbsp; Emitido em {emitido_em_str}", s_subtit))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_dourado_fin()))
    story.append(Spacer(1, 8))

    # ── RESUMO DO MÊS (mesma estrutura oficial, sem o Anúncio) ──
    story.append(Paragraph("RESUMO DO MÊS", s_cls_tit))
    s_res_lbl = ParagraphStyle("resl_fech", fontName="Helvetica", fontSize=9.5,
        textColor=colors.HexColor("#2d1f14"))
    s_res_val = ParagraphStyle("resv_fech", fontName="Helvetica-Bold", fontSize=9.5,
        textColor=colors.HexColor("#2d1f14"), alignment=TA_RIGHT)
    s_res_val_final = ParagraphStyle("resvf_fech", fontName="Helvetica-Bold", fontSize=11,
        textColor=_marrom_fin(), alignment=TA_RIGHT)

    cor_resultado_pdf = colors.HexColor("#1b5e20") if lucro_real_mes >= 0 else colors.HexColor("#c0392b")
    label_resultado = "Saldo Positivo do Mês" if lucro_real_mes >= 0 else "Saldo Negativo do Mês"

    resumo_rows = [
        [Paragraph("Saldo do Mês Anterior", s_res_lbl), Paragraph(brl(saldo_inicial), s_res_val)],
        [Paragraph("(+) Total das Entradas", s_res_lbl),
         Paragraph(brl(receitas_mes), ParagraphStyle("rv1_fech", parent=s_res_val, textColor=colors.HexColor("#1b5e20")))],
        [Paragraph("(–) Total das Despesas", s_res_lbl),
         Paragraph(brl(despesas_mes), ParagraphStyle("rv2_fech", parent=s_res_val, textColor=colors.HexColor("#c0392b")))],
        [Paragraph(f"<b>{label_resultado}</b>", s_res_lbl),
         Paragraph(f"<b>{brl(lucro_real_mes)}</b>", ParagraphStyle("rv3_fech", parent=s_res_val, textColor=cor_resultado_pdf))],
        [Paragraph("<b>Saldo Disponível no Final do Mês</b>", s_res_lbl),
         Paragraph(f"<b>{brl(saldo_final)}</b>", s_res_val_final)],
    ]
    resumo_t = Table(resumo_rows, colWidths=["65%","35%"])
    resumo_t.setStyle(TableStyle([
        ("FONTSIZE",(0,0),(-1,-1),9.5),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("ROWBACKGROUNDS",(0,0),(-1,-2),[colors.white,_bege_fin()]),
        ("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#fff8e1")),
        ("BOX",(0,0),(-1,-1),1,_dourado_fin()),
        ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ("LINEABOVE",(0,-1),(-1,-1),1.2,_dourado_fin()),
    ]))
    story.append(resumo_t)
    story.append(Paragraph(
        "💡 O Saldo Disponível no Final do Mês é sempre transportado automaticamente "
        "como saldo inicial do mês seguinte.",
        ParagraphStyle("nota_fech", fontName="Helvetica-Oblique", fontSize=8,
            textColor=colors.HexColor("#8b7355"), spaceBefore=4),
    ))
    story.append(Spacer(1, 6))

    s_et_hdr = ParagraphStyle("eth_fech", fontName="Helvetica-Bold", fontSize=8.5,
        textColor=colors.white, alignment=TA_CENTER)

    # ── ENTRADAS DO MÊS ──
    story.append(Paragraph("ENTRADAS DO MÊS", s_cls_tit))
    if df_r_mes.empty:
        story.append(Paragraph("Nenhuma entrada registrada neste mês.", styles["Normal"]))
    else:
        rows_r = [[Paragraph("<b>Data</b>", s_et_hdr), Paragraph("<b>Descrição</b>", s_et_hdr), Paragraph("<b>Valor</b>", s_et_hdr)]]
        for _, r in df_r_mes.sort_values("data").iterrows():
            rows_r.append([formatar_data_br(r["data"]), str(r.get("descricao","")), brl(float(r.get("valor",0) or 0))])
        rows_r.append([
            "", Paragraph("<b>TOTAL</b>", ParagraphStyle("tot_fech", fontName="Helvetica-Bold", fontSize=9)),
            Paragraph(f"<b>{brl(receitas_mes)}</b>", ParagraphStyle("totv_fech", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#1b5e20"))),
        ])
        t_r = Table(rows_r, colWidths=["18%","57%","25%"])
        t_r.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),_marrom_fin()),
            ("FONTSIZE",(0,1),(-1,-1),8.5),
            ("ALIGN",(2,1),(2,-1),"RIGHT"),
            ("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.white,_bege_fin()]),
            ("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#fff8e1")),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("BOX",(0,0),(-1,-1),1,_dourado_fin()),
            ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ]))
        story.append(t_r)
    story.append(Spacer(1, 8))

    # ── DESPESAS DO MÊS ──
    story.append(Paragraph("DESPESAS DO MÊS", s_cls_tit))
    if df_g_mes.empty:
        story.append(Paragraph("Nenhuma despesa paga registrada neste mês.", styles["Normal"]))
    else:
        rows_g = [[Paragraph("<b>Data</b>", s_et_hdr), Paragraph("<b>Descrição</b>", s_et_hdr),
                   Paragraph("<b>Categoria</b>", s_et_hdr), Paragraph("<b>Valor</b>", s_et_hdr)]]
        for _, g in df_g_mes.sort_values("data").iterrows():
            rows_g.append([formatar_data_br(g["data"]), str(g.get("descricao","")),
                            str(g.get("categoria","")), brl(float(g.get("valor",0) or 0))])
        rows_g.append([
            "", "", Paragraph("<b>TOTAL</b>", ParagraphStyle("tot2_fech", fontName="Helvetica-Bold", fontSize=9)),
            Paragraph(f"<b>{brl(despesas_mes)}</b>", ParagraphStyle("totv2_fech", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#c0392b"))),
        ])
        t_g = Table(rows_g, colWidths=["15%","42%","20%","23%"])
        t_g.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),_marrom_fin()),
            ("FONTSIZE",(0,1),(-1,-1),8.5),
            ("ALIGN",(3,1),(3,-1),"RIGHT"),
            ("ROWBACKGROUNDS",(0,1),(-1,-2),[colors.white,_bege_fin()]),
            ("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#fff8e1")),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("BOX",(0,0),(-1,-1),1,_dourado_fin()),
            ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ]))
        story.append(t_g)
    story.append(Spacer(1, 8))

    # ── GRANDES DESPESAS PREVISTAS (se houver) ──
    if not df_grandes.empty:
        story.append(Paragraph("GRANDES DESPESAS PREVISTAS (RESERVADAS)", s_cls_tit))
        rows_gd = [[Paragraph("<b>Data Prevista</b>", s_et_hdr), Paragraph("<b>Descrição</b>", s_et_hdr), Paragraph("<b>Valor</b>", s_et_hdr)]]
        for _, gd in df_grandes.sort_values("data").iterrows():
            rows_gd.append([formatar_data_br(gd["data"]), str(gd.get("descricao","")), brl(float(gd.get("valor",0) or 0))])
        t_gd = Table(rows_gd, colWidths=["18%","57%","25%"])
        t_gd.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),_marrom_fin()),
            ("FONTSIZE",(0,1),(-1,-1),8.5),
            ("ALIGN",(2,1),(2,-1),"RIGHT"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,_bege_fin()]),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("BOX",(0,0),(-1,-1),1,_dourado_fin()),
            ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ]))
        story.append(t_gd)
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"Total reservado: <b>{brl(total_grandes)}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Fundos realmente disponíveis (Saldo Final − Reservado): <b>{brl(fundos_disponiveis)}</b>",
            ParagraphStyle("gdtot_fech", fontName="Helvetica", fontSize=9.5),
        ))
        story.append(Spacer(1, 8))

    # ── CONFRONTO COM O EXTRATO BANCÁRIO (se informado) ──
    if saldo_extrato is not None:
        story.append(Paragraph("CONFRONTO COM O EXTRATO BANCÁRIO", s_cls_tit))
        bateu = diferenca is not None and abs(diferenca) < 0.01
        conf_rows = [
            [Paragraph("Saldo calculado pelo sistema", s_res_lbl), Paragraph(brl(saldo_final), s_res_val)],
            [Paragraph("Saldo informado no extrato bancário", s_res_lbl), Paragraph(brl(saldo_extrato), s_res_val)],
            [Paragraph("<b>Diferença</b>", s_res_lbl), Paragraph(
                f"<b>{brl(diferenca)}</b>" if diferenca is not None else "—",
                ParagraphStyle("diff_fech", parent=s_res_val,
                    textColor=(colors.HexColor("#1b5e20") if bateu else colors.HexColor("#c0392b"))),
            )],
        ]
        conf_t = Table(conf_rows, colWidths=["65%","35%"])
        conf_t.setStyle(TableStyle([
            ("FONTSIZE",(0,0),(-1,-1),9.5),
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white,_bege_fin()]),
            ("BOX",(0,0),(-1,-1),1,_dourado_fin()),
            ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ]))
        story.append(conf_t)
        nota_conf = ("✅ Confronto bateu certinho com o extrato bancário." if bateu else
                     "⚠️ Há diferença entre o sistema e o extrato — revisar lançamentos.")
        story.append(Paragraph(nota_conf, ParagraphStyle("notaconf_fech", fontName="Helvetica-Oblique",
            fontSize=8, textColor=colors.HexColor("#8b7355"), spaceBefore=4)))
        story.append(Spacer(1, 8))

    # ── OBSERVAÇÕES ──
    if observacoes and observacoes.strip():
        story.append(Paragraph("OBSERVAÇÕES", s_cls_tit))
        story.append(Paragraph(observacoes.strip(), ParagraphStyle("obsbody_fech", fontName="Helvetica",
            fontSize=9.5, textColor=colors.HexColor("#2d1f14"), leading=14)))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e0d5c9")))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"Lila Closet Atelier · {tel_val} · Fechamento de {mes_nome}/{ano_num} · "
        f"Documento gerado automaticamente pelo sistema",
        s_rodape,
    ))

    doc.build(story)
    return buf.getvalue()


def renderizar_financeiro(df_enc_all: pd.DataFrame, hoje_dt):
    """Renderiza o BLOCO FINANCEIRO completo."""
    st.markdown("### 💰 Controle Financeiro Profissional")

    df_enc_fin = df_enc_all
    df_g_fin   = gastos_listar()
    df_r_fin   = recebimentos_listar()
    df_f_fin   = fechamentos_listar()

    # ── Garantia defensiva de colunas ────────────────────────────────────
    # O Firestore só cria uma coluna no DataFrame quando PELO MENOS UM
    # documento tem aquele campo preenchido. Preenchemos valores padrão
    # para colunas opcionais, evitando KeyError.
    if not df_g_fin.empty:
        for _col, _default in [
            ("conciliado", 0), ("pago", 0), ("recorrente", 0),
            ("grande_despesa_prevista", 0), ("encomenda_id", None),
        ]:
            if _col not in df_g_fin.columns:
                df_g_fin[_col] = _default
    if not df_r_fin.empty:
        for _col, _default in [("conciliado", 0), ("encomenda_id", None)]:
            if _col not in df_r_fin.columns:
                df_r_fin[_col] = _default

    mes_atual_str = f"{hoje_dt.year}-{hoje_dt.month:02d}"

    # ── Números REAIS (histórico já acontecido) ──────────────────────────
    receita_total = _flt(df_r_fin, "valor")
    gastos_pagos  = float(df_g_fin[df_g_fin["pago"].astype(int) == 1]["valor"].fillna(0).astype(float).sum()) if not df_g_fin.empty else 0.0
    lucro_real    = receita_total - gastos_pagos

    saldo_caixa_atual, mes_corte_fech, saldo_herdado = _saldo_em_caixa(df_r_fin, df_g_fin, df_f_fin)

    # ── Números de PREVISÃO (o que ainda vai entrar/sair, lido da agenda) ─
    df_receber_mes_atual = _receber_do_mes(df_enc_fin, mes_atual_str)
    receber_mes_atual = float(df_receber_mes_atual["_saldo_pendente"].sum()) if not df_receber_mes_atual.empty else 0.0

    # [v15] Lucro Previsto (mês) = Lucro Real (histórico, já recebido/pago)
    # + apenas o SALDO que ainda falta receber (valor_total - valor_recebido)
    # de pedidos com Data de Entrega dentro do mês atual. Nunca soma o valor
    # bruto do pedido, e pedidos com entrega em outro mês não entram aqui —
    # eles só vão entrar nesta conta no mês em que a entrega deles acontecer.
    lucro_previsto_mes = lucro_real + receber_mes_atual

    df_receber_atrasado_top = _receber_atrasado(df_enc_fin, hoje_dt)
    receber_atrasado_top = float(df_receber_atrasado_top["_saldo_pendente"].sum()) if not df_receber_atrasado_top.empty else 0.0

    df_pagar_mes_atual = _despesas_abertas_do_mes(df_g_fin, mes_atual_str)
    pagar_mes_atual = _flt(df_pagar_mes_atual, "valor")

    df_pagar_atrasado_top = _despesas_abertas_atrasadas(df_g_fin, hoje_dt)
    pagar_atrasado_top = _flt(df_pagar_atrasado_top, "valor")

    lucro_projetado_mes = receber_mes_atual - pagar_mes_atual
    saldo_projetado_mes = saldo_caixa_atual + lucro_projetado_mes

    df_receber_total_geral = _pedidos_com_saldo_pendente(df_enc_fin)
    receber_total_geral = float(df_receber_total_geral["_saldo_pendente"].sum()) if not df_receber_total_geral.empty else 0.0

    df_gastos_abertos_total = df_g_fin[df_g_fin["pago"].astype(int) == 0] if not df_g_fin.empty else pd.DataFrame()
    gastos_previstos_total = _flt(df_gastos_abertos_total, "valor")

    pct_reserva   = int(cfg_get("reserva_emergencia_meses") or 3)
    pct_capital   = float(cfg_get("capital_giro_pct") or 20) / 100
    margem_min    = float(cfg_get("margem_minima_pct") or 30) / 100
    meta_fat_fin  = float(cfg_get("meta_faturamento") or 5000)

    reserva_sugerida = gastos_pagos * pct_reserva / 12 if gastos_pagos > 0 else gastos_previstos_total * pct_reserva
    capital_giro_sug = receita_total * pct_capital
    teto_gasto_mens  = (receita_total + receber_total_geral) * (1 - margem_min) if (receita_total + receber_total_geral) > 0 else 0

    # ── [v16] Visão Geral (Saldo, Alertas, KPIs, Capital/Reserva/Teto) ────
    # Fica OCULTA por padrão dentro de um expander recolhido — os cálculos
    # continuam acontecendo normalmente (as abas dependem deles), só a
    # EXIBIÇÃO deste bloco é que fica escondida até o usuário clicar para
    # expandir. Nada foi removido, só recolhido.
    with st.expander("📊 Visão Geral (Saldo, KPIs e Indicadores)", expanded=False):
        # ── KPI de topo: Saldo em Caixa Atual ─────────────────────────────
        col_sc, col_sc2 = st.columns([2, 3])
        with col_sc:
            st.markdown(f"""
            <div class="kcard" style="border:2px solid #3d1f10;">
              <div class="kcard-title" style="font-size:1.6rem;">💵 {brl(saldo_caixa_atual)}</div>
              <div class="kcard-sub">Saldo em Caixa Atual
                {f"(herdado do fechamento de {mes_corte_fech})" if mes_corte_fech else "(nenhum mês fechado ainda — considerando todo o histórico)"}
              </div>
            </div>""", unsafe_allow_html=True)
        with col_sc2:
            if not mes_corte_fech:
                st.markdown('<div class="fin-alerta">📌 Você ainda não fez nenhum fechamento de caixa. Vá até a aba "🔒 Fechamento &amp; Conciliação" e feche o primeiro mês para começar a ter um saldo confiável de arrastar entre os meses.</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="fin-ok">✅ Último mês fechado: <b>{mes_corte_fech}</b>, com saldo final de <b>{brl(saldo_herdado)}</b>. Tudo lançado depois disso já está somado ao saldo acima.</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Alerta de atrasados — resumo (detalhe + baixa ficam na aba Projeção) ──
        if receber_atrasado_top > 0.01 or pagar_atrasado_top > 0.01:
            col_al1, col_al2 = st.columns(2)
            if receber_atrasado_top > 0.01:
                col_al1.markdown(
                    f'<div class="fin-danger">🔴 <b>{brl(receber_atrasado_top)}</b> em atraso para receber '
                    f'({len(df_receber_atrasado_top)} pedido(s) com entrega já vencida e saldo pendente). '
                    f'Veja detalhes e dê baixa na aba 📈 Projeção.</div>',
                    unsafe_allow_html=True,
                )
            else:
                col_al1.markdown('<div class="fin-ok">✅ Nenhum recebimento atrasado.</div>', unsafe_allow_html=True)
            if pagar_atrasado_top > 0.01:
                col_al2.markdown(
                    f'<div class="fin-danger">🔴 <b>{brl(pagar_atrasado_top)}</b> em despesas vencidas e não pagas '
                    f'({len(df_pagar_atrasado_top)} lançamento(s)). Veja detalhes e dê baixa na aba 📈 Projeção.</div>',
                    unsafe_allow_html=True,
                )
            else:
                col_al2.markdown('<div class="fin-ok">✅ Nenhuma despesa vencida em aberto.</div>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        col_f1, col_f2, col_f3 = st.columns(3)
        col_f1.metric("💰 Receita Recebida (histórico)", brl(receita_total))
        col_f2.metric("📉 Gastos Pagos (histórico)",     brl(gastos_pagos))
        col_f3.metric("✅ Lucro Real (histórico)",        brl(lucro_real),
                      delta=f"{pct_str(lucro_real, receita_total)} de margem" if receita_total > 0 else "")

        col_f4, col_f5, col_f6, col_f7 = st.columns(4)
        col_f4.metric(
            "🔮 Lucro Previsto (mês)", brl(lucro_previsto_mes),
            help="Lucro Real (histórico) + apenas o saldo que ainda falta receber "
                 "(valor_total − valor_recebido) de pedidos com Data de Entrega "
                 "neste mês. Um pedido com entrega daqui a 3 meses NÃO entra aqui "
                 "— ele só vai aparecer nesta conta no mês em que a entrega dele acontecer.",
        )
        col_f5.metric("📥 A Receber (mês atual)", brl(receber_mes_atual),
                      help="Saldo pendente (valor_total - valor_recebido) de pedidos com Data de Entrega neste mês. Muda sozinho se você reagendar a entrega.")
        col_f6.metric("📤 A Pagar (mês atual)", brl(pagar_mes_atual),
                      help="Despesas em aberto com vencimento neste mês.")
        col_f7.metric("🔮 Saldo Projetado (fim do mês)", brl(saldo_projetado_mes),
                      help="Saldo em Caixa Atual + (A Receber do mês − A Pagar do mês). Não inclui atrasados de meses anteriores — veja o alerta acima.")

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
    f_receb_despe, f_proj, f_fecha = st.tabs([
        "📑 Receb. / Despe.", "📈 Projeção", "🔒 Fechamento & Conciliação",
    ])

    # ═══════════════════════════════════════════════════════════════════
    # ABA: PROJEÇÃO
    # ═══════════════════════════════════════════════════════════════════
    with f_proj:
        st.markdown("#### 📈 Projeção de Fechamento do Mês")
        st.caption(
            "Parte do Saldo em Caixa Atual (real, conferido) e soma o que ainda falta receber "
            "e pagar dentro do mês escolhido, com base na Data de Entrega dos pedidos e no "
            "vencimento das despesas em aberto. Se você mudar a Data de Entrega de um pedido "
            "na Agenda, esta projeção se ajusta sozinha — ela sempre lê a agenda atual, nunca "
            "um valor travado."
        )

        mes_seguinte_str_proj = _mes_seguinte(mes_atual_str)
        opcoes_mes_proj = [mes_atual_str, mes_seguinte_str_proj, _mes_seguinte(mes_seguinte_str_proj)]
        labels_mes_proj = {
            mes_atual_str: f"Mês atual ({MESES_PT[int(mes_atual_str[5:7])-1]}/{mes_atual_str[:4]})",
            mes_seguinte_str_proj: f"Mês seguinte ({MESES_PT[int(mes_seguinte_str_proj[5:7])-1]}/{mes_seguinte_str_proj[:4]})",
            opcoes_mes_proj[2]: f"Depois ({MESES_PT[int(opcoes_mes_proj[2][5:7])-1]}/{opcoes_mes_proj[2][:4]})",
        }
        mes_proj_sel = st.selectbox(
            "Ver projeção de qual mês?", opcoes_mes_proj,
            format_func=lambda m: labels_mes_proj[m], index=0,
        )

        df_receber_proj = _receber_do_mes(df_enc_fin, mes_proj_sel)
        rec_prevista_proj = float(df_receber_proj["_saldo_pendente"].sum()) if not df_receber_proj.empty else 0.0

        df_pagar_proj = _despesas_abertas_do_mes(df_g_fin, mes_proj_sel)
        desp_prevista_proj = _flt(df_pagar_proj, "valor")

        lucro_projetado = rec_prevista_proj - desp_prevista_proj

        # ── Projeção ENCADEADA: para meses futuros, soma o resultado
        #    projetado de cada mês intermediário (mês atual até o mês
        #    anterior ao escolhido) antes de aplicar o lucro do mês
        #    escolhido — não pula direto pro mês final ignorando o meio.
        saldo_base_proj = saldo_caixa_atual
        cursor_mes = mes_atual_str
        while cursor_mes != mes_proj_sel:
            df_r_cursor = _receber_do_mes(df_enc_fin, cursor_mes)
            df_g_cursor = _despesas_abertas_do_mes(df_g_fin, cursor_mes)
            saldo_base_proj += float(df_r_cursor["_saldo_pendente"].sum()) if not df_r_cursor.empty else 0.0
            saldo_base_proj -= _flt(df_g_cursor, "valor")
            cursor_mes = _mes_seguinte(cursor_mes)

        saldo_projetado_fim_mes = saldo_base_proj + lucro_projetado

        col_p1, col_p2, col_p3, col_p4 = st.columns(4)
        col_p1.metric("📥 A receber no mês", brl(rec_prevista_proj))
        col_p2.metric("📤 A pagar no mês", brl(desp_prevista_proj))
        col_p3.metric("🔮 Lucro Projetado", brl(lucro_projetado))
        col_p4.metric("💵 Saldo projetado ao fim do mês", brl(saldo_projetado_fim_mes))

        if mes_proj_sel != mes_atual_str:
            st.caption(
                "💡 Como este é um mês futuro, o saldo acima já passou pelo resultado projetado "
                "de cada mês intermediário (não é só o Saldo Atual + este mês isolado)."
            )
        st.caption(
            "Esta projeção NÃO inclui os atrasados listados na seção abaixo — eles são dinheiro "
            "que já deveria ter entrado/saído e continua em aberto, então ficam destacados à parte "
            "para você não perder de vista."
        )

        st.markdown("---")
        col_pp1, col_pp2 = st.columns(2)
        with col_pp1:
            st.markdown(f"**Pedidos com entrega em {labels_mes_proj[mes_proj_sel]}**")
            if df_receber_proj.empty:
                st.info("Nenhum pedido com saldo pendente e entrega prevista neste mês.")
            else:
                df_pp = df_receber_proj[["cliente", "peca", "_saldo_pendente", "data_entrega"]].copy()
                df_pp.columns = ["Cliente", "Peça", "A Receber", "Entrega"]
                df_pp["Entrega"] = df_pp["Entrega"].apply(formatar_data_br)
                df_pp["A Receber"] = df_pp["A Receber"].apply(lambda x: brl(float(x)))
                st.dataframe(df_pp, use_container_width=True, hide_index=True)
        with col_pp2:
            st.markdown(f"**Despesas em aberto vencendo em {labels_mes_proj[mes_proj_sel]}**")
            if df_pagar_proj.empty:
                st.info("Nenhuma despesa em aberto com vencimento neste mês.")
            else:
                df_gp = df_pagar_proj[["descricao", "categoria", "valor"]].copy()
                df_gp.columns = ["Descrição", "Categoria", "Valor"]
                df_gp["Valor"] = df_gp["Valor"].apply(lambda x: brl(float(x)))
                st.dataframe(df_gp, use_container_width=True, hide_index=True)

        # ── Atrasados — SEMPRE mostrados, independente do mês selecionado ──
        st.markdown("---")
        st.markdown("##### ⚠️ Pendências em atraso (fora do cálculo acima — não somem daqui)")
        st.caption(
            "💡 O que não for baixado aqui continua aparecendo automaticamente nos "
            "meses seguintes, sempre no topo desta lista — nada se perde, e nada "
            "precisa ser 'transportado' manualmente."
        )
        df_receber_atr = _receber_atrasado(df_enc_fin, hoje_dt)
        df_pagar_atr = _despesas_abertas_atrasadas(df_g_fin, hoje_dt)

        col_atr1, col_atr2 = st.columns(2)
        with col_atr1:
            if df_receber_atr.empty:
                st.success("✅ Nenhum recebimento atrasado.")
            else:
                total_atr_receber = float(df_receber_atr["_saldo_pendente"].sum())
                st.markdown(
                    f'<div class="fin-danger">🔴 {len(df_receber_atr)} pedido(s) com entrega já '
                    f'vencida e saldo pendente — total de {brl(total_atr_receber)}.</div>',
                    unsafe_allow_html=True,
                )
                for _, r_atr in df_receber_atr.sort_values("data_entrega").iterrows():
                    saldo_r = float(r_atr["_saldo_pendente"])
                    col_ra1, col_ra2 = st.columns([3, 1.3])
                    col_ra1.markdown(
                        f"**{r_atr['cliente']}** — {r_atr['peca']}<br>"
                        f"<span style='font-size:0.78rem;color:#8b7355;'>"
                        f"Entrega: {formatar_data_br(r_atr['data_entrega'])} &nbsp;·&nbsp; "
                        f"Em atraso: {brl(saldo_r)}</span>",
                        unsafe_allow_html=True,
                    )
                    with col_ra2:
                        st.write("")
                        if st.button("💰 Dar baixa", key=f"baixa_receber_atr_{r_atr['rowid']}", use_container_width=True):
                            recebimentos_inserir({
                                "encomenda_id": str(r_atr["rowid"]),
                                "descricao": f"Quitação (atraso) – {r_atr['cliente']}: {r_atr['peca']}",
                                "valor": saldo_r,
                                "categoria": "Venda de peça",
                                "data": hoje_brasilia().isoformat(),
                                "forma_pagamento": "Pix",
                                "conciliado": 0,
                                "criado_em": agora_br().isoformat(),
                            })
                            encomendas_atualizar(str(r_atr["rowid"]), {
                                "valor_recebido": float(r_atr.get("valor_total", 0) or 0)
                            })
                            st.success(f"✅ Pagamento de {r_atr['cliente']} baixado!")
                            st.rerun()
        with col_atr2:
            if df_pagar_atr.empty:
                st.success("✅ Nenhuma despesa vencida em aberto.")
            else:
                total_atr_pagar = _flt(df_pagar_atr, "valor")
                st.markdown(
                    f'<div class="fin-danger">🔴 {len(df_pagar_atr)} despesa(s) vencida(s) e não '
                    f'pagas — total de {brl(total_atr_pagar)}.</div>',
                    unsafe_allow_html=True,
                )
                for _, g_atr in df_pagar_atr.sort_values("data").iterrows():
                    col_pa1, col_pa2 = st.columns([3, 1.3])
                    col_pa1.markdown(
                        f"**{g_atr['descricao']}** <span style='font-size:0.78rem;color:#8b7355;'>({g_atr['categoria']})</span><br>"
                        f"<span style='font-size:0.78rem;color:#8b7355;'>"
                        f"Vencimento: {formatar_data_br(g_atr['data'])} &nbsp;·&nbsp; "
                        f"Valor: {brl(float(g_atr['valor']))}</span>",
                        unsafe_allow_html=True,
                    )
                    with col_pa2:
                        st.write("")
                        if st.button("✅ Dar baixa", key=f"baixa_pagar_atr_{g_atr['rowid']}", use_container_width=True):
                            gastos_atualizar(str(g_atr["rowid"]), {"pago": 1})
                            st.success(f"✅ Despesa '{g_atr['descricao']}' baixada!")
                            st.rerun()

    # ═══════════════════════════════════════════════════════════════════
    # ABA: RECEB. / DESPE.  (pedidos com saldo pendente + lançamentos avulsos
    # + extrato editável do mês — tudo centralizado numa única aba)
    # ═══════════════════════════════════════════════════════════════════
    with f_receb_despe:
        st.caption(
            "Lance entradas/saídas avulsas rapidamente aqui em cima, veja o relatório do mês "
            "logo abaixo, e os pedidos com saldo pendente ficam recolhidos mais embaixo. "
            "Para editar, excluir ou conciliar um lançamento já existente, vá na aba "
            "🔒 **Fechamento & Conciliação**."
        )

        st.markdown("##### ➕ Novo Lançamento")
        st.caption("Entradas/saídas avulsas. Saídas podem ser vinculadas a um pedido, para entrar no cálculo de Custo Direto/Margem daquele pedido.")

        df_pedidos_nl = encomendas_listar(cancelado=False)
        opcoes_pedido_nl = ["— Nenhum (lançamento avulso) —"]
        mapa_pedido_nl = {}
        if not df_pedidos_nl.empty and "cliente" in df_pedidos_nl.columns:
            df_pedidos_nl_ord = df_pedidos_nl.sort_values("cliente", key=lambda s: s.str.lower())
            for _, p in df_pedidos_nl_ord.iterrows():
                label_p = f"{p['cliente']} – {p['peca']}"
                opcoes_pedido_nl.append(label_p)
                mapa_pedido_nl[label_p] = p["rowid"]

        with st.form("form_novo_lanc_rd", clear_on_submit=True):
            col_nl1, col_nl2, col_nl3 = st.columns([3, 2, 2])
            nl_desc = col_nl1.text_input("Descrição *", placeholder="Ex: Sinal do vestido da Ana")
            nl_val  = col_nl2.number_input("Valor (R$) *", min_value=0.01, step=10.0, format="%.2f")
            nl_tipo = col_nl3.selectbox("Tipo", ["💰 Entrada", "📉 Saída"])
            nl_data = st.date_input("Data", hoje_brasilia(), format="DD/MM/YYYY", key="nl_data_rd")

            nl_pedido_label = st.selectbox(
                "Vincular esta Saída a um pedido? (opcional)",
                opcoes_pedido_nl, key="nl_pedido_rd",
                help="Só vale para Saídas (gastos) — é isso que alimenta o Custo Direto e a "
                     "Margem de cada pedido, na seção 'Pedidos com Saldo Pendente' abaixo. "
                     "Uma Entrada vinculada a um pedido não é contada aqui — use os botões "
                     "'Recebimento Parcial' / 'Quitar saldo total' do próprio pedido para isso.",
            )

            if st.form_submit_button("💾 Lançar", use_container_width=True, type="primary"):
                if nl_desc.strip() and nl_val > 0:
                    enc_id_vinculado = mapa_pedido_nl.get(nl_pedido_label)
                    if nl_tipo.startswith("💰"):
                        recebimentos_inserir({
                            "encomenda_id": None,
                            "descricao": nl_desc.strip(),
                            "valor": nl_val,
                            "categoria": "Outro",
                            "data": nl_data.isoformat(),
                            "forma_pagamento": "",
                            "conciliado": 0,
                            "criado_em": agora_br().isoformat(),
                        })
                        st.success("✅ Entrada lançada!")
                    else:
                        gastos_inserir({
                            "encomenda_id": enc_id_vinculado,
                            "descricao": nl_desc.strip(), "valor": nl_val,
                            "data": nl_data.isoformat(), "categoria": "Outro",
                            "pago": 1, "recorrente": 0,
                            "grande_despesa_prevista": 0,
                            "conciliado": 0,
                            "criado_em": agora_br().isoformat(),
                        })
                        if enc_id_vinculado:
                            st.success(f"✅ Saída lançada e vinculada a **{nl_pedido_label}**!")
                        else:
                            st.success("✅ Saída lançada!")
                    st.rerun()
                else:
                    st.error("Preencha descrição e valor.")

        st.markdown("<br>", unsafe_allow_html=True)

        # ── [v18] Relatório Financeiro Mensal — movido para cá (a antiga aba
        # "📋 Relatório Mensal" foi eliminada; este é exatamente o mesmo
        # conteúdo, só que agora logo abaixo do Novo Lançamento). ─────────
        st.markdown("---")
        st.markdown("#### 📋 Relatório Financeiro Mensal")
        st.caption("Mostra o que já REALMENTE aconteceu no mês (lançamentos com data dentro dele) — não é uma projeção.")
        col_rm1, col_rm2 = st.columns(2)
        mes_sel_fin = col_rm1.selectbox("Mês", list(range(1,13)),
            format_func=lambda x: MESES_PT[x-1], index=hoje_dt.month-1, key="mes_rel_fin")
        ano_sel_fin = col_rm2.number_input("Ano", min_value=2020, max_value=2030, value=hoje_dt.year, key="ano_rel_fin")

        mes_str_rel = f"{ano_sel_fin}-{mes_sel_fin:02d}"

        df_r_mes_rel = df_r_fin[df_r_fin["data"].apply(_mes_de) == mes_str_rel].copy() if not df_r_fin.empty else _df_vazio_receb()
        df_g_mes_rel = df_g_fin[df_g_fin["data"].apply(_mes_de) == mes_str_rel].copy() if not df_g_fin.empty else _df_vazio_gastos()

        rec_mes   = _flt(df_r_mes_rel, "valor")
        gasto_mes = float(df_g_mes_rel[df_g_mes_rel["pago"].astype(int) == 1]["valor"].fillna(0).astype(float).sum()) if not df_g_mes_rel.empty else 0.0
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
            st.markdown("**Entradas do mês**")
            if df_r_mes_rel.empty:
                st.info("Nenhuma entrada neste mês.")
            else:
                df_em = df_r_mes_rel[["data","descricao","categoria","valor","forma_pagamento"]].copy()
                df_em.columns = ["Data","Descrição","Categoria","Valor","Forma"]
                df_em["Data"] = df_em["Data"].apply(formatar_data_br)
                df_em["Valor"] = df_em["Valor"].apply(lambda x: brl(float(x)))
                st.dataframe(df_em, use_container_width=True, hide_index=True)

        with col_rt2:
            st.markdown("**Gastos do mês**")
            if df_g_mes_rel.empty:
                st.info("Nenhum gasto registrado neste mês.")
            else:
                df_gm = df_g_mes_rel[["data","descricao","categoria","valor","pago"]].copy()
                df_gm.columns = ["Data","Descrição","Categoria","Valor","Pago?"]
                df_gm["Data"] = df_gm["Data"].apply(formatar_data_br)
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

            ws1 = wb.add_worksheet("Entradas")
            for ci, h in enumerate(["Descrição","Categoria","Valor","Forma","Data"]):
                ws1.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_r_mes_rel.iterrows(), 1):
                ws1.write(ri, 0, row.get("descricao",""), fmt_n)
                ws1.write(ri, 1, row.get("categoria",""), fmt_n)
                ws1.write(ri, 2, float(row.get("valor",0) or 0), fmt_brl)
                ws1.write(ri, 3, row.get("forma_pagamento",""), fmt_n)
                ws1.write(ri, 4, str(row.get("data","")), fmt_n)

            ws2 = wb.add_worksheet("Gastos")
            for ci, h in enumerate(["Data","Descrição","Categoria","Valor","Pago?"]):
                ws2.write(0, ci, h, fmt_h)
            for ri, (_, row) in enumerate(df_g_mes_rel.iterrows(), 1):
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

        st.markdown("<br>", unsafe_allow_html=True)

        # ── [v17] "Recebimentos e Despesas" (pedidos com saldo pendente) fica
        # OCULTO por padrão dentro de um expander recolhido — mesmo padrão já
        # usado na "Visão Geral" do topo. Nada foi removido, só recolhido.
        with st.expander("📑 Recebimentos e Despesas (Pedidos com Saldo Pendente)", expanded=False):
            st.markdown("##### 💳 Pedidos com Saldo Pendente")
            if df_enc_fin.empty:
                st.info("Nenhum pedido cadastrado.")
            else:
                filtro_pag = st.radio(
                    "Mostrar:", ["Com saldo pendente", "Quitados", "Todos"],
                    horizontal=True, key="filtro_pagto_pedido",
                )
                df_pag_view = df_enc_fin.copy()
                df_pag_view["_saldo_pendente"] = (
                    df_pag_view["valor_total"].fillna(0).astype(float)
                    - df_pag_view["valor_recebido"].fillna(0).astype(float)
                ).clip(lower=0)

                if filtro_pag == "Com saldo pendente":
                    df_pag_view = df_pag_view[df_pag_view["_saldo_pendente"] > 0.01]
                elif filtro_pag == "Quitados":
                    df_pag_view = df_pag_view[df_pag_view["_saldo_pendente"] <= 0.01]

                df_pag_view = df_pag_view.sort_values("cliente", key=lambda s: s.str.lower())

                if df_pag_view.empty:
                    st.info("Nenhum pedido nesse filtro.")
                else:
                    for _, enc in df_pag_view.iterrows():
                        v_total_e  = float(enc.get("valor_total", 0) or 0)
                        v_recebido = float(enc.get("valor_recebido", 0) or 0)
                        v_restante = max(v_total_e - v_recebido, 0.0)

                        gasto_enc = 0.0
                        if not df_g_fin.empty and "encomenda_id" in df_g_fin.columns:
                            gasto_enc = float(df_g_fin[df_g_fin["encomenda_id"] == enc["rowid"]]["valor"].fillna(0).astype(float).sum())
                        lucro_enc  = v_recebido - gasto_enc
                        margem_enc = lucro_enc / v_recebido * 100 if v_recebido > 0 else 0
                        margem_min_val = float(cfg_get("margem_minima_pct") or 30)

                        badge_html = _status_pagamento_badge(v_recebido, v_total_e)

                        with st.expander(
                            f"👗 {enc['cliente']} – {enc['peca']}  |  "
                            f"Recebido: {brl(v_recebido)} / {brl(v_total_e)}  |  Margem: {margem_enc:.0f}%"
                        ):
                            st.markdown(badge_html, unsafe_allow_html=True)
                            col_pm1, col_pm2, col_pm3, col_pm4 = st.columns(4)
                            col_pm1.metric("Valor Total",  brl(v_total_e))
                            col_pm2.metric("Recebido",     brl(v_recebido))
                            col_pm3.metric("A Receber",    brl(v_restante))
                            col_pm4.metric("Custo Direto", brl(gasto_enc))

                            if margem_enc >= margem_min_val:
                                st.markdown(f'<div class="fin-ok">✅ Margem de <b>{margem_enc:.1f}%</b> — saudável.</div>', unsafe_allow_html=True)
                            else:
                                st.markdown(f'<div class="fin-danger">🚨 Margem de <b>{margem_enc:.1f}%</b> abaixo do mínimo ({margem_min_val:.0f}%).</div>', unsafe_allow_html=True)

                            if v_restante > 0.01:
                                col_rec1, col_rec2 = st.columns(2)
                                if col_rec1.button("💵 Recebimento Parcial", key=f"parcial_btn_{enc['rowid']}", use_container_width=True):
                                    _dialog_recebimento_parcial(
                                        enc_id=str(enc["rowid"]), cliente=enc["cliente"], peca=enc["peca"],
                                        v_total_e=v_total_e, v_recebido=v_recebido, v_restante=v_restante,
                                    )

                                if col_rec2.button(f"💰 Quitar saldo total ({brl(v_restante)})", key=f"quit_total_{enc['rowid']}", use_container_width=True):
                                    recebimentos_inserir({
                                        "encomenda_id": str(enc["rowid"]),
                                        "descricao": f"Quitação – {enc['cliente']}: {enc['peca']}",
                                        "valor": v_restante,
                                        "categoria": "Venda de peça",
                                        "data": hoje_brasilia().isoformat(),
                                        "forma_pagamento": "Pix",
                                        "conciliado": 0,
                                        "criado_em": agora_br().isoformat(),
                                    })
                                    encomendas_atualizar(str(enc["rowid"]), {"valor_recebido": v_total_e})
                                    st.success(f"✅ Pedido de {enc['cliente']} quitado!")
                                    st.rerun()
                            else:
                                st.markdown('<div class="fin-ok">✅ Pedido totalmente pago.</div>', unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════════
    # ABA: FECHAMENTO & CONCILIAÇÃO  [v19 — reorganizada]
    # Ordem: (1) Resumo do Fechamento (estrutura oficial, bem claro) →
    #        (2) Extrato do mês (conferência lançamento por lançamento) →
    #        (3) Grandes despesas previstas → (4) Progresso da conferência →
    #        (5) Confronto bancário → (6) Fechar/Reabrir mês →
    #        (7) Exportações (PDF + Excel) → (8) Histórico
    # ═══════════════════════════════════════════════════════════════════
    with f_fecha:
        st.markdown("#### 🔒 Fechamento de Caixa & Conciliação Bancária")
        st.caption("Confira, mês a mês, se tudo que está no sistema bate com o extrato do banco — e trave o saldo do mês pra ele virar automaticamente o saldo inicial do mês seguinte.")

        col_fm1, col_fm2 = st.columns(2)
        mes_sel = col_fm1.selectbox("Mês", list(range(1, 13)),
            format_func=lambda x: MESES_PT[x-1], index=hoje_dt.month-1, key="mes_fechamento")
        ano_sel = col_fm2.number_input("Ano", min_value=2020, max_value=2030, value=hoje_dt.year, key="ano_fechamento")
        mes_str = f"{ano_sel}-{mes_sel:02d}"
        mes_seguinte_label = f"{MESES_PT[int(_mes_seguinte(mes_str)[5:7])-1]}/{_mes_seguinte(mes_str)[:4]}"

        fech_existente = fechamento_buscar(mes_str)
        ja_fechado = bool(fech_existente and int(fech_existente.get("fechado", 0) or 0) == 1)

        mes_ant_dt = pd.Timestamp(year=int(ano_sel), month=int(mes_sel), day=1) - pd.DateOffset(months=1)
        mes_ant_str = mes_ant_dt.strftime("%Y-%m")
        fech_ant = fechamento_buscar(mes_ant_str)
        tem_fechamento_anterior = bool(fech_ant and int(fech_ant.get("fechado", 0) or 0) == 1)

        saldo_inicial_editavel = (not ja_fechado) and (not tem_fechamento_anterior)

        if tem_fechamento_anterior:
            saldo_inicial = float(fech_ant["saldo_final"])
        elif fech_existente:
            saldo_inicial = float(fech_existente.get("saldo_inicial", 0.0))
        else:
            saldo_inicial = 0.0

        st.markdown("##### Saldo inicial do mês")
        if saldo_inicial_editavel:
            st.caption(
                "📌 Este é o primeiro mês controlado no sistema (ou o mês foi reaberto para correção). "
                "Digite o saldo real que você tinha na conta/caixa no primeiro dia do mês. "
                "Depois de fechar este mês, esse valor nunca mais precisa ser digitado — ele passa a "
                "ser transportado automaticamente para o mês seguinte, sem opção de edição."
            )
            saldo_inicial = st.number_input(
                "Saldo inicial do mês (R$)", value=float(saldo_inicial),
                step=10.0, format="%.2f", key=f"saldo_ini_{mes_str}",
            )
        else:
            st.markdown(
                f'<div class="fin-ok">🔒 Saldo transportado automaticamente do fechamento de '
                f'<b>{mes_ant_str}</b>: <b>{brl(saldo_inicial)}</b> — não editável.</div>',
                unsafe_allow_html=True,
            )

        df_r_mes = df_r_fin[df_r_fin["data"].apply(_mes_de) == mes_str].copy() if not df_r_fin.empty else _df_vazio_receb()
        df_g_mes = df_g_fin[(df_g_fin["data"].apply(_mes_de) == mes_str) & (df_g_fin["pago"].astype(int) == 1)].copy() if not df_g_fin.empty else _df_vazio_gastos()

        receitas_mes = _flt(df_r_mes, "valor")
        despesas_mes = _flt(df_g_mes, "valor")
        lucro_real_mes = receitas_mes - despesas_mes
        saldo_teorico = saldo_inicial + lucro_real_mes

        # ══════════════════════════════════════════════════════════════
        # (1) RESUMO DO FECHAMENTO — mesma estrutura oficial do Relatório
        # Mensal de Contas: Saldo do Mês Anterior + Entradas − Despesas =
        # Saldo Disponível no Final do Mês (sempre transportado). Nenhum
        # cálculo novo — só a exibição, bem clara, logo no topo da aba.
        # ══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown(f"## 📋 Resumo do Fechamento — {MESES_PT[mes_sel-1]}/{ano_sel}")
        st.caption(
            "Saldo do Mês Anterior + Entradas − Despesas = Saldo Disponível no Final do Mês "
            "— que é sempre transportado automaticamente para o mês seguinte."
        )

        col_res1, col_res2, col_res3 = st.columns(3)
        col_res1.markdown(f"""
        <div class="kpi-card kpi-cream">
            <div class="kpi-label">📦 Saldo do Mês Anterior</div>
            <div class="kpi-value">{brl(saldo_inicial)}</div>
            <div class="kpi-sub">{("Transportado de " + mes_ant_str) if tem_fechamento_anterior else "Informado manualmente (primeiro mês)"}</div>
        </div>""", unsafe_allow_html=True)
        col_res2.markdown(f"""
        <div class="kpi-card kpi-green">
            <div class="kpi-label">📥 (+) Total das Entradas</div>
            <div class="kpi-value">{brl(receitas_mes)}</div>
            <div class="kpi-sub">{len(df_r_mes)} lançamento(s) neste mês</div>
        </div>""", unsafe_allow_html=True)
        col_res3.markdown(f"""
        <div class="kpi-card kpi-red">
            <div class="kpi-label">📤 (–) Total das Despesas</div>
            <div class="kpi-value">{brl(despesas_mes)}</div>
            <div class="kpi-sub">{len(df_g_mes)} lançamento(s) pagos neste mês</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        col_res4, col_res5 = st.columns(2)
        cor_resultado = "kpi-green" if lucro_real_mes >= 0 else "kpi-red"
        sinal_resultado = "✅ Saldo Positivo do Mês" if lucro_real_mes >= 0 else "⚠️ Saldo Negativo do Mês"
        col_res4.markdown(f"""
        <div class="kpi-card {cor_resultado}">
            <div class="kpi-label">{sinal_resultado}</div>
            <div class="kpi-value">{brl(lucro_real_mes)}</div>
            <div class="kpi-sub">Entradas − Despesas</div>
        </div>""", unsafe_allow_html=True)
        col_res5.markdown(f"""
        <div class="kpi-card kpi-brown" style="border:2px solid #c9a227;">
            <div class="kpi-label">💰 Saldo Disponível no Final do Mês</div>
            <div class="kpi-value" style="font-size:1.7rem;">{brl(saldo_teorico)}</div>
            <div class="kpi-sub">➡️ Transportado automaticamente como saldo inicial de {mes_seguinte_label}</div>
        </div>""", unsafe_allow_html=True)

        st.caption(
            "💡 Este resumo é calculado em tempo real a partir dos lançamentos abaixo. Qualquer "
            "edição ou exclusão no Extrato do mês atualiza os números acima automaticamente."
        )

        # ══════════════════════════════════════════════════════════════
        # (2) EXTRATO DO MÊS — conferência lançamento por lançamento
        # (lógica de edição/exclusão/conciliação 100% inalterada)
        # ══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("##### ✏️ Extrato do mês — Entradas e Saídas")
        st.caption(
            "Confira cada lançamento contra o extrato bancário e marque \"Conciliado?\" conforme "
            "for validando. Edite valor, descrição ou data diretamente na tabela. Para EXCLUIR um "
            "lançamento, clique no ícone de lixeira 🗑️ na linha e depois em \"💾 Salvar alterações\". "
            "Para lançar uma entrada/saída NOVA, vá na aba 📑 **Receb. / Despe.**"
        )

        col_ex1, col_ex2 = st.columns(2)

        with col_ex1:
            st.markdown("**📥 Entradas**")
            if df_r_mes.empty:
                st.info("Nenhuma entrada neste mês.")
            else:
                df_r_edit_base = df_r_mes[["rowid", "data", "descricao", "valor", "conciliado"]].copy()
                df_r_edit_base["data"] = pd.to_datetime(df_r_edit_base["data"]).dt.date
                df_r_edit_base["valor"] = pd.to_numeric(df_r_edit_base["valor"], errors="coerce").fillna(0.0).astype("float64")
                df_r_edit_base["conciliado"] = df_r_edit_base["conciliado"].fillna(0).astype(int).astype(bool)
                df_r_edit_base = df_r_edit_base.sort_values("data").reset_index(drop=True)

                edited_r = st.data_editor(
                    df_r_edit_base,
                    column_config={
                        "rowid": None,
                        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "descricao": st.column_config.TextColumn("Descrição"),
                        "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.0, step=0.01),
                        "conciliado": st.column_config.CheckboxColumn("Conciliado?"),
                    },
                    hide_index=True, use_container_width=True,
                    num_rows="dynamic",
                    key=f"edit_r_{mes_str}", disabled=ja_fechado,
                )

                if not ja_fechado and st.button("💾 Salvar alterações (Entradas)", key=f"salvar_r_{mes_str}", use_container_width=True):
                    rowids_antes = set(df_r_edit_base["rowid"].astype(str))
                    rowids_depois = set(edited_r["rowid"].dropna().astype(str))
                    excluidos_r = rowids_antes - rowids_depois

                    for rid in excluidos_r:
                        recebimentos_deletar(rid)

                    houve_mudanca_r = bool(excluidos_r)
                    for _, row_new in edited_r.iterrows():
                        if pd.isna(row_new["rowid"]):
                            continue
                        match = df_r_edit_base[df_r_edit_base["rowid"] == row_new["rowid"]]
                        if match.empty:
                            continue
                        row_old = match.iloc[0]
                        if (
                            float(row_new["valor"]) != float(row_old["valor"])
                            or str(row_new["descricao"]) != str(row_old["descricao"])
                            or bool(row_new["conciliado"]) != bool(row_old["conciliado"])
                            or row_new["data"] != row_old["data"]
                        ):
                            recebimentos_atualizar(str(row_new["rowid"]), {
                                "valor": float(row_new["valor"]),
                                "descricao": str(row_new["descricao"]),
                                "conciliado": 1 if row_new["conciliado"] else 0,
                                "data": row_new["data"].isoformat() if hasattr(row_new["data"], "isoformat") else str(row_new["data"]),
                            })
                            houve_mudanca_r = True
                    if houve_mudanca_r:
                        if excluidos_r:
                            st.success(f"✅ Entradas atualizadas! ({len(excluidos_r)} excluída(s))")
                        else:
                            st.success("✅ Entradas atualizadas!")
                        st.rerun()
                    else:
                        st.info("Nenhuma alteração para salvar.")

        with col_ex2:
            st.markdown("**📤 Saídas**")
            if df_g_mes.empty:
                st.info("Nenhuma saída paga neste mês.")
            else:
                df_g_edit_base = df_g_mes[["rowid", "data", "descricao", "valor", "conciliado"]].copy()
                df_g_edit_base["data"] = pd.to_datetime(df_g_edit_base["data"]).dt.date
                df_g_edit_base["valor"] = pd.to_numeric(df_g_edit_base["valor"], errors="coerce").fillna(0.0).astype("float64")
                df_g_edit_base["conciliado"] = df_g_edit_base["conciliado"].fillna(0).astype(int).astype(bool)
                df_g_edit_base = df_g_edit_base.sort_values("data").reset_index(drop=True)

                edited_g = st.data_editor(
                    df_g_edit_base,
                    column_config={
                        "rowid": None,
                        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                        "descricao": st.column_config.TextColumn("Descrição"),
                        "valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.0, step=0.01),
                        "conciliado": st.column_config.CheckboxColumn("Conciliado?"),
                    },
                    hide_index=True, use_container_width=True,
                    num_rows="dynamic",
                    key=f"edit_g_{mes_str}", disabled=ja_fechado,
                )

                if not ja_fechado and st.button("💾 Salvar alterações (Saídas)", key=f"salvar_g_{mes_str}", use_container_width=True):
                    rowids_antes_g = set(df_g_edit_base["rowid"].astype(str))
                    rowids_depois_g = set(edited_g["rowid"].dropna().astype(str))
                    excluidos_g = rowids_antes_g - rowids_depois_g

                    for rid in excluidos_g:
                        gastos_deletar(rid)

                    houve_mudanca_g = bool(excluidos_g)
                    for _, row_new in edited_g.iterrows():
                        if pd.isna(row_new["rowid"]):
                            continue
                        match = df_g_edit_base[df_g_edit_base["rowid"] == row_new["rowid"]]
                        if match.empty:
                            continue
                        row_old = match.iloc[0]
                        if (
                            float(row_new["valor"]) != float(row_old["valor"])
                            or str(row_new["descricao"]) != str(row_old["descricao"])
                            or bool(row_new["conciliado"]) != bool(row_old["conciliado"])
                            or row_new["data"] != row_old["data"]
                        ):
                            gastos_atualizar(str(row_new["rowid"]), {
                                "valor": float(row_new["valor"]),
                                "descricao": str(row_new["descricao"]),
                                "conciliado": 1 if row_new["conciliado"] else 0,
                                "data": row_new["data"].isoformat() if hasattr(row_new["data"], "isoformat") else str(row_new["data"]),
                            })
                            houve_mudanca_g = True
                    if houve_mudanca_g:
                        if excluidos_g:
                            st.success(f"✅ Saídas atualizadas! ({len(excluidos_g)} excluída(s))")
                        else:
                            st.success("✅ Saídas atualizadas!")
                        st.rerun()
                    else:
                        st.info("Nenhuma alteração para salvar.")

        # ══════════════════════════════════════════════════════════════
        # (3) GRANDES DESPESAS PREVISTAS
        # ══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("##### 🎯 Grandes Despesas Previstas (fundos reservados)")
        st.caption("Despesas grandes já esperadas mas ainda não pagas — ficam aqui até serem quitadas, não importa o mês. Elas reservam parte do seu saldo para você não gastar esse dinheiro por engano em outra coisa.")
        df_grandes = _grandes_despesas_previstas(df_g_fin)
        total_grandes = _flt(df_grandes, "valor")
        fundos_disponiveis = saldo_teorico - total_grandes

        if df_grandes.empty:
            st.info("Nenhuma grande despesa prevista em aberto no momento.")
        else:
            for _, gd in df_grandes.sort_values("data").iterrows():
                col_gd1, col_gd2 = st.columns([5, 1])
                col_gd1.markdown(f"- {formatar_data_br(gd['data'])} — **{gd['descricao']}** — {brl(float(gd['valor']))}")
                if col_gd2.button("✅ Já paguei", key=f"pagar_grande_{gd['rowid']}"):
                    gastos_atualizar(str(gd["rowid"]), {"pago": 1})
                    st.rerun()

        col_j, col_k = st.columns(2)
        col_j.metric("Total reservado", brl(total_grandes))
        col_k.metric("Fundos realmente disponíveis", brl(fundos_disponiveis),
                     help="Saldo Disponível no Final do Mês menos o que já está reservado para as grandes despesas previstas.")
        if fundos_disponiveis < 0:
            st.markdown(f'<div class="fin-danger">⚠️ O saldo não cobre todas as grandes despesas reservadas — faltam {brl(abs(fundos_disponiveis))}.</div>', unsafe_allow_html=True)

        with st.expander("➕ Lançar nova grande despesa prevista"):
            with st.form("form_grande_despesa", clear_on_submit=True):
                cg1, cg2 = st.columns(2)
                gg_desc = cg1.text_input("Descrição *", placeholder="Ex: Aluguel do espaço para o desfile de fim de ano")
                gg_val  = cg2.number_input("Valor (R$) *", min_value=0.01, step=50.0, format="%.2f")
                gg_data = st.date_input("Data prevista", hoje_brasilia(), format="DD/MM/YYYY")
                if st.form_submit_button("💾 Reservar", use_container_width=True, type="primary"):
                    if gg_desc.strip() and gg_val > 0:
                        gastos_inserir({
                            "encomenda_id": None,
                            "descricao": gg_desc.strip(), "valor": gg_val,
                            "data": gg_data.isoformat(), "categoria": "Grande despesa prevista",
                            "pago": 0, "recorrente": 0,
                            "grande_despesa_prevista": 1,
                            "conciliado": 0,
                            "criado_em": agora_br().isoformat(),
                        })
                        st.success("✅ Reservado!")
                        st.rerun()
                    else:
                        st.error("Preencha descrição e valor.")

        # ══════════════════════════════════════════════════════════════
        # (4) PROGRESSO DA CONFERÊNCIA
        # ══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("##### ✅ Progresso da conferência")
        st.caption("Marque \"Conciliado?\" no Extrato do mês acima conforme for conferindo com o extrato do banco.")

        total_itens = len(df_r_mes) + len(df_g_mes)
        conc_itens = 0
        if not df_r_mes.empty:
            conc_itens += int(df_r_mes["conciliado"].fillna(0).astype(int).sum())
        if not df_g_mes.empty:
            conc_itens += int(df_g_mes["conciliado"].fillna(0).astype(int).sum())
        st.progress(conc_itens / total_itens if total_itens else 0, text=f"{conc_itens} de {total_itens} lançamentos conferidos")

        # ══════════════════════════════════════════════════════════════
        # (5) CONFRONTO FINAL COM O SALDO DO BANCO
        # ══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("##### 🏦 Confronto final com o saldo do banco")
        saldo_extrato = st.number_input(
            "Saldo que aparece no extrato bancário no último dia do mês (R$)",
            value=float(fech_existente.get("saldo_extrato_informado", saldo_teorico)) if fech_existente and fech_existente.get("saldo_extrato_informado") is not None else float(saldo_teorico),
            step=10.0, format="%.2f", disabled=ja_fechado,
        )
        diferenca = saldo_teorico - saldo_extrato
        if abs(diferenca) < 0.01:
            st.markdown('<div class="fin-ok">✅ Bateu certinho! O saldo do sistema é igual ao do extrato.</div>', unsafe_allow_html=True)
        else:
            sinal = "a mais no sistema do que no banco" if diferenca > 0 else "a mais no banco do que no sistema"
            st.markdown(f'<div class="fin-danger">⚠️ Diferença de <b>{brl(abs(diferenca))}</b> ({sinal}). Confira se falta algum lançamento, se houve tarifa bancária, ou lançamento duplicado antes de fechar.</div>', unsafe_allow_html=True)

        observacoes = st.text_area("Observações do fechamento (opcional)",
                                    value=fech_existente.get("observacoes", "") if fech_existente else "",
                                    disabled=ja_fechado)

        # ══════════════════════════════════════════════════════════════
        # (6) FECHAR MÊS / REABRIR / AVANÇAR
        # ══════════════════════════════════════════════════════════════
        if ja_fechado:
            st.success(f"🔒 Mês {mes_str} já está FECHADO (fechamento em {formatar_data_hora_br(fech_existente.get('data_fechamento'))}). Saldo final: {brl(float(fech_existente.get('saldo_final', 0)))} — Fundos disponíveis: {brl(float(fech_existente.get('fundos_disponiveis', fech_existente.get('saldo_final', 0))))}")
            col_reab, col_avc = st.columns(2)
            if col_reab.button("🔓 Reabrir este mês (usar apenas para corrigir erro)", key="reabrir_mes", use_container_width=True):
                fechamento_salvar(mes_str, {"fechado": 0})
                st.warning("Mês reaberto. Os valores voltaram a ser editáveis.")
                st.rerun()
            if col_avc.button("➡️ Ir para o próximo mês", key="ir_prox_mes", use_container_width=True):
                prox = _mes_seguinte(mes_str)
                st.session_state["mes_fechamento"] = int(prox[5:7])
                st.session_state["ano_fechamento"] = int(prox[:4])
                st.rerun()
        else:
            pode_fechar = total_itens == 0 or conc_itens == total_itens
            if not pode_fechar:
                st.warning("⚠️ Ainda existem lançamentos não conferidos. Recomendado conferir tudo antes de fechar — mas se precisar, pode fechar mesmo assim registrando o motivo nas observações.")
            if st.button("🔒 Fechar Mês e Avançar para o Próximo ➡️", type="primary", use_container_width=True):
                saldo_final_oficial = saldo_extrato if abs(diferenca) >= 0.01 else saldo_teorico
                fundos_disp_oficial = saldo_final_oficial - total_grandes
                fechamento_salvar(mes_str, {
                    "mes": mes_str,
                    "saldo_inicial": saldo_inicial,
                    "receitas_mes": receitas_mes,
                    "despesas_mes": despesas_mes,
                    "lucro_real_mes": lucro_real_mes,
                    "saldo_final": saldo_final_oficial,
                    "grandes_despesas_previstas": total_grandes,
                    "fundos_disponiveis": fundos_disp_oficial,
                    "saldo_extrato_informado": saldo_extrato,
                    "diferenca": diferenca,
                    "fechado": 1,
                    "observacoes": observacoes,
                    "data_fechamento": agora_br().isoformat(),
                    "atualizado_em": agora_br().isoformat(),
                })
                prox = _mes_seguinte(mes_str)
                st.session_state["mes_fechamento"] = int(prox[5:7])
                st.session_state["ano_fechamento"] = int(prox[:4])
                st.success(f"✅ Mês {mes_str} fechado! Saldo final de {brl(saldo_final_oficial)} vira o saldo inicial de {prox}. Indo para o próximo mês...")
                st.rerun()

        # ══════════════════════════════════════════════════════════════
        # (7) EXPORTAÇÕES — PDF de Fechamento (estrutura oficial, sem
        # "Anúncio Mensal") + Excel (planilha completa para arquivo/backup)
        # ══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("##### 📤 Exportar Fechamento")

        saldo_final_export = saldo_teorico if not ja_fechado else float(fech_existente.get("saldo_final", saldo_teorico))
        fundos_disp_export = fundos_disponiveis if not ja_fechado else float(fech_existente.get("fundos_disponiveis", fundos_disponiveis))
        data_fech_export = fech_existente.get("data_fechamento") if (ja_fechado and fech_existente) else None

        col_exp1, col_exp2 = st.columns(2)

        with col_exp1:
            pdf_fechamento_bytes = gerar_pdf_fechamento(
                mes_str=mes_str,
                saldo_inicial=saldo_inicial,
                df_r_mes=df_r_mes,
                df_g_mes=df_g_mes,
                receitas_mes=receitas_mes,
                despesas_mes=despesas_mes,
                lucro_real_mes=lucro_real_mes,
                saldo_final=saldo_final_export,
                df_grandes=df_grandes,
                total_grandes=total_grandes,
                fundos_disponiveis=fundos_disp_export,
                saldo_extrato=saldo_extrato,
                diferenca=diferenca,
                observacoes=observacoes,
                fechado=ja_fechado,
                data_fechamento=data_fech_export,
            )
            st.download_button(
                label=f"📄 Baixar PDF de Fechamento — {mes_str}",
                data=pdf_fechamento_bytes,
                file_name=f"Lila_Fechamento_{mes_str}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        with col_exp2:
            buf_fech = io.BytesIO()
            wb_fech = xlsxwriter.Workbook(buf_fech)
            fmt_h_fech = wb_fech.add_format({"bold": True, "bg_color": "#3d1f10", "font_color": "white", "border": 1})
            fmt_brl_fech = wb_fech.add_format({"num_format": "R$ #,##0.00", "border": 1})
            fmt_n_fech = wb_fech.add_format({"border": 1})
            ws_fech = wb_fech.add_worksheet("Fechamento")
            ws_fech.set_column(0, 0, 45)
            ws_fech.set_column(1, 1, 18)
            ws_fech.write(0, 0, f"Fechamento de Caixa — {mes_str}", wb_fech.add_format({"bold": True, "font_size": 14, "font_color": "#3d1f10"}))
            linhas_fech = [
                ("Saldo do Mês Anterior", saldo_inicial),
                ("(+) Total das Entradas", receitas_mes),
                ("(–) Total das Despesas", despesas_mes),
                ("Saldo do Mês (positivo/negativo)", lucro_real_mes),
                ("Saldo Disponível no Final do Mês", saldo_final_export),
                ("Total reservado (grandes despesas)", total_grandes),
                ("Fundos realmente disponíveis", fundos_disp_export),
            ]
            for ri, (label, val) in enumerate(linhas_fech, 2):
                ws_fech.write(ri, 0, label, fmt_n_fech)
                ws_fech.write(ri, 1, float(val), fmt_brl_fech)
            r0 = len(linhas_fech) + 4
            ws_fech.write(r0, 0, "Entradas do mês (detalhado)", fmt_h_fech)
            ws_fech.write(r0, 1, "Valor", fmt_h_fech)
            for i, (_, r) in enumerate(df_r_mes.sort_values("data").iterrows(), 1):
                ws_fech.write(r0 + i, 0, f"{formatar_data_br(r['data'])} — {r['descricao']}", fmt_n_fech)
                ws_fech.write(r0 + i, 1, float(r["valor"]), fmt_brl_fech)
            r1 = r0 + len(df_r_mes) + 3
            ws_fech.write(r1, 0, "Saídas do mês (detalhado)", fmt_h_fech)
            ws_fech.write(r1, 1, "Valor", fmt_h_fech)
            for i, (_, g) in enumerate(df_g_mes.sort_values("data").iterrows(), 1):
                ws_fech.write(r1 + i, 0, f"{formatar_data_br(g['data'])} — {g['descricao']}", fmt_n_fech)
                ws_fech.write(r1 + i, 1, float(g["valor"]), fmt_brl_fech)
            wb_fech.close()
            buf_fech.seek(0)
            st.download_button(
                label=f"📊 Baixar Fechamento de {mes_str} (Excel)",
                data=buf_fech,
                file_name=f"Lila_Fechamento_{mes_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        # ══════════════════════════════════════════════════════════════
        # (8) HISTÓRICO DE FECHAMENTOS
        # ══════════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("##### 🗓️ Histórico de fechamentos")
        if df_f_fin.empty:
            st.info("Nenhum mês fechado ainda.")
        else:
            df_hist = df_f_fin[df_f_fin["fechado"].astype(int) == 1].sort_values("mes", ascending=False).copy()
            if df_hist.empty:
                st.info("Nenhum mês fechado ainda.")
            else:
                if "fundos_disponiveis" not in df_hist.columns:
                    df_hist["fundos_disponiveis"] = df_hist["saldo_final"]
                df_hist_show = df_hist[["mes","saldo_inicial","receitas_mes","despesas_mes","saldo_final","fundos_disponiveis"]].copy()
                df_hist_show.columns = ["Mês","Saldo Anterior","Entradas","Despesas","Saldo Final","Fundos Disponíveis"]
                for c in ["Saldo Anterior","Entradas","Despesas","Saldo Final","Fundos Disponíveis"]:
                    df_hist_show[c] = df_hist_show[c].fillna(0).apply(lambda x: brl(float(x)))
                st.dataframe(df_hist_show, use_container_width=True, hide_index=True)
