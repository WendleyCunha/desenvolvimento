import unicodedata
from datetime import datetime
from difflib import SequenceMatcher


def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texto))
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


def obter_mes_atual_str() -> str:
    meses = [
        "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
        "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
    ]
    now = datetime.now()
    return f"{meses[now.month - 1]} {now.year}"


def normalizar_nome_no_banco(nome_recebido: str, lista_membros) -> str | None:
    entrada_norm = normalizar_texto(nome_recebido)
    if not entrada_norm or len(entrada_norm) < 3:
        return None
    melhor_match, maior_score = None, 0
    for nome_oficial in lista_membros:
        oficial_norm = normalizar_texto(nome_oficial)
        score = SequenceMatcher(None, entrada_norm, oficial_norm).ratio()
        if score > maior_score:
            maior_score, melhor_match = score, nome_oficial
    return melhor_match if maior_score >= 0.85 else None
