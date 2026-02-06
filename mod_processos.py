import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
import plotly.express as px
import plotly.graph_objects as go
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
PALETA_CORES = ["#002366", "#10b981", "#f59e0b", "#ef4444", "#6366f1", "#8b5cf6"]

def exibir(user_role="OPERACIONAL"):
    # 1. ESTILO CSS (Aprimorado)
    st.markdown("""
    <style>
        .main { background-color: #f8fafc; }
        .metric-card { 
            background-color: #ffffff; padding: 20px; border-radius: 12px; 
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; 
            text-align: center; transition: transform 0.2s;
        }
        .metric-value { font-size: 28px; font-weight: 800; color: #002366; margin-bottom: 5px; }
        .metric-label { font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        
        .ponto-regua { width: 35px; height: 35px; border-radius: 50%; background: #f1f5f9; display: flex; 
                       align-items: center; justify-content: center; font-weight: bold; color: #94a3b8; 
                       margin: 0 auto; border: 2px solid #e2e8f0; }
        .ponto-check { background: #10b981 !important; color: white !important; border-color: #10b981 !important; }
        .ponto-atual { background: #002366 !important; color: white !important; border-color: #002366 !important; box-shadow: 0 0 10px rgba(0, 35, 102, 0.3); }
        .label-regua { font-size: 10px; text-align: center; font-weight: 700; margin-top: 8px; color: #475569; line-height: 1.2; height: 30px;}
    </style>
    """, unsafe_allow_html=True)

    # 2. INICIALIZAÇÃO DE DADOS
    if 'db_pqi' not in st.session_state:
        try: st.session_state.db_pqi = db.carregar_projetos()
        except: st.session_state.db_pqi = []

    def salvar_seguro():
        try: db.salvar_projetos(st.session_state.db_pqi)
        except Exception as e: st.error(f"Erro ao salvar: {e}")

    # --- DEFINIÇÃO DAS ABAS ---
    titulos = ["📊 DASHBOARD GERAL"]
    if user_role in ["ADM", "GERENTE"]:
        titulos.append("⚙️ GESTÃO")
    titulos.append("🚀 OPERAÇÃO PQI")

    tabs = st.tabs(titulos)
    tab_dash = tabs[0]
    
    idx_atual = 1
    tab_gestao = None
    if user_role in ["ADM", "GERENTE"]:
        tab_gestao = tabs[idx_atual]
        idx_atual += 1
    tab_operacao = tabs[idx_atual]

    # --- 1. DASHBOARD GERAL ---
    with tab_dash:
        sub_d1, sub_d2 = st.tabs(["📈 Portfólio Ativo", "✅ Projetos Entregues"])
        projs = st.session_state.db_pqi
        
        with sub_d1:
            ativos = [p for p in projs if p.get('status') != "Concluído"]
            if ativos:
                # CARDS PREMIUM
                c1, c2, c3 = st.columns(3)
                c1.markdown(f'<div class="metric-card"><div class="metric-label">Ativos</div><div class="metric-value">{len(ativos)}</div></div>', unsafe_allow_html=True)
                c2.markdown(f'<div class="metric-card"><div class="metric-label">Ações Totais</div><div class="metric-value">{sum(len(p.get("notas", [])) for p in ativos)}</div></div>', unsafe_allow_html=True)
                c3.markdown(f'<div class="metric-card"><div class="metric-label">Lembretes</div><div class="metric-value">{sum(len(p.get("lembretes", [])) for p in ativos)}</div></div>', unsafe_allow_html=True)
                
                st.write("---")
                
                # GRÁFICO PLOTLY (Interativo)
                df_at = pd.DataFrame([
                    {"Projeto": p['titulo'], "Fase": f"Etapa {p['fase']}", "Esforço (Ações)": len(p.get('notas', []))} 
                    for p in ativos
                ])
                
                fig_bar = px.bar(df_at, x="Projeto", y="Esforço (Ações)", color="Fase",
                                 title="Esforço por Projeto e Etapa Atual",
                                 color_discrete_sequence=px.colors.qualitative.Prism,
                                 text_auto=True)
                fig_bar.update_layout(plot_bgcolor="rgba(0,0,0,0)", margin=dict(t=40, b=0, l=0, r=0))
                st.plotly_chart(fig_bar, use_container_width=True)

                st.dataframe(df_at, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum projeto ativo.")

        with sub_d2:
            concluidos = [p for p in projs if p.get('status') == "Concluído"]
            if concluidos:
                df_concl = pd.DataFrame([{"Projeto": p['titulo'], "Conclusão": p.get('data_conclusao', 'Finalizado'), "Ações Realizadas": len(p.get('notas', []))} for p in concluidos])
                
                fig_pie = px.pie(df_concl, names="Projeto", values="Ações Realizadas", hole=0.4, title="Participação no Volume de Entregas")
                st.plotly_chart(fig_pie, use_container_width=True)
                st.dataframe(df_concl, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum projeto entregue.")

    # --- 2. GESTÃO ---
    if tab_gestao:
        with tab_gestao:
            st.subheader("⚙️ Gerenciamento de Projetos")
            if st.button("➕ CRIAR NOVO PROJETO PQI", type="primary", use_container_width=True):
                novo_projeto = {
                    "titulo": f"Novo Projeto {len(st.session_state.db_pqi) + 1}",
                    "fase": 1, "status": "Ativo", "notas": [], "lembretes": [],
                    "pastas_virtuais": {}, "motivos_custom": []
                }
                st.session_state.db_pqi.append(novo_projeto)
                salvar_seguro()
                st.success("Projeto criado com sucesso!")
                st.rerun()

            st.write("---")
            for i, p in enumerate(st.session_state.db_pqi):
                with st.expander(f"Configurações: {p['titulo']}"):
                    p['titulo'] = st.text_input("Nome", p['titulo'], key=f"gest_t_{i}")
                    p['status'] = st.selectbox("Status", ["Ativo", "Concluído", "Pausado"], 
                                             index=["Ativo", "Concluído", "Pausado"].index(p.get('status','Ativo')), 
                                             key=f"gest_s_{i}")
                    if st.button("🗑️ Excluir Projeto", key=f"gest_del_{i}"):
                        st.session_state.db_pqi.remove(p)
                        salvar_seguro(); st.rerun()

    # --- 3. OPERAÇÃO PQI ---
    with tab_operacao:
        st.subheader("🚀 Operação de Processos")
        projs = st.session_state.db_pqi
        
        if not projs:
            st.warning("Vá na aba GESTÃO e crie seu primeiro projeto para começar.")
        else:
            c_f1, c_f2 = st.columns([1, 2])
            status_sel = c_f1.radio("Filtrar por Status:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
            map_status = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
            
            filtrados = [p for p in projs if p.get('status', 'Ativo') == map_status[status_sel]]
            
            if not filtrados:
                st.info(f"Não há projetos com status '{map_status[status_sel]}'.")
            else:
                escolha = c_f2.selectbox("Selecione o Projeto para Trabalhar:", [p['titulo'] for p in filtrados])
                projeto = next(p for p in filtrados if p['titulo'] == escolha)

                # RÉGUA DE NAVEGAÇÃO ESTILIZADA
                st.write("")
                cols_r = st.columns(8)
                for i, etapa in enumerate(ROADMAP):
                    n, cl, txt = i+1, "ponto-regua", str(i+1)
                    if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                    elif n == projeto['fase']: cl += " ponto-atual"
                    cols_r[i].markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

                t_exec, t_dossie, t_esforco = st.tabs(["📝 Execução Diária", "📁 Dossiê & Arquivos", "📊 Análise de Esforço"])

                with t_exec:
                    col_e1, col_e2 = st.columns([2, 1])
                    with col_e1:
                        st.markdown(f"### Etapa {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                        for n in [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]:
                            with st.chat_message("user" if "Anotação" not in n['motivo'] else "assistant"):
                                st.write(f"**{n['motivo']}** - {n['data']}")
                                st.write(n['texto'])
                        
                        st.divider()
                        with st.popover("➕ Adicionar Registro"):
                            mot = st.selectbox("Assunto", MOTIVOS_PADRAO)
                            dsc = st.text_area("O que foi feito?")
                            st.write("**⏰ Agendar Lembrete?**")
                            cl1, cl2 = st.columns(2)
                            dl = cl1.date_input("Data", value=None, key=f"date_{escolha}")
                            hl = cl2.time_input("Hora", value=None, key=f"time_{escolha}")
                            
                            if st.button("Gravar no Banco", use_container_width=True):
                                if dl and hl:
                                    projeto.setdefault('lembretes', []).append({
                                        "data_hora": f"{dl.strftime('%d/%m/%Y')} {hl.strftime('%H:%M')}",
                                        "texto": f"{projeto['titulo']}: {mot}"
                                    })
                                projeto['notas'].append({
                                    "motivo": mot, "texto": dsc, 
                                    "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                    "fase_origem": projeto['fase']
                                })
                                salvar_seguro(); st.rerun()

                    with col_e2:
                        st.markdown("#### ⚙️ Controle de Fase")
                        if st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                            if projeto['fase'] < 8:
                                projeto['fase'] += 1
                                salvar_seguro(); st.rerun()
                        if st.button("⏪ RECUAR ETAPA", use_container_width=True):
                            if projeto['fase'] > 1:
                                projeto['fase'] -= 1
                                salvar_seguro(); st.rerun()
                        
                        st.markdown("---")
                        st.markdown("#### ⏰ Lembretes Deste Projeto")
                        for idx, l in enumerate(projeto.get('lembretes', [])):
                            cl_t, cl_b = st.columns([4, 1])
                            cl_t.info(f"**{l['data_hora']}**\n{l['texto']}")
                            if cl_b.button("✅", key=f"done_l_{idx}"):
                                projeto['lembretes'].pop(idx)
                                salvar_seguro(); st.rerun()

                with t_dossie:
                    sub1, sub2 = st.tabs(["📂 Pastas Virtuais", "📜 Histórico Completo"])
                    with sub1:
                        with st.popover("➕ Criar Pasta"):
                            np = st.text_input("Nome da Pasta")
                            if st.button("Salvar Pasta"):
                                projeto.setdefault('pastas_virtuais', {})[np] = []
                                salvar_seguro(); st.rerun()
                        
                        pastas = projeto.get('pastas_virtuais', {})
                        for p_nome in list(pastas.keys()):
                            with st.expander(f"📁 {p_nome}"):
                                c_p1, c_p2 = st.columns([3, 1])
                                novo_n = c_p1.text_input("Renomear", p_nome, key=f"ren_p_{p_nome}")
                                if novo_n != p_nome:
                                    pastas[novo_n] = pastas.pop(p_nome); salvar_seguro(); st.rerun()
                                if c_p2.button("🗑️", key=f"del_p_{p_nome}"):
                                    del pastas[p_nome]; salvar_seguro(); st.rerun()
                                
                                up = st.file_uploader("Anexar", accept_multiple_files=True, key=f"up_{p_nome}")
                                if st.button("Subir Arquivos", key=f"btn_{p_nome}"):
                                    for a in up:
                                        path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{a.name}")
                                        with open(path, "wb") as f: f.write(a.getbuffer())
                                        pastas[p_nome].append({"nome": a.name, "path": path, "data": datetime.now().strftime("%d/%m/%Y")})
                                    salvar_seguro(); st.rerun()
                                
                                for arq in pastas[p_nome]:
                                    st.caption(f"📄 {arq['nome']} ({arq['data']})")

                    with sub2:
                        df_hist = pd.DataFrame(projeto.get('notas', []))
                        if not df_hist.empty:
                            st.dataframe(df_hist, use_container_width=True)
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                                df_hist.to_excel(writer, index=False)
                            st.download_button("📥 Exportar Dossiê (Excel)", output.getvalue(), f"Dossie_{projeto['titulo']}.xlsx")

                with t_esforco:
                    st.markdown("#### 📊 Análise de Esforço")
                    df_k = pd.DataFrame(projeto.get('notas', []))
                    if not df_k.empty:
                        fig_esf = px.pie(df_k, names="motivo", title="Distribuição por Tipo de Ação", 
                                       color_discrete_sequence=px.colors.sequential.RdBu)
                        st.plotly_chart(fig_esf, use_container_width=True)
                        
                        fig_timeline = px.histogram(df_k, x="data", title="Intensidade de Registros no Tempo")
                        st.plotly_chart(fig_timeline, use_container_width=True)
                    else:
                        st.info("Inicie os registros para ver a análise.")
