import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

def exibir_tamagotchi(user_info):
    st.title("🧞‍♂️ SpinGenius: Seu Tutor 1.8 Automático")
    
    # --- ESTADO DO SISTEMA ---
    if 'km_atual' not in st.session_state:
        st.session_state.km_atual = 138000
    
    # Lógica de Saúde (Calculada dinamicamente)
    # Exemplo: perde 1% a cada 500km rodados desde a última revisão
    saude_base = 100
    km_desde_revisao = st.session_state.km_atual - 138000
    saude_atual = max(0, saude_base - (km_desde_revisao // 100))

    # --- HEADER DE STATUS ---
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.metric("Saúde do Veículo", f"{saude_atual}%", delta="-2% este mês" if saude_atual < 90 else "Excelente")
        st.progress(saude_atual / 100)
    
    with col2:
        st.metric("Quilometragem", f"{st.session_state.km_atual} KM")
        if st.button("Atualizar KM"):
            st.session_state.km_atual += 100 # Simulação de atualização
            st.rerun()

    with col3:
        st.metric("Próxima Revisão", "143.000 KM")
        st.caption("Faltam: " + str(143000 - st.session_state.km_atual) + " KM")

    st.divider()

    # --- ABAS INTERATIVAS ---
    tab1, tab2, tab3 = st.tabs(["🧞 Tutor Jênio", "📅 Plano 10 Anos", "🏆 Quiz Perito"])

    with tab1:
        st.subheader("Desejos do Jênio")
        with st.chat_message("assistant", avatar="🧞"):
            st.write(f"Olá {user_info['nome']}! Notei que você está com 138k rodados. Como o câmbio foi mexido recentemente, meu primeiro conselho: **Não ignore o aquecimento.**")
            st.info("**Tarefa Imediata:** Trocar óleo 5W30 e filtro. Verificar se há vazamento na tampa de válvulas.")

        pergunta = st.text_input("Diga ao Jênio o que o carro está sentindo:")
        if pergunta:
            if "barulho" in pergunta.lower():
                st.warning("Jênio diz: Se for na frente ao passar em buracos, verifique as **Bieletas**. Se for um 'assobio' no motor, veja a correia de acessórios.")

    with tab2:
        st.subheader("Cronograma Mestre de Longevidade")
        
        # Tabela de Manutenção Gamificada
        data = {
            "Sistema": ["Motor", "Câmbio AT", "Arrefecimento", "Suspensão", "Freios"],
            "O que olhar?": ["Óleo e Filtros", "Fluido e Solavancos", "Líquido Rosa/Nível", "Bieletas e Buchas", "Pastilhas e Fluido DOT4"],
            "Frequência": ["5.000 KM", "40.000 KM", "Semanal", "Mensal", "Anual"],
            "Status": ["⚠️ URGENTE", "✅ OK", "🟡 ATENÇÃO", "✅ OK", "✅ OK"]
        }
        st.table(pd.DataFrame(data))
        
        st.info("💡 **Dica de Ouro:** Para durar 10 anos, nunca use água de torneira no radiador. Use sempre aditivo orgânico concentrado + água desmineralizada.")

    with tab3:
        st.subheader("Quiz de Sobrevivência: Spin 2013")
        q1 = st.radio("O que significa um tranco leve entre a 2ª e 3ª marcha na Spin?", 
                      ["Câmbio quebrado", "Característica da 1ª geração do câmbio GF6 (resolvível com software)", "Falta de combustível"])
        if st.button("Validar Resposta"):
            if "software" in q1:
                st.success("Exato! Você já é quase um perito. Uma atualização na TCM resolve a maioria desses casos.")
            else:
                st.error("Errado! Estude mais o manual do Jênio.")
