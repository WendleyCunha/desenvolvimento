import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- CONFIGURAÇÃO INICIAL ---

def inicializar_db():
    """Inicializa a conexão com o Firestore de forma dinâmica usando st.secrets."""
    if "db" not in st.session_state:
        try:
            # 1. Carrega o dicionário da secret 'textkey'
            key_dict = json.loads(st.secrets["textkey"])
            
            # 2. Cria as credenciais
            creds = service_account.Credentials.from_service_account_info(key_dict)
            
            # 3. EXTRAÇÃO DINÂMICA: O código lê o 'project_id' de dentro do próprio JSON.
            # Isso permite usar o mesmo código para 'bancowendley' ou 'wendleydesenvolvimento'.
            project_id = key_dict.get("project_id")
            
            # 4. Inicializa o cliente Firestore sem 'hardcoded' strings
            st.session_state.db = firestore.Client(credentials=creds, project=project_id)
            
        except Exception as e:
            st.error(f"Erro crítico ao conectar no Firebase: {e}")
            return None
    return st.session_state.db

# --- GESTÃO DE USUÁRIOS ---

def carregar_usuarios_firebase():
    db = inicializar_db()
    if not db: return {}
    try:
        # Busca todos os documentos da coleção 'usuarios'
        users_ref = db.collection("usuarios").stream()
        return {doc.id: doc.to_dict() for doc in users_ref}
    except Exception as e:
        st.error(f"Erro ao carregar usuários: {e}")
        return {}

def salvar_usuario(login, dados):
    db = inicializar_db()
    if db:
        # Normaliza o login para minúsculas e remove espaços
        login_limpo = login.lower().strip()
        db.collection("usuarios").document(login_limpo).set(dados, merge=True)

def deletar_usuario(login):
    db = inicializar_db()
    if db:
        db.collection("usuarios").document(login).delete()

# --- GESTÃO DE DEPARTAMENTOS ---

def carregar_departamentos():
    db = inicializar_db()
    padrao = ["GERAL", "TI", "RH", "OPERAÇÃO"]
    if not db: return padrao
    try:
        doc = db.collection("config").document("departamentos").get()
        if doc.exists:
            return doc.to_dict().get("lista", padrao)
        return padrao
    except:
        return padrao

def salvar_departamentos(lista):
    db = inicializar_db()
    if db:
        db.collection("config").document("departamentos").set({"lista": lista})

# --- GESTÃO DE PROJETOS E PROCESSOS ---

def carregar_projetos():
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
    db = inicializar_db()
    if db:
        try:
            db.collection("config").document("projetos_pqi").set({"dados": lista_projetos})
        except Exception as e:
            st.error(f"Erro ao salvar projetos: {e}")

def reset_total_projetos():
    db = inicializar_db()
    if db:
        db.collection("config").document("projetos_pqi").set({"dados": []})
