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

# --- GESTÃO DO MÓDULO SPIN (TAMAGOTCHI) ---

def carregar_dados_spin():
    """Busca os dados da Spin no Firestore para persistência."""
    db = inicializar_db()
    if not db: 
        return {"km_atual": 138000, "historico": []}
    try:
        doc = db.collection("config").document("spin_data").get()
        if doc.exists:
            return doc.to_dict()
        return {"km_atual": 138000, "historico": []}
    except Exception as e:
        print(f"Erro ao carregar dados da Spin: {e}")
        return {"km_atual": 138000, "historico": []}

def salvar_dados_spin(dados):
    """Salva KM e histórico da Spin no Firestore."""
    db = inicializar_db()
    if db:
        try:
            db.collection("config").document("spin_data").set(dados)
        except Exception as e:
            st.error(f"Erro ao salvar dados da Spin no banco: {e}")

# --- GESTÃO DO DIÁRIO (SITUAÇÕES DIÁRIAS) ---

def carregar_diario():
    """Carrega os registros do Diário de Situações Diárias do Firestore."""
    db = inicializar_db()
    if not db: return []
    try:
        doc = db.collection("config").document("diario_situacoes").get()
        if doc.exists:
            return doc.to_dict().get("dados", [])
        return []
    except Exception as e:
        print(f"Erro ao carregar diário: {e}")
        return []

def salvar_diario(lista_diario):
    """Salva a lista completa de situações diárias no Firestore."""
    db = inicializar_db()
    if db:
        try:
            db.collection("config").document("diario_situacoes").set({"dados": lista_diario})
        except Exception as e:
            st.error(f"Erro ao salvar diário no Firebase: {e}")

def carregar_tickets():
    db = inicializar_db()
    if not db: return []
    try:
        doc = db.collection("config").document("tickets_kingstar").get()
        return doc.to_dict().get("dados", []) if doc.exists else []
    except: return []

def salvar_tickets(lista):
    db = inicializar_db()
    if db:
        db.collection("config").document("tickets_kingstar").set({"dados": lista})

def carregar_esforco():
    """Tenta carregar os logs de esforço do Firebase, se falhar retorna lista vazia."""
    try:
        # Se você usa Firebase:
        docs = db.collection("esforco").stream()
        return [doc.to_dict() for doc in docs]
    except Exception:
        # Se você ainda não configurou a coleção no Firebase, 
        # retorna uma lista vazia para o sistema não travar.
        return []

def salvar_esforco(logs):
    """Salva a lista de logs. (Ajuste conforme sua estrutura de banco)"""
    try:
        # Exemplo simplificado para Firebase usando um ID único por log
        for log in logs:
            # Usa o início da tarefa como ID único para não duplicar
            doc_id = f"{log['usuario']}_{log['inicio']}".replace(":", "").replace("-", "")
            db.collection("esforco").document(doc_id).set(log, merge=True)
        return True
    except Exception as e:
        print(f"Erro ao salvar esforço: {e}")
        return False

