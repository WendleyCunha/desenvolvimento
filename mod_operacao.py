import streamlit as st
import pandas as pd
import os

def exibir()
    st.header(📊 Painel Operacional)
    if os.path.exists(lancamentos_operacao.csv)
        df = pd.read_csv(lancamentos_operacao.csv)
        st.line_chart(df.groupby('Data')['Quantidade Tratada'].sum())
    else
        st.warning(Base 'lancamentos_operacao.csv' não encontrada.)
