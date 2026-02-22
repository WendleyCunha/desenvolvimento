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
# 2. LÓGICA DE DADOS
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
        # ID baseado no nome. Se o RG existir, usamos para reforçar a unicidade
        sufixo = dados_pax['rg'] if dados_pax['rg'] else "reserva"
        pax_id = f"{dados_pax['nome']}_{sufixo}".lower().replace(" ", "")
        db.collection("eventos").document(id_evento).collection("passageiros").document(pax_id).set(dados_pax)

def deletar_passageiro(id_evento, nome, rg):
    db = inicializar_db()
    if db:
        sufixo = rg if rg else "reserva"
        pax_id = f"{nome}_{sufixo}".lower().replace(" ", "")
        db.collection("eventos").document(id_evento).collection("passageiros").document(pax_id).delete()

def carregar_passageiros(id_evento):
    db = inicializar_db()
    if not db: return []
    paxs = db.collection("eventos").document(id_evento).collection("passageiros").stream()
    return [p.to_dict() for p in paxs]

# =========================================================
# 3. INTERFACE VISUAL
# =========================================================

@st.dialog("Gerenciar Passageiro")
def gerenciar_pax_dialog(pax, id_evento):
    st.write(f"Gestão de Reserva:")
    st.subheader(pax['nome'])
    rg_display = pax['rg'] if pax['rg'] else "Não informado"
    st.info(f"RG: {rg_display} | Dias: {', '.join(pax['dias'])}")
    
    st.divider()
    c1, c2 = st.columns(2)
    
    if c1.button("✅ Confirmar Pagamento", use_container_width=True, type="primary"):
        pax['pago'] = True
        salvar_passageiro(id_evento, pax)
        st.success("Pago!")
        st.rerun()
        
    if c2.button("🗑️ Excluir Reserva", use_container_width=True):
        deletar_passageiro(id_evento, pax['nome'], pax['rg'])
        st.warning("Removido.")
        st.rerun()

def exibir_modulo_passagens():
    st.title("🚌 Gestão de Passagens e Eventos")
    
    eventos = carregar_eventos()
    
    # Aba 3 movida para 1 para facilitar fluxo, mas mantendo a lógica de configuração
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard Geral", "📝 Nova Reserva", "⚙️ Configurar Evento"])

    # --- ABA: CONFIGURAR EVENTO (Controle de Evento Ativo aqui) ---
    with tab3:
        if eventos:
            st.subheader("Selecionar Evento Ativo")
            id_sel = st.selectbox("Evento em administração:", list(eventos.keys()), format_func=lambda x: eventos[x]['nome'], key="seletor_evento")
            st.divider()
        else:
            id_sel = None

        st.subheader("Criar Novo Evento")
        with st.form("novo_evento"):
            n_evento = st.text_input("Nome do Evento")
            v_evento = st.number_input("Valor da Passagem (R$)", min_value=0.0, value=50.0)
            d_evento = st.multiselect("Dias do Evento", ["Sexta", "Sábado", "Domingo"])
            if st.form_submit_button("Criar Evento"):
                if n_evento and d_evento:
                    criar_evento(n_evento, d_evento, v_evento)
                    st.success("Evento criado!")
                    st.rerun()

    if not id_sel:
        st.warning("Acesse a aba 'Configurar Evento' para selecionar ou criar um evento.")
        return

    evento_atual = eventos[id_sel]
    pax_lista = carregar_passageiros(id_sel)
    df = pd.DataFrame(pax_lista)

    # --- ABA: DASHBOARD GERAL (Unificado) ---
    with tab1:
        st.subheader(f"📍 Evento: {evento_atual['nome']}")
        total_bus = 46
        qtd_total = len(df) if not df.empty else 0
        pagos_df = df[df['pago'] == True] if not df.empty else pd.DataFrame()
        pend_df = df[df['pago'] == False] if not df.empty else pd.DataFrame()
        
        v_pago = len(pagos_df) * evento_atual['valor']
        v_pend = len(pend_df) * evento_atual['valor']
        
        # Métricas Financeiras
        m1, m2, m3 = st.columns(3)
        m1.metric("Ocupação (Geral)", f"{qtd_total}/{total_bus}")
        m2.metric("Total Recebido", f"R$ {v_pago:,.2f}")
        m3.metric("Falta Receber", f"R$ {v_pend:,.2f}", delta_color="inverse")
        
        # --- NOVO: DISPONIBILIDADE POR DIA (DENTRO DO DASH) ---
        st.markdown("#### 📅 Vagas por Dia")
        dias = evento_atual['datas']
        cols_dias = st.columns(len(dias))
        
        for i, dia in enumerate(dias):
            with cols_dias[i]:
                count_dia = 0
                if not df.empty:
                    count_dia = df['dias'].apply(lambda x: dia in x).sum()
                vagas_abertas = total_bus - count_dia
                cor = "green" if vagas_abertas > 5 else "orange" if vagas_abertas > 0 else "red"
                
                st.markdown(f"""
                <div style="border: 1px solid #ddd; border-radius: 8px; padding: 10px; text-align: center; background-color: #f9f9f9;">
                    <strong style="font-size: 14px;">{dia}</strong>
                    <h2 style="color:{cor}; margin:5px 0;">{vagas_abertas}</h2>
                    <small>vagas</small>
                </div>
                """, unsafe_allow_html=True)
        
        st.divider()
        col_esq, col_dir = st.columns(2)
        
        with col_esq:
            st.markdown("### ✅ Confirmados")
            if not pagos_df.empty:
                for _, row in pagos_df.iterrows():
                    with st.container(border=True):
                        st.write(f"**{row['nome']}**")
                        st.caption(f"{', '.join(row['dias'])}")
            else: st.info("Ninguém pagou ainda.")

        with col_dir:
            st.markdown("### ⚠️ Pendentes")
            if not pend_df.empty:
                for _, row in pend_df.iterrows():
                    if st.button(f"👤 {row['nome']}", key=f"p_{row['nome']}_{row['rg']}", use_container_width=True):
                        gerenciar_pax_dialog(row, id_sel)
            else: st.success("Tudo pago!")

    # --- ABA: NOVA RESERVA ---
    with tab2:
        st.subheader("Adicionar à Lista")
        with st.form("add_pax"):
            c_nome = st.text_input("Nome Completo *")
            c_rg = st.text_input("RG (Opcional)")
            c_dias = st.multiselect("Dias", evento_atual['datas'])
            c_pago = st.toggle("Já pagou?")
            
            if st.form_submit_button("Salvar Reserva"):
                if c_nome and c_dias:
                    # Validação de lotação por dia
                    lotado = False
                    for d in c_dias:
                        if not df.empty:
                            if df['dias'].apply(lambda x: d in x).sum() >= total_bus:
                                st.error(f"Sem vagas para {d}!")
                                lotado = True
                                break
                    
                    if not lotado:
                        novo_pax = {"nome": c_nome, "rg": c_rg, "dias": c_dias, "pago": c_pago}
                        salvar_passageiro(id_sel, novo_pax)
                        st.success("Reserva salva!")
                        st.rerun()
                else:
                    st.warning("Nome e Dias são obrigatórios.")
