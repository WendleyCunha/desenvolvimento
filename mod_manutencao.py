import streamlit as st
import pandas as pd

# Função para combinar as bases sem duplicar pedidos idênticos
def consolidar_bases(base_antiga, base_nova):
    # Concatena as duas
    combinada = pd.concat([base_antiga, base_nova], ignore_index=True)
    
    # Ponto importante: Se o Pedido for o MESMO, mantemos a primeira ocorrência (a origem)
    # Isso evita que o mesmo pedido conte duas vezes se ele aparecer em dois uploads
    combinada = combinada.drop_duplicates(subset=['Pedido'], keep='first')
    
    return combinada

def identificar_re_trabalho(df):
    # Ordenamos por cliente e data de emissão
    df = df.sort_values(['ID_Cliente', 'Dt_Emissao'])
    
    # Criamos a flag: se o cliente já apareceu antes com OUTRO número de pedido
    df['Ordem_Pedido_Cliente'] = df.groupby('ID_Cliente').cumcount() + 1
    
    # Todo pedido com ordem > 1 é um potencial Re-trabalho (PV Y vindo de um PV X)
    df['Status_Apuracao'] = df['Ordem_Pedido_Cliente'].apply(
        lambda x: 'RE-TRABALHO DETECTADO' if x > 1 else 'PEDIDO ORIGINAL'
    )
    
    return df
