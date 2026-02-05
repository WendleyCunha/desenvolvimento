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
        .ponto-regua { width: 35px; height: 35px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; }
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 10px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 10px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 30px; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO E PERSISTÊNCIA SEGURA
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    def salvar_seguro():
        try:
            db.salvar_projetos(st.session_state.db_pqi)
        except Exception as e:
            st.error(f"Erro de Persistência: {e}")

    # --- DEFINIÇÃO DE ABAS MESTRAS (Pedido 1 e 2) ---
    titulos_tabs = ["📊 DASHBOARD GERAL"]
    if user_role in ["ADM", "GERENTE"]:
        titulos_tabs.append("⚙️ GESTÃO")
    titulos_tabs.append("🚀 OPERAÇÃO PQI")

    tab_geral, *tab_resto = st.tabs(titulos_tabs)

    # --- 1. PAINEL GERAL (Pedido 1) ---
    with tab_geral:
        st.subheader("📊 Resumo Executivo do Portfólio")
        projs = st.session_state.db_pqi
        if projs:
            c1, c2, c3 = st.columns(3)
            with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Projetos Ativos</div><div class="metric-value">{len([p for p in projs if p.get("status")=="Ativo"])}</div></div>', unsafe_allow_html=True)
            with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Total de Ações</div><div class="metric-value">{sum(len(p.get("notas", [])) for p in projs)}</div></div>', unsafe_allow_html=True)
            with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Média de Progresso</div><div class="metric-value">{int(sum(p["fase"] for p in projs)/len(projs))}/8</div></div>', unsafe_allow_html=True)
            
            df_geral = pd.DataFrame([{"Projeto": p['titulo'], "Esforço (Notas)": len(p.get('notas', []))} for p in projs])
            st.bar_chart(df_geral.set_index("Projeto"))
        else: st.info("Nenhum projeto cadastrado.")

    # --- 2. ABA GESTÃO (Pedido 2 - Ao lado do Dashboard) ---
    idx_op = 0
    if user_role in ["ADM", "GERENTE"]:
        idx_op = 1
        with tab_resto[0]:
            st.subheader("⚙️ Administração de Projetos")
            if st.button("➕ CRIAR NOVO PROJETO PQI", type="primary", use_container_width=True):
                novo = {"titulo": f"Novo Processo {len(projs)+1}", "fase": 1, "status": "Ativo", "notas": [], "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, "lembretes": [], "pastas_virtuais": {}, "motivos_custom": []}
                st.session_state.db_pqi.append(novo); salvar_seguro(); st.rerun()
            
            st.write("---")
            for i, p in enumerate(st.session_state.db_pqi):
                with st.expander(f"Configurar: {p['titulo']}"):
                    p['titulo'] = st.text_input("Editar Nome do Produto", p['titulo'], key=f"edit_t_{i}")
                    p['status'] = st.selectbox("Alterar Status", ["Ativo", "Concluído", "Pausado"], index=["Ativo", "Concluído", "Pausado"].index(p.get('status','Ativo')), key=f"edit_s_{i}")
                    if st.button(f"🗑️ Deletar {p['titulo']}", key=f"del_p_{i}"):
                        st.session_state.db_pqi.remove(p); salvar_seguro(); st.rerun()

    # --- 3. OPERAÇÃO PQI (Pedido 3, 4, 5, 6, 7) ---
    with tab_resto[idx_op]:
        c_f1, c_f2 = st.columns([1, 2])
        status_f = c_f1.radio("Filtrar:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
        s_map = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
        
        projs_f = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == s_map[status_f]]
        
        if projs_f:
            escolha = c_f2.selectbox("Selecione o Projeto:", [p['titulo'] for p in projs_f])
            projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
        else: projeto = None

        if projeto:
            # RÉGUA DE NAVEGAÇÃO
            cols_r = st.columns(8)
            for i, etapa in enumerate(ROADMAP):
                n, cl, txt = i+1, "ponto-regua", str(i+1)
                if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                elif n == projeto['fase']: cl += " ponto-atual"
                cols_r[i].markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

            t_ex, t_dos, t_kpi = st.tabs(["🚀 Execução Diária", "📂 Dossiê Premium", "📊 Painel de Esforço"])

            with t_ex:
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.subheader(f"📍 Fase {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                    # Registros originais
                    for n in [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]:
                        with st.expander(f"📝 {n['motivo']} ({n['data']})"):
                            st.write(n['texto'])
                            if n.get('arquivo_local'):
                                with open(n['arquivo_local'], "rb") as f: st.download_button("📥 Baixar", f, key=f"dl_{n['arquivo_local']}_{n['data']}")
                    
                    st.divider()
                    with st.popover("➕ Novo Registro"):
                        sel_mot = st.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                        desc = st.text_area("Descrição")
                        arq = st.file_uploader("Anexo de Registro")
                        if st.button("Gravar no Banco"):
                            path = None
                            if arq:
                                path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{arq.name}")
                                with open(path, "wb") as f: f.write(arq.getbuffer())
                            projeto['notas'].append({"motivo": sel_mot, "texto": desc, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase'], "arquivo_local": path})
                            salvar_seguro(); st.rerun()

                with c2:
                    st.markdown("#### 🕹️ Fluxo")
                    if st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                        if projeto['fase'] < 8: projeto['fase'] += 1; salvar_seguro(); st.rerun()
                    
                    # LEMBRETES (Pedido 6)
                    st.markdown("#### ⏰ Lembretes Ativos")
                    for l in projeto.get('lembretes', []):
                        st.info(f"**{l['data_hora']}**: {l['texto']}")

            with t_dos:
                # DOSSIÊ PREMIUM (Pedidos 4 e 5)
                sub1, sub2 = st.tabs(["📁 Pastas e Multi-Arquivos", "📜 Histórico Dossiê"])
                with sub1:
                    with st.popover("➕ Criar Nova Pasta"):
                        nome_p = st.text_input("Nome da Pasta")
                        if st.button("Confirmar Criação"):
                            projeto.setdefault('pastas_virtuais', {})[nome_p] = []
                            salvar_seguro(); st.rerun()
                    
                    pastas = projeto.get('pastas_virtuais', {})
                    for p_nome in list(pastas.keys()):
                        with st.expander(f"📁 PASTA: {p_nome}"):
                            # Renomear/Deletar Pasta (Pedido 4)
                            col_p1, col_p2 = st.columns([3, 1])
                            novo_n = col_p1.text_input("Renomear", p_nome, key=f"ren_{p_nome}")
                            if novo_n != p_nome:
                                pastas[novo_n] = pastas.pop(p_nome)
                                salvar_seguro(); st.rerun()
                            if col_p2.button("🗑️ Apagar Pasta", key=f"del_{p_nome}"):
                                del pastas[p_nome]; salvar_seguro(); st.rerun()
                            
                            # Multi-Arquivos (Pedido 5)
                            arqs_up = st.file_uploader("Upload Multi-arquivos", accept_multiple_files=True, key=f"up_{p_nome}")
                            if st.button("Confirmar Upload", key=f"btn_{p_nome}"):
                                for a in arqs_up:
                                    path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{a.name}")
                                    with open(path, "wb") as f: f.write(a.getbuffer())
                                    pastas[p_nome].append({"nome": a.name, "path": path, "data": datetime.now().strftime("%d/%m/%Y")})
                                salvar_seguro(); st.rerun()
                            
                            for doc in pastas[p_nome]:
                                cd1, cd2 = st.columns([4, 1])
                                cd1.caption(f"📄 {doc['nome']}")
                                if os.path.exists(doc['path']):
                                    with open(doc['path'], "rb") as f:
                                        cd2.download_button("📥", f, file_name=doc['nome'], key=f"dl_{doc['path']}")

                with sub2:
                    df_dos = pd.DataFrame(projeto.get('notas', []))
                    if not df_dos.empty:
                        st.dataframe(df_dos, use_container_width=True)
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            df_dos.to_excel(writer, index=False)
                        st.download_button("📥 Exportar Dossiê Excel", output.getvalue(), "Dossie.xlsx")

            with t_kpi:
                # Gráfico de Esforço Corrigido (Pedido 3)
                st.subheader("📊 Distribuição de Esforço por Atividade")
                df_kpi = pd.DataFrame(projeto.get('notas', []))
                if not df_kpi.empty:
                    # Gráfico de barras nativo (Resolve o erro do Plotly)
                    counts = df_kpi['motivo'].value_counts()
                    st.bar_chart(counts)
                    st.write("Ranking de Atividades:")
                    st.table(counts)
                else: st.info("Sem dados de esforço.")
