import streamlit as st
import json
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime


def inicializar_db():
    if "db" not in st.session_state:
        try:
            key_dict = json.loads(st.secrets["textkey"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            st.session_state.db = firestore.Client(
                credentials=creds, project="wendleydesenvolvimento"
            )
        except Exception as e:
            st.error(f"Erro ao conectar ao banco: {e}")
            return None
    return st.session_state.db


# ─── MEMBROS ───────────────────────────────────────────────────────────────────

def carregar_membros():
    db = inicializar_db()
    if not db:
        return {}
    return {doc.id: doc.to_dict() for doc in db.collection("membros_v2").stream()}


def atualizar_membro(nome, categoria, novo=False, extra=None):
    db = inicializar_db()
    if db:
        dados = {"categoria": categoria, "nome_oficial": nome}
        if novo:
            from utils.normalizacao import obter_mes_atual_str
            dados["mes_inicio"] = obter_mes_atual_str()
        if extra:
            dados.update({k: v for k, v in extra.items() if v is not None})
        db.collection("membros_v2").document(nome).set(dados, merge=True)


# ─── RELATÓRIOS ────────────────────────────────────────────────────────────────

def carregar_relatorios():
    db = inicializar_db()
    if not db:
        return []
    return [{"id": doc.id, **doc.to_dict()}
            for doc in db.collection("relatorios_parque_alianca").stream()]


def deletar_relatorio(relatorio_id):
    db = inicializar_db()
    if db:
        db.collection("relatorios_parque_alianca").document(relatorio_id).delete()
        st.toast("Relatório deletado!")
        st.rerun()


def salvar_baixa_manual(nome, mes, horas, estudos):
    db = inicializar_db()
    if db:
        novo_doc = {
            "nome": nome,
            "mes_referencia": mes,
            "horas": horas,
            "estudos_biblicos": estudos,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
        db.collection("relatorios_parque_alianca").add(novo_doc)
        st.success(f"Relatório de {nome} adicionado!")
        st.rerun()


# ─── ANÚNCIOS ──────────────────────────────────────────────────────────────────

def carregar_anuncios():
    db = inicializar_db()
    if not db:
        return []
    try:
        docs = (
            db.collection("anuncios")
            .order_by("data_postagem", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [{"id": doc.id, **doc.to_dict()} for doc in docs]
    except Exception as e:
        st.warning(f"Erro ao carregar anúncios: {e}")
        return []


def salvar_anuncio(dados):
    db = inicializar_db()
    if not db:
        return False
    dados["data_postagem"] = firestore.SERVER_TIMESTAMP
    db.collection("anuncios").add(dados)
    return True


def deletar_anuncio(anuncio_id):
    db = inicializar_db()
    if db:
        db.collection("anuncios").document(anuncio_id).delete()
        st.toast("✅ Anúncio deletado!")
        st.rerun()


# ─── USUÁRIOS ──────────────────────────────────────────────────────────────────

def carregar_usuarios():
    db = inicializar_db()
    if not db:
        return {}
    return {doc.id: doc.to_dict() for doc in db.collection("usuarios").stream()}


def salvar_usuario(email, dados):
    db = inicializar_db()
    if db:
        db.collection("usuarios").document(email).set(dados, merge=True)


def deletar_usuario(email):
    db = inicializar_db()
    if db:
        db.collection("usuarios").document(email).delete()


# ─── PASSAGENS ─────────────────────────────────────────────────────────────────

def carregar_eventos():
    db = inicializar_db()
    if not db:
        return {}
    docs = db.collection("eventos").where("status", "==", "ativo").stream()
    return {doc.id: doc.to_dict() for doc in docs}


def criar_evento(nome, datas, valor_passagem):
    db = inicializar_db()
    if db:
        id_evento = f"{nome.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"
        db.collection("eventos").document(id_evento).set({
            "nome": nome,
            "datas": datas,
            "valor": valor_passagem,
            "status": "ativo",
            "criado_em": datetime.now(),
            "frotas": {dia: 1 for dia in datas},
        })
        return id_evento


def adicionar_novo_onibus(id_evento, dia):
    db = inicializar_db()
    if db:
        doc_ref = db.collection("eventos").document(id_evento)
        evento = doc_ref.get().to_dict()
        frotas = evento.get("frotas", {d: 1 for d in evento["datas"]})
        frotas[dia] = frotas.get(dia, 1) + 1
        doc_ref.update({"frotas": frotas})


def salvar_passageiro(id_evento, dados_pax):
    db = inicializar_db()
    if db:
        sufixo = dados_pax["rg"] if dados_pax.get("rg") else "reserva"
        pax_id = f"{dados_pax['nome']}_{sufixo}".lower().replace(" ", "")
        if "embarcou" not in dados_pax:
            dados_pax["embarcou"] = False
        db.collection("eventos").document(id_evento).collection("passageiros").document(pax_id).set(dados_pax)
        _atualizar_cadastro_central(dados_pax)


def _atualizar_cadastro_central(dados_pax):
    db = inicializar_db()
    if db:
        pax_id = dados_pax["nome"].lower().replace(" ", "")
        db.collection("cadastro_geral").document(pax_id).set({
            "nome": dados_pax["nome"],
            "rg": dados_pax.get("rg", ""),
            "cpf": dados_pax.get("cpf", ""),
            "grupo": dados_pax.get("grupo", "Geral"),
            "ultima_atualizacao": datetime.now(),
        }, merge=True)


def buscar_pessoa_central(nome_pesquisa):
    db = inicializar_db()
    if not db or not nome_pesquisa:
        return None
    docs = db.collection("cadastro_geral").stream()
    nome_busca = nome_pesquisa.lower().strip()
    for doc in docs:
        dados = doc.to_dict()
        if nome_busca in dados.get("nome", "").lower():
            return dados
    return None


def atualizar_embarque(id_evento, pax, status):
    db = inicializar_db()
    if db:
        sufixo = pax["rg"] if pax.get("rg") else "reserva"
        pax_id = f"{pax['nome']}_{sufixo}".lower().replace(" ", "")
        db.collection("eventos").document(id_evento).collection("passageiros").document(pax_id).update({"embarcou": status})


def deletar_passageiro(id_evento, nome, rg):
    db = inicializar_db()
    if db:
        sufixo = rg if rg else "reserva"
        pax_id = f"{nome}_{sufixo}".lower().replace(" ", "")
        db.collection("eventos").document(id_evento).collection("passageiros").document(pax_id).delete()


def carregar_passageiros(id_evento):
    db = inicializar_db()
    paxs = db.collection("eventos").document(id_evento).collection("passageiros").stream()
    return [p.to_dict() for p in paxs]
