import streamlit as st

st.title("🚀 Teste de Hospedagem: OK!")
st.write("Se você está vendo isso, o Streamlit Cloud está funcionando.")

# Botão para testar interatividade
if st.button("Clique aqui"):
    st.balloons()
    st.success("O servidor está vivo e respondendo!")
