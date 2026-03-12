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

# Mantendo sua lista original e adicionando os departamentos para o novo dashboard
MOTIVOS_PADRAO = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna (Sem Dash)"]
DEPARTAMENTOS = ["Compras", "Logística", "TI", "Financeiro", "RH", "Operações", "Comercial", "Diretoria"]

def exibir(user_role="OPERACIONAL"):
    # 1. ESTILO CSS (Preservado)
    st.markdown("""
    <style>
        .metric-card { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #ececec; text-align: center; }
        .metric-value { font-size: 24px; font-weight: 800; color: #002366; }
        .metric-label { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .ponto-regua { width: 30px; height: 30px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; font-size: 12px;}
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 8px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 9px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 25px; line-height: 1; }
    </style>
    """, unsafe_allow_html=True)

    # 2. INICIALIZAÇÃO DE DADOS (Preservado + Nova estrutura para Situações Diárias)
    if 'db_pqi' not in st.session_state:
        try:
            st.session_state.db_pqi = db.carregar_projetos()
        except:
            st.session_state.db_pqi = []

    if 'situacoes_diarias' not in st.session_state:
        # Tenta carregar situações salvas ou inicia lista vazia
        st.session_state.situacoes_diarias = []

    def salvar_seguro():
        try:
            db.salvar_projetos(st.session_state.db_pqi)
            # Aqui você pode adicionar a persistência para situações_diarias no seu database.py se desejar
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

    # --- DEFINIÇÃO DAS ABAS ---
    titulos = ["📊 DASHBOARD GERAL"]
    if user_role in ["ADM", "GERENTE"]:
        titulos.append("⚙️ GESTÃO")
    titulos.append("🚀 OPERAÇÃO PQI")

    tabs = st.tabs(titulos)
    
    tab_dash = tabs[0]
    if user_role in ["ADM", "GERENTE"]:
        tab_gestao = tabs[1]
        tab_operacao = tabs[2]
    else:
        tab_gestao = None
        tab_operacao = tabs[1]

   # --- 1. DASHBOARD GERAL ---
    with tab_dash:
        import plotly.express as px 
        
        sub_d1, sub_d2 = st.tabs(["📈 Portfólio Ativo", "✅ Projetos Entregues"])
        projs = st.session_state.db_pqi
        
        with sub_d1:
            ativos = [p for p in projs if p.get('status') != "Concluído"]
            if ativos:
                c1, c2, c3 = st.columns(3)
                c1.markdown(f'<div class="metric-card"><div class="metric-label">Projetos Ativos</div><div class="metric-value">{len(ativos)}</div></div>', unsafe_allow_html=True)
                c2.markdown(f'<div class="metric-card"><div class="metric-label">Total de Ações</div><div class="metric-value">{sum(len(p.get("notas", [])) for p in ativos)}</div></div>', unsafe_allow_html=True)
                
                todas_notas = []
                for p in ativos:
                    for n in p.get('notas', []):
                        todas_notas.append(n)
                df_notas = pd.DataFrame(todas_notas)
                
                gargalo = "N/A"
                if not df_notas.empty and 'depto' in df_notas.columns:
                    gargalo = df_notas['depto'].mode()[0] if not df_notas['depto'].isnull().all() else "N/A"
                c3.markdown(f'<div class="metric-card"><div class="metric-label">Gargalo (Depto)</div><div class="metric-value" style="font-size:18px">{gargalo}</div></div>', unsafe_allow_html=True)
                
                st.write("") 

                df_at = pd.DataFrame([{"Projeto": p['titulo'], "Fase": f"Fase {p['fase']}", "Esforço": len(p.get('notas', []))} for p in ativos])
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("##### 📊 Esforço por Projeto (Barras)")
                    st.bar_chart(df_at.set_index("Projeto")["Esforço"])
                with col_g2:
                    st.markdown("##### 🍕 Participação no Portfólio (Pizza)")
                    fig_pizza = px.pie(df_at, values='Esforço', names='Projeto', hole=0.4,
                                     color_discrete_sequence=px.colors.qualitative.Prism)
                    fig_pizza.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=300, showlegend=True)
                    st.plotly_chart(fig_pizza, use_container_width=True)

                st.divider()
                st.markdown("##### 📋 Detalhamento do Portfólio")
                st.dataframe(df_at, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum projeto ativo.")

        with sub_d2:
            concluidos = [p for p in projs if p.get('status') == "Concluído"]
            if concluidos:
                df_concl = pd.DataFrame([{"Projeto": p['titulo'], "Data": p.get('data_conclusao', 'S/D'), "Ações": len(p.get('notas', []))} for p in concluidos])
                st.dataframe(df_concl, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum projeto entregue.")

    # --- 2. GESTÃO (Incluso Nova Aba de Situações Diárias) ---
    if tab_gestao:
        with tab_gestao:
            sub_g1, sub_g2 = st.tabs(["⚙️ Gerenciamento de Projetos", "📝 Situações Diárias (Diário)"])
            
            with sub_g1:
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
                        col_g1, col_g2 = st.columns([2,1])
                        p['titulo'] = col_g1.text_input("Nome do Projeto", p['titulo'], key=f"gest_t_{i}")
                        p['status'] = col_g2.selectbox("Status", ["Ativo", "Concluído", "Pausado"], index=["Ativo", "Concluído", "Pausado"].index(p.get('status','Ativo')), key=f"gest_s_{i}")
                        
                        st.write("**Motivos de Esforço Customizados**")
                        novos_mots = st.text_input("Adicionar motivos (separados por vírgula)", key=f"mot_cust_{i}")
                        if st.button("Atualizar Motivos", key=f"btn_mot_{i}"):
                            p['motivos_custom'] = [m.strip() for m in novos_mots.split(",") if m.strip()]
                            salvar_seguro()
                            st.rerun()
                        
                        if st.button("🗑️ Excluir Projeto", key=f"gest_del_{i}"):
                            st.session_state.db_pqi.remove(p)
                            salvar_seguro()
                            st.rerun()

            with sub_g2:
                st.subheader("📓 Diário de Situações Diárias")
                st.caption("Registre demandas paralelas, reuniões de última hora e solicitações rápidas.")
                
                with st.container(border=True):
                    col_sit1, col_sit2 = st.columns([2,1])
                    titulo_sit = col_sit1.text_input("O que pediram? (Ex: Cotação Empresa X)")
                    depto_sit = col_sit2.selectbox("Quem pediu?", DEPARTAMENTOS, key="depto_situacao")
                    desc_sit = st.text_area("Detalhes da ação / Próximo passo")
                    
                    if st.button("Gravar no Diário", type="primary"):
                        if titulo_sit:
                            nova_sit = {
                                "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                "Solicitação": titulo_sit,
                                "Departamento": depto_sit,
                                "Ação Realizada": desc_sit
                            }
                            st.session_state.situacoes_diarias.append(nova_sit)
                            st.success("Registrado!")
                            st.rerun()
                        else:
                            st.warning("Descreva o que foi pedido antes de salvar.")

                st.divider()
                if st.session_state.situacoes_diarias:
                    df_situacoes = pd.DataFrame(st.session_state.situacoes_diarias)
                    st.markdown(f"**Total de acionamentos paralelos registrados: {len(df_situacoes)}**")
                    
                    # Botão de Exportação para Excel
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_situacoes.to_excel(writer, index=False, sheet_name='Situacoes')
                    processed_data = output.getvalue()
                    
                    st.download_button(
                        label="📥 Exportar Diário para Excel",
                        data=processed_data,
                        file_name=f'situacoes_diarias_{datetime.now().strftime("%Y%m%d")}.xlsx',
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    )

                    st.dataframe(df_situacoes.sort_index(ascending=False), use_container_width=True, hide_index=True)
                    if st.button("Clear Diário (CUIDADO)"):
                        st.session_state.situacoes_diarias = []
                        st.rerun()
                else:
                    st.info("Nenhuma situação registrada hoje.")

    # --- 3. OPERAÇÃO PQI ---
    with tab_operacao:
        st.subheader("🚀 Operação de Processos")
        projs = st.session_state.db_pqi
        
        if not projs:
            st.warning("Vá na aba GESTÃO e crie seu primeiro projeto para começar.")
        else:
            c_f1, c_f2 = st.columns([1, 2])
            status_sel = c_f1.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
            map_status = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
            filtrados = [p for p in projs if p.get('status', 'Ativo') == map_status[status_sel]]
            
            if not filtrados:
                st.info(f"Não há projetos com status '{map_status[status_sel]}'.")
            else:
                escolha = c_f2.selectbox("Selecione o Projeto para Operar:", [p['titulo'] for p in filtrados])
                projeto = next(p for p in filtrados if p['titulo'] == escolha)

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
                        with st.popover("➕ Adicionar Registro de Esforço", use_container_width=True):
                            c_p1, c_p2 = st.columns(2)
                            mot = c_p1.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                            dep = c_p2.selectbox("Departamento Relacionado", DEPARTAMENTOS)
                            dsc = st.text_area("Descrição da Ação")
                            st.write("**⏰ Agendar Lembrete?**")
                            cl1, cl2 = st.columns(2)
                            dl = cl1.date_input("Data", value=None, key=f"date_reg_{projeto['titulo']}")
                            hl = cl2.time_input("Hora", value=None, key=f"time_reg_{projeto['titulo']}")
                            
                            if st.button("Gravar no Banco", type="primary"):
                                if dl and hl:
                                    projeto.setdefault('lembretes', []).append({
                                        "data_hora": f"{dl.strftime('%d/%m/%Y')} {hl.strftime('%H:%M')}",
                                        "texto": f"{projeto['titulo']}: {mot}"
                                    })
                                projeto['notas'].append({
                                    "motivo": mot, "depto": dep, "texto": dsc, 
                                    "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                    "fase_origem": projeto['fase']
                                })
                                salvar_seguro(); st.rerun()
                        
                        st.divider()
                        notas_fase = [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]
                        if not notas_fase: st.info("Nenhum registro nesta fase.")
                        for n in reversed(notas_fase):
                            with st.expander(f"📌 {n['motivo']} ({n.get('depto', 'Geral')}) - {n['data']}"):
                                st.write(n['texto'])

                    with col_e2:
                        st.markdown("#### ⚙️ Controle")
                        if st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                            if projeto['fase'] < 8:
                                projeto['fase'] += 1; salvar_seguro(); st.rerun()
                        if st.button("⏪ RECUAR ETAPA", use_container_width=True):
                            if projeto['fase'] > 1:
                                projeto['fase'] -= 1; salvar_seguro(); st.rerun()
                        
                        st.markdown("#### ⏰ Lembretes")
                        for idx, l in enumerate(projeto.get('lembretes', [])):
                            with st.container(border=True):
                                st.caption(f"📅 {l['data_hora']}")
                                st.write(l['texto'])
                                if st.button("Concluir", key=f"done_l_{idx}_{projeto['titulo']}"):
                                    projeto['lembretes'].pop(idx); salvar_seguro(); st.rerun()

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
                                novo_n = c_p1.text_input("Renomear", p_nome, key=f"ren_p_{p_nome}_{projeto['titulo']}")
                                if novo_n != p_nome:
                                    pastas[novo_n] = pastas.pop(p_nome); salvar_seguro(); st.rerun()
                                if c_p2.button("🗑️", key=f"del_p_{p_nome}_{projeto['titulo']}"):
                                    del pastas[p_nome]; salvar_seguro(); st.rerun()
                                
                                up = st.file_uploader("Anexar", accept_multiple_files=True, key=f"up_{p_nome}_{projeto['titulo']}")
                                if st.button("Subir Arquivos", key=f"btn_{p_nome}_{projeto['titulo']}"):
                                    for a in up:
                                        path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{a.name}")
                                        with open(path, "wb") as f: f.write(a.getbuffer())
                                        pastas[p_nome].append({"nome": a.name, "path": path, "data": datetime.now().strftime("%d/%m/%Y")})
                                    salvar_seguro(); st.rerun()
                    with sub2:
                        df_hist = pd.DataFrame(projeto.get('notas', []))
                        if not df_hist.empty:
                            st.dataframe(df_hist, use_container_width=True, hide_index=True)

                with t_esforco:
                    df_k = pd.DataFrame(projeto.get('notas', []))
                    if not df_k.empty:
                        st.markdown(f"### Análise de Esforço: {projeto['titulo']}")
                        c_esf1, c_esf2 = st.columns(2)
                        with c_esf1:
                            st.markdown("**Frequência de Assuntos**")
                            st.bar_chart(df_k['motivo'].value_counts())
                        with c_esf2:
                            st.markdown("**Distribuição Percentual**")
                            df_pizza_motivo = df_k['motivo'].value_counts().reset_index()
                            df_pizza_motivo.columns = ['Motivo', 'Qtd']
                            fig_mot = px.pie(df_pizza_motivo, values='Qtd', names='Motivo', hole=0.4)
                            fig_mot.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=300)
                            st.plotly_chart(fig_mot, use_container_width=True)
                    else:
                        st.info("Inicie os registros para ver a análise.")
