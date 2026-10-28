"""
hub/secretaria_regras.py — REGRAS DA SECRETARIA (Parque Aliança), sem banco.
─────────────────────────────────────────────────────────────────────────────
Funções puras: recebem dicionários, devolvem números. Nada aqui fala com o
Firestore — por isso dá para testar tudo isolado (tests/test_secretaria_regras.py).

MÊS — a chave interna é sempre "AAAA-MM" do calendário (ex.: "2026-09").
  • Ano de serviço (AS) = setembro a agosto, com o número do ANO DO AGOSTO:
      2026-09 … 2027-08  →  AS 2027   (igual ao JW Hub e ao cartão S-21)
  • Rótulo gravado no banco ("mes_referencia"), mantido por compatibilidade
    com o Streamlit (admin-parquealianca): "MÊS <ano de serviço>"
      2026-09 → "SETEMBRO 2027"   ·   2027-01 → "JANEIRO 2027"
  • O formulário público (relatoriosparquealianca) ainda grava o ANO CIVIL
    em set–dez ("SETEMBRO 2026" para 2026-09). `resolver_chave` desfaz essa
    ambiguidade olhando a DATA DE ENVIO — ninguém manda relatório de um mês
    que ainda não começou, nem 1 ano depois.
  • Corte: relatório enviado do dia 1 ao dia 20 conta para o mês ANTERIOR;
    do dia 21 em diante, para o mês ATUAL.

CATEGORIA DO MÊS (regra do secretário):
  1. relatório com "categoria_mes" gravada → vale ela (ajuste manual);
  2. membro é pioneiro regular → PIONEIRO REGULAR;
  3. horas ≥ limite (padrão 15) → PIONEIRO AUXILIAR;
  4. senão → PUBLICADOR.

ATIVO / INATIVO (definição do S-1/S-10):
  • ativo no mês M  = participou em pelo menos 1 dos 6 meses até M (M-5…M);
  • ficou inativo em M = participou em M-6 e em nenhum de M-5…M;
  • reativado em M  = participou em M, estava inativo em M-1.
"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

PUB, AUX, REG = "PUBLICADOR", "PIONEIRO AUXILIAR", "PIONEIRO REGULAR"
CATEGORIAS = [PUB, AUX, REG]

MESES = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
         "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
MESES_TITULO = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
ORDEM_AS = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
JANELA_ATIVO = 6
LIMITE_AUX_PADRAO = 15
CORTE_DIA_PADRAO = 20
FUSO = timezone(timedelta(hours=-3))  # Brasília


# ══════════════════════════════════════════════════════════════════════════════
# TEXTO E NOMES
# ══════════════════════════════════════════════════════════════════════════════
def sem_acento(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or ""))
                   if unicodedata.category(c) != "Mn")


def normalizar(t) -> str:
    return " ".join(sem_acento(t).lower().split())


def achar_membro(nome_recebido, nomes) -> str | None:
    """Mesmo algoritmo do Streamlit (utilitarios.normalizar_nome_no_banco),
    para os dois sistemas reconhecerem as mesmas pessoas."""
    entrada = normalizar(nome_recebido)
    if len(entrada) < 2:
        return None
    tokens = set(entrada.split())
    melhor, maior = None, 0.0
    for oficial in nomes:
        of = normalizar(oficial)
        tok_of = of.split()
        if entrada == of:
            return oficial
        if len(tokens) == 1:
            p1 = tok_of[0] if tok_of else ""
            p2 = tok_of[1] if len(tok_of) > 1 else ""
            if entrada in (p1, p2):
                return oficial
        if tokens and tokens.issubset(set(tok_of)):
            s = len(tokens) / max(len(tok_of), 1) + 0.5
            if s > maior:
                maior, melhor = s, oficial
            continue
        primeiro = tok_of[0] if tok_of else ""
        for t in tokens:
            if t == primeiro and len(t) >= 3 and 0.88 > maior:
                maior, melhor = 0.88, oficial
        s = SequenceMatcher(None, entrada, of).ratio()
        if s > maior:
            maior, melhor = s, oficial
    return melhor if maior >= 0.82 else None


# ══════════════════════════════════════════════════════════════════════════════
# MESES
# ══════════════════════════════════════════════════════════════════════════════
def chave(ano: int, mes: int) -> str:
    return f"{int(ano):04d}-{int(mes):02d}"


def partes(ch: str) -> tuple[int, int]:
    a, m = str(ch).split("-")
    return int(a), int(m)


def chave_valida(ch) -> bool:
    try:
        a, m = partes(ch)
        return 2000 <= a <= 2100 and 1 <= m <= 12 and len(str(ch)) == 7
    except Exception:  # noqa: BLE001
        return False


def somar(ch: str, n: int) -> str:
    a, m = partes(ch)
    i = a * 12 + (m - 1) + n
    return chave(i // 12, i % 12 + 1)


def distancia(de: str, ate: str) -> int:
    """Quantos meses de `de` até `ate` (positivo se `ate` é depois)."""
    a1, m1 = partes(de)
    a2, m2 = partes(ate)
    return (a2 * 12 + m2) - (a1 * 12 + m1)


def ano_servico(ch: str) -> int:
    a, m = partes(ch)
    return a + 1 if m >= 9 else a


def meses_do_as(as_: int) -> list[str]:
    return [chave(as_ - 1 if m >= 9 else as_, m) for m in ORDEM_AS]


def rotulo_banco(ch: str) -> str:
    """Rótulo gravado em mes_referencia (convenção do admin: ano de serviço)."""
    _, m = partes(ch)
    return f"{MESES[m - 1]} {ano_servico(ch)}"


def rotulo_civil(ch: str) -> str:
    a, m = partes(ch)
    return f"{MESES[m - 1]} {a}"


def rotulo(ch: str) -> str:
    """Para pessoas: 'Setembro 2026'."""
    a, m = partes(ch)
    return f"{MESES_TITULO[m - 1]} {a}"


def rotulos_possiveis(ch: str) -> list[str]:
    """Todos os textos de mes_referencia que podem significar este mês."""
    return sorted({rotulo_banco(ch), rotulo_civil(ch)})


def chave_por_data(d, corte: int = CORTE_DIA_PADRAO) -> str:
    """Mês a que se refere um relatório enviado na data d (dia 1–corte → mês anterior)."""
    if isinstance(d, datetime):
        d = (d.astimezone(FUSO) if d.tzinfo else d).date()
    if d.day > corte:
        return chave(d.year, d.month)
    return somar(chave(d.year, d.month), -1)


def _data(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return (v.astimezone(FUSO) if v.tzinfo else v).date()
    if isinstance(v, date):
        return v
    try:
        t = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        return (dt.astimezone(FUSO) if dt.tzinfo else dt).date()
    except ValueError:
        return None


def _mes_do_texto(t: str) -> tuple[int | None, int | None]:
    p = sem_acento(t).upper().split()
    if len(p) != 2:
        return None, None
    nomes = [sem_acento(x) for x in MESES]
    if p[0] not in nomes:
        return None, None
    try:
        return nomes.index(p[0]) + 1, int(p[1])
    except ValueError:
        return None, None


def data_do_relatorio(rel: dict) -> date | None:
    for campo in ("data_envio", "timestamp", "data_processamento", "_criado_em"):
        d = _data(rel.get(campo))
        if d:
            return d
    return None


def resolver_chave(rel: dict) -> str | None:
    """Mês (AAAA-MM) a que o relatório se refere — tolera as duas convenções."""
    ch = rel.get("mes_chave")
    if chave_valida(ch):
        return ch
    mes, ano = _mes_do_texto(rel.get("mes_referencia", ""))
    if not mes:
        return None
    if mes <= 8:
        return chave(ano, mes)
    pelo_admin, pelo_civil = chave(ano - 1, mes), chave(ano, mes)
    enviado = data_do_relatorio(rel)
    if enviado:
        mes_envio = chave(enviado.year, enviado.month)
        validos = [(distancia(c, mes_envio), c) for c in (pelo_admin, pelo_civil)
                   if 0 <= distancia(c, mes_envio) <= 3]
        if validos:
            return min(validos)[1]
    return pelo_admin


# ══════════════════════════════════════════════════════════════════════════════
# MEMBROS
# ══════════════════════════════════════════════════════════════════════════════
def cargos(m: dict) -> list[str]:
    c = m.get("cargo") or []
    if isinstance(c, str):
        return [c] if c else []
    return [x for x in c if x]


def eh_regular(m: dict) -> bool:
    return m.get("categoria") == REG or "Pioneiro regular" in cargos(m)


def inicio_do_membro(m: dict) -> str | None:
    ch = m.get("inicio_chave")
    if chave_valida(ch):
        return ch
    mes, ano = _mes_do_texto(m.get("mes_inicio", ""))
    if not mes:
        return None
    return chave(ano - 1 if mes >= 9 else ano, mes)  # mes_inicio usa a convenção do admin


def saiu_em(m: dict) -> str | None:
    ch = m.get("saiu_em")
    return ch if chave_valida(ch) else None


def no_quadro(m: dict, ch: str) -> bool:
    """O membro pertence à congregação no mês ch?"""
    s = saiu_em(m)
    if s and distancia(s, ch) >= 0:
        return False
    i = inicio_do_membro(m)
    return not (i and distancia(ch, i) > 0)


# ══════════════════════════════════════════════════════════════════════════════
# RELATÓRIOS
# ══════════════════════════════════════════════════════════════════════════════
def _num(v) -> int:
    try:
        f = float(v)
        return 0 if f != f else max(int(round(f)), 0)
    except (TypeError, ValueError):
        return 0


def participou(rel: dict) -> bool:
    """Registro antigo sem o campo (baixa manual) = entregou e participou."""
    if _num(rel.get("horas")) > 0 or _num(rel.get("estudos_biblicos")) > 0:
        return True
    if "participou_ministerio" in rel:
        return bool(rel.get("participou_ministerio"))
    return True


def classificar(membro: dict, rel: dict, limite: int = LIMITE_AUX_PADRAO) -> str:
    manual = rel.get("categoria_mes")
    if manual in CATEGORIAS:
        return manual
    if eh_regular(membro):
        return REG
    if _num(rel.get("horas")) >= limite:
        return AUX
    return PUB


def preparar(relatorios: list[dict], membros: dict[str, dict], limite: int = LIMITE_AUX_PADRAO) -> list[dict]:
    """Uma linha por relatório, já com mês, membro, categoria e duplicidade resolvidos."""
    nomes = list(membros.keys())
    cache_nome: dict[str, str | None] = {}
    linhas = []
    for r in relatorios:
        if r.get("status_validacao") == "EXCLUIDO":
            continue
        ch = resolver_chave(r)
        mid = r.get("membro_id") if r.get("membro_id") in membros else None
        if not mid:
            nome = str(r.get("nome", ""))
            if nome not in cache_nome:
                cache_nome[nome] = achar_membro(nome, nomes)
            mid = cache_nome[nome]
        situacao = "SEM_MES" if not ch else ("IDENTIFICADO" if mid else "TRIAGEM")
        cat = classificar(membros[mid], r, limite) if mid else None
        d = data_do_relatorio(r)
        linhas.append({
            "id": r.get("id"), "chave": ch, "membro_id": mid, "nome_enviado": r.get("nome", ""),
            "situacao": situacao, "categoria": cat, "categoria_manual": r.get("categoria_mes") in CATEGORIAS,
            "participou": participou(r), "horas": _num(r.get("horas")), "estudos": _num(r.get("estudos_biblicos")),
            "observacoes": str(r.get("observacoes") or "").strip() if str(r.get("observacoes") or "").lower() not in ("nan", "none") else "",
            "data": d.isoformat() if d else "", "origem": r.get("origem") or ("formulario" if r.get("data_envio") else "baixa"),
            "rotulo_banco": r.get("mes_referencia", ""), "rotulo_errado": bool(ch) and r.get("mes_referencia", "") != rotulo_banco(ch),
            "principal": True, "duplicado": False,
        })
    # duplicidade: mesmo membro, mesmo mês → vale o mais recente
    grupos: dict[tuple, list[dict]] = {}
    for ln in linhas:
        if ln["situacao"] == "IDENTIFICADO":
            grupos.setdefault((ln["membro_id"], ln["chave"]), []).append(ln)
    for g in grupos.values():
        if len(g) > 1:
            g.sort(key=lambda x: (x["data"], str(x["id"])), reverse=True)
            for i, ln in enumerate(g):
                ln["duplicado"] = True
                ln["principal"] = i == 0
    return linhas


def validas(linhas: list[dict]) -> list[dict]:
    return [ln for ln in linhas if ln["situacao"] == "IDENTIFICADO" and ln["principal"]]


def participacoes(linhas: list[dict]) -> dict[str, set[str]]:
    p: dict[str, set[str]] = {}
    for ln in validas(linhas):
        if ln["participou"]:
            p.setdefault(ln["membro_id"], set()).add(ln["chave"])
    return p


# ══════════════════════════════════════════════════════════════════════════════
# ATIVIDADE
# ══════════════════════════════════════════════════════════════════════════════
def ativo_em(part: set[str], ch: str) -> bool:
    return any(somar(ch, -i) in part for i in range(JANELA_ATIVO))


def situacao(membro: dict, part: set[str], ch: str) -> str:
    """ativo · inativo · sem_relatorio · fora (ainda não chegou / já saiu)."""
    if not no_quadro(membro, ch):
        return "fora"
    if ativo_em(part, ch):
        return "ativo"
    if any(distancia(c, ch) > 0 for c in part):
        return "inativo"
    return "sem_relatorio"


def eventos(membro: dict, part: set[str], meses: list[str]) -> list[dict]:
    """Viradas de situação dentro dos meses pedidos."""
    saida = []
    for ch in meses:
        if not no_quadro(membro, ch):
            continue
        antes = ativo_em(part, somar(ch, -1))
        agora = ativo_em(part, ch)
        teve_antes = any(distancia(c, ch) > 0 for c in part)
        if antes and not agora:
            saida.append({"chave": ch, "tipo": "inativou"})
        elif ch in part and not antes and teve_antes:
            saida.append({"chave": ch, "tipo": "reativou"})
    return saida


def ultimo_mes_com_participacao(part: set[str], ate: str) -> str | None:
    anteriores = [c for c in part if distancia(c, ate) >= 0]
    return max(anteriores) if anteriores else None


# ══════════════════════════════════════════════════════════════════════════════
# ASSISTÊNCIA
# ══════════════════════════════════════════════════════════════════════════════
def resumo_mes(qtd, total) -> dict:
    q, t = _num(qtd), _num(total)
    return {"qtd": q, "total": t, "media": round(t / q, 2) if q else 0}


def resumo_reunioes(reunioes: list[dict]) -> dict:
    vals = [_num(r.get("assistencia")) for r in reunioes if r.get("assistencia") not in (None, "")]
    return resumo_mes(len(vals), sum(vals))


def media_anual(medias_mensais: list[float]) -> float:
    """S-88/S-10: média das médias mensais (só meses com reunião)."""
    v = [m for m in medias_mensais if m]
    return round(sum(v) / len(v), 2) if v else 0


def suspeitos_assistencia(meses: dict[str, dict]) -> list[str]:
    """Meses com média muito abaixo das outras (provável erro de digitação)."""
    medias = [m["media"] for m in meses.values() if m.get("media")]
    if len(medias) < 3:
        return []
    ordenadas = sorted(medias)
    mediana = ordenadas[len(ordenadas) // 2]
    return [ch for ch, m in meses.items() if m.get("media") and m["media"] < mediana * 0.5]


# ══════════════════════════════════════════════════════════════════════════════
# S-1 (mensal) · PENDÊNCIAS · S-10 (anual)
# ══════════════════════════════════════════════════════════════════════════════
def s1(ch: str, linhas: list[dict], membros: dict[str, dict], media_fim_semana=0, part=None) -> dict:
    part = part if part is not None else participacoes(linhas)
    ativos = sum(1 for mid, m in membros.items() if situacao(m, part.get(mid, set()), ch) == "ativo")
    blocos = {c: {"relatorios": 0, "horas": 0, "estudos": 0} for c in CATEGORIAS}
    for ln in validas(linhas):
        if ln["chave"] != ch or not ln["participou"]:
            continue
        b = blocos[ln["categoria"]]
        b["relatorios"] += 1
        b["estudos"] += ln["estudos"]
        if ln["categoria"] != PUB:
            b["horas"] += ln["horas"]
    return {"chave": ch, "rotulo": rotulo(ch), "ativos": ativos, "media_fim_semana": media_fim_semana,
            "publicadores": blocos[PUB], "auxiliares": blocos[AUX], "regulares": blocos[REG]}


def pendencias(ch: str, linhas: list[dict], membros: dict[str, dict], part=None) -> dict:
    """Quem ainda não entregou no mês: ativos/novos (cobrar) e inativos (separado)."""
    part = part if part is not None else participacoes(linhas)
    entregaram = {ln["membro_id"] for ln in validas(linhas) if ln["chave"] == ch}
    cobrar, inativos = [], []
    for mid, m in membros.items():
        if mid in entregaram or not no_quadro(m, ch):
            continue
        st = situacao(m, part.get(mid, set()), somar(ch, -1))
        item = {"membro_id": mid, "nome": m.get("nome_oficial") or mid, "grupo": m.get("grupo", ""),
                "regular": eh_regular(m), "ultimo": ultimo_mes_com_participacao(part.get(mid, set()), somar(ch, -1))}
        (inativos if st == "inativo" else cobrar).append(item)
    chave_ord = lambda x: normalizar(x["nome"])  # noqa: E731
    return {"cobrar": sorted(cobrar, key=chave_ord), "inativos": sorted(inativos, key=chave_ord)}


def s10(as_: int, linhas: list[dict], membros: dict[str, dict], assist: dict, cfg: dict | None = None,
        ate: str | None = None) -> dict:
    """assist = {"meio": {chave: resumo}, "fim": {chave: resumo}}"""
    cfg = cfg or {}
    meses = meses_do_as(as_)
    if ate:
        meses = [c for c in meses if distancia(c, ate) >= 0]
    part = participacoes(linhas)
    ultimo = meses[-1] if meses else None
    novos_inativos, reativados = [], []
    for mid, m in membros.items():
        for ev in eventos(m, part.get(mid, set()), meses):
            item = {"membro_id": mid, "nome": m.get("nome_oficial") or mid, "chave": ev["chave"]}
            (novos_inativos if ev["tipo"] == "inativou" else reativados).append(item)
    ativos_ids = [mid for mid, m in membros.items() if ultimo and situacao(m, part.get(mid, set()), ultimo) == "ativo"]
    cont = lambda campo: sum(1 for mid in ativos_ids if membros[mid].get(campo))  # noqa: E731
    med = lambda tipo: media_anual([(assist.get(tipo) or {}).get(c, {}).get("media", 0) for c in meses])  # noqa: E731
    por_nome = lambda x: (x["chave"], normalizar(x["nome"]))  # noqa: E731
    return {
        "ano_servico": as_, "ate": ultimo, "media_fim_semana": med("fim"), "media_meio_semana": med("meio"),
        "ativos": len(ativos_ids), "novos_inativos": sorted(novos_inativos, key=por_nome),
        "reativados": sorted(reativados, key=por_nome),
        "surdos": cont("surdo"), "cegos": cont("cego"), "presos": cont("preso"),
        "territorios_total": _num(cfg.get("territorios_total")),
        "territorios_nao_trabalhados": _num(cfg.get("territorios_nao_trabalhados")),
    }


def cartao(membro_id: str, as_: int, linhas: list[dict]) -> list[dict]:
    """As 12 linhas (set→ago) do cartão S-21 de um membro."""
    por_mes = {ln["chave"]: ln for ln in validas(linhas) if ln["membro_id"] == membro_id}
    saida = []
    for ch in meses_do_as(as_):
        ln = por_mes.get(ch)
        if not ln:
            saida.append({"chave": ch, "entregou": False})
            continue
        saida.append({"chave": ch, "entregou": True, "participou": ln["participou"], "estudos": ln["estudos"],
                      "auxiliar": ln["categoria"] == AUX,
                      "horas": ln["horas"] if ln["categoria"] != PUB else 0,
                      "observacoes": ln["observacoes"], "categoria": ln["categoria"]})
    return saida


def cartao_total(categoria: str, as_: int, linhas: list[dict]) -> list[dict]:
    """Cartão de totais (padrão JW Hub): estudos, horas e nº de relatórios na observação."""
    saida = []
    for ch in meses_do_as(as_):
        lns = [ln for ln in validas(linhas) if ln["chave"] == ch and ln["categoria"] == categoria and ln["participou"]]
        if not lns:
            saida.append({"chave": ch, "entregou": False})
            continue
        saida.append({"chave": ch, "entregou": True, "participou": True,
                      "estudos": sum(ln["estudos"] for ln in lns),
                      "horas": sum(ln["horas"] for ln in lns) if categoria != PUB else 0,
                      "auxiliar": False, "observacoes": str(len(lns)), "relatorios": len(lns)})
    return saida
