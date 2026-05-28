import streamlit as st
import pandas as pd
from auth import pode_editar, bloquear_edicao
from db import salvar_baixa_manual

CATEGORIAS = ["PUBLICADOR", "PIONEIRO AUXILIAR", "PIONEIRO REGULAR"]

MESES_ORDEM = [
    "SETEMBRO 2025", "OUTUBRO 2025", "NOVEMBRO 2025", "DEZEMBRO 2025",
    "JANEIRO 2026", "FEVEREIRO 2026", "MARÇO 2026", "ABRIL 2026", "MAIO 2026",
]


def render(df: pd.DataFrame, membros_db: dict, mes_sel: str):
    df_mes = df[df["mes_referencia"] == mes_sel] if not df.empty else pd.DataFrame()
    df_ok  = df_mes[df_mes["status_validacao"] == "IDENTIFICADO"] if not df_mes.empty else pd.DataFrame()
    entregaram = df_ok["nome_oficial"].unique() if not df_ok.empty else []

    st.subheader(f"Resumo de {mes_sel}")

    sub_rel = st.tabs(["PUBLICADOR", "P. AUXILIAR", "P. REGULAR", "⏳ PENDÊNCIAS"])

    for i, cat in enumerate(CATEGORIAS):
        with sub_rel[i]:
            df_cat = df_ok[df_ok["cat_oficial"] == cat] if not df_ok.empty else pd.DataFrame()
            if df_cat.empty:
                st.info("Sem envios para esta categoria.")
            else:
                m1, m2, m3 = st.columns(3)
                m1.metric("Envios", len(df_cat))
                m2.metric("Total Horas", f"{int(df_cat['horas'].sum())}h")
                m3.metric("Estudos", int(df_cat["estudos_biblicos"].sum()))

                cols = st.columns(4)
                for idx, (_, r) in enumerate(df_cat.sort_values("nome_oficial").iterrows()):
                    with cols[idx % 4]:
                        st.markdown(
                            f'<div class="card">'
                            f'<div class="card-header">{r["nome_oficial"]}</div>'
                            f'⏱️ {int(r["horas"])}h | 📚 {int(r["estudos_biblicos"])}'
                            f"</div>",
                            unsafe_allow_html=True,
                        )

    # Aba de pendências
    with sub_rel[3]:
        st.warning(f"Quem ainda NÃO entregou em {mes_sel}:")
        idx_mes_sel = (
            MESES_ORDEM.index(mes_sel) if mes_sel in MESES_ORDEM else 99
        )

        pode_dar_baixa = pode_editar("relatorios")

        for cat in CATEGORIAS:
            pendentes = []
            for n, d_m in membros_db.items():
                inicio  = d_m.get("mes_inicio", "SETEMBRO 2025")
                idx_ini = MESES_ORDEM.index(inicio) if inicio in MESES_ORDEM else 0
                if (
                    d_m.get("categoria") == cat
                    and n not in entregaram
                    and idx_mes_sel >= idx_ini
                ):
                    pendentes.append(n)

            if pendentes:
                with st.expander(f"{cat} ({len(pendentes)})"):
                    for p in sorted(pendentes):
                        if pode_dar_baixa:
                            c1, c2, c3, c4 = st.columns([3, 1, 1, 2])
                            c1.write(f"**{p}**")
                            h_manual = c2.number_input("H", min_value=0, step=1,
                                                        key=f"h_man_{p}_{mes_sel}")
                            e_manual = c3.number_input("E", min_value=0, step=1,
                                                        key=f"e_man_{p}_{mes_sel}")
                            if c4.button("Dar Baixa", key=f"btn_man_{p}_{mes_sel}"):
                                salvar_baixa_manual(p, mes_sel, h_manual, e_manual)
                        else:
                            st.write(f"• {p}")relatorios
