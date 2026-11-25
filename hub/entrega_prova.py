"""
hub/entrega_prova.py — COMPROVANTE DE ENTREGA (canhoto digital) do WROUTER
─────────────────────────────────────────────────────────────────────────────
No "Entregue"/"Parcial" do app do motorista ficam juntas, num registro só:
  • palavra-chave do pedido (conferida, liberada ou validada pela frota)
  • nome de quem recebeu, parentesco e final do documento
  • assinatura na tela do celular
  • foto da entrega com marca d'água (data, hora, GPS, cliente, motorista, carga)
  • GPS e distância até o endereço · motorista, placa, carga · NF-e (número e chave)
  • CÓDIGO DE INTEGRIDADE (SHA-256) do registro + foto + assinatura: qualquer alteração depois muda o código.

O resumo vai para o pedido (ped["entrega"]) → ERP, CX e app do cliente veem o mesmo comprovante.
O PDF do comprovante sai daqui (ERP, CX e WROUTER usam a mesma função).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json

import banco

COL_FOTOS = "wrouter_fotos"
PARENTESCOS = ["Próprio cliente", "Cônjuge", "Familiar", "Vizinho", "Porteiro / zelador", "Funcionário", "Outro"]


def _sha(b64: str) -> str:
    return hashlib.sha256((b64 or "").encode()).hexdigest()


def b64_da_data_url(d: str) -> str:
    return str(d or "").split(",", 1)[-1]


def selar(reg: dict, foto_b64: str, ass_b64: str) -> dict:
    """Calcula o código de integridade sobre o que foi capturado na hora (não muda depois)."""
    base = {k: reg.get(k) for k in sorted(reg) if k not in ("hash", "eventos")}
    base["foto_sha256"] = _sha(foto_b64) if foto_b64 else ""
    base["assinatura_sha256"] = _sha(ass_b64) if ass_b64 else ""
    reg["foto_sha256"], reg["assinatura_sha256"] = base["foto_sha256"], base["assinatura_sha256"]
    reg["hash"] = hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return reg


def conferir(reg: dict) -> bool:
    """O registro ainda bate com o código? (lê foto e assinatura guardadas)."""
    fb = _ler_foto(reg.get("foto")) or {}
    ab = _ler_foto(reg.get("assinatura")) or {}
    copia = {k: v for k, v in reg.items() if k not in ("hash", "eventos", "foto_sha256", "assinatura_sha256")}
    return selar(copia, fb.get("b64", ""), ab.get("b64", ""))["hash"] == reg.get("hash")


def texto_palavra(palavra_ok, liberacao: str, validar: dict | None, exigida: bool, vizinho_sem_nome: bool) -> str:
    if vizinho_sem_nome:
        return "dispensada (cliente pediu entregar ao vizinho sem nome)"
    if not exigida:
        return "não exigida para este motorista"
    if palavra_ok is True:
        return "conferida"
    if (validar or {}).get("status") == "pendente":
        return "não conferiu sem sinal — aguardando a frota"
    if (validar or {}).get("status") == "aceita":
        return "validada pela frota (registro sem sinal)"
    if liberacao == "liberada":
        return "liberada pela frota (cliente sem a palavra)"
    return "não conferida"


def _ler_foto(fid) -> dict | None:
    if not fid:
        return None
    try:
        snap = banco.db().collection(COL_FOTOS).document(str(fid)).get(timeout=banco.TIMEOUT)
        return snap.to_dict() if snap.exists else None
    except Exception:  # noqa: BLE001
        return None


def _dh(iso: str) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]} {s[11:19]}" if len(s) >= 19 else s


def pdf(reg: dict, ped: dict, empresa: str = "") -> bytes:
    """PDF A4 do comprovante, com foto e assinatura."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    M = 16 * mm
    c.setTitle(f"Comprovante de entrega - pedido {ped.get('numero')}")
    y = H - M
    c.setFont("Helvetica-Bold", 16)
    c.drawString(M, y, "COMPROVANTE DE ENTREGA")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - M, y, empresa or "")
    y -= 6 * mm
    c.setLineWidth(1)
    c.line(M, y, W - M, y)

    def bloco(titulo, linhas):
        nonlocal y
        y -= 7 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(M, y, titulo.upper())
        for rot, val in linhas:
            y -= 5.2 * mm
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(M, y, rot)
            c.setFont("Helvetica", 9.5)
            c.drawString(M + 48 * mm, y, str(val if val not in (None, "") else "—")[:95])

    end = ped.get("endereco") or {}
    endtxt = ", ".join(x for x in (" ".join(y for y in (end.get("logradouro"), end.get("numero")) if y), end.get("complemento"), end.get("bairro"),
                                   " - ".join(z for z in (end.get("cidade"), end.get("uf")) if z), end.get("cep")) if x)
    bloco("Pedido", [("Pedido", f"#{ped.get('numero')}"), ("Cliente", ped.get("cliente_nome")), ("Endereço", endtxt),
                     ("NF-e", f"{reg.get('nf_numero') or '—'}" + (f" · chave {reg.get('nf_chave')}" if reg.get("nf_chave") else ""))])
    res = {"entregue": "ENTREGUE", "parcial": "ENTREGA PARCIAL"}.get(reg.get("resultado"), str(reg.get("resultado") or "").upper())
    bloco("Recebimento", [("Resultado", res), ("Data e hora", _dh(reg.get("em"))), ("Recebido por", reg.get("recebedor")),
                          ("Parentesco / vínculo", reg.get("parentesco")), ("Documento (final)", reg.get("doc_final")),
                          ("Palavra-chave", reg.get("palavra"))])
    gps = f"{reg.get('lat'):.6f}, {reg.get('lng'):.6f}" if isinstance(reg.get("lat"), (int, float)) and isinstance(reg.get("lng"), (int, float)) else "sem GPS"
    bloco("Local e transporte", [("GPS no registro", gps), ("Distância do endereço", f"{reg['dist_m']} m" if reg.get("dist_m") is not None else "endereço sem coordenada"),
                                 ("Chegada registrada", _dh(reg.get("chegou_em")) if reg.get("chegou_em") else "—"),
                                 ("Motorista / placa", f"{reg.get('motorista') or ''} · {reg.get('placa') or ''}"), ("Carga", reg.get("carga")),
                                 ("Registro sem sinal", _dh(reg.get("offline_em")) if reg.get("offline_em") else "não")])
    for ev in reg.get("eventos") or []:
        y -= 5 * mm
        c.setFont("Helvetica-Oblique", 8.5)
        c.drawString(M, y, f"{_dh(ev.get('em'))} · {ev.get('por') or ''} · {ev.get('texto') or ''}"[:120])

    y -= 8 * mm
    alt = 70 * mm
    foto = _ler_foto(reg.get("foto"))
    ass = _ler_foto(reg.get("assinatura"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(M, y, "FOTO DA ENTREGA")
    c.drawString(W / 2 + 4 * mm, y, "ASSINATURA DE QUEM RECEBEU")
    y -= 2 * mm
    caixa = (W - 2 * M) / 2 - 4 * mm
    for i, f in enumerate((foto, ass)):
        x = M + i * (caixa + 8 * mm)
        c.setLineWidth(0.5)
        c.rect(x, y - alt, caixa, alt)
        if f and f.get("b64"):
            try:
                img = ImageReader(io.BytesIO(base64.b64decode(f["b64"])))
                iw, ih = img.getSize()
                k = min((caixa - 4) / iw, (alt - 4) / ih)
                c.drawImage(img, x + (caixa - iw * k) / 2, y - alt + (alt - ih * k) / 2, iw * k, ih * k, mask="auto")
            except Exception:  # noqa: BLE001
                c.setFont("Helvetica", 8)
                c.drawString(x + 4, y - 12, "(imagem indisponível)")
        else:
            c.setFont("Helvetica", 8)
            c.drawString(x + 4, y - 12, "(não registrada)")
    y -= alt + 8 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(M, y, "CÓDIGO DE INTEGRIDADE (SHA-256)")
    y -= 4.5 * mm
    c.setFont("Courier", 8.5)
    c.drawString(M, y, str(reg.get("hash") or ""))
    y -= 5 * mm
    c.setFont("Helvetica", 7.5)
    c.drawString(M, y, "Calculado no momento do registro sobre os dados acima, a foto e a assinatura. Qualquer alteração posterior gera outro código.")
    c.showPage()
    c.save()
    return buf.getvalue()
