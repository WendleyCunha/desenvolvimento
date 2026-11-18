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
    W.P.update(listar=lista, ler=_ler, gravar=_gravar, marcar=_marcar, usuarios=lambda: CONTAS)
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
LIB = {"weduca": {"acoes": {"acessar": True}}}
CONTAS = {"ana": {"nome": "Ana Ribeiro", "modulos": LIB}, "bia": {"nome": "Bia Souza", "modulos": LIB},
          "zeca": {"nome": "Zeca", "modulos": {}}, "velho": {"nome": "Velho", "ativo": False, "modulos": LIB}}


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


# ══════════════════════════ APRENDIZAGEM ══════════════════════════
CRIADOR = {"acessar": True, "publicar": True, "comentar": True, "cursos": True}


def _curso(t, **kw):
    corpo = {"titulo": "Montagem do palete", "descricao": "Como montar sem avaria", "categoria": "Logística", **kw}
    r = t.post("/api/weduca/cursos", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _aula(t, cid, **kw):
    r = t.post(f"/api/weduca/cursos/{cid}/aulas", json={"titulo": "Aula", "tipo": "texto", "texto": "conteúdo", **kw})
    assert r.status_code == 200, r.text
    return r.json()


QUIZ = {"nota_min": 70, "perguntas": [{"texto": "Colchão vai como?", "opcoes": ["Deitado", "Em pé"], "correta": 1},
                                      {"texto": "Quantas bases no máximo?", "opcoes": ["3", "5", "8"], "correta": 0}]}


def test_curso_criar_publicar_e_permissoes(t):
    como("ana")                                                    # sem "cursos"
    assert t.post("/api/weduca/cursos", json={"titulo": "x"}).status_code == 403
    como("edu", **CRIADOR)
    c = _curso(t, status="publicado")
    assert c["status"] == "rascunho"                               # sem aula não publica
    body = {"titulo": c["titulo"], "status": "publicado"}
    assert t.put(f"/api/weduca/cursos/{c['id']}", json=body).status_code == 400
    _aula(t, c["id"], titulo="Colchão em pé", texto="O colchão vai sempre em pé no palete.", minutos=5)
    assert t.put(f"/api/weduca/cursos/{c['id']}", json=body).json()["status"] == "publicado"
    como("bia")                                                    # aluna: vê só publicados
    lst = t.get("/api/weduca/cursos").json()
    assert [x["id"] for x in lst["cursos"]] == [c["id"]] and lst["pode_criar"] is False
    assert t.put(f"/api/weduca/cursos/{c['id']}", json=body).status_code == 403
    como("edu", **CRIADOR)
    r2 = _curso(t, titulo="Rascunho meu")
    como("bia")
    assert t.get(f"/api/weduca/cursos/{r2['id']}").status_code == 404   # rascunho dos outros não aparece


def test_aulas_entram_na_base_e_avaliacao_nao(t):
    como("edu", **CRIADOR)
    c = _curso(t, quiz=QUIZ)
    a = _aula(t, c["id"], titulo="Base box", texto="A base box vai deitada por baixo, no máximo três por palete.")
    assert W.aulas_na_base() == []                                 # rascunho ainda não é base
    t.put(f"/api/weduca/cursos/{c['id']}", json={"titulo": c["titulo"], "status": "publicado", "quiz": QUIZ})
    base = W.aulas_na_base()
    assert len(base) == 1 and base[0]["hash"] == f"curso={c['id']}&aula={a['id']}"
    assert not any("Quantas bases" in x for x in base[0]["passos"])   # avaliação fora da IA
    como("bia")
    t.post(f"/api/weduca/aulas/{a['id']}/duvidas", json={"texto": "E se o palete for menor?"})
    assert any("palete for menor" in x for x in W.aulas_na_base()[0]["passos"])
    r = t.post("/api/agente/perguntar", json={"pergunta": "quantas base box por palete deitada?"}).json()
    assert r["fonte"]["id"] == f"weduca:aula:{a['id']}" and r["fonte"]["hash"].startswith("curso=")
    t.post("/api/agente/retorno", json={"pergunta_id": r["pergunta_id"], "util": False, "obs": "mudou"})
    assert BANCO[W.COL_AULA][a["id"]]["analise"]["obs"] == "mudou"
    como("chefe")
    t.post("/api/agente/ajustar", json={"artigo_id": f"weduca:aula:{a['id']}", "de": "três", "para": "duas"})
    assert "duas" in BANCO[W.COL_AULA][a["id"]]["correcoes"][0]["texto"]
    # aluna não vê o gabarito
    como("bia")
    q = t.get(f"/api/weduca/cursos/{c['id']}").json()["quiz"]["perguntas"]
    assert all("correta" not in x for x in q)


def test_progresso_avaliacao_e_certificado(t):
    como("edu", **CRIADOR)
    c = _curso(t, quiz=QUIZ)
    a1 = _aula(t, c["id"], titulo="A1", minutos=10)
    a2 = _aula(t, c["id"], titulo="A2", minutos=5)
    t.put(f"/api/weduca/cursos/{c['id']}", json={"titulo": c["titulo"], "status": "publicado", "quiz": QUIZ})
    perg = t.get(f"/api/weduca/cursos/{c['id']}").json()["quiz"]["perguntas"]
    como("bia")
    assert t.post(f"/api/weduca/cursos/{c['id']}/avaliacao", json={"respostas": {}}).status_code == 400   # falta aula
    r = t.post(f"/api/weduca/aulas/{a1['id']}/concluir", json={"feita": True}).json()
    assert r["pct"] == 50 and r["concluido_em"] is None
    t.post(f"/api/weduca/aulas/{a2['id']}/concluir", json={"feita": True})
    assert t.get("/api/weduca/cursos").json()["cursos"][0]["pct"] == 100
    ruim = t.post(f"/api/weduca/cursos/{c['id']}/avaliacao", json={"respostas": {perg[0]["id"]: 0, perg[1]["id"]: 0}}).json()
    assert ruim["nota"] == 50 and not ruim["aprovado"] and ruim["gabarito"] is None and ruim["certificado"] is None
    boa = t.post(f"/api/weduca/cursos/{c['id']}/avaliacao", json={"respostas": {perg[0]["id"]: 1, perg[1]["id"]: 0}}).json()
    assert boa["aprovado"] and boa["certificado"] and boa["concluido_em"]
    cert = t.get("/api/weduca/certificados").json()["certificados"]
    assert cert[0]["codigo"] == boa["certificado"] and cert[0]["minutos"] == 15 and cert[0]["nota"] == 100
    como("edu", **CRIADOR)
    turma = t.get(f"/api/weduca/cursos/{c['id']}/turma").json()["turma"]
    assert turma[0]["login"] == "bia" and turma[0]["pct"] == 100 and turma[0]["tentativas"] == 2


def test_ordem_excluir_e_curso_sem_avaliacao(t):
    como("edu", **CRIADOR)
    c = _curso(t)
    a1, a2 = _aula(t, c["id"], titulo="A1"), _aula(t, c["id"], titulo="A2")
    assert t.post(f"/api/weduca/cursos/{c['id']}/ordem", json={"aulas": [a2["id"], a1["id"]]}).status_code == 200
    assert [x["id"] for x in t.get(f"/api/weduca/cursos/{c['id']}").json()["aulas"]] == [a2["id"], a1["id"]]
    assert t.post(f"/api/weduca/cursos/{c['id']}/aulas", json={"titulo": "v", "tipo": "video"}).status_code == 400
    assert t.post(f"/api/weduca/cursos/{c['id']}/aulas", json={"titulo": "p", "tipo": "pdf"}).status_code == 400
    t.put(f"/api/weduca/cursos/{c['id']}", json={"titulo": c["titulo"], "status": "publicado"})
    assert t.delete(f"/api/weduca/aulas/{a1['id']}").status_code == 200
    assert t.delete(f"/api/weduca/aulas/{a2['id']}").status_code == 400            # última aula de curso publicado
    como("bia")
    r = t.post(f"/api/weduca/aulas/{a2['id']}/concluir", json={"feita": True}).json()
    assert r["concluido_em"] and r["certificado"]                                 # sem avaliação: concluiu as aulas, concluiu o curso
    como("edu", **CRIADOR)
    assert t.delete(f"/api/weduca/cursos/{c['id']}").status_code == 200
    assert t.get("/api/weduca/cursos").json()["cursos"] == [] and W.aulas_na_base() == []


def test_weduca_e_um_item_so_no_menu():
    """O WEDUCA abre uma aba como todo sistema; as seções ficam no menu próprio dele (o "E")."""
    import main
    w = next(i for i in main.catalogo() if i["id"] == "weduca")
    assert main._no_menu(w) == [{k: v for k, v in w.items() if k not in ("_esquema", "secoes")}]


def test_perfis_buscar_seguir_e_feed_seguindo(t):
    como("ana")
    postar(t, texto="Dica de expedição #doca")
    como("bia")
    assert t.put("/api/weduca/perfil", json={"cargo": "Analista", "setor": "Qualidade", "bio": "ISO 9001"}).status_code == 200
    pess = t.get("/api/weduca/perfis").json()
    assert [p["login"] for p in pess["pessoas"]][0] == "bia"            # eu primeiro
    assert {p["login"] for p in pess["pessoas"]} == {"ana", "bia", "zeca"}   # todo mundo ativo do hub; inativo fica de fora
    assert {p["login"]: p["acesso"] for p in pess["pessoas"]}["zeca"] is False  # aparece marcado: ainda sem o WEDUCA
    assert pess["setores"] == ["Qualidade"]
    assert [p["login"] for p in t.get("/api/weduca/perfis?q=qualidade").json()["pessoas"]] == ["bia"]
    assert t.get("/api/weduca/feed?filtro=seguindo").json()["posts"] == []
    assert t.post("/api/weduca/perfis/ana/seguir").json() == {"sigo": True}
    assert len(t.get("/api/weduca/feed?filtro=seguindo").json()["posts"]) == 1
    assert t.post("/api/weduca/perfis/bia/seguir").status_code == 400
    assert t.post("/api/weduca/perfis/velho/seguir").status_code == 404
    ana = t.get("/api/weduca/perfis/ana").json()
    assert ana["posts"] == 1 and ana["seguidores"] == 1 and ana["sigo"] is True and ana["na_base"] == 1
    assert len(t.get("/api/weduca/feed?filtro=autor:ana").json()["posts"]) == 1
    assert t.get("/api/weduca/me").json()["setor"] == "Qualidade"
    assert t.post("/api/weduca/perfis/ana/seguir").json() == {"sigo": False}


def test_stories_somem_em_24h_e_nao_vao_para_a_ia(t, monkeypatch):
    como("ana")
    st = t.post("/api/weduca/stories", json={"texto": "Bom dia, expedição!"}).json()
    assert st["n_vistos"] == 0 and st["pode_mexer"]
    assert t.post("/api/weduca/stories", json={}).status_code == 400
    como("bia")
    g = t.get("/api/weduca/stories").json()["grupos"]
    assert [x["login"] for x in g] == ["ana"] and g[0]["todos_vistos"] is False
    t.post(f"/api/weduca/stories/{st['id']}/visto")
    assert t.get("/api/weduca/stories").json()["grupos"][0]["todos_vistos"] is True
    assert t.get(f"/api/weduca/stories/{st['id']}/vistos").status_code == 403    # só quem publicou
    como("ana")
    assert [p["login"] for p in t.get(f"/api/weduca/stories/{st['id']}/vistos").json()["pessoas"]] == ["bia"]
    assert not [a for a in W.base_conhecimento() if "Bom dia" in str(a)]          # story não é base da IA
    assert t.get("/api/weduca/feed").json()["posts"] == []                         # nem aparece no feed
    BANCO[W.COL_STORY][st["id"]]["expira"] = "2000-01-01T00:00:00"                 # passou de 24 h
    assert t.get("/api/weduca/stories").json()["grupos"] == []
    como("leitor", acessar=True)
    assert t.post("/api/weduca/stories", json={"texto": "x"}).status_code == 403


def test_conquista_quem_curtiu_e_curtir_comentario(t):
    como("ana")
    p = postar(t, conquista="Concluí o curso LGPD na prática")
    assert p["conquista"] == {"titulo": "Concluí o curso LGPD na prática"}
    assert any("Conquista: Concluí o curso LGPD" in " ".join(a["passos"]) for a in W.base_conhecimento())
    c = t.post(f"/api/weduca/posts/{p['id']}/comentarios", json={"texto": "Parabéns!"}).json()
    como("bia")
    t.post(f"/api/weduca/posts/{p['id']}/curtir")
    assert t.get(f"/api/weduca/posts/{p['id']}/curtidas").json()["pessoas"][0]["login"] == "bia"
    como("ana")
    assert t.get(f"/api/weduca/posts/{p['id']}").json()["curtiram"] == ["bia"]
    assert t.post(f"/api/weduca/comentarios/{c['id']}/curtir").json() == {"ligado": True, "total": 1}
    assert t.get(f"/api/weduca/posts/{p['id']}").json()["comentarios"][0]["curti"] is True


def test_foto_do_perfil_sem_poder_publicar(t):
    como("leitor", acessar=True)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
    assert t.post("/api/weduca/arquivos", content=png, headers={"Content-Type": "image/png", "X-Nome": "eu.png"}).status_code == 200
    assert t.post("/api/weduca/arquivos", content=b"%PDF-1.4", headers={"Content-Type": "application/pdf", "X-Nome": "a.pdf"}).status_code == 403


def test_ranking_do_mes(t):
    from datetime import datetime
    mes = datetime.now().strftime("%Y-%m")
    W.P["gravar"](W.COL_PROG, "ana_c1", {"login": "ana", "curso_id": "c1", "concluido_em": f"{mes}-02T10:00:00", "quiz": {"nota": 90}})
    W.P["gravar"](W.COL_PROG, "ana_c2", {"login": "ana", "curso_id": "c2", "concluido_em": "2001-01-02T10:00:00"})
    W.P["gravar"](W.COL_PROG, "bia_c1", {"login": "bia", "curso_id": "c1", "concluido_em": f"{mes}-03T10:00:00", "quiz": {"nota": 70}})
    W.P["gravar"](W.COL_PROG, "zeca_c1", {"login": "zeca", "curso_id": "c1"})       # não concluiu
    como("bia")
    r = t.get("/api/weduca/ranking").json()
    assert [(x["login"], x["pontos"]) for x in r["lista"]] == [("ana", 190), ("bia", 170)]
    assert r["eu"]["pos"] == 2
    assert t.get("/api/weduca/ranking?periodo=tudo").json()["lista"][0]["cursos"] == 2


# ══════════════════════════ NOTIFICAÇÕES E DIRECT ══════════════════════════
def test_notificacoes_curtida_comentario_mencao_seguidor(t):
    como("ana")
    p = postar(t, texto="Fechamos a doca 3 hoje, valeu @bia!")
    como("bia")
    n = t.get("/api/weduca/notificacoes").json()
    assert n["nao_lidas"] == 1 and n["notificacoes"][0]["tipo"] == "mencao" and n["notificacoes"][0]["post_id"] == p["id"]
    t.post(f"/api/weduca/posts/{p['id']}/curtir")
    c = t.post(f"/api/weduca/posts/{p['id']}/comentarios", json={"texto": "Show! @zeca @ana"}).json()
    t.post("/api/weduca/perfis/ana/seguir")
    como("ana")
    tipos = [x["tipo"] for x in t.get("/api/weduca/notificacoes").json()["notificacoes"]]
    assert sorted(tipos) == ["comentario", "curtida", "seguidor"]          # menção de quem já é o autor não duplica
    assert t.get("/api/weduca/novidades?desde=2999").json()["notif"] == 3
    t.post(f"/api/weduca/posts/{p['id']}/curtir")                          # curtir a própria postagem não notifica
    t.post(f"/api/weduca/comentarios/{c['id']}/curtir")
    assert t.post("/api/weduca/notificacoes/lidas", json={}).json() == {"ok": True}
    assert t.get("/api/weduca/notificacoes").json()["nao_lidas"] == 0
    como("bia")
    assert t.get("/api/weduca/notificacoes").json()["notificacoes"][0]["tipo"] == "curtida_com"
    assert W.COL_NOTIF not in str(W.base_conhecimento())


def test_direct_privado_e_fora_da_ia(t):
    como("ana")
    conv = t.post("/api/weduca/direct/com/bia").json()
    assert conv["id"] == "ana__bia" and conv["com"]["nome"] == "Bia Souza"
    assert t.post("/api/weduca/direct/com/ana").status_code == 400
    assert t.post("/api/weduca/direct/com/zeca").status_code == 400          # sem acesso ao WEDUCA
    assert t.get("/api/weduca/direct").json()["conversas"] == []            # conversa vazia não aparece na lista
    assert t.post("/api/weduca/direct/ana__bia", json={"texto": "  "}).status_code == 400
    foto = t.post("/api/weduca/arquivos", content=b"\xff\xd8\xff" + b"0" * 50, headers={"Content-Type": "image/jpeg", "X-Nome": "f.jpg"}).json()
    m = t.post("/api/weduca/direct/ana__bia", json={"texto": "Senha do cofre é segredo-xyz", "midias": [foto["id"]]}).json()
    assert m["minha"] and m["midias"][0]["kind"] == "foto"
    como("bia")
    assert t.get("/api/weduca/novidades?desde=2999").json()["direct"] == 1
    lst = t.get("/api/weduca/direct").json()
    assert lst["nao_lidas"] == 1 and lst["conversas"][0]["com"]["login"] == "ana"
    msgs = t.get("/api/weduca/direct/ana__bia").json()["mensagens"]
    assert msgs[0]["texto"].startswith("Senha") and not msgs[0]["minha"]
    assert t.get(f"/api/weduca/arquivos/{foto['id']}").status_code == 200   # membro abre o anexo
    t.post("/api/weduca/direct/ana__bia/lida")
    assert t.get("/api/weduca/direct").json()["nao_lidas"] == 0
    t.post("/api/weduca/direct/ana__bia", json={"texto": "Recebido"})
    assert len(t.get(f"/api/weduca/direct/ana__bia?desde={msgs[0]['em']}").json()["mensagens"]) == 1
    como("zeca", acessar=True)                                              # quem não está na conversa não vê nada
    assert t.get("/api/weduca/direct/ana__bia").status_code == 404
    assert t.post("/api/weduca/direct/ana__bia", json={"texto": "oi"}).status_code == 404
    assert t.get(f"/api/weduca/arquivos/{foto['id']}").status_code == 404
    assert "segredo-xyz" not in str(W.base_conhecimento()) and "Recebido" not in str(W.base_conhecimento())
    como("ana")
    assert t.post("/api/weduca/posts", json={"texto": "x", "midias": [foto["id"]]}).status_code == 400   # anexo do direct não vira post público
