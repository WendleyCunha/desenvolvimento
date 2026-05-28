import io
import os
import streamlit as st
import pandas as pd
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTES DE CALIBRAÇÃO DO PDF S-21
# ═══════════════════════════════════════════════════════════════════════════════
PDF_Y_OFFSET    = 0.0

PDF_NOME_Y      = 272.0
PDF_NOME_X      = 24.0
PDF_NASCI_Y     = 265.0
PDF_NASCI_X     = 48.0
PDF_BATISM_Y    = 258.0
PDF_BATISM_X    = 48.0
PDF_CARGO_Y     = 252.0

PDF_MASC_X      = 150.0
PDF_FEM_X       = 172.0
PDF_OVELHAS_X   = 150.0
PDF_UNGIDO_X    = 172.0

PDF_ANCIAO_X    = 9.5
PDF_SERVO_X     = 35.0
PDF_PREG_X      = 65.0
PDF_PESP_X      = 100.0
PDF_MISS_X      = 140.0

PDF_TEL_HEADER_Y = 232.0

_Y_MAP_BASE = {
    "SETEMBRO":  228.5,
    "OUTUBRO":   220.5,
    "NOVEMBRO":  212.5,
    "DEZEMBRO":  204.5,
    "JANEIRO":   196.5,
    "FEVEREIRO": 188.5,
    "MARÇO":     180.5,
    "ABRIL":     172.5,
    "MAIO":      164.5,
    "JUNHO":     156.5,
    "JULHO":     148.5,
    "AGOSTO":    140.5,
}

PDF_COL_PARTICIP_X = 53.5
PDF_COL_ESTUDOS_X  = 80.5
PDF_COL_PIAUX_X    = 97.5
PDF_COL_HORAS_X    = 116.5
PDF_COL_OBS_X      = 133.0


def gerar_pdf_padrao_s21(
    nome_cabecalho: str,
    categoria_label: str,
    dados_rows: pd.DataFrame,
    membro_info: dict = None,
) -> bytes | None:
    """
    Preenche o cartão S-21 e retorna os bytes do PDF gerado.
    membro_info: dict com data_nascimento, data_batismo, genero, classe, cargo, telefone_emergencia.
    """
    # Procura o s21.pdf na raiz do projeto
    path_original = os.path.join(os.path.dirname(os.path.dirname(__file__)), "s21.pdf")
    if not os.path.exists(path_original):
        st.error("Arquivo 's21.pdf' não encontrado na pasta do app.")
        return None

    mi = membro_info or {}

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)

    # ── Nome
    can.setFont("Helvetica-Bold", 10)
    can.drawString(PDF_NOME_X * mm, PDF_NOME_Y * mm, str(nome_cabecalho).upper())

    # ── Data de Nascimento
    data_nasc = str(mi.get("data_nascimento", "")).strip()
    if data_nasc:
        can.setFont("Helvetica", 9)
        can.drawString(PDF_NASCI_X * mm, PDF_NASCI_Y * mm, data_nasc)

    # ── Data de Batismo
    data_bat = str(mi.get("data_batismo", "")).strip()
    if data_bat:
        can.setFont("Helvetica", 9)
        can.drawString(PDF_BATISM_X * mm, PDF_BATISM_Y * mm, data_bat)

    # ── Gênero
    genero = mi.get("genero", "")
    can.setFont("Helvetica-Bold", 10)
    if genero == "Masculino":
        can.drawString(PDF_MASC_X * mm, PDF_NASCI_Y * mm, "X")
    elif genero == "Feminino":
        can.drawString(PDF_FEM_X * mm, PDF_NASCI_Y * mm, "X")

    # ── Classe
    classe = mi.get("classe", "")
    if classe == "Outras ovelhas":
        can.drawString(PDF_OVELHAS_X * mm, PDF_BATISM_Y * mm, "X")
    elif classe == "Ungido":
        can.drawString(PDF_UNGIDO_X * mm, PDF_BATISM_Y * mm, "X")

    # ── Cargo
    cargo = mi.get("cargo", "")
    cargo_map = {
        "Ancião":               PDF_ANCIAO_X,
        "Servo ministerial":    PDF_SERVO_X,
        "Pioneiro regular":     PDF_PREG_X,
        "Pioneiro especial":    PDF_PESP_X,
        "Missionário em campo": PDF_MISS_X,
    }
    if cargo in cargo_map:
        can.drawString(cargo_map[cargo] * mm, PDF_CARGO_Y * mm, "X")

    # ── Telefone de emergência no cabeçalho
    tel_emerg = str(mi.get("telefone_emergencia", "")).strip()
    if tel_emerg:
        can.setFont("Helvetica-Bold", 9)
        can.drawString(PDF_COL_OBS_X * mm, PDF_TEL_HEADER_Y * mm, f"Tel: {tel_emerg}"[:32])

    # ── Linhas da tabela de meses
    for _, row in dados_rows.iterrows():
        mes_key = str(row.get("mes_referencia", "")).split()[0].upper()
        y_base  = _Y_MAP_BASE.get(mes_key)
        if y_base is None:
            continue
        y_pos = (y_base + PDF_Y_OFFSET) * mm

        horas = int(row.get("horas", 0))
        estud = int(row.get("estudos_biblicos", 0))

        if horas > 0 or estud > 0:
            can.setFont("Helvetica-Bold", 10)
            can.drawCentredString(PDF_COL_PARTICIP_X * mm, y_pos, "X")

        can.setFont("Helvetica-Bold", 10)
        can.drawCentredString(PDF_COL_ESTUDOS_X * mm, y_pos, str(estud))

        cat_str = str(categoria_label).upper()
        if row.get("cat_oficial") == "PIONEIRO AUXILIAR" or "AUXILIAR" in cat_str:
            can.drawCentredString(PDF_COL_PIAUX_X * mm, y_pos, "X")

        can.drawCentredString(PDF_COL_HORAS_X * mm, y_pos, str(horas))

        obs_normal = str(row.get("observacoes", ""))
        obs_normal = obs_normal if obs_normal.lower() not in ("nan", "", "none") else ""
        if obs_normal:
            can.setFont("Helvetica", 8)
            can.drawString(PDF_COL_OBS_X * mm, y_pos, obs_normal[:32])

        can.setFont("Helvetica-Bold", 10)

    can.save()
    packet.seek(0)

    reader_original = PdfReader(open(path_original, "rb"))
    writer = PdfWriter()
    pagina_base = reader_original.pages[0]
    pagina_base.merge_page(PdfReader(packet).pages[0])
    writer.add_page(pagina_base)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
