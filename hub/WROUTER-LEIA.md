# Fluxo completo de entrega no wendleyservice (sem PQI)

ERP → WLOGISTICA → WROUTER → cliente. Tudo no mesmo banco, sem Excel e sem PDF importado.

1. **ERP · venda**: o pedido nasce com a **palavra-chave** e já aparece no app do cliente (`/cliente/`) e no Atendimento. **PDF do pedido** no ERP, no ticket e no app.
2. **ERP · agenda e carga**: pedido agendado entra numa carga (veículo + motorista do cadastro do ERP).
3. **WLOGISTICA** (`/m/wlogistica`): montagem do palete (1ª conferência) → conferência na doca por **outra** pessoa (2ª) → **liberada**. Divergência vira apontamento. Ajuste na carga trava a etapa até "Ajuste feito no palete".
4. **WROUTER · app do motorista** (`/motorista/`): login pela **placa** + senha (inicial `Rota@2026` ou `WROUTER_SENHA_INICIAL`). Iniciar rota = saída no ERP. Entregue / Parcial / Retorno = **baixa automática no ERP**.
5. **Cliente**: link `/entrega/<código>` (um por cliente + CEP) e o app do cliente mostram a palavra, a situação e o **km** (laranja < 7 km, vermelho < 2 km). "Entregar ao vizinho": o nome vira a palavra; sem nome = sem palavra.
6. **WLOGISTICA · retorno**: o que voltou (ausente, avaria, recusa, recolha da troca) é recebido no CD peça por peça.

Painel do WROUTER (`/m/wrouter`): Ao vivo, Conversas, Histórico (PDF do caso), Motoristas e app.

Permissões em Configurações → Usuários: **WLOGISTICA** (montagem, doca, retorno, apontamentos, configurar) e **WROUTER** (ao vivo, tratar, histórico, motoristas).

Render (opcional): `WROUTER_SENHA_INICIAL`, `HUB_URL_PUBLICA` (endereço público para os links), `WROUTER_GEO=0` desliga a busca de coordenadas (OpenStreetMap/BrasilAPI, grátis).

Testes: `pytest tests` (test_pedido_pdf, test_wlogistica, test_wrouter).
