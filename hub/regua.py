"""
hub/regua.py — RÉGUA DO CLIENTE (aviso no celular a cada etapa do pedido) + PESQUISAS CSAT/NPS
─────────────────────────────────────────────────────────────────────────────
A LINHA DO PEDIDO (Atendimento › Ajustes › Wwhat › Régua do cliente): cada etapa tem título, texto e
liga/desliga. Quando o pedido passa pela etapa, o cliente recebe a notificação no celular (app e/ou link de
atendimento, onde ativou os avisos). Tudo nasce DESLIGADO — quem liga é a central.

Etapas (ordem da linha): pedido criado · troca gerada · bloqueado · liberado · agendado · data alterada ·
aguardando nova data · endereço alterado · carga montada · saiu para entrega · motorista a X km ·
motorista chegou · entregue · entregue com avaria · cliente ausente · recusado · cancelado.

Pesquisas: CSAT (1 a 5) + NPS (0 a 10) + comentário, por link público /pesquisa/<token> (assinado, 15 dias):
  · na compra (pedido criado) · após o atendimento (chat concluído) · após a entrega.
Respostas em `pesquisas` (banco do hub) → Gestão › CSAT/NPS.

Quem chama: erp.Tx.commit (transições do pedido), wrouter (motorista perto / chegou), tickets (chat concluído).
Tudo em segundo plano — nunca atrasa nem derruba o ERP.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

import acesso
import banco

router = APIRouter()

# (id, rótulo, quando dispara, título padrão, texto padrão)
ETAPAS = [
    ("pedido_criado", "Pedido criado", "Quando o pedido é confirmado no ERP", "🛒 Pedido confirmado",
     "Oi, {nome}! Seu pedido #{pedido} foi confirmado. Avisamos você a cada etapa até a entrega."),
    ("troca_gerada", "Troca gerada", "Quando uma troca é aberta para o cliente", "🔄 Troca registrada",
     "{nome}, registramos a troca #{pedido}. Vamos avisar quando estiver agendada."),
    ("pedido_bloqueado", "Pedido bloqueado", "Sem estoque para reservar (aguardando produto)", "⏳ Seu pedido está aguardando produto",
     "{nome}, o pedido #{pedido} está aguardando a chegada do produto. Assim que chegar, liberamos e avisamos você."),
    ("pedido_liberado", "Pedido liberado", "O estoque chegou e o pedido foi reservado", "✅ Pedido liberado",
     "Boa notícia, {nome}! O produto do pedido #{pedido} chegou. Agora vamos agendar a entrega."),
    ("agendado", "Entrega agendada", "Quando a entrega ganha data", "📅 Entrega agendada",
     "{nome}, a entrega do pedido #{pedido} está marcada para {data}{janela}."),
    ("data_alterada", "Data da entrega alterada", "Quando a data agendada muda", "📅 Nova data de entrega",
     "{nome}, a entrega do pedido #{pedido} mudou para {data}{janela}."),
    ("reagendar", "Aguardando nova data", "Quando o pedido volta para reagendar", "🗓 Vamos combinar uma nova data",
     "{nome}, precisamos combinar uma nova data para o pedido #{pedido}. A central vai falar com você."),
    ("endereco_alterado", "Endereço alterado", "Quando o endereço de entrega do pedido muda", "🏠 Endereço de entrega alterado",
     "{nome}, o endereço de entrega do pedido #{pedido} foi alterado. Se não foi você, fale com a central."),
    ("em_carga", "Carga montada", "O pedido foi separado no caminhão", "📦 Pedido separado para entrega",
     "{nome}, o pedido #{pedido} já está separado no caminhão para a entrega de {data}."),
    ("em_rota", "Saiu para entrega", "O caminhão saiu do CD", "🚚 Saiu para entrega",
     "{nome}, o pedido #{pedido} saiu para entrega! Acompanhe pelo app."),
    ("motorista_perto", "Motorista a caminho (perto)", "Quando o motorista está a {km} km ou menos", "📍 O motorista está chegando",
     "{nome}, o motorista está a cerca de {km} km do seu endereço. Deixe alguém para receber!"),
    ("motorista_chegou", "Motorista chegou", "O motorista marcou que chegou no endereço", "🔔 O motorista chegou",
     "{nome}, o motorista chegou com o pedido #{pedido}."),
    ("entregue", "Entregue", "Baixa de entrega feita", "🎉 Pedido entregue",
     "{nome}, o pedido #{pedido} foi entregue. Obrigado pela compra!"),
    ("entrega_avaria", "Entregue com avaria", "Entrega com produto avariado", "⚠️ Entrega com avaria registrada",
     "{nome}, registramos a avaria na entrega do pedido #{pedido}. A central vai cuidar da reposição."),
    ("ausente", "Cliente ausente", "O motorista não encontrou ninguém", "🚪 Não encontramos ninguém",
     "{nome}, passamos para entregar o pedido #{pedido} e não encontramos ninguém. Vamos combinar outra data."),
    ("recusado", "Entrega recusada", "O cliente recusou a entrega", "↩️ Entrega recusada",
     "{nome}, a entrega do pedido #{pedido} foi recusada. A central vai falar com você."),
    ("cancelado", "Pedido cancelado", "Quando o pedido é cancelado", "✖️ Pedido cancelado",
     "{nome}, o pedido #{pedido} foi cancelado. Qualquer dúvida, fale com a central."),
]
PESQUISAS = [
    ("compra", "Pesquisa na compra", "Logo depois de confirmar o pedido", "⭐ Como foi a sua compra?",
     "{nome}, conta pra gente como foi a sua compra? Leva 10 segundos."),
    ("atendimento", "Pesquisa após o atendimento", "Quando a central conclui o chat", "⭐ Como foi o atendimento?",
     "{nome}, como foi o seu atendimento com a nossa central? Sua opinião ajuda muito."),
    ("entrega", "Pesquisa após a entrega", "Depois da entrega feita", "⭐ Como foi a entrega?",
     "{nome}, como foi a entrega do pedido #{pedido}? Avalie em 10 segundos."),
]
KM_PADRAO = 5
URGENTES = {"motorista_perto", "motorista_chegou", "em_rota"}
_enviados = banco.por_empresa(dict)   # (pid, chave) → hora (não repete o mesmo aviso)
_trava = threading.Lock()


def _hub():
    import tickets as T
    return T


def cfg() -> dict:
    """{etapas: {id: {ativo, titulo, texto}}, pesquisas: {id: {...}}, km}. Tudo nasce desligado."""
    bruto = _hub().hub_cfg().get("regua") or {}
    et = {i: {"ativo": False, "titulo": t, "texto": x, **(bruto.get("etapas") or {}).get(i, {})} for i, _r, _q, t, x in ETAPAS}
    pq = {i: {"ativo": False, "titulo": t, "texto": x, **(bruto.get("pesquisas") or {}).get(i, {})} for i, _r, _q, t, x in PESQUISAS}
    try:
        km = float(bruto.get("km") or KM_PADRAO)
    except (TypeError, ValueError):
        km = KM_PADRAO
    return {"etapas": et, "pesquisas": pq, "km": km}


def publico() -> dict:
    c = cfg()
    return {"etapas": [{"id": i, "rotulo": r, "quando": q.replace("{km}", str(c["km"]).rstrip("0").rstrip(".")), **c["etapas"][i]} for i, r, q, _t, _x in ETAPAS],
            "pesquisas": [{"id": i, "rotulo": r, "quando": q, **c["pesquisas"][i]} for i, r, q, _t, _x in PESQUISAS], "km": c["km"]}


def salvar(dados: dict) -> dict:
    novo = {"etapas": {}, "pesquisas": {}, "km": KM_PADRAO}
    ids_e, ids_p = {e[0] for e in ETAPAS}, {p[0] for p in PESQUISAS}
    for grupo, ids in (("etapas", ids_e), ("pesquisas", ids_p)):
        for k, v in ((dados or {}).get(grupo) or {}).items():
            if k in ids:
                novo[grupo][k] = {"ativo": bool((v or {}).get("ativo")), "titulo": str((v or {}).get("titulo") or "").strip()[:80],
                                  "texto": str((v or {}).get("texto") or "").strip()[:400]}
    try:
        novo["km"] = max(0.5, min(float((dados or {}).get("km") or KM_PADRAO), 50))
    except (TypeError, ValueError):
        raise HTTPException(400, "Distância inválida.") from None
    return novo


# ── texto e envio ─────────────────────────────────────────────────────────────
def _fmt_data(d: str) -> str:
    try:
        dt = datetime.fromisoformat(str(d)[:10])
        return ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][dt.weekday()] + f", {dt:%d/%m}"
    except Exception:  # noqa: BLE001
        return str(d or "")


def _texto(modelo: str, ped: dict, cli: dict, km=None, link="") -> str:
    ag = ped.get("agendamento") or {}
    nome = (str(cli.get("nome") or "").strip().split(" ") or [""])[0].title()
    out = str(modelo or "")
    for k, v in {"nome": nome, "pedido": ped.get("numero") or "", "data": _fmt_data(ag.get("data")) if ag.get("data") else "a combinar",
                 "janela": f" ({ag['janela']})" if ag.get("janela") else "", "km": str(km if km is not None else cfg()["km"]).rstrip("0").rstrip("."),
                 "empresa": _empresa(), "link": link}.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _empresa() -> str:
    try:
        import cliente_app
        return cliente_app.cfg_app().get("empresa") or ""
    except Exception:  # noqa: BLE001
        return ""


def _cli(ped: dict) -> dict:
    import erp
    return erp.ST.dados["parceiros"].get(ped.get("cliente_id") or "") or {}


def _ja(pid: str, chave: str, janela: float = 20 * 3600) -> bool:
    """Já avisou isso deste pedido há pouco? (evita repetir quando o ERP salva duas vezes)."""
    with _trava:
        t = _enviados.get((pid, chave))
        if t and time.time() - t < janela:
            return True
        _enviados[(pid, chave)] = time.time()
        if len(_enviados) > 50000:
            _enviados.clear()
        return False


def enviar(etapa: str, ped: dict, pid: str, km=None, chave: str = "") -> dict | None:
    c = cfg()["etapas"].get(etapa)
    cli = _cli(ped)
    if not c or not c["ativo"] or not cli.get("codigo"):
        return None
    if _ja(pid, chave or etapa):
        return None
    import promocoes
    return promocoes.avisar_cliente_detalhe(str(cli["codigo"]).upper(), _texto(c["titulo"], ped, cli, km), _texto(c["texto"], ped, cli, km),
                                           f"{banco.prefixo_publico()}/cliente/", f"regua-{etapa}-{pid}", urgente=etapa in URGENTES)


def pesquisa(tipo: str, cod_cliente: str, nome: str, ref: str, ped: dict | None = None, atendente: str = "", forcar: bool = False) -> dict | None:
    """forcar=True: o atendente marcou "enviar pesquisa" ao encerrar — vai mesmo com a etapa desligada na régua."""
    c = cfg()["pesquisas"].get(tipo)
    if not c or not (c["ativo"] or forcar) or not cod_cliente:
        return None
    if _ja(ref, "pesquisa-" + tipo, 30 * 86400):
        return None
    link = f"{banco.prefixo_publico()}/pesquisa/{token_pesquisa(tipo, cod_cliente, ref, atendente, (ped or {}).get('numero'))}"
    import promocoes
    p = ped or {}
    cli = {"nome": nome}
    return promocoes.avisar_cliente_detalhe(str(cod_cliente).upper(), _texto(c["titulo"], p, cli, link=link), _texto(c["texto"], p, cli, link=link),
                                           link, f"pesquisa-{tipo}-{ref}", urgente=False)


# ── transições do pedido (chamado pelo erp.Tx.commit) ─────────────────────────
def _bloq(p: dict) -> bool:
    return p.get("status") in ("confirmado", "reagendar", "agendado") and not p.get("reservado") and bool(p.get("pendentes"))


def _end(p: dict) -> str:
    e = p.get("endereco") or {}
    v = "|".join(str(e.get(k) or "").strip().lower() for k in ("logradouro", "numero", "complemento", "cep"))
    return "" if v.replace("|", "") == "" else v


def etapas_da_mudanca(antes: dict | None, depois: dict) -> list[str]:
    """Que etapas da régua essa gravação do pedido representa."""
    a, d = antes or {}, depois or {}
    st0, st1 = a.get("status"), d.get("status")
    out = []
    if st1 == "confirmado" and st0 in (None, "rascunho"):
        out.append("troca_gerada" if d.get("tipo") == "troca" else "pedido_criado")
    if _bloq(d) and not _bloq(a) and st1 != "rascunho":
        out.append("pedido_bloqueado")
    if _bloq(a) and not _bloq(d) and st1 not in ("cancelado", "rascunho"):
        out.append("pedido_liberado")
    dt0, dt1 = (a.get("agendamento") or {}).get("data"), (d.get("agendamento") or {}).get("data")
    if st1 == "agendado" and st0 != "agendado" and st0 not in ("em_carga", "em_rota"):
        out.append("agendado")
    elif st1 == "agendado" and dt0 and dt1 and dt0 != dt1:
        out.append("data_alterada")
    if st1 == "reagendar" and st0 != "reagendar":
        out.append("ausente" if d.get("pendencia") == "ausente" else "reagendar")
    if a and _end(a) and _end(d) and _end(a) != _end(d) and st1 not in ("rascunho", "cancelado"):
        out.append("endereco_alterado")
    if st1 == "em_carga" and st0 != "em_carga":
        out.append("em_carga")
    if st1 == "em_rota" and st0 != "em_rota":
        out.append("em_rota")
    if st1 == "entregue" and st0 != "entregue":
        tent = (d.get("tentativas") or [{}])[-1]
        out.append("entrega_avaria" if tent.get("resultado") == "avaria" else "entregue")
    if st1 == "recusado" and st0 != "recusado":
        out.append("recusado")
    if st1 == "cancelado" and st0 != "cancelado":
        out.append("cancelado")
    return out


def processar_pedidos(mudancas: list[tuple]):
    """[(pid, antes, depois)] — dispara a régua e as pesquisas. Em segundo plano."""
    for pid, antes, depois in mudancas:
        try:
            for et in etapas_da_mudanca(antes, depois):
                enviar(et, depois, pid)
                cli = _cli(depois)
                if et in ("pedido_criado",):
                    pesquisa("compra", cli.get("codigo"), cli.get("nome"), pid, depois)
                if et in ("entregue", "entrega_avaria"):
                    pesquisa("entrega", cli.get("codigo"), cli.get("nome"), pid, depois)
        except Exception as ex:  # noqa: BLE001
            print(f"[régua] pedido {pid}: {ex}")


def motorista_perto(pid: str, carga_id: str, km: float):
    import erp
    if km is None or km > cfg()["km"]:
        return
    ped = erp.ST.dados["pedidos"].get(pid)
    if ped:
        banco.thread(enviar, "motorista_perto", ped, pid, km, f"perto-{carga_id}")


def motorista_chegou(pid: str, carga_id: str):
    import erp
    ped = erp.ST.dados["pedidos"].get(pid)
    if ped:
        banco.thread(enviar, "motorista_chegou", ped, pid, None, f"chegou-{carga_id}")


def chat_concluido(t: dict, cod: str, nome: str, atendente: str):
    banco.thread(pesquisa, "atendimento", cod, nome, str(t.get("id") or ""), None, atendente)


# ══════════════════════════════════════════════════════════════════════════════
# PESQUISA (página pública /pesquisa/<token>)
# ══════════════════════════════════════════════════════════════════════════════
ETIQUETA = "pesquisa:"
COL = "pesquisas"
_resp = banco.por_empresa(lambda: {"ok": False, "itens": {}})


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def token_pesquisa(tipo: str, cod: str, ref: str, atendente: str = "", pedido=None) -> str:
    corpo = _b64(json.dumps({"t": tipo, "c": str(cod).upper(), "r": ref, "a": atendente or "", "p": pedido, "e": int(time.time() + 15 * 86400)},
                            separators=(",", ":")).encode())
    return corpo + "." + hmac.new(acesso.SEGREDO.encode(), (ETIQUETA + corpo).encode(), hashlib.sha256).hexdigest()[:32]


def ler_token(tk: str) -> dict:
    if "." not in str(tk or ""):
        raise HTTPException(404, "Pesquisa não encontrada.")
    corpo, ass = tk.rsplit(".", 1)
    if not hmac.compare_digest(hmac.new(acesso.SEGREDO.encode(), (ETIQUETA + corpo).encode(), hashlib.sha256).hexdigest()[:32], ass):
        raise HTTPException(404, "Pesquisa não encontrada.")
    d = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    if d.get("e", 0) < time.time():
        raise HTTPException(410, "Esta pesquisa expirou. Obrigado mesmo assim!")
    return d


def respostas() -> dict:
    st = _resp
    if not st["ok"]:
        try:
            st["itens"] = {s.id: s.to_dict() for s in banco.db().collection(COL).stream(timeout=banco.TIMEOUT)}
        except Exception:  # noqa: BLE001
            st["itens"] = st.get("itens") or {}
        st["ok"] = True
    return st["itens"]


@router.get("/pesquisa/{tk}", include_in_schema=False)
def pagina_pesquisa(tk: str):
    return FileResponse(Path(__file__).parent / "static" / "pesquisa" / "index.html", media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


@router.get("/api/pesquisa/{tk}")
def ver_pesquisa(tk: str):
    d = ler_token(tk)
    rid = hashlib.sha256(tk.encode()).hexdigest()[:24]
    titulo = {"compra": "Como foi a sua compra?", "atendimento": "Como foi o seu atendimento?", "entrega": "Como foi a entrega?"}.get(d["t"], "Sua opinião")
    return {"tipo": d["t"], "titulo": titulo, "empresa": _empresa() or "nossa loja", "pedido": d.get("p"),
            "respondida": rid in respostas()}


@router.post("/api/pesquisa/{tk}")
async def responder(tk: str, request: Request):
    d = ler_token(tk)
    c = await request.json()
    try:
        csat = int(c.get("csat"))
        nps = int(c.get("nps"))
    except (TypeError, ValueError):
        raise HTTPException(422, "Escolha uma nota de 1 a 5 e outra de 0 a 10.") from None
    if not (1 <= csat <= 5 and 0 <= nps <= 10):
        raise HTTPException(422, "Escolha uma nota de 1 a 5 e outra de 0 a 10.")
    rid = hashlib.sha256(tk.encode()).hexdigest()[:24]
    agora = _hub().agora()
    doc = {"tipo": d["t"], "cliente": d["c"], "ref": d["r"], "atendente": d.get("a") or "", "pedido": d.get("p"), "csat": csat, "nps": nps,
           "comentario": str(c.get("comentario") or "").strip()[:600], "em": agora, "dia": agora[:10]}
    banco.db().collection(COL).document(rid).set(doc, timeout=banco.TIMEOUT)
    respostas()[rid] = doc
    return {"ok": True}


def resumo(de: str, ate: str, atendentes: dict | None = None) -> dict:
    """Gestão › CSAT/NPS: notas do período, por momento (compra/atendimento/entrega) e por atendente."""
    itens = [x for x in respostas().values() if de <= str(x.get("dia") or "") <= ate]

    def calc(lst):
        n = len(lst)
        if not n:
            return {"n": 0, "csat": None, "satisfeitos": None, "nps": None, "promotores": 0, "neutros": 0, "detratores": 0}
        pro = sum(1 for x in lst if x["nps"] >= 9)
        det = sum(1 for x in lst if x["nps"] <= 6)
        return {"n": n, "csat": round(sum(x["csat"] for x in lst) / n, 2), "satisfeitos": round(100 * sum(1 for x in lst if x["csat"] >= 4) / n),
                "nps": round(100 * (pro - det) / n), "promotores": pro, "neutros": n - pro - det, "detratores": det}
    por_tipo = {t: calc([x for x in itens if x.get("tipo") == t]) for t, *_ in PESQUISAS}
    por_at = {}
    for x in itens:
        if x.get("tipo") == "atendimento" and x.get("atendente"):
            por_at.setdefault(x["atendente"], []).append(x)
    nomes = atendentes or {}
    return {"de": de, "ate": ate, "geral": calc(itens), "por_tipo": por_tipo,
            "por_atendente": sorted(({"usuario": k, "nome": (nomes.get(k) or {}).get("nome", k), **calc(v)} for k, v in por_at.items()),
                                    key=lambda r: -(r["csat"] or 0)),
            "distribuicao_nps": [sum(1 for x in itens if x["nps"] == i) for i in range(11)],
            "distribuicao_csat": [sum(1 for x in itens if x["csat"] == i) for i in range(1, 6)],
            "comentarios": sorted(({k: x.get(k) for k in ("tipo", "csat", "nps", "comentario", "em", "pedido", "atendente", "cliente")}
                                   for x in itens if x.get("comentario")), key=lambda r: str(r["em"]), reverse=True)[:60]}


def hoje() -> str:
    return (datetime.now(_hub().BRT)).strftime("%Y-%m-%d")


def dias_atras(n: int) -> str:
    return (datetime.now(_hub().BRT) - timedelta(days=n)).strftime("%Y-%m-%d")


@router.get("/pesquisa", include_in_schema=False)
def _sem_token():
    return RedirectResponse(banco.prefixo_publico() + "/cliente/", status_code=307)
