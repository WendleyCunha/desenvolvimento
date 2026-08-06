"""
modulos/mod_prospect.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
BLOCO PROSPECT — [v18] correção do lembrete de "Conserto".

[v18 — correção de bug] O lembrete do conserto era gravado em
`cronograma_inserir` com campos que NÃO EXISTEM no resto do sistema
("data_tarefa", "concluido", "etapa"). O cronograma de verdade (ver
`database.py` e `modulos/mod_encomendas.py`) usa: "tarefa" (texto exibido
no calendário), "categoria", "horas", "data", "frequencia", "concluida"
(0/1) e, principalmente, "tipo_agenda" — que é o campo usado para filtrar
a aba Trabalho e o Calendário (`cronograma_listar(tipo_agenda="Trabalho")`).
Sem "tipo_agenda", o lembrete do conserto NUNCA aparecia em lugar nenhum
da agenda. Corrigido para usar exatamente o mesmo formato de
`mod_encomendas.py`.

Além disso, o texto do lembrete usa o prefixo "🪡 Confecção:" (o mesmo já
reconhecido por `_mapa_prefixo_campo_data()` e `_sincronizar_lembretes_
pedido()` em mod_encomendas.py), com "[Conserto]" no meio do texto — assim
ele aparece escrito como conserto no calendário, mas continua totalmente
compatível com a sincronização de data que já existe para pedidos normais
(editar a data pelo popup do dia no Calendário atualiza os dois lados sem
duplicar lembrete).

[v18] Também passou a preencher `data_prova`, `data_entrega` e
`data_tecido` com a mesma data da confecção (em vez de deixar em branco).
Isso evita um erro ao abrir o Conserto pela tela de Gerenciar Pedidos: o
formulário de edição de pedido usa esses três campos num `st.date_input`,
e um pedido salvo sem eles quebra ao clicar em "Salvar". Como bônus, o
Conserto passa a aparecer certinho no Financeiro como "a receber"/"em
atraso" quando a data passar — o que ajuda a lembrar de cobrar/finalizar.

[v17 — correção de bug] O conserto estava sendo salvo com a chave
"etapa_atual" em vez de "etapa" (chave usada em todo o resto do sistema).
Corrigido. Também passou a gravar "valor_recebido": 0.0 explicitamente.

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
    agenda), mas ignora regras de limite de ocupação e gera apenas UM
    lembrete (Confecção) — sem provas, sem tecido.

    Compatibilidade com o resto do sistema (ver `modulos/regras_agenda.py`
    e `modulos/mod_encomendas.py`):
      - A peça é marcada com o prefixo "[Conserto]" — `regras_agenda.py`
        ignora explicitamente qualquer registro com esse prefixo ao
        calcular ocupação do dia de Confecção e contagem de provas (não
        disputa nem é bloqueado por essas regras).
      - O lembrete no cronograma usa o prefixo de texto "🪡 Confecção:",
        já reconhecido por `_mapa_prefixo_campo_data()` e
        `_sincronizar_lembretes_pedido()` em mod_encomendas.py — então,
        se o conserto for aberto e editado depois pela tela normal de
        Gerenciar Pedidos, a sincronização de data funciona sem duplicar
        lembrete.
      - "data_prova", "data_entrega" e "data_tecido" são preenchidas com a
        mesma data da Confecção, só para o formulário de edição de pedido
        (que espera essas datas preenchidas) nunca quebrar caso alguém
        abra o conserto por lá.
    """
    st.markdown(f"**Cliente:** {nome_fixo}")
    st.caption("Consertos são inseridos diretamente na agenda sem validação de limite de peças e geram apenas a etapa de Confecção.")

    tipo_conserto = st.selectbox("Tipo de conserto", ["Barra", "Zíper", "Ajuste", "Outro"])
    data_conserto = st.date_input("Data da Confecção (Conserto)")
    valor_conserto = st.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")

    if st.button("💾 Agendar Conserto", type="primary", use_container_width=True):
        data_iso = data_conserto.isoformat()

        # 1. Cria o conserto como um pedido simplificado
        nova_enc = {
            "cliente": nome_fixo,
            "peca": f"[Conserto] {tipo_conserto}",
            "descricao": "",
            "valor_total": valor_conserto,
            "valor_recebido": 0.0,   # aguardando quitação no financeiro
            "sinal": 0.0,
            "etapa": 1,              # 1 = Confecção (chave usada em todo o sistema)
            "precisa_tecido": 0,
            "data_tecido": data_iso,
            "data_confeccao": data_iso,
            "data_prova": data_iso,
            "tem_prova2": 0,
            "data_prova2": "",
            "data_entrega": data_iso,
            "cpf_cliente": "",
            "rg_cliente": "",
            "forma_pagamento": "A combinar",
            "observacoes": f"Conserto — {tipo_conserto}",
        }
        novo_id = encomendas_inserir(nova_enc)

        # 2. Gera APENAS o lembrete da confecção (sem provas ou tecidos),
        #    já no formato real do cronograma — aparece no Calendário e na
        #    aba Trabalho igual a qualquer outro pedido.
        cronograma_inserir({
            "tarefa": f"🪡 Confecção: [Conserto] {tipo_conserto} ({nome_fixo})",
            "categoria": "Costura",
            "horas": 1.0,
            "data": data_iso,
            "frequencia": "Pontual",
            "concluida": 0,
            "encomenda_id": novo_id,
            "tipo_agenda": "Trabalho",
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
