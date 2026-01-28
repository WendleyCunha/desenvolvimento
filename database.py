import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- CONFIGURAÇÃO INICIAL ---

def inicializar_db():
    """Inicializa a conexão com o Firestore utilizando as secrets do Streamlit."""
    if "db" not in st.session_state:
        try:
            key_dict = json.loads(st.secrets["textkey"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            st.session_state.db = firestore.Client(credentials=creds, project="bancowendley")
        except Exception as e:
            st.error(f"Erro no Firebase: {e}")
            return None
    return st.session_state.db

# --- GESTÃO DE USUÁRIOS ---

def carregar_usuarios_firebase():
    db = inicializar_db()
    if not db: return {}
    try:
        users_ref = db.collection("usuarios").stream()
        return {doc.id: doc.to_dict() for doc in users_ref}
    except: 
        return {}

def salvar_usuario(login, dados):
    db = inicializar_db()
    if db:
        # lower().strip() garante que o ID do documento seja padronizado
        db.collection("usuarios").document(login.lower().strip()).set(dados, merge=True)

def deletar_usuario(login):
    db = inicializar_db()
    if db:
        db.collection("usuarios").document(login).delete()

# --- GESTÃO DE DEPARTAMENTOS ---

def carregar_departamentos():
    db = inicializar_db()
    if not db: return ["GERAL", "TI", "RH", "OPERAÇÃO"]
    try:
        doc = db.collection("config").document("departamentos").get()
        if doc.exists:
            return doc.to_dict().get("lista", ["GERAL", "TI", "RH", "OPERAÇÃO"])
        return ["GERAL", "TI", "RH", "OPERAÇÃO"]
    except:
        return ["GERAL", "TI", "RH", "OPERAÇÃO"]

def salvar_departamentos(lista):
    db = inicializar_db()
    if db:
        db.collection("config").document("departamentos").set({"lista": lista})

# --- GESTÃO DE PROJETOS E PROCESSOS (PQI / LEMBRETES) ---

def carregar_projetos():
    """Carrega a lista de projetos do Firestore para o módulo de processos."""
    db = inicializar_db()
    if not db: return []
    try:
        doc = db.collection("config").document("projetos_pqi").get()
        if doc.exists:
            return doc.to_dict().get("dados", [])
        return []
    except Exception as e:
        print(f"Erro ao carregar projetos: {e}")
        return []

def salvar_projetos(lista_projetos):
    """Salva a lista completa de projetos no Firestore para persistência."""
    db = inicializar_db()
    if db:
        try:
            db.collection("config").document("projetos_pqi").set({"dados": lista_projetos})
        except Exception as e:
            st.error(f"Erro crítico ao salvar no banco: {e}")

def reset_total_projetos():
    """Limpa todos os projetos do banco de dados (Cuidado!)."""
    db = inicializar_db()
    if db:
        db.collection("config").document("projetos_pqi").set({"dados": []})
