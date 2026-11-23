"""
hub/governanca.py — GOVERNANÇA: permissão por MÓDULO → ABA → CAMPO, conferida no SERVIDOR
─────────────────────────────────────────────────────────────────────────────
Para cada módulo o administrador define, por pessoa (Configurações → Usuários → Personalizado):

  • ABA:   Sem acesso · Ver · Incluir · Editar · Excluir   (cada nível inclui os de baixo)
  • CAMPO: Oculto · Ver · Editar · Excluir                 (Excluir = pode apagar o valor do campo)

Como é garantido:
  1. Toda rota /api de módulo está ligada a uma aba e a um nível (ABAS abaixo). Um middleware (main.py)
     confere ANTES da rota rodar: sem o nível, devolve 403 — nem mexendo no navegador passa.
  2. Os campos são conferidos na gravação (aplicar_campos): mudar campo "Ver/Oculto" ou apagar um campo
     que é só "Editar" é recusado. Campos "Oculto" não saem do servidor (cada módulo filtra a saída).
  3. A tela esconde as abas "Sem acesso" sozinha (estilo injetado em /m/<módulo>).
  4. REGRA PARA FUNÇÃO NOVA: rota nova de módulo TEM de entrar aqui. O teste
     tests/test_governanca.py falha se existir rota de módulo sem aba — o PR não passa.

Compatibilidade: quem não tem nada configurado continua como hoje (aba = Excluir, campo = Excluir);
as "ações" antigas de cada módulo continuam valendo junto (as duas regras precisam deixar).
"""
from __future__ import annotations

from fnmatch import fnmatchcase

NIVEIS_ABA = ("nenhum", "ver", "incluir", "editar", "excluir")
NIVEIS_CAMPO = ("oculto", "ver", "editar", "excluir")
ROTULO_ABA = {"nenhum": "Sem acesso", "ver": "Ver", "incluir": "Incluir", "editar": "Editar", "excluir": "Excluir"}
ROTULO_CAMPO = {"oculto": "Oculto", "ver": "Ver", "editar": "Editar", "excluir": "Excluir"}
_POR_METODO = {"GET": "ver", "HEAD": "ver", "POST": "incluir", "PUT": "editar", "PATCH": "editar", "DELETE": "excluir"}
ACESSO = "acesso"   # rota comum do módulo (carrega a tela): basta abrir o módulo


def _r(metodo: str, padrao: str, nivel: str = "auto") -> tuple:
    return (metodo.upper(), padrao, nivel)


# ══════════════════════════════════════════════════════════════════════════════
# MAPA: módulo → abas (rótulo, campos, rotas). Rotas: (MÉTODO|*, padrão com *, nível|auto)
#   auto = GET ver · POST incluir · PUT/PATCH editar · DELETE excluir.  A primeira regra que casar vale.
#   "por_chave": rota compartilhada por várias abas (ex.: PUT /config) — cada chave do corpo aponta a aba.
# ══════════════════════════════════════════════════════════════════════════════
S = "/api/secretaria"
ABAS: dict[str, dict] = {
    "secretaria": {
        "prefixos": [S],
        "comum": [_r("GET", f"{S}/base", ACESSO)],
        "abas": {
            "mes": {"rotulo": "Mês (relatórios e triagem)", "campos": {"observacoes": "Observações do relatório"}, "rotas": [
                _r("POST", f"{S}/relatorios/corrigir-rotulos", "editar"), _r("POST", f"{S}/relatorios*", "incluir"),
                _r("PUT", f"{S}/relatorios/*", "editar"), _r("DELETE", f"{S}/relatorios/*", "excluir"),
                _r("GET", f"{S}/pdf/total/*", "ver")]},
            "assistencia": {"rotulo": "Assistência", "campos": {}, "rotas": [
                _r("GET", f"{S}/assistencia"), _r("PUT", f"{S}/assistencia/*", "editar"), _r("GET", f"{S}/pdf/s88", "ver"),
                _r("GET", f"{S}/anual", "ver")]},
            "membros": {"rotulo": "Membros", "campos": {
                "nome_oficial": "Nome completo", "categoria": "Categoria fixa", "grupo": "Grupo de campo", "genero": "Gênero",
                "classe": "Classe", "data_nascimento": "Data de nascimento", "data_batismo": "Data de batismo",
                "telefone_emergencia": "Telefone de emergência", "inicio_chave": "Entrou no quadro em", "cargo": "Cargo(s)",
                "observacao": "Observações da ficha", "surdo": "S-10: surdo", "cego": "S-10: cego", "preso": "S-10: preso"},
                "rotas": [
                _r("GET", f"{S}/membro/*", "ver"), _r("GET", f"{S}/lembretes/membros", "ver"), _r("POST", f"{S}/membros/*/status", "editar"), _r("POST", f"{S}/membros", "incluir"),
                _r("PUT", f"{S}/membros/*", "editar"), _r("DELETE", f"{S}/membros/*", "excluir"),
                _r("GET", f"{S}/lixeira", "ver"), _r("POST", f"{S}/lixeira/*/restaurar", "editar"), _r("DELETE", f"{S}/lixeira/*", "excluir"),
                _r("GET", f"{S}/pdf/s21/*", "ver"), _r("POST", f"{S}/importar-s21/ler", "ver"), _r("POST", f"{S}/importar-s21/aplicar", "editar")]},
            "anuncios": {"rotulo": "Anúncios", "campos": {}, "rotas": [_r("*", f"{S}/anuncios*")]},
            "fechamentos": {"rotulo": "Fechamentos", "campos": {}, "rotas": [
                _r("POST", f"{S}/fechamentos/*", "editar"), _r("DELETE", f"{S}/fechamentos/*", "excluir"), _r("POST", f"{S}/visita/zip", "ver")]},
            "it": {"rotulo": "IT", "campos": {}, "rotas": []},
            "ajustes": {"rotulo": "Ajustes", "campos": {}, "rotas": [_r("GET", f"{S}/lembretes", "ver")]},
        },
        "por_chave": {("PUT", f"{S}/config"): {"_padrao": "ajustes", "pastas": "fechamentos", "its": "it",
                                               "territorios_total": "assistencia", "territorios_nao_trabalhados": "assistencia",
                                               "anuncios": "anuncios"}},
    },
    "passagens": {
        "prefixos": ["/api/passagens"],
        "comum": [_r("GET", "/api/passagens/eventos", ACESSO)],
        "abas": {
            "reservas": {"rotulo": "Reservas & Pagamentos", "campos": {
                "nome": "Nome", "rg": "RG", "cpf": "CPF", "grupo": "Grupo", "dias_onibus": "Viagens e ônibus", "pago": "Situação do pagamento",
                "valor_pago": "Valor pago", "valor_total": "Valores da passagem e da frota"}, "rotas": [
                _r("GET", "/api/passagens/eventos/*/passageiros", "ver"), _r("POST", "/api/passagens/eventos/*/passageiros/*/embarque", "editar"),
                _r("POST", "/api/passagens/eventos/*/passageiros", "incluir"), _r("PUT", "/api/passagens/eventos/*/passageiros/*", "editar"),
                _r("DELETE", "/api/passagens/eventos/*/passageiros/*", "excluir"), _r("GET", "/api/passagens/cadastro", "ver"),
                _r("POST", "/api/passagens/importar/previa", "ver"), _r("POST", "/api/passagens/importar", "incluir")]},
            "chamada": {"rotulo": "Chamada de Embarque", "campos": {"embarcou": "Embarque"}, "rotas": []},
            "ajustes": {"rotulo": "Ajustes (eventos e ônibus)", "campos": {}, "rotas": [
                _r("POST", "/api/passagens/eventos/*/arquivar", "excluir"), _r("POST", "/api/passagens/eventos/*/onibus", "incluir"),
                _r("POST", "/api/passagens/eventos", "incluir"), _r("PUT", "/api/passagens/eventos/*", "editar"),
                _r("DELETE", "/api/passagens/eventos/*", "excluir")]},
        },
    },
    "erp": {
        "prefixos": ["/api/erp"],
        "comum": [_r("GET", "/api/erp/estado", ACESSO)],
        "abas": {
            "painel": {"rotulo": "Painel", "campos": {}, "rotas": []},
            "pedidos": {"rotulo": "Pedidos", "campos": {"preco": "Preços e valores de venda"}, "rotas": [
                _r("GET", "/api/erp/pedidos/*/pdf", "ver"), _r("POST", "/api/erp/pedidos/*/acao", "editar"),
                _r("POST", "/api/erp/pedidos", "incluir"), _r("PUT", "/api/erp/pedidos/*", "editar")]},
            "agenda": {"rotulo": "Agenda", "campos": {}, "rotas": []},
            "cargas": {"rotulo": "Cargas", "campos": {}, "rotas": [
                _r("POST", "/api/erp/cargas/*/*", "editar"), _r("POST", "/api/erp/cargas", "incluir"), _r("PUT", "/api/erp/cargas/*", "editar"),
                _r("DELETE", "/api/erp/cargas/*", "excluir"), _r("POST", "/api/erp/plano/confirmar", "incluir"), _r("POST", "/api/erp/plano/*", "ver"),
                _r("PUT", "/api/erp/plano/config", "editar")]},
            "retornos": {"rotulo": "Retornos", "campos": {}, "rotas": []},
            "estoque": {"rotulo": "Estoque", "campos": {"custo": "Custo dos produtos"}, "rotas": [
                _r("GET", "/api/erp/kardex/*", "ver"), _r("POST", "/api/erp/estoque/ajuste", "editar"), _r("POST", "/api/erp/estoque/*", "incluir")]},
            "produtos": {"rotulo": "Produtos", "campos": {}, "rotas": [_r("POST", "/api/erp/produtos", "incluir"), _r("PUT", "/api/erp/produtos/*", "editar")]},
            "cadastros": {"rotulo": "Cadastros", "campos": {"contato": "Documento, telefone e e-mail"}, "rotas": [
                _r("POST", "/api/erp/parceiros", "incluir"), _r("PUT", "/api/erp/parceiros/*", "editar")]},
            "ajustes": {"rotulo": "Ajustes", "campos": {}, "rotas": [
                _r("PUT", "/api/erp/config", "editar"), _r("GET", "/api/erp/backup", "ver"), _r("POST", "/api/erp/zerar", "excluir"),
                _r("POST", "/api/erp/exemplo", "incluir")]},
        },
    },
    "wlogistica": {
        "prefixos": ["/api/wlog"],
        "comum": [_r("GET", "/api/wlog/estado", ACESSO), _r("GET", "/api/wlog/cargas/*", ACESSO)],
        "abas": {
            "painel": {"rotulo": "Painel", "campos": {}, "rotas": []},
            "montagem": {"rotulo": "Montagem", "campos": {}, "rotas": [
                _r("POST", "/api/wlog/cargas/*/montagem/leitura", "incluir"), _r("POST", "/api/wlog/cargas/*/montagem/desfazer", "excluir"),
                _r("POST", "/api/wlog/cargas/*/montagem/finalizar", "editar")]},
            "doca": {"rotulo": "Conferência na doca", "campos": {}, "rotas": [
                _r("POST", "/api/wlog/cargas/*/doca/leitura", "incluir"), _r("POST", "/api/wlog/cargas/*/doca/desfazer", "excluir"),
                _r("POST", "/api/wlog/cargas/*/doca/finalizar", "editar")]},
            "retorno": {"rotulo": "Retorno", "campos": {}, "rotas": [_r("POST", "/api/wlog/cargas/*/retorno/*", "editar")]},
            "apontamentos": {"rotulo": "Apontamentos", "campos": {}, "rotas": [
                _r("POST", "/api/wlog/cargas/*/refazer/*", "excluir"), _r("POST", "/api/wlog/cargas/*/ajuste/*/feito", "editar"),
                _r("POST", "/api/wlog/cargas/*/ajuste", "incluir"), _r("PUT", "/api/wlog/cargas/*/pendencias/*", "editar"),
                _r("POST", "/api/wlog/cargas/*/*/leitura", "incluir"), _r("POST", "/api/wlog/cargas/*/*/desfazer", "excluir"),
                _r("POST", "/api/wlog/cargas/*/*/finalizar", "editar")]},
            "ajustes": {"rotulo": "Ajustes", "campos": {}, "rotas": [_r("PUT", "/api/wlog/config", "editar")]},
        },
    },
    "wrouter": {
        "prefixos": ["/api/wrouter"],
        "publico": ["/api/wrouter/app/*"],   # app do motorista: sessão própria (placa + senha), fora das pessoas do hub
        "comum": [_r("GET", "/api/wrouter/eu", ACESSO)],
        "abas": {
            "aovivo": {"rotulo": "Ao vivo", "campos": {}, "rotas": [
                _r("GET", "/api/wrouter/ao-vivo", "ver"), _r("GET", "/api/wrouter/links", "ver"), _r("GET", "/api/wrouter/foto/*", "ver")]},
            "conversas": {"rotulo": "Conversas e tratativas", "campos": {}, "rotas": [
                _r("GET", "/api/wrouter/cargas/*/pedido/*", "ver"), _r("POST", "/api/wrouter/cargas/*/pedido/*/reabrir", "excluir"),
                _r("POST", "/api/wrouter/cargas/*/pedido/*/*", "incluir"), _r("PUT", "/api/wrouter/cargas/*", "editar")]},
            "historico": {"rotulo": "Histórico de entregas", "campos": {}, "rotas": [_r("GET", "/api/wrouter/historico", "ver")]},
            "motoristas": {"rotulo": "Motoristas e app", "campos": {}, "rotas": [
                _r("GET", "/api/wrouter/motoristas", "ver"), _r("POST", "/api/wrouter/cadastros", "incluir"), _r("PUT", "/api/wrouter/cadastros/*", "editar"),
                _r("PUT", "/api/wrouter/motoristas/*", "editar"), _r("POST", "/api/wrouter/placas/*/resetar", "editar"), _r("PUT", "/api/wrouter/cfg", "editar")]},
        },
    },
    "tickets": {
        "prefixos": ["/api/tickets", "/api/promo"],
        "comum": [_r("GET", "/api/tickets/estado", ACESSO), _r("POST", "/api/tickets/recarregar", ACESSO), _r("GET", "/api/tickets/equipe", ACESSO)],
        "abas": {
            "meudia": {"rotulo": "Meu dia", "campos": {}, "rotas": [_r("POST", "/api/tickets/proximo", "editar")]},
            "caixa": {"rotulo": "Caixa e atendimento", "campos": {}, "rotas": [
                _r("GET", "/api/tickets/ticket/*", "ver"), _r("POST", "/api/tickets/ticket/*", "editar"), _r("POST", "/api/tickets/lote", "editar"),
                _r("GET", "/api/tickets/conversa/*", "ver"), _r("POST", "/api/tickets/conversa*", "incluir"),
                _r("GET", "/api/tickets/cliente/*", "ver"), _r("POST", "/api/tickets/cliente/*", "editar"),
                _r("GET", "/api/tickets/erp/*", "ver"), _r("POST", "/api/tickets/erp/pedido/*/abrir", "incluir"), _r("POST", "/api/tickets/erp/*", "editar"),
                _r("GET", "/api/tickets/app/palavras", "ver"), _r("POST", "/api/tickets/app/*", "editar")]},
            "abrir": {"rotulo": "Abrir chamado", "campos": {}, "rotas": [_r("POST", "/api/tickets/tickets", "incluir")]},
            "internos": {"rotulo": "Pedidos de ajuda", "campos": {}, "rotas": [_r("GET", "/api/tickets/ajuda", "ver"), _r("POST", "/api/tickets/ajuda/*", "incluir")]},
            "gestao": {"rotulo": "Gestão", "campos": {}, "rotas": []},
            "promocoes": {"rotulo": "Disparos e vales (app do cliente)", "campos": {}, "rotas": [
                _r("POST", "/api/promo/publico", "ver"), _r("GET", "/api/promo/*", "ver"), _r("POST", "/api/promo/disparos/*/cancelar", "excluir"),
                _r("POST", "/api/promo/disparos/*/aprovar", "editar"), _r("POST", "/api/promo/disparos", "incluir"), _r("POST", "/api/promo/vale/*/usar", "editar")]},
            "ajustes": {"rotulo": "Ajustes", "campos": {}, "rotas": [_r("PUT", "/api/tickets/config*", "editar")]},
        },
    },
    "lila-closet": {
        "prefixos": ["/api/atelier"],
        "comum": [_r("GET", "/api/atelier/estado", ACESSO), _r("POST", "/api/atelier/recarregar", ACESSO), _r("GET", "/api/atelier/ocupacao", ACESSO)],
        "abas": {
            "pedidos": {"rotulo": "Pedidos e agenda", "telas": ["pedidos", "agenda"], "campos": {}, "rotas": [
                _r("GET", "/api/atelier/encomendas/*", "ver"), _r("POST", "/api/atelier/encomendas/*/*", "editar"),
                _r("*", "/api/atelier/encomendas*"), _r("POST", "/api/atelier/consertos", "incluir")]},
            "clientes": {"rotulo": "Clientes & medidas", "campos": {}, "rotas": [_r("*", "/api/atelier/clientes*")]},
            "prospects": {"rotulo": "Prospects", "campos": {}, "rotas": [_r("*", "/api/atelier/prospects*")]},
            "hoje": {"rotulo": "Hoje (tarefas e vida pessoal)", "campos": {}, "rotas": [
                _r("POST", "/api/atelier/tarefas/*/feito", "editar"), _r("*", "/api/atelier/tarefas*"), _r("*", "/api/atelier/campo*"),
                _r("POST", "/api/atelier/peso", "incluir")]},
            "financeiro": {"rotulo": "Financeiro", "campos": {}, "rotas": [
                _r("GET", "/api/atelier/financeiro"), _r("*", "/api/atelier/recebimentos*"), _r("*", "/api/atelier/gastos*"),
                _r("POST", "/api/atelier/fechamento/*/reabrir", "excluir"), _r("POST", "/api/atelier/fechamento/*/fechar", "editar"),
                _r("GET", "/api/atelier/fechamento/*")]},
            "ajustes": {"rotulo": "Ajustes", "campos": {}, "rotas": [_r("PUT", "/api/atelier/config", "editar")]},
        },
    },
    "lila": {
        "prefixos": ["/api/dados/lila"],
        "abas": {
            "tarefas": {"rotulo": "Tarefas", "campos": {
                "titulo": "Título", "notas": "Detalhes", "prioridade": "Prioridade", "status": "Status", "prazo": "Prazo", "hora": "Hora",
                "lembrete": "Lembrete", "lista": "Lista", "quem": "Responsável", "recorrencia": "Repetição", "subtarefas": "Subtarefas",
                "andamento": "Andamento"}, "rotas": [_r("*", "/api/dados/lila/*")]},
        },
    },
    "weduca": {
        "prefixos": ["/api/weduca"],
        "comum": [_r("GET", "/api/weduca/me", ACESSO), _r("GET", "/api/weduca/novidades", ACESSO), _r("GET", "/api/weduca/notificacoes", ACESSO),
                  _r("POST", "/api/weduca/notificacoes/lidas", ACESSO), _r("GET", "/api/weduca/arquivos/*", ACESSO), _r("POST", "/api/weduca/arquivos", ACESSO),
                  _r("GET", "/api/weduca/perfis*", ACESSO), _r("PUT", "/api/weduca/perfil", ACESSO), _r("POST", "/api/weduca/perfis/*/seguir", ACESSO)],
        "abas": {
            "feed": {"rotulo": "Feed", "campos": {}, "rotas": [
                _r("GET", "/api/weduca/feed"), _r("GET", "/api/weduca/destaques"), _r("GET", "/api/weduca/posts/*"),
                _r("POST", "/api/weduca/posts/*/curtir", "ver"), _r("POST", "/api/weduca/posts/*/salvar", "ver"), _r("POST", "/api/weduca/comentarios/*/curtir", "ver"),
                _r("POST", "/api/weduca/posts/*/comentarios", "incluir"), _r("POST", "/api/weduca/posts/*/*", "editar"), _r("*", "/api/weduca/posts*"),
                _r("DELETE", "/api/weduca/comentarios/*", "excluir"),
                _r("GET", "/api/weduca/stories*", "ver"), _r("POST", "/api/weduca/stories/*/visto", "ver"), _r("*", "/api/weduca/stories*")]},
            "aprendizagem": {"rotulo": "Aprendizagem", "campos": {}, "rotas": [
                _r("POST", "/api/weduca/aulas/*/concluir", "ver"), _r("POST", "/api/weduca/aulas/*/visto", "ver"), _r("POST", "/api/weduca/cursos/*/avaliacao", "ver"),
                _r("POST", "/api/weduca/aulas/*/duvidas", "ver"), _r("POST", "/api/weduca/cursos/*/ordem", "editar"), _r("POST", "/api/weduca/cursos/*/aulas", "incluir"),
                _r("*", "/api/weduca/cursos*"), _r("*", "/api/weduca/aulas*"), _r("GET", "/api/weduca/certificados"), _r("GET", "/api/weduca/ranking")]},
            "direct": {"rotulo": "Mensagens", "campos": {}, "rotas": [
                _r("GET", "/api/weduca/direct*"), _r("POST", "/api/weduca/direct*", "incluir")]},
        },
    },
    "agente": {
        "prefixos": ["/api/agente"],
        "comum": [_r("GET", "/api/agente/me", ACESSO)],
        "abas": {
            "perguntar": {"rotulo": "Perguntar ao agente", "campos": {}, "rotas": [
                _r("POST", "/api/agente/perguntar", "ver"), _r("POST", "/api/agente/retorno", "ver")]},
            "base": {"rotulo": "Base de conhecimento (artigos)", "campos": {}, "rotas": [
                _r("POST", "/api/agente/artigos/*/restaurar", "editar"), _r("*", "/api/agente/artigos*"), _r("POST", "/api/agente/ajustar", "editar"),
                _r("POST", "/api/agente/ia-teste", "ver")]},
            "pendencias": {"rotulo": "Pendências e painel", "campos": {}, "rotas": [
                _r("GET", "/api/agente/*", "ver"), _r("POST", "/api/agente/pendencias/*/descartar", "excluir"), _r("POST", "/api/agente/pendencias/*", "editar")]},
        },
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# CONSULTAS
# ══════════════════════════════════════════════════════════════════════════════
def abas_do(slug: str) -> dict:
    """{aba: {rotulo, campos}} para a tela de Configurações."""
    m = ABAS.get(slug) or {}
    return {a: {"rotulo": d["rotulo"], "campos": dict(d.get("campos") or {})} for a, d in (m.get("abas") or {}).items()}


def campos_do(slug: str) -> dict:
    out = {}
    for d in ((ABAS.get(slug) or {}).get("abas") or {}).values():
        out.update(d.get("campos") or {})
    return out


def _casa(metodo: str, caminho: str, regra: tuple) -> bool:
    m, padrao, _ = regra
    return (m == "*" or m == metodo) and fnmatchcase(caminho, padrao)


def localizar(metodo: str, caminho: str) -> tuple | None:
    """(slug, aba|None, nível exigido, regra_por_chave|None) da rota; None se a rota não é de módulo governado."""
    metodo = metodo.upper()
    for slug, m in ABAS.items():
        if not any(caminho == p or caminho.startswith(p + "/") for p in m["prefixos"]):
            continue
        if any(fnmatchcase(caminho, p) for p in m.get("publico", [])):
            return None
        for (mt, pad), mapa in (m.get("por_chave") or {}).items():
            if mt == metodo and fnmatchcase(caminho, pad):
                return (slug, None, "editar", mapa)
        for r in m.get("comum", []):
            if _casa(metodo, caminho, r):
                return (slug, None, ACESSO, None)
        for aba, d in m["abas"].items():
            for r in d.get("rotas", []):
                if _casa(metodo, caminho, r):
                    nivel = _POR_METODO.get(metodo, "editar") if r[2] == "auto" else r[2]
                    return (slug, aba, nivel, None)
        return (slug, "?", "excluir", None)   # rota de módulo SEM mapa: só admin (o teste também acusa)
    return None


def nivel_ok(tem: str, precisa: str, escala=NIVEIS_ABA) -> bool:
    return escala.index(tem if tem in escala else escala[0]) >= escala.index(precisa)


def checar(u: dict | None, metodo: str, caminho: str, corpo: dict | None, perm_de) -> str | None:
    """Mensagem de bloqueio (403) ou None. perm_de(slug) → permissões efetivas do usuário (acesso.permissoes)."""
    if not u or u.get("admin") or u.get("super") or u.get("fabrica"):
        return None
    achado = localizar(metodo, caminho)
    if not achado:
        return None
    slug, aba, precisa, por_chave = achado
    p = perm_de(slug)
    if p is None:
        return None
    if not p["acoes"].get("acessar"):
        return None   # a própria rota responde "sem acesso ao módulo" (mensagem de sempre)
    abas, rot = p.get("abas") or {}, abas_do(slug)
    if precisa == ACESSO:
        return None if any(v != "nenhum" for v in abas.values()) or not abas else "Sem permissão: nenhuma aba deste módulo liberada para você."
    alvos = [aba]
    if por_chave is not None:
        alvos = sorted({por_chave.get(k, por_chave["_padrao"]) for k in (corpo or {})}) or [por_chave["_padrao"]]
    for a in alvos:
        if a == "?":
            return "Sem permissão: esta função ainda não tem regra de acesso (só administradores)."
        tem = abas.get(a, "excluir")
        if not nivel_ok(tem, precisa):
            return (f"Sem permissão em “{(rot.get(a) or {}).get('rotulo', a)}”: precisa de "
                    f"{ROTULO_ABA[precisa]}, você tem {ROTULO_ABA.get(tem, tem)}.")
    return None


# ── campos: gravar só o que pode ──────────────────────────────────────────────
def _vazio(v) -> bool:
    return v is None or v is False or (isinstance(v, (str, list, dict, tuple)) and not (v.strip() if isinstance(v, str) else v))


def _igual(a, b) -> bool:
    if _vazio(a) and _vazio(b):
        return True
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return sorted(map(str, a)) == sorted(map(str, b))
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


def aplicar_campos(p: dict, slug: str, antigo: dict | None, novo: dict) -> dict:
    """Confere a gravação campo a campo. Igual ao que já está: passa. Mudou campo Oculto/Ver: 403.
    Apagou (deixou vazio) campo que é só Editar: 403. Excluir: tudo pode."""
    from fastapi import HTTPException
    niveis, rot, antigo = p.get("campos_nivel") or {}, campos_do(slug), antigo or {}
    for campo, valor in list(novo.items()):
        if campo not in rot:
            continue
        velho = antigo.get(campo)
        if _igual(valor, velho):
            continue
        nv = niveis.get(campo, "excluir")
        if nv in ("oculto", "ver"):
            raise HTTPException(403, f"Sem permissão para alterar “{rot[campo]}” (você só pode ver).")
        if nv == "editar" and _vazio(valor) and not _vazio(velho):
            raise HTTPException(403, f"Sem permissão para apagar “{rot[campo]}” (você pode editar, mas não excluir).")
    return novo


def estilo_abas_ocultas(p: dict | None, slug: str = "") -> str:
    """CSS + script que a página do módulo recebe: some com as abas Sem acesso e leva para a primeira liberada."""
    if not p:
        return ""
    defs = (ABAS.get(slug) or {}).get("abas") or {}
    fechadas = [t for a, v in (p.get("abas") or {}).items() if v == "nenhum" for t in (defs.get(a, {}).get("telas") or [a])]
    sel = ",".join(f'[data-sec="{a}"],[data-aba="{a}"],[data-gov-aba="{a}"]' for a in fechadas)
    import json as _j
    js = ("<script>window.HUB_GOV=" + _j.dumps({"abas": p.get("abas") or {}, "campos": p.get("campos_nivel") or {}}) + ";"
          "(function(){var f=" + _j.dumps(fechadas) + ";if(!f.length)return;function ir(){document.querySelectorAll('.ativo[data-sec],.ativo[data-aba]')"
          ".forEach(function(b){var k=b.dataset.sec||b.dataset.aba;if(f.indexOf(k)<0)return;var p=b.parentElement;if(!p)return;"
          "var o=[].slice.call(p.querySelectorAll('[data-sec],[data-aba]')).find(function(x){return f.indexOf(x.dataset.sec||x.dataset.aba)<0});if(o)o.click();});}"
          "new MutationObserver(function(){clearTimeout(window.__govT);window.__govT=setTimeout(ir,30);}).observe(document.documentElement,{childList:true,subtree:true});})();</script>")
    css = f"<style>{sel}{{display:none!important}}</style>" if sel else ""
    return css + js
