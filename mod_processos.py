import streamlit as st
import pandas as pd
from datetime import datetime, date
import os
import io
import database as db
import plotly.express as px

# --- CONFIGURAÇÕES DO ROADMAP ---
ROADMAP = [
    {"id": 1, "nome": "Triagem & GUT"}, {"id": 2, "nome": "Escopo & Charter"},
    {"id": 3, "nome": "Autorização Sponsor"}, {"id": 4, "nome": "Coleta & Impedimentos"},
    {"id": 5, "nome": "Modelagem & Piloto"}, {"id": 6, "nome": "Migração (Go-Live)"},
    {"id": 7, "nome": "Acompanhamento/Ajuste"}, {"id": 8, "nome": "Padronização & POP"}
]

MOTIVOS_PADRAO = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna (Sem Dash)"]

def exibir(user_role="OPERACIONAL"):
    # 1. ESTILO CSS PREMIUM
    st.markdown("""
    <style>
        .main-pqi { background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .ponto-regua { width: 40px; height: 40px; border-radius: 50%; background: #f1f5f9; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8; margin: 0 auto; border: 2px solid #e2e8f0; transition: 0.3s; }
        .ponto-check { background: #10b981; color: white; border-color: #10b981; }
        .ponto-atual { background: #002366; color: white; border-color: #002366; box-shadow: 0 0 15px rgba(0, 35, 102, 0.3); transform: scale(1.1); }
        .label-regua { font-size: 11px; text-align: center; font-weight: 700; margin-top: 8px; color: #1e293b; line-height: 1.2; height: 40px; }
        .card-lembrete { padding: 10px; border-radius: 8px; margin-bottom: 8px; border-left: 5px solid #ccc; background: #f8fafc; }
        .roi-box { background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1px solid #bbf7d0; padding: 20px; border-radius: 12px; color: #166534; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

    # 2. CARREGAMENTO
    if 'db_pqi' not in st.session_state:
        st.session_state.db_pqi = db.carregar_projetos()

    # --- CABEÇALHO E FILTROS ---
    c_f1, c_f2, c_f3 = st.columns([1.2, 2, 1])
    with c_f1:
        status_sel = st.segmented_control("Status:", ["🚀 Ativos", "✅ Concluídos", "⏸️ Pausados"], default="🚀 Ativos")
        st_map = {"🚀 Ativos": "Ativo", "✅ Concluídos": "Concluído", "⏸️ Pausados": "Pausado"}
    
    projs_f = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == st_map[status_sel]]

    with c_f2:
        if projs_f:
            escolha = st.selectbox("Selecione o Projeto PQI:", [p['titulo'] for p in projs_f])
            projeto = next(p for p in st.session_state.db_pqi if p['titulo'] == escolha)
        else:
            st.info("Nenhum processo nesta categoria.")
            projeto = None

    with c_f3:
        if user_role in ["ADM", "GERENTE"]:
            if st.button("➕ NOVO PROCESSO", use_container_width=True, type="primary"):
                novo = {
                    "titulo": f"Novo Processo {len(st.session_state.db_pqi)+1}", 
                    "fase": 1, "status": "Ativo", "notas": [], 
                    "historico": {"1": datetime.now().strftime("%d/%m/%Y")}, 
                    "lembretes": [], "custo_atual": 0.0, "custo_estimado": 0.0, "analise_mercado": ""
                }
                st.session_state.db_pqi.append(novo)
                db.salvar_projetos(st.session_state.db_pqi); st.rerun()

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

        # --- ABAS ---
        t1, t2, t3, t4, t5 = st.tabs(["🚀 Execução", "📅 Lembretes", "📂 Dossiê", "📊 Dashboards", "🔍 Mercado & ROI"])

        with t1:
            c_ex1, c_ex2 = st.columns([2, 1])
            with c_ex1:
                st.subheader(f"📍 Fase Atual: {ROADMAP[projeto['fase']-1]['nome']}")
                with st.expander("📝 Adicionar Novo Registro", expanded=False):
                    with st.form("form_nota"):
                        moti = st.selectbox("Assunto", MOTIVOS_PADRAO)
                        setor = st.text_input("Responsável/Setor").upper()
                        obs = st.text_area("Descrição da Atividade")
                        if st.form_submit_button("Salvar no Dossiê"):
                            nova = {"motivo": moti, "setor": setor, "texto": obs, "data": datetime.now().strftime("%d/%m/%Y"), "fase_origem": projeto['fase']}
                            projeto.setdefault('notas', []).append(nova)
                            db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                
                # Exibição de Notas da Fase
                notas_fase = [n for n in projeto.get('notas', []) if n.get('fase_origem') == projeto['fase']]
                for n in reversed(notas_fase):
                    st.info(f"**{n['motivo']}** ({n['data']}) - {n['setor']}\n\n{n['texto']}")

            with c_ex2:
                st.markdown("### 🕹️ Gestão de Fluxo")
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

        with t2:
            st.subheader("📅 Gestão de Lembretes")
            with st.popover("➕ Agendar Tarefa"):
                t_txt = st.text_input("O que precisa ser feito?")
                t_data = st.date_input("Para quando?", min_value=date.today())
                if st.button("Confirmar Lembrete"):
                    projeto.setdefault('lembretes', []).append({"texto": t_txt, "data_hora": t_data.strftime("%d/%m/%Y"), "status": "Pendente"})
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()
            
            for idx, lem in enumerate(projeto.get('lembretes', [])):
                d_obj = datetime.strptime(lem['data_hora'], "%d/%m/%Y").date()
                cor = "#ef4444" if d_obj < date.today() else ("#facc15" if d_obj == date.today() else "#3b82f6")
                icon = "🚨" if d_obj < date.today() else "⏰"
                
                st.markdown(f"""<div class="card-lembrete" style="border-left-color: {cor}">
                    {icon} <b>{lem['data_hora']}</b>: {lem['texto']}
                </div>""", unsafe_allow_html=True)
                if st.button("✅ Concluir", key=f"btn_lem_{idx}"):
                    projeto['lembretes'].pop(idx)
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()

        with t3:
            st.subheader("📂 Dossiê de Esforço")
            df_dos = pd.DataFrame(projeto.get('notas', []))
            if not df_dos.empty:
                st.dataframe(df_dos[['data', 'fase_origem', 'motivo', 'setor', 'texto']], use_container_width=True)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_dos.to_excel(writer, index=False, sheet_name='Dossie')
                st.download_button("📥 Exportar Dossiê para Excel", output.getvalue(), f"Dossie_{projeto['titulo']}.xlsx")

        with t4:
            st.subheader("📊 Análise de Produtividade")
            if projeto.get('notas'):
                df_kpi = pd.DataFrame(projeto['notas'])
                c_k1, c_k2 = st.columns(2)
                fig_mot = px.pie(df_kpi, names='motivo', title="Distribuição de Esforço", hole=0.4)
                c_k1.plotly_chart(fig_mot, use_container_width=True)
                
                esforco_fase = df_kpi['fase_origem'].value_counts().reset_index()
                fig_bar = px.bar(esforco_fase, x='fase_origem', y='count', title="Volume de Ações por Fase")
                c_k2.plotly_chart(fig_bar, use_container_width=True)

        with t5:
            st.subheader("🔍 Inteligência de Negócio")
            cm1, cm2 = st.columns(2)
            with cm1:
                st.markdown("#### 💰 Calculadora de ROI")
                c_at = st.number_input("Custo Mensal Atual (R$)", value=float(projeto.get('custo_atual', 0)))
                c_es = st.number_input("Custo Solução Nova (R$)", value=float(projeto.get('custo_estimado', 0)))
                projeto['custo_atual'] = c_at
                projeto['custo_estimado'] = c_es
                econ = c_at - c_es
                st.markdown(f'<div class="roi-box"><h3>Economia Estimada</h3><h2>R$ {econ:,.2f}</h2><p>por mês</p></div>', unsafe_allow_html=True)
            
            with cm2:
                st.markdown("#### 🏢 Benchmarking / Web Insights")
                merca = st.text_area("Análise de Fornecedores e Mercado", value=projeto.get('analise_mercado', ""), height=200)
                projeto['analise_mercado'] = merca
            
            if st.button("💾 Salvar Business Case"):
                db.salvar_projetos(st.session_state.db_pqi); st.success("Estudo salvo!")

        # GESTÃO DO PROJETO (Admin)
        if user_role == "ADM":
            with st.expander("⚙️ Configurações Críticas"):
                novo_nome = st.text_input("Renomear Projeto", projeto['titulo'])
                if st.button("Atualizar Nome"):
                    projeto['titulo'] = novo_nome
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()
                if st.button("🗑️ DELETAR PROJETO", type="secondary"):
                    st.session_state.db_pqi.remove(projeto)
                    db.salvar_projetos(st.session_state.db_pqi); st.rerun()
