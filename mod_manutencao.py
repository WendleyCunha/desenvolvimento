import streamlit as st
import pandas as pd
import json
import os

def exibir():
    st.header("🏗️ Gestão de Manutenção Predial")
    
    # Simulador do Core que faltava
    DB_MANT = "manutencao_dados.json"
    
    if not os.path.exists(DB_MANT):
        with open(DB_MANT, "w") as f: json.dump([], f)
        
    def carregar():
        with open(DB_MANT, "r") as f: return json.load(f)
    
    dados = carregar()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        with st.form("nova_manut"):
            item = st.selectbox("Item", ["Ar-condicionado", "Pintura", "Elétrica", "Hidráulica"])
            status = st.selectbox("Status", ["OK", "Necessita Reparo", "Em Manutenção"])
            if st.form_submit_button("Registrar"):
                dados.append({"Item": item, "Status": status, "Data": pd.Timestamp.now().strftime("%d/%m/%Y")})
                with open(DB_MANT, "w") as f: json.dump(dados, f)
                st.rerun()
                
    with col2:
        if dados:
            st.dataframe(pd.DataFrame(dados), use_container_width=True)
        else:
            st.info("Nenhum registro encontrado.")
