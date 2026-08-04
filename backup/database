"""
database.py — Lila Closet Atelier
Módulo de acesso ao Firestore (projeto: wendleydesenvolvimento).
Substitui completamente o SQLite original.

Coleções criadas:
  lila_clientes            → ficha de cada cliente + medidas
  lila_encomendas          → pedidos/encomendas
  lila_gastos              → lançamentos de despesas
  lila_recebimentos        → lançamentos de receita (itemizados, com data)
  lila_fechamentos_mensais → fechamento de caixa de cada mês (saldo herdado)
  lila_cronograma          → agenda / tarefas
  lila_campo_horas         → horas de serviço de campo (vida pessoal)
  lila_peso_registro       → registro mensal de peso (vida pessoal)
  lila_config              → pares chave/valor de configuração

──────────────────────────────────────────────────────────────────────────────
SOBRE O CACHE (importante para não estourar a cota gratuita do Firestore):

O plano gratuito do Firestore ("Spark") libera cerca de 50.000 LEITURAS por
dia. Como o Streamlit reexecuta o script inteiro a cada clique/digitação, sem
cache o app pode reler os MESMOS documentos dezenas de vezes por minuto e
estourar a cota (erro `ResourceExhausted`).

Por isso, as funções de LISTAGEM/LEITURA abaixo usam `@st.cache_data` com um
tempo de vida curto (poucos segundos). Toda função que ESCREVE (inserir,
atualizar, deletar, cancelar) chama `.clear()` na(s) função(ões) de leitura
correspondente(s) logo depois de gravar — assim, mesmo com o cache ativo,
você sempre vê o dado mais atual assim que salva algo. O cache só evita
releituras redundantes entre uma gravação e outra.

──────────────────────────────────────────────────────────────────────────────
[v12] Adicionado o parâmetro de configuração `alerta_entrega_dias` (default:
      "7") — quantos dias de antecedência antes da Data de Entrega o Painel
      deve disparar o alerta urgente de prioridade máxima. Ajustável na tela
      de Configurações.

[v13] Adicionadas as coleções `lila_recebimentos` (recebimentos itemizados e
      datados — substitui o antigo modelo de só acumular em
      encomenda.valor_recebido) e `lila_fechamentos_mensais` (fechamento de
      caixa mensal, com saldo herdado entre meses e conciliação bancária).
      O campo `valor_recebido` em `lila_encomendas` CONTINUA existindo e
      sendo atualizado normalmente — ele passa a ser um cache/atalho para
      exibição rápida, e a fonte de verdade financeira passa a ser a soma
      dos documentos em `lila_recebimentos`.
──────────────────────────────────────────────────────────────────────────────
"""

import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json
import datetime
import pandas as pd
from typing import Optional, Any

# Tempo de vida do cache das listagens (segundos). Curto o suficiente para
# não deixar a tela "desatualizada" por muito tempo, mas capaz de absorver
# várias reexecuções do Streamlit em sequência sem reler o Firestore.
_TTL_LISTAS = 20
_TTL_DOC    = 15
_TTL_CONFIG = 60

# ──────────────────────────────────────────────────────────────────────────────
# CONEXÃO
# ──────────────────────────────────────────────────────────────────────────────

def get_db() -> firestore.Client:
    """
    Retorna o cliente Firestore, criando a conexão uma única vez por sessão.
    Usa a secret 'textkey' já configurada no Streamlit Cloud.
    """
    if "db" not in st.session_state:
        key_dict = json.loads(st.secrets["textkey"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        st.session_state.db = firestore.Client(
            credentials=creds,
            project="wendleydesenvolvimento",
        )
    return st.session_state.db


def _col(name: str):
    """Atalho para acessar uma coleção."""
    return get_db().collection(name)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ──────────────────────────────────────────────────────────────────────────────

def _doc_to_dict(doc) -> dict:
    """Converte um DocumentSnapshot em dict, adicionando o campo 'rowid'."""
    if not doc.exists:
        return {}
    d = doc.to_dict() or {}
    d["rowid"] = doc.id
    return d


def _docs_to_df(docs) -> pd.DataFrame:
    """Converte uma lista de DocumentSnapshots em DataFrame."""
    rows = [_doc_to_dict(d) for d in docs]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────

_CONFIG_DEFAULTS = {
    "meta_faturamento":          "5000",
    "meta_pedidos_mes":          "8",
    "margem_minima_pct":         "30",
    "reserva_emergencia_meses":  "3",
    "capital_giro_pct":          "20",
    "cnpj":                      "40.717.967/0001-03",
    "telefone":                  "(11) 94600-6761",
    "endereco":                  "Embu das Artes – SP",
    "alerta_entrega_dias":       "7",
}

@st.cache_data(ttl=_TTL_CONFIG, show_spinner=False)
def cfg_get(chave: str) -> str:
    doc = _col("lila_config").document(chave).get()
    if doc.exists:
        return doc.to_dict().get("valor", _CONFIG_DEFAULTS.get(chave, ""))
    return _CONFIG_DEFAULTS.get(chave, "")


def cfg_set(chave: str, valor: str) -> None:
    _col("lila_config").document(chave).set({"valor": valor})
    cfg_get.clear()


def init_config_defaults() -> None:
    """Garante que os valores padrão existam (chamado na inicialização)."""
    for k, v in _CONFIG_DEFAULTS.items():
        ref = _col("lila_config").document(k)
        if not ref.get().exists:
            ref.set({"valor": v})
    cfg_get.clear()


# ──────────────────────────────────────────────────────────────────────────────
# CLIENTES
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def clientes_listar() -> pd.DataFrame:
    docs = _col("lila_clientes").order_by("nome").stream()
    return _docs_to_df(list(docs))


def clientes_inserir(dados: dict) -> str:
    """Insere cliente e retorna o ID gerado."""
    _, ref = _col("lila_clientes").add(dados)
    clientes_listar.clear()
    return ref.id


def clientes_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_clientes").document(rowid).update(dados)
    clientes_listar.clear()


def clientes_deletar(rowid: str) -> None:
    """
    Apaga permanentemente o cadastro (ficha + medidas) de uma cliente.
    Não apaga encomendas/pedidos já criados para essa cliente — eles
    continuam no histórico normalmente, só deixam de estar vinculados
    a uma ficha de cliente.
    """
    _col("lila_clientes").document(rowid).delete()
    clientes_listar.clear()


# ──────────────────────────────────────────────────────────────────────────────
# ENCOMENDAS
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def encomendas_listar(cancelado: Optional[bool] = None) -> pd.DataFrame:
    q = _col("lila_encomendas")
    if cancelado is not None:
        q = q.where("cancelado", "==", 1 if cancelado else 0)
    docs = q.stream()
    df = _docs_to_df(list(docs))
    if df.empty:
        return df
    # Ordena por criação (campo _criado_em), mais recente primeiro
    if "_criado_em" in df.columns:
        df = df.sort_values("_criado_em", ascending=False)
    return df


def encomendas_inserir(dados: dict) -> str:
    dados.setdefault("cancelado", 0)
    dados.setdefault("etapa", 1)
    dados["_criado_em"] = _now_iso()
    _, ref = _col("lila_encomendas").add(dados)
    encomendas_listar.clear()
    return ref.id


def encomendas_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_encomendas").document(rowid).update(dados)
    encomendas_listar.clear()
    encomendas_buscar.clear()


@st.cache_data(ttl=_TTL_DOC, show_spinner=False)
def encomendas_buscar(rowid: str) -> dict:
    return _doc_to_dict(_col("lila_encomendas").document(rowid).get())


def encomendas_cancelar(rowid: str) -> None:
    """
    Cancela o pedido e zera os campos de andamento.

    NOTA FINANCEIRA (v13): esta função zera `valor_recebido` no cadastro do
    pedido, mas NÃO apaga os lançamentos já feitos em `lila_recebimentos`
    vinculados a este pedido. Isso é intencional — dinheiro que já entrou de
    fato no caixa é um fato financeiro que já aconteceu (não deve sumir do
    histórico/relatório só porque o pedido foi cancelado depois). Se o valor
    recebido precisar ser devolvido à cliente, registre isso como uma SAÍDA
    normal em `lila_gastos` (ex: categoria "Estorno/Reembolso"), para que o
    caixa continue batendo com o extrato bancário.
    """
    _col("lila_encomendas").document(rowid).update({
        "cancelado": 1,
        "etapa": 1,
        "sinal": 0,
        "valor_recebido": 0,
        "data_tecido": None,
        "data_confeccao": None,
        "data_prova": None,
        "data_entrega": None,
    })
    # Remove tarefas vinculadas
    for doc in _col("lila_cronograma").where("encomenda_id", "==", rowid).stream():
        doc.reference.delete()
    # Remove gastos não pagos vinculados
    for doc in _col("lila_gastos").where("encomenda_id", "==", rowid).where("pago", "==", 0).stream():
        doc.reference.delete()
    encomendas_listar.clear()
    encomendas_buscar.clear()
    cronograma_listar.clear()
    gastos_listar.clear()


def encomendas_deletar_completo(rowid: str) -> None:
    """
    NOTA FINANCEIRA (v13): assim como em `encomendas_cancelar`, os
    lançamentos de `lila_recebimentos` vinculados a este pedido NÃO são
    apagados — dinheiro recebido no passado continua valendo para fins de
    caixa e conciliação, mesmo que o cadastro do pedido seja excluído.
    """
    _col("lila_encomendas").document(rowid).delete()
    for doc in _col("lila_cronograma").where("encomenda_id", "==", rowid).stream():
        doc.reference.delete()
    for doc in _col("lila_gastos").where("encomenda_id", "==", rowid).stream():
        doc.reference.delete()
    encomendas_listar.clear()
    encomendas_buscar.clear()
    cronograma_listar.clear()
    gastos_listar.clear()


# ──────────────────────────────────────────────────────────────────────────────
# GASTOS
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def gastos_listar() -> pd.DataFrame:
    docs = _col("lila_gastos").stream()
    df = _docs_to_df(list(docs))
    if not df.empty and "data" in df.columns:
        df = df.sort_values("data", ascending=False)
    return df


def gastos_inserir(dados: dict) -> str:
    dados.setdefault("conciliado", 0)
    dados["_criado_em"] = _now_iso()
    _, ref = _col("lila_gastos").add(dados)
    gastos_listar.clear()
    return ref.id


def gastos_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_gastos").document(rowid).update(dados)
    gastos_listar.clear()


def gastos_deletar(rowid: str) -> None:
    _col("lila_gastos").document(rowid).delete()
    gastos_listar.clear()


def gastos_deletar_pagos() -> None:
    for doc in _col("lila_gastos").where("pago", "==", 1).stream():
        doc.reference.delete()
    gastos_listar.clear()


# ──────────────────────────────────────────────────────────────────────────────
# RECEBIMENTOS  [novo — v13]
# ──────────────────────────────────────────────────────────────────────────────
# Cada entrada de dinheiro (ligada a um pedido ou avulsa) vira um documento
# individual e datado aqui — em vez de só somar um campo acumulado. É isso
# que permite reconciliação bancária e fechamento de caixa mensal corretos.
# Segue exatamente o mesmo padrão de `gastos_*` acima.

@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def recebimentos_listar() -> pd.DataFrame:
    docs = _col("lila_recebimentos").stream()
    df = _docs_to_df(list(docs))
    if not df.empty and "data" in df.columns:
        df = df.sort_values("data", ascending=False)
    return df


def recebimentos_inserir(dados: dict) -> str:
    """
    dados esperado:
      encomenda_id (str | None), descricao (str), valor (float),
      categoria (str), data (str isoformat), forma_pagamento (str),
      conciliado (0/1), criado_em (str isoformat, para exibição).
    """
    dados.setdefault("conciliado", 0)
    dados["_criado_em"] = _now_iso()
    _, ref = _col("lila_recebimentos").add(dados)
    recebimentos_listar.clear()
    return ref.id


def recebimentos_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_recebimentos").document(rowid).update(dados)
    recebimentos_listar.clear()


def recebimentos_deletar(rowid: str) -> None:
    _col("lila_recebimentos").document(rowid).delete()
    recebimentos_listar.clear()


# ──────────────────────────────────────────────────────────────────────────────
# FECHAMENTOS MENSAIS  [novo — v13]
# ──────────────────────────────────────────────────────────────────────────────
# Um documento por mês (chave de negócio: campo "mes", formato "YYYY-MM").
# É isso que carrega o saldo final de um mês para virar o saldo inicial do
# mês seguinte, e que trava (concilia) os lançamentos de um período fechado.
# O upsert por campo (em vez de por rowid) segue o mesmo padrão já usado em
# `peso_upsert` acima.

@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def fechamentos_listar() -> pd.DataFrame:
    docs = _col("lila_fechamentos_mensais").stream()
    df = _docs_to_df(list(docs))
    if not df.empty and "mes" in df.columns:
        df = df.sort_values("mes", ascending=False)
    return df


def fechamento_buscar(mes_str: str) -> Optional[dict]:
    """
    Retorna o dict do fechamento do mês ('YYYY-MM') ou None se não existir.
    Não usa cache próprio — reaproveita o cache de fechamentos_listar(),
    igual ao padrão de `cronograma_com_cliente` reaproveitando `encomendas_buscar`.
    """
    df = fechamentos_listar()
    if df.empty or "mes" not in df.columns:
        return None
    linha = df[df["mes"] == mes_str]
    if linha.empty:
        return None
    return linha.iloc[0].to_dict()


def fechamento_salvar(mes_str: str, dados: dict) -> None:
    """
    Cria ou atualiza (upsert) o fechamento do mês, buscando pelo campo "mes"
    (mesmo padrão de `peso_upsert`, que busca por "mes_ano").

    dados esperado (nem todos os campos precisam vir em toda chamada, já
    que é upsert — ex: `fechamento_reabrir` só manda o campo "fechado"):
      mes (str "YYYY-MM"), saldo_inicial (float), receitas_mes (float),
      despesas_mes (float), saldo_final (float),
      saldo_extrato_informado (float | None), diferenca (float),
      fechado (0/1), observacoes (str), data_fechamento (str isoformat | None).
    """
    dados = dict(dados)
    dados["_atualizado_em"] = _now_iso()
    docs = list(_col("lila_fechamentos_mensais").where("mes", "==", mes_str).stream())
    if docs:
        docs[0].reference.update(dados)
    else:
        dados.setdefault("mes", mes_str)
        _col("lila_fechamentos_mensais").add(dados)
    fechamentos_listar.clear()


def fechamento_reabrir(mes_str: str) -> None:
    """Destrava um mês fechado por engano (fechado=0). Uso raro — corrigir erro."""
    fechamento_salvar(mes_str, {"fechado": 0})


# ──────────────────────────────────────────────────────────────────────────────
# CRONOGRAMA
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def cronograma_listar(
    tipo_agenda: Optional[str] = None,
    concluida: Optional[bool] = None,
    ate_data: Optional[str] = None,
) -> pd.DataFrame:
    q = _col("lila_cronograma")
    if tipo_agenda:
        q = q.where("tipo_agenda", "==", tipo_agenda)
    if concluida is not None:
        q = q.where("concluida", "==", 1 if concluida else 0)
    docs = list(q.stream())
    df = _docs_to_df(docs)
    if df.empty:
        return df
    if ate_data and "data" in df.columns:
        df = df[df["data"] <= ate_data]
    if "data" in df.columns:
        df = df.sort_values("data", ascending=True)
    return df


def cronograma_inserir(dados: dict) -> str:
    dados.setdefault("concluida", 0)
    dados["_criado_em"] = _now_iso()
    _, ref = _col("lila_cronograma").add(dados)
    cronograma_listar.clear()
    return ref.id


def cronograma_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_cronograma").document(rowid).update(dados)
    cronograma_listar.clear()


def cronograma_deletar(rowid: str) -> None:
    _col("lila_cronograma").document(rowid).delete()
    cronograma_listar.clear()


def cronograma_com_cliente(
    tipo_agenda: str = "Trabalho",
    concluida: bool = False,
    ate_data: Optional[str] = None,
) -> pd.DataFrame:
    """
    Retorna cronograma com o nome do cliente da encomenda vinculada.
    Faz o 'join' manualmente (Firestore não tem JOIN), reaproveitando o
    cache de `encomendas_buscar` — na prática, isso significa que essa
    função só bate no Firestore de verdade quando o cache expira ou é
    invalidado por uma gravação, mesmo sendo chamada várias vezes por tela
    (Hoje, aba Trabalho, Calendário).
    """
    df = cronograma_listar(tipo_agenda=tipo_agenda, concluida=concluida, ate_data=ate_data)
    if df.empty:
        return df

    cache_enc: dict[str, str] = {}
    nomes = []
    for _, row in df.iterrows():
        enc_id = row.get("encomenda_id")
        if enc_id and enc_id not in cache_enc:
            enc = encomendas_buscar(str(enc_id))
            cache_enc[str(enc_id)] = enc.get("cliente", "")
        nomes.append(cache_enc.get(str(enc_id), "") if enc_id else "")
    df["nome_cliente"] = nomes
    return df


# ──────────────────────────────────────────────────────────────────────────────
# CAMPO HORAS
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def campo_horas_listar(mes_ano: Optional[str] = None) -> pd.DataFrame:
    q = _col("lila_campo_horas")
    if mes_ano:
        q = q.where("mes_ano", "==", mes_ano)
    docs = list(q.stream())
    df = _docs_to_df(docs)
    if not df.empty and "data" in df.columns:
        df = df.sort_values("data", ascending=True)
    return df


@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def campo_horas_historico() -> pd.DataFrame:
    docs = _col("lila_campo_horas").stream()
    df = _docs_to_df(list(docs))
    if df.empty:
        return df
    return df.groupby("mes_ano")["horas"].sum().reset_index().rename(
        columns={"horas": "total"}
    ).sort_values("mes_ano", ascending=False)


def campo_horas_inserir(dados: dict) -> str:
    _, ref = _col("lila_campo_horas").add(dados)
    campo_horas_listar.clear()
    campo_horas_historico.clear()
    return ref.id


def campo_horas_deletar(rowid: str) -> None:
    _col("lila_campo_horas").document(rowid).delete()
    campo_horas_listar.clear()
    campo_horas_historico.clear()


# ──────────────────────────────────────────────────────────────────────────────
# PESO REGISTRO
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=_TTL_LISTAS, show_spinner=False)
def peso_listar() -> pd.DataFrame:
    docs = _col("lila_peso_registro").stream()
    df = _docs_to_df(list(docs))
    if not df.empty and "mes_ano" in df.columns:
        df = df.sort_values("mes_ano", ascending=True)
    return df


def peso_upsert(mes_ano: str, data_str: str, peso_kg: float) -> None:
    """Insere ou atualiza o registro do mês."""
    docs = list(_col("lila_peso_registro").where("mes_ano", "==", mes_ano).stream())
    if docs:
        docs[0].reference.update({"data": data_str, "peso_kg": peso_kg})
    else:
        _col("lila_peso_registro").add({
            "mes_ano": mes_ano,
            "data": data_str,
            "peso_kg": peso_kg,
        })
    peso_listar.clear()


# ──────────────────────────────────────────────────────────────────────────────
# INICIALIZAÇÃO
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _garantir_config_inicial_uma_vez() -> bool:
    """
    Executa `init_config_defaults()` (leituras no Firestore) apenas UMA
    ÚNICA VEZ durante todo o tempo de vida do app no servidor — não a cada
    rerun do Streamlit. `@st.cache_resource` compartilha esse resultado entre
    TODAS as sessões/usuários do app, então essas leituras só acontecem de
    novo se o app reiniciar (deploy novo, sleep/wake do Streamlit Cloud etc).
    """
    init_config_defaults()
    return True


def init_db() -> None:
    """
    Chamada a cada execução do script (é assim que o Streamlit funciona),
    mas o trabalho pesado (`init_config_defaults`) só roda de fato uma vez
    graças ao cache acima — evita gastar cota do Firestore em todo clique.
    """
    _garantir_config_inicial_uma_vez()
