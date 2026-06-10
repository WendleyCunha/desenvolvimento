import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json
import datetime

# --- 1. CONFIGURAÇÃO DE CONEXÃO (REUTILIZANDO SEU JSON) ---

def inicializar_db():
    """Inicializa a conexão com o Firestore utilizando a secret 'textkey'."""
    if "db" not in st.session_state:
        try:
            # Reutiliza o JSON que você já tem configurado nas Secrets do Streamlit
            key_dict = json.loads(st.secrets["textkey"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            # Mantém o seu projeto original, mas vamos gravar em coleções novas
            st.session_state.db = firestore.Client(credentials=creds, project="wendleydesenvolvimento")
        except Exception as e:
            st.error(f"Erro ao conectar no Firebase: {e}")
            return None
    return st.session_state.db

# --- 2. GESTÃO EXCLUSIVA: RELATÓRIOS PARQUE ALIANÇA ---

def salvar_relatorio_alianca(dados):
    """
    Grava os dados do formulário em uma coleção SEPARADA chamada 'relatorios_parque_alianca'.
    Cada envio gera um documento único com ID automático.
    """
    db = inicializar_db()
    if db:
        try:
            # Adicionamos um timestamp para controle cronológico e organização
            dados["data_processamento"] = datetime.datetime.now()
            
            # .add() cria um novo documento para cada resposta do formulário
            db.collection("relatorios_parque_alianca").add(dados)
            return True
        except Exception as e:
            st.error(f"Erro ao salvar dados: {e}")
            return False
    return False

# --- 3. INTERFACE DO FORMULÁRIO (PARA COLETA EM TEMPO REAL) ---

def main():
    st.set_page_config(page_title="Relatórios Parque Aliança", layout="centered")
    st.title("📋 Formulário de Relatórios - Parque Aliança")
    st.write("Preencha os dados abaixo. As informações serão processadas em tempo real.")

    # Criamos o formulário
    with st.form("form_alianca", clear_on_submit=True):
        st.subheader("Informações do Evento/Ocorrência")
        
        # Campos que servirão para preencher seu PDF futuramente
        nome_solicitante = st.text_input("Nome do Solicitante")
        setor = st.selectbox("Setor Responsável", ["Manutenção", "Segurança", "Limpeza", "Administrativo"])
        descricao = st.text_area("Descrição Detalhada da Situação")
        urgencia = st.select_slider("Grau de Urgência", options=["Baixa", "Média", "Alta", "Crítica"])
        
        btn_enviar = st.form_submit_button("Enviar Relatório")

        if btn_enviar:
            if nome_solicitante and descricao:
                # Dicionário com os dados organizados
                payload = {
                    "solicitante": nome_solicitante,
                    "setor": setor,
                    "descricao": descricao,
                    "urgencia": urgencia,
                    "status_pdf": "Pendente" # Controle para a próxima etapa (automação do PDF)
                }
                
                if salvar_relatorio_alianca(payload):
                    st.success("✅ Dados enviados com sucesso! O sistema está processando as informações.")
            else:
                st.warning("⚠️ Por favor, preencha os campos obrigatórios (Nome e Descrição).")

if __name__ == "__main__":
    main()
