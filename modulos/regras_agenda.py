"""
modulos/regras_agenda.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
Regras de negócio da Agenda / Cronograma de produção. Funções PURAS
(recebem um DataFrame de encomendas e devolvem True/False/mensagem ou
conjuntos de datas) — não fazem nenhuma chamada ao Firestore nem ao
Streamlit, então podem ser reutilizadas tanto pelos formulários de criação
quanto pelos de edição de pedido, sem duplicar regra nenhuma.

Regras implementadas:

  1) DATA DA CONFECÇÃO — nunca dois clientes na mesma data.
  2) DATA DA CONFECÇÃO — bloqueada se o dia já tiver o limite de provas
     (padrão 3) marcadas, mesmo que ainda não haja confecção nesse dia.
  3) DATA DA PROVA — no máximo `LIMITE_PROVAS_POR_DIA` provas (1ª ou 2ª)
     no mesmo dia, somando todos os pedidos ativos.
  4) ENTREGAS PRÓXIMAS — lista de pedidos cuja Data de Entrega caia dentro
     da janela de antecedência configurada (dias), para o alerta urgente.

Em todas as funções, "pedidos ativos" = não cancelados. Ao editar um
pedido já existente, use `excluir_id` para não contar o próprio pedido
como conflito consigo mesmo.
"""

from __future__ import annotations

import datetime
from datetime import date
from typing import Optional

import pandas as pd

LIMITE_PROVAS_POR_DIA = 3


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ──────────────────────────────────────────────────────────────────────────────

def _to_date(valor) -> Optional[date]:
    """Converte string ISO (ou date/datetime) em `date`. Retorna None se vazio/inválido."""
    if valor is None:
        return None
    if isinstance(valor, datetime.datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _pedidos_ativos(df_enc: pd.DataFrame, excluir_id: Optional[str] = None) -> pd.DataFrame:
    """Filtra apenas pedidos não cancelados, e remove o próprio pedido em edição."""
    if df_enc is None or df_enc.empty:
        return pd.DataFrame()
    df = df_enc.copy()
    if "cancelado" in df.columns:
        df = df[df["cancelado"].astype(int) == 0]
    if excluir_id and "rowid" in df.columns:
        df = df[df["rowid"].astype(str) != str(excluir_id)]
    return df


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 1 e 2 — DATA DA CONFECÇÃO
# ──────────────────────────────────────────────────────────────────────────────

def confeccao_ocupada_em(df_enc: pd.DataFrame, data_alvo: date, excluir_id: Optional[str] = None) -> Optional[str]:
    """
    Retorna o nome do cliente que já tem 'Data da Confecção' == data_alvo,
    ou None se o dia estiver livre para confecção.
    """
    df = _pedidos_ativos(df_enc, excluir_id)
    if df.empty or "data_confeccao" not in df.columns:
        return None
    for _, row in df.iterrows():
        if _to_date(row.get("data_confeccao")) == data_alvo:
            return str(row.get("cliente") or "—")
    return None


def dias_confeccao_ocupados(df_enc: pd.DataFrame, excluir_id: Optional[str] = None) -> set:
    """Conjunto de todas as datas (date) já comprometidas com Data da Confecção."""
    df = _pedidos_ativos(df_enc, excluir_id)
    if df.empty or "data_confeccao" not in df.columns:
        return set()
    datas = {_to_date(v) for v in df["data_confeccao"]}
    datas.discard(None)
    return datas


def validar_data_confeccao(df_enc: pd.DataFrame, data_alvo: date, excluir_id: Optional[str] = None):
    """
    Valida se `data_alvo` pode ser usada como Data da Confecção.
    Retorna (True, "") se OK, ou (False, "motivo") se bloqueado.

    Regras:
      - Nunca dois clientes com confecção no mesmo dia.
      - Não pode ser um dia que já esteja "lotado" de provas (padrão: 3).
    """
    if data_alvo is None:
        return True, ""

    cliente_ocupando = confeccao_ocupada_em(df_enc, data_alvo, excluir_id)
    if cliente_ocupando:
        return False, (
            f"❌ O dia {data_alvo.strftime('%d/%m/%Y')} já está reservado para a confecção "
            f"de **{cliente_ocupando}**. Escolha outra data — nunca pode haver dois clientes "
            f"em confecção no mesmo dia."
        )

    qtd_provas = contar_provas_no_dia(df_enc, data_alvo, excluir_id)
    if qtd_provas >= LIMITE_PROVAS_POR_DIA:
        return False, (
            f"❌ O dia {data_alvo.strftime('%d/%m/%Y')} já tem {qtd_provas} prova(s) marcada(s) "
            f"(limite de {LIMITE_PROVAS_POR_DIA} por dia) e por isso não pode receber confecção."
        )
    return True, ""


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 3 — DATA DA PROVA
# ──────────────────────────────────────────────────────────────────────────────

def contar_provas_no_dia(df_enc: pd.DataFrame, data_alvo: date, excluir_id: Optional[str] = None) -> int:
    """
    Conta quantas provas (1ª ou 2ª) já estão marcadas para `data_alvo`,
    entre os pedidos ativos (não cancelados).
    """
    df = _pedidos_ativos(df_enc, excluir_id)
    if df.empty or data_alvo is None:
        return 0
    total = 0
    for _, row in df.iterrows():
        if _to_date(row.get("data_prova")) == data_alvo:
            total += 1
        tem_p2 = bool(int(row.get("tem_prova2", 0) or 0)) or bool(str(row.get("data_prova2") or "").strip())
        if tem_p2 and _to_date(row.get("data_prova2")) == data_alvo:
            total += 1
    return total


def dias_com_provas_lotadas(df_enc: pd.DataFrame, excluir_id: Optional[str] = None,
                             limite: int = LIMITE_PROVAS_POR_DIA) -> set:
    """Conjunto de datas que já atingiram o limite de provas (padrão 3)."""
    df = _pedidos_ativos(df_enc, excluir_id)
    if df.empty:
        return set()
    contagem: dict = {}
    for _, row in df.iterrows():
        d1 = _to_date(row.get("data_prova"))
        if d1:
            contagem[d1] = contagem.get(d1, 0) + 1
        tem_p2 = bool(int(row.get("tem_prova2", 0) or 0)) or bool(str(row.get("data_prova2") or "").strip())
        if tem_p2:
            d2 = _to_date(row.get("data_prova2"))
            if d2:
                contagem[d2] = contagem.get(d2, 0) + 1
    return {d for d, qtd in contagem.items() if qtd >= limite}


def validar_data_prova(df_enc: pd.DataFrame, data_alvo: date, excluir_id: Optional[str] = None,
                        provas_locais: int = 0):
    """
    Valida se `data_alvo` pode receber mais uma prova.
    `provas_locais` conta provas que já estão sendo agendadas no MESMO
    formulário (ex.: 1ª e 2ª prova caindo no mesmo dia), para não deixar
    passar um conflito que só existiria "dentro do próprio pedido novo".
    """
    if data_alvo is None:
        return True, ""
    qtd = contar_provas_no_dia(df_enc, data_alvo, excluir_id) + provas_locais
    if qtd >= LIMITE_PROVAS_POR_DIA:
        return False, (
            f"❌ O dia {data_alvo.strftime('%d/%m/%Y')} já atingiu o limite de "
            f"{LIMITE_PROVAS_POR_DIA} provas marcadas. Escolha outra data para a prova."
        )
    return True, ""


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 4 — ALERTA DE ENTREGA PRÓXIMA
# ──────────────────────────────────────────────────────────────────────────────

def pedidos_com_entrega_proxima(df_enc: pd.DataFrame, hoje: date, dias_antecedencia: int) -> pd.DataFrame:
    """
    Retorna os pedidos ativos (não cancelados, não concluídos — etapa < 7)
    cuja Data de Entrega esteja dentro da janela de `dias_antecedencia` a
    partir de hoje (isso inclui entregas de hoje e entregas já atrasadas).
    Ordenado pela entrega mais próxima/mais atrasada primeiro.

    Uma coluna auxiliar "_dias_restantes" é adicionada ao resultado
    (negativa = atrasado, 0 = hoje, positiva = dias que faltam).
    """
    if df_enc is None or df_enc.empty:
        return pd.DataFrame()

    df = df_enc.copy()
    if "cancelado" in df.columns:
        df = df[df["cancelado"].astype(int) == 0]
    if "etapa" in df.columns:
        df = df[df["etapa"].astype(int) < 7]
    if df.empty or "data_entrega" not in df.columns:
        return pd.DataFrame()

    def _dias_ate(v):
        d = _to_date(v)
        if d is None:
            return None
        return (d - hoje).days

    df = df.assign(_dias_restantes=df["data_entrega"].apply(_dias_ate))
    df = df[df["_dias_restantes"].notna()]
    if df.empty:
        return df
    df = df[df["_dias_restantes"] <= dias_antecedencia]
    if df.empty:
        return df
    return df.sort_values("_dias_restantes", ascending=True)
