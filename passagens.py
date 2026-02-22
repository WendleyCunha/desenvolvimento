import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json
import pandas as pd
from datetime import datetime

# --- CONEXÃO FIREBASE (Reutilizando sua lógica) ---
def inicializar_db():
    if "db" not in st.session_state:
        try:
            key_dict = json.loads(st.secrets["textkey"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            st.session_state.db = firestore.Client(credentials=creds, project="bancowendley")
        except Exception as e:
            st.error(f"Erro no Firebase: {e}")
            return None
    return st.session_state.db

# --- LÓGICA DE NEGÓCIO: EVENTOS ---

def criar_evento(nome, datas, valor_passagem):
    """Cria um novo evento (ex: Excursão Show X)"""
    db = inicializar_db()
    if db:
        id_evento = nome.lower().replace(" ", "_")
        dados = {
            "nome": nome,
            "datas": datas, # Lista: ["Sexta", "Sábado"]
            "valor": valor_passagem,
            "criado_em": datetime.now()
        }
        db.collection("eventos").document(id_evento).set(dados)
        return id_evento

def carregar_eventos():
    db = inicializar_db()
    if not db: return {}
    docs = db.collection("eventos").stream()
    return {doc.id: doc.to_dict() for doc in docs}

# --- LÓGICA DE PASSAGEIROS ---

def salvar_passageiro(id_evento, dados_pax):
    """
    dados_pax deve conter: nome, rg, dias (lista), pago (bool)
    """
    db = inicializar_db()
    if db:
        # Cria um ID único baseado no nome/rg para não duplicar no evento
        pax_id = f"{dados_pax['nome']}_{dados_pax['rg']}".lower().replace(" ", "")
        db.collection("eventos").document(id_evento).collection("passageiros").document(pax_id).set(dados_pax)

def carregar_passageiros(id_evento):
    db = inicializar_db()
    if not db: return []
    paxs = db.collection("eventos").document(id_evento).collection("passageiros").stream()
    return [p.to_dict() for p in paxs]

# --- INTERFACE VISUAL (O SHOW DE BOLA) ---

def exibir_modulo_passagens():
    st.title("🚌 Gestão de Passagens e Eventos")
    
    eventos = carregar_eventos()
    
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📝 Cadastro/Reservas", "⚙️ Novo Evento"])

    with tab3:
        st.subheader("Configurar Novo Período/Evento")
        with st.form("novo_evento"):
            n_evento = st.text_input("Nome do Evento (ex: Retiro Carnaval)")
            v_evento = st.number_input("Valor da Passagem (R$)", min_value=0.0, value=150.0)
            d_evento = st.multiselect("Dias de Saída", ["Sexta", "Sábado", "Domingo"])
            if st.form_submit_button("Criar Evento"):
                criar_evento(n_evento, d_evento, v_evento)
                st.success("Evento Criado!")
                st.rerun()

    if not eventos:
        st.warning("Nenhum evento cadastrado ainda.")
        return

    # Seleção de Evento Global
    id_sel = st.selectbox("Selecione o Evento para Administrar:", list(eventos.keys()), format_func=lambda x: eventos[x]['nome'])
    evento_atual = eventos[id_sel]
    pax_lista = carregar_passageiros(id_sel)
    df = pd.DataFrame(pax_lista)

    with tab1:
        # --- CÁLCULOS DO DASHBOARD ---
        total_lugares = 46
        qtd_pax = len(df) if not df.empty else 0
        pagos_df = df[df['pago'] == True] if not df.empty else pd.DataFrame()
        pendentes_df = df[df['pago'] == False] if not df.empty else pd.DataFrame()
        
        recebido = len(pagos_df) * evento_atual['valor']
        a_receber = len(pendentes_df) * evento_atual['valor']
        ocupacao = (qtd_pax / total_lugares)
        
        # --- MÉTRICAS VISUAIS ---
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ocupação Ônibus", f"{qtd_pax}/{total_lugares}", f"{ocupacao:.1%}")
        c2.metric("Total Recebido", f"R$ {recebido:,.2f}")
        c3.metric("Pendente", f"R$ {a_receber:,.2f}", delta_color="inverse", delta=f"- R$ {a_receber}")
        c4.progress(ocupacao, text=f"Lotação: {ocupacao:.0%}")

        # --- LISTAS DE CORES (AFUNILAMENTO) ---
        st.divider()
        col_pago, col_devendo = st.columns(2)
        
        with col_pago:
            st.markdown("### ✅ Confirmados (Pagos)")
            if not pagos_df.empty:
                for _, row in pagos_df.iterrows():
                    st.success(f"**{row['nome']}** - {row['rg']}  \n🗓️ Dias: {', '.join(row['dias'])}")
            else: st.write("Ninguém pagou ainda.")

        with col_devendo:
            st.markdown("### ⚠️ Pendentes (Reserva)")
            if not pendentes_df.empty:
                for _, row in pendentes_df.iterrows():
                    st.error(f"**{row['nome']}** - {row['rg']}  \n🔴 Falta: R$ {evento_atual['valor']}  \n🗓️ Dias: {', '.join(row['dias'])}")
            else: st.write("Nenhuma pendência!")

    with tab2:
        st.subheader("Adicionar Passageiro à Lista")
        with st.form("cadastro_pax"):
            c_nome = st.text_input("Nome Completo")
            c_rg = st.text_input("RG")
            c_dias = st.multiselect("Vai em quais dias?", evento_atual['datas'])
            c_pago = st.toggle("Já pagou?")
            
            if st.form_submit_button("Confirmar Reserva"):
                if qtd_pax >= total_lugares:
                    st.error("ÔNIBUS LOTADO!")
                elif c_nome and c_rg:
                    novo_pax = {"nome": c_nome, "rg": c_rg, "dias": c_dias, "pago": c_pago}
                    salvar_passageiro(id_sel, novo_pax)
                    st.success(f"{c_nome} adicionado!")
                    st.rerun()
                else:
                    st.warning("Preencha Nome e RG.")
