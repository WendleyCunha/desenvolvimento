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
        .metric-card { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #f0f0f0; text-align: center; }
        .metric-value { font-size: 28px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 12px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
        .ponto-regua { width: 35px; height: 35px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; }
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 10px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 10px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 30px; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO E PERSISTÊNCIA
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    def salvar_seguro():
        try:
            db.salvar_projetos(st.session_state.db_pqi)
        except:
            st.error("Erro ao salvar no banco. Tente novamente.")

    # --- ABAS MESTRAS NO TOPO ---
    abas_topo = ["📊 DASHBOARD GERAL"]
    if user_role in ["ADM", "GERENTE"]:
        abas_topo.append("⚙️ GESTÃO")
    abas_topo.append("🚀 OPERAÇÃO PQI")

    tab_dash, *tab_outras = st.tabs(abas_topo)

    # --- 1. DASHBOARD GERAL (VISÃO PREMIUM) ---
    with tab_dash:
        st.subheader("📈 Resumo Executivo do Portfólio")
        projs = st.session_state.db_pqi
        if projs:
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Projetos</div><div class="metric-value">{len(projs)}</div></div>', unsafe_allow_html=True)
            with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Ações</div><div class="metric-value">{sum(len(p.get("notas", [])) for p in projs)}</div></div>', unsafe_allow_html=True)
            with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">Ativos</div><div class="metric-value">{len([p for p in projs if p.get("status")=="Ativo"])}</div></div>', unsafe_allow_html=True)
            with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">Lembretes</div><div class="metric-value">{sum(len(p.get("lembretes", [])) for p in projs)}</div></div>', unsafe_allow_html=True)
            
            st.write("---")
            df_g = pd.DataFrame([{"Projeto": p['titulo'], "Esforço": len(p.get('notas', []))} for p in projs])
            st.bar_chart(df_g.set_index("Projeto"))

    # --- 2. ABA GESTÃO (CONFIGURAÇÕES) ---
    idx_op = 0
    if user_role in ["ADM", "GERENTE"]:
        idx_op = 1
        with tab_outras[0]:
            st.subheader("⚙️ Gestão de Projetos")
            if st.button("➕ CRIAR NOVO PROJETO", type="primary", use_container_width=True):
                novo = {"titulo": f"Novo Projeto {len(projs)+1}", "fase": 1, "status": "Ativo", "notas": [], "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, "lembretes": [], "pastas_virtuais": {}, "motivos_custom": []}
                st.session_state.db_pqi.append(novo); salvar_seguro(); st.rerun()
            
            for i, p in enumerate(st.session_state.db_pqi):
                with st.expander(f"Configurar: {p['titulo']}"):
                    p['titulo'] = st.text_input("Nome", p['titulo'], key=f"t_{i}")
                    p['status'] = st.selectbox("Status", ["Ativo", "Concluído", "Pausado"], index=["Ativo", "Concluído", "Pausado"].index(p.get('status','Ativo')), key=f"s_{i}")
                    if st.button(f"🗑️ Deletar {p['titulo']}", key=f"del_{i}"):
                        st.session_state.db_pqi.remove(p); salvar_seguro(); st.rerun()

    # --- 3. OPERAÇÃO PQI (CÓDIGO PRINCIPAL) ---
    with tab_outras[idx_op]:
        c_f1, c_f2 = st.columns([1, 2])
        st_sel = c_f1.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
        s_map = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
        
        p_list = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == s_map[st_sel]]
        
        if p_list:
            escolha = c_f2.selectbox("Projeto:", [p['titulo'] for p in p_list])
            projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
        else: projeto = None

        if projeto:
            # RÉGUA
            cols_r = st.columns(8)
            for i, etapa in enumerate(ROADMAP):
                n, cl, txt = i+1, "ponto-regua", str(i+1)
                if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                elif n == projeto['fase']: cl += " ponto-atual"
                cols_r[i].markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

            t_ex, t_dos, t_kpi = st.tabs(["🚀 Execução", "📂 Dossiê Premium", "📊 Esforço"])

            with t_ex:
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.subheader(f"📍 Fase {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                    for n in [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]:
                        with st.expander(f"📝 {n['motivo']} ({n['data']})"):
                            st.write(n['texto'])
                    
                    st.divider()
                    with st.popover("➕ Novo Registro"):
                        sel_mot = st.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                        desc = st.text_area("Descrição")
                        
                        st.write("**⏰ Agendar Lembrete?**")
                        col_l1, col_l2 = st.columns(2)
                        d_l = col_l1.date_input("Data", value=None)
                        h_l = col_l2.time_input("Hora", value=None)

                        if st.button("Gravar Registro"):
                            txt_l = ""
                            if d_l and h_l:
                                txt_l = f"{d_l.strftime('%d/%m/%Y')} {h_l.strftime('%H:%M')}"
                                projeto.setdefault('lembretes', []).append({"data_hora": txt_l, "texto": f"{projeto['titulo']}: {sel_mot}"})
                            
                            projeto['notas'].append({"motivo": sel_mot, "texto": desc, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase']})
                            salvar_seguro(); st.rerun()

                with c2:
                    st.markdown("#### 🕹️ Fluxo de Trabalho")
                    if st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                        if projeto['fase'] < 8: projeto['fase'] += 1; salvar_seguro(); st.rerun()
                    if st.button("⏪ RECUAR ETAPA", use_container_width=True):
                        if projeto['fase'] > 1: projeto['fase'] -= 1; salvar_seguro(); st.rerun()
                    
                    st.markdown("#### ⏰ Lembretes Ativos")
                    for idx, l in enumerate(projeto.get('lembretes', [])):
                        col_lemb_txt, col_lemb_btn = st.columns([3, 1])
                        col_lemb_txt.warning(f"**{l['data_hora']}**\n{l['texto']}")
                        if col_lemb_btn.button("✅", key=f"done_{idx}"):
                            projeto['lembretes'].pop(idx); salvar_seguro(); st.rerun()

            with t_dos:
                # DOSSIÊ PREMIUM
                sub1, sub2 = st.tabs(["📁 Gerenciar Pastas", "📜 Histórico"])
                with sub1:
                    with st.popover("➕ Nova Pasta"):
                        nome_p = st.text_input("Nome")
                        if st.button("Criar"):
                            projeto.setdefault('pastas_virtuais', {})[nome_p] = []
                            salvar_seguro(); st.rerun()
                    
                    pastas = projeto.get('pastas_virtuais', {})
                    for p_nome in list(pastas.keys()):
                        with st.expander(f"📁 {p_nome}"):
                            col_p1, col_p2 = st.columns([3, 1])
                            novo_n = col_p1.text_input("Renomear", p_nome, key=f"r_{p_nome}")
                            if novo_n != p_nome:
                                pastas[novo_n] = pastas.pop(p_nome); salvar_seguro(); st.rerun()
                            if col_p2.button("🗑️", key=f"d_{p_nome}"):
                                del pastas[p_nome]; salvar_seguro(); st.rerun()
                            
                            up = st.file_uploader("Arquivos", accept_multiple_files=True, key=f"u_{p_nome}")
                            if st.button("Salvar Arquivos", key=f"b_{p_nome}"):
                                for a in up:
                                    path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{a.name}")
                                    with open(path, "wb") as f: f.write(a.getbuffer())
                                    pastas[p_nome].append({"nome": a.name, "path": path, "data": datetime.now().strftime("%d/%m/%Y")})
                                salvar_seguro(); st.rerun()
                            for d in pastas[p_nome]:
                                st.caption(f"📄 {d['nome']} ({d['data']})")

                with sub2:
                    st.dataframe(pd.DataFrame(projeto.get('notas', [])), use_container_width=True)

            with t_kpi:
                df_k = pd.DataFrame(projeto.get('notas', []))
                if not df_k.empty:
                    st.bar_chart(df_k['motivo'].value_counts())
                else: st.info("Sem dados.")
