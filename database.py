"""
database.py — Lila Closet Atelier
Módulo de acesso ao Firestore (projeto: wendleydesenvolvimento).
Substitui completamente o SQLite original.

Coleções criadas:
  lila_clientes        → ficha de cada cliente + medidas
  lila_encomendas      → pedidos/encomendas
  lila_gastos          → lançamentos de despesas
  lila_cronograma      → agenda / tarefas
  lila_campo_horas     → horas de serviço de campo (vida pessoal)
  lila_peso_registro   → registro mensal de peso (vida pessoal)
  lila_config          → pares chave/valor de configuração
"""

import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json
import datetime
import pandas as pd
from typing import Optional, Any

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
}

def cfg_get(chave: str) -> str:
    doc = _col("lila_config").document(chave).get()
    if doc.exists:
        return doc.to_dict().get("valor", _CONFIG_DEFAULTS.get(chave, ""))
    return _CONFIG_DEFAULTS.get(chave, "")


def cfg_set(chave: str, valor: str) -> None:
    _col("lila_config").document(chave).set({"valor": valor})


def init_config_defaults() -> None:
    """Garante que os valores padrão existam (chamado na inicialização)."""
    for k, v in _CONFIG_DEFAULTS.items():
        ref = _col("lila_config").document(k)
        if not ref.get().exists:
            ref.set({"valor": v})


# ──────────────────────────────────────────────────────────────────────────────
# CLIENTES
# ──────────────────────────────────────────────────────────────────────────────

def clientes_listar() -> pd.DataFrame:
    docs = _col("lila_clientes").order_by("nome").stream()
    return _docs_to_df(list(docs))


def clientes_inserir(dados: dict) -> str:
    """Insere cliente e retorna o ID gerado."""
    _, ref = _col("lila_clientes").add(dados)
    return ref.id


def clientes_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_clientes").document(rowid).update(dados)


def clientes_deletar(rowid: str) -> None:
    """
    Apaga permanentemente o cadastro (ficha + medidas) de uma cliente.
    Não apaga encomendas/pedidos já criados para essa cliente — eles
    continuam no histórico normalmente, só deixam de estar vinculados
    a uma ficha de cliente.
    """
    _col("lila_clientes").document(rowid).delete()


# ──────────────────────────────────────────────────────────────────────────────
# ENCOMENDAS
# ──────────────────────────────────────────────────────────────────────────────

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
    return ref.id


def encomendas_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_encomendas").document(rowid).update(dados)


def encomendas_buscar(rowid: str) -> dict:
    return _doc_to_dict(_col("lila_encomendas").document(rowid).get())


def encomendas_cancelar(rowid: str) -> None:
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


def encomendas_deletar_completo(rowid: str) -> None:
    _col("lila_encomendas").document(rowid).delete()
    for doc in _col("lila_cronograma").where("encomenda_id", "==", rowid).stream():
        doc.reference.delete()
    for doc in _col("lila_gastos").where("encomenda_id", "==", rowid).stream():
        doc.reference.delete()


# ──────────────────────────────────────────────────────────────────────────────
# GASTOS
# ──────────────────────────────────────────────────────────────────────────────

def gastos_listar() -> pd.DataFrame:
    docs = _col("lila_gastos").stream()
    df = _docs_to_df(list(docs))
    if not df.empty and "data" in df.columns:
        df = df.sort_values("data", ascending=False)
    return df


def gastos_inserir(dados: dict) -> str:
    dados["_criado_em"] = _now_iso()
    _, ref = _col("lila_gastos").add(dados)
    return ref.id


def gastos_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_gastos").document(rowid).update(dados)


def gastos_deletar(rowid: str) -> None:
    _col("lila_gastos").document(rowid).delete()


def gastos_deletar_pagos() -> None:
    for doc in _col("lila_gastos").where("pago", "==", 1).stream():
        doc.reference.delete()


# ──────────────────────────────────────────────────────────────────────────────
# CRONOGRAMA
# ──────────────────────────────────────────────────────────────────────────────

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
    return ref.id


def cronograma_atualizar(rowid: str, dados: dict) -> None:
    _col("lila_cronograma").document(rowid).update(dados)


def cronograma_deletar(rowid: str) -> None:
    _col("lila_cronograma").document(rowid).delete()


def cronograma_com_cliente(
    tipo_agenda: str = "Trabalho",
    concluida: bool = False,
    ate_data: Optional[str] = None,
) -> pd.DataFrame:
    """
    Retorna cronograma com o nome do cliente da encomenda vinculada.
    Faz o 'join' manualmente (Firestore não tem JOIN).
    """
    df = cronograma_listar(tipo_agenda=tipo_agenda, concluida=concluida, ate_data=ate_data)
    if df.empty:
        return df

    # Cache de encomendas para evitar leituras repetidas
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

def campo_horas_listar(mes_ano: Optional[str] = None) -> pd.DataFrame:
    q = _col("lila_campo_horas")
    if mes_ano:
        q = q.where("mes_ano", "==", mes_ano)
    docs = list(q.stream())
    df = _docs_to_df(docs)
    if not df.empty and "data" in df.columns:
        df = df.sort_values("data", ascending=True)
    return df


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
    return ref.id


def campo_horas_deletar(rowid: str) -> None:
    _col("lila_campo_horas").document(rowid).delete()


# ──────────────────────────────────────────────────────────────────────────────
# PESO REGISTRO
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# INICIALIZAÇÃO
# ──────────────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Chamada uma vez ao iniciar o app.
    Garante que os valores de configuração padrão existam no Firestore.
    """
    init_config_defaults()
