"""
atelier_pdf.py — PDFs do Lila Closet Atelier (contrato e fechamento de caixa)
Copiados do sistema em Streamlit (modulos/mod_encomendas.py e mod_financeiro.py)
com o MESMO layout; só trocam a fonte dos dados (dicionários em vez de pandas).
"""
import hashlib
import io
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FUSO_BR = ZoneInfo("America/Sao_Paulo")
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recursos", "lila.png")
MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def agora_br() -> datetime:
    return datetime.now(FUSO_BR)


def brl(valor) -> str:
    return f"R$ {float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data_br(v) -> str:
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        return str(v or "")


def formatar_data_hora_br(v) -> str:
    if not v:
        return "—"
    try:
        dt = datetime.fromisoformat(str(v))
        dt = dt if dt.tzinfo else dt.replace(tzinfo=FUSO_BR)
        return dt.astimezone(FUSO_BR).strftime("%d/%m/%Y às %H:%M")
    except Exception:  # noqa: BLE001
        return str(v)


def _marrom():  return colors.HexColor("#3d1f10")
def _bege():    return colors.HexColor("#fdf6ee")
def _dourado(): return colors.HexColor("#c9a227")

def gerar_pdf_contrato(enc: dict, cpf: str, rg: str, cfg: dict) -> bytes:
    _cfg = lambda k: str(cfg.get(k, "") or "")
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

    cnpj_val = _cfg("cnpj")
    tel_val  = _cfg("telefone")
    end_val  = _cfg("endereco")

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


def _marrom_fin():  return colors.HexColor("#3d1f10")
def _bege_fin():    return colors.HexColor("#fdf6ee")
def _dourado_fin(): return colors.HexColor("#c9a227")


def gerar_pdf_fechamento(
    mes_str: str,
    saldo_inicial: float,
    df_r_mes: list,
    df_g_mes: list,
    receitas_mes: float,
    despesas_mes: float,
    lucro_real_mes: float,
    saldo_final: float,
    df_grandes: list,
    total_grandes: float,
    fundos_disponiveis: float,
    saldo_extrato: float | None = None,
    diferenca: float | None = None,
    observacoes: str = "",
    fechado: bool = False,
    data_fechamento: str | None = None,
    cfg: dict | None = None,
) -> bytes:
    _cfg = lambda k: str((cfg or {}).get(k, "") or "")
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

    cnpj_val = _cfg("cnpj")
    tel_val  = _cfg("telefone")
    end_val  = _cfg("endereco")
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
    if not df_r_mes:
        story.append(Paragraph("Nenhuma entrada registrada neste mês.", styles["Normal"]))
    else:
        rows_r = [[Paragraph("<b>Data</b>", s_et_hdr), Paragraph("<b>Descrição</b>", s_et_hdr), Paragraph("<b>Valor</b>", s_et_hdr)]]
        for r in sorted(df_r_mes, key=lambda x: str(x.get("data") or "")):
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
    if not df_g_mes:
        story.append(Paragraph("Nenhuma despesa paga registrada neste mês.", styles["Normal"]))
    else:
        rows_g = [[Paragraph("<b>Data</b>", s_et_hdr), Paragraph("<b>Descrição</b>", s_et_hdr),
                   Paragraph("<b>Categoria</b>", s_et_hdr), Paragraph("<b>Valor</b>", s_et_hdr)]]
        for g in sorted(df_g_mes, key=lambda x: str(x.get("data") or "")):
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
    if df_grandes:
        story.append(Paragraph("GRANDES DESPESAS PREVISTAS (RESERVADAS)", s_cls_tit))
        rows_gd = [[Paragraph("<b>Data Prevista</b>", s_et_hdr), Paragraph("<b>Descrição</b>", s_et_hdr), Paragraph("<b>Valor</b>", s_et_hdr)]]
        for gd in sorted(df_grandes, key=lambda x: str(x.get("data") or "")):
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
