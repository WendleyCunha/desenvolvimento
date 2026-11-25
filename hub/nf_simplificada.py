"""
hub/nf_simplificada.py — DANFE SIMPLIFICADO – ETIQUETA a partir do PDF das NF-e completas
─────────────────────────────────────────────────────────────────────────────
O sistema fiscal (TOTVS) emite o DANFE completo (A4). Aqui:

  1. ler_pdf(bytes)  → lê o PDF com TODAS as notas (uma ou mais páginas por nota) e devolve os dados
     de cada NF-e: chave (conferida pelo dígito verificador), número, série, protocolo, emissão,
     emitente, destinatário, itens, volumes, peso e o "Pedido de venda" das informações complementares.
  2. etiquetas_pdf(notas) → um PDF com uma ETIQUETA 100 × 150 mm por nota, para impressora térmica,
     com os campos mínimos do DANFE Simplificado – Etiqueta (NT 2020.004 / Ajuste SINIEF 07/05)
     e o bloco "Entrega" (pedido, itens, volumes) para o motorista. A palavra-chave NUNCA vai na etiqueta.

Sem custo: só pypdf e reportlab (já no requirements).
"""
from __future__ import annotations

import io
import re

UF_COD = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
          "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
          "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"}


# ══════════════════════════════════════════════════════════════════════════════
# CHAVE DE ACESSO
# ══════════════════════════════════════════════════════════════════════════════
def so_digitos(x) -> str:
    return re.sub(r"\D", "", str(x or ""))


def chave_valida(chave: str) -> bool:
    """44 dígitos e dígito verificador (módulo 11, pesos 2..9 da direita para a esquerda)."""
    c = so_digitos(chave)
    if len(c) != 44:
        return False
    soma, peso = 0, 2
    for d in reversed(c[:43]):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - soma % 11
    return int(c[43]) == (0 if dv >= 10 else dv)


def partes_da_chave(chave: str) -> dict:
    c = so_digitos(chave)
    return {"uf": UF_COD.get(c[0:2], ""), "aamm": c[2:6], "cnpj": c[6:20], "modelo": c[20:22],
            "serie": str(int(c[22:25])).zfill(3), "numero": c[25:34]}


def fmt_chave(chave: str) -> str:
    c = so_digitos(chave)
    return " ".join(c[i:i + 4] for i in range(0, len(c), 4))


def fmt_numero(n: str) -> str:
    d = so_digitos(n).zfill(9)[-9:]
    return f"{d[0:3]}.{d[3:6]}.{d[6:9]}"


def fmt_cnpj(c: str) -> str:
    d = so_digitos(c)
    if len(d) == 14:
        return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"
    if len(d) == 11:
        return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"
    return str(c or "")


# ══════════════════════════════════════════════════════════════════════════════
# LEITURA DO DANFE COMPLETO
# ══════════════════════════════════════════════════════════════════════════════
RE_CHAVE = re.compile(r"(?<!\d)((?:\d{4}\s?){10}\d{4})(?!\d)")
RE_ITEM = re.compile(r"^(?P<cod>\S+)[ \t]+(?P<desc>[^\n]+?)[ \t]+(?P<ncm>\d{8})[ \t]*\n[ \t]*(?P<cst>\d/?\d{2,3})[ \t]*(?P<cfop>\d{4})[ \t]*(?P<un>[A-Za-z]{1,6})[ \t]+(?P<qtd>\d{1,3}(?:\.\d{3})*,\d{4}|\d+,\d{2})", re.M)


def _entre(t: str, a: str, b: str) -> str:
    m = re.search(re.escape(a) + r"\s*\n?(.*?)\s*" + re.escape(b), t, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _num_br(s) -> float:
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _ler_pagina(t: str) -> dict | None:
    """Dados de UMA página do DANFE (texto do pypdf, modo padrão: rótulo e valor colados)."""
    chaves = [so_digitos(m.group(1)) for m in RE_CHAVE.finditer(t)]
    chave = next((c for c in chaves if chave_valida(c)), "")
    if not chave:
        return None
    pc = partes_da_chave(chave)
    nf = {"chave": chave, "numero": pc["numero"].lstrip("0") or "0", "serie": pc["serie"], "modelo": pc["modelo"],
          "emit_cnpj": pc["cnpj"], "emit_uf": pc["uf"]}
    m = re.search(r"(\d{15})\s*-\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", t)
    nf["protocolo"] = f"{m.group(1)} - {re.sub(r'\s+', ' ', m.group(2))}" if m else ""
    m = re.search(r"RECEBEMOS DE\s+(.+?)\s+OS PRODUTOS", t, re.S)
    nf["emit_nome"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    if not nf["emit_nome"]:
        nf["emit_nome"] = _entre(t, "IDENTIFICAÇÃO DO EMITENTE", "\n")
    m = re.search(r"INSCRIÇÃO ESTADUAL\s*\n\s*(\d[\d.\-/]*)", t)
    nf["emit_ie"] = m.group(1) if m else ""
    m = re.search(r"([01])\s*-\s*SAÍDA\s+([01])\b", t) or re.search(r"1 - SAÍDA\s*([01])", t)
    tp = (m.group(m.lastindex) if m else "1")
    nf["tipo"] = "1 - SAÍDA" if tp == "1" else "0 - ENTRADA"
    m = re.search(r"EMISSÃO:\s*(\d{2}/\d{2}/\d{4})", t)
    nf["emissao"] = m.group(1) if m else ""
    m = re.search(r"VALOR TOTAL:\s*R\$\s*([\d.]+,\d{2})", t)
    nf["valor"] = m.group(1) if m else _entre(t, "V. TOTAL DA NOTA", "\n")
    # destinatário (bloco DESTINATÁRIO / REMETENTE)
    d = t.split("DESTINATÁRIO / REMETENTE", 1)[-1]
    nf["dest_nome"] = _entre(d, "NOME / RAZÃO SOCIAL", "CNPJ / CPF")
    nf["dest_doc"] = _entre(d, "CNPJ / CPF", "DATA DA EMISSÃO")
    if not nf["emissao"]:
        nf["emissao"] = _entre(d, "DATA DA EMISSÃO", "\n")
    nf["dest_end"] = _entre(d, "ENDEREÇO", "BAIRRO / DISTRITO")
    nf["dest_bairro"] = _entre(d, "BAIRRO / DISTRITO", "CEP")
    nf["dest_cep"] = _entre(d, "CEP", "DATA DA SAÍDA")
    nf["dest_cidade"] = _entre(d, "MUNICÍPIO", "UF")
    nf["dest_uf"] = _entre(d, "UF", "FONE")
    nf["dest_fone"] = _entre(d, "FONE / FAX", "INSCRIÇÃO ESTADUAL")
    ie = _entre(d, "INSCRIÇÃO ESTADUAL", "HORA DA SAÍDA")
    nf["dest_ie"] = ie if re.search(r"\d", ie) else ""
    # volumes e peso (bloco do transportador)
    v = t.split("TRANSPORTADOR / VOLUMES", 1)[-1]
    nf["volumes"] = _entre(v, "QUANTIDADE", "ESPÉCIE")
    nf["especie"] = _entre(v, "ESPÉCIE", "MARCA")
    nf["peso_bruto"] = _entre(v, "PESO BRUTO", "PESO LÍQUIDO")
    # itens
    p = t.split("DADOS DOS PRODUTOS / SERVIÇOS", 1)[-1].split("DADOS ADICIONAIS", 1)[0]
    nf["itens"] = [{"codigo": m.group("cod"), "desc": re.sub(r"\s+", " ", m.group("desc")).strip(), "un": m.group("un"),
                    "qtd": _num_br(m.group("qtd"))} for m in RE_ITEM.finditer(p)]
    m = re.search(r"Pedido de venda:\s*(\d+)", t, re.I)
    nf["pedido_origem"] = m.group(1) if m else ""
    m = re.search(r"Folha\s*(\d+)\s*/\s*(\d+)", t)
    nf["folha"] = (int(m.group(1)), int(m.group(2))) if m else (1, 1)
    # limpeza de campos que vieram vazios/compridos por diferença de layout
    for k in ("dest_uf", "emit_ie", "dest_cep"):
        nf[k] = nf[k][:12]
    return nf


def ler_pdf(dados: bytes) -> list[dict]:
    """Todas as NF-e do PDF, na ordem do arquivo. Notas com mais de uma folha viram uma só (itens somados)."""
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(dados))
    notas: dict[str, dict] = {}
    ordem: list[str] = []
    for pg in rd.pages:
        try:
            t = pg.extract_text() or ""
        except Exception:  # noqa: BLE001
            continue
        nf = _ler_pagina(t)
        if not nf:
            continue
        ch = nf["chave"]
        if ch in notas:
            base = notas[ch]
            base["itens"] += nf["itens"]
            for k, val in nf.items():
                if not base.get(k) and val:
                    base[k] = val
        else:
            notas[ch] = nf
            ordem.append(ch)
    out = []
    for ch in ordem:
        nf = notas[ch]
        nf.pop("folha", None)
        out.append(nf)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# ETIQUETA 100 × 150 mm
# ══════════════════════════════════════════════════════════════════════════════
LARG_MM, ALT_MM = 100, 150


def _corta(c, txt: str, fonte: str, tam: float, larg: float) -> str:
    txt = str(txt or "")
    if c.stringWidth(txt, fonte, tam) <= larg:
        return txt
    while txt and c.stringWidth(txt + "…", fonte, tam) > larg:
        txt = txt[:-1]
    return txt + "…"


def _quebra(c, txt: str, fonte: str, tam: float, larg: float, max_linhas: int = 2) -> list[str]:
    palavras, linhas, atual = str(txt or "").split(), [], ""
    for p in palavras:
        t = (atual + " " + p).strip()
        if c.stringWidth(t, fonte, tam) <= larg:
            atual = t
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        linhas[-1] = _corta(c, linhas[-1] + " …", fonte, tam, larg)
    return linhas


def _etiqueta(c, nf: dict, extra: dict | None, mostrar_valor: bool):
    from reportlab.graphics.barcode import code128
    from reportlab.lib.units import mm
    W, H, M = LARG_MM * mm, ALT_MM * mm, 4 * mm
    larg = W - 2 * M
    extra = extra or {}
    y = H - M

    def linha():
        c.setLineWidth(0.6)
        c.line(M, y, W - M, y)

    def titulo(t):
        c.setFont("Helvetica-Bold", 7)
        c.drawString(M, y, t.upper())

    def texto(t, tam=9, bold=False, x=M):
        f = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(f, tam)
        c.drawString(x, y, _corta(c, t, f, tam, W - M - x))

    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W / 2, y - 4 * mm, "DANFE SIMPLIFICADO - ETIQUETA")
    y -= 7 * mm
    linha()
    y -= 4 * mm
    titulo("Chave de acesso")
    bc = code128.Code128(so_digitos(nf["chave"]), barWidth=0.33 * mm, barHeight=13 * mm, quiet=False)
    y -= 14.5 * mm
    bc.drawOn(c, (W - bc.width) / 2, y)
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(W / 2, y, fmt_chave(nf["chave"]))
    y -= 4.5 * mm
    titulo("Protocolo de autorização de uso")
    y -= 4.2 * mm
    texto(nf.get("protocolo") or "—", 9, True)
    y -= 2.5 * mm
    linha()

    y -= 4 * mm
    titulo("Emitente")
    y -= 4.5 * mm
    texto(nf.get("emit_nome") or "", 10, True)
    y -= 4.2 * mm
    texto(f"CNPJ {fmt_cnpj(nf.get('emit_cnpj'))}   IE {nf.get('emit_ie') or '—'}   UF {nf.get('emit_uf') or '—'}", 8.5)
    y -= 2.5 * mm
    linha()

    y -= 4 * mm
    titulo("Dados da NF-e")
    y -= 5 * mm
    texto(f"Nº {fmt_numero(nf['numero'])}", 13, True)
    texto(f"Série {nf.get('serie') or ''}", 10, True, x=M + 42 * mm)
    texto(nf.get("tipo") or "1 - SAÍDA", 10, True, x=M + 64 * mm)
    y -= 4.2 * mm
    texto(f"Emissão: {nf.get('emissao') or '—'}" + (f"     Valor total: R$ {nf.get('valor')}" if mostrar_valor and nf.get("valor") else ""), 8.5)
    y -= 2.5 * mm
    linha()

    y -= 4 * mm
    titulo("Destinatário")
    y -= 4.8 * mm
    texto(nf.get("dest_nome") or "", 11, True)
    y -= 4.2 * mm
    doc = so_digitos(nf.get("dest_doc"))
    texto(("CNPJ " if len(doc) == 14 else "CPF ") + fmt_cnpj(doc) + f"   IE {nf.get('dest_ie') or 'ISENTO/NÃO CONTRIB.'}   UF {nf.get('dest_uf') or ''}", 8.5)
    end = extra.get("endereco") or ", ".join(x for x in (nf.get("dest_end"), nf.get("dest_bairro")) if x)
    for ln in _quebra(c, end, "Helvetica-Bold", 9.5, larg, 2):
        y -= 4.4 * mm
        texto(ln, 9.5, True)
    y -= 4.2 * mm
    cid = extra.get("cidade") or " - ".join(x for x in (nf.get("dest_cidade"), nf.get("dest_uf")) if x)
    cep = extra.get("cep") or nf.get("dest_cep")
    texto(cid + (f" - CEP {cep}" if cep else ""), 9.5, True)
    fone = extra.get("telefone") or nf.get("dest_fone")
    if fone:
        y -= 4.2 * mm
        texto(f"Fone: {fone}", 8.5)
    y -= 2.5 * mm
    linha()

    y -= 4 * mm
    titulo("Entrega")
    y -= 4.6 * mm
    ped = extra.get("pedido") or nf.get("pedido_origem")
    texto(f"Pedido {ped}" if ped else "Pedido —", 11, True)
    vol = nf.get("volumes")
    texto(f"{vol} {(nf.get('especie') or 'VOLUME(S)')}" + (f" · {nf['peso_bruto']} kg" if nf.get("peso_bruto") else "") if vol else "", 9, x=M + 40 * mm)
    itens = extra.get("itens") or [{"qtd": i.get("qtd"), "desc": i.get("desc")} for i in nf.get("itens") or []]
    fundo = 26 * mm
    for i, it in enumerate(itens):
        if y - 4.4 * mm < fundo + 4 * mm and i < len(itens) - 1:
            y -= 4.4 * mm
            texto(f"+ {len(itens) - i} item(ns) — ver a NF completa", 8)
            break
        y -= 4.4 * mm
        q = it.get("qtd")
        q = int(q) if isinstance(q, float) and q.is_integer() else q
        texto(f"{q} x {it.get('desc') or ''}", 8.5)
    if extra.get("carga"):
        y -= 4.2 * mm
        texto(f"Carga {extra['carga']}" + (f" · parada {extra['parada']}" if extra.get("parada") else ""), 8)
    y = fundo
    linha()
    y -= 4 * mm
    titulo("Recebimento")
    y -= 9 * mm
    c.setLineWidth(0.5)
    c.line(M, y, M + 28 * mm, y)
    c.line(M + 32 * mm, y, W - M, y)
    c.setFont("Helvetica", 6.5)
    c.drawString(M, y - 3 * mm, "DATA")
    c.drawString(M + 32 * mm, y - 3 * mm, "NOME / ASSINATURA DO RECEBEDOR")


def etiquetas_pdf(notas: list, mostrar_valor: bool = True, titulo: str = "DANFE Simplificado - Etiqueta") -> bytes:
    """notas: lista de dicts da NF (ou pares (nf, extra)). Uma página 100 × 150 mm por nota."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(LARG_MM * mm, ALT_MM * mm))
    c.setTitle(titulo)
    for n in notas:
        nf, extra = (n if isinstance(n, tuple) else (n, None))
        _etiqueta(c, nf, extra, mostrar_valor)
        c.showPage()
    c.save()
    return buf.getvalue()
