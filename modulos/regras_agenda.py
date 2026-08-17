"""
modulos/regras_agenda.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
Regras de negócio da Agenda / Cronograma de produção. Funções PURAS
(recebem um DataFrame de encomendas e devolvem True/False/mensagem ou
conjuntos de datas) — não fazem nenhuma chamada ao Firestore nem ao
Streamlit, então podem ser reutilizadas tanto pelos formulários de criação
quanto pelos de edição de pedido, sem duplicar regra nenhuma.

Regras implementadas:

  1) DATA DA CONFECÇÃO — dois clientes no mesmo dia NÃO são mais bloqueados
     por senha. A partir da segunda encomenda no mesmo dia, a função de
     validação retorna um status de CONFIRMAÇÃO (sim/não), informando
     quantas encomendas já existem naquele dia, para a tela perguntar ao
     usuário se ele deseja mesmo assim marcar mais uma encomenda ali.
  2) DATA DA CONFECÇÃO — continua BLOQUEADA (sem opção de confirmar) se o
     dia já tiver MAIS de `LIMITE_PROVAS_PARA_CONFECCAO` provas marcadas
     (padrão 3). As provas em si continuam SEM limite nenhum — o cliente
     pode marcar 4, 5, 6 provas no mesmo dia à vontade; o que fica
     bloqueado é usar esse dia para Confecção.
  3) ENTREGAS PRÓXIMAS — lista de pedidos cuja Data de Entrega caia dentro
     da janela de antecedência configurada (dias), para o alerta urgente.

[v2 — correção de bug] `pedidos_com_entrega_proxima` filtrava por
`etapa < 7`, resquício da régua ANTIGA de 7 etapas (de antes do v16 do
mod_encomendas.py). Na régua atual (1 Confecção, 2 Prova, 3 Entrega,
4 Concluído), esse filtro nunca excluía nada — pedidos já CONCLUÍDOS
continuavam aparecendo para sempre no alerta de entrega urgente e na
lista de atrasados da Agenda. Corrigido para `etapa < 4`, que exclui
corretamente os pedidos já concluídos.

[v3 — Consertos não disputam exclusividade de dia] A partir do
mod_prospect.py, um "Conserto" nasce direto na coleção de encomendas
(para integrar com financeiro/agenda), mas por definição de negócio ele
NÃO participa das regras de exclusividade da Data da Confecção nem da
contagem de provas — ele pode ser agendado em qualquer dia, mesmo que já
exista um pedido normal (ou outro conserto) nesse dia. Como a regra vale
nos dois sentidos (o conserto não é bloqueado por essas regras E também
não deve bloquear pedidos normais por causa dele), as funções de ocupação
de dia/provas abaixo agora ignoram qualquer registro cuja peça comece com
o prefixo "[Conserto]" (mesmo prefixo usado por `mod_prospect.py` ao criar
o registro). A regra de ENTREGA PRÓXIMA não precisa desse filtro porque
consertos nunca têm `data_entrega` preenchida.

[v4 — fim do bloqueio por senha na Data da Confecção] Antes, marcar uma
segunda encomenda no mesmo dia de confecção exigia senha (fluxo que ficava
na tela do formulário, fora deste arquivo). Essa trava foi removida. No
lugar, `validar_data_confeccao` agora devolve um status em texto ("ok",
"confirmar" ou "bloqueado"):
  - "confirmar" → o dia já tem N encomenda(s) de confecção; a tela deve
    exibir a quantidade e perguntar sim/não se o usuário quer seguir mesmo
    assim. Se ele confirmar, a tela chama a função de novo passando
    `confirmar_duplicidade=True` para pular a pergunta e liberar o dia.
  - "bloqueado" → continua sendo definitivo, sem opção de confirmar
    (limite de provas excedido).
  - "ok" → segue sem nenhuma pergunta.
A regra de LIMITE DE PROVAS (regra 2) não mudou: continua um bloqueio
definitivo, sem confirmação possível.

Em todas as funções, "pedidos ativos" = não cancelados. Ao editar um
pedido já existente, use `excluir_id` para não contar o próprio pedido
como conflito consigo mesmo.
"""

from __future__ import annotations

import datetime
from datetime import date
from typing import Optional

import pandas as pd

# Quantidade de provas que um dia AINDA PODE TER sem bloquear a Confecção.
# Ex.: com o valor 3, um dia com 1, 2 ou 3 provas continua liberado para
# Confecção; a partir da 4ª prova no mesmo dia, a Confecção fica bloqueada
# nesse dia. As provas em si continuam sem nenhum limite de quantidade.
LIMITE_PROVAS_PARA_CONFECCAO = 3

# Número da última etapa da régua atual (4 = Concluído). Usado para excluir
# pedidos já concluídos dos alertas de entrega/atraso. Mantido como
# constante nomeada (em vez de um "7" ou "4" solto no meio do código) para
# que, se a régua mudar de novo no futuro, só precise ser ajustado aqui.
ETAPA_CONCLUIDO = 4

# Prefixo usado por `mod_prospect.py` para marcar um registro como Conserto
# (em vez de um pedido normal de peça). Mantido como constante nomeada para
# não haver duas strings soltas ("[Conserto]") que possam divergir.
PREFIXO_CONSERTO = "[Conserto]"


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


def _sem_consertos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove os registros de Conserto (peça iniciando com `PREFIXO_CONSERTO`)
    de um DataFrame já filtrado por `_pedidos_ativos`. Usada apenas pelas
    regras de exclusividade de Data da Confecção e contagem de provas —
    consertos não entram nem saem dessas contas, em nenhuma direção.
    """
    if df.empty or "peca" not in df.columns:
        return df
    return df[~df["peca"].astype(str).str.startswith(PREFIXO_CONSERTO)]


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 1 — DATA DA CONFECÇÃO (exclusividade → agora vira confirmação sim/não)
# ──────────────────────────────────────────────────────────────────────────────

def clientes_em_confeccao_no_dia(df_enc: pd.DataFrame, data_alvo: date, excluir_id: Optional[str] = None) -> list:
    """
    Lista os nomes de todos os clientes que já têm 'Data da Confecção' ==
    data_alvo, entre os pedidos ativos (excluindo Consertos, ver
    `_sem_consertos`). Pode ter mais de um nome, já que a exclusividade de
    dia deixou de ser um bloqueio e virou uma confirmação sim/não — a
    tela usa esta lista para montar a mensagem de confirmação.
    """
    df = _sem_consertos(_pedidos_ativos(df_enc, excluir_id))
    if df.empty or "data_confeccao" not in df.columns:
        return []
    lista = []
    for _, row in df.iterrows():
        if _to_date(row.get("data_confeccao")) == data_alvo:
            lista.append(str(row.get("cliente") or "—"))
    return lista


def contar_confeccoes_no_dia(df_enc: pd.DataFrame, data_alvo: date, excluir_id: Optional[str] = None) -> int:
    """Quantidade de encomendas (não-Conserto) já marcadas para confecção em `data_alvo`."""
    return len(clientes_em_confeccao_no_dia(df_enc, data_alvo, excluir_id))


def confeccao_ocupada_em(df_enc: pd.DataFrame, data_alvo: date, excluir_id: Optional[str] = None) -> Optional[str]:
    """
    [DEPRECATED — mantida só por compatibilidade com chamadas antigas]
    Retorna o nome do PRIMEIRO cliente que já tem 'Data da Confecção' ==
    data_alvo, ou None se o dia estiver livre. Como a exclusividade de dia
    deixou de ser um bloqueio (virou confirmação sim/não), prefira usar
    `clientes_em_confeccao_no_dia` ou `contar_confeccoes_no_dia`, que
    trazem todos os nomes/quantidade, e não só o primeiro.
    """
    lista = clientes_em_confeccao_no_dia(df_enc, data_alvo, excluir_id)
    return lista[0] if lista else None


def dias_confeccao_ocupados(df_enc: pd.DataFrame, excluir_id: Optional[str] = None) -> set:
    """
    Conjunto de todas as datas (date) já comprometidas com Data da
    Confecção. Registros de Conserto não entram neste conjunto. Útil para
    a tela destacar visualmente no calendário os dias já usados — não
    significa mais que esses dias estão bloqueados, já que agora é
    possível confirmar mais uma encomenda no mesmo dia.
    """
    df = _sem_consertos(_pedidos_ativos(df_enc, excluir_id))
    if df.empty or "data_confeccao" not in df.columns:
        return set()
    datas = {_to_date(v) for v in df["data_confeccao"]}
    datas.discard(None)
    return datas


def validar_data_confeccao(
    df_enc: pd.DataFrame,
    data_alvo: date,
    excluir_id: Optional[str] = None,
    confirmar_duplicidade: bool = False,
):
    """
    Valida se `data_alvo` pode ser usada como Data da Confecção.

    Retorna uma tupla (status, mensagem):
      - status == "ok"        → segue sem nenhuma pergunta, dia liberado.
      - status == "confirmar" → o dia já tem N encomenda(s) de confecção
        marcada(s). A tela deve mostrar `mensagem` (que já traz a
        quantidade) e perguntar sim/não ao usuário. Se ele responder
        "sim", chame esta função de novo com `confirmar_duplicidade=True`
        para pular esta checagem e liberar o dia.
      - status == "bloqueado" → bloqueio definitivo (mais de
        `LIMITE_PROVAS_PARA_CONFECCAO` provas no dia). Não existe opção de
        confirmar; é preciso escolher outra data.

    Esta validação NUNCA é chamada para Consertos (eles são criados
    direto por `mod_prospect.py`, sem passar por aqui) — mas mesmo que
    fosse, os Consertos já cadastrados não contam como ocupação nem como
    prova (ver `_sem_consertos`).
    """
    if data_alvo is None:
        return "ok", ""

    # Regra 2 — limite de provas: continua sendo bloqueio definitivo,
    # sem opção de confirmação, e é checada mesmo se o usuário já
    # confirmou a duplicidade de encomendas.
    qtd_provas = contar_provas_no_dia(df_enc, data_alvo, excluir_id)
    if qtd_provas > LIMITE_PROVAS_PARA_CONFECCAO:
        return "bloqueado", (
            f"❌ O dia {data_alvo.strftime('%d/%m/%Y')} já tem {qtd_provas} provas marcadas "
            f"(mais de {LIMITE_PROVAS_PARA_CONFECCAO}) e por isso não pode receber confecção. "
            f"Escolha outro dia para a Confecção."
        )

    # Regra 1 — duas (ou mais) encomendas no mesmo dia: agora é só uma
    # confirmação sim/não, não bloqueio nem senha.
    if not confirmar_duplicidade:
        qtd_confeccoes = contar_confeccoes_no_dia(df_enc, data_alvo, excluir_id)
        if qtd_confeccoes > 0:
            plural = "encomenda" if qtd_confeccoes == 1 else "encomendas"
            return "confirmar", (
                f"⚠️ O dia {data_alvo.strftime('%d/%m/%Y')} já tem {qtd_confeccoes} {plural} "
                f"marcada(s) para confecção. Deseja marcar mais uma encomenda para esse mesmo dia?"
            )

    return "ok", ""


# ──────────────────────────────────────────────────────────────────────────────
# CONTAGEM DE PROVAS (sem limite — usada só para decidir o bloqueio de Confecção)
# ──────────────────────────────────────────────────────────────────────────────

def contar_provas_no_dia(df_enc: pd.DataFrame, data_alvo: date, excluir_id: Optional[str] = None) -> int:
    """
    Conta quantas provas (1ª ou 2ª) já estão marcadas para `data_alvo`,
    entre os pedidos ativos (não cancelados, excluindo Consertos). Não há
    limite de provas por dia — o cliente pode marcar quantas quiser. Esta
    contagem serve apenas para decidir se o dia bloqueia (ou não) a Data
    da Confecção, em `validar_data_confeccao`.
    """
    df = _sem_consertos(_pedidos_ativos(df_enc, excluir_id))
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
                             limite: int = LIMITE_PROVAS_PARA_CONFECCAO) -> set:
    """
    Conjunto de datas com MAIS de `limite` provas marcadas (padrão: mais de
    3) — dias que, por causa da quantidade de provas, ficam bloqueados para
    receber Confecção. Um dia com exatamente `limite` provas NÃO entra
    neste conjunto (continua liberado para confecção). Registros de
    Conserto não entram nesta contagem.
    """
    df = _sem_consertos(_pedidos_ativos(df_enc, excluir_id))
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
    return {d for d, qtd in contagem.items() if qtd > limite}


# ──────────────────────────────────────────────────────────────────────────────
# REGRA 4 — ALERTA DE ENTREGA PRÓXIMA
# ──────────────────────────────────────────────────────────────────────────────

def pedidos_com_entrega_proxima(df_enc: pd.DataFrame, hoje: date, dias_antecedencia: int) -> pd.DataFrame:
    """
    Retorna os pedidos ativos (não cancelados, não concluídos — etapa <
    ETAPA_CONCLUIDO) cuja Data de Entrega esteja dentro da janela de
    `dias_antecedencia` a partir de hoje (isso inclui entregas de hoje e
    entregas já atrasadas, sem limite de quão atrasadas). Ordenado pela
    entrega mais próxima/mais atrasada primeiro.

    Consertos nunca aparecem aqui na prática, pois não têm `data_entrega`
    preenchida — por isso não precisam de filtro explícito, diferente das
    funções de Confecção/Provas acima.

    Uma coluna auxiliar "_dias_restantes" é adicionada ao resultado
    (negativa = atrasado, 0 = hoje, positiva = dias que faltam).
    """
    if df_enc is None or df_enc.empty:
        return pd.DataFrame()

    df = df_enc.copy()
    if "cancelado" in df.columns:
        df = df[df["cancelado"].astype(int) == 0]
    if "etapa" in df.columns:
        df = df[df["etapa"].astype(int) < ETAPA_CONCLUIDO]
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
