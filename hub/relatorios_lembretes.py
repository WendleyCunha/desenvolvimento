"""
hub/relatorios_lembretes.py — LEMBRETE DO RELATÓRIO NO CELULAR/COMPUTADOR (notificação do sistema)
─────────────────────────────────────────────────────────────────────────────
100% grátis: Web Push do próprio navegador (as mesmas chaves VAPID do app do cliente, por empresa).

  • No app Relatórios, depois do envio, a pessoa toca em "Ativar lembretes" e aceita a notificação.
    O aparelho guarda um PASSE assinado de cada pessoa que já enviou relatório por ele (a mãe que envia
    por ela e pelos filhos guarda os três). Sem passe ninguém se inscreve no nome de outro.
  • Todo dia, do dia 1 até o dia de corte (Ajustes › corte), a partir da hora escolhida em Ajustes,
    cada aparelho recebe UMA notificação por pessoa cujo relatório do mês ainda não chegou.
    Chegou o relatório → aquela pessoa sai do lembrete naquele mês.
  • Quem chama o disparo é uma tarefa agendada grátis do GitHub (de hora em hora). O disparo é
    idempotente: cada empresa recebe no máximo UMA rodada por dia, só depois da hora marcada —
    chamar a mais não manda nada a mais (por isso não precisa de senha).

Banco (por empresa): relatorios_lembretes/<aparelho> = {sub, membros: [ids], desde: {id: ts}, atualizado}
                     relatorios_lembretes/_controle  = {ultimo: "AAAA-MM-DD"}
                     relatorios_lembretes_envios/<id> = {membro, aparelho, dia, mes, em, status, chegou?, abriu?}
  • Cada lembrete enviado vira uma linha: "enviado" (o Google/Apple aceitou) → "chegou" (o próprio aparelho
    confirmou) → "abriu" (a pessoa tocou). "falhou"/"expirou" quando não deu. O Secretário vê isso por membro.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

import acesso
import banco
import promocoes
import secretaria
import secretaria_regras as R

router = APIRouter()
COL = "relatorios_lembretes"
COL_ENV = "relatorios_lembretes_envios"
_ID_ENVIO = re.compile(r"^[0-9a-f]{24}$")
_resumo = banco.por_empresa(lambda: {"t": 0.0, "dados": None})   # o que o Secretário vê (relido ao mudar algo)
_trava = threading.Lock()
_APARELHO = re.compile(r"^[A-Za-z0-9_-]{16,48}$")
MAX_PESSOAS = 10


def _col():
    return banco.db().collection(COL)


def _col_env():
    return banco.db().collection(COL_ENV)


def _esquecer():
    _resumo["dados"] = None


def ligado() -> bool:
    return secretaria.BASE.config().get("lembretes_ligado", True) is not False


# ── passe: "esta pessoa já enviou relatório por este aparelho" ───────────────
def passe(mid: str) -> str:
    corpo = acesso._b64(json.dumps({"e": banco.empresa_atual(), "m": mid, "t": "lemb"}).encode())
    return corpo + "." + acesso._assinar(corpo)


def ler_passe(p: str) -> str | None:
    import hmac
    try:
        corpo, assin = str(p).rsplit(".", 1)
        if not hmac.compare_digest(acesso._assinar(corpo), assin):
            return None
        d = json.loads(acesso._unb64(corpo))
    except Exception:  # noqa: BLE001
        return None
    if d.get("t") != "lemb" or d.get("e") != banco.empresa_atual():
        return None
    return d.get("m") if d.get("m") in (secretaria.BASE.membros or {}) else None


# ── rotas do app (públicas) ───────────────────────────────────────────────────
@router.get("/api/relatorios-publico/lembretes/chave")
def chave():
    if not banco.configurado() or not ligado():
        return {"ligado": False}
    return {"ligado": True, "publica": promocoes.vapid()["publica"]}


@router.post("/api/relatorios-publico/lembretes/inscrever")
async def inscrever(request: Request):
    if not banco.configurado():
        raise HTTPException(503, "Sistema em manutenção.")
    try:
        d = await request.json()
    except Exception:
        raise HTTPException(400, "Envio inválido.")
    ap, sub = str(d.get("aparelho") or ""), d.get("sub")
    if not _APARELHO.match(ap) or not isinstance(sub, dict) or not str(sub.get("endpoint", "")).startswith("https://"):
        raise HTTPException(422, "Inscrição inválida.")
    if len(json.dumps(sub)) > 2000:
        raise HTTPException(422, "Inscrição inválida.")
    secretaria.BASE.atualizar()
    mids = []
    for p in (d.get("passes") or [])[:MAX_PESSOAS]:
        m = ler_passe(p)
        if m and m not in mids:
            mids.append(m)
    if not mids:
        raise HTTPException(422, "Envie um relatório por este aparelho antes de ativar os lembretes.")
    doc = _col().document(ap)
    antes = doc.get(timeout=banco.TIMEOUT)
    desde = ((antes.to_dict() or {}).get("desde") or {}) if antes.exists else {}
    agora_ts = time.time()
    desde = {m: desde.get(m, agora_ts) for m in mids}
    doc.set({"sub": {"endpoint": sub["endpoint"], "keys": sub.get("keys") or {}},
             "membros": mids, "desde": desde, "atualizado": agora_ts}, timeout=banco.TIMEOUT)
    _esquecer()
    return {"ok": True, "pessoas": len(mids)}


@router.post("/api/relatorios-publico/lembretes/recibo")
async def recibo(request: Request):
    """O aparelho avisa: o lembrete CHEGOU (apareceu na tela) ou a pessoa ABRIU (tocou)."""
    try:
        d = await request.json()
    except Exception:
        raise HTTPException(400, "Envio inválido.")
    i, ev = str(d.get("id") or ""), str(d.get("ev") or "")
    if not _ID_ENVIO.match(i) or ev not in ("chegou", "abriu") or not banco.configurado():
        return {"ok": False}
    campos = {ev: time.time()}
    if ev == "abriu":
        campos.setdefault("chegou", campos["abriu"])
    try:
        doc = _col_env().document(i)
        snap = doc.get(timeout=banco.TIMEOUT)
        if not snap.exists:                       # id que não é de lembrete nenhum: ignora (não cria nada)
            return {"ok": False}
        atual = snap.to_dict() or {}
        doc.set({k: v for k, v in campos.items() if not atual.get(k)}, merge=True, timeout=banco.TIMEOUT)
    except Exception:  # noqa: BLE001
        return {"ok": False}
    _esquecer()
    return {"ok": True}


@router.post("/api/relatorios-publico/lembretes/sair")
async def sair(request: Request):
    try:
        ap = str((await request.json()).get("aparelho") or "")
    except Exception:
        raise HTTPException(400, "Envio inválido.")
    if _APARELHO.match(ap):
        _col().document(ap).delete(timeout=banco.TIMEOUT)
        _esquecer()
    return {"ok": True}


# ── disparo diário ────────────────────────────────────────────────────────────
def _pendentes(mids: list[str], ch: str) -> list[str]:
    membros = secretaria.BASE.membros or {}
    enviados = {ln["membro_id"] for ln in secretaria.BASE.linhas() if ln["chave"] == ch and ln["membro_id"]}
    return [m for m in mids if m in membros and m not in enviados and R.no_quadro(membros[m], ch)]


def disparar_empresa(agora: datetime | None = None, forcar: bool = False) -> dict:
    """Uma rodada para a empresa atual (no máximo 1 por dia, do dia 1 ao corte, depois da hora marcada)."""
    if not acesso.modulo_liberado("secretaria") or not ligado():
        return {"motivo": "desligado"}
    cfg = secretaria.BASE.config()
    agora = agora or datetime.now(R.FUSO)
    corte = int(cfg.get("corte_dia", R.CORTE_DIA_PADRAO))
    hora = int(cfg.get("lembrete_hora", 9))
    if not forcar and (agora.day > corte or agora.hour < hora):
        return {"motivo": "fora do horário"}
    hoje = agora.strftime("%Y-%m-%d")
    with _trava:
        ctl = _col().document("_controle")
        snap = ctl.get(timeout=banco.TIMEOUT)
        if not forcar and snap.exists and (snap.to_dict() or {}).get("ultimo") == hoje:
            return {"motivo": "já enviado hoje"}
        ctl.set({"ultimo": hoje}, timeout=banco.TIMEOUT)
    secretaria.BASE.atualizar()
    ch = R.chave_por_data(agora, corte)
    mes = R.rotulo(ch)
    url = banco.prefixo_publico() + "/relatorios/"
    enviados = falhas = expirados = 0
    for doc in _col().stream(timeout=banco.TIMEOUT):
        if doc.id.startswith("_"):
            continue
        d = doc.to_dict() or {}
        for mid in _pendentes(d.get("membros") or [], ch):
            nome = (secretaria.BASE.membros[mid].get("nome_oficial") or mid).strip()
            eid = secrets.token_hex(12)
            r = promocoes.enviar_push(d.get("sub") or {}, {
                "titulo": f"Relatório de {mes} pendente",
                "texto": f"{nome.split()[0]}, seu relatório de {mes} ainda não chegou. Toque para enviar.",
                "tag": f"rel-{ch}-{mid}", "url": url, "id": eid})
            try:
                _col_env().document(eid).set({"membro": mid, "aparelho": doc.id, "dia": hoje, "mes": ch, "em": time.time(),
                                              "status": {"ok": "enviado"}.get(r, r)}, timeout=banco.TIMEOUT)
            except Exception:  # noqa: BLE001  (registro é extra: não para o disparo)
                pass
            if r == "expirou":
                _col().document(doc.id).delete(timeout=banco.TIMEOUT)
                expirados += 1
                break
            enviados += r == "ok"
            falhas += r == "falhou"
    _esquecer()
    return {"mes": mes, "enviados": enviados, "falhas": falhas, "aparelhos_saíram": expirados}


@router.api_route("/api/lembretes-relatorio/disparar", methods=["GET", "POST"])
def disparar():
    """Chamado de hora em hora pela tarefa agendada do GitHub. Idempotente: no máximo 1 rodada/dia/empresa."""
    if not banco.configurado():
        return {"ok": False}
    saida = {}
    for eid, e in acesso.EMPRESAS.todas().items():
        if e.get("ativo", True) is False:
            continue
        with banco.usar_empresa(eid):
            try:
                saida[eid] = disparar_empresa()
            except Exception as ex:  # noqa: BLE001
                saida[eid] = {"erro": type(ex).__name__}
    return {"ok": True, "empresas": saida}


# ── Ajustes (Secretário) ──────────────────────────────────────────────────────
def aparelhos() -> int:
    try:
        return sum(1 for d in _col().stream(timeout=banco.TIMEOUT) if not d.id.startswith("_"))
    except Exception:  # noqa: BLE001
        return 0


def _situacao(e: dict) -> str:
    return "abriu" if e.get("abriu") else "chegou" if e.get("chegou") else e.get("status") or "enviado"


def resumo() -> dict:
    """Por membro: em quantos aparelhos o lembrete está ativo, desde quando, e o último lembrete (com a situação).
    E a última rodada inteira (quem recebeu, quem abriu). Guardado em memória até alguma coisa mudar (10 min no máximo)."""
    if _resumo["dados"] is not None and time.time() - _resumo["t"] < 600:
        return _resumo["dados"]
    por: dict[str, dict] = {}
    aparelhos = 0
    try:
        for doc in _col().stream(timeout=banco.TIMEOUT):
            if doc.id.startswith("_"):
                continue
            aparelhos += 1
            d = doc.to_dict() or {}
            desde = d.get("desde") or {}
            for m in d.get("membros") or []:
                x = por.setdefault(m, {"aparelhos": 0, "desde": None, "ultimo": None})
                x["aparelhos"] += 1
                t = desde.get(m) or d.get("atualizado")
                if t and (x["desde"] is None or t < x["desde"]):
                    x["desde"] = t
        envios = [dict(e.to_dict() or {}, id=e.id) for e in
                  _col_env().where("em", ">=", time.time() - 45 * 86400).stream(timeout=banco.TIMEOUT)]
    except Exception:  # noqa: BLE001
        envios = []
    envios.sort(key=lambda e: e.get("em") or 0)
    for e in envios:
        x = por.setdefault(e.get("membro"), {"aparelhos": 0, "desde": None, "ultimo": None})
        x["ultimo"] = {"dia": e.get("dia"), "situacao": _situacao(e), "em": e.get("em")}
    ultimo_dia = envios[-1].get("dia") if envios else None
    membros = secretaria.BASE.membros or {}
    rodada = [{"membro": e.get("membro"), "nome": (membros.get(e.get("membro")) or {}).get("nome_oficial") or "(ficha apagada)",
               "situacao": _situacao(e), "em": e.get("em"), "chegou": e.get("chegou"), "abriu": e.get("abriu")}
              for e in envios if e.get("dia") == ultimo_dia]
    rodada.sort(key=lambda x: x["nome"])
    dados = {"aparelhos": aparelhos, "por_membro": {k: v for k, v in por.items() if k}, "ultima_rodada": {"dia": ultimo_dia, "envios": rodada}}
    _resumo["dados"], _resumo["t"] = dados, time.time()
    return dados
