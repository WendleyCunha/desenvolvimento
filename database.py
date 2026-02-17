import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- FUNÇÃO DE CONEXÃO ---
def inicializar_db():
    if "db" not in st.session_state:
        try:
            key_dict = json.loads(st.secrets["textkey"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            project_id = key_dict.get("project_id")
            # Conexão Firestore
            st.session_state.db = firestore.Client(credentials=creds, project=project_id)
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
    if not db: return ["GERAL"]
    doc = db.collection("config").document("departamentos").get()
    return doc.to_dict().get("lista", ["GERAL"]) if doc.exists else ["GERAL"]

def salvar_departamentos(lista):
    db = inicializar_db()
    if db: db.collection("config").document("departamentos").set({"lista": lista})

# --- FUNÇÕES DE PROJETOS ---
def carregar_projetos():
    db = inicializar_db()
    if not db: return []
    try:
        projs = db.collection("projetos").stream()
        return [p.to_dict() for p in projs]
    except: return []

# --- FUNÇÕES DE TICKETS (AJUSTADAS PARA FIRESTORE) ---

def salvar_tickets(lista_tickets):
    """Grava tickets no Firestore usando o ID do ticket como nome do documento"""
    db = inicializar_db()
    if not db: return False
    try:
        # Usamos batch para gravar vários de uma vez (mais rápido)
        batch = db.batch()
        collection_ref = db.collection("tickets_lojas")
        
        for ticket in lista_tickets:
            # O Firestore precisa que o ID seja String
            tid = str(ticket.get('ID do ticket'))
            doc_ref = collection_ref.document(tid)
            batch.set(doc_ref, ticket, merge=True)
            
        batch.commit() # Salva todos
        return True
    except Exception as e:
        st.error(f"Erro ao salvar tickets no Firestore: {e}")
        return False

def carregar_tickets():
    """Carrega todos os tickets da coleção tickets_lojas"""
    db = inicializar_db()
    if not db: return []
    try:
        tickets_ref = db.collection("tickets_lojas").stream()
        lista_final = [doc.to_dict() for doc in tickets_ref]
        return lista_final
    except Exception as e:
        st.warning(f"Erro ao carregar tickets: {e}")
        return []
