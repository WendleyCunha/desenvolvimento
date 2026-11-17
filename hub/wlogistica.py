"""
hub/wlogistica.py — WLOGISTICA · armazém: montagem do palete, conferência na doca, retorno e apontamentos.
─────────────────────────────────────────────────────────────────────────────
100% dentro do wendleyservice: a FONTE é a carga do ERP (erp_cargas). Sem PDF, sem Excel, sem PQI.
A lógica é a mesma da Qualidade do PQI, adaptada ao ERP.

  ERP monta a carga (pedidos agendados)  →  aparece aqui em "Aguardando montagem"
  1ª conferência  MONTAGEM DO PALETE   — lê o código (SKU ou EAN) de cada volume de cada pedido
  2ª conferência  CONFERÊNCIA NA DOCA  — OUTRA pessoa confere o que foi montado
  Divergência (falta/sobra) fecha a etapa com motivo e vira APONTAMENTO (pendência) para resolver
  Sem pendência aberta  →  carga LIBERADA  →  cai no app do motorista (WROUTER)
  Na volta  RETORNO  — o que voltou (baixa do motorista: ausente, avaria, recusa, recolha da troca)
                       é recebido no CD peça por peça; o que não voltou vira apontamento.

  Ajuste na carga durante a montagem/doca: RETIRAR ou AGRUPAR um pedido. A etapa em andamento fica
  TRAVADA até quem está nela tocar "Ajuste feito no palete".

Onde fica gravado: no próprio documento da carga do ERP, em car["wlog"] (gravado junto com o ERP,
na mesma transação — nada pela metade). A carga só sai (ERP "Liberar saída" ou "Iniciar rota" no
app do motorista) depois de LIBERADA aqui — ERP → Ajustes → "Exigir a conferência do WLOGISTICA".
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, HTTPException, Request

import acesso
import banco
import erp as E

router = APIRouter(prefix="/api/wlog")
MOD = "wlogistica"
ETAPAS = {"montagem": "Montagem do palete", "doca": "Conferência na doca"}
MOTIVOS_DIVERGENCIA = ["Produto não localizado no estoque", "Avaria no armazém", "Volume a mais", "Erro de separação", "Pedido alterado", "Outro"]
ESTADOS_PECA = {"ok": "Peça OK", "avariada": "Avariada"}
DIAS_LISTA = 20


def _ctx(request: Request, acao: str | None = None, texto: str = ""):
    u = acesso.exigir_usuario(request)
    esq = acesso.obter_esquema(MOD)
    if esq is None:
        raise HTTPException(404, "Módulo WLOGISTICA não encontrado (falta modulos/wlogistica.html).")
    p = acesso.permissoes(u, MOD, esq)
    if not p["acoes"].get("acessar"):
        raise HTTPException(403, "Sem acesso ao WLOGISTICA.")
    if acao and not p["acoes"].get(acao):
        raise HTTPException(403, f"Sem permissão para {texto or acao}.")
    if not banco.configurado():
        raise HTTPException(503, "Banco não configurado: falta FIRESTORE_CREDS no Render.")
    E.ST.carregar()
    return u, p


def _quem(u: dict) -> dict:
    return {"login": u.get("login", ""), "nome": u.get("nome") or u.get("login", ""), "admin": bool(u.get("admin"))}


def cfg() -> dict:
    c = E.ST.config.get("wlog") or {}
    return {"motivos_divergencia": c.get("motivos_divergencia") or list(MOTIVOS_DIVERGENCIA),
            "exigir": c.get("exigir", True) is not False}


def wl(car: dict) -> dict:
    w = car.get("wlog")
    if not isinstance(w, dict):
        w = car["wlog"] = {}
    for k, v in (("montagem", None), ("doca", None), ("pendencias", []), ("ajustes", []), ("pessoas", {}), ("hist", []),
                 ("retorno", {"itens": [], "fim": None})):
        w.setdefault(k, v)
    return w


def hist(car: dict, q: dict, acao: str, det: str = "") -> None:
    w = wl(car)
    w["hist"].append({"em": E.agora(), "por": q.get("nome") or q.get("login", ""), "acao": acao, "det": det[:300]})
    w["hist"] = w["hist"][-300:]


# ══════════════════════════════════════════════════════════════════════════════
# UNIDADES: cada VOLUME de cada peça de cada pedido da carga (id estável → leituras sobrevivem a ajustes)
# ══════════════════════════════════════════════════════════════════════════════
def unidades(tx, car: dict) -> list:
    un = []
    for pid in car.get("pedidos") or []:
        ped = tx.get("pedidos", pid) or {}
        end = ped.get("endereco") or {}
        for it in ped.get("pendentes") or []:
            pr = tx.get("produtos", it["produto_id"]) or {}
            vol = max(E._int(pr.get("volumes") or 1), 1)
            for k in range(1, E._int(it.get("qtd")) + 1):
                for v in range(1, vol + 1):
                    un.append({"id": f"{pid}|{it['produto_id']}|{k}|{v}", "pid": pid, "numero": ped.get("numero"), "cliente": ped.get("cliente_nome"),
                               "bairro": end.get("bairro", ""), "produto_id": it["produto_id"], "sku": pr.get("sku", ""), "ean": pr.get("ean", ""),
                               "desc": pr.get("nome", "Produto"), "peca": k, "de": E._int(it.get("qtd")), "vol": v, "vols": vol})
    return un


def _codigo_bate(u: dict, cod: str) -> bool:
    cod = cod.upper()
    return bool(cod) and cod in {str(u.get("sku") or "").upper(), str(u.get("ean") or "").upper()} - {""}


def _tem_codigo(u: dict) -> bool:
    return bool(u.get("sku") or u.get("ean"))


def status_de(car: dict) -> str:
    """aguardando · em_montagem · montada · em_conferencia · divergencia · liberada (+ em_rota/finalizada pelo ERP)."""
    if car.get("status") in ("em_rota", "finalizada"):
        return car["status"]
    w = wl(car)
    if any(a.get("status") == "aberta" for a in w["pendencias"]):
        return "divergencia"
    mt, dc = w.get("montagem"), w.get("doca")
    if dc and dc.get("fim"):
        return "liberada"
    if dc:
        return "em_conferencia"
    if mt and mt.get("fim"):
        return "montada"
    if mt:
        return "em_montagem"
    return "aguardando"


def recalcular(car: dict, q: dict) -> str:
    w = wl(car)
    st = status_de(car)
    antes = w.get("status")
    w["status"] = st
    if st == "liberada" and not w.get("liberada"):
        w["liberada"] = {"em": E.agora(), "por": q.get("nome") or q.get("login", "")}
        hist(car, q, "carga LIBERADA para o motorista", "montagem e doca conferidas")
    elif st not in ("liberada", "em_rota", "finalizada"):
        w["liberada"] = None
    if antes != st:
        w["status_em"] = E.agora()
    return st


def liberada(car: dict) -> bool:
    return status_de(car) in ("liberada", "em_rota", "finalizada")


def ajuste_pendente(car: dict) -> dict | None:
    return next((a for a in wl(car)["ajustes"] if a.get("status") == "pendente"), None)


# ══════════════════════════════════════════════════════════════════════════════
# ETAPAS (montagem e doca)
# ══════════════════════════════════════════════════════════════════════════════
def _pessoas(car: dict) -> dict:
    w = wl(car)
    p = {k: set(v or []) for k, v in w["pessoas"].items()}
    for nome in ETAPAS:
        e = w.get(nome) or {}
        p.setdefault(nome, set()).update({x.get("login") for x in (e.get("leituras") or {}).values()} | {e.get("login"), (e.get("fim") or {}).get("login")})
        for a in w.get("anteriores") or []:
            if a.get("etapa") == nome:
                p[nome].update(x.get("login") for x in (a.get("leituras") or {}).values())
    return {k: {x for x in v if x} for k, v in p.items()}


def _checar_pessoa(car: dict, nome: str, q: dict) -> None:
    if q.get("admin"):
        return
    outra = "doca" if nome == "montagem" else "montagem"
    if q["login"] in _pessoas(car).get(outra, set()):
        raise HTTPException(403, f"Você já fez {ETAPAS[outra].lower()} da carga {car.get('numero')}. "
                                 f"{ETAPAS[nome]} precisa ser feita por OUTRA pessoa.")
    lst = wl(car)["pessoas"].setdefault(nome, [])
    if q["login"] not in lst:
        lst.append(q["login"])


def _etapa(car: dict, nome: str, q: dict) -> dict:
    if car.get("status") != "montando":
        raise HTTPException(409, "A carga já saiu — o armazém não confere mais.")
    if not car.get("pedidos"):
        raise HTTPException(409, "Carga sem pedidos.")
    w = wl(car)
    if nome == "doca" and not (w.get("montagem") or {}).get("fim"):
        raise HTTPException(409, "Feche a montagem do palete antes da conferência na doca.")
    if nome == "montagem" and w.get("doca"):
        raise HTTPException(409, "A doca já começou a conferir: a montagem está fechada.")
    if (w.get(nome) or {}).get("fim"):
        raise HTTPException(409, f"{ETAPAS[nome]} já foi fechada. Para refazer, use “Refazer”.")
    a = ajuste_pendente(car)
    if a:
        raise HTTPException(423, f"Carga TRAVADA: {('retirar' if a['tipo'] == 'retirar' else 'agrupar')} o pedido #{a.get('numero')} — toque “Ajuste feito no palete” antes de continuar.")
    _checar_pessoa(car, nome, q)
    if not w.get(nome):
        w[nome] = {"inicio": E.agora(), "login": q["login"], "por": q["nome"], "leituras": {}, "sobras": [], "fim": None}
        hist(car, q, f"{ETAPAS[nome]} iniciada")
    return w[nome]


def esperadas(tx, car: dict, nome: str) -> list:
    un = unidades(tx, car)
    if nome == "montagem":
        return un
    w = wl(car)
    lidas_mt = set(((w.get("montagem") or {}).get("leituras") or {}))
    return [u for u in un if u["id"] in lidas_mt or u["id"] in set(w.get("pos_montagem") or [])]


def ler(tx, car: dict, nome: str, q: dict, codigo: str = "", unidade: str = "", pedido: str = "", sem_leitor: bool = False, motivo: str = "") -> dict:
    et = _etapa(car, nome, q)
    lidas = et["leituras"]
    esp = esperadas(tx, car, nome)
    if unidade and not codigo:   # tocar na unidade: produto sem código, ou "sem leitor" com motivo
        alvo = next((x for x in esp if x["id"] == unidade), None)
        if not alvo:
            raise HTTPException(404, "Volume não encontrado nesta etapa da carga.")
        if alvo["id"] in lidas:
            return {"resultado": "ja_lido", "unidade": alvo}
        if _tem_codigo(alvo):
            motivo = str(motivo or "").strip()
            if not sem_leitor:
                return {"resultado": "exige_codigo", "unidade": alvo, "mensagem": "Este produto tem código: leia o código. Sem leitor? Confirme “sem leitor” e diga o motivo."}
            if not motivo:
                raise HTTPException(400, "Diga por que não foi possível ler o código.")
            lidas[alvo["id"]] = {"modo": "sem_leitor", "motivo": motivo[:200], "login": q["login"], "por": q["nome"], "em": E.agora()}
            hist(car, q, f"{ETAPAS[nome]}: confirmado sem leitor", f"{alvo['desc']} · pedido #{alvo['numero']} — {motivo[:150]}")
        else:
            lidas[alvo["id"]] = {"modo": "manual", "login": q["login"], "por": q["nome"], "em": E.agora()}
        return {"resultado": "ok", "unidade": alvo}
    cod = re.sub(r"\s+", "", str(codigo or "")).upper()
    if not cod:
        raise HTTPException(400, "Leitura vazia.")
    livres = [x for x in esp if _codigo_bate(x, cod) and x["id"] not in lidas]
    if pedido:
        livres = [x for x in livres if x["pid"] == pedido]
    if not livres:
        na_carga = any(_codigo_bate(x, cod) for x in unidades(tx, car))
        prod = next((p for p in E.ST.dados["produtos"].values() if cod in {str(p.get("sku") or "").upper(), str(p.get("ean") or "").upper()}), None)
        desc = (prod or {}).get("nome") or cod
        et["sobras"].append({"id": uuid.uuid4().hex[:8], "codigo": cod, "desc": desc, "login": q["login"], "por": q["nome"], "em": E.agora()})
        return {"resultado": "sobra", "codigo": cod, "desc": desc,
                "mensagem": "Todos os volumes deste produto já foram lidos — é um volume A MAIS." if na_carga else "Este produto NÃO é desta carga."}
    pids = list(dict.fromkeys(x["pid"] for x in livres))
    if len(pids) > 1:
        return {"resultado": "escolher_pedido", "codigo": cod,
                "opcoes": [{"pid": p, "numero": next(x["numero"] for x in livres if x["pid"] == p), "cliente": next(x["cliente"] for x in livres if x["pid"] == p),
                            "faltam": sum(1 for x in livres if x["pid"] == p)} for p in pids]}
    alvo = livres[0]
    lidas[alvo["id"]] = {"modo": "codigo", "codigo": cod, "login": q["login"], "por": q["nome"], "em": E.agora()}
    return {"resultado": "ok", "unidade": alvo}


def desfazer(car: dict, nome: str, q: dict, unidade: str) -> None:
    et = _etapa(car, nome, q)
    if et["leituras"].pop(unidade, None) is None:
        et["sobras"] = [s for s in et["sobras"] if s["id"] != unidade]
    hist(car, q, f"{ETAPAS[nome]}: leitura desfeita", unidade.split("|")[1] if "|" in unidade else unidade)


def divergencias(tx, car: dict, nome: str) -> list:
    w = wl(car)
    et = w[nome]
    lidas = et["leituras"]
    esp = esperadas(tx, car, nome)
    div: dict = {}

    def soma(tipo, pid, numero, desc, extra=None):
        k = f"{tipo}|{pid}|{desc}"
        d = div.setdefault(k, {"chave": k, "tipo": tipo, "pid": pid, "numero": numero, "desc": desc, "qtd": 0, **(extra or {})})
        d["qtd"] += 1
    for u in esp:
        if u["id"] not in lidas:
            soma("falta", u["pid"], u["numero"], u["desc"] + (f" (vol {u['vol']}/{u['vols']})" if u["vols"] > 1 else ""))
    if nome == "doca":
        ids = {u["id"] for u in esp}
        for uid in lidas:
            if uid not in ids:
                soma("sobra", uid.split("|")[0], "", "volume lido na doca que não estava no palete")
    for s in et.get("sobras") or []:
        soma("sobra", "", "", s["desc"], {"codigo": s["codigo"]})
    return list(div.values())


def finalizar(tx, car: dict, nome: str, q: dict, respostas: list, obs: str) -> dict:
    et = _etapa(car, nome, q)
    todas = divergencias(tx, car, nome)
    resp = {str(d.get("chave")): d for d in respostas or []}
    if [d for d in todas if not str((resp.get(d["chave"]) or {}).get("motivo") or "").strip()]:
        return {"resultado": "precisa_motivo", "divergencias": todas, "motivos": cfg()["motivos_divergencia"]}
    for d in todas:
        d["motivo"] = str(resp[d["chave"]]["motivo"])[:120]
        d["obs"] = str(resp[d["chave"]].get("obs") or "")[:300]
    et["fim"] = {"em": E.agora(), "login": q["login"], "por": q["nome"], "ok": not todas, "divergencias": todas, "obs": str(obs or "")[:500]}
    w = wl(car)
    for d in todas:
        w["pendencias"].append({"id": uuid.uuid4().hex[:8], "origem": nome, "tipo": d["tipo"], "pid": d.get("pid"), "numero": d.get("numero"),
                                "desc": d["desc"], "qtd": d["qtd"], "motivo": d["motivo"], "obs": d["obs"], "status": "aberta",
                                "por": q["nome"], "em": E.agora()})
    hist(car, q, f"{ETAPAS[nome]} fechada" + (" — OK" if not todas else f" com {len(todas)} divergência(s)"), "; ".join(f"{d['tipo']} {d['qtd']}× {d['desc']}" for d in todas)[:300])
    st = recalcular(car, q)
    return {"resultado": "ok", "divergencias": todas, "status": st}


def refazer(car: dict, nome: str, q: dict, motivo: str) -> None:
    if car.get("status") != "montando":
        raise HTTPException(409, "A carga já saiu.")
    w = wl(car)
    if not w.get(nome):
        raise HTTPException(404, "Etapa ainda não começou.")
    if nome == "montagem" and w.get("doca"):
        refazer(car, "doca", q, motivo)
    w.setdefault("anteriores", []).append({**w[nome], "etapa": nome, "arquivada_em": E.agora(), "motivo": motivo[:200]})
    w["anteriores"] = w["anteriores"][-10:]
    w[nome] = None
    w["pendencias"] = [a if not (a.get("origem") == nome and a.get("status") == "aberta") else {**a, "status": "superada", "resolucao": "etapa refeita"}
                       for a in w["pendencias"]]
    hist(car, q, f"{ETAPAS[nome]} refeita (leituras arquivadas)", motivo)
    recalcular(car, q)


# ══════════════════════════════════════════════════════════════════════════════
# AJUSTE NA CARGA (retirar / agrupar pedido) — a etapa em andamento trava até "Ajuste feito no palete"
# ══════════════════════════════════════════════════════════════════════════════
def ajustar(tx, car: dict, cid: str, q: dict, tipo: str, pid: str, motivo: str, u: dict) -> dict:
    if car.get("status") != "montando":
        raise HTTPException(409, "A carga já saiu.")
    motivo = str(motivo or "").strip()
    if not motivo:
        raise HTTPException(400, "Informe o motivo do ajuste.")
    ped = tx.get("pedidos", pid)
    if not ped:
        raise HTTPException(404, "Pedido não encontrado.")
    w = wl(car)
    ids = list(car.get("pedidos") or [])
    if tipo == "retirar":
        if pid not in ids:
            raise HTTPException(409, "O pedido não está nesta carga.")
        if len(ids) == 1:
            raise HTTPException(409, "É o único pedido da carga — desfaça a carga no ERP.")
        ids.remove(pid)
    elif tipo == "agrupar":
        if pid in ids:
            raise HTTPException(409, "O pedido já está nesta carga.")
        ids.append(pid)
    else:
        raise HTTPException(400, "Ajuste inválido.")
    car["id"] = cid
    E._definir_pedidos_carga(tx, u, cid, car, ids)
    car = tx.get("cargas", cid)
    w = wl(car)
    etapa = "doca" if (w.get("montagem") or {}).get("fim") else ("montagem" if w.get("montagem") else "")
    if tipo == "retirar":   # leituras do pedido retirado saem (as peças precisam sair do palete)
        for nome in ETAPAS:
            if w.get(nome):
                w[nome]["leituras"] = {k: v for k, v in w[nome]["leituras"].items() if not k.startswith(pid + "|")}
    elif etapa == "doca":   # entrou depois da montagem fechada: a doca confere direto
        w.setdefault("pos_montagem", [])
        w["pos_montagem"] += [x["id"] for x in unidades(tx, car) if x["pid"] == pid and x["id"] not in w["pos_montagem"]]
        if (w.get("doca") or {}).get("fim"):
            w["doca"]["fim"] = None
    a = {"id": uuid.uuid4().hex[:8], "tipo": tipo, "pid": pid, "numero": ped.get("numero"), "cliente": ped.get("cliente_nome"), "motivo": motivo[:200],
         "etapa": etapa, "status": "pendente" if etapa else "feito", "por": q["nome"], "em": E.agora()}
    w["ajustes"].append(a)
    hist(car, q, f"ajuste na carga: {'RETIRAR' if tipo == 'retirar' else 'AGRUPAR'} pedido #{ped.get('numero')}", motivo)
    recalcular(car, q)
    tx.put("cargas", cid, {k: v for k, v in car.items() if k != "id"})
    return a


# ══════════════════════════════════════════════════════════════════════════════
# RETORNO NO CD — o ERP registra o que volta na baixa (motorista/app ou manual) em wlog.retorno.itens
# ══════════════════════════════════════════════════════════════════════════════
def esperar_retorno(tx, car: dict, pid: str, ped: dict, itens: list, origem: str, motivo: str) -> None:
    """Chamado pela baixa do ERP: cada peça que vai voltar para o CD vira um item a receber."""
    w = wl(car)
    for it in itens:
        pr = tx.get("produtos", it["produto_id"]) or {}
        for _ in range(E._int(it.get("qtd"))):
            w["retorno"]["itens"].append({"id": uuid.uuid4().hex[:8], "pid": pid, "numero": ped.get("numero"), "cliente": ped.get("cliente_nome"),
                                          "produto_id": it["produto_id"], "desc": pr.get("nome", "Produto"), "sku": pr.get("sku", ""),
                                          "origem": origem, "motivo": motivo, "em": E.agora(), "recebido": None, "nao_voltou": None})
    w["retorno"]["fim"] = None


def receber(car: dict, q: dict, item_id: str, estado: str, obs: str, codigo: str = "") -> dict:
    w = wl(car)
    it = next((x for x in w["retorno"]["itens"] if x["id"] == item_id), None)
    if not it:
        raise HTTPException(404, "Peça não encontrada no retorno desta carga.")
    if it.get("recebido") or it.get("nao_voltou"):
        raise HTTPException(409, "Esta peça já foi tratada.")
    if estado not in ESTADOS_PECA:
        raise HTTPException(400, "Informe o estado da peça (OK ou avariada).")
    it["recebido"] = {"em": E.agora(), "por": q["nome"], "login": q["login"], "estado": estado, "obs": str(obs or "")[:300], "codigo": codigo[:40]}
    hist(car, q, "peça recebida no CD", f"pedido #{it['numero']} · {it['desc']} · {ESTADOS_PECA[estado]}")
    return it


def nao_voltou(car: dict, q: dict, item_id: str, obs: str) -> dict:
    w = wl(car)
    it = next((x for x in w["retorno"]["itens"] if x["id"] == item_id), None)
    if not it:
        raise HTTPException(404, "Peça não encontrada no retorno desta carga.")
    if it.get("recebido") or it.get("nao_voltou"):
        raise HTTPException(409, "Esta peça já foi tratada.")
    if not str(obs or "").strip():
        raise HTTPException(400, "Explique o que aconteceu com a peça.")
    it["nao_voltou"] = {"em": E.agora(), "por": q["nome"], "obs": str(obs)[:300]}
    w["pendencias"].append({"id": uuid.uuid4().hex[:8], "origem": "retorno", "tipo": "nao_voltou", "pid": it["pid"], "numero": it["numero"],
                            "desc": it["desc"], "qtd": 1, "motivo": it.get("motivo") or "", "obs": str(obs)[:300], "status": "aberta",
                            "por": q["nome"], "em": E.agora()})
    hist(car, q, "peça NÃO voltou para o CD", f"pedido #{it['numero']} · {it['desc']} — {obs}")
    return it


def retorno_resumo(car: dict) -> dict:
    its = wl(car)["retorno"]["itens"]
    return {"total": len(its), "recebidos": sum(1 for x in its if x.get("recebido")), "nao_voltou": sum(1 for x in its if x.get("nao_voltou")),
            "pendentes": sum(1 for x in its if not x.get("recebido") and not x.get("nao_voltou")), "fim": wl(car)["retorno"].get("fim")}


# ══════════════════════════════════════════════════════════════════════════════
# O QUE A TELA VÊ
# ══════════════════════════════════════════════════════════════════════════════
def _etapa_pub(e: dict | None) -> dict | None:
    if not e:
        return None
    fim = e.get("fim") or {}
    return {"inicio": e.get("inicio"), "por": e.get("por"), "lidas": len(e.get("leituras") or {}), "sobras": len(e.get("sobras") or []),
            "leitores": sorted({x.get("por") for x in (e.get("leituras") or {}).values() if x.get("por")}),
            "fim_em": fim.get("em"), "fim_por": fim.get("por"), "ok": fim.get("ok"), "divergencias": len(fim.get("divergencias") or [])}


def resumo_carga(tx, cid: str, car: dict) -> dict:
    w = wl(car)
    un = unidades(tx, car) if car.get("status") == "montando" else []
    veic = tx.get("parceiros", car.get("veiculo_id") or "") or {}
    mot = tx.get("parceiros", car.get("motorista_id") or "") or {}
    return {"id": cid, "numero": car.get("numero"), "data": car.get("data"), "erp_status": car.get("status"), "status": status_de(car),
            "placa": veic.get("placa") or veic.get("nome") or "", "motorista": mot.get("nome") or "", "pedidos": len(car.get("pedidos") or []),
            "volumes": len(un), "montagem": _etapa_pub(w.get("montagem")), "doca": _etapa_pub(w.get("doca")),
            "pend_abertas": sum(1 for a in w["pendencias"] if a.get("status") == "aberta"),
            "ajuste": ajuste_pendente(car), "liberada": w.get("liberada"), "retorno": retorno_resumo(car),
            "saiu_em": car.get("saiu_em"), "fechada_em": car.get("fechada_em"), "status_em": w.get("status_em")}


def detalhe_carga(tx, cid: str, car: dict) -> dict:
    w = wl(car)
    un = unidades(tx, car) if car.get("status") == "montando" else []
    lmt = (w.get("montagem") or {}).get("leituras") or {}
    ldc = (w.get("doca") or {}).get("leituras") or {}
    pos = set(w.get("pos_montagem") or [])
    for u in un:
        u["montagem"] = lmt.get(u["id"])
        u["doca"] = ldc.get(u["id"])
        u["pos_montagem"] = u["id"] in pos
        u["tem_codigo"] = _tem_codigo(u)
    peds = []
    for pid in car.get("pedidos") or []:
        p = tx.get("pedidos", pid) or {}
        end = p.get("endereco") or {}
        peds.append({"id": pid, "numero": p.get("numero"), "cliente": p.get("cliente_nome"), "bairro": end.get("bairro"), "cidade": end.get("cidade"),
                     "status": p.get("status"), "tipo": p.get("tipo"), "baixa": (car.get("baixas") or {}).get(pid)})
    return {**resumo_carga(tx, cid, car), "unidades": un, "pedidos_det": peds, "pendencias": w["pendencias"], "ajustes": w["ajustes"][-20:],
            "sobras": {n: (w.get(n) or {}).get("sobras") or [] for n in ETAPAS}, "retorno_itens": w["retorno"]["itens"],
            "hist": w["hist"][-80:], "divergencias_fim": {n: ((w.get(n) or {}).get("fim") or {}).get("divergencias") or [] for n in ETAPAS}}


def _cargas_visiveis() -> list:
    corte = E.hoje()
    from datetime import datetime, timedelta
    corte = (datetime.strptime(corte, "%Y-%m-%d") - timedelta(days=DIAS_LISTA)).strftime("%Y-%m-%d")
    out = []
    for cid, car in E.ST.dados["cargas"].items():
        if car.get("status") == "montando" and car.get("pedidos"):
            out.append((cid, car))
        elif car.get("status") in ("em_rota", "finalizada") and (str(car.get("data") or "") >= corte or retorno_resumo(car)["pendentes"]):
            out.append((cid, car))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════════════════════════
@router.get("/estado")
def estado(request: Request):
    u, p = _ctx(request)
    with E.ST.trava:
        tx = E.Tx(u)
        cargas = [resumo_carga(tx, cid, car) for cid, car in _cargas_visiveis()]
        pend = [{**a, "carga_id": cid, "carga": car.get("numero")} for cid, car in _cargas_visiveis() for a in wl(car)["pendencias"] if a.get("status") == "aberta"]
        agendados = [{"id": i, "numero": d.get("numero"), "cliente": d.get("cliente_nome"), "data": (d.get("agendamento") or {}).get("data")}
                     for i, d in E.ST.dados["pedidos"].items() if d.get("status") == "agendado" and not d.get("carga_id")]
    cargas.sort(key=lambda x: (x["data"] or "", x["numero"] or 0), reverse=True)
    return {"cargas": cargas, "pendencias": pend, "agendados": agendados, "perm": p, "cfg": cfg(), "estados": ESTADOS_PECA,
            "eu": _quem(u), "hoje": E.hoje(), "agora": E.agora()}


def _carga(tx, cid: str) -> dict:
    car = tx.get("cargas", cid)
    if not car:
        raise HTTPException(404, "Carga não encontrada.")
    return car


@router.get("/cargas/{cid}")
def ver_carga(cid: str, request: Request):
    u, p = _ctx(request)
    with E.ST.trava:
        tx = E.Tx(u)
        return detalhe_carga(tx, cid, _carga(tx, cid))


def _gravar(tx, cid: str, car: dict, q: dict) -> dict:
    recalcular(car, q)
    car["atualizado_em"] = E.agora()
    tx.put("cargas", cid, {k: v for k, v in car.items() if k != "id"})
    tx.commit()
    return detalhe_carga(E.Tx({}), cid, E.ST.dados["cargas"][cid])


@router.post("/cargas/{cid}/{etapa}/leitura")
async def rota_leitura(cid: str, etapa: str, request: Request):
    if etapa not in ETAPAS:
        raise HTTPException(404, "Etapa inválida.")
    u, p = _ctx(request, etapa, ETAPAS[etapa].lower())
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        r = ler(tx, car, etapa, _quem(u), str(c.get("codigo") or ""), str(c.get("unidade") or ""), str(c.get("pedido") or ""),
                bool(c.get("sem_leitor")), str(c.get("motivo") or ""))
        if r["resultado"] in ("ok", "sobra"):
            r["carga"] = _gravar(tx, cid, car, _quem(u))
        return r


@router.post("/cargas/{cid}/{etapa}/desfazer")
async def rota_desfazer(cid: str, etapa: str, request: Request):
    if etapa not in ETAPAS:
        raise HTTPException(404, "Etapa inválida.")
    u, p = _ctx(request, etapa, ETAPAS[etapa].lower())
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        desfazer(car, etapa, _quem(u), str(c.get("unidade") or ""))
        return _gravar(tx, cid, car, _quem(u))


@router.post("/cargas/{cid}/{etapa}/finalizar")
async def rota_finalizar(cid: str, etapa: str, request: Request):
    if etapa not in ETAPAS:
        raise HTTPException(404, "Etapa inválida.")
    u, p = _ctx(request, etapa, ETAPAS[etapa].lower())
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        r = finalizar(tx, car, etapa, _quem(u), c.get("respostas") or [], str(c.get("obs") or ""))
        if r["resultado"] == "ok":
            r["carga"] = _gravar(tx, cid, car, _quem(u))
        return r


@router.post("/cargas/{cid}/refazer/{etapa}")
async def rota_refazer(cid: str, etapa: str, request: Request):
    if etapa not in ETAPAS:
        raise HTTPException(404, "Etapa inválida.")
    u, p = _ctx(request, "apontamentos", "refazer etapas")
    c = await request.json()
    if not str(c.get("motivo") or "").strip():
        raise HTTPException(400, "Informe o motivo.")
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        refazer(car, etapa, _quem(u), str(c["motivo"]))
        return _gravar(tx, cid, car, _quem(u))


@router.post("/cargas/{cid}/ajuste")
async def rota_ajuste(cid: str, request: Request):
    u, p = _ctx(request, "apontamentos", "ajustar a carga")
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        a = ajustar(tx, car, cid, _quem(u), str(c.get("tipo") or ""), str(c.get("pedido_id") or ""), str(c.get("motivo") or ""), u)
        tx.commit()
        return {"ajuste": a, "carga": detalhe_carga(E.Tx({}), cid, E.ST.dados["cargas"][cid])}


@router.post("/cargas/{cid}/ajuste/{aid}/feito")
def rota_ajuste_feito(cid: str, aid: str, request: Request):
    u, p = _ctx(request)
    if not (p["acoes"].get("montagem") or p["acoes"].get("doca") or p["acoes"].get("apontamentos")):
        raise HTTPException(403, "Sem permissão para validar o ajuste.")
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        a = next((x for x in wl(car)["ajustes"] if x["id"] == aid), None)
        if not a or a.get("status") != "pendente":
            raise HTTPException(404, "Ajuste pendente não encontrado.")
        a.update(status="feito", feito_em=E.agora(), feito_por=_quem(u)["nome"])
        hist(car, _quem(u), "ajuste feito no palete", f"{a['tipo']} pedido #{a.get('numero')}")
        return _gravar(tx, cid, car, _quem(u))


@router.put("/cargas/{cid}/pendencias/{aid}")
async def rota_pendencia(cid: str, aid: str, request: Request):
    u, p = _ctx(request, "apontamentos", "tratar apontamentos")
    c = await request.json()
    nota = str(c.get("nota") or "").strip()
    if not nota:
        raise HTTPException(400, "Escreva como foi resolvido.")
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        a = next((x for x in wl(car)["pendencias"] if x["id"] == aid), None)
        if not a or a.get("status") != "aberta":
            raise HTTPException(404, "Apontamento aberto não encontrado.")
        a.update(status="resolvida", resolucao=nota[:300], resolvido_em=E.agora(), resolvido_por=_quem(u)["nome"])
        hist(car, _quem(u), "apontamento resolvido", f"{a['tipo']} · {a['desc']} — {nota[:200]}")
        return _gravar(tx, cid, car, _quem(u))


@router.post("/cargas/{cid}/retorno/receber")
async def rota_receber(cid: str, request: Request):
    u, p = _ctx(request, "retorno", "receber retornos")
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        receber(car, _quem(u), str(c.get("item_id") or ""), str(c.get("estado") or ""), str(c.get("obs") or ""), str(c.get("codigo") or ""))
        return _gravar(tx, cid, car, _quem(u))


@router.post("/cargas/{cid}/retorno/nao-voltou")
async def rota_nao_voltou(cid: str, request: Request):
    u, p = _ctx(request, "retorno", "receber retornos")
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        nao_voltou(car, _quem(u), str(c.get("item_id") or ""), str(c.get("obs") or ""))
        return _gravar(tx, cid, car, _quem(u))


@router.post("/cargas/{cid}/retorno/concluir")
def rota_concluir_retorno(cid: str, request: Request):
    u, p = _ctx(request, "retorno", "concluir o retorno")
    with E.ST.trava:
        tx = E.Tx(u)
        car = _carga(tx, cid)
        r = retorno_resumo(car)
        if car.get("status") == "montando":
            raise HTTPException(409, "A carga ainda não saiu.")
        if r["pendentes"]:
            raise HTTPException(409, f"Ainda há {r['pendentes']} peça(s) para receber (ou marcar que não voltou).")
        wl(car)["retorno"]["fim"] = {"em": E.agora(), "por": _quem(u)["nome"]}
        hist(car, _quem(u), "retorno concluído", f"{r['recebidos']} recebida(s) · {r['nao_voltou']} não voltou")
        return _gravar(tx, cid, car, _quem(u))


@router.put("/config")
async def rota_config(request: Request):
    u, p = _ctx(request, "configurar", "configurar o WLOGISTICA")
    c = await request.json()
    with E.ST.trava:
        tx = E.Tx(u)
        conf = tx.config()
        w = dict(conf.get("wlog") or {})
        if "motivos_divergencia" in c:
            w["motivos_divergencia"] = [str(x).strip()[:80] for x in c["motivos_divergencia"] or [] if str(x).strip()][:30] or list(MOTIVOS_DIVERGENCIA)
        if "exigir" in c:
            w["exigir"] = bool(c["exigir"])
        conf["wlog"] = w
        tx.commit()
    return {"ok": True, "cfg": cfg()}
