import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import os
import io
from modulos import database as db

# --- CONFIGURAÇÕES GERAIS ---
UPLOAD_DIR = "anexos_pqi"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

MAPA_MODULOS = {
    "🏗️ Manutenção": "manutencao",
    "🎯 Processos": "processos",
    "📄 RH Docs": "rh",
    "📊 Operação": "operacao",
    "🚗 Minha Spin": "spin",
    "🚌 Passagens": "passagens",
    "🎫 Tickets": "tickets",
}

ROADMAP = [
    {"id": 1, "nome": "Triagem & GUT"}, {"id": 2, "nome": "Escopo & Charter"},
    {"id": 3, "nome": "Autorização Sponsor"}, {"id": 4, "nome": "Coleta & Impedimentos"},
    {"id": 5, "nome": "Modelagem & Piloto"}, {"id": 6, "nome": "Migração (Go-Live)"},
    {"id": 7, "nome": "Acompanhamento/Ajuste"}, {"id": 8, "nome": "Padronização & POP"}
]

MOTIVOS_PADRAO = ["Reunião", "Pedido de Posicionamento", "Elaboração de Documentos", "Anotação Interna (Sem Dash)"]

# --- FUNÇÕES UTILITÁRIAS ---
def formatar_duracao_h_min(minutos):
    if pd.isna(minutos) or minutos <= 0: return "0min"
    horas = int(minutos // 60)
    mins = int(minutos % 60)
    return f"{horas}H:{mins:02d}min" if horas > 0 else f"{mins}min"

def exibir(is_adm):
    if not is_adm:
        st.error("🚫 Acesso restrito aos administradores.")
        return

    # --- 1. ESTILO CSS ---
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

    # --- 2. CARREGAMENTO E INICIALIZAÇÃO ---
    usuarios_dict = db.carregar_usuarios_firebase()
    departamentos = db.carregar_departamentos()
    motivos = db.carregar_motivos()
    logs_esforco = db.carregar_esforco()

    if 'db_pqi' not in st.session_state:
        dados_pqi = db.carregar_projetos()
        st.session_state.db_pqi = dados_pqi if isinstance(dados_pqi, list) else []

    if 'situacoes_diarias' not in st.session_state:
        dados_diario = db.carregar_diario()
        st.session_state.situacoes_diarias = dados_diario if isinstance(dados_diario, list) else []

    def salvar_seguro_pqi():
        try:
            db.salvar_projetos(st.session_state.db_pqi)
            db.salvar_diario(st.session_state.situacoes_diarias)
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

    # --- 3. MENU PRINCIPAL ---
    st.title("⚙️ Central de Comando")
    
    menu = st.segmented_control(
        "Gerenciamento:", 
        ["🔴 MONITOR", "🚀 PROJETOS PQI", "📊 DASHBOARD", "👥 USUÁRIOS", "🏢 DEPTOS", "⚙️ MOTIVOS"], 
        default="🔴 MONITOR"
    )

    # --- SEÇÃO 1: MONITORAMENTO ---
    if menu == "🔴 MONITOR":
        st.subheader("Monitoramento em Tempo Real")
        ativos = [a for a in logs_esforco if a.get('status') == 'Em andamento']
        
        if ativos:
            for atv in ativos:
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                    c1.markdown(f"👤 **{atv['usuario']}**")
                    c2.markdown(f"📌 {atv['motivo']}\n<small>{atv.get('detalhes', '')}</small>", unsafe_allow_html=True)
                    
                    try:
                        inicio_dt = datetime.fromisoformat(atv['inicio']).replace(tzinfo=None)
                        decorrido = (datetime.now() - inicio_dt).seconds // 60
                        c3.metric("Tempo", f"{decorrido} min")
                    except: c3.write("⏰ N/A")
                    
                    key_btn = f"adm_stop_{atv['usuario']}_{atv['inicio']}".replace(":", "")
                    if c4.button("🛑 Encerrar", key=key_btn):
                        agora = datetime.now()
                        duracao = (agora - inicio_dt).total_seconds() / 60
                        for a in logs_esforco:
                            if a['usuario'] == atv['usuario'] and a['status'] == 'Em andamento':
                                a['status'] = 'Finalizado'
                                a['fim'] = agora.isoformat()
                                a['duracao_min'] = round(duracao, 2)
                        db.salvar_esforco(logs_esforco)
                        st.success(f"Finalizado: {atv['usuario']}")
                        st.rerun()
        else:
            st.info("Ninguém online no momento.")

    # --- SEÇÃO 2: PROJETOS PQI (INTEGRADO) ---
    elif menu == "🚀 PROJETOS PQI":
        tab_dash_pqi, tab_gestao_pqi, tab_operacao_pqi = st.tabs(["📊 DASHBOARD GERAL", "⚙️ GESTÃO", "🚀 OPERAÇÃO"])

        with tab_dash_pqi:
            projs = st.session_state.db_pqi
            sub_d1, sub_d2 = st.tabs(["📈 Ativos", "✅ Entregues"])
            
            with sub_d1:
                ativos_pqi = [p for p in projs if p.get('status') != "Concluído"]
                if ativos_pqi:
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f'<div class="metric-card"><div class="metric-label">Projetos Ativos</div><div class="metric-value">{len(ativos_pqi)}</div></div>', unsafe_allow_html=True)
                    c2.markdown(f'<div class="metric-card"><div class="metric-label">Total de Ações</div><div class="metric-value">{sum(len(p.get("notas", [])) for p in ativos_pqi)}</div></div>', unsafe_allow_html=True)
                    
                    todas_notas = [n for p in ativos_pqi for n in p.get('notas', [])]
                    df_notas = pd.DataFrame(todas_notas)
                    gargalo = df_notas['depto'].mode().iloc[0] if not df_notas.empty else "N/A"
                    c3.markdown(f'<div class="metric-card"><div class="metric-label">Gargalo (Depto)</div><div class="metric-value" style="font-size:18px">{gargalo}</div></div>', unsafe_allow_html=True)
                    
                    df_at = pd.DataFrame([{"Projeto": p['titulo'], "Esforço": len(p.get('notas', []))} for p in ativos_pqi])
                    st.bar_chart(df_at.set_index("Projeto")["Esforço"])
                else: st.info("Sem projetos ativos.")

            with sub_d2:
                concluidos = [p for p in projs if p.get('status') == "Concluído"]
                if concluidos:
                    st.dataframe(pd.DataFrame([{"Projeto": p['titulo'], "Data": p.get('data_conclusao', 'S/D')} for p in concluidos]), use_container_width=True)
                else: st.info("Nenhum projeto entregue.")

        with tab_gestao_pqi:
            if st.button("➕ CRIAR NOVO PROJETO PQI", type="primary", use_container_width=True):
                st.session_state.db_pqi.append({"titulo": f"Novo Projeto {len(st.session_state.db_pqi) + 1}", "fase": 1, "status": "Ativo", "notas": [], "lembretes": [], "pastas_virtuais": {}, "motivos_custom": []})
                salvar_seguro_pqi(); st.rerun()
            
            st.divider()
            for i, p in enumerate(st.session_state.db_pqi):
                with st.expander(f"Configurar: {p['titulo']}"):
                    p['titulo'] = st.text_input("Nome", p['titulo'], key=f"p_t_{i}")
                    p['status'] = st.selectbox("Status", ["Ativo", "Concluído", "Pausado"], index=["Ativo", "Concluído", "Pausado"].index(p.get('status', 'Ativo')), key=f"p_s_{i}")
                    if st.button("🗑️ Excluir Projeto", key=f"p_del_{i}"):
                        st.session_state.db_pqi.pop(i); salvar_seguro_pqi(); st.rerun()

        
        with tab_operacao_pqi:
            # Filtro robusto: considera "Ativo" como padrão se o campo não existir
            filtrados = [p for p in st.session_state.db_pqi if p.get('status', 'Ativo') == "Ativo"]
            
            if filtrados:
                # Adicionamos uma key única para evitar conflitos de widget
                escolha = st.selectbox("Selecione o Projeto:", [p['titulo'] for p in filtrados], key="sel_proj_operacao")
                
                # Busca segura usando next com valor default None
                projeto = next((p for p in filtrados if p['titulo'] == escolha), None)
                
                if projeto:
                    # Regua de Roadmap
                    cols_r = st.columns(8)
                    for i, etapa in enumerate(ROADMAP):
                        n, cl, txt = i+1, "ponto-regua", str(i+1)
                        if n < projeto['fase']: cl += " ponto-check"; txt = "✔"
                        elif n == projeto['fase']: cl += " ponto-atual"
                        cols_r[i].markdown(f'<div class="{cl}">{txt}</div><div class="label-regua">{etapa["nome"]}</div>', unsafe_allow_html=True)
                    
                    t_exec, t_dossie = st.tabs(["📝 Execução", "📁 Dossiê"])
            
            else:
                st.info("Nenhum projeto ativo encontrado. Ative ou crie um na aba GESTÃO.")
                
                with t_exec:
                    c1, c2 = st.columns([2,1])
                    with c1:
                        st.write(f"### Etapa {projeto['fase']}")
                        with st.popover("➕ Novo Registro"):
                            mot = st.selectbox("Motivo", MOTIVOS_PADRAO + projeto.get('motivos_custom', []), key=f"m_{projeto['titulo']}")
                            dep = st.selectbox("Departamento", departamentos, key=f"d_{projeto['titulo']}")
                            dsc = st.text_area("Descrição")
                            if st.button("Salvar Registro"):
                                projeto['notas'].append({"motivo": mot, "depto": dep, "texto": dsc, "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "fase_origem": projeto['fase']})
                                salvar_seguro_pqi(); st.rerun()
                        
                        for n in reversed(projeto['notas']):
                            if n.get('fase_origem') == projeto['fase']:
                                with st.expander(f"📌 {n['motivo']} - {n['data']}"): st.write(n['texto'])
                    with c2:
                        if st.button("▶️ AVANÇAR", use_container_width=True) and projeto['fase'] < 8:
                            projeto['fase'] += 1; salvar_seguro_pqi(); st.rerun()
                        if st.button("⏪ RECUAR", use_container_width=True) and projeto['fase'] > 1:
                            projeto['fase'] -= 1; salvar_seguro_pqi(); st.rerun()
                
                with t_dossie:
                    # Upload Simplificado para Firestore
                    nome_pasta = st.text_input("Nova Pasta Virtual")
                    if st.button("Criar Pasta"):
                        projeto.setdefault('pastas_virtuais', {})[nome_pasta] = []
                        salvar_seguro_pqi(); st.rerun()
                    
                    for p_nome, arqs in projeto.get('pastas_virtuais', {}).items():
                        with st.expander(f"📁 {p_nome}"):
                            up = st.file_uploader("Subir", key=f"up_{p_nome}")
                            if up and st.button("Confirmar Upload", key=f"btn_up_{p_nome}"):
                                file_id = f"{datetime.now().timestamp()}_{up.name}"
                                if db.salvar_arquivo_firestore(file_id, up.getvalue()):
                                    arqs.append({"nome": up.name, "file_id": file_id, "data": datetime.now().strftime("%d/%m/%Y")})
                                    salvar_seguro_pqi(); st.rerun()
                            for a in arqs:
                                st.write(f"📄 {a['nome']}")

    # --- SEÇÃO 3: DASHBOARD BI (ESFORÇO GERAL) ---
    elif menu == "📊 DASHBOARD":
        st.subheader("📊 BI - Esforço Operacional")
        df = pd.DataFrame(logs_esforco)
        if not df.empty and 'status' in df.columns:
            df_fin = df[df['status'] == 'Finalizado'].copy()
            if not df_fin.empty:
                col_f1, col_f2 = st.columns(2)
                user_f = col_f1.selectbox("Filtrar Usuário", ["Todos"] + sorted(df_fin['usuario'].unique().tolist()))
                if user_f != "Todos": df_fin = df_fin[df_fin['usuario'] == user_f]

                m1, m2, m3 = st.columns(3)
                m1.metric("Atividades", len(df_fin))
                m2.metric("Tempo Total", formatar_duracao_h_min(df_fin['duracao_min'].sum()))
                m3.metric("Média", f"{df_fin['duracao_min'].mean():.1f} min")

                g1, g2 = st.columns(2)
                with g1:
                    st.plotly_chart(px.bar(df_fin.groupby('motivo')['duracao_min'].sum().reset_index(), x='motivo', y='duracao_min', title="Tempo por Motivo"), use_container_width=True)
                with g2:
                    st.plotly_chart(px.pie(df_fin, names='usuario', title="Distribuição"), use_container_width=True)
        else: st.warning("Sem dados de esforço.")

    # --- SEÇÃO 4: USUÁRIOS ---
    elif menu == "👥 USUÁRIOS":
        st.subheader("Gestão de Colaboradores")
        with st.expander("➕ Novo Colaborador"):
            with st.form("f_user"):
                u_id = st.text_input("ID Login")
                u_nome = st.text_input("Nome")
                u_cargo = st.selectbox("Cargo", ["ADM", "OPERACIONAL", "GERÊNCIA"])
                u_depto = st.selectbox("Departamento", departamentos)
                if st.form_submit_button("Salvar"):
                    db.salvar_usuario(u_id, {"nome": u_nome, "role": u_cargo, "depto": u_depto, "modulos": [], "ativo": True})
                    st.success("Criado!"); st.rerun()
        
        for uid, info in usuarios_dict.items():
            with st.container(border=True):
                c_u1, c_u2 = st.columns([4, 1])
                c_u1.write(f"**{info['nome']}** ({uid}) - {info['role']}")
                if c_u2.button("🗑️", key=f"del_u_{uid}"):
                    st.info("Exclusão lógica: Desative no banco.")

    # --- SEÇÃO 5: DEPTOS ---
    elif menu == "🏢 DEPTOS":
        st.subheader("Departamentos")
        novo_d = st.text_input("Novo Setor")
        if st.button("Adicionar"):
            departamentos.append(novo_d.upper())
            db.salvar_departamentos(list(set(departamentos)))
            st.rerun()
        st.write(sorted(departamentos))

    # --- SEÇÃO 6: MOTIVOS ---
    elif menu == "⚙️ MOTIVOS":
        st.subheader("Motivos Globais")
        novo_m = st.text_input("Nova Categoria")
        if st.button("Salvar Motivo"):
            motivos.append(novo_m.upper())
            db.salvar_motivos(list(set(motivos)))
            st.rerun()
        st.table(pd.DataFrame({"Motivos Habilitados": motivos}))
