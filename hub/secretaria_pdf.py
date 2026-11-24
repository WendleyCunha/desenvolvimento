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
import threading
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


_MODELO_CACHE: dict = {}
_MODELO_TRAVA = threading.Lock()


def _novo_do_modelo() -> PdfWriter:
    """Cópia do formulário S-21 em branco. O modelo é lido UMA vez e fica em memória:
    no ZIP da visita (centenas de cartões) isso corta a maior parte do tempo."""
    with _MODELO_TRAVA:
        leitor = _MODELO_CACHE.get("leitor")
        if leitor is None:
            leitor = _MODELO_CACHE["leitor"] = PdfReader(io.BytesIO(MODELO_S21.read_bytes()))
        return PdfWriter(clone_from=leitor)


def _preencher(campos_txt: dict, caixas: set[str], carimbo: str = "") -> bytes:
    w = _novo_do_modelo()
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
    if carimbo:   # contato de emergência na mesma passada (sem reabrir o PDF)
        larg, alt = float(pagina.mediabox.width), float(pagina.mediabox.height)
        sobre = _pagina_carimbo(carimbo, larg, alt)
        if sobre is not None:
            pagina.merge_page(sobre)
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


def _pagina_carimbo(telefone: str, larg: float, alt: float):
    """Página transparente com 'Contato de emergência: …' logo abaixo da linha 'Total' do S-21."""
    telefone = " ".join(str(telefone or "").split())
    if not telefone:
        return None
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(larg, alt) if larg and alt else A4)
    y = 366   # a linha "Total" do S-21-T vai de 385 a 402 (pontos); 1 cm abaixo dela
    c.setFont("Helvetica-Bold", 9)
    c.drawString(19, y, "Contato de emergência:")
    c.setFont("Helvetica", 9)
    largura_max = (larg or A4[0]) - 19 - 125
    linha, linhas = "", []
    for palavra in telefone.split():   # quebra em até 2 linhas
        teste = (linha + " " + palavra).strip()
        if c.stringWidth(teste, "Helvetica", 9) > largura_max and linha:
            linhas.append(linha)
            linha = palavra
        else:
            linha = teste
    linhas.append(linha)
    for i, t in enumerate(linhas[:2]):
        c.drawString(125, y - 12 * i, t)
    c.save()
    return PdfReader(io.BytesIO(buf.getvalue())).pages[0]


def _carimbo_emergencia(pdf: bytes, telefone: str) -> bytes:
    """Escreve o contato de emergência na parte branca do S-21, logo abaixo da linha 'Total'."""
    if not " ".join(str(telefone or "").split()):
        return pdf
    leitor = PdfReader(io.BytesIO(pdf))
    larg, alt = float(leitor.pages[0].mediabox.width), float(leitor.pages[0].mediabox.height)
    w = PdfWriter(clone_from=leitor)
    w.pages[0].merge_page(_pagina_carimbo(telefone, larg, alt))
    saida = io.BytesIO()
    w.write(saida)
    return saida.getvalue()


def s21_membro(membro: dict, linhas: list[dict], as_: int) -> bytes:
    return _s21_membro_form(membro, linhas, as_, carimbo=membro.get("telefone_emergencia", ""))


def _s21_membro_form(membro: dict, linhas: list[dict], as_: int, carimbo: str = "") -> bytes:
    txt = {"900_1_Text_SanSerif": membro.get("nome_oficial") or membro.get("id") or "", "900_2_Text_SanSerif": membro.get("data_nascimento", ""),
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
    return _preencher(txt, caixas, carimbo)


def achatar(pdf: bytes) -> bytes:
    """Transforma os campos do formulário em desenho fixo (para juntar vários S-21 num PDF só sem
    os campos de mesmo nome se misturarem). Funciona no pypdf 4.x: desenha a aparência (/AP) de cada campo."""
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject as N

    leitor = PdfReader(io.BytesIO(pdf))
    w = PdfWriter(clone_from=leitor)
    for pagina in w.pages:
        anots = pagina.get("/Annots")
        if not anots:
            continue
        recursos = pagina.get("/Resources")
        recursos = recursos.get_object() if recursos is not None else DictionaryObject()
        xobjs = recursos.get("/XObject")
        xobjs = xobjs.get_object() if xobjs is not None else DictionaryObject()
        cmds, n = [], 0
        for ref in anots:
            a = ref.get_object()
            if a.get("/Subtype") != "/Widget":
                continue
            ap = a.get("/AP")
            if not ap:
                continue
            normal = ap.get_object().get("/N")
            if normal is None:
                continue
            normal = normal.get_object()
            if "/BBox" not in normal:   # caixa de seleção: um desenho por estado
                estado = a.get("/AS")
                if estado is None or str(estado) == "/Off" or estado not in normal:
                    continue
                normal = normal[estado].get_object()
            r = [float(x) for x in a["/Rect"]]
            bbox = [float(x) for x in normal.get("/BBox", [0, 0, r[2] - r[0], r[3] - r[1]])]
            nome = f"/Fl{n}"
            n += 1
            xobjs[N(nome)] = w._add_object(normal) if not hasattr(normal, "indirect_reference") or normal.indirect_reference is None else normal.indirect_reference
            cmds.append(f"q 1 0 0 1 {r[0] - bbox[0]:.3f} {r[1] - bbox[1]:.3f} cm {nome} Do Q")
        recursos[N("/XObject")] = xobjs
        pagina[N("/Resources")] = recursos
        if cmds:
            extra = DecodedStreamObject()
            extra.set_data(("\n".join(cmds) + "\n").encode("latin-1"))
            conteudo = pagina.get("/Contents")
            lista = conteudo.get_object() if conteudo is not None else ArrayObject()
            if not isinstance(lista, ArrayObject):
                lista = ArrayObject([conteudo])
            lista.append(w._add_object(extra))
            pagina[N("/Contents")] = lista
        del pagina["/Annots"]
    if "/AcroForm" in w._root_object:
        del w._root_object["/AcroForm"]
    saida = io.BytesIO()
    w.write(saida)
    return saida.getvalue()


def _s21_achatado(membro: dict, linhas: list[dict], as_: int) -> bytes:
    """S-21 sem campos (preenchido e 'impresso'), com o contato de emergência."""
    return _carimbo_emergencia(achatar(_s21_membro_form(membro, linhas, as_)), membro.get("telefone_emergencia", ""))


# ── Texto formatado da carta (editor do popup) ──────────────────────────────────────────────────
# O editor (contenteditable) gera HTML; aqui ele é LIMPO (só negrito, itálico, sublinhado, cor, tamanho,
# alinhamento, quebras) e convertido para o PDF. O mesmo HTML limpo é o que volta para a tela.
TAMANHOS_PT = {1: 8, 2: 10, 3: None, 4: 13, 5: 16, 6: 20, 7: 26}   # <font size=N> do editor → pontos (3 = tamanho base)
FMT_PADRAO = {"fonte": 10.5, "entrelinhas": 1.3, "esp_par": 0, "esp_cab": 4, "alinha_data": "right"}
_ALINHAS = {"left", "center", "right", "justify"}


def _cor_ok(v: str) -> str | None:
    v = str(v or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", v):
        return v
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        return "#" + "".join(ch * 2 for ch in v[1:])
    m = re.fullmatch(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*[\d.]+)?\s*\)", v)
    if m:
        return "#" + "".join(f"{min(int(x), 255):02x}" for x in m.groups())
    return None


def _tam_de_css(v: str) -> int | None:
    """font-size do CSS → degrau 1..7 do editor."""
    m = re.fullmatch(r"\s*([\d.]+)\s*(px|pt)?\s*", str(v or ""))
    if not m:
        return {"x-small": 1, "small": 2, "medium": 3, "large": 4, "x-large": 5, "xx-large": 6, "xxx-large": 7}.get(str(v).strip())
    pt = float(m.group(1)) * (0.75 if (m.group(2) or "px") == "px" else 1)
    return min(TAMANHOS_PT, key=lambda k: abs((TAMANHOS_PT[k] or 10.5) - pt))


def ler_html_carta(html: str) -> list[dict]:
    """HTML do editor → parágrafos [{alinha, itens:[('t', texto, estilo) | ('br',)]}]. Tudo que não é permitido é ignorado."""
    from html.parser import HTMLParser

    blocos_tag = {"div", "p", "li", "h1", "h2", "h3", "h4", "blockquote"}

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.pars, self.atual, self.pilha, self.alinhas, self.ignorar = [], None, [{}], [], 0

        def _par(self):
            if self.atual is None:
                self.atual = {"alinha": next((a for a in reversed(self.alinhas) if a), "left"), "itens": []}
            return self.atual

        def _fecha(self):
            if self.atual is not None:
                self.pars.append(self.atual)
                self.atual = None

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag in ("script", "style", "head", "title"):
                self.ignorar += 1
                return
            estilo = {}
            for d in str(a.get("style") or "").split(";"):
                if ":" in d:
                    k, v = d.split(":", 1)
                    estilo[k.strip().lower()] = v.strip().lower()
            if tag in blocos_tag:
                self._fecha()
                al = (estilo.get("text-align") or a.get("align") or "").lower()
                self.alinhas.append(al if al in _ALINHAS else None)
                if tag.startswith("h"):
                    self.pilha.append({**self.pilha[-1], "b": True})
                return
            if tag == "br":
                self._par()["itens"].append(("br",))
                return
            novo = dict(self.pilha[-1])
            if tag in ("b", "strong") or estilo.get("font-weight") in ("bold", "700", "600", "800", "900"):
                novo["b"] = True
            if tag in ("i", "em") or estilo.get("font-style") == "italic":
                novo["i"] = True
            if tag == "u" or "underline" in estilo.get("text-decoration", ""):
                novo["u"] = True
            cor = _cor_ok(a.get("color") or estilo.get("color"))
            if cor:
                novo["cor"] = cor
            tam = None
            if a.get("size") and str(a["size"]).strip().isdigit():
                tam = min(max(int(a["size"]), 1), 7)
            elif estilo.get("font-size"):
                tam = _tam_de_css(estilo["font-size"])
            if tam:
                novo["tam"] = tam
            if tag in ("b", "strong", "i", "em", "u", "font", "span", "a", "sub", "sup", "small", "big"):
                self.pilha.append(novo)

        def handle_endtag(self, tag):
            if tag in ("script", "style", "head", "title"):
                self.ignorar = max(0, self.ignorar - 1)
                return
            if tag in blocos_tag:
                self._fecha()
                if self.alinhas:
                    self.alinhas.pop()
                if tag.startswith("h") and len(self.pilha) > 1:
                    self.pilha.pop()
                return
            if tag in ("b", "strong", "i", "em", "u", "font", "span", "a", "sub", "sup", "small", "big") and len(self.pilha) > 1:
                self.pilha.pop()

        def handle_data(self, data):
            if self.ignorar or not data:
                return
            data = data.replace("\r", "").replace("\n", " ").replace("\xa0", " ")
            if not data.strip() and self.atual is None:
                return
            self._par()["itens"].append(("t", data, dict(self.pilha[-1])))

    p = P()
    p.feed(str(html or "")[:80000])
    p.close()
    p._fecha()
    return p.pars[:400]


def html_limpo_carta(html: str) -> str:
    """O HTML que fica gravado e volta para o editor/prévia (sem nada além do permitido)."""
    from xml.sax.saxutils import escape, quoteattr

    out = []
    for par in ler_html_carta(html):
        partes = []
        for it in par["itens"]:
            if it[0] == "br":
                partes.append("<br>")
                continue
            _, txt, e = it
            s = escape(txt)
            if e.get("u"):
                s = f"<u>{s}</u>"
            if e.get("i"):
                s = f"<i>{s}</i>"
            if e.get("b"):
                s = f"<b>{s}</b>"
            if e.get("cor") or e.get("tam"):
                at = (f" color={quoteattr(e['cor'])}" if e.get("cor") else "") + (f' size="{e["tam"]}"' if e.get("tam") else "")
                s = f"<font{at}>{s}</font>"
            partes.append(s)
        dentro = "".join(partes) or "<br>"
        al = par["alinha"]
        out.append(f'<div style="text-align:{al}">{dentro}</div>' if al != "left" else f"<div>{dentro}</div>")
    return "".join(out)


def _paragrafos_reportlab(html: str, fmt: dict):
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer
    from xml.sax.saxutils import escape

    base = float(fmt.get("fonte") or 10.5)
    fator = float(fmt.get("entrelinhas") or 1.3)
    esp = float(fmt.get("esp_par") or 0)
    al_map = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}
    saida = []
    for par in ler_html_carta(html):
        partes, maior, so_br = [], base, True
        for it in par["itens"]:
            if it[0] == "br":
                partes.append("<br/>")
                continue
            _, txt, e = it
            if txt.strip():
                so_br = False
            s = escape(txt).replace("  ", " &nbsp;")
            if e.get("u"):
                s = f"<u>{s}</u>"
            if e.get("i"):
                s = f"<i>{s}</i>"
            if e.get("b"):
                s = f"<b>{s}</b>"
            pt = TAMANHOS_PT.get(e.get("tam")) if e.get("tam") else None
            if pt:
                maior = max(maior, pt)
            if e.get("cor") or pt:
                attrs = ""
                if e.get("cor"):
                    attrs += f' color="{e["cor"]}"'
                if pt:
                    attrs += f" size={pt}"
                s = f"<font{attrs}>{s}</font>"
            partes.append(s)
        if so_br:   # linha em branco
            saida.append(Spacer(1, base * fator + esp))
            continue
        while partes and partes[-1] == "<br/>":
            partes.pop()
        estilo = ParagraphStyle("p", fontName="Helvetica", fontSize=base, leading=maior * fator,
                                alignment=al_map.get(par["alinha"], TA_LEFT), spaceAfter=esp)
        saida.append(Paragraph("".join(partes), estilo))
    return saida


def texto_para_html_carta(destino: str, referencia: str, conteudo: str) -> str:
    """Carta antiga (campos de texto) → HTML do editor, para abrir no formato novo."""
    from xml.sax.saxutils import escape

    linhas = list(str(destino or "").splitlines()) + [""] + [str(referencia or "")] + [""] + str(conteudo or "").splitlines()
    return "".join(f"<div>{escape(x) if x.strip() else '<br>'}</div>" for x in linhas)


CABECALHO_CARTA = ["Congregação Parque Aliança (72249)", "Av. Felipe Carrilo Puerto, 827 – Jardim Magdalena",
                   "São Paulo – SP          CEP 05890 – 000."]


def carta_transferencia(*, data: str, destino: str = "", referencia: str = "", conteudo: str = "",
                        cabecalho: list[str] | None = None, assinaturas_png: bytes | None = None,
                        corpo_html: str | None = None, fmt: dict | None = None) -> bytes:
    """Carta de mudança de publicador no modelo da congregação (cabeçalho e assinaturas fixos)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Frame, Paragraph
    from xml.sax.saxutils import escape

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(referencia or "Carta de transferência")
    larg, alt = A4
    cab = [x for x in (cabecalho or CABECALHO_CARTA) if str(x).strip()] or CABECALHO_CARTA
    y = alt - 30 * mm
    for i, t in enumerate(cab):
        if i == 0:
            c.setFont("Helvetica-Bold", 15)
        else:
            c.setFont("Helvetica-BoldOblique", 12)
        c.drawCentredString(larg / 2, y, str(t))
        y -= 6.5 * mm
    f_ = {**FMT_PADRAO, **(fmt or {})}
    y -= float(f_["esp_cab"]) * mm
    c.setFont("Helvetica-Bold", float(f_["fonte"]))
    al_data = f_.get("alinha_data")
    if al_data == "left":
        c.drawString(25 * mm, y, str(data or ""))
    elif al_data == "center":
        c.drawCentredString(larg / 2, y, str(data or ""))
    else:
        c.drawRightString(larg - 25 * mm, y, str(data or ""))
    if corpo_html:   # carta feita no editor com formatação
        blocos = _paragrafos_reportlab(corpo_html, f_)
    else:            # carta antiga (só texto)
        corpo = ParagraphStyle("corpo", fontName="Helvetica", fontSize=10.5, leading=14)
        blocos = []
        blocos.append(Paragraph("<br/>".join(escape(x) for x in str(destino or "").splitlines()), corpo))
        blocos.append(Paragraph("&nbsp;", corpo))
        blocos.append(Paragraph(escape(str(referencia or "")), corpo))
        blocos.append(Paragraph("&nbsp;", corpo))
        for par in re.split(r"\n\s*\n", str(conteudo or "").strip()):
            blocos.append(Paragraph("<br/>".join(escape(x) for x in par.splitlines()), corpo))
            blocos.append(Paragraph("&nbsp;", ParagraphStyle("esp", fontSize=4, leading=5)))
    alt_assin = 34 * mm
    margem_baixo = 20 * mm                # páginas do meio: texto até 2 cm do fim da folha
    base_assin = 30 * mm + alt_assin      # última página: texto termina acima das assinaturas
    topo_pag = alt - 25 * mm              # páginas 2, 3…: começam 2,5 cm abaixo do topo

    def _frame(topo, base):
        return Frame(25 * mm, base, larg - 50 * mm, max(topo - base, 10), showBoundary=0, leftPadding=0, rightPadding=0)

    def _cabe_tudo(lista, topo):
        """Testa (num rascunho) se o que falta cabe acima das assinaturas."""
        teste = list(lista)
        _frame(topo, base_assin).addFromList(teste, canvas.Canvas(io.BytesIO(), pagesize=A4))
        return not teste

    topo = y - 10 * mm
    pagina = 1
    while True:
        if not blocos or _cabe_tudo(blocos, topo):      # última página: texto + assinaturas
            _frame(topo, base_assin).addFromList(blocos, c)
            break
        antes = len(blocos)
        teste = list(blocos)
        _frame(topo, margem_baixo).addFromList(teste, canvas.Canvas(io.BytesIO(), pagesize=A4))
        if not teste:
            # O resto cabe na folha, mas não junto com as assinaturas: escreve só até o limite das assinaturas
            # e leva o final do texto para a próxima página (a assinatura nunca fica sozinha numa página).
            _frame(topo, base_assin).addFromList(blocos, c)
        else:
            _frame(topo, margem_baixo).addFromList(blocos, c)   # página cheia; o resto vai para a próxima
        if not blocos:
            break
        if len(blocos) == antes and pagina > 60:             # proteção: nunca entra em laço infinito
            break
        c.showPage()
        pagina += 1
        topo = topo_pag
        c.setFont("Helvetica", 7.5)
        c.drawRightString(larg - 25 * mm, alt - 15 * mm, f"(continuação — página {pagina})")
    if assinaturas_png:
        try:
            img = ImageReader(io.BytesIO(assinaturas_png))
            iw, ih = img.getSize()
            w_ = min(150 * mm, larg - 50 * mm)
            h_ = w_ * ih / iw
            if h_ > alt_assin:
                h_ = alt_assin
                w_ = h_ * iw / ih
            c.drawImage(img, (larg - w_) / 2, 30 * mm, w_, h_, mask="auto")
        except Exception:  # noqa: BLE001 — imagem inválida: a carta sai sem as assinaturas
            assinaturas_png = None
    if not assinaturas_png:
        c.setFont("Helvetica", 8)
        for i, rot in enumerate(("Coordenador", "Secretário", "Superintendente de Serviço")):
            x = 25 * mm + i * (larg - 50 * mm) / 3
            c.line(x + 4 * mm, 45 * mm, x + (larg - 50 * mm) / 3 - 4 * mm, 45 * mm)
            c.drawCentredString(x + (larg - 50 * mm) / 6, 41 * mm, rot)
    c.save()
    return buf.getvalue()


def juntar(pdfs: list[bytes]) -> bytes:
    w = PdfWriter()
    for b in pdfs:
        for pg in PdfReader(io.BytesIO(b)).pages:
            w.add_page(pg)
    saida = io.BytesIO()
    w.write(saida)
    return saida.getvalue()


def pacote_transferencia(carta: bytes, membro: dict, cartoes: list[tuple[int, list[dict]]]) -> bytes:
    """Carta + um S-21 (achatado) por ano de serviço."""
    return juntar([carta] + [_s21_achatado(membro, linhas, as_) for as_, linhas in cartoes])


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


# ══════════════════════════════════════════════════════════════════════════════
# LEITURA de cartões S-21 (os que o JW Hub exporta) — para importar o cadastro
# Lê direto as "anotações" da página: funciona também nos cartões em que o PDF
# perdeu o formulário (AcroForm) mas os valores continuam nos campos.
# ══════════════════════════════════════════════════════════════════════════════
def _campos_pagina(dados: bytes) -> dict:
    import logging
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    leitor = PdfReader(io.BytesIO(dados))
    if not leitor.pages:
        return {}
    campos = {}
    for a in leitor.pages[0].get("/Annots") or []:
        a = a.get_object()
        nome = a.get("/T")
        if nome is None and a.get("/Parent"):
            nome = a["/Parent"].get_object().get("/T")
        if nome is None:
            continue
        tipo = a.get("/FT") or (a["/Parent"].get_object().get("/FT") if a.get("/Parent") else None)
        if tipo == "/Btn":
            v = a.get("/V") or a.get("/AS")
            campos[str(nome)] = v is not None and str(v) not in ("/Off", "Off", "")
        else:
            campos[str(nome)] = str(a.get("/V") or "").strip()
    return campos


def ler_s21(dados: bytes) -> dict | None:
    """{nome, data_nascimento, data_batismo, genero, classe, cargo[], regular, ano, meses[]} ou None."""
    try:
        c = _campos_pagina(dados)
    except Exception:  # noqa: BLE001
        return None
    nome = " ".join(str(c.get("900_1_Text_SanSerif", "")).split())
    if not nome:
        return None
    marcado = lambda k: bool(c.get(k))  # noqa: E731
    cargo = [rot for rot, campo in CARGO_CAMPO.items() if marcado(campo)]
    try:
        ano = int(str(c.get("900_13_Text_C_SanSerif", "")).strip()[:4])
    except ValueError:
        ano = 0

    def n(v):
        try:
            return int(float(str(v).replace(",", ".")))
        except ValueError:
            return 0

    meses = []
    if ano:
        for i, ch in enumerate(R.meses_do_as(ano)):
            k = 20 + i
            part = marcado(f"901_{k}_CheckBox")
            est, hrs = n(c.get(f"902_{k}_Text_C_SanSerif", "")), n(c.get(f"904_{k}_S21_Value", ""))
            obs = str(c.get(f"905_{k}_Text_SanSerif", "") or "").strip()
            if part or est or hrs:
                meses.append({"chave": ch, "participou": part, "estudos": est, "horas": hrs,
                              "auxiliar": marcado(f"903_{k}_CheckBox"), "observacoes": obs})
    total = R.normalizar(nome)
    eh_total = any(total.startswith(x) for x in ("publicadores", "pioneiros regulares", "pioneiros auxiliares", "consolidado"))
    return {"nome": nome, "data_nascimento": str(c.get("900_2_Text_SanSerif", "")).strip(),
            "data_batismo": str(c.get("900_5_Text_SanSerif", "")).strip(),
            "genero": "Masculino" if marcado("900_3_CheckBox") else "Feminino" if marcado("900_4_CheckBox") else "",
            "classe": "Outras ovelhas" if marcado("900_6_CheckBox") else "Ungido" if marcado("900_7_CheckBox") else "",
            "cargo": cargo, "regular": "Pioneiro regular" in cargo, "ano": ano, "meses": meses, "total": eh_total}


def ler_arquivos(arquivos: list[tuple[str, bytes]]) -> list[dict]:
    """Aceita PDFs soltos e ZIPs (com pastas). Devolve um item por cartão lido."""
    saida = []
    for nome, dados in arquivos:
        if nome.lower().endswith(".zip") or dados[:2] == b"PK":
            try:
                z = zipfile.ZipFile(io.BytesIO(dados))
            except zipfile.BadZipFile:
                continue
            for info in z.infolist():
                if info.filename.lower().endswith(".pdf") and info.file_size < 15 * 1024 * 1024:
                    saida.extend(ler_arquivos([(info.filename, z.read(info))]))
        elif nome.lower().endswith(".pdf") or dados[:4] == b"%PDF":
            lido = ler_s21(dados)
            if lido:
                caminho = nome.replace("\\", "/")
                pasta = caminho.split("/")[-2] if "/" in caminho else ""
                saida.append({**lido, "arquivo": caminho, "pasta": pasta})
    return saida
