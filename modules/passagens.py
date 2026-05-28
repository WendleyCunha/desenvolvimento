import streamlit as st
import pandas as pd
import io
from auth import pode_editar, tem_modulo
from db import (
    carregar_eventos,
    criar_evento,
    adicionar_novo_onibus,
    salvar_passageiro,
    atualizar_embarque,
    deletar_passageiro,
    carregar_passageiros,
    buscar_pessoa_central,
    inicializar_db,
)

CAPACIDADE = 46
GRUPOS     = ["Rosas", "Engenho", "Cohab", "Geral"]


def render():
    if not tem_modulo("passagens"):
        st.warning("🔒 Você não tem acesso ao módulo de Passagens.")
        return

    st.markdown(
        "<h2 style='color:#003399;font-weight:800;letter-spacing:-1px;'>🚌 Passagens VGP</h2>",
        unsafe_allow_html=True,
    )

    eventos_ativos = carregar_eventos()

    tab_reserva, tab_dash, tab_gestao, tab_chamada, tab_config = st.tabs([
        "📝 Reserva", "📊 Dashboard", "👥 Passageiros", "🚩 Chamada", "⚙️ Ajustes",
    ])

    # ── Sem evento: mostrar criação ────────────────────────────────────────────
    if not eventos_ativos:
        with tab_config:
            if pode_editar("chamada") or pode_editar():
                st.subheader("Configurar Primeiro Evento")
                with st.form("criar_evento_inicial"):
                    n_ev = st.text_input("Nome do Evento (Ex: Excursão Março)")
                    v_ev = st.number_input("Valor da Passagem", min_value=0.0, value=50.0)
                    d_ev = st.multiselect("Dias de Operação", ["Sexta", "Sábado", "Domingo"])
                    if st.form_submit_button("🚀 Iniciar Evento"):
                        criar_evento(n_ev, d_ev, v_ev)
                        st.rerun()
            else:
                st.info("Nenhum evento ativo no momento.")
        st.info("Nenhum evento ativo. Vá em 'Ajustes' para criar um.")
        return

    # ── Seletor de evento na sidebar ───────────────────────────────────────────
    id_sel = st.sidebar.selectbox(
        "Selecione o Evento",
        list(eventos_ativos.keys()),
        format_func=lambda x: eventos_ativos[x]["nome"],
    )
    evento    = eventos_ativos[id_sel]
    pax_lista = carregar_passageiros(id_sel)
    df        = pd.DataFrame(pax_lista)

    if not df.empty:
        if "grupo" not in df.columns:
            df["grupo"] = "Geral"
        df["grupo"] = df["grupo"].fillna("Geral")
        df["pago"]  = df["pago"].fillna(False)

    # ── Aba Reserva ─────────────────────────────────────────────────────────────
    with tab_reserva:
        _pode = pode_editar("chamada") or pode_editar()
        if not _pode:
            st.info("🔒 Somente leitura — você não pode fazer reservas.")
            if not df.empty:
                st.dataframe(df[["nome", "grupo", "pago"]].sort_values("nome"), use_container_width=True)
        else:
            _tab_reserva(id_sel, evento)

    # ── Aba Dashboard ────────────────────────────────────────────────────────────
    with tab_dash:
        _tab_dashboard(df, evento, id_sel)

    # ── Aba Passageiros ──────────────────────────────────────────────────────────
    with tab_gestao:
        if not pode_editar() and not pode_editar("chamada"):
            st.info("🔒 Somente leitura.")
            if not df.empty:
                st.dataframe(df[["nome", "grupo", "pago", "embarcou"]].sort_values("nome"), use_container_width=True)
        else:
            _tab_gestao(df, id_sel, evento)

    # ── Aba Chamada ──────────────────────────────────────────────────────────────
    with tab_chamada:
        # Chamada tem permissão própria — operadores de chamada podem editar aqui
        _tab_chamada(df, id_sel)

    # ── Aba Config ───────────────────────────────────────────────────────────────
    with tab_config:
        _tab_config(df, id_sel, evento)


# ── Aba Reserva ────────────────────────────────────────────────────────────────

def _tab_reserva(id_sel, evento):
    st.subheader("Lançar Nova Reserva")
    busca_nome = st.text_input("🔍 Buscar no histórico central (Nome)")
    mestre     = buscar_pessoa_central(busca_nome) if busca_nome else None
    if mestre:
        st.success(f"Cadastro encontrado: {mestre['nome']}")

    with st.form("reserva_form_v2", clear_on_submit=True):
        nome_f = st.text_input("Nome Completo", value=mestre["nome"] if mestre else busca_nome)
        c_id1, c_id2 = st.columns(2)
        rg_f  = c_id1.text_input("RG",  value=mestre["rg"]  if mestre else "")
        cpf_f = c_id2.text_input("CPF", value=mestre["cpf"] if mestre else "")
        grupo_f = st.selectbox("Grupo / Localização", GRUPOS)

        st.markdown("**Selecione os dias e ônibus:**")
        viagens = []
        for dia in evento["datas"]:
            c1, c2 = st.columns([1, 2])
            if c1.checkbox(f"Viagem {dia}", key=f"f_res_{dia}"):
                f_dia = evento.get("frotas", {}).get(dia, 1)
                b_sel = c2.selectbox(f"Selecione o Bus {dia}", range(1, f_dia + 1), key=f"f_bus_{dia}")
                viagens.append({"dia": dia, "bus": b_sel})

        pago_f = st.toggle("Pagamento Confirmado?")
        if st.form_submit_button("✅ Finalizar Reserva", type="primary", use_container_width=True):
            if nome_f and viagens:
                valor_total = evento["valor"] * len(viagens)
                salvar_passageiro(id_sel, {
                    "nome": nome_f, "rg": rg_f, "cpf": cpf_f, "grupo": grupo_f,
                    "dias_onibus": viagens, "pago": pago_f, "embarcou": False,
                    "valor_total": valor_total,
                    "valor_pago":  valor_total if pago_f else 0.0,
                })
                st.success("Reserva gravada!")
                st.rerun()
            else:
                st.error("Preencha o nome e escolha ao menos um dia.")


# ── Aba Dashboard ──────────────────────────────────────────────────────────────

def _tab_dashboard(df, evento, id_sel):
    if df.empty:
        st.info("Aguardando dados para gerar o dashboard.")
        return

    st.subheader(f"📊 Indicadores: {evento['nome']}")
    m1, m2, m3, m4 = st.columns(4)
    total_reservas = len(df)
    pagos          = len(df[df["pago"] == True])
    financeiro     = df["valor_pago"].sum() if "valor_pago" in df.columns else pagos * evento["valor"]

    m1.metric("Total Reservas", total_reservas)
    m2.metric("Pagos", pagos, f"{round((pagos/total_reservas)*100)}%" if total_reservas else "0%")
    m3.metric("Pendentes", total_reservas - pagos)
    m4.metric("Arrecadado", f"R$ {financeiro:,.2f}")

    st.divider()
    st.markdown("### 🚌 Ocupação por Dia e Frota")
    cols_dia = st.columns(len(evento["datas"]))

    for idx, dia in enumerate(evento["datas"]):
        with cols_dia[idx]:
            st.info(f"📅 **{dia}**")
            num_onibus = evento.get("frotas", {}).get(dia, 1)

            for b in range(1, num_onibus + 1):
                qtd = sum(
                    1 for _, p in df.iterrows()
                    for v in p.get("dias_onibus", [])
                    if v["dia"] == dia and v["bus"] == b
                )
                perc = round((qtd / CAPACIDADE) * 100) if CAPACIDADE > 0 else 0

                with st.container(border=True):
                    st.write(f"**Ônibus {b}**")
                    st.progress(min(perc / 100, 1.0))
                    st.markdown(f"**{qtd}/{CAPACIDADE}** PAX ({perc}%)")
                    if qtd >= CAPACIDADE:
                        st.warning("Lotação Máxima!")
                        if b == num_onibus and (pode_editar() or pode_editar("chamada")):
                            if st.button(f"➕ Add Ônibus {b+1}", key=f"add_{dia}_{b}", use_container_width=True):
                                adicionar_novo_onibus(id_sel, dia)
                                st.rerun()


# ── Aba Gestão de Passageiros ──────────────────────────────────────────────────

def _tab_gestao(df, id_sel, evento):
    st.subheader("Controle de Pagamento e Edição")
    if df.empty:
        st.info("Sem passageiros cadastrados.")
        return

    col_pg, col_pn = st.columns(2)

    with col_pg:
        st.markdown("<h4 style='color:green;'>✅ Pagos</h4>", unsafe_allow_html=True)
        for _, r in df[df["pago"] == True].sort_values("nome").iterrows():
            if st.button(f"✏️ {r['nome']}", key=f"ed_pg_{r['nome']}", use_container_width=True):
                _dialog_passageiro(r.to_dict(), id_sel, evento)

    with col_pn:
        st.markdown("<h4 style='color:red;'>⚠️ Pendentes</h4>", unsafe_allow_html=True)
        for _, r in df[df["pago"] == False].sort_values("nome").iterrows():
            v_total = r.get("valor_total", len(r.get("dias_onibus", [])) * evento["valor"])
            v_pago  = r.get("valor_pago", 0.0)
            v_falta = v_total - v_pago
            label   = f"👤 {r['nome']} | Falta: R$ {v_falta:,.2f}"
            if st.button(label, key=f"ed_pe_{r['nome']}", use_container_width=True):
                _dialog_passageiro(r.to_dict(), id_sel, evento)


# ── Aba Chamada ────────────────────────────────────────────────────────────────

def _tab_chamada(df, id_sel):
    st.subheader("🚩 Chamada em Tempo Real")

    # Chamada pode ser editada por quem tem role "chamada" OU por editores gerais
    pode_marcar = pode_editar("chamada") or pode_editar()

    if df.empty:
        st.info("Sem passageiros cadastrados.")
        return

    grupos = sorted(df["grupo"].unique())
    for grp in grupos:
        with st.expander(f"📍 GRUPO: {grp.upper()}", expanded=True):
            df_grp  = df[df["grupo"] == grp]
            c_faltam, c_ok = st.columns(2)

            with c_faltam:
                st.caption("❌ AGUARDANDO EMBARQUE")
                faltam = df_grp[(df_grp["pago"] == True) & (df_grp["embarcou"] == False)].sort_values("nome")
                for _, p in faltam.iterrows():
                    if pode_marcar:
                        col_n, col_b = st.columns([4, 1])
                        col_n.write(p["nome"])
                        if col_b.button("✅", key=f"emb_{grp}_{p['nome']}"):
                            atualizar_embarque(id_sel, p.to_dict(), True)
                            st.rerun()
                    else:
                        st.write(f"• {p['nome']}")

            with c_ok:
                st.caption("🟢 EMBARCADOS")
                embarcados = df_grp[df_grp["embarcou"] == True].sort_values("nome")
                for _, p in embarcados.iterrows():
                    if pode_marcar:
                        col_n, col_b = st.columns([4, 1])
                        col_n.write(f":gray[~~{p['nome']}~~]")
                        if col_b.button("🔙", key=f"rem_{grp}_{p['nome']}"):
                            atualizar_embarque(id_sel, p.to_dict(), False)
                            st.rerun()
                    else:
                        st.write(f":gray[~~{p['nome']}~~]")


# ── Aba Config Passagens ───────────────────────────────────────────────────────

def _tab_config(df, id_sel, evento):
    st.subheader("⚙️ Painel Administrativo")

    if not pode_editar() and not pode_editar("chamada"):
        st.info("🔒 Somente administradores podem acessar configurações.")
        return

    with st.container(border=True):
        st.write("**Relatórios**")
        if st.button("📥 Exportar Lista para Excel", use_container_width=True):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Passageiros")
            st.download_button(
                "💾 Baixar Arquivo Excel",
                output.getvalue(),
                f"lista_{id_sel}.xlsx",
                use_container_width=True,
            )

    if pode_editar():
        st.divider()
        with st.expander("🚨 Zona de Perigo"):
            st.warning("Ao finalizar, o evento sairá da lista de ativos.")
            if st.button("🏁 Finalizar e Arquivar Evento", type="primary", use_container_width=True):
                inicializar_db().collection("eventos").document(id_sel).update({"status": "finalizado"})
                st.rerun()

        with st.expander("➕ Criar Novo Evento"):
            with st.form("criar_evento_novo"):
                n_ev = st.text_input("Nome do Evento")
                v_ev = st.number_input("Valor da Passagem", min_value=0.0, value=50.0)
                d_ev = st.multiselect("Dias de Operação", ["Sexta", "Sábado", "Domingo"])
                if st.form_submit_button("🚀 Criar Evento"):
                    criar_evento(n_ev, d_ev, v_ev)
                    st.rerun()


# ── Dialog de edição de passageiro ────────────────────────────────────────────

@st.dialog("Gerenciar Passageiro")
def _dialog_passageiro(pax, id_sel, evento_atual):
    st.subheader(f"👤 {pax['nome']}")

    total_devido = pax.get("valor_total", len(pax.get("dias_onibus", [])) * evento_atual["valor"])
    pago_atualmente = pax.get("valor_pago", 0.0)
    saldo_devedor   = total_devido - pago_atualmente

    col_f1, col_f2 = st.columns(2)
    col_f1.metric("Total da Passagem", f"R$ {total_devido:.2f}")
    col_f2.metric("Saldo Pendente", f"R$ {saldo_devedor:.2f}", delta_color="inverse")

    with st.form("edit_pax_final"):
        nome = st.text_input("Nome", value=pax["nome"])
        c1, c2 = st.columns(2)
        rg  = c1.text_input("RG",  value=pax.get("rg",  ""))
        cpf = c2.text_input("CPF", value=pax.get("cpf", ""))

        grupo_atual = pax.get("grupo", "Geral")
        idx_grupo   = GRUPOS.index(grupo_atual) if grupo_atual in GRUPOS else len(GRUPOS) - 1
        grupo       = st.selectbox("Grupo", GRUPOS, index=idx_grupo)

        st.divider()
        st.markdown("### 💰 Recebimentos / Troco")
        c_rec1, c_rec2, c_rec3 = st.columns(3)
        valor_recebido = c_rec1.number_input("Valor Recebido Agora", min_value=0.0, value=0.0, step=5.0)
        valor_entregue = c_rec2.number_input("Dinheiro (Troco)",     min_value=0.0, value=0.0)
        if valor_entregue > valor_recebido:
            c_rec3.success(f"Troco: R$ {valor_entregue - valor_recebido:.2f}")

        st.divider()
        novas_viagens    = []
        viagens_atuais   = {v["dia"]: v["bus"] for v in pax.get("dias_onibus", [])}
        for dia in evento_atual["datas"]:
            col_d1, col_d2 = st.columns([1, 2])
            ativo = col_d1.checkbox(f"Viaja {dia}", value=dia in viagens_atuais, key=f"edit_chk_{dia}")
            if ativo:
                frotas_dia  = evento_atual.get("frotas", {}).get(dia, 1)
                bus_default = viagens_atuais.get(dia, 1)
                bus_sel     = col_d2.selectbox(
                    f"Bus {dia}", range(1, frotas_dia + 1),
                    index=min(bus_default - 1, frotas_dia - 1),
                    key=f"edit_sel_{dia}",
                )
                novas_viagens.append({"dia": dia, "bus": bus_sel})

        st.divider()
        novo_total_pago = pago_atualmente + valor_recebido
        pago    = st.toggle("💰 Pagamento Total Quitado", value=pax.get("pago", False) or (novo_total_pago >= total_devido))
        embarque = st.toggle("🚩 Embarcou", value=pax.get("embarcou", False))

        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.form_submit_button("💾 Salvar Alterações", use_container_width=True, type="primary"):
            if nome != pax["nome"] or rg != pax.get("rg", ""):
                deletar_passageiro(id_sel, pax["nome"], pax.get("rg", ""))
            pax.update({
                "nome": nome, "rg": rg, "cpf": cpf, "grupo": grupo,
                "dias_onibus": novas_viagens, "pago": pago, "embarcou": embarque,
                "valor_total": evento_atual["valor"] * len(novas_viagens),
                "valor_pago":  novo_total_pago,
            })
            salvar_passageiro(id_sel, pax)
            st.rerun()
        if col_btn2.form_submit_button("🗑️ Excluir Reserva", use_container_width=True):
            deletar_passageiro(id_sel, pax["nome"], pax.get("rg", ""))
            st.rerun()
