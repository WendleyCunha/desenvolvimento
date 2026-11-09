"""
hub/agente.py — AGENTE IA do Wendley Desenvolvimento (base de conhecimento)
─────────────────────────────────────────────────────────────────────────────
O agente fica no TOPO do hub (static/agente.js), ao lado de atualizar / tela cheia /
configurações, e abre como popup.

QUEM FAZ O QUÊ (Configurações → Usuários → "Agente IA")
  • "Perguntar ao agente"   → vê o botão e conversa;
  • "Alimentar o agente"    → ⚙️ no popup: artigos, pendências, histórico e painel;
  • Administrador           → tudo, sempre.
  Pendência pode ser ATRIBUÍDA a um usuário do hub que pergunta ao agente: ele escreve a
  resposta (📥 no popup) e quem alimenta revisa e publica — ou devolve com um recado.

COMO RESPONDE
  Procura nos artigos ativos; sem IA externa (padrão, custo zero) devolve o passo a passo.
  Com AGENTE_IA=groq (+ GROQ_API_KEY) ou anthropic (+ ANTHROPIC_API_KEY) no Render, a IA
  escreve a resposta usando SÓ os artigos encontrados; se não cobrem, diz que não sabe.
  Nada do que as pessoas escrevem entra na base sem passar por quem alimenta.

Firestore: hub_agente_artigos · hub_agente_pendencias · hub_agente_perguntas · hub_agente_historico
"""
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

import acesso
import banco

router = APIRouter(prefix="/api/agente")

COL_ART = "hub_agente_artigos"
COL_PEN = "hub_agente_pendencias"
COL_PERG = "hub_agente_perguntas"
COL_HIS = "hub_agente_historico"
COL_EX = "hub_agente_exemplos"      # respostas aprovadas (👍) — referência para perguntas parecidas
MODULO = "agente"   # permissões em Configurações → Usuários (ver RECURSO em main.py)
RECURSO = {"id": MODULO, "titulo": "Agente IA (topo)", "icone": "faisca", "cor": "#8b5cf6", "grupo": "Recursos",
           "ordem": 999, "descricao": "Base de conhecimento: perguntar e alimentar o agente do topo", "url": "", "tipo": "recurso",
           "_esquema": {"acoes": {"acessar": "Perguntar ao agente", "alimentar": "Alimentar o agente (artigos e pendências)"}}}

MAX_VERSOES = 20          # versões anteriores guardadas dentro de cada artigo (para "voltar versão")
MIN_PONTOS = 3            # pontuação mínima para considerar que um artigo responde a pergunta
_CACHE_SEG = 60


def ligar(app) -> None:
    app.include_router(router)


# ══════════════════════════════════════════════════════════════════════════
# Persistência (trocável nos testes — ver testes_agente.py)
# ══════════════════════════════════════════════════════════════════════════
def _fs_listar(col: str) -> list:
    return [{**(d.to_dict() or {}), "id": d.id} for d in banco.db().collection(col).stream(timeout=banco.TIMEOUT)]


def _fs_ler(col: str, doc_id: str) -> Optional[dict]:
    s = banco.db().collection(col).document(doc_id).get(timeout=banco.TIMEOUT)
    return {**(s.to_dict() or {}), "id": s.id} if s.exists else None


def _fs_gravar(col: str, doc_id: str, dados: dict) -> None:
    dados = {k: v for k, v in dados.items() if k != "id"}
    banco.db().collection(col).document(doc_id).set(dados, timeout=banco.TIMEOUT)


def _fs_desde(col: str, campo: str, desde: str) -> list:
    q = banco.db().collection(col).where(campo, ">=", desde)
    return [{**(d.to_dict() or {}), "id": d.id} for d in q.stream(timeout=banco.TIMEOUT)]


def _fs_usuarios() -> dict:
    return acesso.USUARIOS.todos() if banco.configurado() else {}


P = {"listar": _fs_listar, "ler": _fs_ler, "gravar": _fs_gravar, "desde": _fs_desde, "usuarios": _fs_usuarios}


# ══════════════════════════════════════════════════════════════════════════
# Utilidades
# ══════════════════════════════════════════════════════════════════════════
def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def novo_id() -> str:
    return uuid.uuid4().hex[:16]


def sem_acento(s) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_PARADAS = set("""a o e de da do das dos um uma uns umas como que qual quais quando onde para pra pro com sem
no na nos nas em por eu meu minha meus minhas se ser ao aos os as ou isso esse essa este esta aqui ali
la lá faco faço fazer feito tem ter tenho voce vocês voces sobre mais menos muito pode posso devo preciso
quero sei saber oi ola olá bom dia boa tarde noite obrigado""".split())


def palavras(texto: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9+]+", sem_acento(texto)) if len(w) > 2 and w not in _PARADAS]


def _usuario(request: Request) -> dict:
    u = acesso.exigir_usuario(request)
    if not pode_usar(u):
        raise HTTPException(status_code=403, detail="O agente não está liberado para você. Peça ao administrador (Configurações → Usuários → Agente IA).")
    return u


def _quem(u: dict) -> dict:
    return {"login": u.get("login"), "nome": u.get("nome") or u.get("login")}


def _acoes(u: dict) -> dict:
    return acesso.permissoes(u, MODULO, acesso.normalizar_esquema(RECURSO["_esquema"]))["acoes"]


def pode_usar(u: dict) -> bool:
    return bool(u.get("admin") or _acoes(u).get("acessar"))


def pode_alimentar(u: dict) -> bool:
    return bool(u.get("admin") or _acoes(u).get("alimentar"))


def _exigir_alimentar(request: Request) -> dict:
    u = _usuario(request)
    if not pode_alimentar(u):
        raise HTTPException(status_code=403, detail="Só o Administrador e o perfil Gerente alimentam o agente.")
    return u


# ══════════════════════════════════════════════════════════════════════════
# Base de artigos (com cache curto: o agente é chamado a cada pergunta)
# ══════════════════════════════════════════════════════════════════════════
_cache = {"t": 0.0, "artigos": []}


def esquecer_cache() -> None:
    _cache["t"] = 0.0


def artigos() -> list:
    if time.time() - _cache["t"] > _CACHE_SEG:
        _cache.update(t=time.time(), artigos=P["listar"](COL_ART))
    return _cache["artigos"]


def _radical(w: str) -> str:
    """Radical simples: "libero", "liberar", "liberação", "liberaram" → "liber" (plural, verbo, substantivo)."""
    return w[:5] if len(w) >= 5 else w


def pontuar(pergunta: str, art: dict) -> int:
    """Quantas palavras da pergunta aparecem no artigo (título e palavras-chave valem mais).
    Variações da mesma palavra contam em todo o texto (título, palavras-chave E passos)."""
    alvo_forte = set(palavras(art.get("titulo", "") + " " + art.get("palavras", "")))
    alvo_fraco = set(palavras(" ".join(art.get("passos") or [])))
    rad_forte = {_radical(x) for x in alvo_forte if len(x) >= 5}
    rad_fraco = {_radical(x) for x in alvo_fraco if len(x) >= 5}
    pts = 0
    for w in set(palavras(pergunta)):
        if w in alvo_forte or (len(w) >= 5 and _radical(w) in rad_forte):
            pts += 2
        elif w in alvo_fraco or (len(w) >= 5 and _radical(w) in rad_fraco):
            pts += 1
    return pts


MIN_PONTOS_IA = 2   # com IA ligada a busca pode ser menos exigente: se não tiver a ver, a IA responde "não sei"


def buscar(pergunta: str, limite: int = 3) -> list:
    ativos = [a for a in artigos() if a.get("ativo", True)]
    notas = sorted(((pontuar(pergunta, a), a) for a in ativos), key=lambda x: -x[0])
    minimo = MIN_PONTOS_IA if provedor() else MIN_PONTOS
    return [a for n, a in notas if n >= minimo][:limite]


def fonte(a: dict) -> dict:
    return {"id": a.get("id"), "titulo": a.get("titulo"), "versao": a.get("versao", 1),
            "atualizado_em": a.get("atualizado_em"), "por": (a.get("atualizado_por") or {}).get("nome")}


# ══════════════════════════════════════════════════════════════════════════
# IA externa (opcional)
# ══════════════════════════════════════════════════════════════════════════
INSTRUCOES = (   # [v6.4] mais humano: um colega experiente, com as próprias palavras
    "Você é o Agente do PQI, um colega experiente da King Star Colchões que ajuda as pessoas no dia a dia. "
    "Converse em português do Brasil de um jeito natural e humano, com as SUAS palavras — não copie o texto dos artigos. "
    "Vá direto ao ponto do que foi perguntado e explique o porquê quando isso ajudar a pessoa a fazer certo. "
    "Use passos numerados só quando for um procedimento com várias etapas; para dúvidas simples, responda em uma ou duas frases. "
    "Você pode juntar informações de artigos diferentes e tirar conclusões lógicas a partir deles, como um colega que conhece bem o processo. "
    "Mas NUNCA invente nome de tela, botão, campo, menu, opção, prazo, valor ou regra que não esteja escrito nos artigos: "
    "se o artigo não diz o nome exato, descreva o que fazer sem inventar um nome. "
    "As CORREÇÕES escritas num artigo valem mais que o resto do texto dele. "
    "Se houver CONVERSA ANTERIOR, continue o mesmo assunto. EXEMPLOS APROVADOS são respostas que a equipe validou: use como referência de conteúdo e de jeito de responder. "
    "Se os artigos não permitem responder, responda exatamente: NAO_SEI. "
    "Na última linha, escreva FONTE: seguido do número do artigo que você mais usou (ex.: FONTE: 2)."
)


ULTIMO_ERRO_IA: dict = {}   # o último motivo de a IA não ter respondido (aparece no teste da ⚙️, sem a chave)


def _http_json(url: str, corpo: dict, cab: dict, timeout: int = 40) -> dict:
    # User-Agent próprio: a Groq (Cloudflare) recusa chamadas que se identificam como "Python-urllib"
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          "User-Agent": "Hub-Agente/1.0", **cab})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def provedor() -> str:
    p = os.environ.get("AGENTE_IA", "").strip().lower()
    if p == "groq" and os.environ.get("GROQ_API_KEY"):
        return "groq"
    if p == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return ""


def perguntar_ia(pergunta: str, achados: list, historico: Optional[list] = None, exemplos: Optional[list] = None) -> Optional[str]:
    """Texto da IA, "NAO_SEI", ou None se a IA está desligada/falhou (aí vale a resposta da base)."""
    prov = provedor()
    if not prov:
        return None
    base = "\n\n".join(f"ARTIGO {i + 1}: {a.get('titulo')}\n" + "\n".join(f"- {p}" for p in (a.get("passos") or []))
                       for i, a in enumerate(achados))
    usuario = f"ARTIGOS:\n{base}\n\n"
    if exemplos:
        usuario += "EXEMPLOS APROVADOS:\n" + "\n\n".join(f"Pergunta: {e.get('pergunta')}\nResposta aprovada: {e.get('texto')}" for e in exemplos) + "\n\n"
    if historico:
        usuario += "CONVERSA ANTERIOR:\n" + "\n".join(f"Pessoa: {h.get('p')}\nAgente: {h.get('r')}" for h in historico) + "\n\n"
    usuario += f"PERGUNTA: {pergunta}"
    try:
        if prov == "groq":
            modelo = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
            corpo = {"model": modelo, "temperature": 0.4, "max_tokens": 700,
                     "messages": [{"role": "system", "content": INSTRUCOES}, {"role": "user", "content": usuario}]}
            if "gpt-oss" in modelo:   # modelo que "pensa" antes: raciocínio curto e espaço para a resposta não sair vazia
                corpo.update(max_tokens=2500, reasoning_effort="low", include_reasoning=False)
            r = _http_json("https://api.groq.com/openai/v1/chat/completions", corpo,
                           {"Authorization": "Bearer " + os.environ["GROQ_API_KEY"]})
            return (r.get("choices") or [{}])[0].get("message", {}).get("content", "").strip() or None
        r = _http_json("https://api.anthropic.com/v1/messages",
                       {"model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"), "max_tokens": 700, "system": INSTRUCOES,
                        "messages": [{"role": "user", "content": usuario}]},
                       {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text").strip() or None
    except urllib.error.HTTPError as e:
        try:
            corpo_erro = e.read().decode("utf-8", "replace")[:400]
        except Exception:   # noqa: BLE001
            corpo_erro = ""
        ULTIMO_ERRO_IA.clear(); ULTIMO_ERRO_IA.update(em=agora(), provedor=prov, status=e.code, detalhe=corpo_erro)
        print(f"[agente] IA ({prov}) recusou: HTTP {e.code} {corpo_erro}")
        return None
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
        ULTIMO_ERRO_IA.clear(); ULTIMO_ERRO_IA.update(em=agora(), provedor=prov, status=None, detalhe=f"{type(e).__name__}: {e}"[:400])
        print(f"[agente] IA ({prov}) falhou: {type(e).__name__}: {e}")
        return None


def _separar_fonte(texto: str, achados: list):
    m = re.search(r"\n?\s*FONTE:\s*(\d+)\s*$", texto)
    usado = achados[0]
    if m:
        i = int(m.group(1)) - 1
        if 0 <= i < len(achados):
            usado = achados[i]
        texto = texto[:m.start()].rstrip()
    return texto, usado


# ══════════════════════════════════════════════════════════════════════════
# Rotas — qualquer pessoa logada
# ══════════════════════════════════════════════════════════════════════════
class Pergunta(BaseModel):
    pergunta: str
    tela: Optional[str] = None     # sistema aberto no momento (só para o painel)
    historico: List[dict] = []     # [v6.4] últimas trocas da conversa: [{"p": pergunta, "r": resposta}]

    @field_validator("historico")
    @classmethod
    def _h(cls, v):
        out = []
        for h in (v or [])[-3:]:
            if isinstance(h, dict) and str(h.get("p") or "").strip():
                out.append({"p": str(h.get("p"))[:300], "r": str(h.get("r") or "")[:800]})
        return out

    @field_validator("pergunta")
    @classmethod
    def _limpa(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Escreva a pergunta.")
        return v[:500]


class Retorno(BaseModel):
    pergunta_id: str
    util: bool
    obs: Optional[str] = None


def _nova_pendencia(u: dict, pergunta: str, motivo: str, obs: str = "", artigo_id: Optional[str] = None,
                    pergunta_id: Optional[str] = None) -> None:
    pid = novo_id()
    P["gravar"](COL_PEN, pid, {"pergunta": pergunta, "motivo": motivo, "obs": (obs or "")[:500], "artigo_id": artigo_id,
                               "pergunta_id": pergunta_id, "status": "aberta", "em": agora(), **{"de": _quem(u)}})


def _abertas() -> list:
    return [p for p in P["listar"](COL_PEN) if p.get("status") == "aberta"]


def _chave(x) -> str:
    return str(x or "").strip().lower()


def fase(p: dict) -> str:
    """sem_responsavel → com_responsavel → aguardando_aprovacao (quem alimenta publica ou devolve)."""
    if p.get("proposta") and p["proposta"].get("status") == "enviada":
        return "aguardando_aprovacao"
    if (p.get("atribuida") or {}).get("login"):
        return "com_responsavel"
    return "sem_responsavel"


def _comigo(u: dict) -> list:
    eu = _chave(u.get("login"))
    return [p for p in _abertas() if _chave((p.get("atribuida") or {}).get("login")) == eu and fase(p) == "com_responsavel"]


def _com_fase(p: dict) -> dict:
    return {**p, "fase": fase(p)}


# ✏️ AJUSTAR DE → PARA
class Ajuste(BaseModel):
    artigo_id: str
    de: str
    para: str
    pergunta_id: Optional[str] = None

    @field_validator("de", "para")
    @classmethod
    def _dp(cls, v):
        v = re.sub(r"\s+", " ", (v or "")).strip()
        if not v:
            raise ValueError("Preencha o DE (o que está errado) e o PARA (o correto).")
        return v[:1200]


def _trocar(texto: str, de: str, para: str):
    """Troca a 1ª ocorrência de `de` em `texto` (sem ligar para maiúsculas e espaços). → (novo_texto, trocou?)"""
    padrao = r"\s+".join(re.escape(w) for w in de.split())
    novo, n = re.subn(padrao, lambda _m: para, str(texto or ""), count=1, flags=re.IGNORECASE)
    return novo, bool(n)


def _ajustar_artigo(art: dict, de: str, para: str, u: dict) -> dict:
    passos = list(art.get("passos") or [])
    onde, modo = None, "texto"
    for i, t in enumerate(passos):
        novo, ok_ = _trocar(t, de, para)
        if ok_:
            passos[i] = novo; onde = f"passo {i + 1} do artigo"; break
    if not onde:
        passos.append(f"Correção: onde se dizia “{de}”, o correto é: {para}")
        onde, modo = "correção no fim do artigo", "correcao"
    anterior = {**_conteudo(art), "versao": art.get("versao", 1), "em": art.get("atualizado_em"), "por": art.get("atualizado_por")}
    art.update(passos=passos, versao=int(art.get("versao", 1)) + 1, atualizado_em=agora(), atualizado_por=_quem(u),
               versoes=([anterior] + list(art.get("versoes") or []))[:MAX_VERSOES])
    P["gravar"](COL_ART, art["id"], art)
    esquecer_cache()
    return {"modo": modo, "onde": onde}


@router.post("/ajustar")
def agente_ajustar(payload: Ajuste, request: Request):
    """✏️ AJUSTAR DE → PARA (quem alimenta): troca no passo do artigo; se não está escrito lá, vira correção no fim."""
    u = _exigir_alimentar(request)
    if payload.de.lower() == payload.para.lower():
        raise HTTPException(status_code=400, detail="O DE e o PARA estão iguais.")
    art = P["ler"](COL_ART, payload.artigo_id)
    if not art:
        raise HTTPException(status_code=404, detail="Artigo não encontrado.")
    r = _ajustar_artigo(art, payload.de, payload.para, u)
    _historico(u, "ajustou", {"id": art["id"], "titulo": art.get("titulo"), "versao": art.get("versao", 1)},
               f"DE “{payload.de[:120]}” → PARA “{payload.para[:120]}” ({r['onde']})")
    if payload.pergunta_id:
        for p in _abertas():
            if p.get("pergunta_id") == payload.pergunta_id:
                p.update(status="resolvida", resolvida_em=agora(), resolvida_por=_quem(u), nota=f"ajustado: {r['onde']}")
                P["gravar"](COL_PEN, p["id"], p)
    return r


@router.post("/ia-teste")
def agente_ia_teste(request: Request):
    """Diagnóstico da IA (só quem alimenta): chama a IA com uma pergunta de teste e mostra o motivo se falhar."""
    _exigir_alimentar(request)
    prov = provedor()
    if not prov:
        return {"ok": False, "provedor": "", "motivo": "IA desligada: falta AGENTE_IA (groq/anthropic) e a chave no Render."}
    t = perguntar_ia("Responda só: OK", [{"titulo": "Teste", "passos": ["Responda OK."]}])
    return {"ok": bool(t), "provedor": prov, "modelo": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b") if prov == "groq" else os.environ.get("ANTHROPIC_MODEL", ""),
            "resposta": (t or "")[:200], "erro": None if t else dict(ULTIMO_ERRO_IA)}


@router.get("/me")
def agente_me(request: Request):
    u = _usuario(request)
    pode = pode_alimentar(u)
    return {"pode_alimentar": pode, "pendencias": len(_abertas()) if pode else 0, "comigo": len(_comigo(u)),
            "ia": provedor() or "base", "nome": (u.get("nome") or u.get("login") or "").split(" ")[0],
            "sugestoes": [a.get("titulo") for a in sorted((a for a in artigos() if a.get("ativo", True)),
                                                           key=lambda a: -(a.get("usos") or 0))[:4]]}


def exemplos_para(pergunta: str, achados: list, limite: int = 2) -> list:
    """[v6.4] Respostas aprovadas (👍) de perguntas parecidas, dos mesmos artigos e da MESMA versão deles.
    Se o artigo (a IT) mudou depois, o exemplo deixa de valer sozinho."""
    vers = {a.get("id"): a.get("versao", 1) for a in achados}
    alvo = set(palavras(pergunta))
    cands = []
    for e in P["listar"](COL_EX):
        if e.get("artigo_id") in vers and e.get("artigo_versao") == vers[e.get("artigo_id")]:
            comuns = len(alvo & set(palavras(e.get("pergunta", ""))))
            if comuns:
                cands.append((comuns, e))
    cands.sort(key=lambda x: -x[0])
    return [e for _, e in cands[:limite]]


@router.post("/perguntar")
def agente_perguntar(payload: Pergunta, request: Request):
    u = _usuario(request)
    achados = buscar(payload.pergunta)
    if not achados and payload.historico:   # continuação ("e se o cliente não atender?"): busca com o assunto da conversa
        achados = buscar(payload.historico[-1]["p"] + " " + payload.pergunta)
    pid = novo_id()
    resp: dict = {"pergunta_id": pid}
    if achados:
        texto = perguntar_ia(payload.pergunta, achados, payload.historico, exemplos_para(payload.pergunta, achados) if provedor() else None)
        if texto and texto.strip().upper().startswith("NAO_SEI"):
            achados = []
        elif texto:
            texto, usado = _separar_fonte(texto, achados)
            resp.update(tipo="resposta", modo="ia", titulo=usado.get("titulo"), texto=texto, fonte=fonte(usado))
        if achados and "tipo" not in resp:
            a = achados[0]
            resp.update(tipo="resposta", modo="base", titulo=a.get("titulo"), passos=a.get("passos") or [], fonte=fonte(a))
    if not achados:
        resp.update(tipo="nao_sei")
        _nova_pendencia(u, payload.pergunta, "sem_resposta", pergunta_id=pid)
    P["gravar"](COL_PERG, pid, {"pergunta": payload.pergunta, "em": agora(), "de": _quem(u), "tela": payload.tela,
                                "resultado": resp["tipo"], "artigo_id": (resp.get("fonte") or {}).get("id"),
                                "artigo_versao": (resp.get("fonte") or {}).get("versao"),
                                "texto": (resp.get("texto") or "")[:2000] if resp.get("modo") == "ia" else "",
                                "modo": resp.get("modo"), "util": None})
    if resp.get("fonte"):   # contador de uso (ordena as sugestões)
        art = next((a for a in artigos() if a.get("id") == resp["fonte"]["id"]), None)
        if art:
            art["usos"] = int(art.get("usos") or 0) + 1
            P["gravar"](COL_ART, art["id"], art)
    return resp


@router.post("/retorno")
def agente_retorno(payload: Retorno, request: Request):
    u = _usuario(request)
    perg = P["ler"](COL_PERG, payload.pergunta_id)
    if not perg or (perg.get("de") or {}).get("login") != u.get("login"):
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")
    if perg.get("util") is not None:
        return {"ok": True}
    perg["util"] = payload.util
    perg["obs"] = (payload.obs or "")[:500]
    P["gravar"](COL_PERG, payload.pergunta_id, perg)
    if payload.util and perg.get("modo") == "ia" and perg.get("texto") and perg.get("artigo_id"):   # 👍 vira exemplo aprovado
        P["gravar"](COL_EX, payload.pergunta_id, {"id": payload.pergunta_id, "pergunta": perg.get("pergunta"), "texto": perg.get("texto"),
                                                  "artigo_id": perg.get("artigo_id"), "artigo_versao": perg.get("artigo_versao"),
                                                  "por": _quem(u), "em": agora()})
    if not payload.util:
        _nova_pendencia(u, perg.get("pergunta", ""), "nao_resolveu", payload.obs or "", perg.get("artigo_id"), payload.pergunta_id)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════
# Rotas — quem alimenta (Administrador e perfil Gerente)
# ══════════════════════════════════════════════════════════════════════════
class Artigo(BaseModel):
    titulo: str
    setor: Optional[str] = ""
    passos: List[str]
    palavras: Optional[str] = ""
    ativo: bool = True
    pendencia_id: Optional[str] = None   # veio de uma pendência: ela é dada como resolvida
    motivo: Optional[str] = None         # o que mudou (vai para o histórico)

    @field_validator("titulo")
    @classmethod
    def _t(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Dê um título ao artigo.")
        return v[:160]

    @field_validator("passos")
    @classmethod
    def _p(cls, v):
        v = [str(x).strip()[:600] for x in (v or []) if str(x).strip()]
        if not v:
            raise ValueError("Escreva pelo menos um passo.")
        return v[:30]


class Restaurar(BaseModel):
    versao: int


def _historico(u: dict, acao: str, art: dict, detalhe: str = "") -> None:
    P["gravar"](COL_HIS, novo_id(), {"em": agora(), "por": _quem(u), "acao": acao, "artigo_id": art.get("id"),
                                     "titulo": art.get("titulo"), "versao": art.get("versao", 1), "detalhe": detalhe[:300]})


def _fechar_pendencia(pid: Optional[str], u: dict, artigo_id: str) -> str:
    """Resolve a pendência; devolve o crédito ("resposta de Fulano") quando veio de um responsável."""
    if not pid:
        return ""
    p = P["ler"](COL_PEN, pid)
    if not p or p.get("status") != "aberta":
        return ""
    credito = ""
    if fase(p) == "aguardando_aprovacao":
        p["proposta"].update(status="aprovada", aprovada_em=agora(), aprovada_por=_quem(u))
        credito = f"resposta de {(p['proposta'].get('por') or {}).get('nome', '')}, aprovada"
    p.update(status="resolvida", resolvida_em=agora(), resolvida_por=_quem(u), artigo_id=artigo_id)
    P["gravar"](COL_PEN, pid, p)
    return credito


def _conteudo(a: dict) -> dict:
    return {k: a.get(k) for k in ("titulo", "setor", "passos", "palavras", "ativo")}


@router.get("/artigos")
def agente_artigos(request: Request):
    _exigir_alimentar(request)
    lst = sorted(P["listar"](COL_ART), key=lambda a: a.get("atualizado_em") or "", reverse=True)
    return {"artigos": [{**a, "versoes": [{"versao": v.get("versao"), "em": v.get("em"), "por": (v.get("por") or {}).get("nome")}
                                          for v in (a.get("versoes") or [])]} for a in lst]}


@router.post("/artigos")
def agente_artigo_criar(payload: Artigo, request: Request):
    u = _exigir_alimentar(request)
    aid = novo_id()
    art = {"id": aid, **payload.model_dump(exclude={"pendencia_id", "motivo"}), "versao": 1, "usos": 0,
           "criado_em": agora(), "criado_por": _quem(u), "atualizado_em": agora(), "atualizado_por": _quem(u), "versoes": []}
    P["gravar"](COL_ART, aid, art)
    credito = _fechar_pendencia(payload.pendencia_id, u, aid)
    _historico(u, "criou", art, payload.motivo or credito or ("respondeu uma pendência" if payload.pendencia_id else ""))
    esquecer_cache()
    return art


@router.put("/artigos/{aid}")
def agente_artigo_editar(aid: str, payload: Artigo, request: Request):
    u = _exigir_alimentar(request)
    art = P["ler"](COL_ART, aid)
    if not art:
        raise HTTPException(status_code=404, detail="Artigo não encontrado.")
    novo = payload.model_dump(exclude={"pendencia_id", "motivo"})
    if novo == _conteudo(art):
        return art
    anterior = {**_conteudo(art), "versao": art.get("versao", 1), "em": art.get("atualizado_em"), "por": art.get("atualizado_por")}
    art.update(novo, versao=int(art.get("versao", 1)) + 1, atualizado_em=agora(), atualizado_por=_quem(u),
               versoes=([anterior] + list(art.get("versoes") or []))[:MAX_VERSOES])
    P["gravar"](COL_ART, aid, art)
    acao = "desativou" if anterior["ativo"] and not art["ativo"] else ("reativou" if not anterior["ativo"] and art["ativo"] else "editou")
    credito = _fechar_pendencia(payload.pendencia_id, u, aid)
    _historico(u, acao, art, " · ".join(x for x in (payload.motivo or "", credito) if x))
    esquecer_cache()
    return art


@router.post("/artigos/{aid}/restaurar")
def agente_artigo_restaurar(aid: str, payload: Restaurar, request: Request):
    u = _exigir_alimentar(request)
    art = P["ler"](COL_ART, aid)
    if not art:
        raise HTTPException(status_code=404, detail="Artigo não encontrado.")
    alvo = next((v for v in (art.get("versoes") or []) if int(v.get("versao", 0)) == payload.versao), None)
    if not alvo:
        raise HTTPException(status_code=404, detail="Essa versão não está mais guardada.")
    anterior = {**_conteudo(art), "versao": art.get("versao", 1), "em": art.get("atualizado_em"), "por": art.get("atualizado_por")}
    art.update(_conteudo(alvo), versao=int(art.get("versao", 1)) + 1, atualizado_em=agora(), atualizado_por=_quem(u),
               versoes=([anterior] + list(art.get("versoes") or []))[:MAX_VERSOES])
    P["gravar"](COL_ART, aid, art)
    _historico(u, "restaurou", art, f"voltou ao conteúdo da versão {payload.versao}")
    esquecer_cache()
    return art


@router.get("/pendencias")
def agente_pendencias(request: Request):
    _exigir_alimentar(request)
    return {"pendencias": [_com_fase(p) for p in sorted(_abertas(), key=lambda p: p.get("em") or "", reverse=True)]}


# ── Atribuir a uma pessoa do ORGANOGRAMA: o responsável do setor escreve a resposta ──
class Atribuir(BaseModel):
    login: str
    nota: Optional[str] = None


class Proposta(BaseModel):
    titulo: str
    passos: List[str]
    palavras: Optional[str] = ""

    @field_validator("titulo")
    @classmethod
    def _t(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Dê um título à resposta.")
        return v[:160]

    @field_validator("passos")
    @classmethod
    def _p(cls, v):
        v = [str(x).strip()[:600] for x in (v or []) if str(x).strip()]
        if not v:
            raise ValueError("Escreva pelo menos um passo.")
        return v[:30]


class Devolver(BaseModel):
    motivo: str


def responsaveis() -> list:
    """Usuários ativos do hub que podem perguntar ao agente (são eles que recebem pendências)."""
    saida = []
    for login, x in (P["usuarios"]() or {}).items():
        if not x.get("ativo", True):
            continue
        u = {**x, "login": login}
        saida.append({"login": _chave(login), "nome": x.get("nome") or login, "cargo": "Administrador" if x.get("admin") else "",
                      "setor": "", "tem_login": pode_usar(u), "alimenta": pode_alimentar(u)})
    return sorted(saida, key=lambda x: str(x["nome"]).lower())


@router.get("/responsaveis")
def agente_responsaveis(request: Request):
    _exigir_alimentar(request)
    return {"pessoas": responsaveis()}


@router.post("/pendencias/{pid}/atribuir")
def agente_pendencia_atribuir(pid: str, payload: Atribuir, request: Request):
    u = _exigir_alimentar(request)
    p = P["ler"](COL_PEN, pid)
    if not p or p.get("status") != "aberta":
        raise HTTPException(status_code=404, detail="Pendência não encontrada ou já fechada.")
    alvo = next((x for x in responsaveis() if x["login"] == _chave(payload.login)), None)
    if not alvo:
        raise HTTPException(status_code=400, detail="Usuário não encontrado (ou desativado).")
    if not alvo["tem_login"]:
        raise HTTPException(status_code=400, detail=f"{alvo['nome']} não tem o agente liberado (Configurações → Usuários → Agente IA).")
    p["atribuida"] = {k: alvo[k] for k in ("login", "nome", "cargo", "setor")}
    p["atribuida"].update(em=agora(), por=_quem(u), nota=(payload.nota or "")[:300])
    if p.get("proposta"):
        p["proposta"]["status"] = "substituida"
    P["gravar"](COL_PEN, pid, p)
    return _com_fase(p)


@router.get("/comigo")
def agente_comigo(request: Request):
    u = _usuario(request)
    nomes = {a.get("id"): a for a in artigos()}
    lst = sorted(_comigo(u), key=lambda p: (p.get("atribuida") or {}).get("em") or "", reverse=True)
    return {"pendencias": [{**_com_fase(p), "artigo": ({k: nomes[p["artigo_id"]].get(k) for k in ("titulo", "passos", "palavras")}
                                                        if p.get("artigo_id") in nomes else None)} for p in lst]}


@router.post("/pendencias/{pid}/proposta")
def agente_pendencia_proposta(pid: str, payload: Proposta, request: Request):
    """O responsável escreve a resposta; ela só vira artigo depois que quem alimenta aprova."""
    u = _usuario(request)
    p = P["ler"](COL_PEN, pid)
    if not p or p.get("status") != "aberta":
        raise HTTPException(status_code=404, detail="Pendência não encontrada ou já fechada.")
    if _chave((p.get("atribuida") or {}).get("login")) != _chave(u.get("login")):
        raise HTTPException(status_code=403, detail="Esta pendência não está com você.")
    p["proposta"] = {**payload.model_dump(), "status": "enviada", "em": agora(), "por": _quem(u)}
    P["gravar"](COL_PEN, pid, p)
    return _com_fase(p)


@router.post("/pendencias/{pid}/devolver")
def agente_pendencia_devolver(pid: str, payload: Devolver, request: Request):
    u = _exigir_alimentar(request)
    p = P["ler"](COL_PEN, pid)
    if not p or fase(p) != "aguardando_aprovacao":
        raise HTTPException(status_code=404, detail="Não há resposta aguardando aprovação nesta pendência.")
    p["proposta"].update(status="devolvida", devolvida_em=agora(), devolvida_por=_quem(u), motivo_devolucao=(payload.motivo or "")[:300])
    P["gravar"](COL_PEN, pid, p)
    return _com_fase(p)


@router.post("/pendencias/{pid}/descartar")
def agente_pendencia_descartar(pid: str, request: Request):
    u = _exigir_alimentar(request)
    p = P["ler"](COL_PEN, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    p.update(status="descartada", resolvida_em=agora(), resolvida_por=_quem(u))
    P["gravar"](COL_PEN, pid, p)
    return {"ok": True}


@router.get("/historico")
def agente_historico(request: Request):
    _exigir_alimentar(request)
    return {"historico": sorted(P["listar"](COL_HIS), key=lambda h: h.get("em") or "", reverse=True)[:200]}


@router.get("/painel")
def agente_painel(request: Request, dias: int = 30):
    _exigir_alimentar(request)
    dias = max(1, min(int(dias or 30), 180))
    desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    pergs = P["desde"](COL_PERG, "em", desde)
    total = len(pergs)
    respondidas = sum(1 for p in pergs if p.get("resultado") == "resposta")
    nomes = {a.get("id"): a.get("titulo") for a in artigos()}
    usos: dict = {}
    negativos: dict = {}
    for p in pergs:
        aid = p.get("artigo_id")
        if aid:
            usos[aid] = usos.get(aid, 0) + 1
            if p.get("util") is False:
                negativos[aid] = negativos.get(aid, 0) + 1
    limite_rev = (datetime.now() - timedelta(days=60)).isoformat(timespec="seconds")
    return {
        "dias": dias, "perguntas": total, "respondidas": respondidas,
        "sem_resposta": sum(1 for p in pergs if p.get("resultado") == "nao_sei"),
        "uteis": sum(1 for p in pergs if p.get("util") is True),
        "nao_resolveu": sum(1 for p in pergs if p.get("util") is False),
        "mais_usados": [{"titulo": nomes.get(k, "(artigo removido)"), "n": n} for k, n in sorted(usos.items(), key=lambda x: -x[1])[:6]],
        "mais_negativos": [{"titulo": nomes.get(k, "(artigo removido)"), "n": n} for k, n in sorted(negativos.items(), key=lambda x: -x[1])[:3]],
        "sem_revisao": [a.get("titulo") for a in artigos() if a.get("ativo", True) and (a.get("atualizado_em") or "") < limite_rev],
        "artigos_ativos": sum(1 for a in artigos() if a.get("ativo", True)),
        "ia": provedor() or "base",
    }
