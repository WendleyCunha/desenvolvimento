import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import plotly.express as px
import database as db

# --- CONFIGURAÇÕES ---
UPLOAD_DIR = "anexos_pqi"
if not os.path.exists(UPLOAD_DIR): os.makedirs(UPLOAD_DIR)

ROADMAP = [
    {"id": 1, "nome": "Triagem & GUT"}, {"id": 2, "nome": "Escopo & Charter"},
    {"id": 3, "nome": "Autorização Sponsor"}, {"id": 4, "nome": "Coleta & Impedimentos"},
    {"id": 5, "nome": "Modelagem & Piloto"}, {"id": 6, "nome": "Migração (Go-Live)"},
    {"id": 7, "nome": "Acompanhamento/Ajuste"}, {"id": 8, "nome": "Padronização & POP"}
]

# Lista padrão de departamentos para identificar gargalos
DEPARTAMENTOS = ["Compras", "Logística", "TI", "Financeiro", "RH", "Operações", "Comercial", "Diretoria"]
MOTIVOS_BASE = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna"]

def exibir(user_role="OPERACIONAL"):
    # --- CSS ---
    st.markdown("""
    <style>
        .metric-card { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; text-align: center; }
        .metric-value { font-size: 28px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .ponto-regua { width: 35px; height: 35px; border-radius: 50%; background: #f1f5f9; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8; margin: 0 auto; border: 2px solid #e2e8f0; }
        .ponto-check { background: #10b981 !important; color: white !important; }
        .ponto-atual { background: #002366 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

    # --- DADOS ---
    if 'db_pqi' not in st.session_state:
        try: st.session_state.db_pqi = db.carregar_projetos()
        except: st.session_state.db_pqi = []

    def salvar_seguro():
        try: db.salvar_projetos(st.session_state.db_pqi)
        except Exception as e: st.error(f"Erro ao salvar: {e}")

    # --- ABAS ---
    titulos = ["📊 DASHBOARD GERAL"]
    if user_role in ["ADM", "GERENTE"]: titulos.append("⚙️ GESTÃO")
    titulos.append("🚀 OPERAÇÃO PQI")
    tabs = st.tabs(titulos)

    # --- 1. DASHBOARD GERAL (Mapeamento de Gargalos) ---
    with tabs[0]:
        projs = st.session_state.db_pqi
        ativos = [p for p in projs if p.get('status') != "Concluído"]
        
        if ativos:
            c1, c2, c3 = st.columns(3)
            # Acumular todas as notas de todos os projetos ativos
            todas_notas = []
            for p in ativos:
                for n in p.get('notas', []):
                    n['Projeto_Origem'] = p['titulo']
                    todas_notas.append(n)
            df_total = pd.DataFrame(todas_notas)

            c1.markdown(f'<div class="metric-card"><div class="metric-label">Projetos</div><div class="metric-value">{len(ativos)}</div></div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="metric-card"><div class="metric-label">Ações Totais</div><div class="metric-value">{len(df_total)}</div></div>', unsafe_allow_html=True)
            
            # Identificar o departamento com mais "Pedido de Posicionamento" (O Gargalo)
            gargalo_text = "N/A"
            if not df_total.empty and 'depto' in df_total.columns:
                gargalo_df = df_total[df_total['motivo'] == "Pedido de Posicionamento"]
                if not gargalo_df.empty:
                    gargalo_text = gargalo_df['depto'].mode()[0]
            c3.markdown(f'<div class="metric-card"><div class="metric-label">Maior Gargalo</div><div class="metric-value" style="color:#ef4444">{gargalo_text}</div></div>', unsafe_allow_html=True)

            st.write("---")
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.markdown("#### 🏗️ Esforço por Departamento")
                if not df_total.empty and 'depto' in df_total.columns:
                    fig_depto = px.bar(df_total['depto'].value_counts(), orientation='h', color_discrete_sequence=['#6366f1'])
                    st.plotly_chart(fig_depto, use_container_width=True)
            
            with col_g2:
                st.markdown("#### 🎯 Tipos de Assunto")
                if not df_total.empty:
                    fig_motivo = px.pie(df_total, names="motivo", hole=0.4)
                    st.plotly_chart(fig_motivo, use_container_width=True)

    # --- 2. GESTÃO (Assuntos Customizados) ---
    if user_role in ["ADM", "GERENTE"]:
        with tabs[1]:
            st.subheader("⚙️ Configurações Globais")
            # Gestão de Assuntos Customizados por Projeto ou Global
            st.info("Aqui você pode gerenciar os projetos e seus assuntos específicos.")
            
            for i, p in enumerate(st.session_state.db_pqi):
                with st.expander(f"Configurações: {p['titulo']}"):
                    p['titulo'] = st.text_input("Nome", p['titulo'], key=f"t_{i}")
                    
                    # Campo para adicionar novos assuntos exclusivos deste projeto
                    st.write("**Assuntos/Motivos Customizados**")
                    novos_assuntos = st.text_input("Adicionar Assunto (separe por vírgula)", key=f"new_ass_{i}")
                    if st.button("Atualizar Lista de Assuntos", key=f"btn_ass_{i}"):
                        p['motivos_custom'] = [a.strip() for a in novos_assuntos.split(",") if a.strip()]
                        salvar_seguro(); st.rerun()
                    
                    if st.button("🗑️ Excluir Projeto", key=f"del_{i}"):
                        st.session_state.db_pqi.remove(p); salvar_seguro(); st.rerun()

    # --- 3. OPERAÇÃO PQI (Com Campo Departamento) ---
    with tabs[-1]:
        # ... (lógica de seleção de projeto mantida) ...
        # No formulário de "Adicionar Registro":
        
        # Supondo que 'projeto' é o selecionado:
        assuntos_finais = MOTIVOS_BASE + projeto.get('motivos_custom', [])
        
        with st.popover("➕ Adicionar Registro com Mapeamento"):
            mot = st.selectbox("Assunto/Motivo", assuntos_finais)
            
            # NOVO CAMPO: Departamento
            depto = st.selectbox("Departamento Relacionado (Gargalo)", ["Nenhum"] + DEPARTAMENTOS)
            
            dsc = st.text_area("O que foi feito / O que está pendente?")
            
            if st.button("Gravar Registro"):
                projeto['notas'].append({
                    "motivo": mot,
                    "depto": depto,
                    "texto": dsc,
                    "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "fase_origem": projeto['fase']
                })
                salvar_seguro(); st.rerun()
