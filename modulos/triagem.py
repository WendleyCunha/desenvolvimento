import streamlit as st
import pandas as pd
from auth import pode_editar
from db import inicializar_db, atualizar_membro
from utils.normalizacao import normalizar_nome_no_banco

CATEGORIAS = ["PUBLICADOR", "PIONEIRO AUXILIAR", "PIONEIRO REGULAR"]


def render(df: pd.DataFrame, df_mes: pd.DataFrame, membros_db: dict):
    df_triagem = (
        df_mes[df_mes["status_validacao"] == "TRIAGEM"]
        if not df_mes.empty
        else pd.DataFrame()
    )

    if df_triagem.empty:
        st.success("✅ Tudo limpo! Nenhum relatório em triagem.")
        return

    if not pode_editar("triagem"):
        st.info("🔒 Somente leitura — você não pode resolver itens de triagem.")
        st.dataframe(
            df_triagem[["nome", "horas", "estudos_biblicos"]].rename(columns={
                "nome": "Nome digitado",
                "horas": "Horas",
                "estudos_biblicos": "Estudos",
            }),
            use_container_width=True,
        )
        return

    nomes_db = sorted(list(membros_db.keys()))

    for _, row in df_triagem.iterrows():
        with st.container(border=True):
            c_info, c_hrs = st.columns([3, 1])
            c_info.write(f"**Digitado:** {row['nome']}")
            c_hrs.metric("Horas", int(row["horas"]))

            sugestao = normalizar_nome_no_banco(row["nome"], nomes_db)
            idx_sug  = nomes_db.index(sugestao) + 1 if sugestao else 0

            c1, c2 = st.columns(2)
            vincular = c1.selectbox(
                "Vincular a:",
                ["-- Novo Membro --"] + nomes_db,
                index=idx_sug,
                key=f"v_{row['id']}",
            )
            cat_v = c2.selectbox("Categoria:", CATEGORIAS, key=f"c_{row['id']}")

            if st.button("✅ Confirmar Vínculo", key=f"b_{row['id']}"):
                nome_final = row["nome"] if vincular == "-- Novo Membro --" else vincular
                atualizar_membro(nome_final, cat_v, novo=(vincular == "-- Novo Membro --"))
                inicializar_db().collection("relatorios_parque_alianca").document(
                    row["id"]
                ).update({"nome": nome_final})
                st.rerun()
