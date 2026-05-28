"""
Script de bootstrap: cria o usuário admin inicial no Firestore.
Execute UMA VEZ localmente antes de subir para o Streamlit Cloud:

    python criar_admin.py

Depois delete este arquivo do repositório.
"""
import json
import hashlib
from google.cloud import firestore
from google.oauth2 import service_account

# ── Preencha aqui ──────────────────────────────────────────────────────────────
CAMINHO_CREDENCIAL = "credencial.json"   # seu arquivo de service account local
EMAIL_ADMIN        = "seu@email.com"
NOME_ADMIN         = "Administrador"
SENHA_ADMIN        = "troque_esta_senha"
# ───────────────────────────────────────────────────────────────────────────────


def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode()).hexdigest()


def main():
    with open(CAMINHO_CREDENCIAL) as f:
        key_dict = json.load(f)

    creds = service_account.Credentials.from_service_account_info(key_dict)
    db    = firestore.Client(credentials=creds, project="wendleydesenvolvimento")

    db.collection("usuarios").document(EMAIL_ADMIN).set({
        "nome":  NOME_ADMIN,
        "role":  "admin",
        "senha": hash_senha(SENHA_ADMIN),
    })
    print(f"✅ Admin '{EMAIL_ADMIN}' criado com sucesso!")


if __name__ == "__main__":
    main()
