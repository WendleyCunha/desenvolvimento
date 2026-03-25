import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json

# --- FUNÇÃO DE CONEXÃO ---
def inicializar_db():
    if "db" not in st.session_state:
        try:
            # Tenta carregar das secrets do Streamlit
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
    if not db: return ["CX", "PQI", "TI"]
    doc = db.collection("config").document("departamentos").get()
    return doc.to_dict().get("lista", ["CX", "PQI", "TI"]) if doc.exists else ["CX", "PQI", "TI"]

def salvar_departamentos(lista):
    db = inicializar_db()
    if db: db.collection("config").document("departamentos").set({"lista": lista})

# --- FUNÇÕES DE MOTIVOS (TIMER) ---
def carregar_motivos():
    db = inicializar_db()
    if not db: return ["Reunião", "Análise", "Documentação"]
    doc = db.collection("config").document("motivos_timer").get()
    return doc.to_dict().get("lista", ["Reunião", "Análise", "Documentação"]) if doc.exists else ["Reunião", "Análise", "Documentação"]

def salvar_motivos(lista):
    db = inicializar_db()
    if db: db.collection("config").document("motivos_timer").set({"lista": lista})

# --- FUNÇÕES DE PROJETOS PQI ---
def carregar_projetos():
    db = inicializar_db()
    if not db: return []
    try:
        # Carrega todos os projetos da coleção
        projs = db.collection("projetos_pqi").stream()
        return [p.to_dict() for p in projs]
    except: return []

def salvar_projetos(lista_projetos):
    db = inicializar_db()
    if not db: return
    batch = db.batch()
    for proj in lista_projetos:
        # Usa o título como ID de documento (ou crie um campo 'id' único)
        doc_ref = db.collection("projetos_pqi").document(proj['titulo'])
        batch.set(doc_ref, proj)
    batch.commit()

# --- FUNÇÕES DE ESFORÇO (TIMER) ---
def carregar_esforco():
    db = inicializar_db()
    if not db: return []
    try:
        esforcos = db.collection("timer_esforco").stream()
        return [e.to_dict() for e in esforcos]
    except: return []

def salvar_esforco(lista_esforco):
    db = inicializar_db()
    if not db: return
    batch = db.batch()
    for atv in lista_esforco:
        # Gera um ID baseado no timestamp e usuário para não sobrepor
        id_atv = f"{atv.get('usuario')}_{atv.get('inicio')}".replace(".", "_")
        doc_ref = db.collection("timer_esforco").document(id_atv)
        batch.set(doc_ref, atv)
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
        # Usa o ID gerado na criação do registro
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
