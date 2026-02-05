import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from database import inicializar_db
from datetime import datetime
import unicodedata

# --- UTILITÁRIO DE TRATAMENTO (Essencial para sua planilha) ---
def normalizar_cabecalhos(df):
    # Transforma "Criação do ticket - Hora" em "HORA", etc.
    mapeamento = {
        'CRIACAO DO TICKET - DATA': 'DATA',
        'CRIACAO DO TICKET - DIA DA SEMANA': 'DIA_SEMANA',
        'CRIACAO DO TICKET - HORA': 'HORA',
        'TICKETS': 'TICKETS'
    }
    df.columns = [unicodedata.normalize('NFKD', str(c)).encode('ASCII', 'ignore').decode('ASCII').upper().strip() for c in df.columns]
    df = df.rename(columns=mapeamento)
    return df

# --- COMPONENTE DE PICOS (Os 3 Gráficos) ---
def renderizar_analise_picos(df_picos):
    if df_picos.empty:
        st.info("💡 Suba o relatório de picos na aba CONFIG.")
        return

    df = normalizar_cabecalhos(df_picos)
    df['TICKETS'] = pd.to_numeric(df['TICKETS'], errors='coerce').fillna(0)
    
    st.subheader("🔥 Inteligência de Canais e Picos")

    # --- GRÁFICO 1: PICO HORA A HORA ---
    st.markdown("### 1. Volume por Faixa Horária")
    df_hora = df.groupby('HORA')['TICKETS'].sum().reset_index()
    # Identificar o pico para destacar
    pico_hora_val = df_hora['TICKETS'].max()
    df_hora['COR'] = ['#ef4444' if v == pico_hora_val else '#002366' for v in df_hora['TICKETS']]
    
    fig_hora = px.bar(df_hora, x='HORA', y='TICKETS', 
                     title="Total de Entradas por Hora (Destaque em Vermelho no Pico)",
                     color='COR', color_discrete_map="identity")
    fig_hora.update_layout(xaxis_type='category')
    st.plotly_chart(fig_hora, use_container_width=True)

    # --- GRÁFICO 2: VOLUME POR DIA DA SEMANA ---
    st.markdown("### 2. Volume por Dia da Semana")
    ordem_dias = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
    df_dia = df.groupby('DIA_SEMANA')['TICKETS'].sum().reindex(ordem_dias).reset_index().dropna()
    
    pico_dia_val = df_dia['TICKETS'].max()
    df_dia['COR'] = ['#ef4444' if v == pico_dia_val else '#3b82f6' for v in df_dia['TICKETS']]

    fig_dia = px.bar(df_dia, x='DIA_SEMANA', y='TICKETS', 
                    title="Volume Total por Dia (Destaque no Dia mais Crítico)",
                    color='COR', color_discrete_map="identity")
    st.plotly_chart(fig_dia, use_container_width=True)

    # --- GRÁFICO 3: MAPA DE CALOR (Mantido) ---
    st.markdown("### 3. Mapa de Calor (Densidade de Chamados)")
    pivot_picos = df.pivot_table(index='HORA', columns='DIA_SEMANA', values='TICKETS', aggfunc='sum').fillna(0)
    # Reordenar colunas do mapa
    colunas_mapa = [d for d in ordem_dias if d in pivot_picos.columns]
    pivot_picos = pivot_picos[colunas_mapa]
    
    fig_heat = px.imshow(pivot_picos, text_auto=True, aspect="auto", 
                        color_continuous_scale='Reds',
                        title="Cruzamento Dia x Hora")
    st.plotly_chart(fig_heat, use_container_width=True)

# --- INTEGRAÇÃO NA ABA (Resumo da Função Principal) ---
# Adicione esta chamada dentro das suas tabs originais
# with tabs[2]: # Na aba de Picos
#     renderizar_analise_picos(pd.DataFrame(db_data.get("picos", [])))
