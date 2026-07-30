"""
modulos/utils.py — Helpers compartilhados do Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
Funções e constantes de uso geral (fuso horário de Brasília, formatação de
datas/moeda, nomes de mês em PT-BR, categorias de gasto) usadas tanto pelo
`main.py` quanto pelos módulos extraídos (ex.: `mod_financeiro.py`).

Ficam aqui para evitar import circular: os módulos em `modulos/` importam
daqui, e o `main.py` também importa daqui — nenhum dos dois precisa importar
do outro só para pegar um helper de formatação.
"""

from datetime import datetime, date
from zoneinfo import ZoneInfo

# ── Fuso horário de Brasília ──────────────────────────────────────────────────
FUSO_BR = ZoneInfo("America/Sao_Paulo")

MESES_PT = [
    "Janeiro","Fevereiro","Março","Abril","Maio","Junho",
    "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro",
]

CAT_GASTOS = [
    "Tecido", "Aviamentos/Linhas", "Zíper/Botões", "Transporte",
    "Manutenção de máquina", "Marketing/Redes Sociais",
    "Embalagem", "Água/Luz/Aluguel", "Impostos/Taxas", "Outros",
]


def agora_br() -> datetime:
    """Data e hora atuais no fuso horário de Brasília (America/Sao_Paulo)."""
    return datetime.now(FUSO_BR)


def hoje_brasilia() -> date:
    """Data atual (apenas o dia) no fuso horário de Brasília."""
    return agora_br().date()


def converter_para_data(valor):
    if not valor or str(valor) in ("None", "NoneType", "", "nan"):
        return hoje_brasilia()
    try:
        if isinstance(valor, (date, datetime)):
            return valor if isinstance(valor, date) else valor.date()
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except Exception:
        return hoje_brasilia()


def formatar_data_br(data_iso):
    """Formata para o padrão brasileiro dd/mm/aaaa (somente data)."""
    try:
        if isinstance(data_iso, (date, datetime)):
            return data_iso.strftime("%d/%m/%Y")
        return datetime.strptime(str(data_iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return str(data_iso)


def formatar_data_hora_br(valor) -> str:
    """
    Formata um datetime (ou string ISO com data e hora) para o padrão
    brasileiro dd/mm/aaaa às HH:MM, sempre convertido para o horário de Brasília.
    Retorna '—' se o valor estiver vazio/ausente (ex: registros antigos sem hora salva).
    """
    if valor is None or str(valor).strip() in ("", "None", "NoneType", "nan", "NaT"):
        return "—"
    try:
        if isinstance(valor, datetime):
            dt = valor
        else:
            dt = datetime.fromisoformat(str(valor))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=FUSO_BR)
        else:
            dt = dt.astimezone(FUSO_BR)
        return dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return str(valor)


def brl(valor: float) -> str:
    if valor is None:
        valor = 0.0
    return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct_str(valor: float, total: float) -> str:
    if total <= 0:
        return "0%"
    return f"{(valor/total*100):.1f}%"
