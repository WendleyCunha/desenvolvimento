"""
pedido_pdf.py — PDF do pedido do ERP (baixar na venda, no Atendimento e no app do cliente).

Uma página A4 com: empresa, número e data do pedido, cliente (código, telefone, endereço de
entrega), itens (preço só para quem pode ver), totais, agendamento e — quando quem baixa pode
ver — a PALAVRA-CHAVE da entrega (o cliente informa ao motorista; ela confere a entrega).
Gerado no servidor com reportlab (sem serviço pago).
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

TINTA = colors.HexColor("#111827")
CINZA = colors.HexColor("#6B7280")
LINHA = colors.HexColor("#E5E7EB")
DESTAQUE = colors.HexColor("#0E7490")
OURO = colors.HexColor("#B7791F")

ST_ROT = {"rascunho": "Rascunho", "confirmado": "Confirmado", "agendado": "Agendado", "em_carga": "Em carga", "em_rota": "Saiu para entrega",
          "entregue": "Entregue", "reagendar": "Reagendar", "cancelado": "Cancelado", "recusado": "Recusado"}


def brl(v) -> str:
    return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(v) -> str:
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        return str(v or "")


def _esc(t) -> str:
    return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def endereco_txt(e: dict) -> str:
    e = e or {}
    l1 = ", ".join(x for x in (e.get("logradouro"), e.get("numero")) if x)
    partes = [l1, e.get("complemento"), e.get("bairro"), "/".join(x for x in (e.get("cidade"), e.get("uf")) if x)]
    txt = " · ".join(x for x in partes if x)
    if e.get("cep"):
        txt += f" · CEP {e['cep']}"
    if e.get("referencia"):
        txt += f" · Ref.: {e['referencia']}"
    return txt


def gerar(ped: dict, produtos: dict, cliente: dict | None, empresa: str, ver_preco: bool = True, ver_contato: bool = True,
          palavra: str = "", emitido_por: str = "", emitido_em: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.4 * cm, bottomMargin=1.4 * cm,
                            title=f"Pedido {ped.get('numero')}", author=empresa)
    s_tit = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=TINTA)
    s_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, leading=13, textColor=CINZA)
    s_txt = ParagraphStyle("x", fontName="Helvetica", fontSize=10.5, leading=14, textColor=TINTA)
    s_rot = ParagraphStyle("r", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=CINZA)
    s_pal = ParagraphStyle("p", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=TINTA, alignment=1)
    s_pal_rot = ParagraphStyle("pr", fontName="Helvetica", fontSize=9, leading=12, textColor=OURO, alignment=1)
    el = []
    tipo = "TROCA" if ped.get("tipo") == "troca" else "PEDIDO"
    cab = Table([[Paragraph(f"<b>{_esc(empresa)}</b>", ParagraphStyle("e", fontName="Helvetica-Bold", fontSize=13, textColor=DESTAQUE)),
                  Paragraph(f"{tipo} <b>#{_esc(ped.get('numero'))}</b>", ParagraphStyle("n", fontName="Helvetica", fontSize=13, alignment=2, textColor=TINTA))]],
                colWidths=[10 * cm, 7.8 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, DESTAQUE), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    el += [cab, Spacer(1, 10)]
    ag = ped.get("agendamento") or {}
    info = [[Paragraph("DATA DO PEDIDO", s_rot), Paragraph("SITUAÇÃO", s_rot), Paragraph("ENTREGA", s_rot)],
            [Paragraph(data_br(ped.get("criado_em")), s_txt), Paragraph(ST_ROT.get(ped.get("status"), str(ped.get("status") or "")), s_txt),
             Paragraph(f"{data_br(ag.get('data'))} {_esc(ag.get('janela') or '')}".strip() if ag.get("data") else "A agendar", s_txt)]]
    ti = Table(info, colWidths=[5.9 * cm] * 3)
    ti.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F9FAFB")), ("BOX", (0, 0), (-1, -1), 0.6, LINHA),
                            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el += [ti, Spacer(1, 12)]
    cli = cliente or {}
    linhas_cli = [f"<b>{_esc(ped.get('cliente_nome') or cli.get('nome'))}</b>" + (f" · código <b>{_esc(cli.get('codigo'))}</b>" if cli.get("codigo") else "")]
    if ver_contato and (ped.get("telefone") or cli.get("telefone")):
        linhas_cli.append(f"Telefone: {_esc(ped.get('telefone') or cli.get('telefone'))}")
    linhas_cli.append(f"Endereço de entrega: {_esc(endereco_txt(ped.get('endereco')))}")
    el += [Paragraph("CLIENTE", s_rot), Spacer(1, 3)] + [Paragraph(x, s_txt) for x in linhas_cli] + [Spacer(1, 12)]
    cabec = ["Produto", "Código", "Qtd"] + (["Preço", "Total"] if ver_preco else [])
    dados = [cabec]
    for i in ped.get("itens") or []:
        pr = produtos.get(i.get("produto_id")) or {}
        ln = [Paragraph(_esc(pr.get("nome") or "Produto"), s_txt), _esc(pr.get("sku") or ""), str(i.get("qtd") or 0)]
        if ver_preco:
            ln += [brl(i.get("preco")), brl(float(i.get("preco") or 0) * int(i.get("qtd") or 0))]
        dados.append(ln)
    for i in ped.get("recolher") or []:
        pr = produtos.get(i.get("produto_id")) or {}
        ln = [Paragraph("↩ Recolher: " + _esc(pr.get("nome") or "Produto"), s_txt), _esc(pr.get("sku") or ""), str(i.get("qtd") or 0)]
        dados.append(ln + (["", ""] if ver_preco else []))
    larg = [8.3 * cm, 3 * cm, 1.5 * cm] + ([2.5 * cm, 2.5 * cm] if ver_preco else [])
    tt = Table(dados, colWidths=larg, repeatRows=1)
    tt.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                            ("TEXTCOLOR", (0, 0), (-1, 0), CINZA), ("LINEBELOW", (0, 0), (-1, 0), 0.8, TINTA),
                            ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINHA), ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el += [Paragraph("ITENS", s_rot), Spacer(1, 3), tt]
    if ver_preco:
        tot = []
        if ped.get("frete"):
            tot.append(["Frete", brl(ped.get("frete"))])
        if ped.get("desconto"):
            tot.append(["Desconto", "- " + brl(ped.get("desconto"))])
        tot.append(["TOTAL", brl(ped.get("valor_total"))])
        tb = Table(tot, colWidths=[13.3 * cm, 4.5 * cm])
        tb.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                                ("FONTSIZE", (0, 0), (-1, -1), 10.5), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
        el += [Spacer(1, 6), tb]
    if ped.get("obs"):
        el += [Spacer(1, 10), Paragraph("OBSERVAÇÕES", s_rot), Paragraph(_esc(ped.get("obs")), s_txt)]
    if ag.get("obs"):
        el += [Spacer(1, 6), Paragraph(f"Entrega: {_esc(ag.get('obs'))}", s_txt)]
    if palavra:
        cx = Table([[Paragraph("PALAVRA-CHAVE DA ENTREGA — informe ao motorista na hora de receber", s_pal_rot)],
                    [Paragraph(_esc(palavra), s_pal)],
                    [Paragraph("Não compartilhe com ninguém além do motorista. Sem a palavra, a entrega não é registrada.", s_sub)]],
                   colWidths=[17.8 * cm])
        cx.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.4, OURO), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
                                ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        el += [Spacer(1, 16), cx]
    el += [Spacer(1, 18), Paragraph(f"Emitido em {data_br(emitido_em)} {str(emitido_em)[11:16]}" + (f" por {_esc(emitido_por)}" if emitido_por else "")
                                    + f" · {_esc(empresa)}", s_sub)]
    doc.build(el)
    return buf.getvalue()
