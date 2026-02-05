import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import io
import zipfile
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
        .metric-label { font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .ponto-regua { width: 35px; height: 35px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; }
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 10px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 10px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 30px; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO DE DADOS
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- FILTROS NO TOPO ---
    c_t1, c_t2, c_t3 = st.columns([1, 2, 1])
    
    with c_t1:
        status_filtro = st.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
        status_map = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
    
    projs_f = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == status_map[status_filtro]]
    
    with c_t2:
        if projs_f:
            escolha = st.selectbox("Selecione o Projeto PQI:", [p['titulo'] for p in projs_f])
            projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
        else:
            st.warning("Nenhum projeto neste status.")
            projeto = None

    with c_t3:
        if user_role in ["ADM", "GERENTE"]:
            if st.button("➕ NOVO PROJETO", use_container_width=True, type="primary"):
                novo = {
                    "titulo": f"Novo Processo {len(st.session_state.db_pqi)+1}", 
                    "fase": 1, "status": "Ativo", "notas": [], 
                    "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, 
                    "lembretes": [], "pastas_virtuais": {}, "motivos_custom": []
                }
                st.session_state.db_pqi.append(novo)
                db.salvar_projetos(st.session_state.db_pqi)
                st.rerun()

    if projeto:
        # 3. RÉGUA DE NAVEGAÇÃO
        st.write("")
        cols_r = st.columns(8)
        for i, etapa in enumerate(ROADMAP):
            n = i + 1
            cl = "ponto-regua"
            txt = str(n)
            if n < projeto['fase']: 
                cl += " ponto-check"; txt = "✔"
            elif n == projeto['fase']: 
                cl += " ponto-atual"
            
            with cols_r[i]:
                st.markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

        # 4. TABS
        tab_ex, tab_dos, tab_kpi, tab_cfg = st.tabs(["🚀 Execução", "📂 Dossiê / Arquivos", "📊 Painel de Esforço", "⚙️ Gestão"])

        with tab_ex:
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader(f"📍 Fase {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                notas_fase = [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]
                
                if not notas_fase:
                    st.info("Sem registros nesta etapa.")
                else:
                    for idx, n in enumerate(notas_fase):
                        with st.expander(f"📝 {n['motivo']} - {n.get('setor', 'GERAL')} ({n['data']})"):
                            st.write(n['texto'])
                            if n.get('arquivo_local') and os.path.exists(n['arquivo_local']):
                                with open(n['arquivo_local'], "rb") as f:
                                    st.download_button("📥 Baixar Anexo", f, key=f"dl_{projeto['titulo']}_{idx}")
                            if st.button("🗑️ Excluir", key=f"del_nota_{idx}_{n['data']}"):
                                projeto['notas'].remove(n)
                                db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                st.divider()
                with st.popover("➕ Adicionar Novo Registro"):
                    # Lista de motivos dinâmica
                    opcoes_assunto = MOTIVOS_PADRAO + projeto.get('motivos_custom', [])
                    sel_mot = st.selectbox("Assunto", opcoes_assunto)
                    setor = st.text_input("Setor/Responsável").upper()
                    desc = st.text_area("O que foi feito?")
                    arq = st.file_uploader("Anexar Documento")
                    
                    usa_lemb = st.checkbox("⏰ Agendar Lembrete?")
                    d_l, h_l = None, None
                    if usa_lemb:
                        col_l1, col_l2 = st.columns(2)
                        d_l = col_l1.date_input("Data")
                        h_l = col_l2.time_input("Hora")

                    if st.button("Gravar no Banco de Dados"):
                        caminho_anexo = None
                        if arq:
                            caminho_anexo = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{arq.name}")
                            with open(caminho_anexo, "wb") as f: f.write(arq.getbuffer())
                        
                        txt_lembrete = datetime.combine(d_l, h_l).strftime("%d/%m/%Y %H:%M") if usa_lemb else ""

                        nova_nota = {
                            "motivo": sel_mot, "setor": setor, "texto": desc,
                            "data": datetime.now().strftime("%d/%m/%Y"),
                            "fase_origem": projeto['fase'], "arquivo_local": caminho_anexo,
                            "visivel_dash": sel_mot != "Anotação Interna (Sem Dash)",
                            "lembrete_agendado": txt_lembrete
                        }
                        projeto.setdefault('notas', []).append(nova_nota)
                        if usa_lemb:
                            projeto.setdefault('lembretes', []).append({"data_hora": txt_lembrete, "texto": f"{projeto['titulo']}: {sel_mot}"})
                        
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

            with c2:
                st.markdown("#### 🕹️ Fluxo de Trabalho")
                if user_role in ["ADM", "GERENTE", "SUPERVISÃO"]:
                    if projeto['fase'] < 8:
                        if st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                            projeto['fase'] += 1
                            projeto['historico'][str(projeto['fase'])] = datetime.now().strftime("%d/%m/%Y")
                            db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                    if projeto['fase'] > 1:
                        if st.button("⏪ RECUAR ETAPA", use_container_width=True):
                            projeto['fase'] -= 1
                            db.salvar_projetos(st.session_state.db_pqi); st.rerun()

        with tab_dos:
            sub1, sub2 = st.tabs(["📁 Pastas Organizadoras", "📜 Histórico Completo (Dossiê)"])
            with sub1:
                with st.popover("➕ Criar Pasta"):
                    np = st.text_input("Nome da Pasta")
                    if st.button("Confirmar"):
                        projeto.setdefault('pastas_virtuais', {})[np] = []
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                
                for p_nome, arqs in projeto.get('pastas_virtuais', {}).items():
                    with st.expander(f"📁 {p_nome}"):
                        for a in arqs: st.write(f"📄 {a['nome']} ({a['data']})")
                        up = st.file_uploader("Subir para esta pasta", key=f"up_{p_nome}")
                        if up: pass 

            with sub2:
                st.subheader("📜 Dossiê de Esforço do Projeto")
                todas_notas = projeto.get('notas', [])
                if todas_notas:
                    df_dossie = pd.DataFrame(todas_notas)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_dossie.to_excel(writer, index=False)
                    st.download_button("📥 EXPORTAR DOSSIÊ (EXCEL)", output.getvalue(), f"Dossie_{projeto['titulo']}.xlsx", type="primary")
                    st.dataframe(df_dossie, use_container_width=True)

        with tab_kpi:
            st.subheader("📊 Métricas e Distribuição de Esforço")
            df = pd.DataFrame(projeto.get('notas', []))
            
            if not df.empty:
                c1, c2, c3 = st.columns(3)
                with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">Total de Ações</div><div class="metric-value">{len(df)}</div></div>', unsafe_allow_html=True)
                with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">Etapa Atual</div><div class="metric-value">{projeto["fase"]}/8</div></div>', unsafe_allow_html=True)
                with c3:
                    top = df['motivo'].mode()[0] if not df.empty else "-"
                    st.markdown(f'<div class="metric-card"><div class="metric-label">Foco Principal</div><div class="metric-value" style="font-size:16px">{top}</div></div>', unsafe_allow_html=True)
                
                st.write("---")
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("**📈 Volume por Assunto (Barras)**")
                    st.bar_chart(df['motivo'].value_counts())
                
                with col_g2:
                    st.markdown("**🍕 Distribuição de Esforço (Pizza)**")
                    # Gráfico de Pizza nativo via Streamlit (utilizando dataframe processado)
                    pizza_data = df['motivo'].value_counts().reset_index()
                    st.write("Percentual de cada atividade no projeto:")
                    st.dataframe(pizza_data.rename(columns={'count': 'Qtd', 'motivo': 'Assunto'}), use_container_width=True)

                st.markdown("**📋 Ranking Detalhado de Assuntos**")
                ranking = df.groupby('motivo').size().sort_values(ascending=False).reset_index(name='Total de Registros')
                st.table(ranking)
            else:
                st.info("Inicie os registros para visualizar os gráficos de esforço.")

        with tab_cfg:
            if user_role in ["ADM", "GERENTE"]:
                st.subheader("⚙️ Configurações do Projeto")
                projeto['titulo'] = st.text_input("Nome do Projeto", projeto['titulo'])
                projeto['status'] = st.selectbox("Status", ["Ativo", "Concluído", "Pausado"], 
                                                index=["Ativo", "Concluído", "Pausado"].index(projeto['status']))
                
                st.write("---")
                st.subheader("➕ Gerenciar Assuntos")
                novo_assunto = st.text_input("Adicionar novo assunto à lista:")
                if st.button("Adicionar Assunto"):
                    if novo_assunto and novo_assunto not in projeto.get('motivos_custom', []):
                        projeto.setdefault('motivos_custom', []).append(novo_assunto)
                        db.salvar_projetos(st.session_state.db_pqi); st.success("Assunto adicionado!"); st.rerun()
                
                if projeto.get('motivos_custom'):
                    st.write("Assuntos personalizados atuais:")
                    for m in projeto['motivos_custom']:
                        st.caption(f"- {m}")
                
                st.write("---")
                if st.button("💾 Salvar Tudo"):
                    db.salvar_projetos(st.session_state.db_pqi); st.success("Salvo!"); st.rerun()
                
                if st.button("🗑️ EXCLUIR PROJETO DEFINITIVAMENTE"):
                    st.session_state.db_pqi.remove(projeto)
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()
