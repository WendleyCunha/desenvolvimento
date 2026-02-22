import streamlit as st
import pandas as pd
from datetime import datetime

# --- LÓGICA DE BANCO (Mantendo sua estrutura Firestore) ---
# Importe aqui suas funções do database original se necessário
import passagens as db 

@st.dialog("Gerenciar Reserva")
def gerenciar_reserva_dialog(pax, id_evento):
    st.write(f"O que deseja fazer com a reserva de **{pax['nome']}**?")
    st.info(f"RG: {pax['rg']} | Dias: {', '.join(pax['dias'])}")
    
    c1, c2 = st.columns(2)
    
    if c1.button("✅ Confirmar Pagamento", use_container_width=True):
        pax['pago'] = True
        db.salvar_passageiro(id_evento, pax)
        st.success("Pagamento confirmado!")
        st.rerun()
        
    if c2.button("🗑️ Remover Desistência", use_container_width=True, type="secondary"):
        # Aqui você deve criar a função deletar_passageiro no seu passagens.py original
        # Ou usar uma função que sobrescreva/remova do array
        st.warning("Removendo passageiro...")
        # db.deletar_passageiro(id_evento, pax) # Implementar conforme sua estrutura
        st.rerun()

def exibir_modulo_passagens():
    st.title("🚌 Gestão de Passagens Premium")
    
    eventos = db.carregar_eventos()
    if not eventos:
        st.info("Crie um evento na aba 'Novo Evento' para começar.")
        return

    # Seleção de Evento
    id_sel = st.selectbox("Evento Ativo:", list(eventos.keys()), format_func=lambda x: eventos[x]['nome'])
    evento_atual = eventos[id_sel]
    pax_lista = db.carregar_passageiros(id_sel)
    df = pd.DataFrame(pax_lista)

    tab1, tab2, tab3 = st.tabs(["📊 Dashboard Geral", "📅 Visão por Dia", "📝 Reservas"])

    with tab1:
        # --- MÉTRICAS GERAIS ---
        total_vagas = 46
        qtd_pax = len(df) if not df.empty else 0
        pago_sim = len(df[df['pago'] == True]) if not df.empty else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ocupação Total", f"{qtd_pax}/{total_vagas}")
        c2.metric("Total Recebido", f"R$ {pago_sim * evento_atual['valor']:,.2f}")
        c3.metric("A Receber", f"R$ {(qtd_pax - pago_sim) * evento_atual['valor']:,.2f}")
        
        st.divider()
        col_p, col_r = st.columns(2)
        
        with col_p:
            st.subheader("✅ Pagos")
            if not df.empty:
                pagos = df[df['pago'] == True]
                for _, p in pagos.iterrows():
                    st.success(f"**{p['nome']}** ({', '.join(p['dias'])})")
        
        with col_r:
            st.subheader("⚠️ Pendentes (Clique para Agir)")
            if not df.empty:
                pendentes = df[df['pago'] == False]
                for _, p in pendentes.iterrows():
                    # O segredo do 'Premium': O card é um botão invisível ou tem um botão de ação
                    if st.button(f"🔔 {p['nome']} - {p['rg']}", key=f"btn_{p['rg']}", use_container_width=True):
                        gerenciar_reserva_dialog(p, id_sel)

    with tab2:
        st.subheader("Situação por Dia do Evento")
        dias_evento = evento_atual['datas'] # Ex: ["Sexta", "Sábado", "Domingo"]
        
        cols_dias = st.columns(len(dias_evento))
        
        for i, dia in enumerate(dias_evento):
            with cols_dias[i]:
                # Filtra quem vai nesse dia específico
                pax_dia = df[df['dias'].apply(lambda x: dia in x)] if not df.empty else pd.DataFrame()
                qtd_dia = len(pax_dia)
                vagas_restantes = total_vagas - qtd_dia
                
                # Visual do Card por Dia
                st.markdown(f"""
                <div style="background-color:#f0f2f6; padding:15px; border-radius:10px; border-top: 5px solid #002366;">
                    <h4 style="margin:0; text-align:center;">{dia}</h4>
                    <h2 style="text-align:center; color:#002366; margin:10px 0;">{vagas_restantes}</h2>
                    <p style="text-align:center; font-size:12px;">VAGAS DISPONÍVEIS</p>
                </div>
                """, unsafe_allow_html=True)
                
                if qtd_dia > 40: st.warning(f"⚠️ {dia} quase lotado!")
                elif qtd_dia >= 46: st.error(f"❌ {dia} LOTADO")

    with tab3:
        # (Mantém o formulário de cadastro que já tínhamos)
        st.write("Use esta aba para adicionar novos interessados.")
