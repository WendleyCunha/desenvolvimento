import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json
import pandas as pd
from datetime import datetime

# =========================================================
# 1. CONEXÃO E CONFIGURAÇÃO (FIRESTORE)
# =========================================================

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

# =========================================================
# 2. LÓGICA DE DADOS (EVENTOS E PASSAGEIROS)
# =========================================================

def criar_evento(nome, datas, valor_passagem):
    db = inicializar_db()
    if db:
        id_evento = nome.lower().replace(" ", "_")
        dados = {
            "nome": nome,
            "datas": datas,
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

def salvar_passageiro(id_evento, dados_pax):
    db = inicializar_db()
    if db:
        # ID único baseado no nome e RG para evitar duplicatas
        pax_id = f"{dados_pax['nome']}_{dados_pax['rg']}".lower().replace(" ", "")
        db.collection("eventos").document(id_evento).collection("passageiros").document(pax_id).set(dados_pax)

def deletar_passageiro(id_evento, nome, rg):
    db = inicializar_db()
    if db:
        pax_id = f"{nome}_{rg}".lower().replace(" ", "")
        db.collection("eventos").document(id_evento).collection("passageiros").document(pax_id).delete()

def carregar_passageiros(id_evento):
    db = inicializar_db()
    if not db: return []
    paxs = db.collection("eventos").document(id_evento).collection("passageiros").stream()
    return [p.to_dict() for p in paxs]

# =========================================================
# 3. INTERFACE VISUAL PREMIUM
# =========================================================

@st.dialog("Gerenciar Passageiro")
def gerenciar_pax_dialog(pax, id_evento):
    """Pop-up para confirmar pagamento ou registrar desistência."""
    st.write(f"O que deseja fazer com a reserva de:")
    st.subheader(pax['nome'])
    st.info(f"RG: {pax['rg']} | Dias: {', '.join(pax['dias'])}")
    
    st.divider()
    c1, c2 = st.columns(2)
    
    if c1.button("✅ Confirmar Pagamento", use_container_width=True, type="primary"):
        pax['pago'] = True
        salvar_passageiro(id_evento, pax)
        st.success("Pagamento registrado!")
        st.rerun()
        
    if c2.button("🗑️ Registrar Desistência", use_container_width=True):
        deletar_passageiro(id_evento, pax['nome'], pax['rg'])
        st.warning("Reserva excluída.")
        st.rerun()

def exibir_modulo_passagens():
    st.title("🚌 Gestão de Passagens e Eventos")
    
    eventos = carregar_eventos()
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Dashboard Geral", 
        "📅 Vagas por Dia", 
        "📝 Nova Reserva", 
        "⚙️ Configurar Evento"
    ])

    # --- ABA: CONFIGURAR EVENTO ---
    with tab4:
        st.subheader("Criar Novo Evento")
        with st.form("novo_evento"):
            n_evento = st.text_input("Nome do Evento")
            v_evento = st.number_input("Valor da Passagem (R$)", min_value=0.0, value=50.0)
            d_evento = st.multiselect("Dias disponíveis", ["Sexta", "Sábado", "Domingo"])
            if st.form_submit_button("Salvar Evento"):
                if n_evento and d_evento:
                    criar_evento(n_evento, d_evento, v_evento)
                    st.success("Evento criado com sucesso!")
                    st.rerun()

    if not eventos:
        st.warning("Crie um evento na aba de configurações para começar.")
        return

    # Seletor Global de Evento
    id_sel = st.selectbox("Selecione o Evento:", list(eventos.keys()), format_func=lambda x: eventos[x]['nome'])
    evento_atual = eventos[id_sel]
    pax_lista = carregar_passageiros(id_sel)
    df = pd.DataFrame(pax_lista)

    # --- ABA: DASHBOARD GERAL ---
    with tab1:
        total_bus = 46
        qtd_total = len(df) if not df.empty else 0
        pagos_df = df[df['pago'] == True] if not df.empty else pd.DataFrame()
        pend_df = df[df['pago'] == False] if not df.empty else pd.DataFrame()
        
        v_pago = len(pagos_df) * evento_atual['valor']
        v_pend = len(pend_df) * evento_atual['valor']
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ocupação Total", f"{qtd_total}/{total_bus}", f"{total_bus - qtd_total} livres")
        c2.metric("Total Recebido", f"R$ {v_pago:,.2f}")
        c3.metric("Pendente", f"R$ {v_pend:,.2f}", delta=f"-R$ {v_pend}", delta_color="inverse")
        
        st.divider()
        col_esq, col_dir = st.columns(2)
        
        with col_esq:
            st.markdown("### ✅ Confirmados (Pagos)")
            if not pagos_df.empty:
                for _, row in pagos_df.iterrows():
                    with st.container(border=True):
                        st.write(f"**{row['nome']}**")
                        st.caption(f"RG: {row['rg']} | {', '.join(row['dias'])}")
            else: st.write("Ninguém pagou ainda.")

        with col_dir:
            st.markdown("### ⚠️ Pendentes (Clique para Gerenciar)")
            if not pend_df.empty:
                for _, row in pend_df.iterrows():
                    # Card Interativo que abre o Pop-up
                    if st.button(f"👤 {row['nome']} (Falta R$ {evento_atual['valor']})", key=f"p_{row['rg']}", use_container_width=True):
                        gerenciar_pax_dialog(row, id_sel)
            else: st.write("Tudo em
