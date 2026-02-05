import streamlit as st
import pandas as pd
from datetime import datetime, date
import os
import io
import plotly.express as px
import database as db

# --- CONFIGURAÇÕES E ESTILOS ---
ROADMAP = [
    {"id": 1, "nome": "Triagem & GUT"}, {"id": 2, "nome": "Escopo & Charter"},
    {"id": 3, "nome": "Autorização Sponsor"}, {"id": 4, "nome": "Coleta & Impedimentos"},
    {"id": 5, "nome": "Modelagem & Piloto"}, {"id": 6, "nome": "Migração (Go-Live)"},
    {"id": 7, "nome": "Acompanhamento/Ajuste"}, {"id": 8, "nome": "Padronização & POP"}
]

MOTIVOS_PADRAO = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna (Sem Dash)"]

def exibir(user_role="OPERACIONAL"):
    # Estilo CSS Upgrade
    st.markdown("""
    <style>
        .ponto-regua { width: 38px; height: 38px; border-radius: 50%; background: #f1f5f9; display: flex; 
                       align-items: center; justify-content: center; font-weight: bold; color: #94a3b8; 
                       margin: 0 auto; border: 2px solid #e2e8f0; }
        .ponto-check { background: #10b981 !important; color: white !important; border-color: #10b981 !important; }
        .ponto-atual { background: #002366 !important; color: white !important; border-color: #002366 !important; 
                       box-shadow: 0 0 12px rgba(0, 35, 102, 0.4); transform: scale(1.1); }
        .label-regua { font-size: 10px; text-align: center; font-weight: 700; margin-top: 8px; color: #1e293b; height: 35px; line-height: 1.1; }
        .roi-box { background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1px solid #bbf7d0; 
                   padding: 15px; border-radius: 12px; color: #166534; text-align: center; }
        .card-lembrete { padding: 12px; border-radius: 8px; margin-bottom: 8px; border-left: 5px solid #ccc; background: #f8fafc; box-shadow: 0 2px 4px rgba(0,0,0,0.03); }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO SEGURO
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- CABEÇALHO E TABS PRINCIPAIS ---
    st.title("🚀 Sistema de Gestão de Processos (PQI)")
    tab_diretoria, tab_projetos = st.tabs(["📊 DASHBOARD GERAL", "🛠️ OPERAÇÃO DO PROCESSO"])

    # --- TAB 1: VISÃO DIRETORIA ---
    with tab_diretoria:
        projs_all = st.session_state.db_pqi
        if projs_all:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Projetos", len(projs_all))
            c2.metric("Ativos 🚀", len([p for p in projs_all if p.get('status') == 'Ativo']))
            c3.metric("Concluídos ✅", len([p for p in projs_all if p.get('status') == 'Concluído']))
            
            df_geral = pd.DataFrame([{"Projeto": p['titulo'], "Fase": p['fase'], "Status": p.get('status', 'Ativo')} for p in projs_all])
            
            col_g1, col_g2 = st.columns(2)
            fig_status = px.pie(df_geral, names='Status', title="Distribuição por Status", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            col_g1.plotly_chart(fig_status, use_container_width=True)
            
            fig_fases = px.bar(df_geral, x='Projeto', y='Fase', title="Fase Atual por Projeto", color='Fase', color_continuous_scale='Blues')
            col_g2.plotly_chart(fig_fases, use_container_width=True)
        else:
            st.info("Nenhum dado para exibir no Dashboard.")

    # --- TAB 2: GESTÃO OPERACIONAL ---
    with tab_projetos:
        c_t1, c_t2, c_t3 = st.columns([1.2, 2, 1])
        with c_t1:
            status_filtro = st.radio("Filtro:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], horizontal=True)
            st_map = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
        
        projs_f = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == st_map[status_filtro]]
        
        projeto = None
        with c_t2:
            if projs_f:
                escolha = st.selectbox("Selecione o Projeto PQI:", [p['titulo'] for p in projs_f])
                projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
        
        with c_t3:
            if user_role in ["ADM", "GERENTE"]:
                if st.button("➕ NOVO PROCESSO", use_container_width=True, type="primary"):
                    novo = {
                        "titulo": f"Novo Processo {len(st.session_state.db_pqi)+1}", 
                        "fase": 1, "status": "Ativo", "notas": [], 
                        "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, 
                        "lembretes": [], "custo_atual": 0.0, "custo_estimado": 0.0, "analise_mercado": ""
                    }
                    st.session_state.db_pqi.append(novo)
                    db.salvar_projetos(st.session_state.db_pqi)
                    st.rerun()

        if projeto:
            # --- RÉGUA DE EVOLUÇÃO ---
            st.write("---")
            cols_r = st.columns(8)
            for i, etapa in enumerate(ROADMAP):
                n = i + 1
                cl = "ponto-regua"
                txt = str(n)
                if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                elif n == projeto['fase']: cl += " ponto-atual"
                with cols_r[i]:
                    st.markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)

            # --- SUB-TABS DO PROJETO ---
            t_ex, t_lem, t_dos, t_merc, t_cfg = st.tabs(["🚀 Execução", "📅 Lembretes", "📂 Dossiê", "🔍 Mercado & ROI", "⚙️ Gestão"])

            with t_ex:
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.subheader(f"📍 Fase {projeto['fase']}: {ROADMAP[projeto['fase']-1]['nome']}")
                    with st.popover("➕ Adicionar Registro ao Dossiê"):
                        sel_mot = st.selectbox("Assunto", MOTIVOS_PADRAO)
                        setor = st.text_input("Responsável").upper()
                        desc = st.text_area("O que foi executado?")
                        if st.button("Gravar no Banco"):
                            nova_nota = {"motivo": sel_mot, "setor": setor, "texto": desc, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase']}
                            projeto.setdefault('notas', []).append(nova_nota)
                            db.salvar_projetos(st.session_state.db_pqi)
                            st.rerun()
                    
                    for n in reversed(projeto.get('notas', [])):
                        if n.get('fase_origem') == projeto['fase']:
                            st.info(f"**{n['motivo']}** - {n['setor']} ({n['data']})\n\n{n['texto']}")

                with c2:
                    st.markdown("#### 🕹️ Fluxo")
                    if user_role in ["ADM", "GERENTE"]:
                        if projeto['fase'] < 8:
                            if st.button("▶️ AVANÇAR ETAPA", use_container_width=True, type="primary"):
                                projeto['fase'] += 1
                                projeto['historico'][str(projeto['fase'])] = datetime.now().strftime("%d/%m/%Y")
                                db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                        if projeto['fase'] > 1:
                            if st.button("⏪ RECUAR ETAPA", use_container_width=True):
                                projeto['fase'] -= 1
                                db.salvar_projetos(st.session_state.db_pqi); st.rerun()

            with t_lem:
                st.subheader("📅 Próximas Ações e Lembretes")
                with st.popover("➕ Agendar Lembrete"):
                    txt_lem = st.text_input("Tarefa")
                    data_lem = st.date_input("Data Limite", min_value=date.today())
                    if st.button("Salvar Lembrete"):
                        projeto.setdefault('lembretes', []).append({"texto": txt_lem, "data": data_lem.strftime("%d/%m/%Y"), "status": "Pendente"})
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

                for idx, lem in enumerate(projeto.get('lembretes', [])):
                    d_venc = datetime.strptime(lem['data'], "%d/%m/%Y").date()
                    cor = "#ef4444" if d_venc < date.today() else ("#facc15" if d_venc == date.today() else "#3b82f6")
                    st.markdown(f'<div class="card-lembrete" style="border-left-color: {cor}"><b>{lem["data"]}</b>: {lem["texto"]}</div>', unsafe_allow_html=True)
                    if st.button("✅ Concluir", key=f"lem_{idx}"):
                        projeto['lembretes'].pop(idx)
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()

            with t_dos:
                st.subheader("📂 Dossiê Completo")
                df_dos = pd.DataFrame(projeto.get('notas', []))
                if not df_dos.empty:
                    st.dataframe(df_dos[['data', 'fase_origem', 'motivo', 'setor', 'texto']], use_container_width=True)
                    towrite = io.BytesIO()
                    df_dos.to_excel(towrite, index=False, engine='xlsxwriter')
                    st.download_button("📥 Baixar Dossiê Excel", towrite.getvalue(), f"Dossie_{projeto['titulo']}.xlsx")
                else:
                    st.info("Nenhum histórico registrado.")

            with t_merc:
                st.subheader("💰 Inteligência e ROI")
                cm1, cm2 = st.columns(2)
                with cm1:
                    at = st.number_input("Custo Mensal Atual (R$)", value=float(projeto.get('custo_atual', 0)))
                    es = st.number_input("Custo Solução Nova (R$)", value=float(projeto.get('custo_estimado', 0)))
                    projeto['custo_atual'], projeto['custo_estimado'] = at, es
                    st.markdown(f'<div class="roi-box"><b>Economia Mensal:</b><br><span style="font-size:20px">R$ {at-es:,.2f}</span></div>', unsafe_allow_html=True)
                with cm2:
                    analise = st.text_area("Análise de Mercado/Benchmarking", value=projeto.get('analise_mercado', ""), height=150)
                    projeto['analise_mercado'] = analise
                if st.button("💾 Salvar Business Case"):
                    db.salvar_projetos(st.session_state.db_pqi); st.success("Salvo!")

            with t_cfg:
                if user_role in ["ADM", "GERENTE"]:
                    projeto['titulo'] = st.text_input("Nome do Projeto", projeto['titulo'])
                    projeto['status'] = st.selectbox("Status", ["Ativo", "Concluído", "Pausado"], index=["Ativo", "Concluído", "Pausado"].index(projeto.get('status', 'Ativo')))
                    if st.button("💾 Aplicar Alterações"):
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                    st.divider()
                    if st.button("🗑️ EXCLUIR PROCESSO", type="secondary"):
                        st.session_state.db_pqi.remove(projeto)
                        db.salvar_projetos(st.session_state.db_pqi); st.rerun()
