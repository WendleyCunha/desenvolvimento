"""
modulos/mod_prospect.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
BLOCO PROSPECT — [v16] novo módulo.

O QUE É: uma lista simples de "gente interessada" — só o nome (e telefone,
opcional) — para antes de existir um pedido de verdade. Quando você
finalmente tira as medidas e fecha os detalhes com a cliente, clica em
"Converter em Pedido": abre o MESMO popup de criação de encomenda que já
existe em `modulos/mod_encomendas.py` (`dialog_nova_encomenda`), só que com
o nome já preenchido e travado. Ao criar a encomenda com sucesso, o
prospect correspondente é excluído da lista automaticamente — ele "virou"
o pedido, não existem mais os dois ao mesmo tempo.

NENHUMA regra de negócio de criação de encomenda é duplicada aqui — este
módulo só gerencia a lista de prospects (Firestore: `database.prospects_*`)
e delega a conversão inteira para `dialog_nova_encomenda`, que já cuida de:
peça, valores, Data da Confecção (primeira etapa — não existe mais "Data
Medidas" em lugar nenhum do sistema), Prova, Tecido, Entrega, CPF/RG e
geração do PDF do contrato.

Ponto de entrada usado pelo main.py:
  renderizar_prospects()

⚠️ Este é o ÚNICO ponto do pedido do Wendley que exige um pequeno ajuste em
   `main.py` (import + botão na sidebar + roteamento) — inevitável, já que
   é o main.py quem monta a navegação lateral. O snippet exato está na
   mensagem que acompanha esta entrega.
"""

import streamlit as st

from database import prospects_listar, prospects_inserir, prospects_deletar
from modulos.utils import agora_br
from modulos.mod_encomendas import dialog_nova_encomenda


def renderizar_prospects():
    st.markdown("## 🌱 Prospect")
    st.caption(
        "Cadastre só o nome de quem está interessado — vai formando uma lista. "
        "Quando for tirar as medidas e fechar os detalhes, clique em "
        "**🪡 Converter em Pedido**: abre o mesmo formulário de Nova Encomenda, "
        "já com o nome preenchido — você só completa peça, valores e datas "
        "(começando pela Data da Confecção). O prospect sai da lista assim "
        "que o pedido é criado."
    )

    with st.form("form_novo_prospect", clear_on_submit=True):
        col_p1, col_p2 = st.columns([2, 1])
        nome_prospect = col_p1.text_input("Nome *", placeholder="Ex: Fernanda Souza")
        tel_prospect = col_p2.text_input("Telefone / WhatsApp (opcional)")
        if st.form_submit_button("➕ Adicionar à lista", use_container_width=True, type="primary"):
            if nome_prospect.strip():
                prospects_inserir({
                    "nome": nome_prospect.strip(),
                    "telefone": tel_prospect.strip(),
                    "criado_em": agora_br().isoformat(),
                })
                st.success(f"✅ **{nome_prospect.strip()}** adicionado(a) à lista de prospects!")
                st.rerun()
            else:
                st.error("Informe o nome.")

    st.markdown("---")

    df_p = prospects_listar()
    if df_p.empty:
        st.info("Nenhum prospect cadastrado ainda.")
        return

    busca_prospect = st.text_input("🔍 Buscar por nome", key="busca_prospect")
    df_p_view = df_p
    if busca_prospect.strip():
        df_p_view = df_p[df_p["nome"].astype(str).str.contains(busca_prospect, case=False, na=False)]

    st.markdown(f"**{len(df_p_view)} prospect(s)**")

    if df_p_view.empty:
        st.info("Nenhum resultado para essa busca.")
        return

    for _, p in df_p_view.iterrows():
        col1, col2, col3 = st.columns([3, 1.6, 1])
        tel_txt = f" &nbsp;·&nbsp; {p['telefone']}" if str(p.get("telefone") or "").strip() else ""
        col1.markdown(f"**{p['nome']}**{tel_txt}")

        if col2.button("🪡 Converter em Pedido", key=f"conv_prospect_{p['rowid']}", use_container_width=True):
            dialog_nova_encomenda(nome_fixo=p["nome"], prospect_id=p["rowid"])

        if col3.button("🗑️ Remover", key=f"rm_prospect_{p['rowid']}", use_container_width=True):
            prospects_deletar(str(p["rowid"]))
            st.success(f"Prospect **{p['nome']}** removido.")
            st.rerun()
