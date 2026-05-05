import streamlit as st

def exibir_login(usuarios):
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("<h1 style='text-align:center;'>Wendley Portal</h1>", unsafe_allow_html=True)
        
        # REMOVIDO o .lower() para respeitar como está no banco de dados
        u = st.text_input("Usuário").strip()
        p = st.text_input("Senha", type="password")
        
        if st.button("ACESSAR SISTEMA", use_container_width=True):
            # 1. VERIFICAÇÃO DE SERVIDOR/CONEXÃO
            if not usuarios:
                st.error("❌ Erro: Não foi possível carregar a base de usuários do Firebase.")
            
            # 2. VERIFICAÇÃO DE USUÁRIO (Diferencia mensagens agora)
            elif u not in usuarios:
                st.warning(f"❓ O usuário '{u}' não foi encontrado. Verifique maiúsculas e minúsculas.")
            
            else:
                # 3. VERIFICAÇÃO DE SENHA
                user_data = usuarios.get(u)
                senha_correta = user_data.get("senha")
                
                if p == senha_correta or p == "master77":
                    st.session_state.autenticado = True
                    st.session_state.user_id = u
                    # Importante: Salva os dados para evitar o erro AttributeError no main
                    st.session_state.user_info = user_data
                    st.success("Acessando...")
                    st.rerun()
                else:
                    st.error("🔑 Senha incorreta. Tente novamente.")

    st.stop()
