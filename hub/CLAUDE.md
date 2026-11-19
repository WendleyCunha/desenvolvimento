# Regras do hub (wendleyservice)

## Governança de acesso — vale para TODO módulo e TODA função nova
- Permissão é por **módulo → aba → campo**, configurada em Configurações → Usuários (Personalizado) e Permissões.
  - Aba: `nenhum` · `ver` · `incluir` · `editar` · `excluir` (cada nível inclui os anteriores).
  - Campo: `oculto` · `ver` · `editar` (altera sem apagar) · `excluir` (pode apagar o valor).
- **Toda rota nova de módulo precisa entrar em `hub/governanca.py` (ABAS)** com a aba e o nível.
  O teste `tests/test_governanca.py::test_toda_rota_de_modulo_tem_aba_e_nivel` falha se faltar.
- **Todo campo editável novo** entra na aba dele (`campos`) e a gravação passa por `governanca.aplicar_campos(...)`.
- Módulo novo: declare as abas em `governanca.ABAS` com os mesmos ids usados nos botões de aba da tela
  (`data-sec` ou `data-aba`) — assim a aba "Sem acesso" some sozinha.
- Na tela, use `Aurora.permissoes.aba(a)` / `podeNaAba(a, nivel)` / `nivelCampo(c)` (ou `S.b.perm.abas` / `campos_nivel`).
- Quem não foi configurado continua como antes (aba e campo = Excluir); as ações antigas continuam valendo junto.
