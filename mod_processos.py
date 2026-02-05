import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import plotly.express as px  # Adicionado para os gráficos da diretoria
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
    # 1. ESTILO CSS ORIGINAL
    st.markdown("""
    <style>
        .metric-card { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #ececec; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .ponto-regua { width: 35px; height: 35px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; }
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 10px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 10px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 30px; }
        .roi-box { background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 10px; color: #166534; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO DE DADOS
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- NOVA PARTE: ABA DA DIRETORIA (VISÃO GERAL) ---
    st.markdown("## 📊 Gestão Estratégica PQI")
    tab_diretoria, tab_projetos = st.tabs(["📺 VISÃO DIRETORIA", "🛠️ GESTÃO DE PROJETOS"])

    with tab_diretoria:
        projetos_all = st.session_state.db_pqi
        if not projetos_all:
            st.info("Nenhum dado disponível para análise.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Projetos Totais", len(projetos_all))
            c2.metric("Ativos 🚀", len([p for p in projetos_all if p.get('status') == 'Ativo']))
            c3.metric("Concluídos ✅", len([p for p in projetos_all if p.get('status') == 'Concluído']))
            
            # Gráfico de Status
            df_status = pd.DataFrame([{"Status": p.get('status', 'Ativo')} for p in projetos_all])
            fig_status = px.pie(df_status, names='Status', title="Distribuição por Status", hole=0.4)
            fig_status.update_layout(height=300, margin=dict(t=30, b=0, l=0, r=0))
            
            # Gráfico de Fases
            df_fases = pd.DataFrame([{"Projeto": p['titulo'], "Fase": p['fase']} for p in projetos_all])
            fig_fases = px.bar(df_fases, x='Projeto', y='Fase', title="Estágio dos Projetos", color='Fase')
            fig_fases.update_layout(height=300)

            col_g1, col_g2 = st.columns(2)
            col_g1.plotly_chart(fig_status, use_container_width=True)
            col_g2.plotly_chart(fig_fases, use_container_width=True)

    # --- ABA DE PROJETOS (SEU CÓDIGO ORIGINAL ÍNTEGRO) ---
    with tab_projetos:
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
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()

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

            # 4. TABS ORIGINAIS
            tab_ex, tab_dos, tab_kpi, tab_merc, tab_cfg = st.tabs([
                "🚀 Execução", "📂 Dossiê", "📊 KPIs", "🔍 Mercado & ROI", "⚙️ Gestão"
            ])

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

            with tab_merc:
                st.subheader("🔍 Inteligência de Mercado e Business Case")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown("### 💰 Estimativa de ROI")
                    c_atual = st.number_input("Custo Mensal Atual (R$)", value=float(projeto.get('custo_atual', 0)))
                    c_estimado = st.number_input("Custo da Solução Sugerida (R$)", value=float(projeto.get('custo_estimado', 0)))
                    projeto['custo_atual'] = c_atual
                    projeto['custo_estimado'] = c_estimado
                    economia = c_atual - c_estimado
                    if economia > 0:
                        st.markdown(f"""<div class="roi-box"><b>Potencial de Economia:</b> R$ {economia:,.2f} / mês</div>""", unsafe_allow_html=True)
                with col_m2:
                    st.markdown("### 🏢 Benchmarking")
                    st.info("Utilize este espaço para comparar os fornecedores.")
                    analise = st.text_area("Análise de Fornecedores", value=projeto.get('analise_mercado', ""), height=200)
                    projeto['analise_mercado'] = analise
                if st.button("💾 Salvar Estudo de Mercado"):
                    db.salvar_projetos(st.session_state.db_pqi); st.success("Estudo salvo!")

            with tab_dos:
                st.subheader("📜 Histórico de Esforço")
                df_dossie = pd.DataFrame(projeto.get('notas', []))
                if not df_dossie.empty:
                    st.dataframe(df_dossie, use_container_width=True)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_dossie.to_excel(writer, index=False)
                    st.download_button("📥 Baixar Excel", output.getvalue(), f"Dossie_{projeto['titulo']}.xlsx")

            with tab_kpi:
                st.subheader("📊 Métricas")
                df = pd.DataFrame(projeto.get('notas', []))
                if not df.empty:
                    c1, c2 = st.columns(2)
                    c1.metric("Ações Registradas", len(df))
                    c2.metric("Fase Atual", f"{projeto['fase']}/8")
                    st.bar_chart(df['motivo'].value_counts())

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
