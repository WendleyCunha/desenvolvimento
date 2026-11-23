"""Módulo Web: extensão Hub Web (download montado para o endereço do hub) e aviso quando o site recusa o servidor."""
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_empresas import entrar, hub  # noqa: E402,F401  (fixture)


def test_extensao_zip_feita_para_este_hub(hub):
    c = hub()
    assert c.get("/api/web/extensao.zip").status_code in (401, 403)          # só logado
    entrar(c, "chefe", "senha-forte")
    r = c.get("/api/web/extensao.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert set(z.namelist()) == {"hub-web/manifest.json", "hub-web/bg.js", "hub-web/ponte.js", "hub-web/icone.png"}
    m = json.loads(z.read("hub-web/manifest.json"))
    assert m["manifest_version"] == 3 and m["content_scripts"][0]["matches"] == ["http://testserver/*"]
    bg = z.read("hub-web/bg.js").decode()
    assert 'const HUB = "testserver"' in bg and "x-frame-options" in bg
    assert "__HUB__" not in bg and "__VERSAO__" not in z.read("hub-web/ponte.js").decode()


def test_site_que_recusa_o_servidor_vira_aviso():
    import web_proxy as W
    akamai = '<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY>Reference #18.9054 https://errors.edgesuite.net/18.9054</BODY></HTML>'
    cloud = "<html><title>Just a moment...</title><body>Executando verificação de segurança</body></html>"
    assert W._recusou_servidor(403, akamai) == "protecao"
    assert W._recusou_servidor(200, cloud) == "protecao"
    assert W._recusou_servidor(503, "") == "protecao"
    noticia = "<html><body>" + "texto da matéria sobre verificação de segurança nos aeroportos. " * 800 + "</body></html>"
    assert W._recusou_servidor(200, noticia) == ""                           # página normal (longa) não vira aviso
    pg = W._pagina_recusa("https://noticias.uol.com.br/x", "protecao")
    assert "noticias.uol.com.br recusou" in pg and 'hubWeb:"recusou"' in pg
