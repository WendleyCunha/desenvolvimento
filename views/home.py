import streamlit as st
import pandas as pd
from datetime import datetime
from modulos.utils_tempo import agora_br, agora_iso, parse_dt_safe
from modulos import database as db

def formatar_duracao_h_min(minutos):
    if pd.isna(minutos) or minutos <= 0: return "0min"
    horas = int(minutos // 60)
    mins = int(minutos % 60)
    return f"{horas}H:{mins:02d}min" if horas > 0 else f"{mins}min"

def finalizar_atividade_atual(nome_usuario):
    logs = db.carregar_esforco()
    mudou = False
    agora = agora_br()
    for idx, act in enumerate(logs):
        if act['usuario'] == nome_usuario and act['status'] == 'Em andamento':
            logs[idx]['fim'] = agora.isoformat()
            logs[idx]['status'] = 'Finalizado'
            inicio_dt = parse_dt_safe(act.get('inicio'))
            duracao = (agora - inicio_dt).total_seconds() / 60
            logs[idx]['duracao_min'] = round(duracao, 2)
            mudou = True
    if mudou:
        db.salvar_esforco(logs)

def exibir(user_info):
    # --- Estilos Aprimorados ---
    st.markdown("""
        <style>
        .reminder-card, .diary-card {
            background: #ffffff; padding: 16px; border-radius: 12px;
            margin-bottom: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
            border-left: 6px solid;
        }
        .reminder-card { border-left-color: #ef4444; }
        .diary-card { border-left-color: #3b82f6; }
        .status-tag { font-size: 0.75rem; font-weight: 800; text-transform: uppercase; }
        </style>
    """, unsafe_allow_html=True)
    
    st.title(f"Olá, {user_info['nome']}! 👋")
        
    # Carga de dados
    projs = db.carregar_projetos()
    diario = db.carregar_diario()
    atividades_log = db.carregar_esforco()
    motivos_gestao = db.carregar_motivos()
    hoje_dt = datetime.now().date()
    
    tab_esforco, tab_pendentes, tab_agenda, tab_novo, tab_perfil = st.tabs([
        "⚡ Esforço Hoje",
        "🚀 Pendências",
        "📅 Agenda",
        "➕ Novo",
        "👤 Perfil"
    ])

    # --- ABA 1: ESFORÇO ---
    with tab_esforco:
        atv_ativa = next((a for a in atividades_log if a['usuario'] == user_info['nome'] and a['status'] == 'Em andamento'), None)
        c1, c2 = st.columns([1, 1.2])
        
        with c1:
            if atv_ativa:
                st.info(f"🚀 **Ativo agora:**\n\n**{atv_ativa['motivo']}**")
        
                try:
                    inicio_dt = parse_dt_safe(atv_ativa.get('inicio'))
                    if inicio_dt:
                        decorrido = int((agora_br() - inicio_dt).total_seconds() // 60)
                        st.caption(f"Iniciado às {inicio_dt.strftime('%H:%M')} ({decorrido} min decorridos)")
                    else:
                        st.caption("Iniciado agora")
        
                except Exception as e:
                    st.caption("Erro ao calcular tempo da atividade")
        
                if st.button("🏁 FINALIZAR TAREFA", type="secondary", use_container_width=True):
                    finalizar_atividade_atual(user_info['nome'])
                    st.rerun()
            else: 
                st.success("✨ Você está livre no momento!")
        
        with c2:
            with st.expander("Iniciar nova atividade", expanded=not atv_ativa):
                motivo_sel = st.selectbox("Categoria:", motivos_gestao)
                detalhes   = st.text_input("Observação ou Ticket:")
            
                usar_horario_manual = st.checkbox("⏰ Ajustar horário de início manualmente")
                if usar_horario_manual:
                    col_h, col_m = st.columns(2)
                    hora_manual = col_h.number_input("Hora", 0, 23, value=agora_br().hour)
                    min_manual  = col_m.number_input("Minuto", 0, 59, value=agora_br().minute)
            
                if st.button("INICIAR AGORA ⚡", type="primary", use_container_width=True):
                    finalizar_atividade_atual(user_info['nome'])
            
                    if usar_horario_manual:
                        inicio_ref = agora_br().replace(hour=int(hora_manual), minute=int(min_manual), second=0)
                    else:
                        inicio_ref = agora_br()
            
                    atividades_log.append({
                        "usuario":     user_info['nome'],
                        "motivo":      motivo_sel,
                        "detalhes":    detalhes,
                        "inicio":      inicio_ref.isoformat(),
                        "fim":         None,
                        "status":      "Em andamento",
                        "duracao_min": 0
                    })
                    db.salvar_esforco(atividades_log)
                    st.rerun()

        st.subheader("Histórico de Hoje")
        meu_hist = [a for a in atividades_log if a['usuario'] == user_info['nome']]
        if meu_hist:
            df_meu = pd.DataFrame(meu_hist)
            df_meu['inicio_dt'] = df_meu['inicio'].apply(parse_dt_safe)
            df_meu = df_meu[df_meu['inicio_dt'].apply(
                lambda x: x.date() == hoje_dt if x is not None else False
            )].sort_values('inicio_dt', ascending=False)
            
            if not df_meu.empty:
                df_meu['Hora'] = df_meu['inicio_dt'].dt.strftime('%H:%M')
                df_meu['Tempo'] = df_meu['duracao_min'].apply(formatar_duracao_h_min)
                st.dataframe(df_meu[['Hora', 'motivo', 'detalhes', 'status', 'Tempo']], use_container_width=True, hide_index=True)

    # --- ABA 2: PENDÊNCIAS ---
    with tab_pendentes:
        tipo_pnd = st.radio("Filtro visual:", ["Minhas Pendências", "Visão Equipe"], horizontal=True)
        col_pqi, col_dir = st.columns(2)
        
        with col_pqi:
            st.subheader("📌 Processos (PQI)")
            for p_idx, p in enumerate(projs):
                lembretes = p.get('lembretes', [])
                # Iteração reversa para permitir remoção segura
                for l_idx in range(len(lembretes) - 1, -1, -1):
                    l = lembretes[l_idx]
                    try:
                        data_l_dt = datetime.strptime(l['data_hora'].split(" ")[0], "%d/%m/%Y").date()
                        if data_l_dt <= hoje_dt:
                            atrasado = data_l_dt < hoje_dt
                            cor = "#f87171" if atrasado else "#ef4444"
                            st.markdown(f'''
                                <div class="reminder-card" style="border-left-color: {cor};">
                                    <span class="status-tag" style="color:{cor};">{"⚠️ Atrasada" if atrasado else "⏰ Hoje"}</span><br>
                                    <strong>{p["titulo"]}</strong><br>{l["texto"]}
                                </div>
                            ''', unsafe_allow_html=True)
                            if st.button(f"Concluir", key=f"btn_pqi_{p_idx}_{l_idx}", use_container_width=True):
                                p['lembretes'].pop(l_idx)
                                db.salvar_projetos(projs)
                                st.rerun()
                    except: continue

        with col_dir:
            st.subheader("📓 Diário de Bordo")
            for idx, sit in enumerate(diario):
                if sit.get('status') == "Pendente" and sit.get('lembrete') != "N/A":
                    if tipo_pnd == "Minhas Pendências" and sit.get('usuario') != user_info['nome']:
                        continue
                    try:
                        data_s_dt = datetime.strptime(sit['lembrete'].split(" ")[0], "%d/%m/%Y").date()
                        if data_s_dt <= hoje_dt:
                            atrasado = data_s_dt < hoje_dt
                            st.markdown(f'''
                                <div class="diary-card">
                                    <span class="status-tag" style="color:{'#ef4444' if atrasado else '#3b82f6'};">{"🚨 Atrasado" if atrasado else "📅 Agendado"}</span><br>
                                    <strong>{sit["depto"]}:</strong> {sit["solicitacao"]}<br>
                                    <small>Resp: {sit.get('usuario','S/I')}</small>
                                </div>
                            ''', unsafe_allow_html=True)
                            if st.button(f"Concluir", key=f"btn_dir_{idx}", use_container_width=True):
                                sit['status'] = "Executado"
                                db.salvar_diario(diario)
                                st.rerun()
                    except: continue

    # --- ABA 3: AGENDA ---
    with tab_agenda:
        tipo_age = st.radio("Visualizar compromissos de:", ["Apenas Meus", "Toda a Equipe"], horizontal=True)
        agenda_raw = []

        # 1. Dados do Diário
        for sit in diario:
            if sit.get('status') == "Pendente" and sit.get('lembrete', "N/A") != "N/A":
                try:
                    data_dt = datetime.strptime(sit['lembrete'].split(" ")[0], "%d/%m/%Y").date()
                    dono = sit.get('usuario', 'S/I')
                    if tipo_age == "Apenas Meus" and dono != user_info['nome']: continue
                    
                    if data_dt > hoje_dt:
                        agenda_raw.append({
                            "Data_Ref": data_dt, "Data": data_dt.strftime("%d/%m/%Y"),
                            "Origem": f"Diário ({sit['depto']})", "Tarefa": sit['solicitacao'], "Quem": dono
                        })
                except: continue

        # 2. Dados do PQI (Filtro por equipe se necessário, aqui mostramos tudo que for futuro)
        for p in projs:
            for l in p.get('lembretes', []):
                try:
                    data_dt = datetime.strptime(l['data_hora'].split(" ")[0], "%d/%m/%Y").date()
                    if data_dt > hoje_dt:
                        agenda_raw.append({
                            "Data_Ref": data_dt, "Data": data_dt.strftime("%d/%m/%Y"),
                            "Origem": f"PQI: {p['titulo']}", "Tarefa": l['texto'], "Quem": "Equipe"
                        })
                except: continue
        
        if agenda_raw:
            df_age = pd.DataFrame(agenda_raw).sort_values(by="Data_Ref")
            st.dataframe(df_age[['Data', 'Origem', 'Tarefa', 'Quem']], use_container_width=True, hide_index=True)
        else: 
            st.info("Nenhum compromisso futuro encontrado.")

    # --- ABA 4: NOVO AGENDAMENTO ---
    with tab_novo:
        st.subheader("🎯 Criar Novo Lembrete")
        with st.form("form_novo_v2"):
            tipo = st.selectbox("Vincular a:", ["Situações Diárias (Diário)", "Processos (PQI)"])
            txt_lembrete = st.text_area("O que precisa ser feito?", placeholder="Descreva a tarefa...")
            
            c1, c2 = st.columns(2)
            d_agendada = c1.date_input("Para quando?", min_value=hoje_dt)
            h_agendada = c2.time_input("Qual horário?", value=datetime.now().time())
            
            proj_vinc = None
            if tipo == "Processos (PQI)":
                proj_vinc = st.selectbox("Selecione o Projeto PQI:", [p['titulo'] for p in projs])
            
            if st.form_submit_button("AGENDAR TAREFA 🚀", use_container_width=True):
                if not txt_lembrete:
                    st.error("Por favor, descreva a tarefa.")
                else:
                    data_f = f"{d_agendada.strftime('%d/%m/%Y')} {h_agendada.strftime('%H:%M')}"
                    if tipo == "Processos (PQI)":
                        for p in projs:
                            if p['titulo'] == proj_vinc:
                                p.setdefault('lembretes', []).append({
                                    "id": datetime.now().timestamp(), 
                                    "data_hora": data_f, 
                                    "texto": txt_lembrete, 
                                    "status": "Pendente"
                                })
                        db.salvar_projetos(projs)
                    else:
                        diario.append({
                            "usuario": user_info['nome'], 
                            "data_reg": datetime.now().strftime("%d/%m/%Y %H:%M"), 
                            "solicitacao": txt_lembrete, 
                            "depto": "GERAL", 
                            "lembrete": data_f, 
                            "status": "Pendente"
                        })
                        db.salvar_diario(diario)
                    
                    st.success(f"Tarefa agendada para {data_f}!")
                    st.rerun()


    # --- ABA 5: PERFIL ---
    with tab_perfil:

        st.subheader("👤 Meu Perfil")

        foto = st.file_uploader(
            "Escolha uma foto",
            type=["png", "jpg", "jpeg"]
        )

        if foto is not None:

            caminho = f"fotos/{user_info['nome']}.png"

            with open(caminho, "wb") as f:
                f.write(foto.getbuffer())

            st.success("Foto salva com sucesso!")

        # Mostrar foto atual
        try:
            st.image(f"fotos/{user_info['nome']}.png", width=150)
        except:
            st.info("Você ainda não possui foto.")
