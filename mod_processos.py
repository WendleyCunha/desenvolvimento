import streamlit as st
import pandas as pd
from datetime import datetime, date
import os
import io
import plotly.express as px
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
    # 1. ESTILO CSS (Ajustado para Professional Up)
    st.markdown("""
    <style>
        .ponto-regua { width: 38px; height: 38px; border-radius: 50%; background: #f1f5f9; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8; margin: 0 auto; border: 2px solid #e2e8f0; }
        .ponto-check { background: #10b981 !important; color: white !important; border-color: #10b981 !important; }
        .ponto-atual { background: #002366 !important; color: white !important; border-color: #002366 !important; box-shadow: 0 0 10px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 10px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 35px; line-height: 1.1; }
        .roi-box { background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1px solid #bbf7d0; padding: 15px; border-radius: 10px; color: #166534; text-align: center; }
        .card-lembrete { padding: 10px; border-radius: 8px; margin-bottom: 8px; border-left: 5px solid #ccc; background: #f8fafc; font-size: 13px; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO DE DADOS
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- NOVO: PAINEL DE GESTÃO GERAL (VISÃO EXECUTIVA) ---
    st.markdown("### 📊 Painel de Gestão Estratégica")
    with st.expander("📺 Visualizar Status Global de Processos", expanded=False):
        if st.session_state.db_pqi:
            df_geral = pd.DataFrame(st.session_state.db_pqi)
            c1, c2, c3 = st.columns(3)
            c1.metric("Projetos Totais", len(df_geral))
            c2.metric("Ativos 🚀", len(df_geral[df_geral['status'] == 'Ativo']))
            c3.metric("Concluídos ✅", len(df_geral[df_geral['status'] == 'Concluído']))
            
            col_g1, col_g2 = st.columns(2)
            fig_fase = px.bar(df_geral, x="titulo", y="fase", title="Estágio por Projeto", color="fase", color_continuous_scale="Blues")
            col_g1.plotly_chart(fig_fase, use_container_width=True)
            
            fig_status = px.pie(df_geral, names="status", title="Distribuição de Status", hole=0.4)
            col_g2.plotly_chart(fig_status, use_container_width=True)
        else:
            st.info("Nenhum dado para o painel geral.")

    st.divider()

    # --- FILTROS NO TOPO ---
    c_t1, c_t2, c_t3 = st.columns([1, 2, 1])
    with c_t1:
        status_filtro = st.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
        status_map = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
    
    projs_f = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == status_map[status_filtro]]
    
    projeto = None
    with c_t2:
        if projs_f:
            escolha = st.selectbox("Selecione o Projeto PQI:", [p['titulo'] for p in projs_f])
            projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
        else:
            st.warning("Nenhum projeto neste status.")

    with c_t3:
        if user_role in ["ADM", "GERENTE"]:
            if st.button("➕ NOVO PROJETO", use_container_width=True, type="primary"):
                novo = {
                    "titulo": f"Novo Processo {len(st.session_state.db_pqi)+1}", 
                    "fase": 1, "status": "Ativo", "notas": [], 
                    "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, 
                    "lembretes": [], "pastas_virtuais": {}, "motivos_custom": [],
                    "analise_mercado": "", "custo_atual": 0.0, "custo_estimado": 0.0
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
            if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
            elif n == projeto['fase']: cl += " ponto-atual"
            with cols_r[i]:
                st.markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

        # 4. TABS
        tab_ex, tab_lem, tab_dos, tab_kpi, tab_merc, tab_cfg = st.tabs([
            "🚀 Execução", "📅 Lembretes", "📂 Dossiê", "📊 KPIs", "🔍 Mercado & ROI", "⚙️ Gestão"
        ])

        with tab_ex:
            c1, c2 = st.columns([2, 1])
            with c1:
                st.subheader(f"📍 Fase {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                notas_fase = [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]
                if not notas_fase:
                    st.info("Sem registros nesta etapa.")
                else:
                    for idx, n in enumerate(reversed(notas_fase)):
                        with st.expander(f"📝 {n['motivo']} - {n.get('setor', 'GERAL')} ({n['data']})"):
                            st.write(n['texto'])
                            if n.get('arquivo_local') and os.path.exists(n['arquivo_local']):
                                with open(n['arquivo_local'], "rb") as f:
                                    st.download_button("📥 Baixar Anexo", f, key=f"dl_{projeto['titulo']}_{idx}")
                            if st.button("🗑️ Excluir", key=f"del_nota_{idx}"):
                                projeto['notas'].remove(n)
                                db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                st.divider()
                with st.popover("➕ Adicionar Novo Registro"):
                    sel_mot = st.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                    setor = st.text_input("Setor/Responsável").upper()
                    desc = st.text_area("O que foi feito?")
                    arq = st.file_uploader("Anexar Documento")
                    if st.button("Gravar no Banco de Dados"):
                        caminho_anexo = None
                        if arq:
                            caminho_anexo = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{arq.name}")
                            with open(caminho_anexo, "wb") as f: f.write(arq.getbuffer())
                        nova_nota = {
                            "motivo": sel_mot, "setor": setor, "texto": desc,
                            "data": datetime.now().strftime("%d/%m/%Y"),
                            "fase_origem": projeto['fase'], "arquivo_local": caminho_anexo,
                            "visivel_dash": sel_mot != "Anotação Interna (Sem Dash)"
                        }
                        projeto.setdefault('notas', []).append(nova_nota)
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

            with c2:
                st.markdown("#### 🕹️ Fluxo")
                if user_role in ["ADM", "GERENTE"]:
                    if projeto['fase'] < 8 and st.button("▶️ AVANÇAR", use_container_width=True, type="primary"):
                        projeto['fase'] += 1
                        projeto['historico'][str(projeto['fase'])] = datetime.now().strftime("%d/%m/%Y")
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                    if projeto['fase'] > 1 and st.button("⏪ RECUAR", use_container_width=True):
                        projeto['fase'] -= 1
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

        with tab_lem:
            st.subheader("📅 Gestão de Lembretes do Projeto")
            col_l1, col_l2 = st.columns([1, 2])
            with col_l1:
                with st.form("novo_lembrete", clear_on_submit=True):
                    l_desc = st.text_input("O que precisa ser feito?")
                    l_data = st.date_input("Para quando?", min_value=date.today())
                    if st.form_submit_button("Agendar Lembrete"):
                        projeto.setdefault('lembretes', []).append({
                            "texto": l_desc, "data": l_data.strftime("%d/%m/%Y"), "status": "Pendente"
                        })
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()
            with col_l2:
                for idx, lem in enumerate(projeto.get('lembretes', [])):
                    d_obj = datetime.strptime(lem['data'], "%d/%m/%Y").date()
                    cor = "#ef4444" if d_obj < date.today() else ("#facc15" if d_obj == date.today() else "#3b82f6")
                    st.markdown(f'<div class="card-lembrete" style="border-left-color: {cor}"><b>{lem["data"]}</b>: {lem["texto"]}</div>', unsafe_allow_html=True)
                    if st.button("✅ Concluir", key=f"lem_{idx}"):
                        projeto['lembretes'].pop(idx)
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

        with tab_dos:
            st.subheader("📜 Dossiê de Esforço")
            df_dossie = pd.DataFrame(projeto.get('notas', []))
            if not df_dossie.empty:
                st.dataframe(df_dossie[['data', 'fase_origem', 'motivo', 'setor', 'texto']], use_container_width=True)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_dossie.to_excel(writer, index=False, sheet_name='Dossie')
                st.download_button("📥 Baixar Excel", output.getvalue(), f"Dossie_{projeto['titulo']}.xlsx")

        with tab_merc:
            st.subheader("🔍 Mercado e ROI")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.markdown("### 💰 ROI")
                c_atual = st.number_input("Custo Mensal Atual (R$)", value=float(projeto.get('custo_atual', 0)))
                c_estimado = st.number_input("Custo da Solução Sugerida (R$)", value=float(projeto.get('custo_estimado', 0)))
                projeto['custo_atual'], projeto['custo_estimado'] = c_atual, c_estimado
                st.markdown(f'<div class="roi-box"><b>Potencial de Economia:</b> R$ {c_atual - c_estimado:,.2f} / mês</div>', unsafe_allow_html=True)
            with col_m2:
                st.markdown("### 🏢 Benchmarking")
                analise = st.text_area("Análise de Fornecedores", value=projeto.get('analise_mercado', ""), height=180)
                projeto['analise_mercado'] = analise
            if st.button("💾 Salvar Estudo"):
                db.salvar_projetos(st.session_state.db_pqi); st.success("Salvo!")

        with tab_kpi:
            st.subheader("📊 Métricas de Esforço")
            df = pd.DataFrame(projeto.get('notas', []))
            if not df.empty:
                c1, c2 = st.columns(2)
                c1.metric("Ações Registradas", len(df))
                c2.metric("Fase Atual", f"{projeto['fase']}/8")
                fig = px.bar(df['motivo'].value_counts(), title="Volume por Motivo")
                st.plotly_chart(fig, use_container_width=True)

        with tab_cfg:
            if user_role in ["ADM", "GERENTE"]:
                projeto['titulo'] = st.text_input("Nome do Projeto", projeto['titulo'])
                projeto['status'] = st.selectbox("Status", ["Ativo", "Concluído", "Pausado"], 
                                                 index=["Ativo", "Concluído", "Pausado"].index(projeto.get('status', 'Ativo')))
                if st.button("💾 Salvar Alterações"):
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                st.divider()
                if st.button("🗑️ EXCLUIR PROJETO", type="secondary"):
                    st.session_state.db_pqi.remove(projeto)
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()
