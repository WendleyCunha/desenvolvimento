import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json
import os

# --- FUNÇÃO DE CONEXÃO ---
def inicializar_db():
    if "db" not in st.session_state:
        try:
            if "textkey" in st.secrets:
                key_dict = json.loads(st.secrets["textkey"])
                creds = service_account.Credentials.from_service_account_info(key_dict)
                st.session_state.db = firestore.Client(credentials=creds, project=key_dict.get("project_id"))
            else:
                st.error("Secret 'textkey' não encontrada.")
                return None
        except Exception as e:
            st.error(f"Erro na conexão com Firebase: {e}")
            return None
    return st.session_state.db

# --- FUNÇÕES DE USUÁRIOS ---
def carregar_usuarios_firebase():
    db = inicializar_db()
    if not db: return {}
    try:
        users_ref = db.collection("usuarios").stream()
        return {doc.id: doc.to_dict() for doc in users_ref}
    except: return {}

def salvar_usuario(user_id, dados):
    db = inicializar_db()
    if db: db.collection("usuarios").document(user_id).set(dados, merge=True)

def deletar_usuario(user_id):
    db = inicializar_db()
    if db: db.collection("usuarios").document(user_id).delete()

# --- FUNÇÕES DE DEPARTAMENTOS ---
def carregar_departamentos():
    db = inicializar_db()
    default = ["CX", "PQI", "TI"]
    if not db: return default
    try:
        doc = db.collection("config").document("departamentos").get()
        return doc.to_dict().get("lista", default) if doc.exists else default
    except: return default

def salvar_departamentos(lista):
    db = inicializar_db()
    if db: db.collection("config").document("departamentos").set({"lista": lista})

# --- FUNÇÕES DE MOTIVOS (TIMER) ---
def carregar_motivos():
    db = inicializar_db()
    default = ["Operação Padrão", "Reunião", "Pausa", "Ajuste de Sistema"]
    if not db: return default
    try:
        doc = db.collection("config").document("motivos_timer").get()
        return doc.to_dict().get("lista", default) if doc.exists else default
    except: return default

def salvar_motivos(lista):
    db = inicializar_db()
    if db: db.collection("config").document("motivos_timer").set({"lista": lista})

# --- FUNÇÕES DE ESFORÇO (TIMER NO FIREBASE) ---
def carregar_esforco():
    db = inicializar_db()
    if not db: return []
    try:
        # Trazemos os esforços ordenados por início para facilitar o painel
        esforcos = db.collection("timer_esforco").order_by("inicio", direction=firestore.Query.DESCENDING).stream()
        return [e.to_dict() for e in esforcos]
    except Exception as e:
        print(f"Erro ao carregar esforço: {e}")
        return []

def salvar_esforco(lista_esforco):
    db = inicializar_db()
    if not db: return
    try:
        batch = db.batch()
        for atv in lista_esforco:
            # Gera um ID único para cada atividade para não sobrescrever o histórico
            id_atv = f"{atv.get('usuario')}_{atv.get('inicio')}".replace(".", "_").replace(":", "_")
            doc_ref = db.collection("timer_esforco").document(id_atv)
            batch.set(doc_ref, atv)
        batch.commit()
    except Exception as e:
        st.error(f"Erro ao salvar esforço no Firebase: {e}")

# --- FUNÇÕES DE PROJETOS PQI ---
def carregar_projetos():
    db = inicializar_db()
    if not db: return []
    try:
        projs = db.collection("projetos_pqi").stream()
        return [p.to_dict() for p in projs]
    except: return []

def salvar_projetos(lista_projetos):
    db = inicializar_db()
    if not db: return
    batch = db.batch()
    for proj in lista_projetos:
        doc_ref = db.collection("projetos_pqi").document(proj['titulo'])
        batch.set(doc_ref, proj)
    batch.commit()

# --- FUNÇÕES DO DIÁRIO DE SITUAÇÕES ---
def carregar_diario():
    db = inicializar_db()
    if not db: return []
    try:
        diario_ref = db.collection("diario_situacoes").stream()
        return [doc.to_dict() for doc in diario_ref]
    except: return []

def salvar_diario(lista_diario):
    db = inicializar_db()
    if not db: return
    batch = db.batch()
    for sit in lista_diario:
        sid = str(sit.get('id'))
        doc_ref = db.collection("diario_situacoes").document(sid)
        batch.set(doc_ref, sit)
    batch.commit()

# --- FUNÇÕES DE TICKETS ---
def salvar_tickets(lista_tickets):
    db = inicializar_db()
    if not db: return False
    try:
        batch = db.batch()
        collection_ref = db.collection("tickets_lojas")
        for ticket in lista_tickets:
            tid = str(ticket.get('ID do ticket'))
            doc_ref = collection_ref.document(tid)
            batch.set(doc_ref, ticket, merge=True)
        batch.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar tickets: {e}")
        return False

def carregar_tickets():
    db = inicializar_db()
    if not db: return []
    try:
        tickets_ref = db.collection("tickets_lojas").stream()
        return [doc.to_dict() for doc in tickets_ref]
    except: return []
