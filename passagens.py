import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account
import json
import pandas as pd
from datetime import datetime
import io

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
        id_evento = f"{nome.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"
        dados = {
            "nome": nome,
            "datas": datas,
            "valor": valor_passagem,
            "status": "ativo",
            "criado_em": datetime.now()
        }
        db.collection("eventos").document(id_evento).set(dados)
        return id_evento

def finalizar_evento_db(id_evento):
    db = inicializar_db()
    if db:
        db.collection("eventos").document(id_evento).update({"status": "finalizado", "finalizado_em": datetime.now()})

def carregar_eventos(incluir_finalizados=True):
    db = inicializar_db()
    if not db: return {}
    query = db.collection("eventos")
    if not incluir_finalizados:
        query = query.where("status", "==", "ativo")
    docs = query.stream()
    return {doc.id: doc.to_dict() for doc in docs}

def salvar_passageiro(id_evento, dados_pax):
    db = inicializar_db()
    if db:
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
    
    # Carregamos todos para o histórico, mas separamos os ativos
    todos_eventos = carregar_eventos()
    eventos_ativos = {k: v for k, v in todos_eventos.items() if v.get('status') == 'ativo'}
    
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard Geral", "📝 Nova Reserva", "⚙️ Configurar Evento"])

    # --- ABA: CONFIGURAR EVENTO ---
    with tab3:
        col_cfg1, col_cfg2 = st.columns(2)
        
        with col_cfg1:
            st.subheader("Gerenciar Evento Ativo")
            if eventos_ativos:
                id_sel = st.selectbox("Evento em administração:", list(eventos_ativos.keys()), format_func=lambda x: eventos_ativos[x]['nome'])
                
                # Botão de Exportar para Excel
                pax_atual = carregar_passageiros(id_sel)
                if pax_atual:
                    df_excel = pd.DataFrame(pax_atual)
                    # Organizando colunas para o Excel
                    colunas_ordem = ['nome', 'rg', 'pago', 'dias']
                    df_excel = df_excel[[c for c in colunas_ordem if c in df_excel.columns]]
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_excel.to_excel(writer, index=False, sheet_name='Passageiros')
                    
                    st.download_button(
                        label="📥 Exportar Lista (Excel)",
                        data=output.getvalue(),
                        file_name=f"passageiros_{id_sel}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                
                # Opção de Finalizar Evento
                st.divider()
                if st.button("🏁 FINALIZAR EVENTO", type="secondary", use_container_width=True, help="Move o evento para o histórico e fecha novas reservas."):
                    finalizar_evento_db(id_sel)
                    st.toast("Evento finalizado e movido para o histórico!")
                    st.rerun()
            else:
                st.info("Nenhum evento ativo.")
                id_sel = None

        with col_cfg2:
            st.subheader("Criar Novo Evento")
            with st.form("novo_evento"):
                n_evento = st.text_input("Nome do Evento")
                v_evento = st.number_input("Valor Passagem (R$)", min_value=0.0, value=50.0)
                d_evento = st.multiselect("Dias", ["Sexta", "Sábado", "Domingo"])
                if st.form_submit_button("Criar Evento"):
                    if n_evento and d_evento:
                        criar_evento(n_evento, d_evento, v_evento)
                        st.success("Evento criado!")
                        st.rerun()

    if not id_sel:
        st.warning("Acesse a aba 'Configurar Evento' para começar.")
        return

    evento_atual = todos_eventos[id_sel]
    pax_lista = carregar_passageiros(id_sel)
    df = pd.DataFrame(pax_lista)

    # --- ABA: DASHBOARD GERAL ---
    with tab1:
        st.subheader(f"📍 {evento_atual['nome']}")
        total_bus = 46
        qtd_total = len(df) if not df.empty else 0
        pagos_df = df[df['pago'] == True] if not df.empty else pd.DataFrame()
        pend_df = df[df['pago'] == False] if not df.empty else pd.DataFrame()
        
        v_pago = len(pagos_df) * evento_atual['valor']
        v_pend = len(pend_df) * evento_atual['valor']
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Ocupação (Geral)", f"{qtd_total}/{total_bus}")
        m2.metric("Total Recebido", f"R$ {v_pago:,.2f}")
        m3.metric("Pendente", f"R$ {v_pend:,.2f}", delta_color="inverse")
        
        # --- DISPONIBILIDADE POR DIA COM CORES PERSONALIZADAS ---
        st.markdown("#### 📅 Vagas por Dia")
        dias = evento_atual['datas']
        cols_dias = st.columns(len(dias))
        
        # Mapeamento de cores por dia
        cores_por_dia = {
            "Sexta": "#FFEBEE",   # Vermelho muito claro
            "Sábado": "#E3F2FD",  # Azul muito claro
            "Domingo": "#E8F5E9"  # Verde muito claro
        }
        cores_texto = {"Sexta": "#C62828", "Sábado": "#1565C0", "Domingo": "#2E7D32"}

        for i, dia in enumerate(dias):
            with cols_dias[i]:
                count_dia = df['dias'].apply(lambda x: dia in x).sum() if not df.empty else 0
                vagas_abertas = total_bus - count_dia
                bg_dia = cores_por_dia.get(dia, "#f9f9f9")
                txt_dia = cores_texto.get(dia, "#333")
                
                st.markdown(f"""
                <div style="border: 1px solid #ddd; border-radius: 8px; padding: 15px; text-align: center; background-color: {bg_dia};">
                    <strong style="color: {txt_dia}; font-size: 16px;">{dia}</strong>
                    <h2 style="color: {txt_dia}; margin:10px 0;">{vagas_abertas}</h2>
                    <small style="color: #666;">Vagas Restantes</small>
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
            else: st.info("Nenhum pagamento.")

        with col_dir:
            st.markdown("### ⚠️ Pendentes")
            if not pend_df.empty:
                for _, row in pend_df.iterrows():
                    if st.button(f"👤 {row['nome']}", key=f"p_{row['nome']}_{row['rg']}", use_container_width=True):
                        gerenciar_pax_dialog(row, id_sel)
            else: st.success("Sem pendências!")

    # --- ABA: NOVA RESERVA ---
    with tab2:
        st.subheader("Nova Reserva")
        with st.form("add_pax"):
            c_nome = st.text_input("Nome Completo *")
            c_rg = st.text_input("RG (Opcional)")
            c_dias = st.multiselect("Dias", evento_atual['datas'])
            c_pago = st.toggle("Pagamento Realizado?")
            
            if st.form_submit_button("Confirmar Reserva"):
                if c_nome and c_dias:
                    lotado = False
                    for d in c_dias:
                        if not df.empty and df['dias'].apply(lambda x: d in x).sum() >= total_bus:
                            st.error(f"O ônibus de {d} já está lotado!")
                            lotado = True
                            break
                    if not lotado:
                        novo_pax = {"nome": c_nome, "rg": c_rg, "dias": c_dias, "pago": c_pago}
                        salvar_passageiro(id_sel, novo_pax)
                        st.success("Salvo!")
                        st.rerun()
                else:
                    st.warning("Nome e Dias são obrigatórios.")
