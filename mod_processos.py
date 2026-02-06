import streamlit as st
import pandas as pd
from datetime import datetime
import os
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

DEPARTAMENTOS = ["Compras", "Logística", "TI", "Financeiro", "RH", "Operações", "Comercial", "Diretoria"]
MOTIVOS_BASE = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna"]

def exibir(user_role="OPERACIONAL"):
    # 1. CSS PROFISSIONAL
    st.markdown("""
    <style>
        .stApp { background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%); }
        .metric-card {
            background: white; padding: 20px; border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
            border-left: 5px solid #002366; text-align: center;
        }
        .metric-value { font-size: 28px; font-weight: 800; color: #1e293b; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; }
        .metric-percent { font-size: 12px; color: #10b981; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO DE DADOS
    if 'db_pqi' not in st.session_state:
        try:
            st.session_state.db_pqi = db.carregar_projetos()
        except:
            st.session_state.db_pqi = []

    def salvar_seguro():
        try: db.salvar_projetos(st.session_state.db_pqi)
        except Exception as e: st.error(f"Erro ao salvar: {e}")

    # 3. ABAS
    titulos = ["📊 DASHBOARD ESTRATÉGICO"]
    if user_role in ["ADM", "GERENTE"]: titulos.append("⚙️ GESTÃO")
    titulos.append("🚀 OPERAÇÃO PQI")
    tabs = st.tabs(titulos)

    # --- ABA 1: DASHBOARD ---
    with tabs[0]:
        projs = st.session_state.db_pqi
        if not projs:
            st.info("Nenhum projeto encontrado para análise.")
        else:
            todas_notas = []
            for p in projs:
                for n in p.get('notas', []):
                    item = n.copy()
                    item['Projeto'] = p.get('titulo', 'Sem Título')
                    todas_notas.append(item)
            
            df_total = pd.DataFrame(todas_notas)

            # KPIs
            c1, c2, c3 = st.columns(3)
            with c1:
                concluidos = len([p for p in projs if p.get('status') == "Concluído"])
                perc = (concluidos / len(projs) * 100) if len(projs) > 0 else 0
                st.markdown(f'<div class="metric-card"><div class="metric-label">Taxa de Conclusão</div><div class="metric-value">{perc:.1f}%</div><div class="metric-percent">{concluidos} concluídos</div></div>', unsafe_allow_html=True)
            
            with c2:
                st.markdown(f'<div class="metric-card"><div class="metric-label">Ações Totais</div><div class="metric-value">{len(df_total)}</div><div class="metric-percent">Registros de Esforço</div></div>', unsafe_allow_html=True)
            
            with c3:
                gargalo = "Nenhum"
                if not df_total.empty and 'depto' in df_total.columns:
                    pedidos = df_total[df_total['motivo'] == "Pedido de Posicionamento"]
                    if not pedidos.empty:
                        gargalo = pedidos['depto'].mode()[0]
                st.markdown(f'<div class="metric-card" style="border-left-color: #ef4444;"><div class="metric-label">Maior Gargalo</div><div class="metric-value" style="color:#ef4444">{gargalo}</div></div>', unsafe_allow_html=True)

            st.divider()

            if not df_total.empty:
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("##### 📈 Esforço por Departamento (%)")
                    if 'depto' in df_total.columns:
                        df_d = df_total['depto'].value_counts(normalize=True).reset_index()
                        df_d.columns = ['Depto', 'Perc']
                        df_d['Perc'] *= 100
                        fig_d = px.bar(df_d, x='Perc', y='Depto', orientation='h', text_auto='.1f', color='Perc', color_continuous_scale='Blues')
                        fig_d.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig_d, width='stretch')

                with col_g2:
                    st.markdown("##### 🎯 Tipos de Assunto")
                    fig_p = px.pie(df_total, names="motivo", hole=0.5, color_discrete_sequence=px.colors.sequential.RdBu)
                    fig_p.update_traces(textinfo='percent+label')
                    fig_p.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_p, width='stretch')

    # --- ABA 3: OPERAÇÃO (CÓDIGO FUNCIONAL) ---
    with tabs[-1]:
        if not projs:
            st.warning("Cadastre um projeto na aba Gestão primeiro.")
        else:
            projeto_nome = st.selectbox("Selecione o Projeto", [p['titulo'] for p in projs])
            projeto = next(p for p in projs if p['titulo'] == projeto_nome)
            
            st.subheader(f"📍 Projeto: {projeto['titulo']}")
            
            # Formulário de Registro
            with st.expander("➕ Registrar Novo Posicionamento / Esforço", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    mot = st.selectbox("Assunto", MOTIVOS_BASE + projeto.get('motivos_custom', []))
                with c2:
                    depto = st.selectbox("Departamento Alvo (Gargalo)", DEPARTAMENTOS)
                
                dsc = st.text_area("Descrição da Ação/Pendência")
                if st.button("Gravar no Histórico"):
                    if 'notas' not in projeto: projeto['notas'] = []
                    projeto['notas'].append({
                        "motivo": mot,
                        "depto": depto,
                        "texto": dsc,
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M")
                    })
                    salvar_seguro()
                    st.success("Registrado com sucesso!")
                    st.rerun()

            # Exibição do Histórico
            if projeto.get('notas'):
                st.write("### Histórico de Mapeamento")
                for n in reversed(projeto['notas']):
                    with st.container(border=True):
                        st.caption(f"📅 {n['data']} | 🏢 {n.get('depto', 'N/A')} | 🏷️ {n['motivo']}")
                        st.write(n['texto'])
