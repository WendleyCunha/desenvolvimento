"""WEDUCA — feed real (sem Firestore nos testes) e a IA do topo lendo o que as pessoas publicam.

    cd hub && python -m pytest tests/test_weduca.py -q
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import acesso  # noqa: E402
import agente as A  # noqa: E402
import banco  # noqa: E402
import weduca as W  # noqa: E402

BANCO: dict = {}
EU: dict = {}
PERM: dict = {}


def _ler(col, i):
    return dict(BANCO[col][i], id=i) if i in BANCO.get(col, {}) else None


def _gravar(col, i, d):
    BANCO.setdefault(col, {})[i] = {k: v for k, v in d.items() if k != "id"}


def _marcar(col, i, campo, valor, ligar):
    lst = [x for x in BANCO[col][i].get(campo) or [] if x != valor]
    BANCO[col][i][campo] = lst + ([valor] if ligar else [])


@pytest.fixture()
def t(monkeypatch):
    BANCO.clear()
    lista = lambda col: [dict(v, id=k) for k, v in BANCO.get(col, {}).items()]  # noqa: E731
    W.P.update(listar=lista, ler=_ler, gravar=_gravar, marcar=_marcar)
    A.P.update(listar=lista, ler=_ler, gravar=_gravar, desde=lambda c, f, d: [], usuarios=lambda: {})
    W.esquecer(); A.esquecer_cache()
    monkeypatch.setattr(W, "_CACHE_SEG", -1)          # sem cache nos testes: cada leitura vê o banco
    monkeypatch.setattr(W, "youtube_titulo", lambda vid: "Montagem do palete")
    monkeypatch.setenv("FIRESTORE_CREDS", "teste")
    monkeypatch.delenv("AGENTE_IA", raising=False)
    monkeypatch.setattr(acesso, "exigir_usuario", lambda request: dict(EU))
    monkeypatch.setattr(acesso, "obter_esquema", lambda slug: {"acoes": {}, "campos": {}})

    def perm(u, slug, esq):
        if slug == "agente":
            return {"acoes": {"acessar": True, "alimentar": u.get("login") == "chefe"}, "campos": {}}
        return {"acoes": PERM.get(u.get("login"), {}), "campos": {}}
    monkeypatch.setattr(acesso, "permissoes", perm)
    A.FONTES_EXTRAS[:] = [W.base_conhecimento]
    A.ORIGENS.clear(); A.ORIGENS["weduca"] = {"nao_resolveu": W.nao_resolveu, "ajustar": W.ajustar}
    app = FastAPI()
    app.include_router(W.router); A.ligar(app)
    yield TestClient(app)
    A.FONTES_EXTRAS.clear(); A.ORIGENS.clear()


TODOS = {"acessar": True, "publicar": True, "comentar": True}


def como(login, **acoes):
    EU.clear(); EU.update(login=login, nome=login.title())
    PERM[login] = acoes or dict(TODOS)


def postar(t, **kw):
    r = t.post("/api/weduca/posts", json=kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_permissoes(t):
    como("zeca", acessar=False)
    assert t.get("/api/weduca/feed").status_code == 403
    como("leitor", acessar=True)
    assert t.get("/api/weduca/feed").status_code == 200
    assert t.post("/api/weduca/posts", json={"texto": "oi"}).status_code == 403
    como("ana")
    p = postar(t, texto="oi")
    como("leitor", acessar=True)
    assert t.post(f"/api/weduca/posts/{p['id']}/comentarios", json={"texto": "x"}).status_code == 403
    assert t.delete(f"/api/weduca/posts/{p['id']}").status_code == 403      # não é dele


def test_feed_curtir_comentar_salvar(t):
    como("ana")
    p = postar(t, texto="Na montagem do palete, colchão sempre em pé. #palete")
    como("bia")
    assert t.post(f"/api/weduca/posts/{p['id']}/curtir").json() == {"ligado": True, "total": 1}
    assert t.post(f"/api/weduca/posts/{p['id']}/salvar").json()["ligado"] is True
    c = t.post(f"/api/weduca/posts/{p['id']}/comentarios", json={"texto": "E a base box vai deitada."}).json()
    f = t.get("/api/weduca/feed").json()["posts"][0]
    assert f["curti"] and f["salvei"] and f["curtidas"] == 1 and f["n_coment"] == 1 and f["comentarios"][0]["id"] == c["id"]
    assert [x["id"] for x in t.get("/api/weduca/feed?filtro=salvos").json()["posts"]] == [p["id"]]
    assert t.get("/api/weduca/feed?filtro=meus").json()["posts"] == []
    assert len(t.get("/api/weduca/feed?q=base box").json()["posts"]) == 1           # busca também nos comentários
    assert t.post(f"/api/weduca/posts/{p['id']}/curtir").json() == {"ligado": False, "total": 0}
    como("ana")
    assert t.get("/api/weduca/novidades?desde=2000-01-01").json()["novas"] == 0     # a própria postagem não conta


def test_postagem_e_comentarios_viram_base_da_ia(t):
    como("ana")
    p = postar(t, texto="Para liberar a carga no WLOGISTICA, a conferência da doca precisa ser feita por outra pessoa.")
    como("bia")
    t.post(f"/api/weduca/posts/{p['id']}/comentarios", json={"texto": "Se der divergência, abre apontamento."})
    base = W.base_conhecimento()
    assert len(base) == 1 and base[0]["id"] == f"weduca:{p['id']}"
    assert any("divergência" in x for x in base[0]["passos"]) and "não revisada" in base[0]["titulo"]
    r = t.post("/api/agente/perguntar", json={"pergunta": "como liberar a carga na doca conferência?"}).json()
    assert r["tipo"] == "resposta" and r["fonte"]["origem"] == "weduca" and r["fonte"]["post_id"] == p["id"]
    # tirar da base: a IA para de usar (continua no feed)
    como("ana")
    assert t.post(f"/api/weduca/posts/{p['id']}/base", json={"base": False}).json()["base"] is False
    assert W.base_conhecimento() == []
    assert len(t.get("/api/weduca/feed").json()["posts"]) == 1


def test_nao_resolveu_vai_para_analise_e_ajuste(t):
    como("ana")
    p = postar(t, texto="O frete do pedido é sempre grátis acima de dois colchões no ERP.")
    como("bia")
    r = t.post("/api/agente/perguntar", json={"pergunta": "frete grátis pedido colchões"}).json()
    assert r["fonte"]["origem"] == "weduca"
    t.post("/api/agente/retorno", json={"pergunta_id": r["pergunta_id"], "util": False, "obs": "não é mais assim"})
    assert BANCO[W.COL_POST][p["id"]]["analise"]["obs"] == "não é mais assim"
    pend = [x for x in BANCO[A.COL_PEN].values() if x["motivo"] == "nao_resolveu"]
    assert pend and pend[0]["artigo_id"] == f"weduca:{p['id']}"
    como("chefe")
    aj = t.post("/api/agente/ajustar", json={"artigo_id": f"weduca:{p['id']}", "de": "dois colchões", "para": "três colchões",
                                              "pergunta_id": r["pergunta_id"]}).json()
    assert aj["modo"] == "correcao"
    post = BANCO[W.COL_POST][p["id"]]
    assert post["analise"] is None and "três colchões" in post["correcoes"][0]["texto"]
    assert W.base_conhecimento()[0]["passos"][0].startswith("Correção")          # a correção vem antes do texto


def test_excluir_e_moderar(t):
    como("ana")
    p = postar(t, texto="texto qualquer de teste")
    como("mod", acessar=True, moderar=True)
    assert t.post(f"/api/weduca/posts/{p['id']}/revisar").status_code == 200
    assert "(revisada)" in W.base_conhecimento()[0]["titulo"]
    assert t.delete(f"/api/weduca/posts/{p['id']}").status_code == 200
    assert t.get("/api/weduca/feed").json()["posts"] == [] and W.base_conhecimento() == []
    assert BANCO[W.COL_POST][p["id"]]["status"] == "removido"                     # guardada, fora do feed e da IA


def test_youtube(t):
    for url in ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ?t=3", "https://youtube.com/shorts/dQw4w9WgXcQ",
                "https://www.youtube.com/watch?feature=x&v=dQw4w9WgXcQ"]:
        assert W.youtube_id(url) == "dQw4w9WgXcQ"
    assert W.youtube_id("https://vimeo.com/123") is None
    como("ana")
    assert t.post("/api/weduca/posts", json={"video_url": "https://vimeo.com/1"}).status_code == 400
    p = postar(t, video_url="https://youtu.be/dQw4w9WgXcQ", transcricao="Primeiro o colchão, depois a base.")
    assert p["video"]["titulo"] == "Montagem do palete"
    assert W.base_conhecimento()[0]["titulo"].startswith("Montagem do palete")
    assert any("depois a base" in x for x in W.base_conhecimento()[0]["passos"])


def _pdf(texto):
    from reportlab.pdfgen import canvas
    b = io.BytesIO(); c = canvas.Canvas(b); c.drawString(72, 720, texto); c.save()
    return b.getvalue()


def test_pdf_e_foto(t, monkeypatch):
    monkeypatch.setattr(W, "PARTE", 500)                 # força vários pedaços
    como("ana")
    dados = _pdf("Instrucao de trabalho: embalar com filme stretch")
    r = t.post("/api/weduca/arquivos", content=dados, headers={"Content-Type": "application/pdf", "X-Nome": "IT%20embalagem.pdf"}).json()
    assert r["kind"] == "pdf" and r["nome"] == "IT embalagem.pdf" and r["tem_texto"]
    assert BANCO[W.COL_ARQ][r["id"]]["partes"] > 1
    assert t.get(f"/api/weduca/arquivos/{r['id']}").content == dados             # remonta os pedaços
    p = postar(t, texto="Nova IT", midias=[r["id"]])
    assert any("stretch" in x for x in W.base_conhecimento()[0]["passos"])        # o texto do PDF vai para a IA
    como("bia")
    assert t.post("/api/weduca/posts", json={"texto": "x", "midias": [r["id"]]}).status_code == 400   # anexo de outra postagem
    foto = t.post("/api/weduca/arquivos", content=b"\xff\xd8\xff" + b"0" * 50, headers={"Content-Type": "image/jpeg", "X-Nome": "f.jpg",
                                                                                     "X-Largura": "800", "X-Altura": "600"}).json()
    assert foto["kind"] == "foto" and foto["w"] == 800
    assert t.post("/api/weduca/arquivos", content=b"MZ...", headers={"Content-Type": "application/x-msdownload"}).status_code == 415
    assert t.post("/api/weduca/arquivos", content=b"nao e pdf", headers={"Content-Type": "application/pdf"}).status_code == 400
    assert p["midias"][0]["kind"] == "pdf"
