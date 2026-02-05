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
    # 1. ESTILO CSS PREMIUM
    st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .metric-card { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e9ecef; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 11px; color: #6c757d; font-weight: 700; text-transform: uppercase; }
        .ponto-regua { width: 35px; height: 35px; border-radius: 50%; background: #dee2e6; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #495057; margin: 0 auto; border: 2px solid #ced4da; }
        .ponto-check { background: #198754; color: white; border-color: #198754; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 12px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 10px; text-align: center; font-weight: bold; margin-top: 5px; color: #495057; height: 35px; line-height: 1.1; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO DE DADOS
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- DEFINIÇÃO DE ABAS MESTRAS NO TOPO ---
    abas_principais = ["📊 DASHBOARD GERAL"]
    if user_role in ["ADM", "GERENTE"]:
        abas_principais.append("⚙️ GESTÃO")
    abas_principais.append("🚀 OPERAÇÃO PQI")

    tab_dash_geral, *tab_outras = st.tabs(abas_principais)

    # --- 1. ABA DASHBOARD GERAL (RESUMO PREMIUM) ---
    with tab_dash_geral:
        st.subheader("📈 Visão Consolidada de Esforço")
        projs = st.session_state.db_pqi
        if projs:
            m1, m2, m3, m4 = st.columns(4)
            total_acoes = sum(len(p.get('notas', [])) for p in projs)
            ativos = len([p for p in projs if p.get('status') == 'Ativo'])
            
            with m1: st.markdown(f'<div class="metric-card"><div class="metric-label">Projetos Ativos</div><div class="metric-value">{ativos}</div></div>', unsafe_allow_html=True)
            with m2: st.markdown(f'<div class="metric-card"><div class="metric-label">Ações Registradas</div><div class="metric-value">{total_acoes}</div></div>', unsafe_allow_html=True)
            
            # Gráfico de esforço por projeto
            df_esforco = pd.DataFrame([{"Projeto": p['titulo'], "Esforço": len(p.get('notas', []))} for p in projs])
            st.bar_chart(df_esforco.set_index("Projeto"))
        else:
            st.info("Nenhum dado disponível para o painel.")

    # --- 2. ABA GESTÃO (APENAS ADM/GERENTE) ---
    idx_tab_op = 0
    if user_role in ["ADM", "GERENTE"]:
        tab_gestao = tab_outras[0]
        idx_tab_op = 1
        with tab_gestao:
            st.subheader("⚙️ Painel Administrativo")
            col_g1, col_g2 = st.columns([2,1])
            with col_g1:
                if st.button("➕ CRIAR NOVO PROJETO", use_container_width=True, type="primary"):
                    novo = {"titulo": f"Novo Processo {len(projs)+1}", "fase": 1, "status": "Ativo", "notas": [], "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, "lembretes": [], "pastas_virtuais": {}, "motivos_custom": []}
                    st.session_state.db_pqi.append(novo); db.salvar_projetos(st.session_state.db_pqi); st.rerun()
            
            st.divider()
            for i, p in enumerate(st.session_state.db_pqi):
                with st.expander(f"Configurações: {p['titulo']}"):
                    p['titulo'] = st.text_input("Editar Nome", p['titulo'], key=f"edit_tit_{i}")
                    p['status'] = st.selectbox("Alterar Status", ["Ativo", "Concluído", "Pausado"], index=["Ativo", "Concluído", "Pausado"].index(p.get('status', 'Ativo')), key=f"edit_st_{i}")
                    if st.button(f"🗑️ EXCLUIR DEFINITIVAMENTE: {p['titulo']}", key=f"del_p_{i}"):
                        st.session_state.db_pqi.remove(p); db.salvar_projetos(st.session_state.db_pqi); st.rerun()

    # --- 3. ABA OPERAÇÃO PQI (CÓDIGO ORIGINAL INTEGRAL COM AJUSTES) ---
    tab_operacao = tab_outras[idx_tab_op]
    with tab_operacao:
        c_t1, c_t2 = st.columns([1, 2])
        with c_t1:
            status_filtro = st.radio("Status para trabalho:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
            status_map = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
        
        projs_f = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == status_map[status_filtro]]
        
        with c_t2:
            if projs_f:
                escolha = st.selectbox("Selecione o Projeto para operar:", [p['titulo'] for p in projs_f])
                projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
            else:
                projeto = None

        if projeto:
            # RÉGUA DE NAVEGAÇÃO
            cols_r = st.columns(8)
            for i, etapa in enumerate(ROADMAP):
                n, cl, txt = i + 1, "ponto-regua", str(i+1)
                if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                elif n == projeto['fase']: cl += " ponto-atual"
                with cols_r[i]: st.markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

            tab_ex, tab_dos, tab_kpi = st.tabs(["🚀 Execução Diária", "📂 Dossiê & Pastas", "📊 Esforço do Produto"])

            with tab_ex:
                col_e1, col_e2 = st.columns([2, 1])
                with col_e1:
                    st.subheader(f"📍 Fase {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                    # Listagem de notas (Original)
                    for n in [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]:
                        with st.expander(f"📝 {n['motivo']} - {n.get('setor', 'GERAL')} ({n['data']})"):
                            st.write(n['texto'])
                            if n.get('arquivo_local') and os.path.exists(n['arquivo_local']):
                                with open(n['arquivo_local'], "rb") as f: st.download_button("📥 Baixar", f, key=f"dl_{n['data']}_{n['motivo']}")

                    st.divider()
                    with st.popover("➕ Adicionar Registro"):
                        sel_mot = st.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                        setor = st.text_input("Setor").upper()
                        desc = st.text_area("Descrição")
                        arq = st.file_uploader("Anexo")
                        usa_lemb = st.checkbox("⏰ Lembrete?")
                        if st.button("Gravar no Banco"):
                            caminho = None
                            if arq:
                                caminho = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{arq.name}")
                                with open(caminho, "wb") as f: f.write(arq.getbuffer())
                            projeto['notas'].append({"motivo": sel_mot, "setor": setor, "texto": desc, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase'], "arquivo_local": caminho})
                            db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                with col_e2:
                    st.markdown("#### 🕹️ Controle")
                    if st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                        if projeto['fase'] < 8: projeto['fase'] += 1; db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                    
                    st.markdown("#### ⏰ Lembretes Ativos")
                    for l in projeto.get('lembretes', []):
                        st.warning(f"{l['data_hora']}: {l['texto']}")

            with tab_dos:
                # NOVO DOSSIÊ PREMIUM COM MULTI-ARQUIVOS, RENOMEAR E DELETAR
                sub_p1, sub_p2 = st.tabs(["📁 Pastas Virtuais", "📜 Histórico Completo"])
                with sub_p1:
                    with st.popover("➕ Nova Pasta"):
                        nome_np = st.text_input("Nome da Pasta")
                        if st.button("Criar"):
                            projeto.setdefault('pastas_virtuais', {})[nome_np] = []
                            db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                    for p_nome in list(projeto.get('pastas_virtuais', {}).keys()):
                        with st.expander(f"📁 {p_nome}"):
                            # Opções da Pasta
                            c_p1, c_p2 = st.columns(2)
                            novo_nome = c_p1.text_input("Renomear Pasta", p_nome, key=f"ren_{p_nome}")
                            if novo_nome != p_nome:
                                projeto['pastas_virtuais'][novo_nome] = projeto['pastas_virtuais'].pop(p_nome)
                                db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                            
                            if c_p2.button("🗑️ Deletar Pasta", key=f"del_p_{p_nome}"):
                                del projeto['pastas_virtuais'][p_nome]
                                db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                            
                            st.divider()
                            # Multi-Anexos por Pasta
                            multi_arqs = st.file_uploader("Adicionar arquivos à pasta", accept_multiple_files=True, key=f"multi_{p_nome}")
                            if st.button("Confirmar Upload", key=f"btn_up_{p_nome}"):
                                for a in multi_arqs:
                                    caminho = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{a.name}")
                                    with open(caminho, "wb") as f: f.write(a.getbuffer())
                                    projeto['pastas_virtuais'][p_nome].append({"nome": a.name, "caminho": caminho, "data": datetime.now().strftime("%d/%m/%Y")})
                                db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                            
                            for doc in projeto['pastas_virtuais'][p_nome]:
                                col_d1, col_d2 = st.columns([3, 1])
                                col_d1.write(f"📄 {doc['nome']}")
                                if os.path.exists(doc['caminho']):
                                    with open(doc['caminho'], "rb") as f:
                                        col_d2.download_button("📥", f, key=f"dl_{doc['caminho']}", file_name=doc['nome'])

                with sub_p2:
                    df_h = pd.DataFrame(projeto.get('notas', []))
                    if not df_h.empty:
                        st.dataframe(df_h, use_container_width=True)
                    else: st.info("Sem histórico.")

            with tab_kpi:
                st.subheader("📊 Distribuição de Esforço")
                df_k = pd.DataFrame(projeto.get('notas', []))
                if not df_k.empty:
                    st.bar_chart(df_k['motivo'].value_counts())
                else: st.info("Sem registros para gerar gráficos.")
