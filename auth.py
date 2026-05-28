import streamlit as st
import hashlib
from db import inicializar_db, salvar_usuario, carregar_usuarios, deletar_usuario

# ─── DEFINIÇÃO DE ROLES ────────────────────────────────────────────────────────
ROLES = {
    "admin": {
        "label":     "Administrador",
        "can_edit":  True,
        "abas_edit": ["*"],
        "modulos":   ["passagens"],
        "icon":      "👑",
    },
    "editor": {
        "label":     "Editor",
        "can_edit":  True,
        "abas_edit": ["relatorios", "triagem", "consolidado", "anuncios"],
        "modulos":   [],
        "icon":      "✏️",
    },
    "chamada": {
        "label":     "Operador de Chamada",
        "can_edit":  True,
        "abas_edit": ["chamada"],
        "modulos":   ["passagens"],
        "icon":      "🚩",
    },
    "viewer": {
        "label":     "Somente Leitura",
        "can_edit":  False,
        "abas_edit": [],
        "modulos":   [],
        "icon":      "👁️",
    },
    "viewer_passagens": {
        "label":     "Visualizador de Passagens",
        "can_edit":  False,
        "abas_edit": [],
        "modulos":   ["passagens"],
        "icon":      "🚌",
    },
}


# ─── HASH DE SENHA (deve vir antes de bootstrap_admin) ────────────────────────

def _hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()


# ─── BOOTSTRAP: cria admin inicial se banco estiver vazio ─────────────────────
# REMOVA a chamada bootstrap_admin() do main.py após o primeiro login.

def bootstrap_admin():
    BOOTSTRAP_EMAIL = "wendley@admin.com"
    BOOTSTRAP_SENHA = "admin123"

    db = inicializar_db()
    if not db:
        return

    usuarios = list(db.collection("usuarios").limit(1).stream())
    if not usuarios:
        db.collection("usuarios").document(BOOTSTRAP_EMAIL).set({
            "nome":  "Administrador",
            "role":  "admin",
            "senha": _hash_senha(BOOTSTRAP_SENHA),
        })


# ─── LOGIN / LOGOUT ────────────────────────────────────────────────────────────

def login():
    if "usuario" in st.session_state:
        return st.session_state.usuario

    st.markdown("""
        <style>
        .login-box { max-width: 400px; margin: 80px auto; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='login-box'>", unsafe_allow_html=True)
    st.markdown("## 🔐 Acesso ao Sistema")
    st.markdown("**Parque Aliança — Gestão**")
    st.divider()

    with st.form("form_login"):
        email  = st.text_input("E-mail", placeholder="seu@email.com")
        senha  = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True, type="primary")

    if entrar:
        if not email or not senha:
            st.error("Preencha e-mail e senha.")
            st.stop()

        db = inicializar_db()
        if not db:
            st.error("Erro de conexão com o banco.")
            st.stop()

        doc = db.collection("usuarios").document(email).get()
        if not doc.exists:
            st.error("Usuário não encontrado.")
            st.stop()

        dados            = doc.to_dict()
        senha_armazenada = dados.get("senha", "")
        senha_ok         = (
            senha_armazenada == _hash_senha(senha)
            or senha_armazenada == senha  # legado texto puro
        )

        if not senha_ok:
            st.error("Senha incorreta.")
            st.stop()

        role        = dados.get("role", "viewer")
        role_config = ROLES.get(role, ROLES["viewer"])

        st.session_state.usuario = {
            "email": email,
            "nome":  dados.get("nome", email),
            "role":  role,
            **role_config,
        }
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


def logout():
    if "usuario" in st.session_state:
        del st.session_state["usuario"]
    st.rerun()


# ─── HELPERS DE PERMISSÃO ──────────────────────────────────────────────────────

def usuario_atual() -> dict:
    return st.session_state.get("usuario", {})


def pode_editar(aba: str = None) -> bool:
    u    = usuario_atual()
    if not u.get("can_edit"):
        return False
    abas = u.get("abas_edit", [])
    if "*" in abas:
        return True
    if aba is None:
        return len(abas) > 0
    return aba in abas


def tem_modulo(modulo: str) -> bool:
    u = usuario_atual()
    if u.get("role") == "admin":
        return True
    return modulo in u.get("modulos", [])


def is_admin() -> bool:
    return usuario_atual().get("role") == "admin"


def bloquear_edicao(aba: str = None):
    if not pode_editar(aba):
        st.info("🔒 Você tem acesso **somente leitura** nesta aba.")
        return True
    return False


# ─── PAINEL DE GESTÃO DE USUÁRIOS (apenas admin) ──────────────────────────────

def render_gestao_usuarios():
    if not is_admin():
        st.warning("Acesso restrito a administradores.")
        return

    st.subheader("👥 Gerenciar Usuários do Sistema")
    usuarios = carregar_usuarios()

    if usuarios:
        st.caption(f"{len(usuarios)} usuário(s) cadastrado(s)")
        for email, u in usuarios.items():
            role_info = ROLES.get(u.get("role", "viewer"), ROLES["viewer"])
            with st.expander(
                f"{role_info['icon']} **{u.get('nome', email)}** — {email} — {role_info['label']}"
            ):
                c1, c2    = st.columns(2)
                novo_nome = c1.text_input("Nome", value=u.get("nome", ""), key=f"un_{email}")
                novo_role = c2.selectbox(
                    "Permissão",
                    list(ROLES.keys()),
                    format_func=lambda r: f"{ROLES[r]['icon']} {ROLES[r]['label']}",
                    index=list(ROLES.keys()).index(u.get("role", "viewer")),
                    key=f"ur_{email}",
                )
                nova_senha = st.text_input(
                    "Nova Senha (deixe em branco para não alterar)",
                    type="password",
                    key=f"us_{email}",
                )
                col_salvar, col_del = st.columns(2)
                if col_salvar.button("💾 Salvar", key=f"save_u_{email}", use_container_width=True):
                    dados_update = {"nome": novo_nome, "role": novo_role}
                    if nova_senha.strip():
                        dados_update["senha"] = _hash_senha(nova_senha.strip())
                    salvar_usuario(email, dados_update)
                    st.toast(f"✅ {email} atualizado!")
                    st.rerun()
                if col_del.button("🗑️ Remover", key=f"del_u_{email}", use_container_width=True):
                    if email != usuario_atual().get("email"):
                        deletar_usuario(email)
                        st.toast(f"Usuário {email} removido.")
                        st.rerun()
                    else:
                        st.error("Você não pode remover sua própria conta.")
    else:
        st.info("Nenhum usuário cadastrado ainda.")

    st.divider()
    st.markdown("##### ➕ Novo Usuário")

    with st.form("form_novo_usuario", clear_on_submit=True):
        c1, c2       = st.columns(2)
        novo_email   = c1.text_input("E-mail *")
        novo_nome_f  = c2.text_input("Nome completo *")
        c3, c4       = st.columns(2)
        novo_role_f  = c3.selectbox(
            "Permissão *",
            list(ROLES.keys()),
            format_func=lambda r: f"{ROLES[r]['icon']} {ROLES[r]['label']}",
        )
        nova_senha_f = c4.text_input("Senha *", type="password")

        st.caption("**Resumo das permissões:**")
        _render_role_info(novo_role_f)

        if st.form_submit_button("➕ Criar Usuário", use_container_width=True, type="primary"):
            if novo_email.strip() and novo_nome_f.strip() and nova_senha_f.strip():
                salvar_usuario(novo_email.strip(), {
                    "nome":  novo_nome_f.strip(),
                    "role":  novo_role_f,
                    "senha": _hash_senha(nova_senha_f.strip()),
                })
                st.success(f"✅ Usuário {novo_email} criado com sucesso!")
                st.rerun()
            else:
                st.error("Preencha todos os campos obrigatórios.")


def _render_role_info(role: str):
    info = ROLES.get(role, ROLES["viewer"])
    abas = info["abas_edit"]
    mods = info["modulos"]
    if "*" in abas:
        st.markdown("✅ Edita **todas** as abas e módulos")
    elif abas:
        st.markdown(f"✅ Edita: `{'`, `'.join(abas)}`")
    else:
        st.markdown("🔒 Somente leitura (sem edição)")
    if mods:
        st.markdown(f"📦 Módulos: `{'`, `'.join(mods)}`")
