import streamlit as st
import pandas as pd
from datetime import datetime
import os
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

# --- FUNÇÃO DO DASHBOARD PARA O CEO ---
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
        .roi-box { background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 15px; border-radius: 10px; color: #166534; }
    </style>
    """, unsafe_allow_html=True)

    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- PAINEL EXECUTIVO ---
    with st.expander("📺 VISÃO DIRETORIA", expanded=False):
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

    with c_t3:
        if user_role in ["ADM", "GERENTE"]:
            if st.button("➕ NOVO PROJETO", use_container_width=True):
                novo = {"titulo": f"Novo Processo {len(st.session_state.db_pqi)+1}", "fase": 1, "status": "Ativo", "notas": [], "historico": {"1": datetime.now().strftime("%d/%m/%Y")}}
                st.session_state.db_pqi.append(novo)
                db.salvar_projetos(st.session_state.db_pqi)
                st.rerun()

    if projeto:
        # 3. RÉGUA
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
        tab_ex, tab_dos, tab_merc, tab_cfg = st.tabs(["🚀 Execução", "📂 Dossiê", "🔍 Mercado & ROI", "⚙️ Gestão"])

        with tab_ex:
            c1, c2 = st.columns([2,1])
            with c1:
                st.subheader(f"📍 Etapa: {ROADMAP[projeto['fase']-1]['nome']}")
                for idx, n in enumerate(projeto.get('notas', [])):
                    if n.get('fase_origem') == projeto['fase']:
                        with st.expander(f"📝 {n['motivo']} ({n['data']})"):
                            st.write(n['texto'])
                            if st.button("🗑️", key=f"del_{idx}"):
                                projeto['notas'].remove(n)
                                db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                with st.popover("➕ Novo Registro"):
                    mot = st.selectbox("Motivo", MOTIVOS_PADRAO)
                    setor = st.text_input("Setor").upper()
                    txt = st.text_area("Descrição")
                    if st.button("Salvar"):
                        projeto.setdefault('notas', []).append({"motivo": mot, "setor": setor, "texto": txt, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase']})
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

            with c2:
                if st.button("▶️ AVANÇAR"):
                    projeto['fase'] = min(8, projeto['fase']+1)
                    projeto.setdefault('historico', {})[str(projeto['fase'])] = datetime.now().strftime("%d/%m/%Y")
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()

        with tab_merc:
            c_at = st.number_input("Custo Atual", value=float(projeto.get('custo_atual', 0)))
            c_es = st.number_input("Custo Sugerido", value=float(projeto.get('custo_estimado', 0)))
            if st.button("Salvar ROI"):
                projeto['custo_atual'], projeto['custo_estimado'] = c_at, c_es
                db.salvar_projetos(st.session_state.db_pqi); st.success("Salvo!")
            st.metric("Economia Estimada", f"R$ {c_at - c_es:,.2f}")

        with tab_cfg:
            new_name = st.text_input("Nome", value=projeto['titulo'])
            if st.button("Renomear"):
                projeto['titulo'] = new_name
                db.salvar_projetos(st.session_state.db_pqi); st.rerun()
