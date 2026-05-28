import streamlit as st
import base64
from auth import pode_editar
from db import carregar_anuncios, salvar_anuncio, deletar_anuncio
from utils.agenda_html import gerar_html_agenda


def render():
    sub_an = st.tabs(["✏️ Nova Postagem", "🗂️ Gerenciar Postagens"])

    # ── Nova Postagem ───────────────────────────────────────────────────────────
    with sub_an[0]:
        if not pode_editar("anuncios"):
            st.info("🔒 Somente leitura — você não pode publicar anúncios.")
            _exibir_anuncios_readonly()
            return

        tipo = st.radio(
            "Tipo de postagem",
            ["📝 Texto / Markdown", "🖼️ Imagem (JPEG/PNG)", "📅 Agenda de Reunião"],
            horizontal=True,
        )

        if tipo == "📝 Texto / Markdown":
            _form_texto()
        elif tipo == "🖼️ Imagem (JPEG/PNG)":
            _form_imagem()
        elif tipo == "📅 Agenda de Reunião":
            _form_agenda()

    # ── Gerenciar ───────────────────────────────────────────────────────────────
    with sub_an[1]:
        _exibir_anuncios_readonly(com_delete=pode_editar("anuncios"))


# ── Formulários privados ────────────────────────────────────────────────────────

def _form_texto():
    st.info("Use Markdown: **negrito**, *itálico*, listas com `-`, títulos com `#`.")
    titulo_txt  = st.text_input("Título do anúncio (opcional)")
    conteudo_md = st.text_area("Conteúdo", height=200, placeholder="Digite o texto aqui...")
    st.caption("Pré-visualização:")
    if conteudo_md:
        st.markdown(conteudo_md)
    if st.button("📤 Publicar Texto", use_container_width=True):
        if conteudo_md.strip():
            salvar_anuncio({
                "tipo":               "texto",
                "titulo":             titulo_txt or "Anúncio",
                "conteudo_html":      conteudo_md,
                "renderizar_markdown": True,
            })
            st.success("✅ Anúncio publicado!")
            st.rerun()
        else:
            st.error("O conteúdo não pode estar vazio.")


def _form_imagem():
    titulo_img = st.text_input("Legenda / Título da imagem (opcional)")
    arquivo    = st.file_uploader("Enviar imagem", type=["jpg", "jpeg", "png"])
    if arquivo:
        st.image(arquivo, caption=titulo_img or "Pré-visualização", use_column_width=True)
        if st.button("📤 Publicar Imagem", use_container_width=True):
            img_bytes = arquivo.read()
            mime  = "image/png" if arquivo.name.endswith(".png") else "image/jpeg"
            b64   = base64.b64encode(img_bytes).decode("utf-8")
            html_img = (
                f'<div style="text-align:center;padding:10px;">'
                f'<img src="data:{mime};base64,{b64}" '
                f'style="max-width:100%;border-radius:8px;" />'
                + (
                    f'<p style="margin-top:8px;color:#555;font-size:14px;">{titulo_img}</p>'
                    if titulo_img
                    else ""
                )
                + "</div>"
            )
            salvar_anuncio({
                "tipo":               "imagem",
                "titulo":             titulo_img or arquivo.name,
                "conteudo_html":      html_img,
                "renderizar_markdown": False,
            })
            st.success("✅ Imagem publicada!")
            st.rerun()
    else:
        st.info("Selecione uma imagem para enviar.")


def _form_agenda():
    st.markdown("#### 📋 Preencha a Agenda")

    col_a, col_b = st.columns(2)
    data_texto = col_a.text_input("📅 Período", placeholder="18-24 DE MAIO")
    escritura  = col_b.text_input("📖 Escritura", placeholder="ISAÍAS 62-64")

    col_c, col_d, col_e = st.columns(3)
    cant_ab   = col_c.text_input("🎵 Cântico Abertura", placeholder="44")
    cant_meio = col_d.text_input("🎵 Cântico NVC",      placeholder="115")
    cant_fin  = col_e.text_input("🎵 Cântico Final",    placeholder="151")

    st.markdown("---")
    st.markdown(
        '<div style="background:#1a3566;color:white;padding:7px 12px;'
        'border-radius:5px;font-weight:bold;margin-bottom:6px;">'
        "TESOUROS DA PALAVRA DE DEUS</div>",
        unsafe_allow_html=True,
    )
    n_tes    = st.number_input("Nº de itens", 1, 6, 3, key="n_tes")
    tesouros = []
    for i in range(int(n_tes)):
        c1, c2 = st.columns([4, 1])
        t     = c1.text_input(f"Item {i+1}", key=f"tes_t_{i}", label_visibility="collapsed", placeholder=f"Item {i+1} – Título")
        d_dur = c2.text_input("Dur.", key=f"tes_d_{i}", label_visibility="collapsed", placeholder="10 min")
        tesouros.append({"num": i + 1, "titulo": t, "duracao": d_dur})

    st.markdown("---")
    st.markdown(
        '<div style="background:#8a6200;color:white;padding:7px 12px;'
        'border-radius:5px;font-weight:bold;margin-bottom:6px;">'
        "FAÇA SEU MELHOR NO MINISTÉRIO</div>",
        unsafe_allow_html=True,
    )
    n_min      = st.number_input("Nº de itens", 1, 6, 3, key="n_min")
    ministerio = []
    base_min   = int(n_tes)
    for i in range(int(n_min)):
        c1, c2 = st.columns([4, 1])
        t     = c1.text_input(f"Item {base_min+i+1}", key=f"min_t_{i}", label_visibility="collapsed", placeholder=f"Item {base_min+i+1} – Título")
        d_dur = c2.text_input("Dur.", key=f"min_d_{i}", label_visibility="collapsed", placeholder="")
        ministerio.append({"num": base_min + i + 1, "titulo": t, "duracao": d_dur})

    st.markdown("---")
    st.markdown(
        '<div style="background:#cc0000;color:white;padding:7px 12px;'
        'border-radius:5px;font-weight:bold;margin-bottom:6px;">'
        "NOSSA VIDA CRISTÃ</div>",
        unsafe_allow_html=True,
    )
    n_nvc       = st.number_input("Nº de itens", 1, 10, 2, key="n_nvc")
    vida_crista = []
    base_nvc    = int(n_tes) + int(n_min)
    for i in range(int(n_nvc)):
        c1, c2 = st.columns([4, 1])
        t     = c1.text_input(f"Item {base_nvc+i+1}", key=f"nvc_t_{i}", label_visibility="collapsed", placeholder=f"Item {base_nvc+i+1} – Título")
        d_dur = c2.text_input("Dur.", key=f"nvc_d_{i}", label_visibility="collapsed", placeholder="30 min" if i == int(n_nvc)-1 else "")
        vida_crista.append({"num": base_nvc + i + 1, "titulo": t, "duracao": d_dur})

    st.markdown("---")
    agenda_dados = {
        "data_texto":      data_texto,
        "escritura":       escritura,
        "cantico_abertura": cant_ab,
        "cantico_meio":    cant_meio,
        "cantico_final":   cant_fin,
        "tesouros":        tesouros,
        "ministerio":      ministerio,
        "vida_crista":     vida_crista,
    }

    col_prev, col_pub = st.columns(2)
    with col_prev:
        if st.button("👁️ Pré-visualizar", use_container_width=True):
            st.markdown(gerar_html_agenda(agenda_dados), unsafe_allow_html=True)
    with col_pub:
        if st.button("📤 Publicar Agenda", use_container_width=True, type="primary"):
            if not data_texto.strip():
                st.error("Informe o período da semana.")
            else:
                html_agenda = gerar_html_agenda(agenda_dados)
                salvar_anuncio({
                    "tipo":               "agenda",
                    "titulo":             data_texto,
                    "conteudo_html":      html_agenda,
                    "renderizar_markdown": False,
                    "dados_agenda":       agenda_dados,
                })
                st.success(f"✅ Agenda '{data_texto}' publicada!")
                st.rerun()


def _exibir_anuncios_readonly(com_delete: bool = False):
    anuncios = carregar_anuncios()
    if not anuncios:
        st.info("Nenhuma postagem encontrada.")
        return

    st.caption(f"{len(anuncios)} postagem(ns) • mais recente primeiro")
    for a in anuncios:
        tipo_icon = {"texto": "📝", "imagem": "🖼️", "agenda": "📅"}.get(a.get("tipo", ""), "📌")
        titulo_a  = a.get("titulo", "Sem título")
        ts        = a.get("data_postagem")
        data_str  = ts.strftime("%d/%m/%Y %H:%M") if hasattr(ts, "strftime") else "–"

        with st.expander(f"{tipo_icon} {titulo_a}  ·  {data_str}"):
            if a.get("renderizar_markdown"):
                st.markdown(a.get("conteudo_html", ""), unsafe_allow_html=False)
            else:
                st.markdown(a.get("conteudo_html", ""), unsafe_allow_html=True)

            if com_delete:
                st.markdown("---")
                if st.button(f"🗑️ Deletar esta postagem", key=f"del_an_{a['id']}", type="secondary"):
                    deletar_anuncio(a["id"])
