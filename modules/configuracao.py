import streamlit as st
import pandas as pd
import io
import zipfile
from auth import pode_editar, is_admin, render_gestao_usuarios
from db import (
    inicializar_db,
    atualizar_membro,
    deletar_relatorio,
    salvar_baixa_manual,
)
from utils.pdf_s21 import gerar_pdf_padrao_s21
from utils.normalizacao import obter_mes_atual_str

CATEGORIAS  = ["PUBLICADOR", "PIONEIRO AUXILIAR", "PIONEIRO REGULAR"]
GENEROS     = ["", "Masculino", "Feminino"]
CLASSES     = ["", "Outras ovelhas", "Ungido"]
CARGOS      = ["", "Ancião", "Servo ministerial", "Pioneiro regular",
               "Pioneiro especial", "Missionário em campo"]


def render(df: pd.DataFrame, membros_db: dict, mes_sel: str):
    # Abas disponíveis — Usuários só aparece para admin
    abas_cfg = ["✏️ EDITAR RELATÓRIOS", "👥 GERENCIAR MEMBROS", "➕ NOVO MEMBRO", "📦 EXPORTAR ZIP"]
    if is_admin():
        abas_cfg.append("🔐 USUÁRIOS DO SISTEMA")

    sub_cfg = st.tabs(abas_cfg)

    # ── Sub-aba 0: Editar Relatórios ──────────────────────────────────────────
    with sub_cfg[0]:
        if not pode_editar("relatorios"):
            st.info("🔒 Você não tem permissão para editar relatórios.")
            return

        if df.empty:
            st.info("Sem relatórios no período.")
            return

        df_ok_mes = df[
            (df["mes_referencia"] == mes_sel)
            & (df["status_validacao"] == "IDENTIFICADO")
        ]
        if df_ok_mes.empty:
            st.info(f"Sem relatórios identificados em {mes_sel}.")
            return

        for _, r in df_ok_mes.sort_values("nome_oficial").iterrows():
            with st.expander(f"📝 {r['nome_oficial']} ({int(r['horas'])}h)"):
                ce1, ce2, ce3 = st.columns([2, 1, 1])
                idx_cat  = CATEGORIAS.index(r["cat_oficial"]) if r["cat_oficial"] in CATEGORIAS else 0
                nova_cat = ce1.selectbox("Categoria", CATEGORIAS, index=idx_cat, key=f"e_c_{r['id']}")
                novas_h  = ce2.number_input("Horas",   value=int(r["horas"]),              key=f"e_h_{r['id']}")
                novos_e  = ce3.number_input("Estudos", value=int(r["estudos_biblicos"]),    key=f"e_e_{r['id']}")

                col_s, col_d = st.columns(2)
                if col_s.button("💾 Salvar", key=f"s_b_{r['id']}", use_container_width=True):
                    inicializar_db().collection("relatorios_parque_alianca").document(
                        r["id"]
                    ).update({"horas": novas_h, "estudos_biblicos": novos_e})
                    atualizar_membro(r["nome_oficial"], nova_cat)
                    st.toast("✅ Alterações salvas!")
                    st.rerun()
                if col_d.button("🗑️ Deletar", key=f"del_{r['id']}", use_container_width=True):
                    deletar_relatorio(r["id"])

    # ── Sub-aba 1: Gerenciar Membros ───────────────────────────────────────────
    with sub_cfg[1]:
        _render_gerenciar_membros(membros_db)

    # ── Sub-aba 2: Novo Membro ─────────────────────────────────────────────────
    with sub_cfg[2]:
        _render_novo_membro()

    # ── Sub-aba 3: Exportar ZIP ────────────────────────────────────────────────
    with sub_cfg[3]:
        _render_exportar_zip(df, membros_db, mes_sel)

    # ── Sub-aba 4: Usuários (admin only) ──────────────────────────────────────
    if is_admin() and len(sub_cfg) > 4:
        with sub_cfg[4]:
            render_gestao_usuarios()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _render_gerenciar_membros(membros_db: dict):
    if not pode_editar():
        st.info("🔒 Somente leitura.")
        for nome, m in sorted(membros_db.items()):
            st.write(f"• **{nome}** — {m.get('categoria', 'PUBLICADOR')}")
        return

    st.subheader("👥 Gerenciar Membros")
    st.caption("Clique no nome para expandir e editar.")

    for nome in sorted(membros_db.keys()):
        m        = membros_db[nome]
        cat_icon = {"PUBLICADOR": "👤", "PIONEIRO AUXILIAR": "🌟", "PIONEIRO REGULAR": "⭐"}.get(
            m.get("categoria", ""), "👤"
        )

        with st.expander(f"{cat_icon} **{nome}** — {m.get('categoria', 'PUBLICADOR')}"):
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown("##### 📋 Dados Pessoais")
                cat_gravada = m.get("categoria", "PUBLICADOR")
                if cat_gravada not in CATEGORIAS:
                    cat_gravada = "PUBLICADOR"
                nova_cat = st.selectbox(
                    "Categoria de Serviço", CATEGORIAS,
                    index=CATEGORIAS.index(cat_gravada),
                    key=f"cat_{nome}",
                )
                data_nasc = st.text_input("📅 Data de Nascimento", value=m.get("data_nascimento", ""),
                                           placeholder="DD/MM/AAAA", key=f"nasc_{nome}")
                data_bat  = st.text_input("🕊️ Data de Batismo", value=m.get("data_batismo", ""),
                                           placeholder="DD/MM/AAAA", key=f"bat_{nome}")
                tel_emer  = st.text_input("📞 Telefone de Emergência", value=m.get("telefone_emergencia", ""),
                                           placeholder="(XX) XXXXX-XXXX", key=f"tel_{nome}")

            with col_b:
                st.markdown("##### 🏷️ Classificação & Cargo")
                gen_val  = m.get("genero", "")
                nova_gen = st.selectbox("Gênero", GENEROS,
                                         index=GENEROS.index(gen_val) if gen_val in GENEROS else 0,
                                         key=f"gen_{nome}")
                cls_val  = m.get("classe", "")
                nova_cls = st.selectbox("Classe", CLASSES,
                                         index=CLASSES.index(cls_val) if cls_val in CLASSES else 0,
                                         key=f"cls_{nome}")
                cgo_val  = m.get("cargo", "")
                novo_cgo = st.selectbox("Cargo / Privilégio", CARGOS,
                                         index=CARGOS.index(cgo_val) if cgo_val in CARGOS else 0,
                                         key=f"cgo_{nome}")

                st.markdown("##### 🗂️ Resumo p/ Cartão S-21")
                flags = []
                if nova_gen:  flags.append(nova_gen)
                if nova_cls:  flags.append(nova_cls)
                if novo_cgo:  flags.append(novo_cgo)
                if data_nasc: flags.append(f"Nasc: {data_nasc}")
                if data_bat:  flags.append(f"Bat: {data_bat}")
                if tel_emer:  flags.append(f"Tel: {tel_emer}")
                for f in flags:
                    st.markdown(f"• {f}")
                if not flags:
                    st.caption("Nenhum dado extra cadastrado ainda.")

            st.divider()
            if st.button("💾 Salvar Alterações", key=f"save_{nome}", use_container_width=True, type="primary"):
                extra = {
                    "data_nascimento":     data_nasc,
                    "data_batismo":        data_bat,
                    "telefone_emergencia": tel_emer,
                    "genero":              nova_gen,
                    "classe":              nova_cls,
                    "cargo":               novo_cgo,
                }
                atualizar_membro(nome, nova_cat, extra=extra)
                st.toast(f"✅ {nome} atualizado com sucesso!")
                st.rerun()


def _render_novo_membro():
    if not pode_editar():
        st.info("🔒 Você não tem permissão para cadastrar membros.")
        return

    st.subheader("➕ Cadastrar Novo Membro")
    with st.form("novo_membro", clear_on_submit=True):
        st.markdown("##### Dados Obrigatórios")
        c1, c2 = st.columns(2)
        nm = c1.text_input("Nome Completo *")
        ct = c2.selectbox("Categoria *", CATEGORIAS)

        st.markdown("##### Dados do Cartão S-21")
        c3, c4 = st.columns(2)
        data_nasc_n = c3.text_input("📅 Data de Nascimento", placeholder="DD/MM/AAAA")
        data_bat_n  = c4.text_input("🕊️ Data de Batismo",    placeholder="DD/MM/AAAA")

        c5, c6, c7 = st.columns(3)
        gen_n = c5.selectbox("Gênero", GENEROS)
        cls_n = c6.selectbox("Classe", CLASSES)
        cgo_n = c7.selectbox("Cargo / Privilégio", CARGOS)
        tel_n = st.text_input("📞 Telefone de Emergência", placeholder="(XX) XXXXX-XXXX")

        if st.form_submit_button("➕ Adicionar Membro", use_container_width=True):
            if nm.strip():
                extra_n = {
                    "data_nascimento":     data_nasc_n,
                    "data_batismo":        data_bat_n,
                    "telefone_emergencia": tel_n,
                    "genero":              gen_n,
                    "classe":              cls_n,
                    "cargo":              cgo_n,
                }
                atualizar_membro(nm.strip(), ct, novo=True, extra=extra_n)
                st.success(f"✅ {nm.strip()} adicionado com sucesso!")
                st.rerun()
            else:
                st.error("Informe o nome completo.")


def _render_exportar_zip(df: pd.DataFrame, membros_db: dict, mes_sel: str):
    df_ok_zip = (
        df[
            (df["mes_referencia"] == mes_sel)
            & (df["status_validacao"] == "IDENTIFICADO")
        ]
        if not df.empty
        else pd.DataFrame()
    )

    if df_ok_zip.empty:
        st.info(f"Sem relatórios identificados em {mes_sel} para exportar.")
        return

    if st.button("🚀 GERAR ZIP MENSAL", use_container_width=True, type="primary"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "a") as zf:
            for _, r in df_ok_zip.iterrows():
                mi  = membros_db.get(r["nome_oficial"], {})
                pdf = gerar_pdf_padrao_s21(
                    r["nome_oficial"], r["cat_oficial"], pd.DataFrame([r]), membro_info=mi
                )
                if pdf:
                    zf.writestr(f"S21_{r['nome_oficial']}.pdf", pdf)
        st.download_button(
            "📥 Baixar ZIP",
            buf.getvalue(),
            f"S21_{mes_sel}.zip",
            mime="application/zip",
        )
