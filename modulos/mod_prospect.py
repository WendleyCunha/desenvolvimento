"""
modulos/mod_prospect.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
BLOCO PROSPECT — [v17] correção no fluxo de "Conserto".

[v17 — correção de bug] O conserto estava sendo salvo com a chave
"etapa_atual", mas TODO o resto do sistema (database.py, regras_agenda.py,
mod_financeiro.py) usa a chave "etapa" para saber em que estágio da régua
um pedido está. Como as duas chaves nunca batiam, o conserto ficava sem
"etapa" de verdade nas telas que dependem desse campo. Corrigido para
"etapa": 1. Também passou a gravar "valor_recebido": 0.0 explicitamente
(antes ficava implícito via NaN→0 do pandas), deixando o registro
idêntico em formato a um pedido normal recém-criado.

[v16] BLOCO PROSPECT — novo módulo. Adição do fluxo simplificado de
"Conserto".
"""

import streamlit as st
import time

from database import (
    prospects_listar, prospects_inserir, prospects_deletar,
    encomendas_inserir, cronograma_inserir
)
from modulos.utils import agora_br
from modulos.mod_encomendas import dialog_nova_encomenda


@st.dialog("✂️ Novo Conserto")
def dialog_novo_conserto(nome_fixo: str, prospect_id: str):
    """
    Cria um conserto a partir de um prospect.
    Salva como uma encomenda simplificada (para integrar com financeiro e
    agenda), mas ignora regras de limite de ocupação e gera apenas o
    lembrete de confecção.

    IMPORTANTE: para que este conserto não dispute (nem seja bloqueado por)
    a exclusividade do dia de Confecção ou o limite de provas de pedidos
    normais, ele é marcado com o prefixo "[Conserto]" na peça — e
    `modulos/regras_agenda.py` explicitamente ignora qualquer registro com
    esse prefixo ao calcular ocupação de dias e contagem de provas.
    """
    st.markdown(f"**Cliente:** {nome_fixo}")
    st.caption("Consertos são inseridos diretamente na agenda sem validação de limite de peças e geram apenas a etapa de Confecção.")

    tipo_conserto = st.selectbox("Tipo de conserto", ["Barra", "Zíper", "Ajuste", "Outro"])
    data_conserto = st.date_input("Data da Confecção (Conserto)")
    valor_conserto = st.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")

    if st.button("💾 Agendar Conserto", type="primary", use_container_width=True):
        # 1. Cria o conserto como um pedido simplificado
        nova_enc = {
            "cliente": nome_fixo,
            "peca": f"[Conserto] {tipo_conserto}",
            "valor_total": valor_conserto,
            "valor_recebido": 0.0,   # aguardando quitação no financeiro
            "sinal": 0.0,
            "data_confeccao": data_conserto.isoformat(),
            "etapa": 1,              # 1 = Confecção (chave usada em todo o sistema)
            "precisa_tecido": False,
        }
        novo_id = encomendas_inserir(nova_enc)

        # 2. Gera APENAS o lembrete da confecção (sem provas ou tecidos)
        cronograma_inserir({
            "encomenda_id": novo_id,
            "etapa": 1,
            "data_tarefa": data_conserto.isoformat(),
            "concluido": False
        })

        # 3. Remove da lista de prospects (já virou serviço ativo)
        prospects_deletar(str(prospect_id))

        st.success("✅ Conserto registrado na agenda e no financeiro!")
        time.sleep(1)
        st.rerun()


def renderizar_prospects():
    st.markdown("## 🌱 Prospect")
    st.caption(
        "Cadastre só o nome de quem está interessado — vai formando uma lista. "
        "Quando for fechar os detalhes, clique em **🪡 Converter em Pedido** ou **✂️ Conserto**."
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

    # Ajuste nas colunas para caber os 3 botões
    for _, p in df_p_view.iterrows():
        col1, col2, col3, col4 = st.columns([2.8, 1.5, 1.2, 1])
        tel_txt = f" &nbsp;·&nbsp; {p['telefone']}" if str(p.get("telefone") or "").strip() else ""
        col1.markdown(f"**{p['nome']}**{tel_txt}")

        if col2.button("🪡 Converter", key=f"conv_prospect_{p['rowid']}", use_container_width=True):
            dialog_nova_encomenda(nome_fixo=p["nome"], prospect_id=p["rowid"])

        if col3.button("✂️ Conserto", key=f"cons_prospect_{p['rowid']}", use_container_width=True):
            dialog_novo_conserto(nome_fixo=p["nome"], prospect_id=p["rowid"])

        if col4.button("🗑️ Remover", key=f"rm_prospect_{p['rowid']}", use_container_width=True):
            prospects_deletar(str(p["rowid"]))
            st.success(f"Prospect **{p['nome']}** removido.")
            st.rerun()
