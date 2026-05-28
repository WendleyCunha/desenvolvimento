import streamlit as st
import pandas as pd
from db import carregar_membros
from utils.pdf_s21 import gerar_pdf_padrao_s21

CATEGORIAS = ["PUBLICADOR", "PIONEIRO AUXILIAR", "PIONEIRO REGULAR"]


def render(df: pd.DataFrame, membros_db: dict):
    c1_tab, c2_tab = st.tabs(["👤 INDIVIDUAL (HISTÓRICO)", "📊 CATEGORIA"])

    # ── Individual ─────────────────────────────────────────────────────────────
    with c1_tab:
        if not membros_db:
            st.info("Nenhum membro cadastrado.")
            return

        publicador = st.selectbox(
            "Escolha o Publicador", sorted(list(membros_db.keys()))
        )

        if publicador and not df.empty:
            df_hist = df[
                (df["nome_oficial"] == publicador)
                & (df["status_validacao"] == "IDENTIFICADO")
            ].sort_values("mes_referencia")

            if df_hist.empty:
                st.info("Nenhum relatório encontrado para este publicador.")
            else:
                st.table(
                    df_hist[["mes_referencia", "horas", "estudos_biblicos"]].rename(
                        columns={
                            "mes_referencia": "Mês",
                            "horas": "Horas",
                            "estudos_biblicos": "Estudos",
                        }
                    )
                )
                pdf = gerar_pdf_padrao_s21(
                    publicador,
                    membros_db[publicador].get("categoria"),
                    df_hist,
                    membro_info=membros_db[publicador],
                )
                if pdf:
                    st.download_button(
                        "📥 Baixar Cartão S-21 Completo",
                        pdf,
                        f"S21_{publicador}.pdf",
                        mime="application/pdf",
                    )

    # ── Por categoria ──────────────────────────────────────────────────────────
    with c2_tab:
        cat_sel = st.selectbox("Consolidado por Categoria", CATEGORIAS)

        if df.empty:
            st.info("Sem dados.")
            return

        df_cons = df[
            (df["status_validacao"] == "IDENTIFICADO") & (df["cat_oficial"] == cat_sel)
        ]

        if df_cons.empty:
            st.info(f"Sem dados para {cat_sel}.")
            return

        resumo = (
            df_cons.groupby("mes_referencia")
            .agg({"id": "count", "horas": "sum", "estudos_biblicos": "sum"})
            .reset_index()
            .rename(
                columns={
                    "id": "Relatórios",
                    "horas": "Total Horas",
                    "estudos_biblicos": "Total Estudos",
                    "mes_referencia": "Mês",
                }
            )
        )
        st.dataframe(resumo, use_container_width=True)

        pdf_c = gerar_pdf_padrao_s21(
            f"CONSOLIDADO {cat_sel}S",
            cat_sel,
            resumo.rename(
                columns={"Total Horas": "horas", "Total Estudos": "estudos_biblicos", "Mês": "mes_referencia"}
            ),
        )
        if pdf_c:
            st.download_button(
                f"📥 Baixar Cartão {cat_sel}",
                pdf_c,
                f"S21_Consolidado_{cat_sel}.pdf",
                mime="application/pdf",
            )
