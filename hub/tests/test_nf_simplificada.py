"""NF simplificada (etiqueta térmica) a partir do PDF das NF-e completas + comprovante de entrega do WROUTER."""
import base64
import io
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import erp as E  # noqa: E402
import entrega_prova as P  # noqa: E402
import nf_simplificada as N  # noqa: E402
from test_wrouter import FOTO, entrar, montar, t  # noqa: E402,F401

ASS = "data:image/png;base64," + base64.b64encode(b"\x89PNG-assinatura-de-teste").decode()


def chave_com_dv(base43: str) -> str:
    soma, peso = 0, 2
    for d in reversed(base43):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - soma % 11
    return base43 + str(0 if dv >= 10 else dv)


CH1 = chave_com_dv("3525063520700400012055001000123456" + "112345678")
CH2 = chave_com_dv("3525063520700400012055001000123457" + "112345679")


def danfe(chave: str, numero: str, nome: str, doc: str, pedido: str, item: str) -> list[str]:
    """Linhas no formato que o pypdf devolve do DANFE do sistema fiscal (rótulo e valor colados)."""
    g = " ".join(chave[i:i + 4] for i in range(0, 44, 4))
    return ["RECEBEMOS DE KING STAR COLCHOES LTDA OS PRODUTOS E/OU SERVIÇOS CONSTANTES DA NOTA FISCAL ELETRÔNICA INDICADA",
            f"ABAIXO. EMISSÃO: 18/06/2025 VALOR TOTAL: R$ 1.189,29 DESTINATÁRIO: {nome} - Rua Um, 10 Centro Embu-SPNF-e",
            f"Nº. {numero}", "IDENTIFICAÇÃO DO EMITENTE", "KING STAR COLCHOES LTDA", "1 - SAÍDA 1", "CHAVE DE ACESSO", g,
            "NATUREZA DA OPERAÇÃO", "VENDA MERC.PROTOCOLO DE AUTORIZAÇÃO DE USO", "135251655724339  -  18/06/2025 08:57:11",
            "INSCRIÇÃO ESTADUAL", "126945750111INSCRIÇÃO MUNICIPAL", "CNPJ / CPF", "35.207.004/0001-20",
            "DESTINATÁRIO / REMETENTE", "NOME / RAZÃO SOCIAL", f"{nome}CNPJ / CPF", f"{doc}DATA DA EMISSÃO", "18/06/2025",
            "ENDEREÇO", "Rua Um, 10BAIRRO / DISTRITO", "CentroCEP", "06820-051DATA DA SAÍDA/ENTRADA", "18/06/2025",
            "MUNICÍPIO", "EmbuUF", "SPFONE / FAX", "1140000000INSCRIÇÃO ESTADUAL", "HORA DA SAÍDA/ENTRADA", "08:51:00",
            "TRANSPORTADOR / VOLUMES TRANSPORTADOS", "QUANTIDADE", "1ESPÉCIE", "VOLUMESMARCA", "PESO BRUTO", "27,900PESO LÍQUIDO", "28,500",
            "DADOS DOS PRODUTOS / SERVIÇOS", "CÓDIGO PRODUTO DESCRIÇÃO DO PRODUTO / SERVIÇO NCM/SH O/CST CFOP UN QUANTVALOR", "IPI",
            f"CMP138X188 {item} 94042900", "0/005102UN 1,00001.189,2900 1.189,29 0,001.189,29 142,71 12,00",
            "DADOS ADICIONAIS", f"Inf. Contribuinte: Pedido de venda: {pedido} Valor Aproximado"]


def pdf_de(paginas: list[list[str]]) -> bytes:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for linhas in paginas:
        y = 820
        for ln in linhas:
            c.setFont("Helvetica", 6)
            c.drawString(10, y, ln)
            y -= 9
        c.showPage()
    c.save()
    return buf.getvalue()


def test_chave_e_leitura_do_pdf():
    assert N.chave_valida(CH1) and not N.chave_valida(CH1[:-1] + str((int(CH1[-1]) + 1) % 10))
    notas = N.ler_pdf(pdf_de([danfe(CH1, "000.123.456", "MARIA SOUZA", "529.982.247-25", "1", "COLCHAO CASAL SUPER")]))
    assert len(notas) == 1
    nf = notas[0]
    assert nf["chave"] == CH1 and nf["numero"] == "123456" and nf["serie"] == "001" and nf["emit_uf"] == "SP"
    assert nf["dest_nome"] == "MARIA SOUZA" and nf["dest_doc"] == "529.982.247-25" and nf["pedido_origem"] == "1"
    assert nf["protocolo"].startswith("135251655724339") and nf["itens"][0]["desc"] == "COLCHAO CASAL SUPER" and nf["itens"][0]["qtd"] == 1.0
    pdf = N.etiquetas_pdf(notas)
    from pypdf import PdfReader
    pg = PdfReader(io.BytesIO(pdf)).pages[0]
    assert round(float(pg.mediabox.width) / 72 * 25.4) == 100 and round(float(pg.mediabox.height) / 72 * 25.4) == 150, "etiqueta 100 × 150 mm"
    assert "DANFE SIMPLIFICADO - ETIQUETA" in pg.extract_text()


def test_importar_nfs_na_carga_e_etiquetas(t):
    pq, cid = montar(t)
    E.ST.dados["parceiros"]["c2"]["doc"] = "111.444.777-35"
    pdf = pdf_de([danfe(CH1, "000.123.456", "MARIA SOUZA", "", "1", "COLCHAO"), danfe(CH2, "000.123.457", "PEDRO ALVES", "111.444.777-35", "", "COLCHAO")])
    r = pq.post(f"/api/erp/cargas/{cid}/nf/ler", json={"pdf": "data:application/pdf;base64," + base64.b64encode(pdf).decode()}).json()
    sug = {x["nf"]["numero"]: (x["pid"], x["como"]) for x in r["notas"]}
    assert sug["123456"][0] == "ped1" and "pedido" in sug["123456"][1], "casou pelo 'Pedido de venda' da nota"
    assert sug["123457"] == ("ped2", "CPF/CNPJ do cliente")
    assert "nf" not in E.ST.dados["pedidos"]["ped1"], "ler não grava"
    x = pq.post(f"/api/erp/cargas/{cid}/nf/aplicar", json={"vinculos": [{"pid": n["pid"], "nf": n["nf"]} for n in r["notas"]]}).json()
    assert x["alterados"] == 2 and x["faturada"], "importar conta como faturado"
    assert E.ST.dados["pedidos"]["ped1"]["nf"]["chave"] == CH1
    bad = dict(r["notas"][0]["nf"], chave=CH1[:-1] + "0" if CH1[-1] != "0" else CH1[:-1] + "1")
    assert pq.post(f"/api/erp/cargas/{cid}/nf/aplicar", json={"vinculos": [{"pid": "ped1", "nf": bad}]}).status_code == 400, "chave inválida é recusada"
    e = pq.get(f"/api/erp/cargas/{cid}/etiquetas")
    assert e.status_code == 200 and e.headers["content-type"] == "application/pdf"
    from pypdf import PdfReader
    rd = PdfReader(io.BytesIO(e.content))
    assert len(rd.pages) == 2
    txt = rd.pages[0].extract_text()
    assert "SOL42" not in txt and "LUA17" not in txt, "a palavra-chave nunca vai na etiqueta"
    assert pq.get("/api/erp/pedidos/ped2/etiqueta").status_code == 200
    assert pq.get(f"/api/wlog/cargas/{cid}/etiquetas").status_code == 200, "WLOGISTICA imprime na montagem"


def test_comprovante_de_entrega_completo(t):
    pq, cid = montar(t)
    mot = TestClient(t)
    entrar(mot)
    pq.put("/api/wrouter/motoristas/m1", json={"palavra": True})
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    url = f"/api/wrouter/app/cargas/{cid}/pedido/ped1"
    base = {"desfecho": "entregue", "palavra": "SOL42", "lat": -23.5, "lng": -46.6, "cid": "c1"}
    assert mot.post(url, json={**base, "prova": {"recebedor": "", "parentesco": "Cônjuge", "assinatura": ASS}, "foto": FOTO}).status_code == 400
    assert mot.post(url, json={**base, "prova": {"recebedor": "Ana", "parentesco": "Cônjuge"}, "foto": FOTO}).status_code == 400, "sem assinatura não sai"
    assert mot.post(url, json={**base, "prova": {"recebedor": "Ana", "parentesco": "Cônjuge", "assinatura": ASS}}).status_code == 400, "sem foto não sai"
    r = mot.post(url, json={**base, "prova": {"recebedor": "Ana Souza", "parentesco": "Cônjuge", "doc_final": "12-34", "assinatura": ASS}, "foto": FOTO})
    assert r.json()["resultado"] == "ok", r.text
    ped = E.ST.dados["pedidos"]["ped1"]
    ent = ped["entrega"]
    assert ent["recebedor"] == "Ana Souza" and ent["parentesco"] == "Cônjuge" and ent["doc_final"] == "1234" and ent["palavra"] == "conferida"
    assert len(ent["hash"]) == 64 and ent["completo"]
    reg = E.ST.dados["cargas"][cid]["rota"]["pedidos"]["ped1"]["comprovante"]
    assert P.conferir(reg), "o código de integridade bate com foto e assinatura guardadas"
    adulterado = dict(reg, recebedor="Outra Pessoa")
    assert not P.conferir(adulterado), "qualquer alteração muda o código"
    assert ped["status"] == "entregue" and any("Comprovante de entrega" in h["evento"] for h in ped["historico"])
    for u in ("/api/erp/pedidos/ped1/comprovante", "/api/wrouter/comprovante/ped1"):
        c = pq.get(u)
        assert c.status_code == 200 and c.headers["content-type"] == "application/pdf", u
    assert mot.get(f"/api/wrouter/app/cargas/{cid}").status_code in (404, 405)
    app = mot.get("/api/wrouter/app/cargas").json()["cargas"][0]
    p1 = next(p for p in app["pedidos"] if p["pid"] == "ped1")
    assert p1["recebido"]["recebedor"] == "Ana Souza"
    assert mot.post(f"{url}/desfazer").status_code == 200
    assert "entrega" not in E.ST.dados["pedidos"]["ped1"], "corrigiu: o comprovante sai do pedido (fica no histórico da rota)"
    assert E.ST.dados["cargas"][cid]["rota"]["pedidos"]["ped1"]["corrigidos"][-1]["comprovante"]["hash"] == reg["hash"]


def test_app_antigo_sem_comprovante_continua_funcionando(t):
    pq, cid = montar(t)
    mot = TestClient(t)
    entrar(mot)
    mot.post(f"/api/wrouter/app/cargas/{cid}/saida", json={})
    r = mot.post(f"/api/wrouter/app/cargas/{cid}/pedido/ped1", json={"desfecho": "entregue", "cid": "z", "offline_em": "2026-11-25T10:00:00"})
    assert r.json()["resultado"] == "ok", "registro guardado no celular por versão antiga do app não se perde"
    ent = E.ST.dados["pedidos"]["ped1"]["entrega"]
    assert ent["completo"] is False and ent["palavra"] == "não exigida para este motorista"
