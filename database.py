import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json

# Função de Conexão (O Motor)
def inicializar_db():
    if "db" not in st.session_state:
        try:
            key_dict = json.loads(st.secrets["textkey"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            project_id = key_dict.get("project_id")
            st.session_state.db = firestore.Client(credentials=creds, project=project_id)
        except Exception as e:
            st.error(f"Erro na conexão com Firebase: {e}")
            return None
    return st.session_state.db

# Funções de Usuários
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

# Funções de Departamentos
def carregar_departamentos():
    db = inicializar_db()
    if not db: return ["GERAL"]
    doc = db.collection("config").document("departamentos").get()
    return doc.to_dict().get("lista", ["GERAL"]) if doc.exists else ["GERAL"]

def salvar_departamentos(lista):
    db = inicializar_db()
    if db: db.collection("config").document("departamentos").set({"lista": lista})

# Funções de Projetos/Lembretes (Para a Home)
def carregar_projetos():
    db = inicializar_db()
    if not db: return []
    try:
        projs = db.collection("projetos").stream()
        return [p.to_dict() for p in projs]
    except: return []
