import streamlit as st
import pandas as pd
from datetime import datetime
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
DEPARTAMENTOS = ["CX", "PQI","Compras", "Logística", "TI", "Financeiro", "RH", "Fiscal", "Operações", "Comercial", "Diretoria"]

def exibir(user_role="OPERACIONAL"):
    # 1. ESTILO CSS
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

    # 2. INICIALIZAÇÃO DE DADOS (Carregando direto do Banco)
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    if 'situacoes_diarias' not in st.session_state:
        st.session_state.situacoes_diarias = db.carregar_diario()

    def salvar_seguro():
        try:
            db.salvar_projetos(st.session_state.db_pqi)
            db.salvar_diario(st.session_state.situacoes_diarias)
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

    # --- DEFINIÇÃO DAS ABAS ---
    # Centralização da lógica de abas para manter integridade de navegação
    titulos = ["📊 DASHBOARD GERAL"]
    if user_role in ["ADM", "GERENTE"]:
        titulos.append("⚙️ GESTÃO")
    titulos.append("🚀 OPERAÇÃO PQI")

    tabs = st.tabs(titulos)
    
    # Mapeamento dinâmico para evitar erro de índice se o usuário não for ADM
    tab_dash = tabs[0]
    if user_role in ["ADM", "GERENTE"]:
        tab_gestao = tabs[1]
        tab_operacao = tabs[2]
    else:
        tab_gestao = None
        tab_operacao = tabs[1]

    # --- 1. DASHBOARD GERAL ---
    with tab_dash:
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
                    valid_deptos = df_notas['depto'].dropna()
                    if not valid_deptos.empty:
                        gargalo = valid_deptos.mode().iloc[0]
                c3.markdown(f'<div class="metric-card"><div class="metric-label">Gargalo (Depto)</div><div class="metric-value" style="font-size:18px">{gargalo}</div></div>', unsafe_allow_html=True)
                
                st.write("") 
                df_at = pd.DataFrame([{"Projeto": p.get('titulo', 'S/N'), "Fase": f"Fase {p.get('fase', 1)}", "Esforço": len(p.get('notas', []))} for p in ativos])
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("##### 📊 Esforço por Projeto (Barras)")
                    st.bar_chart(df_at.set_index("Projeto")["Esforço"])
                with col_g2:
                    st.markdown("##### 🍕 Participação no Portfólio (Pizza)")
                    fig_pizza = px.pie(df_at, values='Esforço', names='Projeto', hole=0.4, color_discrete_sequence=px.colors.qualitative.Prism)
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
                df_concl = pd.DataFrame([{"Projeto": p.get('titulo', 'S/N'), "Data": p.get('data_conclusao', 'S/D'), "Ações": len(p.get('notas', []))} for p in concluidos])
                st.dataframe(df_concl, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum projeto entregue.")

    # --- 2. GESTÃO ---
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
                    st.rerun()

                st.write("---")
                for i, p in enumerate(st.session_state.db_pqi):
                    with st.expander(f"Configurações: {p.get('titulo', 'Sem Título')}"):
                        col_cfg1, col_cfg2 = st.columns([2,1])
                        p['titulo'] = col_cfg1.text_input("Nome do Projeto", p.get('titulo', ''), key=f"gest_t_{i}")
                        stts_options = ["Ativo", "Concluído", "Pausado"]
                        p['status'] = col_cfg2.selectbox("Status", stts_options, index=stts_options.index(p.get('status','Ativo')), key=f"gest_s_{i}")
                        
                        st.write("**Motivos de Esforço Customizados**")
                        novos_mots = st.text_input("Adicionar motivos (separados por vírgula)", key=f"mot_cust_{i}")
                        if st.button("Atualizar Motivos", key=f"btn_mot_{i}"):
                            p['motivos_custom'] = [m.strip() for m in novos_mots.split(",") if m.strip()]
                            salvar_seguro()
                            st.rerun()
                        if st.button("🗑️ Excluir Projeto", key=f"gest_del_{i}"):
                            st.session_state.db_pqi.pop(i)
                            salvar_seguro()
                            st.rerun()

            with sub_g2:
                st.subheader("📓 Diário de Situações Diárias")
                with st.container(border=True):
                    col_sit1, col_sit2 = st.columns([2,1])
                    titulo_sit = col_sit1.text_input("O que pediram? (Ex: Reservar sala)")
                    depto_sit = col_sit2.selectbox("Quem pediu?", DEPARTAMENTOS, key="depto_sit_diario")
                    desc_sit = st.text_area("Detalhes da ação")
                    
                    st.write("**⏰ Agendar Lembrete para esta demanda?**")
                    cl_d1, cl_d2 = st.columns(2)
                    dl_sit = cl_d1.date_input("Data Limite", value=None, key="date_sit_diario")
                    hl_sit = cl_d2.time_input("Hora Limite", value=None, key="time_sit_diario")
                    
                    if st.button("Gravar no Diário", type="primary"):
                        if titulo_sit:
                            nova_sit = {
                                "id": datetime.now().timestamp(),
                                "data_reg": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                "solicitacao": titulo_sit, "depto": depto_sit, "detalhes": desc_sit,
                                "lembrete": f"{dl_sit.strftime('%d/%m/%Y')} {hl_sit.strftime('%H:%M')}" if dl_sit and hl_sit else "N/A",
                                "status": "Pendente", "obs_final": ""
                            }
                            st.session_state.situacoes_diarias.append(nova_sit)
                            salvar_seguro()
                            st.success("Demanda registrada!")
                            st.rerun()

                st.divider()
                if st.session_state.situacoes_diarias:
                    f_col1, f_col2 = st.columns([1,1])
                    ver_status = f_col1.multiselect("Filtrar Status:", ["Pendente", "Executado", "Cancelado", "Não Possível"], default=["Pendente"])
                    
                    for idx, sit in enumerate(st.session_state.situacoes_diarias):
                        if not ver_status or sit['status'] in ver_status:
                            cor_status = {"Pendente": "🔵", "Executado": "✅", "Cancelado": "❌", "Não Possível": "⚠️"}
                            with st.expander(f"{cor_status.get(sit['status'], '⚪')} {sit['solicitacao']} | {sit['depto']} ({sit['status']})"):
                                st.write(f"**Registrado em:** {sit['data_reg']} | **Lembrete:** {sit['lembrete']}")
                                st.info(f"**Detalhes:** {sit['detalhes']}")
                                if sit['obs_final']: st.warning(f"**Motivo/OBS:** {sit['obs_final']}")
                                
                                if sit['status'] == "Pendente":
                                    c_btn1, c_btn2, c_btn3, c_btn4 = st.columns(4)
                                    if c_btn1.button("✅ Executado", key=f"ok_{idx}"):
                                        sit['status'] = "Executado"; salvar_seguro(); st.rerun()
                                    with c_btn2.popover("❌ Cancelar"):
                                        motivo_canc = st.text_input("Motivo", key=f"txt_cnc_{idx}")
                                        if st.button("Confirmar", key=f"btn_cnc_{idx}"):
                                            sit['status'] = "Cancelado"; sit['obs_final'] = motivo_canc; salvar_seguro(); st.rerun()
                                    with c_btn3.popover("⚠️ Não Possível"):
                                        motivo_imp = st.text_input("Motivo", key=f"txt_imp_{idx}")
                                        if st.button("Confirmar", key=f"btn_imp_{idx}"):
                                            sit['status'] = "Não Possível"; sit['obs_final'] = motivo_imp; salvar_seguro(); st.rerun()
                                    if c_btn4.button("🗑️ Excluir", key=f"del_sit_{idx}"):
                                        st.session_state.situacoes_diarias.pop(idx); salvar_seguro(); st.rerun()

                st.divider()
                df_export = pd.DataFrame(st.session_state.situacoes_diarias)
                if not df_export.empty:
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_export.to_excel(writer, index=False, sheet_name='Diario')
                    st.download_button("📥 Exportar Diário para Excel", output.getvalue(), file_name=f"diario_{datetime.now().strftime('%Y%m%d')}.xlsx")

    # --- 3. OPERAÇÃO PQI ---
    with tab_operacao:
        st.subheader("🚀 Operação de Processos")
        projs = st.session_state.db_pqi
        if not projs:
            st.warning("Vá na aba GESTÃO e crie seu primeiro projeto.")
        else:
            c_f1, c_f2 = st.columns([1, 2])
            status_sel = c_f1.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
            map_status = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
            filtrados = [p for p in projs if p.get('status', 'Ativo') == map_status[status_sel]]
            
            if filtrados:
                escolha = c_f2.selectbox("Selecione o Projeto:", [p.get('titulo', 'Sem Título') for p in filtrados])
                projeto = next(p for p in filtrados if p.get('titulo') == escolha)
                
                # Defesa contra erro de fase nula
                fase_atual = projeto.get('fase', 1)
                
                st.write("")
                cols_r = st.columns(8)
                for i, etapa in enumerate(ROADMAP):
                    n, cl, txt = i+1, "ponto-regua", str(i+1)
                    if n < fase_atual: cl += " ponto-check"; txt = "✔"
                    elif n == fase_atual: cl += " ponto-atual"
                    cols_r[i].markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

                t_exec, t_dossie, t_esforco = st.tabs(["📝 Execução Diária", "📁 Dossiê & Arquivos", "📊 Análise de Esforço"])

                with t_exec:
                    col_e1, col_e2 = st.columns([2, 1])
                    with col_e1:
                        # Proteção de índice do ROADMAP
                        nome_etapa = ROADMAP[fase_atual-1]['nome'] if 0 < fase_atual <= 8 else "Etapa Indefinida"
                        st.markdown(f"### Etapa {fase_atual}: {nome_etapa}")
                        with st.popover("➕ Adicionar Registro de Esforço", use_container_width=True):
                            c_p1, c_p2 = st.columns(2)
                            mot = c_p1.selectbox("Assunto", MOTIVOS_PADRAO + projeto.get('motivos_custom', []))
                            dep = c_p2.selectbox("Departamento", DEPARTAMENTOS)
                            dsc = st.text_area("Descrição")
                            cl1, cl2 = st.columns(2)
                            dl = cl1.date_input("Data Lembrete", value=None, key=f"d_pqi_{projeto.get('titulo')}")
                            hl = cl2.time_input("Hora Lembrete", value=None, key=f"h_pqi_{projeto.get('titulo')}")
                            if st.button("Gravar no Banco", type="primary"):
                                if dl and hl:
                                    projeto.setdefault('lembretes', []).append({"id": datetime.now().timestamp(), "data_hora": f"{dl.strftime('%d/%m/%Y')} {hl.strftime('%H:%M')}", "texto": f"{projeto.get('titulo')}: {mot}"})
                                projeto.setdefault('notas', []).append({"motivo": mot, "depto": dep, "texto": dsc, "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "fase_origem": fase_atual})
                                salvar_seguro(); st.rerun()
                        st.divider()
                        notas_fase = [n for n in projeto.get('notas', []) if n.get('fase_origem') == fase_atual]
                        for n in reversed(notas_fase):
                            with st.expander(f"📌 {n['motivo']} ({n.get('depto', 'Geral')}) - {n['data']}"): 
                                st.write(n['texto'])

                    with col_e2:
                        st.markdown("#### ⚙️ Controle")
                        if st.button("▶️ AVANÇAR", use_container_width=True, type="primary") and fase_atual < 8:
                            projeto['fase'] = fase_atual + 1
                            salvar_seguro(); st.rerun()
                        
                        if st.button("⏪ RECUAR", use_container_width=True) and fase_atual > 1:
                            projeto['fase'] = fase_atual - 1
                            salvar_seguro(); st.rerun()

                        st.markdown("#### ⏰ Lembretes")
                        lembretes_atuais = projeto.get('lembretes', [])
                        for l_idx, l in enumerate(lembretes_atuais):
                            with st.container(border=True):
                                st.caption(f"📅 {l['data_hora']}")
                                st.write(l['texto'])
                                if st.button("Concluir", key=f"done_pqi_{l.get('id', l_idx)}"): 
                                    projeto['lembretes'].pop(l_idx)
                                    salvar_seguro(); st.rerun()

                with t_dossie:
                    sub_dos1, sub_dos2 = st.tabs(["📂 Pastas", "📜 Histórico"])
                    with sub_dos1:
                        with st.popover("➕ Criar Pasta"):
                            nome_pasta = st.text_input("Nome da Pasta")
                            if st.button("Salvar Pasta"):
                                projeto.setdefault('pastas_virtuais', {})[nome_pasta] = []
                                salvar_seguro(); st.rerun()
                        pastas = projeto.get('pastas_virtuais', {})
                        for p_nome in list(pastas.keys()):
                            with st.expander(f"📁 {p_nome}"):
                                c_rn1, c_rn2 = st.columns([3, 1])
                                novo_nome = c_rn1.text_input("Renomear", p_nome, key=f"r_{p_nome}_{projeto.get('titulo')}")
                                if novo_nome != p_nome:
                                    pastas[novo_nome] = pastas.pop(p_nome); salvar_seguro(); st.rerun()
                                if c_rn2.button("🗑️", key=f"d_{p_nome}"):
                                    del pastas[p_nome]; salvar_seguro(); st.rerun()
                                up_files = st.file_uploader("Anexar", accept_multiple_files=True, key=f"u_{p_nome}")
                                if st.button("Subir Arquivos", key=f"b_{p_nome}"):
                                    for a in up_files:
                                        path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{a.name}")
                                        with open(path, "wb") as f: f.write(a.getbuffer())
                                        pastas[p_nome].append({"nome": a.name, "path": path, "data": datetime.now().strftime("%d/%m/%Y")})
                                    salvar_seguro(); st.rerun()

                    with sub_dos2:
                        df_hist = pd.DataFrame(projeto.get('notas', []))
                        if not df_hist.empty: st.dataframe(df_hist, use_container_width=True, hide_index=True)

                with t_esforco:
                    df_esf = pd.DataFrame(projeto.get('notas', []))
                    if not df_esf.empty:
                        st.markdown(f"### Análise: {projeto.get('titulo')}")
                        c_esf1, c_esf2 = st.columns(2)
                        with c_esf1: st.bar_chart(df_esf['motivo'].value_counts())
                        with c_esf2:
                            df_p = df_esf['motivo'].value_counts().reset_index()
                            df_p.columns = ['Motivo', 'Qtd']
                            fig = px.pie(df_p, values='Qtd', names='Motivo', hole=0.4)
                            fig.update_layout(margin=dict(l=20,r=20,t=20,b=20), height=300)
                            st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhum projeto encontrado com este status.")
