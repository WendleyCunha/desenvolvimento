import streamlit as st
import pandas as pd
import zipfile
import os
from datetime import datetime
from docx import Document
from io import BytesIO
import database as db  # Conexão com seu Firebase

# --- FUNÇÕES DE NÚCLEO ---

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

def exibir(user_role):
    st.markdown("""
        <style>
        .card-carta { background-color: white; padding: 20px; border-radius: 15px; border-left: 5px solid #002366; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 15px; }
        .status-badge { padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; background-color: #e2e8f0; }
        </style>
    """, unsafe_allow_html=True)

    st.title("📑 Gestão de Cartas de Débito")
    fire = db.inicializar_db()
    
    # --- CARREGAR DADOS ---
    def obter_cartas():
        docs = fire.collection("cartas_rh").stream()
        return [doc.to_dict() for doc in docs]

    cartas = obter_cartas()
    tabs = st.tabs(["🆕 Nova Carta", "📋 Painel de Controle", "📦 Fechamento de Lote", "✅ Histórico"])

    # 1. NOVA CARTA
    with tabs[0]:
        with st.form("f_premium", clear_on_submit=True):
            st.subheader("Informações do Lançamento")
            c1, c2, c3 = st.columns(3)
            nome = c1.text_input("Nome do Colaborador").upper()
            cpf = c2.text_input("CPF")
            cod_cli = c3.text_input("Código do Cliente")
            v1, v2, v3 = st.columns(3)
            valor = v1.number_input("Valor R$", min_value=0.0)
            loja = v2.text_input("Loja Origem").upper()
            data_c = v3.date_input("Data da Ocorrência")
            motivo = st.text_area("Motivo Detalhado").upper()
            
            if st.form_submit_button("✨ Gerar e Registrar"):
                if nome and cpf and cod_cli:
                    id_carta = datetime.now().strftime("%Y%m%d%H%M%S")
                    dados_fb = {
                        "id": id_carta, "NOME": nome, "CPF": cpf, "COD_CLI": cod_cli, 
                        "VALOR": valor, "LOJA": loja, "DATA": data_c.strftime("%d/%m/%Y"), 
                        "MOTIVO": motivo, "status": "Aguardando Assinatura", "anexo_bin": None,
                        "data_criacao": datetime.now().strftime("%d/%m/%Y %H:%M")
                    }
                    fire.collection("cartas_rh").document(id_carta).set(dados_fb)
                    st.success("Carta registrada com sucesso!")
                    st.rerun()

    # 2. PAINEL DE CONTROLE
    with tabs[1]:
        col_s1, col_s2 = st.columns([2, 1])
        busca_p = col_s1.text_input("🔍 Buscar no Painel (Nome/Código)")
        lista_painel = [c for c in cartas if c.get('status') == "Aguardando Assinatura"]
        if busca_p:
            lista_painel = [c for c in lista_painel if busca_p.upper() in c['NOME'] or busca_p in c['COD_CLI']]

        for c in lista_painel:
            with st.container():
                st.markdown(f'<div class="card-carta"><strong>{c["NOME"]}</strong> | Loja: {c["LOJA"]} | CPF: {c["CPF"]}<br><small>Valor: R$ {c["VALOR"]:,.2f} | Cliente: {c["COD_CLI"]}</small></div>', unsafe_allow_html=True)
                b1, b2, b3 = st.columns([1, 2, 1])
                
                # Download Word para assinar
                dados_w = {"NOME_COLAB": c['NOME'], "CPF": c['CPF'], "CODIGO_CLIENTE": c['COD_CLI'], "VALOR_DEBITO": f"R$ {c['VALOR']:,.2f}", "LOJA_ORIGEM": c['LOJA'], "DATA_COMPRA": c['DATA'], "DESC_DEBITO": c['MOTIVO'], "DATA_LOCAL": f"São Paulo, {datetime.now().strftime('%d/%m/%Y')}"}
                w_bytes = gerar_word_memoria(dados_w)
                b1.download_button("📂 Word", w_bytes, file_name=f"Carta_{c['NOME']}.docx", key=f"w_{c['id']}")
                
                # UPLOAD DA ASSINADA
                up = b2.file_uploader("Arraste a CARTA ASSINADA aqui", key=f"up_{c['id']}")
                if up:
                    conteudo = up.getvalue()
                    if len(conteudo) > 800000:
                        st.error("Arquivo muito pesado (limite 800KB).")
                    else:
                        fire.collection("cartas_rh").document(c['id']).update({
                            "status": "CARTA RECEBIDA", 
                            "anexo_bin": conteudo, 
                            "nome_arquivo": up.name
                        })
                        st.rerun()
                if user_role in ["ADM", "GERENTE"] and b3.button("🗑️", key=f"del_{c['id']}"):
                    fire.collection("cartas_rh").document(c['id']).delete(); st.rerun()

    # 3. FECHAMENTO DE LOTE
    with tabs[2]:
        prontas = [c for c in cartas if c.get('status') == "CARTA RECEBIDA"]
        if not prontas:
            st.info("Nenhuma carta assinada pronta para fechamento.")
        else:
            st.subheader(f"📦 Lote pronto com {len(prontas)} cartas assinadas")
            df_preview = pd.DataFrame(prontas)[['NOME', 'CPF', 'VALOR', 'LOJA', 'DATA']]
            st.dataframe(df_preview, use_container_width=True)
            
            if st.button("🚀 FINALIZAR LOTE E ENVIAR AO HISTÓRICO", type="primary"):
                id_lote = datetime.now().strftime("%Y%m%d_%H%M")
                ids_componentes = [c['id'] for c in prontas]
                
                fire.collection("lotes_rh").document(id_lote).set({
                    "id": id_lote, "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "total": len(prontas), "ids_cartas": ids_componentes
                })
                for c in prontas:
                    fire.collection("cartas_rh").document(c['id']).update({"status": "LOTE_FECHADO"})
                st.success("Lote finalizado! Disponível na aba Histórico.")
                st.rerun()

    # 4. HISTÓRICO (Com Busca e Limpeza Seletiva)
    with tabs[3]:
        col_h1, col_h2 = st.columns([2, 1])
        busca_h = col_h1.text_input("🔎 Pesquisar no Histórico (Nome ou CPF)")
        
        docs_lotes = fire.collection("lotes_rh").stream()
        lotes = [d.to_dict() for d in docs_lotes]
        
        for l in sorted(lotes, key=lambda x: x['id'], reverse=True):
            ids_lote = l.get('ids_cartas', [])
            cartas_do_lote = [c for c in cartas if c['id'] in ids_lote]
            
            # Filtro de busca dentro do lote
            if busca_h:
                cartas_do_lote = [c for c in cartas_do_lote if busca_h.upper() in c['NOME'] or busca_h in c['CPF']]
            
            if not cartas_do_lote and busca_h: continue # Pula lotes que não batem com a busca

            with st.expander(f"📦 Lote {l['data']} ({len(cartas_do_lote)} itens)"):
                # 1. Gerar Excel (Sempre disponível)
                df_lote = pd.DataFrame(cartas_do_lote)[['NOME', 'CPF', 'VALOR', 'LOJA', 'DATA', 'MOTIVO', 'COD_CLI']]
                out_ex = BytesIO(); df_lote.to_excel(out_ex, index=False)
                
                # 2. Gerar ZIP (Somente se houver anexos)
                cartas_com_anexo = [c for c in cartas_do_lote if c.get('anexo_bin')]
                out_zip = BytesIO()
                with zipfile.ZipFile(out_zip, "w") as z:
                    for c in cartas_com_anexo:
                        z.writestr(f"Assinada_{c['NOME']}.pdf", c['anexo_bin'])
                
                c1, c2, c3 = st.columns(3)
                c1.download_button("📊 Baixar Excel", out_ex.getvalue(), file_name=f"Dados_Lote_{l['id']}.xlsx", key=f"ex_{l['id']}")
                
                if cartas_com_anexo:
                    c2.download_button("📥 Baixar ZIP (Assinadas)", out_zip.getvalue(), file_name=f"Cartas_Assinadas_{l['id']}.zip", key=f"zp_{l['id']}")
                    if user_role in ["ADM", "GERENTE"] and c3.button("🔥 Limpar PDFs (Espaço)", key=f"lp_{l['id']}"):
                        # APAGA APENAS O ARQUIVO PESADO, MANTÉM OS DADOS
                        for c in cartas_com_anexo:
                            fire.collection("cartas_rh").document(c['id']).update({"anexo_bin": None})
                        st.toast("Arquivos removidos. Dados preservados!"); st.rerun()
                else:
                    c2.info("PDFs já removidos.")
                    if user_role in ["ADM", "GERENTE"] and c3.button("🗑️ Deletar Registro", key=f"rm_{l['id']}"):
                        fire.collection("lotes_rh").document(l['id']).delete(); st.rerun()
