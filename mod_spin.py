import streamlit as st
import pandas as pd
from datetime import datetime

def exibir_tamagotchi(user_info):
    # Inicializar histórico no session_state (O ideal é salvar no Firebase depois)
    if 'historico_manutencao' not in st.session_state:
        st.session_state.historico_manutencao = []

    st.title("🧞‍♂️ SpinGenius: Gestão Profissional")

    # --- ABA DE REGISTRO DE GASTOS ---
    with st.expander("➕ Registrar Nova Manutenção / Peça"):
        with st.form("form_manutencao"):
            col1, col2 = st.columns(2)
            data_serv = col1.date_input("Data do Serviço")
            km_serv = col2.number_input("KM no momento", value=st.session_state.km_atual)
            servico = st.text_input("O que foi feito? (Ex: Troca de Óleo)")
            valor = st.number_input("Valor Pago (R$)", min_value=0.0)
            obs = st.text_area("Observações Técnicas / Peças usadas")
            foto = st.file_uploader("Anexar Nota ou Foto da Peça", type=['png', 'jpg', 'pdf'])
            
            if st.form_submit_button("Salvar no Livro de Bordo"):
                novo_registro = {
                    "Data": data_serv,
                    "KM": km_serv,
                    "Serviço": servico,
                    "Custo": valor,
                    "Obs": obs
                }
                st.session_state.historico_manutencao.append(novo_registro)
                st.success("Registro salvo com sucesso!")

    # --- EXIBIÇÃO DO HISTÓRICO ---
    st.subheader("📋 Histórico de Manutenção")
    if st.session_state.historico_manutencao:
        df_hist = pd.DataFrame(st.session_state.historico_manutencao)
        st.dataframe(df_hist, use_container_width=True)
        
        # Botão para "Imprimir" (Simulado via CSV por enquanto)
        st.download_button("📥 Exportar Relatório para PDF/Excel", 
                           df_hist.to_csv().encode('utf-8'), 
                           "historico_spin.csv", "text/csv")
    else:
        st.info("Nenhum registro encontrado. Comece trocando o óleo!")

    # --- TUTOR COM BOTÃO DE TAREFA ---
    st.divider()
    st.subheader("🧞 Dicas do Jênio")
    col_aviso, col_btn = st.columns([3, 1])
    
    with col_aviso:
        st.warning("**PENDÊNCIA:** Troca de óleo do motor (Vence com 143.000 KM)")
    with col_btn:
        if st.button("✅ Marcar como Executada"):
            st.balloons()
            st.info("Agora preencha o formulário acima para registrar o valor!")
