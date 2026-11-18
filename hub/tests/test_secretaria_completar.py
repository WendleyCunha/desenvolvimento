"""App Relatórios: depois do envio pede só o que está VAZIO na ficha e grava; nunca sobrescreve."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_empresas as T  # noqa: E402
from test_empresas import entrar, hub  # noqa: E402,F401  (fixture)


def _prep(secretaria, ligado=True):
    import relatorios_publico
    relatorios_publico._envios.clear()   # freio anti-robô entre testes
    T.DB[(secretaria.COL_MEMBROS, "Carla Souza Lima")] = {"nome_oficial": "Carla Souza Lima", "categoria": "PUBLICADOR",
                                                         "data_batismo": "03/04/2005", "genero": "Feminino"}
    T.DB[(secretaria.COL_MEMBROS, "Maria Almeida Couto")] = {"nome_oficial": "Maria Almeida Couto", "categoria": "PUBLICADOR"}
    T.DB[(secretaria.COL_MEMBROS, "Maria de Almeida Couto")] = {"nome_oficial": "Maria de Almeida Couto", "categoria": "PUBLICADOR"}
    secretaria.BASE.membros = None
    secretaria.BASE.cfg = {**secretaria.CONFIG_PADRAO, "grupos": [{"id": "norte", "nome": "Norte"}], "pedir_dados_publicador": ligado}


def _enviar(c, nome):
    return c.post("/api/relatorios-publico/enviar", json={"nome": nome, "participou": True}).json()


def test_pede_so_o_vazio_e_grava(hub):
    import secretaria
    c = hub()
    _prep(secretaria)
    r = _enviar(c, "Carla Lima")                       # palavras dentro de UMA ficha só
    campos = [x["campo"] for x in r["completar"]["campos"]]
    assert campos == ["data_nascimento", "telefone_emergencia", "grupo"]   # batismo e gênero já existem
    assert "03/04/2005" not in str(r)                  # nunca mostra o que já está na ficha
    ok = c.post("/api/relatorios-publico/completar", json={"passe": r["completar"]["passe"], "dados": {
        "data_nascimento": "10/05/1990", "grupo": "norte", "data_batismo": "01/01/2000", "genero": "Masculino"}})
    assert ok.status_code == 200 and ok.json()["faltando"] == ["Telefone de emergência"]
    m = T.DB[(secretaria.COL_MEMBROS, "Carla Souza Lima")]
    assert m["data_nascimento"] == "10/05/1990" and m["grupo"] == "norte"
    assert m["data_batismo"] == "03/04/2005" and m["genero"] == "Feminino"   # não sobrescreveu
    assert set(m["informado_publicador"]) == {"data_nascimento", "grupo"}


def test_validacao_e_passe(hub):
    import secretaria
    c = hub()
    _prep(secretaria)
    p = _enviar(c, "Carla Souza Lima")["completar"]["passe"]
    assert c.post("/api/relatorios-publico/completar", json={"passe": p, "dados": {"data_nascimento": "24/06/1083"}}).status_code == 422
    assert c.post("/api/relatorios-publico/completar", json={"passe": p, "dados": {"grupo": "inventado"}}).status_code == 422
    assert c.post("/api/relatorios-publico/completar", json={"passe": p[:-2] + "00", "dados": {"data_nascimento": "10/05/1990"}}).status_code == 403
    assert c.post("/api/relatorios-publico/completar", json={"passe": p, "dados": {"telefone_emergencia": "Ana 11 99999-0000"}}).status_code == 200


def test_nome_em_duvida_ou_desligado_nao_pede(hub):
    import secretaria
    c = hub()
    _prep(secretaria)
    assert _enviar(c, "Maria Almeida")["completar"] is None          # duas fichas possíveis
    assert _enviar(c, "Pessoa Desconhecida")["completar"] is None
    _prep(secretaria, ligado=False)
    assert _enviar(c, "Carla Souza Lima")["completar"] is None       # Ajustes › desligado
