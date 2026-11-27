"""
hub/cliente_acesso.py — ACESSO SEGURO AO APP DO CLIENTE
─────────────────────────────────────────────────────────────────────────────
Fluxo:
  1. O cliente valida pelo LINK de atendimento (/atendimento/: CPF + 2 perguntas do ERP).
  2. O bot oferece instalar o app → ele cria uma SENHA → o aparelho fica conectado.
  3. O aparelho entra direto por 30 DIAS; depois pede a senha. 3 senhas erradas → começa do zero
     (aparelho desconectado e senha bloqueada: só validando pelo link de novo).
  4. Em outro aparelho: CPF + senha (sem bot). Esqueceu? Valida pelo link e cria outra.
  5. Mudou o ENDEREÇO de entrega (cadastro ou pedido) → todos os acessos caem: valida pelo link de novo.
  6. 3 validações erradas no link em 24 h → validação travada por 24 h (a central destrava antes).
  7. Aparelhos conectados: o cliente vê e desconecta; a central também. Aparelho novo → aviso nos outros.
  8. Com senha criada, a PALAVRA-CHAVE da entrega (e o PDF do pedido) só aparece depois de digitar a senha.
  O login antigo (CPF + e-mail) continua funcionando junto até ser desligado.

Guardado em cliente_acesso/<id do cliente no ERP> (banco do hub): hash da senha (scrypt), aparelhos,
contadores de erro e a "impressão" dos endereços na última validação.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

import acesso
import banco
import cliente_app as C
import tickets as T

COL = "cliente_acesso"
DIAS_APARELHO = 30
ERROS_SENHA = 3
FALHAS_VALIDACAO, JANELA_VALIDACAO = 3, 86400
DESBLOQUEIO_SEG = 600
ETIQUETA_DESB = "cliente-desb:"
_cache = banco.por_empresa(dict)
_trava = threading.Lock()


# ── armazenamento ─────────────────────────────────────────────────────────────
def _ref(cid: str):
    return banco.db().collection(COL).document(cid)


def ler(cid: str) -> dict:
    if cid not in _cache:
        try:
            snap = _ref(cid).get(timeout=banco.TIMEOUT)
            _cache[cid] = (snap.to_dict() if snap.exists else None) or {}
        except Exception:  # noqa: BLE001
            return {}
    d = _cache[cid]
    d.setdefault("aparelhos", {})
    return d


def gravar(cid: str, d: dict):
    _cache[cid] = d
    _ref(cid).set(json.loads(json.dumps(d)), timeout=banco.TIMEOUT)


def agora_txt() -> str:
    return T.agora()


# ── senha e impressão dos endereços ───────────────────────────────────────────
def _hash(senha: str, sal: str) -> str:
    return hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=2 ** 14, r=8, p=1, dklen=32).hex()


def senha_valida(senha: str) -> str:
    s = str(senha or "").strip()
    if not (6 <= len(s) <= 20):
        raise HTTPException(422, "A senha precisa ter de 6 a 20 caracteres (pode ser 6 números).")
    if len(set(s)) == 1 or s in ("123456", "654321", "012345", "123123", "1234567", "12345678"):
        raise HTTPException(422, "Essa senha é fácil de adivinhar. Escolha outra.")
    return s


def confere(d: dict, senha: str) -> bool:
    sv = d.get("senha") or {}
    return bool(sv.get("hash")) and hmac.compare_digest(_hash(str(senha or "").strip(), sv["sal"]), sv["hash"])


def _end_txt(e: dict) -> str:
    e = e or {}
    return "|".join(T.norm(e.get(k)) for k in ("logradouro", "numero", "complemento")) + "|" + T.digitos(e.get("cep"))


def impressao(cid: str, cli: dict) -> str:
    """Muda se o CPF ou QUALQUER endereço de entrega (cadastro ou pedidos) mudar → precisa validar de novo."""
    ends = {_end_txt(cli.get("endereco"))}
    for p in C._erp().ST.dados["pedidos"].values():
        if p.get("cliente_id") == cid and p.get("status") not in (None, "rascunho", "cancelado") and p.get("endereco"):
            ends.add(_end_txt(p["endereco"]))
    ends.discard("|||")
    return hashlib.sha256((T.digitos(cli.get("doc")) + "#" + ";".join(sorted(ends))).encode()).hexdigest()[:20]


def tem_senha(cid: str) -> bool:
    return bool((ler(cid).get("senha") or {}).get("hash"))


# ── token do aparelho (cookie do app) ─────────────────────────────────────────
def token_aparelho(cid: str, aparelho: str, imp: str) -> str:
    corpo = C._b64(json.dumps({"c": cid, "d": aparelho, "k": imp, "e": int(time.time() + DIAS_APARELHO * 86400)}).encode())
    return corpo + "." + C._assinar(corpo)


def ler_token_bruto(token: str | None) -> dict | None:
    """Assinatura conferida, MESMO vencido (para pedir a senha depois dos 30 dias)."""
    if not token or "." not in token:
        return None
    corpo, ass = token.rsplit(".", 1)
    if not hmac.compare_digest(C._assinar(corpo), ass):
        return None
    try:
        return json.loads(C._unb64(corpo))
    except Exception:  # noqa: BLE001
        return None


def checar_aparelho(d: dict, cid: str, cli: dict):
    """Chamado pela sessão do app quando o token é de aparelho."""
    A = ler(cid)
    ap = A["aparelhos"].get(d.get("d") or "")
    if not ap or ap.get("revogado"):
        raise HTTPException(401, "Este aparelho foi desconectado. Valide de novo pelo atendimento para entrar.")
    if d.get("k") != impressao(cid, cli) or A.get("imp") != d.get("k"):
        raise HTTPException(401, "Seus dados de entrega mudaram. Por segurança, valide de novo pelo atendimento.")
    hoje = agora_txt()[:10]
    if str(ap.get("ultimo") or "")[:10] != hoje:   # "visto por último" — grava no máximo 1x por dia
        ap["ultimo"] = agora_txt()
        banco.thread(gravar, cid, A)


def _nome_aparelho(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    so = "iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua else "Windows" if "Windows" in ua else \
        "Mac" if "Mac OS" in ua else "Celular"
    nav = "Safari" if ("Safari" in ua and "Chrome" not in ua and "CriOS" not in ua) else "Chrome" if ("Chrome" in ua or "CriOS" in ua) else \
        "Firefox" if "Firefox" in ua else "navegador"
    return f"{so} · {nav}"


def conectar(request: Request, cid: str, cli: dict, A: dict) -> JSONResponse:
    """Registra este aparelho, avisa os outros e devolve a resposta com o cookie do app."""
    nome = _nome_aparelho(request)
    if any(not a.get("revogado") for a in A["aparelhos"].values()) and cli.get("codigo"):
        try:
            import promocoes
            banco.thread(promocoes.avisar_cliente, str(cli["codigo"]).upper(), "📱 Novo aparelho conectado",
                         f"{nome} entrou na sua conta agora. Não foi você? Abra o app › Aparelhos e desconecte.",
                         f"{banco.prefixo_publico()}/cliente/", f"aparelho-{cli['codigo']}")
        except Exception as ex:  # noqa: BLE001
            print(f"[acesso] sem aviso de aparelho: {ex}")
    aid = secrets.token_hex(8)
    A["aparelhos"][aid] = {"nome": nome, "criado": agora_txt(), "ultimo": agora_txt(), "revogado": False}
    # guarda só os últimos 10 (os desconectados saem primeiro)
    if len(A["aparelhos"]) > 10:
        for k in sorted(A["aparelhos"], key=lambda k: (not A["aparelhos"][k].get("revogado"), A["aparelhos"][k].get("ultimo") or ""))[:len(A["aparelhos"]) - 10]:
            A["aparelhos"].pop(k, None)
    gravar(cid, A)
    if cli.get("codigo"):   # avisos que este cliente ativou pelo link passam a abrir o app
        try:
            import promocoes
            promocoes.apontar_para_app(str(cli["codigo"]).upper())
        except Exception as ex:  # noqa: BLE001
            print(f"[acesso] avisos não apontados para o app: {ex}")
    resp = JSONResponse({"ok": True, "nome": C._primeiro_nome(cli.get("nome")), "aparelho": aid, "url": banco.prefixo_publico() + "/cliente/"})
    resp.set_cookie(C._ck(), token_aparelho(cid, aid, A["imp"]), httponly=True, samesite="lax", secure=C._https(request),
                    max_age=DIAS_APARELHO * 86400 + 30 * 86400, path="/")   # o cookie dura mais que o token: depois dos 30 dias pede a senha
    return resp


def _erro_senha(cid: str, A: dict, aparelho: str | None = None) -> HTTPException:
    A["erros"] = int(A.get("erros") or 0) + 1
    if A["erros"] >= ERROS_SENHA:
        A.update(bloqueada=True, erros=0)
        if aparelho and aparelho in A["aparelhos"]:
            A["aparelhos"][aparelho]["revogado"] = True
        gravar(cid, A)
        return HTTPException(423, "Senha errada 3 vezes. Por segurança, o acesso foi bloqueado: valide de novo pelo atendimento e crie outra senha.")
    gravar(cid, A)
    resta = ERROS_SENHA - A["erros"]
    return HTTPException(401, f"Senha incorreta. Você tem mais {resta} tentativa{'s' if resta > 1 else ''}.")


# ── validação do link: trava de 24 h após 3 validações erradas ───────────────
def validacao_travada(cid: str) -> bool:
    return float(ler(cid).get("travado_ate") or 0) > time.time()


def falhou_validacao(cid: str):
    A = ler(cid)
    agora_s = time.time()
    f = [x for x in (A.get("valid_falhas") or []) if agora_s - x < JANELA_VALIDACAO] + [agora_s]
    A["valid_falhas"] = f
    if len(f) >= FALHAS_VALIDACAO:
        A["travado_ate"] = agora_s + JANELA_VALIDACAO
        A["valid_falhas"] = []
    gravar(cid, A)


def validou(cid: str, cli: dict):
    """Validação certa pelo link: zera as falhas e guarda a impressão atual dos endereços."""
    A = ler(cid)
    A.update(valid_falhas=[], travado_ate=0, imp=impressao(cid, cli))
    gravar(cid, A)


# ── desbloqueio da palavra-chave (10 min) ─────────────────────────────────────
def _ck_desb() -> str:
    return "cli_desb" if banco.empresa_atual() == banco.PRINCIPAL else f"cli_desb_{banco.empresa_atual()}"


def desbloqueado(request: Request, cid: str) -> bool:
    tk = request.cookies.get(_ck_desb()) or ""
    if "." not in tk:
        return False
    corpo, ass = tk.rsplit(".", 1)
    if not hmac.compare_digest(hmac.new(acesso.SEGREDO.encode(), (ETIQUETA_DESB + corpo).encode(), hashlib.sha256).hexdigest(), ass):
        return False
    try:
        d = json.loads(C._unb64(corpo))
    except Exception:  # noqa: BLE001
        return False
    return d.get("c") == cid and d.get("e", 0) > time.time()


def palavra_protegida(request: Request, cid: str) -> bool:
    return tem_senha(cid) and not desbloqueado(request, cid)


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS (registradas no router do app do cliente)
# ══════════════════════════════════════════════════════════════════════════════
router = C.router


@router.post("/api/cliente/atendimento/instalar")
async def instalar(request: Request):
    """Depois de validar pelo link: cria (ou troca) a senha e conecta este aparelho ao app."""
    cid, cli = C._cliente_do_link(request)
    if cli.get("tipo") == "visitante" or not cid:
        raise HTTPException(403, "Para instalar o app, valide com o seu CPF.")
    d = await request.json()
    senha = senha_valida(d.get("senha"))
    with _trava:
        A = ler(cid)
        if A.get("imp") != impressao(cid, cli):
            raise HTTPException(409, "Seus dados de entrega mudaram. Valide de novo pelo atendimento.")
        sal = secrets.token_hex(16)
        A.update(senha={"hash": _hash(senha, sal), "sal": sal, "em": agora_txt()}, erros=0, bloqueada=False)
        return conectar(request, cid, cli, A)


@router.post("/api/cliente/atendimento/conectar")
async def conectar_com_senha(request: Request):
    """Validou pelo link e JÁ TEM senha: digita a senha que já tem para conectar este celular (não cria outra)."""
    cid, cli = C._cliente_do_link(request)
    if cli.get("tipo") == "visitante" or not cid:
        raise HTTPException(403, "Para usar o app, valide com o seu CPF.")
    if not tem_senha(cid):
        raise HTTPException(404, "Você ainda não tem senha. Crie a sua.")
    d = await request.json()
    with _trava:
        A = ler(cid)
        if A.get("bloqueada"):
            raise HTTPException(423, "Seu acesso está bloqueado por segurança. Toque em \"Esqueci a senha\" e crie outra.")
        if A.get("imp") != impressao(cid, cli):
            raise HTTPException(409, "Seus dados de entrega mudaram. Valide de novo pelo atendimento.")
        if not confere(A, d.get("senha")):
            raise _erro_senha(cid, A)
        A["erros"] = 0
        return conectar(request, cid, cli, A)


@router.post("/api/cliente/entrar-senha")
async def entrar_senha(request: Request):
    """Outro aparelho: CPF + senha (sem bot). Esqueceu ou bloqueou → valida pelo link e cria outra."""
    d = await request.json()
    doc = T.digitos(d.get("cpf"))
    ip = "ip:" + C._ip(request)
    if C._bloqueado(ip, C.LIMITE_IP):
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    if not C.doc_valido(doc):
        raise HTTPException(422, "Confira o CPF — ele parece incompleto ou errado.")
    achado = C.achar_por_cpf(doc)
    if not achado or not tem_senha(achado[0]):
        C._falhou(ip)
        raise HTTPException(404, "Não há senha criada para esse CPF. Valide pelo atendimento e crie a sua (é rápido).")
    cid, cli = achado
    with _trava:
        A = ler(cid)
        if A.get("bloqueada"):
            raise HTTPException(423, "Seu acesso está bloqueado por segurança. Valide de novo pelo atendimento e crie outra senha.")
        if A.get("imp") != impressao(cid, cli):
            raise HTTPException(409, "Seus dados de entrega mudaram. Por segurança, valide de novo pelo atendimento.")
        if not confere(A, d.get("senha")):
            C._falhou(ip)
            raise _erro_senha(cid, A)
        A["erros"] = 0
        return conectar(request, cid, cli, A)


@router.get("/api/cliente/sessao")
def sessao(request: Request):
    """O que o app mostra quando não consegue entrar: ok · senha (passaram os 30 dias) · revalidar · nada."""
    d = ler_token_bruto(request.cookies.get(C._ck()))
    if not d:
        return {"estado": "nada"}
    if not d.get("d"):   # login antigo (CPF + e-mail)
        return {"estado": "ok" if d.get("e", 0) >= time.time() else "nada"}
    cid = d.get("c") or ""
    cli = C._erp().ST.dados["parceiros"].get(cid) or {}
    A = ler(cid)
    ap = A["aparelhos"].get(d["d"])
    if not cli or not ap or ap.get("revogado") or A.get("bloqueada"):
        return {"estado": "revalidar", "motivo": "Este aparelho foi desconectado."}
    if d.get("k") != impressao(cid, cli) or A.get("imp") != d.get("k"):
        return {"estado": "revalidar", "motivo": "Seus dados de entrega mudaram."}
    if d.get("e", 0) < time.time():
        return {"estado": "senha", "nome": C._primeiro_nome(cli.get("nome"))}
    return {"estado": "ok"}


@router.post("/api/cliente/reentrar")
async def reentrar(request: Request):
    """Passaram os 30 dias: este aparelho pede a senha. 3 erros → desconecta e bloqueia (volta ao começo)."""
    d = ler_token_bruto(request.cookies.get(C._ck()))
    if not d or not d.get("d"):
        raise HTTPException(401, "Entre de novo.")
    cid = d["c"]
    cli = C._erp().ST.dados["parceiros"].get(cid) or {}
    corpo = await request.json()
    with _trava:
        A = ler(cid)
        ap = A["aparelhos"].get(d["d"])
        if not cli or not ap or ap.get("revogado") or A.get("bloqueada"):
            raise HTTPException(423, "Este aparelho foi desconectado. Valide de novo pelo atendimento.")
        if d.get("k") != impressao(cid, cli) or A.get("imp") != d.get("k"):
            raise HTTPException(409, "Seus dados de entrega mudaram. Por segurança, valide de novo pelo atendimento.")
        if not confere(A, corpo.get("senha")):
            raise _erro_senha(cid, A, d["d"])
        A["erros"] = 0
        ap["ultimo"] = agora_txt()
        gravar(cid, A)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(C._ck(), token_aparelho(cid, d["d"], A["imp"]), httponly=True, samesite="lax", secure=C._https(request),
                    max_age=DIAS_APARELHO * 86400 + 30 * 86400, path="/")
    return resp


@router.post("/api/cliente/desbloquear")
async def desbloquear(request: Request):
    """Mostrar a palavra-chave / baixar o PDF: pede a senha (vale 10 min neste aparelho)."""
    cid, cli = C._cliente_da_sessao(request)
    d = ler_token_bruto(request.cookies.get(C._ck())) or {}
    corpo = await request.json()
    with _trava:
        A = ler(cid)
        if A.get("bloqueada"):
            raise HTTPException(423, "Seu acesso está bloqueado por segurança. Valide de novo pelo atendimento.")
        if not confere(A, corpo.get("senha")):
            raise _erro_senha(cid, A, d.get("d"))
        A["erros"] = 0
        gravar(cid, A)
    c = C._b64(json.dumps({"c": cid, "e": int(time.time() + DESBLOQUEIO_SEG)}).encode())
    tk = c + "." + hmac.new(acesso.SEGREDO.encode(), (ETIQUETA_DESB + c).encode(), hashlib.sha256).hexdigest()
    resp = JSONResponse({"ok": True, "minutos": DESBLOQUEIO_SEG // 60})
    resp.set_cookie(_ck_desb(), tk, httponly=True, samesite="lax", secure=C._https(request), max_age=DESBLOQUEIO_SEG, path="/")
    return resp


def lista_aparelhos(cid: str, atual: str = "") -> list[dict]:
    A = ler(cid)
    return sorted(({"id": k, "nome": v.get("nome"), "criado": v.get("criado"), "ultimo": v.get("ultimo"), "este": k == atual}
                   for k, v in A["aparelhos"].items() if not v.get("revogado")), key=lambda x: str(x["ultimo"] or ""), reverse=True)


@router.get("/api/cliente/aparelhos")
def aparelhos(request: Request):
    cid, _cli = C._cliente_da_sessao(request)
    d = ler_token_bruto(request.cookies.get(C._ck())) or {}
    return {"aparelhos": lista_aparelhos(cid, d.get("d") or ""), "tem_senha": tem_senha(cid)}


@router.post("/api/cliente/aparelhos/{aid}/desconectar")
def desconectar(aid: str, request: Request):
    cid, _cli = C._cliente_da_sessao(request)
    with _trava:
        A = ler(cid)
        if aid not in A["aparelhos"]:
            raise HTTPException(404, "Aparelho não encontrado.")
        A["aparelhos"][aid]["revogado"] = True
        gravar(cid, A)
    return {"ok": True}


# ── lado da central (CX) ──────────────────────────────────────────────────────
def resumo_central(cid: str) -> dict:
    A = ler(cid)
    return {"tem_senha": tem_senha(cid), "bloqueada": bool(A.get("bloqueada")), "travado_ate": float(A.get("travado_ate") or 0),
            "validacao_travada": validacao_travada(cid), "aparelhos": lista_aparelhos(cid)}


def acao_central(cid: str, acao: str, aparelho: str = "") -> dict:
    with _trava:
        A = ler(cid)
        if acao == "desconectar":
            for k, v in A["aparelhos"].items():
                if aparelho in ("todos", k):
                    v["revogado"] = True
        elif acao == "destravar":
            A.update(travado_ate=0, valid_falhas=[], bloqueada=False, erros=0)
        else:
            raise HTTPException(400, "Ação inválida.")
        gravar(cid, A)
    return resumo_central(cid)
