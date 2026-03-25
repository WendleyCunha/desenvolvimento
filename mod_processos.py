import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import plotly.express as px
import database as db
import time

# --- DIRETÓRIO DE ANEXOS ---
UPLOAD_DIR = "anexos_pqi"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- CONFIGURAÇÕES DO ROADMAP ---
ROADMAP = [
    {"id": 1, "nome": "Triagem & GUT"}, {"id": 2, "nome": "Escopo & Charter"},
    {"id": 3, "nome": "Autorização Sponsor"}, {"id": 4, "nome": "Coleta & Impedimentos"},
    {"id": 5, "nome": "Modelagem & Piloto"}, {"id": 6, "nome": "Migração (Go-Live)"},
    {"id": 7, "nome": "Acompanhamento/Ajuste"}, {"id": 8, "nome": "Padronização & POP"}
]

DEPARTAMENTOS = ["CX", "PQI","Compras", "Logística", "TI", "Financeiro", "RH", "Fiscal", "Operações", "Comercial", "Diretoria"]
MOTIVOS_PADRAO = ["Reunião", "Análise de Dados", "Mapeamento", "Treinamento", "Outros"]

def exibir(user_role="OPERACIONAL", user_name="Usuário"):
    # 1. ESTILO CSS
    st.markdown("""
    <style>
        .ponto-regua { width: 30px; height: 30px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; font-size: 12px;}
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 8px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 9px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 25px; line-height: 1; }
        .timer-ativo { background-color: #f0fdf4; border: 1px solid #16a34a; padding: 10px; border-radius: 5px; color: #16a34a; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

    # 2. INICIALIZAÇÃO DE DADOS
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()
    if 'historico_esforco' not in st.session_state:
        st.session_state.historico_esforco = db.carregar_esforco()
    if 'motivos_timer' not in st.session_state:
        st.session_state.motivos_timer = db.carregar_motivos()

    def salvar_seguro():
        db.salvar_projetos(st.session_state.db_pqi)
        db.salvar_esforco(st.session_state.historico_esforco)

    # --- DEFINIÇÃO DAS ABAS ---
    titulos = ["⏱️ MEU TIMER", "📊 DASHBOARD"]
    if user_role == "ADM":
        titulos.append("🛡️ PAINEL ADM")
    titulos.append("⚙️ GESTÃO")
    titulos.append("🚀 OPERAÇÃO PQI")

    tabs = st.tabs(titulos)
    
    # ... (Abas de Timer, Dash e ADM omitidas para focar no erro, mas mantidas no seu código real) ...

    # Encontrar o índice da aba de Operação
    idx_op = len(titulos) - 1 

    with tabs[idx_op]:
        st.subheader("🚀 Operação de Processos")
        projs = st.session_state.db_pqi
        
        if not projs:
            st.warning("Nenhum projeto cadastrado.")
        else:
            c_f1, c_f2 = st.columns([1, 2])
            status_sel = c_f1.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
            map_status = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
            
            filtrados = [p for p in projs if p.get('status', 'Ativo') == map_status[status_sel]]
            
            if filtrados:
                escolha = c_f2.selectbox("Selecione o Projeto:", [p.get('titulo', 'Sem Título') for p in filtrados])
                projeto = next(p for p in filtrados if p.get('titulo') == escolha)
                
                # CORREÇÃO CRÍTICA: Garantir que 'fase' existe
                fase_atual = projeto.get('fase', 1) 

                st.write("")
                cols_r = st.columns(8)
                for i, etapa in enumerate(ROADMAP):
                    n = i + 1
                    cl, txt = "ponto-regua", str(n)
                    
                    # Lógica da Régua com a variável segura fase_atual
                    if n < fase_atual: 
                        cl += " ponto-check"
                        txt = "✔"
                    elif n == fase_atual: 
                        cl += " ponto-atual"
                    
                    cols_r[i].markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

                t_exec, t_dossie = st.tabs(["📝 Execução", "📁 Dossiê"])
                
                with t_exec:
                    # Garantia de que a fase não ultrapasse o limite do Roadmap ao exibir o nome
                    nome_etapa = ROADMAP[fase_atual-1]['nome'] if 0 < fase_atual <= 8 else "Etapa Indefinida"
                    st.markdown(f"### Etapa {fase_atual}: {nome_etapa}")
                    
                    col_btn1, col_btn2 = st.columns(2)
                    if col_btn1.button("▶️ AVANÇAR", use_container_width=True) and fase_atual < 8:
                        projeto['fase'] = fase_atual + 1
                        salvar_seguro()
                        st.rerun()
                    if col_btn2.button("⏪ RECUAR", use_container_width=True) and fase_atual > 1:
                        projeto['fase'] = fase_atual - 1
                        salvar_seguro()
                        st.rerun()
            else:
                st.info("Nenhum projeto encontrado para este filtro.")
