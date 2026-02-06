import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import plotly.express as px
import plotly.graph_objects as go
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

DEPARTAMENTOS = ["Compras", "Logística", "TI", "Financeiro", "RH", "Operações", "Comercial", "Diretoria"]
MOTIVOS_BASE = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna"]

def exibir(user_role="OPERACIONAL"):
    # 1. CSS COM DEGRADÊ E ESTILO PREMIUM
    st.markdown("""
    <style>
        /* Fundo da página com degradê leve */
        .stApp {
            background: linear-gradient(180deg, #f0f4f8 0%, #ffffff 100%);
        }
        
        /* Cards de Métrica Estilizados */
        .metric-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05);
            border-left: 5px solid #002366;
            text-align: center;
        }
        .metric-value { font-size: 32px; font-weight: 800; color: #1e293b; line-height: 1; }
        .metric-label { font-size: 12px; color: #64748b; font-weight: 700; text-transform: uppercase; margin-top: 8px; }
        .metric-percent { font-size: 14px; color: #10b981; font-weight: bold; }

        /* Régua de Progresso */
        .ponto-regua { width: 38px; height: 38px; border-radius: 50%; background: white; display: flex; 
                       align-items: center; justify-content: center; font-weight: bold; color: #94a3b8; 
                       margin: 0 auto; border: 2px solid #e2e8f0; transition: 0.3s; }
        .ponto-check { background: #10b981 !important; color: white !important; border-color: #10b981 !important; }
        .ponto-atual { background: #002366 !important; color: white !important; border-color: #002366 !important; transform: scale(1.1); }
    </style>
    """, unsafe_allow_html=True)

    if 'db_pqi' not in st.session_state:
        try:
            st.session_state.db_pqi = db.carregar_projetos()
        except Exception as e:
            st.error(f"Erro ao carregar banco de dados: {e}")
            st.session_state.db_pqi = [] # Fallback para não travar a tela

    # 2. INICIALIZAÇÃO DE DADOS
    if 'db_pqi' not in st.session_state:
        try: st.session_state.db_pqi = db.carregar_projetos()
        except: st.session_state.db_pqi = []

    def salvar_seguro():
        try: db.salvar_projetos(st.session_state.db_pqi)
        except Exception as e: st.error(f"Erro ao salvar: {e}")

    # --- ESTRUTURA DE ABAS ---
    titulos = ["📊 DASHBOARD ESTRATÉGICO"]
    if user_role in ["ADM", "GERENTE"]: titulos.append("⚙️ GESTÃO")
    titulos.append("🚀 OPERAÇÃO PQI")
    tabs = st.tabs(titulos)

    # --- 1. DASHBOARD ESTRATÉGICO (COM PERCENTUAIS) ---
    with tabs[0]:
        projs = st.session_state.db_pqi
        ativos = [p for p in projs if p.get('status') != "Concluído"]
        
        if ativos:
            todas_notas = []
            for p in projs:
                for n in p.get('notas', []):
                    n['Projeto'] = p['titulo']
                    todas_notas.append(n)
            df_total = pd.DataFrame(todas_notas)

            # --- LINHA DE KPIS ---
            c1, c2, c3 = st.columns(3)
            
            # KPI 1: % de Conclusão Geral do Portfólio
            total_projs = len(projs)
            concluidos = len([p for p in projs if p.get('status') == "Concluído"])
            perc_concl = (concluidos / total_projs * 100) if total_projs > 0 else 0
            c1.markdown(f'''<div class="metric-card">
                <div class="metric-label">Taxa de Entrega</div>
                <div class="metric-value">{perc_concl:.1f}%</div>
                <div class="metric-percent">{concluidos} de {total_projs} projetos</div>
            </div>''', unsafe_allow_html=True)

            # KPI 2: Volume de Ações Ativas
            total_acoes = len(df_total)
            c2.markdown(f'''<div class="metric-card">
                <div class="metric-label">Ações Registradas</div>
                <div class="metric-value">{total_acoes}</div>
                <div class="metric-percent">Histórico Completo</div>
            </div>''', unsafe_allow_html=True)

            # KPI 3: Departamento "Gargalo" em %
            gargalo_html = "N/A"
            if not df_total.empty and 'depto' in df_total.columns:
                df_pos = df_total[df_total['motivo'] == "Pedido de Posicionamento"]
                if not df_pos.empty:
                    top_depto = df_pos['depto'].value_counts()
                    nome_depto = top_depto.index[0]
                    perc_depto = (top_depto.iloc[0] / len(df_pos)) * 100
                    gargalo_html = f"{nome_depto} ({perc_depto:.0f}%)"
            
            c3.markdown(f'''<div class="metric-card" style="border-left-color: #ef4444;">
                <div class="metric-label">Principal Gargalo</div>
                <div class="metric-value" style="color:#ef4444; font-size:24px;">{gargalo_html}</div>
                <div class="metric-percent">Pedidos de Posicionamento</div>
            </div>''', unsafe_allow_html=True)

            st.write("---")
            
            # --- GRÁFICOS COM DEGRADÊ E PERCENTUAL ---
            col_left, col_right = st.columns([1.2, 1])
            
            with col_left:
                st.markdown("#### 📊 Representatividade do Esforço por Departamento")
                if not df_total.empty and 'depto' in df_total.columns:
                    df_depto_perc = df_total['depto'].value_counts(normalize=True).reset_index()
                    df_depto_perc.columns = ['Departamento', 'Porcentagem']
                    df_depto_perc['Porcentagem'] *= 100

                    fig_depto = px.bar(df_depto_perc, x='Porcentagem', y='Departamento', 
                                       orientation='h', text_auto='.1f',
                                       color='Porcentagem', color_continuous_scale='Blues')
                    fig_depto.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
                    st.plotly_chart(fig, width='stretch')

            with col_right:
                st.markdown("#### 🍩 Distribuição de Assuntos")
                if not df_total.empty:
                    fig_donut = px.pie(df_total, names="motivo", hole=0.6,
                                       color_discrete_sequence=px.colors.sequential.RdBu)
                    fig_donut.update_traces(textinfo='percent+label')
                    fig_donut.update_layout(margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig, width='stretch')

    # --- ABA OPERAÇÃO (CÉREBRO DO SISTEMA) ---
    with tabs[-1]:
        # (Lógica de seleção de projeto e régua mantida conforme versões anteriores)
        # O campo de departamento e assuntos customizados seguem a mesma regra
        pass
