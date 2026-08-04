"""
modulos/mod_encomendas.py — Lila Closet Atelier
─────────────────────────────────────────────────────────────────────────────
BLOCO ENCOMENDAS — extraído do main.py em [v15] para reduzir o orquestrador
principal. Reúne TUDO que gira em torno do ciclo de vida de um pedido:

  • Geração de PDF de contrato (`gerar_pdf_contrato` + helpers de cor)
  • Mini-calendário de ocupação da Data da Confecção
  • Senha ADM para conflito de Data da Confecção (`_checar_confeccao_com_senha`
    / `_render_confirmacao_senha_confeccao`)
  • Criação de encomenda — popup (`dialog_nova_encomenda`) e formulário fixo
    (`secao_nova_encomenda_inline`)
  • Sincronização de lembretes/cronograma com as datas do pedido
  • Edição completa de um pedido (`_conteudo_pedido`) — reaproveitada pelos
    popups da Agenda e por Gerenciar Pedidos
  • Popups (`_abrir_popup_pedido`, `_dialog_editar_dia`,
    `_dialog_editar_data_tarefa`)
  • Cards de pedido (`_card_pedido`)
  • As telas `renderizar_contratos`, `renderizar_nova_encomenda` e
    `renderizar_gerenciar_pedidos`

DUAS ÚNICAS ADAPTAÇÕES TÉCNICAS feitas para este módulo funcionar sozinho,
sem depender de variáveis globais do main.py:

  1) `dialog_nova_encomenda` e `secao_nova_encomenda_inline` buscam a lista
     de encomendas na hora com `encomendas_listar(cancelado=False)` (já
     cacheado por `database.py` — nenhum custo extra de leitura), em vez de
     depender de um `df_enc_all` global calculado no main.py.

  2) As constantes `ETAPAS`, `DIC_MEDIDAS`, `SENHA_DELETE` e `LOGO_PATH`
     vivem aqui (fonte única). O `main.py` importa `DIC_MEDIDAS` (usada em
     Medidas), `SENHA_DELETE` (Configurações → Exclusão Permanente) e
     `LOGO_PATH` (cabeçalho) deste módulo, em vez de as redefinir.

[v16] — TRÊS MUDANÇAS GRANDES:

  1) CONTRATOS + GERENCIAR PEDIDOS UNIFICADOS: as duas telas faziam a
     mesma coisa por baixo (abrir `_conteudo_pedido`) com visual diferente.
     `renderizar_gerenciar_pedidos()` passou a ser a ÚNICA tela completa
     (cards + filtro de status + busca + selo de contrato pronto/pendente
     + saldo pendente). `renderizar_contratos()` agora é só um ALIAS que
     chama a mesma função — o `main.py` não precisou ser tocado, os dois
     botões da sidebar (que já existiam) levam ao mesmo lugar.

  2) "DATA MEDIDAS" ELIMINADA DE TODA A LÓGICA: não existe mais o campo
     `data_visita` em nenhum formulário, no PDF do contrato, na
     sincronização de lembretes nem na régua de etapas. A régua agora
     começa direto em **Confecção** (etapa 1) → Prova (2) → Entrega (3) →
     Concluído (4). A etapa "Sinal" (que na prática nunca era atingida — o
     avanço automático já pulava direto dela) também saiu da régua; o campo
     de dinheiro "Sinal / Entrada (R$)" continua existindo normalmente, só
     não é mais uma etapa visual. "Tecido" continua existindo como
     tarefa/lembrete opcional (quando marcado "Precisa comprar tecido?"),
     só deixou de ser uma etapa própria da régua.

  3) SUPORTE A PROSPECT: `dialog_nova_encomenda` ganhou os parâmetros
     opcionais `nome_fixo` e `prospect_id`, usados pelo novo
     `modulos/mod_prospect.py` para converter um prospect (só nome) em um
     pedido completo — o nome já vem preenchido e travado, e ao criar a
     encomenda o prospect correspondente é excluído da lista automaticamente
     (usa `database.prospects_deletar`).

⚠️ ATENÇÃO — ponto que precisa de um ajuste manual em `main.py` (fora deste
   módulo, não alterado aqui a pedido): o botão "✅ Feito" em
   `_secao_tarefas_e_entregas_hoje` (Agenda) tem uma lógica de avanço de
   etapa HARDCODED para a numeração ANTIGA (1-7, com saltos manuais). Com a
   régua nova (1-4) esse trecho precisa ser trocado — veja o texto que
   acompanha esta entrega para o snippet exato.

Ponto de entrada usados pelo main.py:
  renderizar_contratos(), renderizar_nova_encomenda(),
  renderizar_gerenciar_pedidos(), _abrir_popup_pedido(enc, cancelado),
  _dialog_editar_dia(dt_str, tasks_dia), _dialog_editar_data_tarefa(row)
"""

import os
import io
import time
import hashlib
import calendar
from datetime import date, timedelta

import streamlit as st
import pandas as pd

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

# ── Helpers compartilhados ───────────────────────────────────────────────────
from modulos.utils import (
    MESES_PT,
    agora_br, hoje_brasilia, converter_para_data,
    formatar_data_br, formatar_data_hora_br, brl,
)

# ── Regras de agenda (validação pura, sem Firestore/Streamlit) ─────────────
from modulos.regras_agenda import (
    validar_data_confeccao,
    dias_confeccao_ocupados, dias_com_provas_lotadas,
    LIMITE_PROVAS_PARA_CONFECCAO,
)

# ── Banco de dados Firestore ─────────────────────────────────────────────────
from database import (
    cfg_get,
    clientes_listar, clientes_inserir, clientes_atualizar,
    encomendas_listar, encomendas_inserir, encomendas_atualizar,
    encomendas_buscar, encomendas_cancelar,
    cronograma_listar, cronograma_inserir, cronograma_atualizar, cronograma_deletar,
    prospects_deletar,
)

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES (fonte única — main.py importa DIC_MEDIDAS, SENHA_DELETE e
# LOGO_PATH daqui para as suas próprias telas que ainda precisam delas)
# ══════════════════════════════════════════════════════════════════════════════
# [v16] Régua enxuta: sem "Visita" (Data Medidas) e sem "Sinal" (que na
# prática nunca era atingida — o avanço automático já pulava direto dela).
# Confecção agora é a ETAPA 1.
ETAPAS = {
    1: ("🪡", "Confecção"),
    2: ("👗", "Prova"),
    3: ("🎁", "Entrega"),
    4: ("✅", "Concluído"),
}

DIC_MEDIDAS = {
    "Ombros":      "ombros",
    "Costas":      "costas",
    "Alt. Busto":  "alt_busto",
    "Alt. Frente": "alt_frente",
    "Busto":       "busto",
    "Cintura":     "cintura",
    "Quadril":     "quadril",
    "Larg. Braço": "larg_braco",
    "Comp. Braço": "comp_braco",
    "Comprimento": "comprimento",
    "Comp. Perna": "comp_perna",
    "Coxa":        "coxa",
    "Gancho":      "gancho",
    "Colarinho":   "colarinho",
}

SENHA_DELETE = "Qmerd@10"

LOGO_PATH = "lila.png"

# ══════════════════════════════════════════════════════════════════════════════
# MINI-CALENDÁRIO DE OCUPAÇÃO — Data da Confecção
# ══════════════════════════════════════════════════════════════════════════════
def _render_ocupacao_confeccao(df_enc: pd.DataFrame, ano: int, mes: int, excluir_id: str | None = None):
    """
    Mostra um mini-calendário do mês/ano informados, com legenda visual:
      🔴 dia já reservado para confecção de outro cliente (bloqueado)
      🟡 dia com mais de LIMITE_PROVAS_PARA_CONFECCAO provas marcadas
         (bloqueado para confecção, mas SEM limite de provas em si)
    Puramente informativo: a validação de verdade acontece ao salvar,
    usando as mesmas funções de `modulos/regras_agenda.py`.
    """
    ocupados = dias_confeccao_ocupados(df_enc, excluir_id)
    lotados_prova = dias_com_provas_lotadas(df_enc, excluir_id)

    st.caption(
        f"📌 Ocupação de **{MESES_PT[mes-1]}/{ano}** para a Data da Confecção — "
        f"🔴 já reservado por outro cliente &nbsp;·&nbsp; "
        f"🟡 mais de {LIMITE_PROVAS_PARA_CONFECCAO} provas nesse dia (bloqueado p/ confecção)"
    )
    cols_h = st.columns(7)
    for i, d in enumerate(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]):
        cols_h[i].markdown(
            f"<center style='font-size:0.65rem;color:#8b7355'><b>{d}</b></center>",
            unsafe_allow_html=True,
        )
    for semana in calendar.monthcalendar(ano, mes):
        cols_s = st.columns(7)
        for i, dia in enumerate(semana):
            if dia == 0:
                cols_s[i].markdown("&nbsp;", unsafe_allow_html=True)
                continue
            dt_obj = date(ano, mes, dia)
            marca = ""
            if dt_obj in ocupados:
                marca = " 🔴"
            elif dt_obj in lotados_prova:
                marca = " 🟡"
            cols_s[i].markdown(
                f"<center style='font-size:0.74rem;color:#3d1f10'>{dia}{marca}</center>",
                unsafe_allow_html=True,
            )


def _render_ocupacao_confeccao_navegavel(
    df_enc: pd.DataFrame, key_prefix: str, data_referencia: date, excluir_id: str | None = None,
):
    """
    Mesmo mini-calendário de ocupação da Confecção, mas com botões de
    navegação (◀ Anterior / Próximo ▶) para folhear os meses seguintes —
    útil para checar a agenda antes de decidir a Data da Confecção.
    O mês navegado fica guardado em session_state, então a navegação não
    "some" a cada rerun; para voltar ao mês da data já escolhida no
    formulário, use o botão "📍 Ir para o mês da data escolhida".
    """
    state_key = f"{key_prefix}_mes_ref_conf"
    if state_key not in st.session_state:
        st.session_state[state_key] = data_referencia.replace(day=1)

    ref = st.session_state[state_key]

    nav1, nav_tit, nav2, nav3 = st.columns([1, 2, 1, 2.4])
    if nav1.button("◀", key=f"{key_prefix}_conf_prev", use_container_width=True):
        st.session_state[state_key] = (ref.replace(day=1) - timedelta(days=1)).replace(day=1)
        st.rerun()
    if nav2.button("▶", key=f"{key_prefix}_conf_next", use_container_width=True):
        st.session_state[state_key] = (ref.replace(day=28) + timedelta(days=4)).replace(day=1)
        st.rerun()
    if nav3.button("📍 Ir para o mês da data escolhida", key=f"{key_prefix}_conf_ir_data", use_container_width=True):
        st.session_state[state_key] = data_referencia.replace(day=1)
        st.rerun()

    ref = st.session_state[state_key]
    nav_tit.markdown(
        f"<center style='color:#6b3a22;font-weight:700;'>{MESES_PT[ref.month-1]}/{ref.year}</center>",
        unsafe_allow_html=True,
    )

    _render_ocupacao_confeccao(df_enc, ref.year, ref.month, excluir_id=excluir_id)


# ══════════════════════════════════════════════════════════════════════════════
# SENHA ADM PARA CONFLITO DE DATA DA CONFECÇÃO  [v14]
# ══════════════════════════════════════════════════════════════════════════════
def _checar_confeccao_com_senha(df_check: pd.DataFrame, data_confeccao: date, escopo_key: str,
                                 excluir_id: str | None = None, dados_para_salvar: dict | None = None) -> bool:
    """
    Verifica a exclusividade da Data da Confecção. Sem conflito: retorna
    True imediatamente (fluxo normal, o chamador salva com os valores atuais
    dos widgets). Com conflito: grava o aviso + uma FOTO de `dados_para_salvar`
    em session_state e força um st.rerun().
    """
    ok_conf, msg_conf = validar_data_confeccao(df_check, data_confeccao, excluir_id=excluir_id)
    pend_key = f"pend_conf_{escopo_key}"

    if ok_conf:
        st.session_state.pop(pend_key, None)
        return True

    st.session_state[pend_key] = {"msg": msg_conf, "dados": dados_para_salvar}
    st.rerun()


def _render_confirmacao_senha_confeccao(escopo_key: str):
    """
    Se houver um conflito de Data da Confecção pendente para `escopo_key`,
    mostra o aviso de bloqueio + campo de senha ADM + botões de
    confirmar/cancelar. Retorna a FOTO de `dados_para_salvar` (gravada por
    `_checar_confeccao_com_senha`) SOMENTE no clique em que a senha correta
    é confirmada.
    """
    pend_key = f"pend_conf_{escopo_key}"
    pend = st.session_state.get(pend_key)
    if not pend:
        return None

    st.error(pend["msg"])
    st.warning(
        "🔑 Duas Confecções no mesmo dia não são permitidas sem autorização. "
        "Informe a senha de administrador para salvar mesmo assim."
    )
    senha_digitada = st.text_input(
        "Senha ADM", type="password", key=f"senha_{pend_key}",
        placeholder="Digite a senha para liberar",
    )
    col_c1, col_c2 = st.columns(2)
    confirmou = col_c1.button("✅ Confirmar com senha", key=f"btn_ok_{pend_key}", use_container_width=True)
    cancelou  = col_c2.button("❌ Cancelar", key=f"btn_no_{pend_key}", use_container_width=True)

    if cancelou:
        st.session_state.pop(pend_key, None)
        st.rerun()

    if confirmou:
        if senha_digitada == SENHA_DELETE:
            dados = pend.get("dados")
            st.session_state.pop(pend_key, None)
            return dados if dados is not None else {}
        else:
            st.error("❌ Senha incorreta. Não é possível salvar com dois clientes na mesma Data da Confecção.")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PDF — CONTRATO  (usado pelo BLOCO CONTRATOS e também na criação de encomendas)
# ══════════════════════════════════════════════════════════════════════════════
def _marrom():  return colors.HexColor("#3d1f10")
def _bege():    return colors.HexColor("#fdf6ee")
def _dourado(): return colors.HexColor("#c9a227")

def gerar_pdf_contrato(enc: dict, cpf: str, rg: str) -> bytes:
    buf = io.BytesIO()
    styles = getSampleStyleSheet()

    s_titulo = ParagraphStyle("titulo", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=15, textColor=_marrom(),
        alignment=TA_CENTER, spaceAfter=3)
    s_subtit = ParagraphStyle("subtit", parent=styles["Normal"],
        fontName="Helvetica", fontSize=8, textColor=_dourado(),
        alignment=TA_CENTER, spaceAfter=10, leading=12)
    s_cls_tit = ParagraphStyle("clt", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=10, textColor=_marrom(),
        spaceBefore=10, spaceAfter=3, leading=13)
    s_body = ParagraphStyle("body", parent=styles["Normal"],
        fontName="Helvetica", fontSize=9.5, textColor=colors.HexColor("#2d1f14"),
        leading=15, spaceAfter=5, alignment=TA_JUSTIFY)
    s_rodape = ParagraphStyle("rodape", parent=styles["Normal"],
        fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#9e8a78"),
        alignment=TA_CENTER)

    seed = f"{enc.get('cliente','')}{enc.get('peca','')}{time.time()}"
    num_contrato = hashlib.md5(seed.encode()).hexdigest()[:10].upper()
    emitido_em_str = agora_br().strftime("%d/%m/%Y às %H:%M")

    dt_prova   = formatar_data_br(enc.get("data_prova", ""))
    tem_prova2 = bool(str(enc.get("data_prova2") or "").strip())
    dt_prova2  = formatar_data_br(enc.get("data_prova2", "")) if tem_prova2 else ""
    dt_entrega = formatar_data_br(enc.get("data_entrega", ""))
    dt_tecido  = formatar_data_br(enc.get("data_tecido", "")) if enc.get("precisa_tecido") else "—"
    dt_confec  = formatar_data_br(enc.get("data_confeccao", ""))

    valor_total   = float(enc.get("valor_total", 0) or 0)
    sinal         = float(enc.get("sinal", 0) or 0)
    restante      = valor_total - sinal
    forma_pag     = enc.get("forma_pagamento", "A combinar")
    cliente_nome  = enc.get("cliente", "—")
    peca_nome     = enc.get("peca", "—")
    descricao     = enc.get("descricao", "") or ""
    obs           = enc.get("observacoes", "") or ""

    cnpj_val = cfg_get("cnpj")
    tel_val  = cfg_get("telefone")
    end_val  = cfg_get("endereco")

    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=2.0*cm, leftMargin=2.0*cm,
        topMargin=2.2*cm,   bottomMargin=2.2*cm)
    story = []

    s_hdr_empresa = ParagraphStyle("hdr_emp", fontName="Helvetica-Bold", fontSize=14,
        textColor=colors.white, alignment=TA_LEFT, leading=18)
    s_hdr_slogan = ParagraphStyle("hdr_slo", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#f5e6d3"), alignment=TA_LEFT, leading=11, spaceBefore=2)
    s_hdr_info = ParagraphStyle("hdr_inf", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#f5dfc0"), alignment=TA_RIGHT, leading=12)

    if os.path.exists(LOGO_PATH):
        logo_img = RLImage(LOGO_PATH, width=2.4*cm, height=2.4*cm)
        logo_cell = logo_img
    else:
        logo_cell = Paragraph("🧵", ParagraphStyle("lc", fontName="Helvetica-Bold",
            fontSize=28, textColor=colors.HexColor("#c9a227"), alignment=TA_CENTER))

    nome_empresa_cell = Table([
        [Paragraph("LILA CLOSET ATELIER", s_hdr_empresa)],
        [Paragraph("Costura sob medida com excelência", s_hdr_slogan)],
    ], colWidths=["100%"])
    nome_empresa_cell.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),1),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
    ]))

    left_cell = Table([[logo_cell, nome_empresa_cell]], colWidths=[2.8*cm, "100%"])
    left_cell.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),0),
        ("BOTTOMPADDING",(0,0),(-1,-1),0),("LEFTPADDING",(0,0),(-1,-1),0),
        ("RIGHTPADDING",(0,0),(0,-1),8),("RIGHTPADDING",(1,0),(1,-1),0),
    ]))

    right_cell = Paragraph(
        f"CNPJ: {cnpj_val}<br/>{end_val}<br/>Tel.: {tel_val}", s_hdr_info)

    hdr_table = Table([[left_cell, right_cell]], colWidths=["60%","40%"])
    hdr_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),_marrom()),
        ("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14),
        ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE COSTURA SOB MEDIDA", s_titulo))
    story.append(Paragraph(
        f"Contrato N.º <b>{num_contrato}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Emitido em: <b>{emitido_em_str}</b> &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Validade jurídica: Art. 421 CC/2002 e MP 2.200-2/2001", s_subtit))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_dourado()))
    story.append(Spacer(1, 6))

    story.append(Paragraph("CLÁUSULA 1ª – IDENTIFICAÇÃO DAS PARTES", s_cls_tit))
    s_ptab = ParagraphStyle("pt", fontName="Helvetica", fontSize=9, leading=14,
        textColor=colors.HexColor("#2d1f14"))
    s_ptab_hdr = ParagraphStyle("pth", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.white, alignment=TA_CENTER)
    partes_data = [
        [Paragraph("<b>CONTRATADA</b>", s_ptab_hdr), Paragraph("<b>CONTRATANTE</b>", s_ptab_hdr)],
        [
            Paragraph(f"<b>LILA CLOSET ATELIER</b><br/>CNPJ: {cnpj_val}<br/>Tel.: {tel_val}<br/>{end_val}", s_ptab),
            Paragraph(f"<b>{cliente_nome}</b><br/>CPF: {cpf}<br/>RG: {rg}", s_ptab),
        ],
    ]
    partes_t = Table(partes_data, colWidths=["50%","50%"])
    partes_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),_marrom()),
        ("TOPPADDING",(0,0),(-1,0),8),("BOTTOMPADDING",(0,0),(-1,0),8),
        ("BACKGROUND",(0,1),(-1,1),_bege()),
        ("TOPPADDING",(0,1),(-1,1),10),("BOTTOMPADDING",(0,1),(-1,1),10),
        ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
        ("BOX",(0,0),(-1,-1),1,_dourado()),("LINEAFTER",(0,0),(0,-1),1,_dourado()),
        ("VALIGN",(0,1),(-1,1),"TOP"),
    ]))
    story.append(partes_t)
    story.append(Spacer(1, 6))

    story.append(Paragraph("CLÁUSULA 2ª – DO OBJETO DO CONTRATO", s_cls_tit))
    obj_text = (f"O presente contrato tem por objeto a <b>confecção sob medida</b> da seguinte peça: "
                f"<b>{peca_nome}</b>.")
    if descricao:
        obj_text += f" Descrição adicional: {descricao}."
    obj_text += (" A execução será realizada conforme as medidas fornecidas pela CONTRATANTE, "
                 "com os ajustes necessários durante a etapa de prova.")
    story.append(Paragraph(obj_text, s_body))

    story.append(Paragraph("CLÁUSULA 3ª – DOS PRAZOS E CRONOGRAMA", s_cls_tit))
    story.append(Paragraph(
        "O início da produção fica condicionado ao recebimento do <b>sinal acordado</b>. "
        "Os prazos abaixo são estimativas e podem ser ajustados por mútuo acordo.", s_body))

    s_et_hdr = ParagraphStyle("eth", fontName="Helvetica-Bold", fontSize=8.5,
        textColor=colors.white, alignment=TA_CENTER)
    etapas_rows = [
        [Paragraph("<b>Etapa</b>", s_et_hdr), Paragraph("<b>Descrição</b>", s_et_hdr), Paragraph("<b>Data Prevista</b>", s_et_hdr)],
        ["🛍️ Tecidos",  "Compra e separação dos tecidos e aviamentos",         dt_tecido],
        ["🪡 Confecção", "Início da produção da peça na medida solicitada",     dt_confec],
        ["👗 Prova",     "Prova com a cliente para ajustes finos e acabamentos", dt_prova],
    ]
    if tem_prova2:
        etapas_rows.append(["👗 2ª Prova", "Segunda prova para ajustes adicionais", dt_prova2])
    etapas_rows.append(["🎁 Entrega",   "Entrega final da peça pronta e devidamente embalada", dt_entrega])
    cron_t = Table(etapas_rows, colWidths=["22%","48%","30%"])
    cron_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),_marrom()),("FONTSIZE",(0,1),(-1,-1),9),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"),("ALIGN",(2,1),(2,-1),"CENTER"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,_bege()]),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("BOX",(0,0),(-1,-1),1,_dourado()),
        ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story.append(cron_t)
    story.append(Spacer(1, 6))

    story.append(Paragraph("CLÁUSULA 4ª – DO VALOR E FORMA DE PAGAMENTO", s_cls_tit))
    story.append(Paragraph(
        f"O valor total acordado é de <b>{brl(valor_total)}</b>, "
        f"sendo <b>{brl(sinal)}</b> como sinal no ato da contratação "
        f"e o saldo de <b>{brl(restante)}</b> na entrega. "
        f"Forma de pagamento: <b>{forma_pag}</b>.", s_body))

    s_fin_hdr = ParagraphStyle("fnh", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white)
    s_fin_hdr_r = ParagraphStyle("fnhr", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.white, alignment=TA_RIGHT)
    fin_rows = [
        [Paragraph("<b>Descrição</b>", s_fin_hdr), Paragraph("<b>Valor</b>", s_fin_hdr_r)],
        ["Valor Total do Serviço", brl(valor_total)],
        ["Sinal / Entrada (pago no ato)", brl(sinal)],
        ["Saldo Restante (pago na entrega)", brl(restante)],
        [Paragraph(f"<b>Forma de Pagamento:</b> {forma_pag}", ParagraphStyle("fp",
            fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#2d1f14"))), ""],
    ]
    fin_t = Table(fin_rows, colWidths=["65%","35%"])
    fin_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),_marrom()),("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("FONTSIZE",(0,1),(-1,-1),9.5),("FONTNAME",(1,1),(1,-2),"Helvetica-Bold"),
        ("TEXTCOLOR",(1,2),(1,2),colors.HexColor("#c9a227")),
        ("TEXTCOLOR",(1,3),(1,3),colors.HexColor("#1b5e20")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,_bege()]),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
        ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
        ("BOX",(0,0),(-1,-1),1,_dourado()),
        ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#e0d5c9")),
        ("SPAN",(0,4),(1,4)),
    ]))
    story.append(fin_t)
    story.append(Spacer(1, 6))

    story.append(Paragraph("CLÁUSULA 5ª – DO CANCELAMENTO E DESISTÊNCIA", s_cls_tit))
    story.append(Paragraph(
        "5.1 – Em caso de desistência pela CONTRATANTE após a assinatura, "
        "o <b>sinal não será devolvido</b>, pois cobre reserva de agenda e compra de materiais. "
        "<br/>5.2 – Cancelamento por responsabilidade da CONTRATADA enseja devolução integral dos valores pagos. "
        "<br/>5.3 – Peças com medidas confirmadas e em produção não permitem alterações de modelo sem custo adicional.",
        s_body))

    story.append(Paragraph("CLÁUSULA 6ª – DA GARANTIA DE SERVIÇO", s_cls_tit))
    story.append(Paragraph(
        "A CONTRATADA garante <b>30 dias</b> a partir da entrega para identificação de defeitos "
        "de costura ou acabamento, obrigando-se à correção sem custo. "
        "Avarias por uso inadequado ou lavagem incorreta estão excluídas desta garantia.", s_body))

    story.append(Paragraph("CLÁUSULA 7ª – PROTEÇÃO DE DADOS (LGPD – Lei 13.709/2018)", s_cls_tit))
    story.append(Paragraph(
        "Os dados pessoais coletados (nome, CPF, RG, medidas) são utilizados exclusivamente "
        "para execução dos serviços contratados e não serão compartilhados com terceiros.", s_body))

    story.append(Paragraph("CLÁUSULA 8ª – DO FORO E ASSINATURA DIGITAL", s_cls_tit))
    story.append(Paragraph(
        "Fica eleito o foro da Comarca de Embu das Artes – SP. "
        "Este instrumento pode ser assinado digitalmente via <b>GOV.BR</b> "
        "(assinador.iti.br), com validade jurídica pela MP 2.200-2/2001.", s_body))

    if obs:
        story.append(Paragraph("OBSERVAÇÕES ADICIONAIS", s_cls_tit))
        story.append(Paragraph(obs, s_body))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e0d5c9")))
    story.append(Spacer(1, 8))
    gov_data = [[Paragraph(
        "✅ <b>ASSINAR DIGITALMENTE VIA GOV.BR — assinador.iti.br/assinatura/index.xhtml</b>",
        ParagraphStyle("gov", fontName="Helvetica-Bold", fontSize=8.5,
            textColor=colors.HexColor("#1b5e20"), alignment=TA_CENTER, leading=13))]]
    gov_t = Table(gov_data, colWidths=["100%"])
    gov_t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#e8f5e9")),
        ("BOX",(0,0),(-1,-1),1.5,colors.HexColor("#2e7d32")),
        ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),
    ]))
    story.append(gov_t)
    story.append(Spacer(1, 14))

    s_asn = ParagraphStyle("asn", fontName="Helvetica", fontSize=9,
        alignment=TA_CENTER, textColor=colors.HexColor("#2d1f14"), leading=14)
    asn_data = [
        [Paragraph("<br/><br/>________________________________________", s_asn),
         Paragraph("<br/><br/>________________________________________", s_asn)],
        [Paragraph(f"<b>{cliente_nome}</b><br/>CONTRATANTE<br/>CPF: {cpf}", s_asn),
         Paragraph(f"<b>Lila Closet Atelier</b><br/>CONTRATADA<br/>CNPJ: {cnpj_val}", s_asn)],
    ]
    asn_t = Table(asn_data, colWidths=["50%","50%"])
    asn_t.setStyle(TableStyle([
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LINEAFTER",(0,0),(0,-1),0.5,colors.HexColor("#e0d5c9")),
    ]))
    story.append(asn_t)
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0d5c9")))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"Lila Closet Atelier · {tel_val} | Contrato N.º {num_contrato} · {emitido_em_str}", s_rodape))

    doc.build(story)
    return buf.getvalue()

# ══════════════════════════════════════════════════════════════════════════════
# COMPONENTES COMPARTILHADOS — usados pelos blocos CONTRATOS, ENCOMENDAS e AGENDA
# ══════════════════════════════════════════════════════════════════════════════

# ── Popup: Nova Encomenda Rápida (a partir do calendário, ou de um Prospect) ──
@st.dialog("🛍️ Nova Encomenda Rápida", width="large")
def dialog_nova_encomenda(data_pre: date | None = None, nome_fixo: str | None = None,
                           prospect_id: str | None = None):
    """
    `nome_fixo` e `prospect_id` são usados pelo `modulos/mod_prospect.py` na
    conversão de um Prospect em pedido: quando `nome_fixo` vem preenchido,
    o campo de cliente já aparece travado com esse nome (sem a escolha de
    "Selecionar existente / Cadastrar nova"), e ao criar a encomenda com
    sucesso o prospect correspondente (`prospect_id`) é excluído da lista
    automaticamente — ele "virou" o pedido.
    """
    resultado = st.session_state.get("_dlg_enc_resultado")
    if resultado:
        st.success(f"✅ Encomenda **{resultado['peca']}** criada para **{resultado['cliente']}**!")
        if resultado.get("pdf_bytes"):
            col_pdf, col_gov = st.columns(2)
            col_pdf.download_button(
                "📥 BAIXAR CONTRATO PDF", data=resultado["pdf_bytes"],
                file_name=f"Contrato_{resultado['cliente'].replace(' ','_')}.pdf",
                mime="application/pdf", use_container_width=True, key="dlg_dl_pdf_resultado",
            )
            col_gov.link_button("✍️ ASSINAR VIA GOV.BR",
                url="https://assinador.iti.br/assinatura/index.xhtml",
                use_container_width=True)
        else:
            st.info("💡 Preencha CPF e RG (seção Dados para Contrato) para gerar o contrato automaticamente.")
        if st.button("✅ Fechar", use_container_width=True, type="primary", key="dlg_btn_fechar_resultado"):
            del st.session_state["_dlg_enc_resultado"]
            st.rerun()
        return

    d_base = data_pre or hoje_brasilia()

    df_clis_dlg = clientes_listar()
    clis_dlg = df_clis_dlg["nome"].tolist() if not df_clis_dlg.empty else []

    st.markdown("##### 👤 Cliente")
    if nome_fixo:
        st.info(f"Convertendo prospect em pedido: **{nome_fixo}**")
        modo_cli = "Selecionar existente" if nome_fixo in clis_dlg else "Cadastrar nova"
        cli_sel_dlg = nome_fixo
        cli_tel_dlg = ""
    else:
        modo_cli = st.radio(
            "Cliente", ["Selecionar existente", "Cadastrar nova"],
            horizontal=True, key="dlg_modo_cli", label_visibility="collapsed",
            index=0 if clis_dlg else 1,
        )
        cli_tel_dlg = ""
        if modo_cli == "Selecionar existente" and clis_dlg:
            cli_sel_dlg = st.selectbox("Cliente *", clis_dlg, key="dlg_cli_sel")
        else:
            col_cn1, col_cn2 = st.columns(2)
            cli_sel_dlg = col_cn1.text_input("Nome da nova cliente *", key="dlg_cli_novo")
            cli_tel_dlg = col_cn2.text_input("Telefone / WhatsApp", key="dlg_cli_tel")

    st.markdown("##### 🧵 Peça / Serviço")
    peca_dlg = st.text_input("Peça / Serviço *", placeholder="Ex: Vestido de festa…", key="dlg_peca")
    descricao_dlg = st.text_area("Descrição detalhada", key="dlg_descricao", height=70)

    st.markdown("##### 💰 Valores")
    col_v1, col_v2, col_v3 = st.columns(3)
    v_total_dlg = col_v1.number_input("Valor Total (R$)", min_value=0.0, step=50.0, format="%.2f", key="dlg_valor")
    v_sinal_dlg = col_v2.number_input("Sinal / Entrada (R$)", min_value=0.0, step=50.0, format="%.2f", key="dlg_sinal")
    forma_pag_dlg = col_v3.selectbox("Forma de Pagamento",
        ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"], key="dlg_forma_pag")

    st.markdown("##### 📅 Datas")
    st.caption("A primeira etapa do pedido é a Data da Confecção — não há mais um campo separado de 'Data Medidas'.")

    d_confeccao_dlg = st.date_input(
        "🪡 Data da Confecção", value=d_base + timedelta(days=7),
        key="dlg_confeccao", format="DD/MM/YYYY"
    )
    _render_ocupacao_confeccao_navegavel(encomendas_listar(cancelado=False), key_prefix="dlg", data_referencia=d_confeccao_dlg)

    d_prova_dlg = st.date_input(
        "👗 Data da Prova", value=d_base + timedelta(days=25), key="dlg_prova", format="DD/MM/YYYY"
    )
    st.caption(
        f"ℹ️ Não há limite de provas por dia. Mas se um dia passar de "
        f"{LIMITE_PROVAS_PARA_CONFECCAO} provas, ele fica bloqueado para receber Confecção (veja 🟡 acima)."
    )

    tem_prova2_dlg = st.checkbox("Precisa de uma segunda prova?", key="dlg_tem_prova2")
    d_prova2_dlg = None
    if tem_prova2_dlg:
        d_prova2_dlg = st.date_input(
            "👗 Data da 2ª Prova", value=d_prova_dlg + timedelta(days=7),
            key="dlg_prova2", format="DD/MM/YYYY",
        )

    precisa_tecido_dlg = st.checkbox("Precisa comprar tecido?", key="dlg_tecido")
    d_tecido_dlg = d_base + timedelta(days=3)
    if precisa_tecido_dlg:
        d_tecido_dlg = st.date_input(
            "🛍️ Data Compra do Tecido", value=d_tecido_dlg, key="dlg_data_tecido", format="DD/MM/YYYY"
        )

    d_entrega_dlg = st.date_input(
        "🎁 Data de Entrega", value=d_base + timedelta(days=30), key="dlg_entrega", format="DD/MM/YYYY"
    )

    st.markdown("##### 📄 Dados para Contrato")
    st.caption("Preencha CPF e RG para o contrato ser gerado automaticamente assim que a encomenda for criada.")
    col_c1, col_c2 = st.columns(2)
    cpf_dlg = col_c1.text_input("CPF da cliente", placeholder="000.000.000-00", key="dlg_cpf")
    rg_dlg  = col_c2.text_input("RG da cliente",  placeholder="00.000.000-0", key="dlg_rg")
    obs_dlg = st.text_area("Observações", key="dlg_obs", height=68)

    def _criar_encomenda_dlg(dados_form: dict | None = None):
        """Grava a encomenda + tarefas + PDF e mostra o resultado. `dados_form`
        é uma FOTO dos campos preenchidos, tirada no clique em "Criar
        Encomenda" — usada tanto no fluxo normal quanto após confirmar a
        senha ADM, para garantir que o que é salvo é exatamente o que o
        usuário preencheu naquele clique. Se vier de um Prospect
        (`prospect_id`), o prospect é excluído da lista ao final."""
        if dados_form is None:
            dados_form = dict(
                nome_final=(cli_sel_dlg.strip() if isinstance(cli_sel_dlg, str) else cli_sel_dlg),
                modo_cli=modo_cli, cli_tel_dlg=cli_tel_dlg,
                peca_dlg=peca_dlg, descricao_dlg=descricao_dlg,
                v_total_dlg=v_total_dlg, v_sinal_dlg=v_sinal_dlg, forma_pag_dlg=forma_pag_dlg,
                d_confeccao_dlg=d_confeccao_dlg, d_prova_dlg=d_prova_dlg,
                tem_prova2_dlg=tem_prova2_dlg, d_prova2_dlg=d_prova2_dlg,
                precisa_tecido_dlg=precisa_tecido_dlg, d_tecido_dlg=d_tecido_dlg,
                d_entrega_dlg=d_entrega_dlg, cpf_dlg=cpf_dlg, rg_dlg=rg_dlg, obs_dlg=obs_dlg,
            )

        nome_final = dados_form["nome_final"]
        f_modo_cli = dados_form["modo_cli"]
        f_peca = dados_form["peca_dlg"]; f_desc = dados_form["descricao_dlg"]
        f_vtotal = dados_form["v_total_dlg"]; f_vsinal = dados_form["v_sinal_dlg"]
        f_fpag = dados_form["forma_pag_dlg"]
        f_dconf = dados_form["d_confeccao_dlg"]
        f_dprova = dados_form["d_prova_dlg"]; f_temprova2 = dados_form["tem_prova2_dlg"]
        f_dprova2 = dados_form["d_prova2_dlg"]; f_precisatecido = dados_form["precisa_tecido_dlg"]
        f_dtecido = dados_form["d_tecido_dlg"]; f_dentrega = dados_form["d_entrega_dlg"]
        f_cpf = dados_form["cpf_dlg"]; f_rg = dados_form["rg_dlg"]; f_obs = dados_form["obs_dlg"]

        if f_modo_cli != "Selecionar existente":
            clientes_inserir({
                "nome": nome_final, "telefone": dados_form["cli_tel_dlg"].strip(),
                "criado_em": agora_br().isoformat(),
            })

        e_id = encomendas_inserir({
            "cliente": nome_final, "peca": f_peca.strip(),
            "descricao": f_desc.strip(), "valor_total": f_vtotal, "sinal": f_vsinal,
            "valor_recebido": f_vsinal,
            "etapa": 1, "precisa_tecido": 1 if f_precisatecido else 0,
            "data_tecido":    f_dtecido.isoformat(),
            "data_confeccao": f_dconf.isoformat(),
            "data_prova":     f_dprova.isoformat(),
            "tem_prova2":     1 if f_temprova2 else 0,
            "data_prova2":    f_dprova2.isoformat() if f_dprova2 else "",
            "data_entrega":   f_dentrega.isoformat(),
            "cpf_cliente": f_cpf.strip(), "rg_cliente": f_rg.strip(),
            "forma_pagamento": f_fpag, "observacoes": f_obs.strip(),
            "cancelado": 0,
            "criado_em": agora_br().isoformat(),
        })

        desc_dlg = f"{f_peca.strip()} ({nome_final})"
        tarefas_auto_dlg = []
        if f_precisatecido:
            tarefas_auto_dlg.append((f"🛍️ Tecido: {desc_dlg}", "Compras", 1.0, f_dtecido.isoformat()))
        tarefas_auto_dlg.append((f"🪡 Confecção: {desc_dlg}", "Costura", 3.0, f_dconf.isoformat()))
        tarefas_auto_dlg.append((f"👗 Prova: {desc_dlg}",     "Costura", 1.0, f_dprova.isoformat()))
        if f_temprova2 and f_dprova2:
            tarefas_auto_dlg.append((f"👗 2ª Prova: {desc_dlg}", "Costura", 1.0, f_dprova2.isoformat()))
        tarefas_auto_dlg.append((f"🎁 Entrega: {desc_dlg}",   "Costura", 0.5, f_dentrega.isoformat()))

        for tarefa_a, cat_a, hrs_a, dt_a in tarefas_auto_dlg:
            cronograma_inserir({
                "tarefa": tarefa_a, "categoria": cat_a, "horas": hrs_a,
                "data": dt_a, "frequencia": "Pontual", "concluida": 0,
                "encomenda_id": e_id, "tipo_agenda": "Trabalho",
            })

        pdf_bytes_dlg = None
        if f_cpf.strip() and f_rg.strip():
            enc_dict_pdf = {
                "cliente": nome_final, "peca": f_peca.strip(),
                "descricao": f_desc.strip(), "valor_total": f_vtotal,
                "sinal": f_vsinal, "forma_pagamento": f_fpag,
                "data_tecido": f_dtecido.isoformat() if f_precisatecido else "",
                "data_confeccao": f_dconf.isoformat(),
                "data_prova": f_dprova.isoformat(),
                "data_prova2": f_dprova2.isoformat() if f_dprova2 else "",
                "data_entrega": f_dentrega.isoformat(),
                "precisa_tecido": 1 if f_precisatecido else 0,
                "observacoes": f_obs.strip(),
            }
            pdf_bytes_dlg = gerar_pdf_contrato(enc_dict_pdf, f_cpf.strip(), f_rg.strip())

        if prospect_id:
            prospects_deletar(str(prospect_id))

        st.session_state["_dlg_enc_resultado"] = {
            "cliente": nome_final, "peca": f_peca.strip(), "pdf_bytes": pdf_bytes_dlg,
        }
        st.success(f"✅ Encomenda **{f_peca.strip()}** criada para **{nome_final}**!")
        if pdf_bytes_dlg:
            col_pdf, col_gov = st.columns(2)
            col_pdf.download_button(
                "📥 BAIXAR CONTRATO PDF", data=pdf_bytes_dlg,
                file_name=f"Contrato_{nome_final.replace(' ','_')}.pdf",
                mime="application/pdf", use_container_width=True, key="dlg_dl_pdf_imediato",
            )
            col_gov.link_button("✍️ ASSINAR VIA GOV.BR",
                url="https://assinador.iti.br/assinatura/index.xhtml",
                use_container_width=True)
        else:
            st.info("💡 Preencha CPF e RG para gerar o contrato automaticamente.")
        if st.button("✅ Fechar", use_container_width=True, type="primary", key="dlg_btn_fechar_imediato"):
            del st.session_state["_dlg_enc_resultado"]
            st.rerun()

    st.markdown("")
    col_ok, col_cancel = st.columns(2)

    if col_ok.button("✅ Criar Encomenda", use_container_width=True, type="primary", key="dlg_btn_ok"):
        nome_final = cli_sel_dlg.strip() if isinstance(cli_sel_dlg, str) else cli_sel_dlg

        if not nome_final:
            st.error("Informe o nome da cliente.")
            return
        if not peca_dlg.strip():
            st.error("Informe a peça / serviço.")
            return

        dados_atuais_dlg = dict(
            nome_final=nome_final, modo_cli=modo_cli, cli_tel_dlg=cli_tel_dlg,
            peca_dlg=peca_dlg, descricao_dlg=descricao_dlg,
            v_total_dlg=v_total_dlg, v_sinal_dlg=v_sinal_dlg, forma_pag_dlg=forma_pag_dlg,
            d_confeccao_dlg=d_confeccao_dlg, d_prova_dlg=d_prova_dlg,
            tem_prova2_dlg=tem_prova2_dlg, d_prova2_dlg=d_prova2_dlg,
            precisa_tecido_dlg=precisa_tecido_dlg, d_tecido_dlg=d_tecido_dlg,
            d_entrega_dlg=d_entrega_dlg, cpf_dlg=cpf_dlg, rg_dlg=rg_dlg, obs_dlg=obs_dlg,
        )

        # ── Validação de agenda (exclusividade da Data da Confecção) ──
        # Sem conflito: cria direto. Com conflito: pede senha ADM (o helper
        # já cuida de gravar o estado e forçar o rerun necessário).
        df_check_dlg = encomendas_listar(cancelado=False)
        if _checar_confeccao_com_senha(
            df_check_dlg, d_confeccao_dlg, escopo_key="dlg_nova",
            dados_para_salvar=dados_atuais_dlg,
        ):
            _criar_encomenda_dlg(dados_atuais_dlg)
        return

    # ── Se há um conflito pendente desta tela, mostra o campo de senha ADM.
    #    Só cria de fato (usando a foto tirada no clique original) quando a
    #    senha correta é confirmada. ──────────────
    dados_pend_dlg = _render_confirmacao_senha_confeccao("dlg_nova")
    if dados_pend_dlg is not None:
        _criar_encomenda_dlg(dados_pend_dlg)
        return

    if col_cancel.button("❌ Cancelar", use_container_width=True, key="dlg_btn_cancel"):
        st.rerun()


# ── Formulário fixo de Nova Encomenda (sem popup — usado no bloco ENCOMENDAS) ──
def secao_nova_encomenda_inline():
    """
    Mesma lógica do dialog_nova_encomenda, mas renderizada direto na página
    (sem st.dialog). Isso evita que o formulário "suma" no celular quando o
    usuário troca de aba/app e o Streamlit reconecta a sessão.
    """
    resultado = st.session_state.get("_ne_resultado")
    if resultado:
        st.success(f"✅ Encomenda **{resultado['peca']}** criada para **{resultado['cliente']}**!")
        if resultado.get("pdf_bytes"):
            col_pdf, col_gov = st.columns(2)
            col_pdf.download_button(
                "📥 BAIXAR CONTRATO PDF", data=resultado["pdf_bytes"],
                file_name=f"Contrato_{resultado['cliente'].replace(' ','_')}.pdf",
                mime="application/pdf", use_container_width=True, key="ne_dl_pdf_resultado",
            )
            col_gov.link_button("✍️ ASSINAR VIA GOV.BR",
                url="https://assinador.iti.br/assinatura/index.xhtml",
                use_container_width=True)
        else:
            st.info("💡 Preencha CPF e RG (seção Dados para Contrato) para gerar o contrato automaticamente.")
        if st.button("➕ Cadastrar Outra Encomenda", use_container_width=True, type="primary", key="ne_btn_outra"):
            for k in list(st.session_state.keys()):
                if k.startswith("ne_"):
                    del st.session_state[k]
            del st.session_state["_ne_resultado"]
            st.rerun()
        return

    d_base = hoje_brasilia()

    df_clis_dlg = clientes_listar()
    clis_dlg = df_clis_dlg["nome"].tolist() if not df_clis_dlg.empty else []

    st.markdown("##### 👤 Cliente")
    modo_cli = st.radio(
        "Cliente", ["Selecionar existente", "Cadastrar nova"],
        horizontal=True, key="ne_modo_cli", label_visibility="collapsed",
        index=0 if clis_dlg else 1,
    )

    cli_tel_dlg = ""
    if modo_cli == "Selecionar existente" and clis_dlg:
        cli_sel_dlg = st.selectbox("Cliente *", clis_dlg, key="ne_cli_sel")
    else:
        col_cn1, col_cn2 = st.columns(2)
        cli_sel_dlg = col_cn1.text_input("Nome da nova cliente *", key="ne_cli_novo")
        cli_tel_dlg = col_cn2.text_input("Telefone / WhatsApp", key="ne_cli_tel")

    st.markdown("##### 🧵 Peça / Serviço")
    peca_dlg = st.text_input("Peça / Serviço *", placeholder="Ex: Vestido de festa…", key="ne_peca")
    descricao_dlg = st.text_area("Descrição detalhada", key="ne_descricao", height=70)

    st.markdown("##### 💰 Valores")
    col_v1, col_v2, col_v3 = st.columns(3)
    v_total_dlg = col_v1.number_input("Valor Total (R$)", min_value=0.0, step=50.0, format="%.2f", key="ne_valor")
    v_sinal_dlg = col_v2.number_input("Sinal / Entrada (R$)", min_value=0.0, step=50.0, format="%.2f", key="ne_sinal")
    forma_pag_dlg = col_v3.selectbox("Forma de Pagamento",
        ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"], key="ne_forma_pag")

    st.markdown("##### 📅 Datas")
    st.caption("A primeira etapa do pedido é a Data da Confecção — não há mais um campo separado de 'Data Medidas'.")

    d_confeccao_dlg = st.date_input(
        "🪡 Data da Confecção", value=d_base + timedelta(days=7),
        key="ne_confeccao", format="DD/MM/YYYY"
    )
    _render_ocupacao_confeccao_navegavel(encomendas_listar(cancelado=False), key_prefix="ne", data_referencia=d_confeccao_dlg)

    d_prova_dlg = st.date_input(
        "👗 Data da Prova", value=d_base + timedelta(days=25), key="ne_prova", format="DD/MM/YYYY"
    )
    st.caption(
        f"ℹ️ Não há limite de provas por dia. Mas se um dia passar de "
        f"{LIMITE_PROVAS_PARA_CONFECCAO} provas, ele fica bloqueado para receber Confecção (veja 🟡 acima)."
    )

    tem_prova2_dlg = st.checkbox("Precisa de uma segunda prova?", key="ne_tem_prova2")
    d_prova2_dlg = None
    if tem_prova2_dlg:
        d_prova2_dlg = st.date_input(
            "👗 Data da 2ª Prova", value=d_prova_dlg + timedelta(days=7),
            key="ne_prova2", format="DD/MM/YYYY",
        )

    precisa_tecido_dlg = st.checkbox("Precisa comprar tecido?", key="ne_tecido")
    d_tecido_dlg = d_base + timedelta(days=3)
    if precisa_tecido_dlg:
        d_tecido_dlg = st.date_input(
            "🛍️ Data Compra do Tecido", value=d_tecido_dlg, key="ne_data_tecido", format="DD/MM/YYYY"
        )

    d_entrega_dlg = st.date_input(
        "🎁 Data de Entrega", value=d_base + timedelta(days=30), key="ne_entrega", format="DD/MM/YYYY"
    )

    st.markdown("##### 📄 Dados para Contrato")
    st.caption("Preencha CPF e RG para o contrato ser gerado automaticamente assim que a encomenda for criada.")
    col_c1, col_c2 = st.columns(2)
    cpf_dlg = col_c1.text_input("CPF da cliente", placeholder="000.000.000-00", key="ne_cpf")
    rg_dlg  = col_c2.text_input("RG da cliente",  placeholder="00.000.000-0", key="ne_rg")
    obs_dlg = st.text_area("Observações", key="ne_obs", height=68)

    def _criar_encomenda_ne(dados_form: dict | None = None):
        """Grava a encomenda + tarefas + PDF e reinicia a tela mostrando o
        resultado. `dados_form` é uma FOTO dos campos, tirada no clique em
        "Criar Encomenda" — usada tanto no fluxo normal quanto após a senha
        ADM, para garantir que o que é salvo é exatamente o que o usuário
        preencheu naquele clique."""
        if dados_form is None:
            dados_form = dict(
                nome_final=(cli_sel_dlg.strip() if isinstance(cli_sel_dlg, str) else cli_sel_dlg),
                modo_cli=modo_cli, cli_tel_dlg=cli_tel_dlg,
                peca_dlg=peca_dlg, descricao_dlg=descricao_dlg,
                v_total_dlg=v_total_dlg, v_sinal_dlg=v_sinal_dlg, forma_pag_dlg=forma_pag_dlg,
                d_confeccao_dlg=d_confeccao_dlg, d_prova_dlg=d_prova_dlg,
                tem_prova2_dlg=tem_prova2_dlg, d_prova2_dlg=d_prova2_dlg,
                precisa_tecido_dlg=precisa_tecido_dlg, d_tecido_dlg=d_tecido_dlg,
                d_entrega_dlg=d_entrega_dlg, cpf_dlg=cpf_dlg, rg_dlg=rg_dlg, obs_dlg=obs_dlg,
            )

        nome_final = dados_form["nome_final"]
        f_modo_cli = dados_form["modo_cli"]
        f_peca = dados_form["peca_dlg"]; f_desc = dados_form["descricao_dlg"]
        f_vtotal = dados_form["v_total_dlg"]; f_vsinal = dados_form["v_sinal_dlg"]
        f_fpag = dados_form["forma_pag_dlg"]
        f_dconf = dados_form["d_confeccao_dlg"]
        f_dprova = dados_form["d_prova_dlg"]; f_temprova2 = dados_form["tem_prova2_dlg"]
        f_dprova2 = dados_form["d_prova2_dlg"]; f_precisatecido = dados_form["precisa_tecido_dlg"]
        f_dtecido = dados_form["d_tecido_dlg"]; f_dentrega = dados_form["d_entrega_dlg"]
        f_cpf = dados_form["cpf_dlg"]; f_rg = dados_form["rg_dlg"]; f_obs = dados_form["obs_dlg"]

        if f_modo_cli != "Selecionar existente":
            clientes_inserir({
                "nome": nome_final, "telefone": dados_form["cli_tel_dlg"].strip(),
                "criado_em": agora_br().isoformat(),
            })

        e_id = encomendas_inserir({
            "cliente": nome_final, "peca": f_peca.strip(),
            "descricao": f_desc.strip(), "valor_total": f_vtotal, "sinal": f_vsinal,
            "valor_recebido": f_vsinal,
            "etapa": 1, "precisa_tecido": 1 if f_precisatecido else 0,
            "data_tecido":    f_dtecido.isoformat(),
            "data_confeccao": f_dconf.isoformat(),
            "data_prova":     f_dprova.isoformat(),
            "tem_prova2":     1 if f_temprova2 else 0,
            "data_prova2":    f_dprova2.isoformat() if f_dprova2 else "",
            "data_entrega":   f_dentrega.isoformat(),
            "cpf_cliente": f_cpf.strip(), "rg_cliente": f_rg.strip(),
            "forma_pagamento": f_fpag, "observacoes": f_obs.strip(),
            "cancelado": 0,
            "criado_em": agora_br().isoformat(),
        })

        desc_dlg = f"{f_peca.strip()} ({nome_final})"
        tarefas_auto_dlg = []
        if f_precisatecido:
            tarefas_auto_dlg.append((f"🛍️ Tecido: {desc_dlg}", "Compras", 1.0, f_dtecido.isoformat()))
        tarefas_auto_dlg.append((f"🪡 Confecção: {desc_dlg}", "Costura", 3.0, f_dconf.isoformat()))
        tarefas_auto_dlg.append((f"👗 Prova: {desc_dlg}",     "Costura", 1.0, f_dprova.isoformat()))
        if f_temprova2 and f_dprova2:
            tarefas_auto_dlg.append((f"👗 2ª Prova: {desc_dlg}", "Costura", 1.0, f_dprova2.isoformat()))
        tarefas_auto_dlg.append((f"🎁 Entrega: {desc_dlg}",   "Costura", 0.5, f_dentrega.isoformat()))

        for tarefa_a, cat_a, hrs_a, dt_a in tarefas_auto_dlg:
            cronograma_inserir({
                "tarefa": tarefa_a, "categoria": cat_a, "horas": hrs_a,
                "data": dt_a, "frequencia": "Pontual", "concluida": 0,
                "encomenda_id": e_id, "tipo_agenda": "Trabalho",
            })

        pdf_bytes_dlg = None
        if f_cpf.strip() and f_rg.strip():
            enc_dict_pdf = {
                "cliente": nome_final, "peca": f_peca.strip(),
                "descricao": f_desc.strip(), "valor_total": f_vtotal,
                "sinal": f_vsinal, "forma_pagamento": f_fpag,
                "data_tecido": f_dtecido.isoformat() if f_precisatecido else "",
                "data_confeccao": f_dconf.isoformat(),
                "data_prova": f_dprova.isoformat(),
                "data_prova2": f_dprova2.isoformat() if f_dprova2 else "",
                "data_entrega": f_dentrega.isoformat(),
                "precisa_tecido": 1 if f_precisatecido else 0,
                "observacoes": f_obs.strip(),
            }
            pdf_bytes_dlg = gerar_pdf_contrato(enc_dict_pdf, f_cpf.strip(), f_rg.strip())

        st.session_state["_ne_resultado"] = {
            "cliente": nome_final, "peca": f_peca.strip(), "pdf_bytes": pdf_bytes_dlg,
        }
        st.rerun()

    st.markdown("")
    if st.button("✅ Criar Encomenda", use_container_width=True, type="primary", key="ne_btn_ok"):
        nome_final = cli_sel_dlg.strip() if isinstance(cli_sel_dlg, str) else cli_sel_dlg

        if not nome_final:
            st.error("Informe o nome da cliente.")
            return
        if not peca_dlg.strip():
            st.error("Informe a peça / serviço.")
            return

        dados_atuais_ne = dict(
            nome_final=nome_final, modo_cli=modo_cli, cli_tel_dlg=cli_tel_dlg,
            peca_dlg=peca_dlg, descricao_dlg=descricao_dlg,
            v_total_dlg=v_total_dlg, v_sinal_dlg=v_sinal_dlg, forma_pag_dlg=forma_pag_dlg,
            d_confeccao_dlg=d_confeccao_dlg, d_prova_dlg=d_prova_dlg,
            tem_prova2_dlg=tem_prova2_dlg, d_prova2_dlg=d_prova2_dlg,
            precisa_tecido_dlg=precisa_tecido_dlg, d_tecido_dlg=d_tecido_dlg,
            d_entrega_dlg=d_entrega_dlg, cpf_dlg=cpf_dlg, rg_dlg=rg_dlg, obs_dlg=obs_dlg,
        )

        # ── Validação de agenda (exclusividade da Data da Confecção) ──
        df_check_ne = encomendas_listar(cancelado=False)
        if _checar_confeccao_com_senha(
            df_check_ne, d_confeccao_dlg, escopo_key="ne_nova",
            dados_para_salvar=dados_atuais_ne,
        ):
            _criar_encomenda_ne(dados_atuais_ne)
        return

    dados_pend_ne = _render_confirmacao_senha_confeccao("ne_nova")
    if dados_pend_ne is not None:
        _criar_encomenda_ne(dados_pend_ne)


# ── Sincronização de lembretes (cronograma) com as datas do pedido ────────────
def _sincronizar_lembretes_pedido(
    enc_id: str, cliente: str, peca: str,
    precisa_tecido: bool, d_tecido: date,
    d_confeccao: date, d_prova: date, tem_prova2: bool, d_prova2,
    d_entrega: date,
):
    """
    Após editar um pedido, sincroniza as tarefas do cronograma vinculadas a
    essa encomenda para refletir as novas datas no Calendário e na aba Trabalho.
    Somente tarefas ainda PENDENTES são sincronizadas; tarefas já concluídas
    são preservadas como histórico.
    """
    desc = f"{peca} ({cliente})"

    df_crono = cronograma_listar(tipo_agenda="Trabalho", concluida=False)
    if df_crono is None or df_crono.empty or "encomenda_id" not in df_crono.columns:
        df_crono = pd.DataFrame(columns=["rowid", "tarefa", "encomenda_id"])
    else:
        df_crono = df_crono[df_crono["encomenda_id"].astype(str) == str(enc_id)]

    especificacoes = [
        ("🛍️ Tecido:",     "Compras", 1.0, d_tecido, bool(precisa_tecido)),
        ("🪡 Confecção:",   "Costura", 3.0, d_confeccao, True),
        ("👗 2ª Prova:",    "Costura", 1.0, d_prova2, bool(tem_prova2) and d_prova2 is not None),
        ("👗 Prova:",       "Costura", 1.0, d_prova, True),
        ("🎁 Entrega:",     "Costura", 0.5, d_entrega, True),
    ]

    for prefixo, categoria, horas, data_val, deve_existir in especificacoes:
        linha_existente = None
        if not df_crono.empty:
            match = df_crono[df_crono["tarefa"].astype(str).str.startswith(prefixo)]
            if not match.empty:
                linha_existente = match.iloc[0]

        if not deve_existir:
            if linha_existente is not None:
                cronograma_deletar(str(linha_existente["rowid"]))
            continue

        if data_val is None:
            continue

        novo_texto = f"{prefixo} {desc}"
        if linha_existente is not None:
            cronograma_atualizar(str(linha_existente["rowid"]), {
                "tarefa": novo_texto,
                "data": data_val.isoformat(),
            })
        else:
            cronograma_inserir({
                "tarefa": novo_texto, "categoria": categoria, "horas": horas,
                "data": data_val.isoformat(), "frequencia": "Pontual", "concluida": 0,
                "encomenda_id": enc_id, "tipo_agenda": "Trabalho",
            })


def _calcular_etapa_maxima_por_datas(
    hoje: date, d_confeccao: date, d_prova: date, d_entrega: date,
) -> int:
    """
    Calcula, comparando com a data de hoje, até qual etapa da régua as datas
    do pedido já justificam. Régua enxuta: 1 Confecção, 2 Prova, 3 Entrega.
    Nunca retorna 4 (Concluído) — essa etapa continua sendo sempre uma
    confirmação manual.
    """
    etapa = 1
    if hoje >= d_confeccao:
        etapa = 2
    if hoje >= d_prova:
        etapa = 3
    return etapa


def _reverter_lembretes_por_etapa(enc_id: str, etapa_atual: int):
    """
    Mantém o cronograma coerente com a etapa atual do pedido: se a régua
    "voltou", marca de volta como PENDENTE qualquer tarefa cuja conclusão
    representaria uma etapa mais avançada do que a etapa_atual.
    """
    df_todas = cronograma_listar(tipo_agenda="Trabalho")
    if df_todas is None or df_todas.empty or "encomenda_id" not in df_todas.columns:
        return
    df_todas = df_todas[df_todas["encomenda_id"].astype(str) == str(enc_id)]
    if df_todas.empty:
        return

    mapa_etapas = [
        ("🪡 Confecção:", 1),
        ("👗 Prova:",     2),
        ("🎁 Entrega:",   3),
    ]

    for prefixo, etapa_gerada in mapa_etapas:
        match = df_todas[df_todas["tarefa"].astype(str).str.startswith(prefixo)]
        if match.empty:
            continue
        linha = match.iloc[0]
        deve_estar_concluida = etapa_gerada <= etapa_atual
        concluida_atual = bool(int(linha.get("concluida", 0) or 0))
        if concluida_atual != deve_estar_concluida:
            cronograma_atualizar(str(linha["rowid"]), {"concluida": 1 if deve_estar_concluida else 0})


# ── Corpo completo de um pedido: régua, valores, contrato, edição ─────────────
def _conteudo_pedido(enc: dict, cancelado: bool):
    """
    Renderiza o conteúdo COMPLETO de um pedido: régua de etapas, valores,
    datas, seção de contrato (CPF/RG + baixar PDF + assinar via GOV.BR),
    medidas da cliente e formulário de edição (incluindo o nome da cliente,
    editável). É o mesmo "miolo" usado tanto dentro de um popup
    (Encomendas/Agenda) quanto dentro do painel de detalhe do BLOCO
    CONTRATOS/GERENCIAR PEDIDOS — a única diferença é o container que o
    envolve por fora.
    """
    enc_atualizado = encomendas_buscar(str(enc["rowid"]))
    if enc_atualizado:
        enc = enc_atualizado
        cancelado = bool(int(enc.get("cancelado", 0) or 0))

    etapa_num  = int(enc.get("etapa", 1))
    restante_enc = float(enc.get("valor_total", 0) or 0) - float(enc.get("valor_recebido", 0) or 0)

    st.markdown(f"### 👤 {enc.get('cliente','—')} &nbsp;·&nbsp; 🧵 {enc.get('peca','—')}")
    st.caption(f"📝 Pedido registrado em {formatar_data_hora_br(enc.get('criado_em'))}")

    if not cancelado:
        steps_html = '<div class="step-bar">'
        for i in range(1, 5):
            ic, nm = ETAPAS[i]
            cls = "done" if i < etapa_num else ("active" if i == etapa_num else "")
            steps_html += f'<div class="step-item {cls}"><div class="step-dot">{ic}</div><div class="step-lbl">{nm}</div></div>'
        steps_html += "</div>"
        st.markdown(steps_html, unsafe_allow_html=True)
        st.markdown("")

    col_inf1, col_inf2, col_inf3, col_inf4 = st.columns(4)
    col_inf1.metric("Valor Total",    brl(float(enc.get("valor_total",0) or 0)))
    col_inf2.metric("Recebido",       brl(float(enc.get("valor_recebido",0) or 0)))
    col_inf3.metric("Saldo Restante", brl(max(restante_enc, 0)))
    col_inf4.metric("Entrega",        formatar_data_br(enc.get("data_entrega","")))

    prova2_txt = ""
    if str(enc.get("data_prova2") or "").strip():
        prova2_txt = f" &nbsp;|&nbsp; 👗 2ª Prova: **{formatar_data_br(enc.get('data_prova2'))}**"
    tecido_txt = ""
    if enc.get("precisa_tecido") and str(enc.get("data_tecido") or "").strip():
        tecido_txt = f" &nbsp;|&nbsp; 🛍️ Tecido: **{formatar_data_br(enc.get('data_tecido'))}**"
    st.caption(
        f"🪡 Confecção: **{formatar_data_br(enc.get('data_confeccao',''))}** "
        f"&nbsp;|&nbsp; 👗 Prova: **{formatar_data_br(enc.get('data_prova',''))}**"
        f"{prova2_txt}{tecido_txt}"
    )

    st.markdown("##### 📄 Contrato")
    col_cpf, col_rg = st.columns(2)
    cpf_s = str(enc.get("cpf_cliente") or "")
    rg_s  = str(enc.get("rg_cliente") or "")
    v_cpf = col_cpf.text_input("CPF", value=cpf_s, key=f"cpf_{enc['rowid']}")
    v_rg  = col_rg.text_input("RG",   value=rg_s,  key=f"rg_{enc['rowid']}")

    if v_cpf != cpf_s or v_rg != rg_s:
        encomendas_atualizar(str(enc["rowid"]), {"cpf_cliente": v_cpf, "rg_cliente": v_rg})

    if v_cpf.strip() and v_rg.strip():
        pdf_bytes = gerar_pdf_contrato(dict(enc), v_cpf.strip(), v_rg.strip())
        col_dl1, col_dl2 = st.columns(2)
        col_dl1.download_button(
            "📥 BAIXAR CONTRATO PDF", data=pdf_bytes,
            file_name=f"Contrato_{enc['cliente'].replace(' ','_')}.pdf",
            mime="application/pdf", key=f"dl_{enc['rowid']}",
            use_container_width=True,
        )
        col_dl2.link_button("✍️ ASSINAR VIA GOV.BR",
            url="https://assinador.iti.br/assinatura/index.xhtml",
            use_container_width=True)
    else:
        st.info("💡 Preencha CPF e RG para habilitar o contrato.")

    st.markdown("##### ✏️ Editar Pedido")

    with st.expander("📏 Ver / Editar Medidas desta Cliente"):
        df_cli_medidas = clientes_listar()
        cli_row_medidas = None
        if not df_cli_medidas.empty:
            match_cli = df_cli_medidas[df_cli_medidas["nome"] == enc.get("cliente")]
            if not match_cli.empty:
                cli_row_medidas = match_cli.iloc[0]

        if cli_row_medidas is None:
            st.info("Cliente não encontrada no cadastro (pode ter sido removida).")
        else:
            with st.form(f"form_medidas_pedido_{enc['rowid']}"):
                colm1, colm2, colm3 = st.columns(3)
                novas_medidas = {}
                for i, (label, col_db) in enumerate(DIC_MEDIDAS.items()):
                    raw = cli_row_medidas.get(col_db, 0)
                    val_f = float(raw) if raw not in [None, "", "nan"] and pd.notna(raw) else 0.0
                    alvo = colm1 if i < 5 else (colm2 if i < 10 else colm3)
                    novas_medidas[col_db] = alvo.number_input(
                        f"{label} (cm)", value=val_f, format="%.1f", step=0.5,
                        key=f"med_{enc['rowid']}_{col_db}",
                    )
                obs_medidas = st.text_area(
                    "Observações de modelagem",
                    value=str(cli_row_medidas.get("outro") or ""),
                    key=f"med_obs_{enc['rowid']}",
                )
                if st.form_submit_button("💾 Salvar Medidas", use_container_width=True):
                    clientes_atualizar(str(cli_row_medidas["rowid"]), {**novas_medidas, "outro": obs_medidas})
                    st.success("✅ Medidas atualizadas!")
                    st.rerun()

    tem_prova2_atual = bool(int(enc.get("tem_prova2", 0) or 0)) or bool(str(enc.get("data_prova2") or "").strip())
    ed_tem_prova2 = st.checkbox("Precisa de uma segunda prova?", value=tem_prova2_atual, key=f"tp2_{enc['rowid']}")

    # ── Mini-calendário de ocupação da Data da Confecção (informativo,
    #    com navegação de mês — fica fora do st.form abaixo de propósito,
    #    já que dentro de um st.form não é permitido usar st.button comum) ──
    mes_ref_conf = converter_para_data(enc.get("data_confeccao")) or hoje_brasilia()
    df_check_edicao = encomendas_listar(cancelado=False)
    _render_ocupacao_confeccao_navegavel(
        df_check_edicao, key_prefix=f"cp_{enc['rowid']}",
        data_referencia=mes_ref_conf, excluir_id=str(enc["rowid"]),
    )

    with st.form(f"edit_{enc['rowid']}"):
        ed_cliente = st.text_input("Cliente", value=str(enc.get("cliente") or ""), key=f"cliente_{enc['rowid']}")
        ed_peca = st.text_input("Peça", value=str(enc.get("peca") or ""))
        ed_desc = st.text_area("Descrição", value=str(enc.get("descricao") or ""), height=60)
        col_f1e, col_f2e = st.columns(2)
        fpag_opts = ["PIX","Dinheiro","Cartão de Crédito","Cartão de Débito","A combinar"]
        fpag_cur  = enc.get("forma_pagamento","A combinar")
        fpag_idx  = fpag_opts.index(fpag_cur) if fpag_cur in fpag_opts else 4
        ed_fpag   = col_f1e.selectbox("Forma de Pagamento", fpag_opts, index=fpag_idx)
        ed_obs    = col_f2e.text_area("Observações", value=str(enc.get("observacoes") or ""), height=60)

        st.markdown("📅 Datas")
        d2, d3 = st.columns(2)
        ed_conf = d2.date_input("🪡 Data da Confecção", value=converter_para_data(enc.get("data_confeccao")),
                                 key=f"dconf_{enc['rowid']}", format="DD/MM/YYYY")
        ed_pro = d3.date_input("👗 Data da Prova", value=converter_para_data(enc.get("data_prova")),
                                key=f"dp_{enc['rowid']}", format="DD/MM/YYYY")

        d4, d5 = st.columns(2)
        ed_pro2 = None
        if ed_tem_prova2:
            ed_pro2 = d4.date_input(
                "👗 Data da 2ª Prova",
                value=converter_para_data(enc.get("data_prova2")) if enc.get("data_prova2") else ed_pro + timedelta(days=7),
                key=f"dp2_{enc['rowid']}", format="DD/MM/YYYY",
            )

        d6, d7 = st.columns(2)
        ed_tec  = d6.date_input("🛍️ Data Compra do Tecido", value=converter_para_data(enc.get("data_tecido")),
                                 key=f"dt_{enc['rowid']}", format="DD/MM/YYYY")
        ed_ent  = d7.date_input("🎁 Data de Entrega", value=converter_para_data(enc.get("data_entrega")),
                                 key=f"de_{enc['rowid']}", format="DD/MM/YYYY")

        col_b1, col_b2, col_b3 = st.columns(3)
        clicou_salvar = col_b1.form_submit_button("💾 Salvar", use_container_width=True)
        clicou_concluir = False
        clicou_cancelar_pedido = False
        if not cancelado:
            clicou_concluir = col_b2.form_submit_button("✅ Marcar Concluído", use_container_width=True)
            clicou_cancelar_pedido = col_b3.form_submit_button("❌ Cancelar Pedido", use_container_width=True)

    # ── Ações do formulário — processadas FORA do st.form. Isso é necessário
    #    para o fluxo de senha ADM em caso de conflito de Data da Confecção:
    #    os botões de confirmar/cancelar senha não podem viver dentro de um
    #    st.form (só o botão de submit de um form dispara o processamento). ──
    def _executar_salvamento_pedido(dados_form: dict | None = None):
        """
        `dados_form` é uma FOTO dos valores do formulário (ver abaixo). Se
        vier None, usa os valores ATUAIS dos widgets (fluxo normal, sem
        conflito de agenda). Se vier preenchido, usa exatamente esses
        valores — é o caso do fluxo de senha ADM, onde os widgets podem já
        não refletir mais o que o usuário preencheu no momento do clique
        original em "Salvar".
        """
        if dados_form is None:
            dados_form = dict(
                ed_cliente=ed_cliente, ed_peca=ed_peca, ed_desc=ed_desc,
                ed_fpag=ed_fpag, ed_obs=ed_obs,
                ed_tec=ed_tec, ed_conf=ed_conf,
                ed_pro=ed_pro, ed_tem_prova2=ed_tem_prova2, ed_pro2=ed_pro2,
                ed_ent=ed_ent,
            )

        f_tec, f_conf = dados_form["ed_tec"], dados_form["ed_conf"]
        f_pro, f_pro2, f_ent = dados_form["ed_pro"], dados_form["ed_pro2"], dados_form["ed_ent"]
        f_tem_prova2 = dados_form["ed_tem_prova2"]

        precisa_tecido_enc = bool(int(enc.get("precisa_tecido", 0) or 0))
        etapa_atual = int(enc.get("etapa", 1))
        cliente_final = dados_form["ed_cliente"].strip()

        dados_salvar = {
            "cliente": cliente_final,
            "peca": dados_form["ed_peca"], "descricao": dados_form["ed_desc"],
            "forma_pagamento": dados_form["ed_fpag"], "observacoes": dados_form["ed_obs"],
            "data_tecido": f_tec.isoformat(),
            "data_confeccao": f_conf.isoformat(),
            "data_prova": f_pro.isoformat(),
            "tem_prova2": 1 if f_tem_prova2 else 0,
            "data_prova2": f_pro2.isoformat() if f_pro2 else "",
            "data_entrega": f_ent.isoformat(),
        }

        etapa_ajustada = False
        if not cancelado:
            etapa_max_datas = _calcular_etapa_maxima_por_datas(
                hoje=hoje_brasilia(), d_confeccao=f_conf, d_prova=f_pro, d_entrega=f_ent,
            )
            if etapa_max_datas < etapa_atual:
                dados_salvar["etapa"] = etapa_max_datas
                etapa_atual = etapa_max_datas
                etapa_ajustada = True

        encomendas_atualizar(str(enc["rowid"]), dados_salvar)

        if etapa_ajustada:
            _reverter_lembretes_por_etapa(enc_id=str(enc["rowid"]), etapa_atual=etapa_atual)

        _sincronizar_lembretes_pedido(
            enc_id=str(enc["rowid"]), cliente=cliente_final, peca=dados_form["ed_peca"],
            precisa_tecido=precisa_tecido_enc, d_tecido=f_tec,
            d_confeccao=f_conf, d_prova=f_pro,
            tem_prova2=f_tem_prova2, d_prova2=f_pro2,
            d_entrega=f_ent,
        )

        if etapa_ajustada:
            st.success(
                f"✅ Pedido e lembretes atualizados! A régua foi ajustada automaticamente "
                f"para **{ETAPAS[etapa_atual][1]}**, já que ainda há etapas com data futura."
            )
        else:
            st.success("✅ Pedido e lembretes atualizados!")
        st.rerun()

    if clicou_salvar:
        if not ed_cliente.strip():
            st.error("Informe o nome da cliente.")
        else:
            # ── Foto dos dados exatamente como estão neste clique — é o que
            #    será salvo, seja agora (sem conflito) ou depois (com senha). ──
            dados_atuais = dict(
                ed_cliente=ed_cliente, ed_peca=ed_peca, ed_desc=ed_desc,
                ed_fpag=ed_fpag, ed_obs=ed_obs,
                ed_tec=ed_tec, ed_conf=ed_conf,
                ed_pro=ed_pro, ed_tem_prova2=ed_tem_prova2, ed_pro2=ed_pro2,
                ed_ent=ed_ent,
            )
            # ── Validação de agenda (exclusividade da Data da Confecção) ──
            df_check_save = encomendas_listar(cancelado=False)
            if _checar_confeccao_com_senha(
                df_check_save, ed_conf, escopo_key=f"pedido_{enc['rowid']}",
                excluir_id=str(enc["rowid"]), dados_para_salvar=dados_atuais,
            ):
                _executar_salvamento_pedido(dados_atuais)

    # ── Se há um conflito pendente para este pedido, mostra o campo de
    #    senha ADM. Só salva de fato (usando a foto tirada acima) quando a
    #    senha correta é confirmada. ──
    dados_pendentes_pedido = _render_confirmacao_senha_confeccao(f"pedido_{enc['rowid']}")
    if dados_pendentes_pedido is not None:
        _executar_salvamento_pedido(dados_pendentes_pedido)

    if clicou_concluir:
        encomendas_atualizar(str(enc["rowid"]), {"etapa": 4})
        st.rerun()
    if clicou_cancelar_pedido:
        encomendas_cancelar(str(enc["rowid"]))
        st.rerun()


def _abrir_popup_pedido(enc: dict, cancelado: bool):
    titulo = f"📦 {enc['cliente']} — {enc['peca']}"
    @st.dialog(titulo, width="large")
    def _p():
        _conteudo_pedido(enc, cancelado)
    _p()


def _dialog_editar_dia(dt_str: str, tasks_dia: pd.DataFrame):
    """
    Popup usado a partir do Calendário: mostra o(s) pedido(s) vinculados
    às tarefas daquele dia e permite editar diretamente, sem opção de
    criar nova encomenda.
    """
    encomenda_ids = []
    if tasks_dia is not None and not tasks_dia.empty and "encomenda_id" in tasks_dia.columns:
        encomenda_ids = [e for e in tasks_dia["encomenda_id"].dropna().unique().tolist() if str(e).strip()]

    @st.dialog(f"✏️ Editar pedidos — {formatar_data_br(dt_str)}", width="large")
    def _d():
        if not encomenda_ids:
            st.info("Nenhum pedido vinculado a esta data.")
            return

        encomendas_dia = []
        for eid in encomenda_ids:
            enc_d = encomendas_buscar(str(eid))
            if enc_d:
                encomendas_dia.append(enc_d)

        if not encomendas_dia:
            st.info("Nenhum pedido vinculado a esta data.")
            return

        if len(encomendas_dia) == 1:
            enc_d = encomendas_dia[0]
            cancelado_d = bool(int(enc_d.get("cancelado", 0) or 0))
            _conteudo_pedido(enc_d, cancelado_d)
        else:
            labels = [f"{e['cliente']} — {e['peca']}" for e in encomendas_dia]
            escolha = st.radio("Vários pedidos nesta data. Selecione qual editar:",
                                labels, key=f"sel_dia_{dt_str}")
            idx_sel = labels.index(escolha)
            enc_d = encomendas_dia[idx_sel]
            st.divider()
            cancelado_d = bool(int(enc_d.get("cancelado", 0) or 0))
            _conteudo_pedido(enc_d, cancelado_d)
    _d()


def _mapa_prefixo_campo_data():
    """
    Relaciona o prefixo do texto da tarefa (gerado automaticamente ao criar
    a encomenda) com o campo de data correspondente na encomenda.
    """
    return {
        "🛍️ Tecido:":    "data_tecido",
        "🪡 Confecção:":  "data_confeccao",
        "👗 2ª Prova:":   "data_prova2",
        "👗 Prova:":      "data_prova",
        "🎁 Entrega:":    "data_entrega",
    }


@st.dialog("📅 Editar Data da Tarefa", width="small")
def _dialog_editar_data_tarefa(row):
    """
    Popup enxuto para alterar SOMENTE a data de uma tarefa/etapa pontual,
    sem abrir o formulário completo do pedido.
    """
    st.markdown(f"**{row['tarefa']}**")
    if row.get("nome_cliente"):
        st.caption(f"👤 {row['nome_cliente']}")
    st.caption("Isso altera apenas a data desta etapa — o restante do pedido permanece igual.")

    nova_data = st.date_input(
        "Nova data",
        value=converter_para_data(row["data"]),
        key=f"nova_data_{row['rowid']}",
        format="DD/MM/YYYY",
    )

    def _salvar_data_tarefa(data_para_salvar: date | None = None):
        if data_para_salvar is None:
            data_para_salvar = nova_data

        cronograma_atualizar(str(row["rowid"]), {"data": data_para_salvar.isoformat()})

        enc_id_check = row.get("encomenda_id")
        tarefa_txt_check = str(row["tarefa"])
        if enc_id_check and str(enc_id_check).strip():
            for prefixo, campo_data in _mapa_prefixo_campo_data().items():
                if tarefa_txt_check.startswith(prefixo):
                    encomendas_atualizar(str(enc_id_check), {campo_data: data_para_salvar.isoformat()})
                    break

        st.success("✅ Data atualizada!")
        st.rerun()

    col_ok, col_cancel = st.columns(2)
    if col_ok.button("💾 Salvar", use_container_width=True, type="primary", key=f"salvar_data_{row['rowid']}"):
        # Se a tarefa for de Confecção, aplica a regra de exclusividade do dia
        # (com senha ADM em caso de conflito). Provas não têm limite, então
        # não há validação para elas aqui.
        tarefa_txt_check = str(row["tarefa"])
        enc_id_check = row.get("encomenda_id")

        if tarefa_txt_check.startswith("🪡 Confecção:"):
            df_check_tarefa = encomendas_listar(cancelado=False)
            if _checar_confeccao_com_senha(
                df_check_tarefa, nova_data,
                escopo_key=f"tarefa_{row['rowid']}",
                excluir_id=str(enc_id_check) if enc_id_check else None,
                dados_para_salvar={"data": nova_data},
            ):
                _salvar_data_tarefa(nova_data)
        else:
            _salvar_data_tarefa(nova_data)

    # ── Se há um conflito pendente desta tarefa, mostra o campo de senha
    #    ADM. Só salva de fato (usando a data tirada em foto) quando a
    #    senha correta é confirmada. ────────────────────────────────────
    dados_pend_tarefa = _render_confirmacao_senha_confeccao(f"tarefa_{row['rowid']}")
    if dados_pend_tarefa is not None:
        _salvar_data_tarefa(dados_pend_tarefa.get("data", nova_data))

    if col_cancel.button("❌ Cancelar", use_container_width=True, key=f"cancelar_data_{row['rowid']}"):
        st.rerun()


def _card_pedido(enc: dict, idx: int):
    etapa_num  = int(enc.get("etapa", 1))
    etapa_ic, etapa_nm = ETAPAS.get(etapa_num, ("📦", "–"))
    cancelado  = bool(int(enc.get("cancelado", 0) or 0))
    restante_enc = float(enc.get("valor_total", 0) or 0) - float(enc.get("valor_recebido", 0) or 0)
    pct = 0 if cancelado else round(min(etapa_num / 4, 1.0) * 100)
    badge_cls = "badge-red" if cancelado else "badge-gold"
    badge_txt = "❌ Cancelado" if cancelado else f"{etapa_ic} {etapa_nm}"

    tem_contrato = bool(
        str(enc.get("cpf_cliente") or "").strip()
        and str(enc.get("rg_cliente") or "").strip()
    )
    contrato_badge = (
        '&nbsp;<span class="badge badge-blue">📄 Contrato pronto</span>' if tem_contrato
        else '&nbsp;<span class="badge badge-navy">⏳ Falta CPF/RG</span>'
    )

    if st.button(f"📦 {enc['cliente']} — {enc['peca']}",
                 key=f"pedcard_{idx}_{enc['rowid']}", use_container_width=True):
        _abrir_popup_pedido(enc, cancelado)

    saldo_badge = ""
    if not cancelado and restante_enc > 0.01:
        saldo_badge = f'&nbsp;<span class="badge badge-amber">Saldo {brl(restante_enc)}</span>'

    st.markdown(f"""
    <div class="lila-cardbody">
        <div class="lila-cardsub">💰 {brl(float(enc.get('valor_total',0) or 0))} &nbsp;·&nbsp; Entrega {formatar_data_br(enc.get('data_entrega',''))}</div>
        <div class="lila-bar"><div style="width:{pct}%;"></div></div>
        <div style="margin-top:6px;">
            <span class="badge {badge_cls}">{badge_txt}</span>
            &nbsp;<span class="badge badge-green">Recebido {brl(float(enc.get('valor_recebido',0) or 0))}</span>
            {saldo_badge}{contrato_badge}
        </div>
    </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# ██████████████████████████  BLOCO: GERENCIAR PEDIDOS  ████████████████████████
# [v16] ÚNICA tela — reúne tudo que "Contratos" e "Gerenciar Pedidos" faziam
# separadamente. "renderizar_contratos" abaixo é só um alias, para o main.py
# não precisar de nenhum ajuste (os dois botões da sidebar caem aqui).
# ══════════════════════════════════════════════════════════════════════════════
def renderizar_gerenciar_pedidos():
    st.markdown("## 📋 Gerenciar Pedidos")
    st.caption(
        "💡 Clique em um pedido para ver e editar tudo — régua de etapas, valores, "
        "contrato (CPF/RG, baixar PDF, assinar via GOV.BR) e medidas da cliente."
    )

    filtro_cli = st.text_input(
        "🔍 Buscar por cliente ou peça",
        key="busca_ger",
        placeholder="Digite o nome da cliente ou da peça...",
    )

    filtro_status = st.radio(
        "Filtrar por status:",
        ["Em andamento", "Todos", "Concluídos", "Cancelados"],
        horizontal=True, key="filtro_ger",
    )

    df_e = encomendas_listar()

    if not df_e.empty:
        if filtro_status == "Em andamento":
            df_e = df_e[(df_e["etapa"].astype(int) < 4) & (df_e["cancelado"].astype(int) == 0)]
        elif filtro_status == "Concluídos":
            df_e = df_e[(df_e["etapa"].astype(int) == 4) & (df_e["cancelado"].astype(int) == 0)]
        elif filtro_status == "Cancelados":
            df_e = df_e[df_e["cancelado"].astype(int) == 1]
        else:
            pass  # Todos

        if filtro_cli.strip():
            mask_busca = (
                df_e["cliente"].astype(str).str.contains(filtro_cli, case=False, na=False)
                | df_e["peca"].astype(str).str.contains(filtro_cli, case=False, na=False)
            )
            df_e = df_e[mask_busca]

        if "data_entrega" in df_e.columns:
            df_e = df_e.sort_values("data_entrega", ascending=True, na_position="last")

    if df_e.empty:
        st.info("Nenhum pedido encontrado com os filtros selecionados.")
    else:
        cols_ped = st.columns(2)
        for idx, (_, enc) in enumerate(df_e.iterrows()):
            with cols_ped[idx % 2]:
                _card_pedido(enc, idx)


def renderizar_contratos():
    """
    [v16] Alias: "Contratos" e "Gerenciar Pedidos" faziam a mesma coisa por
    baixo (abrir `_conteudo_pedido`), só com visual diferente. Unificamos
    numa tela só, e este alias garante que o botão "Contratos" da sidebar
    (em main.py) continue funcionando sem precisar de nenhum ajuste lá.
    """
    renderizar_gerenciar_pedidos()


# ══════════════════════════════════════════════════════════════════════════════
# ████████████████████████████  BLOCO: NOVA ENCOMENDA  █████████████████████████
# ══════════════════════════════════════════════════════════════════════════════
def renderizar_nova_encomenda():
    st.markdown("## 🆕 Nova Encomenda")
    st.caption(
        "Preencha os dados abaixo para cadastrar uma nova encomenda. "
        "Este formulário fica sempre visível nesta tela — inclusive se você trocar "
        "de aba ou de aplicativo no celular, os dados já digitados permanecem aqui."
    )
    with st.container(border=True):
        secao_nova_encomenda_inline()
