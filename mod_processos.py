import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import io
import zipfile
import database as db
import plotly.express as px  # Necessário para os novos gráficos

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

# --- NOVO: FUNÇÃO DO DASHBOARD PARA O CEO ---
def dashboard_executivo(projetos):
    if not projetos:
        st.info("Aguardando dados para gerar indicadores...")
        return

    st.markdown("### 📊 Business Intelligence - Melhoria Contínua")
    
    # 1. MÉTRICAS TOPO
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Projetos Totais", len(projetos))
    with c2: st.metric("Em Execução 🚀", len([p for p in projetos if p.get('status') == 'Ativo']))
    with c3: st.metric("Concluídos ✅", len([p for p in projetos if p.get('status') == 'Concluído']))
    with c4: st.metric("Fase Piloto 🛠️", len([p for p in projetos if p.get('fase') == 5]))

    col_g1, col_g2 = st.columns([2, 1])

    with col_g1:
        # 2. GRÁFICO DE GANTT (CRONOGRAMA GERAL)
        st.markdown("#### 📅 Cronograma de Evolução")
        dados_gantt = []
        for p in projetos:
            # Pega a data da fase 1 (início)
            inicio_str = p.get('historico', {}).get('1', datetime.now().strftime("%d/%m/%Y"))
            try:
                data_ini = datetime.strptime(inicio_str, "%d/%m/%Y")
            except:
                data_ini = datetime.now()
            
            dados_gantt.append(dict(
                Projeto=p['titulo'], 
                Início=data_ini, 
                Hoje=datetime.now(), 
                Fase=f"Etapa {p['fase']}"
            ))
        
        if dados_gantt:
            df_gantt = pd.DataFrame(dados_gantt)
            fig_gantt = px.timeline(df_gantt, x_start="Início", x_end="Hoje", y="Projeto", color="Fase",
                                   color_discrete_sequence=px.colors.qualitative.Safe)
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_gantt, use_container_width=True)

    with col_g2:
        # 3. MAPA DE CALOR / GARGALOS (ONDE ESTÁ TRAVANDO POR SETOR)
        st.markdown("#### 🔥 Gargalos por Setor")
        setores_dados = []
        for p in projetos:
            for n in p.get('notas', []):
                if n.get('setor'):
                    setores_dados.append({"Setor": n['setor']})
        
        if setores_dados:
            df_setores = pd.DataFrame(setores_dados)
            heatmap_data = df_setores.groupby("Setor").size().reset_index(name='Interações')
            fig_heat = px.bar(heatmap_data, y="Setor", x="Interações", orientation='h',
                             color="Interações", color_continuous_scale='Reds')
            fig_heat.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
            st.plotly_chart(fig_heat, use_container_width=True)
        else:
            st.caption("Sem apontamentos de setor ainda.")

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
        .roi-box { background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 10px; color: #166534; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO DE DADOS
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- NOVO: PAINEL EXECUTIVO NO TOPO ---
    with st.expander("📺 VISÃO DIRETORIA (Geral dos Processos)", expanded=False):
        dashboard_executivo(st.session_state.db_pqi)

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

        # 4. TABS
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
                if st.button("Salvar Dados Financeiros"):
                    db.salvar_projetos(st.session_state.db_pqi)
                    st.success("Dados salvos!")

                if economia > 0:
                    st.markdown(f"""
                    <div class="roi-box">
                        <b>Potencial de Economia Mensal:</b><br>
                        <span style="font-size: 24px;">R$ {economia:,.2f}</span>
                    </div>
                    """, unsafe_allow_html=True)

            with col_m2:
                st.markdown("### 📑 Análise Técnica")
                an_merc = st.text_area("Notas sobre Soluções de Mercado / Benchmarking", value=projeto.get('analise_mercado', ""))
                if st.button("Salvar Análise"):
                    projeto['analise_mercado'] = an_merc
                    db.salvar_projetos(st.session_state.db_pqi)
                    st.success("Análise atualizada!")

        with tab_dos:
             st.subheader("📂 Central de Documentos (Dossiê)")
             # Lógica original de dossiê aqui se necessário

        with tab_kpi:
             st.subheader("📊 Performance do Projeto")
             # Lógica original de KPI aqui se necessário

        with tab_cfg:
             st.subheader("⚙️ Configurações do Projeto")
             novo_titulo = st.text_input("Alterar Nome do Projeto", value=projeto['titulo'])
             if st.button("Atualizar Nome"):
                 projeto['titulo'] = novo_titulo
                 db.salvar_projetos(st.session_state.db_pqi); st.rerun()
             
             status_op = st.selectbox("Status Geral", ["Ativo", "Concluído", "Pausado"], index=["Ativo", "Concluído", "Pausado"].index(projeto.get('status', 'Ativo')))
             if st.button("Atualizar Status"):
                 projeto['status'] = status_op
                 db.salvar_projetos(st.session_state.db_pqi); st.rerun()
