import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import database as db

# --- CONFIGURAÇÕES ---
UPLOAD_DIR = "anexos_pqi"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

ROADMAP = [
    {"id": 1, "nome": "Triagem & GUT"}, {"id": 2, "nome": "Escopo & Charter"},
    {"id": 3, "nome": "Autorização Sponsor"}, {"id": 4, "nome": "Coleta & Impedimentos"},
    {"id": 5, "nome": "Modelagem & Piloto"}, {"id": 6, "nome": "Migração (Go-Live)"},
    {"id": 7, "nome": "Acompanhamento/Ajuste"}, {"id": 8, "nome": "Padronização & POP"}
]

MOTIVOS_PADRAO = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna (Sem Dash)"]

def exibir(user_role="OPERACIONAL"):
    # 1. ESTILO CSS PREMIUM
    st.markdown("""
    <style>
        .header-card { background-color: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; border-left: 5px solid #002366; }
        .metric-card { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .ponto-regua { width: 38px; height: 38px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; }
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 12px rgba(0, 35, 102, 0.3); }
        .label-regua { font-size: 10px; text-align: center; font-weight: 700; margin-top: 5px; color: #475569; min-height: 30px; }
    </style>
    """, unsafe_allow_html=True)

    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- DEFINIÇÃO DE ABAS MESTRAS ---
    abas_principais = ["📊 DASHBOARD GERAL", "🚀 GESTÃO DE PROJETOS", "📜 DOSSIÊS"]
    if user_role in ["ADM", "GERENTE"]:
        abas_principais.append("⚙️ CONFIGURAÇÕES")
    
    tab_dash, tab_gestao, tab_dossie, *tab_config = st.tabs(abas_principais)

    # --- ABA 1: DASHBOARD PREMIUM (VISÃO DE ESFORÇO) ---
    with tab_dash:
        st.subheader("📊 Painel de Controle de Esforço PQI")
        projs = st.session_state.db_pqi
        if projs:
            c1, c2, c3, c4 = st.columns(4)
            total_acoes = sum(len(p.get('notas', [])) for p in projs)
            with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Projetos</div><div class="metric-value">{len(projs)}</div></div>', unsafe_allow_html=True)
            with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Ações Totais</div><div class="metric-value">{total_acoes}</div></div>', unsafe_allow_html=True)
            
            # Gráfico de Esforço por Projeto
            st.write("---")
            df_esforco = pd.DataFrame([{"Projeto": p['titulo'], "Ações": len(p.get('notas', []))} for p in projs])
            st.bar_chart(df_esforco.set_index("Projeto"))

    # --- ABA 2: GESTÃO (COM RÉGUA E FILTROS) ---
    with tab_gestao:
        with st.container():
            st.markdown('<div class="header-card">', unsafe_allow_html=True)
            col_f1, col_f2, col_f3 = st.columns([1, 2, 1])
            with col_f1:
                status_sel = st.selectbox("Filtrar Status", ["Ativo", "Concluído", "Pausado"])
            projs_f = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == status_sel]
            with col_f2:
                if projs_f:
                    escolha = st.selectbox("Projeto:", [p['titulo'] for p in projs_f])
                    projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
                else: projeto = None
            with col_f3:
                if user_role in ["ADM", "GERENTE"]:
                    if st.button("➕ NOVO PROJETO", use_container_width=True):
                        novo = {"titulo": f"Novo {len(projs)+1}", "fase": 1, "status": "Ativo", "notas": [], "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, "lembretes": [], "pastas_virtuais": {}, "motivos_custom": []}
                        st.session_state.db_pqi.append(novo); db.salvar_projetos(st.session_state.db_pqi); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        if projeto:
            # RÉGUA MANTIDA
            cols_r = st.columns(8)
            for i, etapa in enumerate(ROADMAP):
                n, cl, txt = i + 1, "ponto-regua", str(i+1)
                if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                elif n == projeto['fase']: cl += " ponto-atual"
                with cols_r[i]: st.markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)
            
            # Execução e Lembretes
            c_exec1, c_exec2 = st.columns([2, 1])
            with c_exec1:
                st.subheader(f"📍 Fase {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                # Aqui entra sua lógica de adicionar notas (idêntica ao original)
                with st.expander("📝 Adicionar Registro de Esforço"):
                    sel_mot = st.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                    desc = st.text_area("Descrição")
                    if st.button("Salvar Registro"):
                        projeto['notas'].append({"motivo": sel_mot, "texto": desc, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase']})
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()
            with c_exec2:
                st.markdown("#### ⚙️ Controle")
                if user_role in ["ADM", "GERENTE", "SUPERVISÃO"]:
                    if projeto['fase'] < 8 and st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                        projeto['fase'] += 1; db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                    if projeto['fase'] > 1 and st.button("⏪ RECUAR", use_container_width=True):
                        projeto['fase'] -= 1; db.salvar_projetos(st.session_state.db_pqi); st.rerun()

    # --- ABA 3: DOSSIÊ (HISTÓRICO E EXPORTAÇÃO) ---
    with tab_dossie:
        st.subheader("📜 Dossiê Completo de Esforço")
        if 'projeto' in locals() and projeto:
            df_dossie = pd.DataFrame(projeto.get('notas', []))
            if not df_dossie.empty:
                st.dataframe(df_dossie, use_container_width=True)
                # Lógica de Exportação Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_dossie.to_excel(writer, index=False)
                st.download_button("📥 Exportar Excel", output.getvalue(), f"Dossie_{projeto['titulo']}.xlsx")
            else: st.info("Sem registros para este projeto.")

    # --- ABA 4: CONFIGURAÇÕES (APENAS ALÇADA ADM/GERENTE) ---
    if user_role in ["ADM", "GERENTE"] and tab_config:
        with tab_config[0]:
            st.subheader("⚙️ Gestão Administrativa")
            if 'projeto' in locals() and projeto:
                projeto['titulo'] = st.text_input("Renomear Projeto", projeto['titulo'])
                if st.button("🗑️ DELETAR PROJETO DEFINITIVAMENTE", type="secondary"):
                    st.session_state.db_pqi.remove(projeto); db.salvar_projetos(st.session_state.db_pqi); st.rerun()
