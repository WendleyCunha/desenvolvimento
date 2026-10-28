"""
hub/secretaria_pdf.py — PDFs e ZIP da Secretaria (Parque Aliança).
─────────────────────────────────────────────────────────────────────────────
• S-21: preenche os CAMPOS do formulário oficial S-21-T (recursos/s21_modelo.pdf,
  o mesmo que o JW Hub exporta) — sem coordenadas calibradas na mão.
    900_1 nome · 900_2 nascimento · 900_3/4 masc/fem · 900_5 batismo
    900_6/7 outras ovelhas/ungido · 900_8..12 ancião/servo/PR/PE/missionário
    900_13 ano de serviço · linhas 20..31 = set..ago:
      901 participou · 902 estudos · 903 pioneiro auxiliar · 904 horas · 905 observações
    904_32 total de horas
  Cartões de TOTAIS (Publicadores / Auxiliares / Regulares) seguem o padrão do
  JW Hub: estudos, horas e o número de relatórios na coluna de observações.
• S-88: desenhado com ReportLab (tabela meio/fim de semana + médias).
• ZIP da visita: pastas no mesmo formato da pasta que o secretário entrega.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject

import secretaria_regras as R

MODELO_S21 = Path(__file__).resolve().parent / "recursos" / "s21_modelo.pdf"
LIGADO = "/N"   # valor "marcado" das caixas do S-21-T
CARGO_CAMPO = {"Ancião": "900_8_CheckBox", "Servo ministerial": "900_9_CheckBox", "Pioneiro regular": "900_10_CheckBox",
               "Pioneiro especial": "900_11_CheckBox", "Missionário em campo": "900_12_CheckBox"}


def nome_arquivo(t: str) -> str:
    t = re.sub(r'[\\/:*?"<>|]+', " ", str(t or "")).strip()
    return re.sub(r"\s+", " ", t)[:120] or "sem nome"


def _preencher(campos_txt: dict, caixas: set[str]) -> bytes:
    leitor = PdfReader(str(MODELO_S21))
    w = PdfWriter(clone_from=leitor)
    pagina = w.pages[0]
    w.update_page_form_field_values(pagina, {k: str(v) for k, v in campos_txt.items()}, auto_regenerate=False)
    for a in pagina.get("/Annots", []):
        a = a.get_object()
        nome = a.get("/T")
        if a.get("/FT") == "/Btn" and nome is not None:
            estado = NameObject(LIGADO if str(nome) in caixas else "/Off")
            a[NameObject("/V")] = estado
            a[NameObject("/AS")] = estado
    w.set_need_appearances_writer(True)
    saida = io.BytesIO()
    w.write(saida)
    return saida.getvalue()


def _linhas_no_formulario(linhas: list[dict], txt: dict, caixas: set[str]) -> None:
    total = 0
    for i, ln in enumerate(linhas):
        n = 20 + i
        if not ln.get("entregou"):
            continue
        if ln.get("participou"):
            caixas.add(f"901_{n}_CheckBox")
        if ln.get("estudos"):
            txt[f"902_{n}_Text_C_SanSerif"] = ln["estudos"]
        if ln.get("auxiliar"):
            caixas.add(f"903_{n}_CheckBox")
        if ln.get("horas"):
            txt[f"904_{n}_S21_Value"] = ln["horas"]
            total += ln["horas"]
        if ln.get("observacoes"):
            txt[f"905_{n}_Text_SanSerif"] = str(ln["observacoes"])[:60]
    if total:
        txt["904_32_S21_Value"] = total


def s21_membro(membro: dict, linhas: list[dict], as_: int) -> bytes:
    txt = {"900_1_Text_SanSerif": membro.get("nome_oficial", ""), "900_2_Text_SanSerif": membro.get("data_nascimento", ""),
           "900_5_Text_SanSerif": membro.get("data_batismo", ""), "900_13_Text_C_SanSerif": as_}
    caixas: set[str] = set()
    if membro.get("genero") == "Masculino":
        caixas.add("900_3_CheckBox")
    elif membro.get("genero") == "Feminino":
        caixas.add("900_4_CheckBox")
    if membro.get("classe") == "Outras ovelhas":
        caixas.add("900_6_CheckBox")
    elif membro.get("classe") == "Ungido":
        caixas.add("900_7_CheckBox")
    for c in R.cargos(membro):
        if c in CARGO_CAMPO:
            caixas.add(CARGO_CAMPO[c])
    if R.eh_regular(membro):
        caixas.add(CARGO_CAMPO["Pioneiro regular"])
    _linhas_no_formulario(linhas, txt, caixas)
    return _preencher(txt, caixas)


def s21_total(titulo: str, linhas: list[dict], as_: int) -> bytes:
    txt = {"900_1_Text_SanSerif": titulo, "900_13_Text_C_SanSerif": as_}
    caixas: set[str] = set()
    _linhas_no_formulario(linhas, txt, caixas)
    return _preencher(txt, caixas)


# ══════════════════════════════════════════════════════════════════════════════
# S-88 e resumo (ReportLab)
# ══════════════════════════════════════════════════════════════════════════════
def _fmt(v) -> str:
    if v in (None, "", 0):
        return ""
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(v)


def s88(as_: int, meio: dict, fim: dict) -> bytes:
    """meio/fim = {chave: {qtd, total, media}}"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"S-88 — Assistência {as_}")
    larg, alt = A4
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(larg / 2, alt - 22 * mm, "REGISTRO DA ASSISTÊNCIA ÀS REUNIÕES CONGREGACIONAIS")
    y = alt - 34 * mm
    for titulo, dados in (("Reunião do meio de semana", meio), ("Reunião do fim de semana", fim)):
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, titulo)
        y -= 7 * mm
        cols = [20, 62, 100, 140, 180]
        cab = [f"Ano de serviço {as_}", "Qtd. de reuniões", "Assistência total", "Média por semana"]
        c.setFont("Helvetica-Bold", 8.5)
        meio_col = lambda i: (cols[i] + cols[i + 1]) / 2 * mm  # noqa: E731
        c.drawString(cols[0] * mm + 2, y, cab[0])
        for i, t in enumerate(cab[1:], 1):
            c.drawCentredString(meio_col(i), y, t)
        c.line(20 * mm, y - 2.5 * mm, 180 * mm, y - 2.5 * mm)
        y -= 7 * mm
        c.setFont("Helvetica", 9.5)
        medias = []
        for ch in R.meses_do_as(as_):
            d = dados.get(ch) or {}
            medias.append(d.get("media", 0))
            c.drawString(cols[0] * mm + 2, y, R.MESES_TITULO[R.partes(ch)[1] - 1])
            c.drawCentredString(meio_col(1), y, _fmt(d.get("qtd")))
            c.drawCentredString(meio_col(2), y, _fmt(d.get("total")))
            c.drawCentredString(meio_col(3), y, _fmt(d.get("media")))
            c.setStrokeGray(.8)
            c.line(20 * mm, y - 2 * mm, 180 * mm, y - 2 * mm)
            c.setStrokeGray(0)
            y -= 6.2 * mm
        c.setFont("Helvetica-Bold", 9.5)
        c.drawRightString(cols[3] * mm - 4, y, "Assistência média por mês")
        c.drawCentredString(meio_col(3), y, _fmt(R.media_anual(medias)))
        y -= 14 * mm
    c.setFont("Helvetica", 7)
    c.drawString(20 * mm, 12 * mm, "S-88-T · gerado pela Secretaria (hub Wendley Desenvolvimento)")
    c.save()
    return buf.getvalue()


def resumo_periodo(titulo: str, s1s: list[dict], s10_: dict | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    pag = landscape(A4)
    c = canvas.Canvas(buf, pagesize=pag)
    c.setTitle(titulo)
    larg, alt = pag
    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, alt - 16 * mm, titulo)
    cab = ["Mês", "Ativos", "Média fim sem.", "Pub. relat.", "Pub. estudos", "Aux. relat.", "Aux. horas",
           "Aux. estudos", "Reg. relat.", "Reg. horas", "Reg. estudos"]
    x0, w0, wn = 15 * mm, 34 * mm, 21.5 * mm
    y = alt - 28 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x0, y, cab[0])
    for i, t in enumerate(cab[1:]):
        c.drawRightString(x0 + w0 + wn * (i + 1), y, t)
    c.line(x0, y - 2.5 * mm, x0 + w0 + wn * 10 + 2, y - 2.5 * mm)
    y -= 8 * mm
    c.setFont("Helvetica", 9.5)
    for s in s1s:
        vals = [s["ativos"], s["media_fim_semana"], s["publicadores"]["relatorios"], s["publicadores"]["estudos"],
                s["auxiliares"]["relatorios"], s["auxiliares"]["horas"], s["auxiliares"]["estudos"],
                s["regulares"]["relatorios"], s["regulares"]["horas"], s["regulares"]["estudos"]]
        c.drawString(x0, y, s["rotulo"])
        for i, v in enumerate(vals):
            c.drawRightString(x0 + w0 + wn * (i + 1), y, _fmt(v) or "0")
        y -= 6.5 * mm
        if y < 30 * mm:
            c.showPage()
            y = alt - 20 * mm
            c.setFont("Helvetica", 9.5)
    if s10_:
        y -= 6 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x0, y, f"Análise da congregação (S-10) — ano de serviço {s10_['ano_servico']}")
        c.setFont("Helvetica", 9.5)
        itens = [("Média fim de semana", s10_["media_fim_semana"]), ("Média meio de semana", s10_["media_meio_semana"]),
                 ("Publicadores ativos", s10_["ativos"]), ("Novos inativos", len(s10_["novos_inativos"])),
                 ("Reativados", len(s10_["reativados"]))]
        for rot, v in itens:
            y -= 6 * mm
            c.drawString(x0 + 4 * mm, y, f"{rot}: {_fmt(v) or '0'}")
    c.save()
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# ZIP DA VISITA
# ══════════════════════════════════════════════════════════════════════════════
def zip_visita(*, raiz: str, anos: list[int], membros: dict[str, dict], linhas: list[dict], ate: str,
               situacoes: dict[str, str], assist: dict, s1s: list[dict], s10_: dict | None,
               pastas: list[dict], por_grupo: bool, grupos: dict[str, str], anexos: list[tuple[str, bytes]]) -> bytes:
    """
    situacoes: {membro_id: "ativo"|"inativo"|...} no fim do período
    pastas:    [{"caminho": "Dianteira/Família X", "membros": [ids]}]
    anexos:    [(caminho_relativo, bytes)]  → vão para <raiz>/Contas/...
    """
    buf = io.BytesIO()
    raiz = nome_arquivo(raiz)
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for as_ in anos:
            reg = f"{raiz}/Registros {as_}"
            cache: dict[str, bytes] = {}
            for mid, m in sorted(membros.items(), key=lambda kv: R.normalizar(kv[1].get("nome_oficial") or kv[0])):
                linhas_m = R.cartao(mid, as_, linhas)
                if not any(ln["entregou"] for ln in linhas_m) and situacoes.get(mid) in ("fora", None):
                    continue
                pdf = s21_membro(m, linhas_m, as_)
                cache[mid] = pdf
                nome = nome_arquivo(m.get("nome_oficial") or mid) + ".pdf"
                if situacoes.get(mid) == "inativo" or situacoes.get(mid) == "sem_relatorio":
                    pasta = "Inativos"
                elif R.eh_regular(m):
                    pasta = f"Pioneiros {as_}"
                else:
                    pasta = f"Publicadores {as_}"
                z.writestr(f"{reg}/{pasta}/{nome}", pdf)
                if por_grupo and m.get("grupo"):
                    z.writestr(f"{reg}/Por grupo/{nome_arquivo(grupos.get(m['grupo'], m['grupo']))}/{nome}", pdf)
            for cat, titulo in ((R.PUB, "PUBLICADORES"), (R.REG, "PIONEIROS REGULARES"), (R.AUX, "PIONEIROS AUXILIARES")):
                z.writestr(f"{reg}/{titulo} {as_}.pdf", s21_total(f"{titulo} {as_}", R.cartao_total(cat, as_, linhas), as_))
            for p in pastas:
                caminho = "/".join(nome_arquivo(x) for x in str(p.get("caminho", "")).split("/") if x.strip())
                if not caminho:
                    continue
                for mid in p.get("membros") or []:
                    if mid in cache:
                        nome = nome_arquivo(membros[mid].get("nome_oficial") or mid) + ".pdf"
                        z.writestr(f"{reg}/{caminho}/{nome}", cache[mid])
            z.writestr(f"{raiz}/S-88 Assistência {as_}.pdf",
                       s88(as_, {c: v for c, v in (assist.get("meio") or {}).items() if R.ano_servico(c) == as_},
                           {c: v for c, v in (assist.get("fim") or {}).items() if R.ano_servico(c) == as_}))
        z.writestr(f"{raiz}/Fechamentos do período.pdf", resumo_periodo(f"Fechamentos mensais até {R.rotulo(ate)}", s1s, s10_))
        for caminho, dados in anexos:
            partes_ = [nome_arquivo(x) for x in str(caminho).replace("\\", "/").split("/") if x.strip() and x not in (".", "..")]
            if partes_:
                z.writestr(f"{raiz}/Contas/" + "/".join(partes_), dados)
    return buf.getvalue()
