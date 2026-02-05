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

# --- FUNÇÃO DO DASHBOARD PARA O CEO (BI) ---
def dashboard_executivo(projetos):
    if not projetos:
        st.info("Aguardando dados para gerar indicadores...")
        return

    st.markdown("### 📊 Business Intelligence - Melhoria Contínua")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Projetos Totais", len(projetos))
    with c2: st.metric("Em Execução 🚀", len([p for p in projetos if p.get('status') == 'Ativo']))
    with c3: st.metric("Concluídos ✅", len([p for p in projetos if p.get('status') == 'Concluído']))
    with c4: st.metric("Fase Piloto 🛠️", len([p for p in projetos if p.get('fase') == 5]))

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown("#### 📅 Cronograma de Evolução")
        dados_gantt = []
        for p in projetos:
            # Pega a data da fase 1 ou a data atual se não existir
            inicio_str = p.get('historico', {}).get('1', datetime.now().strftime("%d/%m/%Y"))
            try:
                data_ini = datetime.strptime(inicio_str, "%d/%m/%Y")
            except:
                data_ini = datetime.now()
            
            dados_gantt.append(dict(Projeto=p['titulo'], Início=data_ini, Hoje=datetime.now(), Fase=f"Etapa {p['fase']}"))
        
        if dados_gantt:
            df_gantt = pd.DataFrame(dados_gantt)
            fig_gantt = px.timeline(df_gantt, x_start="Início", x_end="Hoje", y="Projeto", color="Fase")
            fig_gantt.update_yaxes(autorange="reversed")
            fig_gantt.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_gantt, use_container_width=True)

    with col_g2:
        st.markdown("#### 🔥 Gargalos por Setor")
        setores_dados = []
        for p in projetos:
            for n in p.get('notas', []):
                if n.get('setor'):
                    setores_dados.append({"Setor": n['setor']})
        
        if setores_dados:
            df_setores = pd.DataFrame(setores_dados)
            heatmap_data = df_setores.groupby("Setor").size().reset_index(name='Interações')
            fig_heat = px.bar(heatmap_data, y="Setor", x="Interações", orientation='h', color="Interações", color_continuous_scale='Reds')
            fig_heat.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
            st.plotly_chart(fig_heat, use_container_width=True)

def exibir(user_role="OPERACIONAL"):
    # 1. ESTILO CSS
    st.markdown("""
    <style>
        .ponto-regua { width: 35px; height: 35px; border-radius: 50%; background: #e2e8f0; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #64748b; margin: 0 auto; border: 2px solid #cbd5e1; }
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 10px rgba(0, 35, 102, 0.4); }
        .label-regua { font-size: 10px; text-align: center; font-weight: bold; margin-top: 5px; color: #475569; height: 30px; }
        .roi-box { background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 10px; color: #166534; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- PAINEL EXECUTIVO ---
    with st.expander("📺 VISÃO DIRETORIA (BI)", expanded=False):
        dashboard_executivo(st.session_state.db_pqi)

    # --- FILTROS ---
    c_t1, c_t2, c_t3 = st.columns([1,2,1])
    with c_t1:
        status_filtro = st.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
        status_map = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
    
    projs_f = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == status_map[status_filtro]]
    
    projeto = None
    with c_t2:
        if projs_f:
            escolha = st.selectbox("Selecione o Projeto:", [p['titulo'] for p in projs_f])
            projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
        else:
            st.warning("Nenhum projeto encontrado.")

    with c_t3:
        if user_role in ["ADM", "GERENTE"]:
            if st.button("➕ NOVO PROJETO", use_container_width=True, type="primary"):
                novo = {
                    "titulo": f"Novo Processo {len(st.session_state.db_pqi)+1}", 
                    "fase": 1, "status": "Ativo", "notas": [], 
                    "historico": {"1": datetime.now().strftime("%d/%m/%Y")},
                    "custo_atual": 0.0, "custo_estimado": 0.0, "analise_mercado": ""
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
        tab_ex, tab_dos, tab_kpi, tab_merc, tab_cfg = st.tabs(["🚀 Execução", "📂 Dossiê", "📊 KPIs", "🔍 Mercado & ROI", "⚙️ Gestão"])

        with tab_ex:
            c1, c2 = st.columns([2,1])
            with c1:
                st.subheader(f"📍 Etapa: {ROADMAP[projeto['fase']-1]['nome']}")
                notas_fase = [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]
                
                for idx, n in enumerate(notas_fase):
                    with st.expander(f"📝 {n['motivo']} - {n.get('setor', 'GERAL')} ({n['data']})"):
                        st.write(n['texto'])
                        if n.get('arquivo_local') and os.path.exists(n['arquivo_local']):
                            with open(n['arquivo_local'], "rb") as f:
                                st.download_button("📥 Baixar Anexo", f, key=f"dl_{idx}_{n['data']}")
                        
                        if st.button("🗑️", key=f"del_{idx}_{n['data']}"):
                            projeto['notas'].remove(n)
                            db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                with st.popover("➕ Novo Registro"):
                    mot = st.selectbox("Motivo", MOTIVOS_PADRAO)
                    setor = st.text_input("Setor").upper()
                    txt = st.text_area("Descrição")
                    arq = st.file_uploader("Anexar Documento")
                    if st.button("Salvar Registro"):
                        caminho_anexo = None
                        if arq:
                            caminho_anexo = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{arq.name}")
                            with open(caminho_anexo, "wb") as f: f.write(arq.getbuffer())
                        
                        projeto.setdefault('notas', []).append({
                            "motivo": mot, "setor": setor, "texto": txt, 
                            "data": datetime.now().strftime("%d/%m/%Y"), 
                            "fase_origem": projeto['fase'],
                            "arquivo_local": caminho_anexo
                        })
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

            with c2:
                st.markdown("#### 🕹️ Fluxo")
                if user_role in ["ADM", "GERENTE"]:
                    if projeto['fase'] < 8 and st.button("▶️ AVANÇAR", use_container_width=True, type="primary"):
                        projeto['fase'] += 1
                        projeto.setdefault('historico', {})[str(projeto['fase'])] = datetime.now().strftime("%d/%m/%Y")
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                    
                    if projeto['fase'] > 1 and st.button("⏪ RECUAR", use_container_width=True):
                        projeto['fase'] -= 1
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

        with tab_dos:
            st.subheader("📜 Histórico de Esforço")
            df_dossie = pd.DataFrame(projeto.get('notas', []))
            if not df_dossie.empty:
                st.dataframe(df_dossie, use_container_width=True)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_dossie.to_excel(writer, index=False)
                st.download_button("📥 Baixar Planilha Completa", output.getvalue(), f"Dossie_{projeto['titulo']}.xlsx")
            else:
                st.info("Nenhum registro para exportar.")

        with tab_kpi:
            st.subheader("📊 Métricas do Projeto")
            df_kpi = pd.DataFrame(projeto.get('notas', []))
            if not df_kpi.empty:
                col_k1, col_k2 = st.columns(2)
                col_k1.metric("Total de Ações", len(df_kpi))
                col_k2.metric("Estágio Atual", f"{projeto['fase']}/8")
                st.bar_chart(df_kpi['motivo'].value_counts())

        with tab_merc:
            st.subheader("🔍 Inteligência de Mercado & ROI")
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                c_at = st.number_input("Custo Atual (R$)", value=float(projeto.get('custo_atual', 0)))
                c_es = st.number_input("Custo Estimado (R$)", value=float(projeto.get('custo_estimado', 0)))
                economia = c_at - c_es
                st.markdown(f'<div class="roi-box">Economia: R$ {economia:,.2f}</div>', unsafe_allow_html=True)
            with col_m2:
                analise = st.text_area("Insights de Benchmarking", value=projeto.get('analise_mercado', ""))
            
            if st.button("Salvar Dados de Mercado"):
                projeto['custo_atual'], projeto['custo_estimado'] = c_at, c_es
                projeto['analise_mercado'] = analise
                db.salvar_projetos(st.session_state.db_pqi); st.success("Salvo com sucesso!")

        with tab_cfg:
            new_name = st.text_input("Renomear Projeto", value=projeto['titulo'])
            new_status = st.selectbox("Alterar Status", ["Ativo", "Concluído", "Pausado"], 
                                    index=["Ativo", "Concluído", "Pausado"].index(projeto.get('status', 'Ativo')))
            if st.button("Atualizar Configurações"):
                projeto['titulo'] = new_name
                projeto['status'] = new_status
                db.salvar_projetos(st.session_state.db_pqi); st.rerun()
            
            if user_role == "ADM":
                st.divider()
                if st.button("🗑️ EXCLUIR PROJETO DEFINITIVAMENTE", type="secondary"):
                    st.session_state.db_pqi.remove(projeto)
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()
