"""PDF do pedido: ERP (palavra só para quem pode ver), app do cliente (o próprio pedido, com a palavra)."""
import io

from pypdf import PdfReader

import erp as E
from test_cliente_app import entrar, t  # noqa: F401  (fixture: ERP + Tickets + app do cliente em memória)


def _texto(pdf: bytes) -> str:
    return " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)


def test_pdf_do_erp_com_e_sem_palavra(t, monkeypatch):
    t.app.include_router(E.router)
    r = t.get("/api/erp/pedidos/ped1/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    txt = _texto(r.content)
    assert "#101" in txt and "Colchão Casal Molas" in txt and "SOL42" in txt and "14/11/2026" in txt
    import tickets
    monkeypatch.setattr(tickets, "ver_palavra", lambda u: False)
    assert "SOL42" not in _texto(t.get("/api/erp/pedidos/ped1/pdf").content), "sem a permissão do Atendimento, o PDF sai sem a palavra"
    assert t.get("/api/erp/pedidos/naoexiste/pdf").status_code == 404


def test_pdf_no_app_do_cliente(t):
    assert t.get("/api/cliente/pedido/ped1/pdf").status_code == 401
    entrar(t)
    r = t.get("/api/cliente/pedido/ped1/pdf")
    assert r.status_code == 200 and "SOL42" in _texto(r.content)
    assert t.get("/api/cliente/pedido/ped3/pdf").status_code == 404, "pedido de outro cliente não abre"
    assert t.get("/api/cliente/pedido/ped2/pdf").status_code == 404, "rascunho não aparece"
