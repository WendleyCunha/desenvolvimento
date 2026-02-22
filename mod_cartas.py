import streamlit as st
import pandas as pd
import zipfile
import os
from datetime import datetime
from docx import Document
from io import BytesIO
import database as db  # Conexão com seu Firebase

# --- FUNÇÕES DE NÚCLEO (MANTIDAS) ---

def gerar_word_memoria(dados):
    try:
        doc = Document("carta_preenchida.docx")
        for p in doc.paragraphs:
            for k, v in dados.items():
                if f"{{{{{k}}}}}" in p.text: p.text = p.text.replace(f"{{{{{k}}}}}", str(v))
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for k, v in dados.items():
                            if f"{{{{{k}}}}}" in p.text: p.text = p.text.replace(f"{{{{{k}}}}}", str(v))
        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue()
    except Exception as e:
        st.error(f"Erro no template: {e}")
        return None

# --- FUNÇÕES DE APOIO PARA A BASE DE DADOS ---

def obter_base_colaboradores(fire):
    docs = fire.collection("colaboradores_base").stream()
    return {doc.id: doc.to_dict().get("cpf") for doc in docs}

def salvar_novo_colaborador(fire, nome, cpf):
    fire.collection("colaboradores_base").document(nome.upper().strip()).set({"cpf": str(cpf).strip()})

# --- INTERFACE PRINCIPAL ---

def exibir(user_role):
    # CSS Ajustado para os novos "Quadrados" (Cards)
    st.markdown("""
        <style>
        .metric-card {
            background-color: #ffffff;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .card-carta {
            background-color: white;
            padding: 20px;
            border-radius: 12px;
            border-top: 5px solid #002366;
            box-shadow: 0 4px 6px rgba(0,0,0,0.07);
            margin-bottom: 20px;
            min-height: 180px;
        }
        .loja-header {
            background-color: #002366;
            color: white;
            padding: 8px 15px;
            border-radius: 8px;
            margin: 25px 0 15px 0;
            font-weight: bold;
            font-size: 1.1rem;
        }
        .label-card { color: #64748b; font-size: 0.85rem; margin-bottom: 2px; }
        .info-card { font-weight: 600; color: #1e293b; margin-bottom: 8px; }
        </style>
    """, unsafe_allow_html=True)

    st.title("📑 Gestão de Cartas de Débito")
    fire = db.inicializar_db()
    
    # --- CARREGAR DADOS ---
    def obter_cartas():
        docs = fire.collection("cartas_rh").stream()
        return [doc.to_dict() for doc in docs]

    cartas = obter_cartas()
    dict_colab = obter_base_colaboradores(fire)
    lista_nomes = sorted(list(dict_colab.keys()))

    tabs = st.tabs(["🆕 Nova Carta", "📋 Painel de Controle", "📦 Fechamento de Lote", "✅ Histórico", "⚙️ Config"])

    # 1. NOVA CARTA
    with tabs[0]:
        st.subheader("Informações do Lançamento")
        escolha_nome = st.selectbox("Busque ou selecione o Colaborador:", ["+ CADASTRAR NOVO"] + lista_nomes)
        
        with st.form("f_premium", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            if escolha_nome == "+ CADASTRAR NOVO":
                nome = c1.text_input("Nome do Colaborador").upper().strip()
                cpf = c2.text_input("CPF")
            else:
                nome = escolha_nome
                cpf = c2.text_input("CPF", value=dict_colab.get(escolha_nome, ""))
            
            cod_cli = c3.text_input("Código do Cliente")
            v1, v2, v3 = st.columns(3)
            valor = v1.number_input("Valor R$", min_value=0.0)
            loja = v2.text_input("Loja Origem").upper()
            data_c = v3.date_input("Data da Ocorrência")
            motivo = st.text_area("Motivo Detalhado").upper()
            
            if st.form_submit_button("✨ Gerar e Registrar"):
                if nome and cpf and cod_cli:
                    if escolha_nome == "+ CADASTRAR NOVO":
                        salvar_novo_colaborador(fire, nome, cpf)
                    
                    id_carta = datetime.now().strftime("%Y%m%d%H%M%S")
                    dados_fb = {
                        "id": id_carta, "NOME": nome, "CPF": cpf, "COD_CLI": cod_cli, 
                        "VALOR": valor, "LOJA": loja, "DATA": data_c.strftime("%d/%m/%Y"), 
                        "MOTIVO": motivo, "status": "Aguardando Assinatura", "anexo_bin": None,
                        "data_criacao": datetime.now().strftime("%d/%m/%Y %H:%M")
                    }
                    fire.collection("cartas_rh").document(id_carta).set(dados_fb)
                    st.success("Carta registrada!")
                    st.rerun()

    # 2. PAINEL DE CONTROLE (AJUSTADO: Resumo + Grid de Cards)
    with tabs[1]:
        lista_painel = [c for c in cartas if c.get('status') == "Aguardando Assinatura"]
        
        # --- NOVO: PAINEL DE RESUMO ---
        if lista_painel:
            total_valor = sum(c['VALOR'] for c in lista_painel)
            m1, m2 = st.columns(2)
            with m1:
                st.markdown(f'<div class="metric-card"><div class="label-card">Total Pendente</div><div style="font-size:1.5rem; font-weight:bold;">{len(lista_painel)} Cartas</div></div>', unsafe_allow_html=True)
            with m2:
                st.markdown(f'<div class="metric-card"><div class="label-card">Valor Total</div><div style="font-size:1.5rem; font-weight:bold; color:#d9534f;">R$ {total_valor:,.2f}</div></div>', unsafe_allow_html=True)
            
            st.write("---")
            busca_p = st.text_input("🔍 Buscar no Painel (Nome/Código do Cliente)")
            if busca_p:
                lista_painel = [c for c in lista_painel if busca_p.upper() in c['NOME'] or busca_p in str(c['COD_CLI'])]

            df_p = pd.DataFrame(lista_painel).sort_values(by="LOJA")
            
            for loja_n, group in df_p.groupby("LOJA"):
                st.markdown(f'<div class="loja-header">📍 {loja_n} ({len(group)} itens)</div>', unsafe_allow_html=True)
                
                # --- NOVO: GRID DE CARDS (3 por linha) ---
                cols = st.columns(3)
                for idx, (_, c) in enumerate(group.iterrows()):
                    col_idx = idx % 3
                    with cols[col_idx]:
                        # Card Visual
                        st.markdown(f"""
                            <div class="card-carta">
                                <div class="label-card">COLABORADOR</div>
                                <div class="info-card">{c['NOME']}</div>
                                <div class="label-card">CPF | CÓD. CLIENTE</div>
                                <div class="info-card">{c['CPF']} | {c['COD_CLI']}</div>
                                <div class="label-card">VALOR</div>
                                <div style="font-size: 1.2rem; font-weight: bold; color: #002366;">R$ {c['VALOR']:,.2f}</div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Ações do Card
                        dados_w = {"NOME_COLAB": c['NOME'], "CPF": c['CPF'], "CODIGO_CLIENTE": c['COD_CLI'], "VALOR_DEBITO": f"R$ {c['VALOR']:,.2f}", "LOJA_ORIGEM": c['LOJA'], "DATA_COMPRA": c['DATA'], "DESC_DEBITO": c['MOTIVO'], "DATA_LOCAL": f"São Paulo, {datetime.now().strftime('%d/%m/%Y')}"}
                        w_bytes = gerar_word_memoria(dados_w)
                        
                        btn_col1, btn_col2 = st.columns([1, 1])
                        btn_col1.download_button("📂 Baixar", w_bytes, file_name=f"Carta_{c['NOME']}.docx", key=f"w_{c['id']}", use_container_width=True)
                        
                        if user_role in ["ADM", "GERENTE"]:
                            if btn_col2.button("🗑️ Excluir", key=f"del_{c['id']}", use_container_width=True):
                                fire.collection("cartas_rh").document(c['id']).delete()
                                st.rerun()
                        
                        up = st.file_uploader("Upload Assinada", key=f"up_{c['id']}", label_visibility="collapsed")
                        if up:
                            fire.collection("cartas_rh").document(c['id']).update({"status": "CARTA RECEBIDA", "anexo_bin": up.getvalue(), "nome_arquivo": up.name})
                            st.rerun()
        else:
            st.info("Nada pendente.")

    # 3. FECHAMENTO DE LOTE
    with tabs[2]:
        prontas = [c for c in cartas if c.get('status') == "CARTA RECEBIDA"]
        if not prontas:
            st.info("Nenhuma carta assinada pronta.")
        else:
            st.subheader(f"📦 Lote pronto ({len(prontas)} itens)")
            st.dataframe(pd.DataFrame(prontas)[['NOME', 'CPF', 'VALOR', 'LOJA', 'COD_CLI']])
            if st.button("🚀 FINALIZAR LOTE E ENVIAR AO HISTÓRICO"):
                id_lote = datetime.now().strftime("%Y%m%d_%H%M")
                fire.collection("lotes_rh").document(id_lote).set({
                    "id": id_lote, "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "total": len(prontas), "ids_cartas": [c['id'] for c in prontas]
                })
                for c in prontas:
                    fire.collection("cartas_rh").document(c['id']).update({"status": "LOTE_FECHADO"})
                st.success("Lote finalizado!"); st.rerun()

    # 4. HISTÓRICO
    with tabs[3]:
        busca_h = st.text_input("🔎 Pesquisar no Histórico")
        docs_lotes = fire.collection("lotes_rh").stream()
        lotes = [d.to_dict() for d in docs_lotes]
        
        for l in sorted(lotes, key=lambda x: x['id'], reverse=True):
            ids_do_lote = l.get('ids_cartas', [])
            cartas_do_lote = [c for c in cartas if c['id'] in ids_do_lote]
            
            if busca_h:
                cartas_do_lote = [c for c in cartas_do_lote if busca_h.upper() in c['NOME'] or busca_h in c['CPF'] or busca_h in str(c['COD_CLI'])]
            
            if not cartas_do_lote and busca_h: continue

            with st.expander(f"📦 Lote {l['data']} ({len(cartas_do_lote)} itens)"):
                df_lote = pd.DataFrame(cartas_do_lote)[['NOME', 'CPF', 'VALOR', 'LOJA', 'DATA', 'MOTIVO', 'COD_CLI']]
                out_ex = BytesIO(); df_lote.to_excel(out_ex, index=False)
                
                cartas_com_anexo = [c for c in cartas_do_lote if c.get('anexo_bin')]
                out_zip = BytesIO()
                with zipfile.ZipFile(out_zip, "w") as z:
                    for c in cartas_com_anexo:
                        z.writestr(f"Assinada_{c['NOME']}.pdf", c['anexo_bin'])
                
                c1, c2, c3 = st.columns(3)
                c1.download_button("📊 Excel", out_ex.getvalue(), file_name=f"Lote_{l['id']}.xlsx", key=f"ex_{l['id']}")
                
                if cartas_com_anexo:
                    c2.download_button("📥 ZIP", out_zip.getvalue(), file_name=f"Cartas_{l['id']}.zip", key=f"zp_{l['id']}")
                    if user_role in ["ADM", "GERENTE"] and c3.button("🔥 Limpar PDFs", key=f"lp_{l['id']}"):
                        for c in cartas_com_anexo:
                            fire.collection("cartas_rh").document(c['id']).update({"anexo_bin": None})
                        st.rerun()
                else:
                    c2.info("PDFs limpos.")
                    if user_role in ["ADM", "GERENTE"] and c3.button("🗑️ Deletar Registro", key=f"rm_{l['id']}"):
                        fire.collection("lotes_rh").document(l['id']).delete(); st.rerun()

    # 5. CONFIGURAÇÃO
    if user_role in ["ADM", "GERENTE"]:
        with tabs[4]:
            st.subheader("⚙️ Configurar Base")
            up_base = st.file_uploader("Subir Novo Excel de Colaboradores", type="xlsx")
            if up_base:
                df_b = pd.read_excel(up_base)
                if st.button("Confirmar Importação"):
                    for _, r in df_b.iterrows():
                        salvar_novo_colaborador(fire, str(r['NOME']), str(r['CPF']))
                    st.success("Base atualizada!"); st.rerun()
