import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import database as db

# --- CONFIGURAÇÕES DE DIRETÓRIO ---
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

def exibir(user_role="ADM"):
    # 1. ESTILO CSS PARA REPAGINADA VISUAL
    st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .header-card {
            background-color: white; padding: 20px; border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; border-left: 5px solid #002366;
        }
        .metric-card { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        
        /* Régua de Navegação */
        .ponto-regua { width: 38px; height: 38px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; }
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 12px rgba(0, 35, 102, 0.3); }
        .label-regua { font-size: 10px; text-align: center; font-weight: 700; margin-top: 5px; color: #475569; min-height: 30px; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO DE DADOS
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- ABAS PRINCIPAIS ---
    tab_geral, tab_detalhe = st.tabs(["📊 DASHBOARD GERAL", "🚀 GESTÃO DE PROJETOS"])

    # --- ABA 1: VISÃO GERAL (O QUE VOCÊ PEDIU) ---
    with tab_geral:
        projs = st.session_state.db_pqi
        if not projs:
            st.info("Nenhum projeto cadastrado ainda.")
        else:
            c1, c2, c3 = st.columns(3)
            total_acoes = sum(len(p.get('notas', [])) for p in projs)
            ativos = len([p for p in projs if p.get('status') == 'Ativo'])
            
            with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Projetos Ativos</div><div class="metric-value">{ativos}</div></div>', unsafe_allow_html=True)
            with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Total de Ações</div><div class="metric-value">{total_acoes}</div></div>', unsafe_allow_html=True)
            with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Média de Progresso</div><div class="metric-value">{int(sum(p["fase"] for p in projs)/len(projs))}/8</div></div>', unsafe_allow_html=True)
            
            st.write("### 📋 Status do Portfólio")
            df_geral = []
            for p in projs:
                df_geral.append({
                    "Projeto": p['titulo'],
                    "Status": p['status'],
                    "Fase Atual": f"Etapa {p['fase']}: {ROADMAP[p['fase']-1]['nome']}",
                    "Ações": len(p.get('notas', []))
                })
            st.table(pd.DataFrame(df_geral))

    # --- ABA 2: GESTÃO DE PROJETOS ---
    with tab_detalhe:
        # Cabeçalho Repaginado
        with st.container():
            st.markdown('<div class="header-card">', unsafe_allow_html=True)
            col_h1, col_h2, col_h3 = st.columns([1, 2, 1])
            
            with col_h1:
                status_sel = st.selectbox("Status:", ["Ativo", "Concluído", "Pausado"], label_visibility="collapsed")
            
            projs_filtrados = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == status_sel]
            
            with col_h2:
                if projs_filtrados:
                    escolha = st.selectbox("Selecione o Projeto:", [p['titulo'] for p in projs_filtrados], label_visibility="collapsed")
                    projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
                else:
                    st.warning("Sem projetos.")
                    projeto = None
            
            with col_h3:
                if user_role in ["ADM", "GERENTE"]:
                    if st.button("➕ NOVO PROJETO", use_container_width=True, type="primary"):
                        novo = {"titulo": f"Projeto {len(st.session_state.db_pqi)+1}", "fase": 1, "status": "Ativo", "notas": [], "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, "lembretes": [], "pastas_virtuais": {}, "motivos_custom": []}
                        st.session_state.db_pqi.append(novo); db.salvar_projetos(st.session_state.db_pqi); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        if projeto:
            # RÉGUA DE NAVEGAÇÃO
            cols_r = st.columns(8)
            for i, etapa in enumerate(ROADMAP):
                n = i + 1
                cl = "ponto-regua"
                txt = str(n)
                if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                elif n == projeto['fase']: cl += " ponto-atual"
                with cols_r[i]:
                    st.markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

            # ABAS DE CONTEÚDO
            t1, t2, t3, t4 = st.tabs(["🚀 Execução", "📂 Dossiê", "📊 Esforço", "⚙️ Gestão"])
            
            with t1:
                col_e1, col_e2 = st.columns([2, 1])
                with col_e1:
                    st.subheader(f"📍 Fase {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                    notas_fase = [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]
                    
                    if not notas_fase: st.info("Sem registros nesta etapa.")
                    else:
                        for idx, n in enumerate(notas_fase):
                            with st.expander(f"📝 {n['motivo']} - {n.get('setor', 'GERAL')} ({n['data']})"):
                                st.write(n['texto'])
                                if n.get('arquivo_local') and os.path.exists(n['arquivo_local']):
                                    with open(n['arquivo_local'], "rb") as f:
                                        st.download_button("📥 Baixar Anexo", f, key=f"dl_{idx}")
                                if st.button("🗑️ Excluir", key=f"del_{idx}"):
                                    projeto['notas'].remove(n); db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                    st.divider()
                    with st.popover("➕ Adicionar Novo Registro"):
                        sel_mot = st.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                        setor = st.text_input("Setor/Responsável").upper()
                        desc = st.text_area("O que foi feito?")
                        arq = st.file_uploader("Anexo")
                        if st.button("Gravar no Banco"):
                            caminho = None
                            if arq:
                                caminho = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{arq.name}")
                                with open(caminho, "wb") as f: f.write(arq.getbuffer())
                            projeto['notas'].append({"motivo": sel_mot, "setor": setor, "texto": desc, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase'], "arquivo_local": caminho})
                            db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                with col_e2:
                    st.markdown("#### 🕹️ Fluxo")
                    if projeto['fase'] < 8 and st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                        projeto['fase'] += 1; db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                    if projeto['fase'] > 1 and st.button("⏪ RECUAR ETAPA", use_container_width=True):
                        projeto['fase'] -= 1; db.salvar_projetos(st.session_state.db_pqi); st.rerun()

            with t3:
                df = pd.DataFrame(projeto.get('notas', []))
                if not df.empty:
                    st.bar_chart(df['motivo'].value_counts())
                else: st.info("Sem dados para gráficos.")

            with t4:
                if user_role in ["ADM", "GERENTE"]:
                    projeto['titulo'] = st.text_input("Nome do Projeto", projeto['titulo'])
                    projeto['status'] = st.selectbox("Status do Projeto", ["Ativo", "Concluído", "Pausado"], index=["Ativo", "Concluído", "Pausado"].index(projeto['status']))
                    if st.button("🗑️ EXCLUIR PROJETO DEFINITIVAMENTE", type="secondary"):
                        st.session_state.db_pqi.remove(projeto); db.salvar_projetos(st.session_state.db_pqi); st.rerun()
