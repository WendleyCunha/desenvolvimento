import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import database as db

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

MOTIVOS_PADRAO = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna (Sem Dash)"]

def exibir(user_role="OPERACIONAL"):
    # 1. ESTILO CSS
    st.markdown("""
    <style>
        .metric-card { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #ececec; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .ponto-regua { width: 30px; height: 30px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; font-size: 12px;}
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 8px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 9px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 25px; line-height: 1; }
    </style>
    """, unsafe_allow_html=True)

    # 2. PERSISTÊNCIA SEGURA
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    def salvar_seguro():
        try:
            db.salvar_projetos(st.session_state.db_pqi)
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

    # --- ABAS MESTRAS ---
    abas_topo = ["📊 DASHBOARD GERAL"]
    if user_role in ["ADM", "GERENTE"]:
        abas_topo.append("⚙️ GESTÃO")
    abas_topo.append("🚀 OPERAÇÃO PQI")

    tab_dash, *tab_outras = st.tabs(abas_topo)

    # --- 1. DASHBOARD GERAL (Melhorado) ---
    with tab_dash:
        sub_dash1, sub_dash2 = st.tabs(["📈 Portfólio Ativo", "✅ Projetos Entregues"])
        
        projs = st.session_state.db_pqi
        
        with sub_dash1:
            ativos = [p for p in projs if p.get('status') != "Concluído"]
            if ativos:
                c1, c2, c3 = st.columns(3)
                c1.markdown(f'<div class="metric-card"><div class="metric-label">Em Andamento</div><div class="metric-value">{len(ativos)}</div></div>', unsafe_allow_html=True)
                c2.markdown(f'<div class="metric-card"><div class="metric-label">Total Ações</div><div class="metric-value">{sum(len(p.get("notas", [])) for p in ativos)}</div></div>', unsafe_allow_html=True)
                c3.markdown(f'<div class="metric-card"><div class="metric-label">Lembretes</div><div class="metric-value">{sum(len(p.get("lembretes", [])) for p in ativos)}</div></div>', unsafe_allow_html=True)
                
                st.write("#### Esforço por Projeto (Ações Registradas)")
                df_ativos = pd.DataFrame([{
                    "Projeto": p['titulo'], 
                    "Fase": f"Fase {p['fase']}", 
                    "Esforço": len(p.get('notas', []))
                } for p in ativos])
                st.bar_chart(df_ativos.set_index("Projeto")["Esforço"])
                
                st.write("#### Lista Detalhada")
                st.dataframe(df_ativos, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum projeto ativo no momento.")

        with sub_dash2:
            entregues = [p for p in projs if p.get('status') == "Concluído"]
            if entregues:
                df_entregues = pd.DataFrame([{
                    "Projeto": p['titulo'], 
                    "Conclusão": p.get('data_conclusao', 'N/A'),
                    "Total de Ações": len(p.get('notas', []))
                } for p in entregues])
                st.dataframe(df_entregues, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum projeto concluído ainda.")

    # --- 2. GESTÃO ---
    idx_op = 0
    if user_role in ["ADM", "GERENTE"]:
        idx_op = 1
        with tab_outras[0]:
            st.subheader("⚙️ Painel Administrativo")
            if st.button("➕ CRIAR NOVO PROJETO", type="primary"):
                novo = {"titulo": f"Novo Projeto {len(projs)+1}", "fase": 1, "status": "Ativo", "notas": [], "lembretes": [], "pastas_virtuais": {}}
                st.session_state
