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

## Planejamento de cargas (ERP › Cargas) — etapa 5
- **Pedidos para carga**: por padrão os agendados para amanhã; filtros de data, janela, bairro/cidade/CEP/cliente e "incluir sem agenda" (confirmados ou reagendar com estoque reservado).
- **Puxar**: pôr na carga um pedido de outro dia ou sem agenda muda a agenda para a data da carga e grava no histórico ("Entrega antecipada de 20/11 para 18/11 (carga 43)"), o que chega ao ticket e ao app do cliente. Mudar a data da carga leva a agenda dos pedidos junto.
- **Sugerir cargas** (`cargas_plano.py`): a entrega mais urgente é a semente; a carga cresce pelo pedido mais próximo que ainda cabe em paradas · volumes · m³ · kg · raio (km). Limite do veículo > padrão de Ajustes; 0 = não usa. Ordem: do CD, vizinho mais próximo + 2-opt; com janela, manhã → sem janela → tarde. Nada grava até "Criar cargas".
- **Medidas**: cubagem (m³) e peso (kg) por unidade no cadastro do produto; limites de paradas/m³/kg no cadastro do veículo.
- **Localização**: OpenStreetMap/BrasilAPI (grátis), em segundo plano, guardada no pedido (`ped.geo`), refeita se o endereço mudar. O WROUTER reaproveita.
- **Faturamento**: botão Faturar na carga (nº da NF por pedido; a NF-e continua no sistema fiscal). Com "Exigir faturamento" ligado em Ajustes, a carga só sai e só aparece no app do motorista quando todos os pedidos têm NF.
- Permissões novas no ERP: "Sugerir cargas" (planejar) e "Faturar cargas" (faturar).

## NF simplificada e comprovante de entrega
- **ERP › Cargas › Faturar → Importar o PDF das NF-e**: o hub lê o DANFE completo (todas as notas num PDF só), confere a chave de acesso (dígito verificador) e liga cada nota ao pedido da carga (chave → nº da NF → "Pedido de venda" + CPF/CNPJ → CPF/CNPJ → nome). Conta como faturado.
- **Etiquetas NF** (ERP › Cargas e WLOGISTICA › montagem): um PDF com o DANFE Simplificado – Etiqueta (100 × 150 mm, térmica) de cada pedido, na ordem das paradas. A palavra-chave nunca vai na etiqueta. O motorista abre a NF simplificada no app.
- **Comprovante de entrega** (app do motorista, Entregue/Parcial): palavra-chave + nome de quem recebeu + parentesco + final do documento + assinatura na tela + foto com marca d'água + GPS/distância, selados com SHA-256 (`entrega_prova.py`). O resumo fica no pedido (`ped.entrega`): ERP, CX e app do cliente mostram e baixam o PDF; o cliente recebe notificação no app.
- A palavra só é exigida para o motorista com a chave ligada em WROUTER › Motoristas e app (o comprovante registra "não exigida" quando não está).
