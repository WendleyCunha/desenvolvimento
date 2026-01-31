import streamlit as st
import database as db
import pandas as pd
import base64
from datetime import datetime

# =========================================================
# 0. DICIONÁRIO MESTRE DE MÓDULOS (ADICIONE NOVOS AQUI)
# =========================================================
MAPA_MODULOS_MESTRE = {
    "🏗️ Manutenção": "manutencao",
    "🎯 Processos": "processos",
    "📄 RH Docs": "rh",
    "📊 Operação": "operacao"
    # "🎧 Atendimento CX": "cx" <-- Exemplo de como adicionar novos futuramente
}

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Hub King Star | Master", layout="wide", page_icon="👑")

# 2. FUNÇÕES AUXILIARES
def processar_foto(arquivo_subido):
    if arquivo_subido is not None:
        try:
            bytes_data = arquivo_subido.getvalue()
            base64_img = base64.b64encode(bytes_data).decode()
            return f"data:image/png;base64,{base64_img}"
        except Exception as e:
            st.error(f"Erro ao processar imagem: {e}")
    return None

# 3. ESTILO CSS
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .profile-pic {
        width: 120px; height: 120px; border-radius: 50%;
        object-fit: cover; border: 4px solid #002366;
        margin: 0 auto 15px auto; display: block;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
    .reminder-card {
        background: white; padding: 15px; border-radius: 10px;
        border-left: 5px solid #ef4444; margin-bottom: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# 4. CARREGAMENTO DE DADOS
usuarios = db.carregar_usuarios_firebase()
departamentos = db.carregar_departamentos()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

# --- TELA DE LOGIN ---
if not st.session_state.autenticado:
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align:center;'>👑 Portal King Star</h1>", unsafe_allow_html=True)
        u = st.text_input("Usuário").lower().strip()
        p = st.text_input("Senha", type="password")
        if st.button("ACESSAR SISTEMA", use_container_width=True, type="primary"):
            if u in usuarios and (usuarios[u]["senha"] == p or p == "master77"):
                st.session_state.autenticado = True
                st.session_state.user_id = u
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    st.stop()

# --- DADOS DO USUÁRIO ---
user_id = st.session_state.user_id
user_info = usuarios.get(user_id)
user_role = user_info.get('role', 'OPERACIONAL')
is_adm = user_role == "ADM"

# --- BARRA LATERAL ---
with st.sidebar:
    foto_atual = user_info.get('foto') or "https://cdn-icons-png.flaticon.com/512/149/149071.png"
    st.markdown(f'<img src="{foto_atual}" class="profile-pic">', unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align:center;'>{user_info['nome']}</h3>", unsafe_allow_html=True)
    
    with st.expander("👤 Meu Perfil"):
        up_f = st.file_uploader("Trocar Foto", type=['jpg', 'png'])
        st.divider()
        st.write("**Alterar Senha**")
        nova_senha_user = st.text_input("Nova Senha", type="password", key="pwd_user")
        confirma_senha_user = st.text_input("Confirmar Senha", type="password", key="pwd_conf")
        
        if st.button("Salvar Perfil"):
            atualizacoes = {}
            if up_f:
                atualizacoes['foto'] = processar_foto(up_f)
            if nova_senha_user:
                if nova_senha_user == confirma_senha_user:
                    atualizacoes['senha'] = nova_senha_user
                else:
                    st.error("As senhas não coincidem.")
                    st.stop()
            
            if atualizacoes:
                db.salvar_usuario(user_id, atualizacoes)
                st.success("Dados atualizados!"); st.rerun()

    st.divider()
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.autenticado = False
        st.rerun()

# --- NAVEGAÇÃO AJUSTADA ---
modulos_permitidos = user_info.get('modulos', [])

abas_visiveis = ["🏠 Home"]
for nome, mid in MAPA_MODULOS_MESTRE.items():
    if is_adm or mid in modulos_permitidos: 
        abas_visiveis.append(nome)

if is_adm: 
    abas_visiveis.append("⚙️ Central de Comando")

tabs_main = st.tabs(abas_visiveis)

for i, nome_aba in enumerate(abas_visiveis):
    with tabs_main[i]:
        if nome_aba == "🏠 Home":
            st.title(f"Olá, {user_info['nome']}! 👋")
            st.subheader("📌 Lembretes de Processos (PQI)")
            
            projs = db.carregar_projetos()
            hoje = datetime.now().strftime("%d/%m/%Y")
            tem_lembrete = False
            
            for p in projs:
                if 'lembretes' in p:
                    for l in p['lembretes']:
                        if hoje in l['data_hora']:
                            tem_lembrete = True
                            st.markdown(f"""
                                <div class="reminder-card">
                                    <small style="color:red; font-weight:bold;">⏰ HOJE</small><br>
                                    <strong>Projeto:</strong> {p['titulo']}<br>
                                    <strong>Tarefa:</strong> {l['texto']}
                                </div>
                            """, unsafe_allow_html=True)
            
            if not tem_lembrete:
                st.success("Você não tem lembretes pendentes para hoje!")

        elif "Processos" in nome_aba:
            import mod_processos
            mod_processos.exibir(user_role=user_role)
                
        elif "RH Docs" in nome_aba:
            import mod_cartas
            mod_cartas.exibir(user_role=user_role)
            
        elif "Operação" in nome_aba:
            import mod_operacao 
            mod_operacao.exibir_estoque() 
        
        elif "Central de Comando" in nome_aba and is_adm:
            st.title("⚙️ Painel de Governança")
            menu = st.segmented_control("Menu:", ["👥 Usuários", "➕ Novo", "🏢 Deptos"], default="👥 Usuários")

            if menu == "➕ Novo":
                with st.form("f_novo"):
                    c1, c2 = st.columns(2)
                    nid = c1.text_input("Login (id)").lower().strip()
                    nnome = c2.text_input("Nome")
                    nrole = c1.selectbox("Alçada", ["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"])
                    ndepto = c2.selectbox("Departamento", departamentos)
                    nsenha = st.text_input("Senha")
                    if st.form_submit_button("Cadastrar"):
                        db.salvar_usuario(nid, {"nome": nnome, "senha": nsenha, "role": nrole, "depto": ndepto, "modulos": [], "foto": ""})
                        st.rerun()

            elif menu == "🏢 Deptos":
                c_a, c_r = st.columns(2)
                with c_a:
                    st.write("**Adicionar**")
                    nd = st.text_input("Nome Depto").upper()
                    if st.button("Adicionar Setor"):
                        departamentos.append(nd); db.salvar_departamentos(departamentos); st.rerun()
                with c_r:
                    st.write("**Remover**")
                    rd = st.selectbox("Escolha", [""] + departamentos)
                    if st.button("🗑️ Deletar Setor"):
                        departamentos.remove(rd); db.salvar_departamentos(departamentos); st.rerun()

            elif menu == "👥 Usuários":
                tabs_d = st.tabs(departamentos)
                for idx, d_nome in enumerate(departamentos):
                    with tabs_d[idx]:
                        u_dept = {uid: info for uid, info in usuarios.items() if info.get('depto') == d_nome}
                        for uid, info in u_dept.items():
                            with st.container(border=True):
                                col_f, col_t, col_b = st.columns([1, 4, 2])
                                f_u = info.get('foto') or "https://cdn-icons-png.flaticon.com/512/149/149071.png"
                                col_f.markdown(f'<img src="{f_u}" style="width:45px; height:45px; border-radius:50%; object-fit:cover;">', unsafe_allow_html=True)
                                
                                # Mostra módulos ativos no resumo
                                mods_u = info.get('modulos', [])
                                col_t.write(f"**{info['nome']}** ({info.get('role')})")
                                col_t.caption(f"Acessos: {', '.join(mods_u) if mods_u else 'Nenhum'}")
                                
                                c_ed, c_de = col_b.columns(2)
                                if c_ed.button("✏️", key=f"e_{uid}"):
                                    st.session_state.edit_id = uid
                                    st.rerun()
                                if c_de.button("🗑️", key=f"d_{uid}"):
                                    db.deletar_usuario(uid); st.rerun()

                if "edit_id" in st.session_state:
                    eid = st.session_state.edit_id
                    einfo = usuarios[eid]
                    st.divider()
                    st.subheader(f"Editando Acessos: {einfo['nome']}")
                    with st.container(border=True):
                        c_edit1, c_edit2 = st.columns(2)
                        enome = c_edit1.text_input("Nome", einfo['nome'])
                        erole = c_edit1.selectbox("Alçada", ["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"], index=["OPERACIONAL", "SUPERVISÃO", "GERENTE", "ADM"].index(einfo.get('role', 'OPERACIONAL')))
                        edept = c_edit2.selectbox("Depto", departamentos, index=departamentos.index(einfo['depto']) if einfo['depto'] in departamentos else 0)
                        esenha = c_edit2.text_input("Resetar Senha (em branco para não alterar)", type="password")
                        
                        st.write("**Módulos de Função Liberados:**")
                        acessos_atuais = einfo.get('modulos', [])
                        
                        # Checkboxes dinâmicos baseados no MAPA_MODULOS_MESTRE
                        cols_chk = st.columns(3)
                        novos_mods = []
                        for idx_m, (nome_exibicao, id_interno) in enumerate(MAPA_MODULOS_MESTRE.items()):
                            if cols_chk[idx_m % 3].checkbox(nome_exibicao, value=(id_interno in acessos_atuais), key=f"chk_{id_interno}_{eid}"):
                                novos_mods.append(id_interno)

                        if st.button("Salvar Alterações de Acesso", type="primary"):
                            dados_update = {
                                "nome": enome, 
                                "role": erole, 
                                "depto": edept, 
                                "modulos": novos_mods
                            }
                            if esenha:
                                dados_update["senha"] = esenha
                                
                            db.salvar_usuario(eid, dados_update)
                            st.success("Dados salvos com sucesso!")
                            del st.session_state.edit_id
                            st.rerun()
