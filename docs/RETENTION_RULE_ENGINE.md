# Motor de regras da régua de retenção

O motor em `backend/app/agents/rule_engine.py` é puro: valida e avalia JSON sem acessar banco, ORM ou canais de envio. As campanhas e versões são persistidas por tenant em `retention_campaigns`.

## Regras

- Campos permitidos: `risk_level`, `risk_score`, `days_since_contact`, `opt_out`, `has_phone` e `has_email`.
- Operadores: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in` e `not_in`.
- `conditions.all`: todas precisam passar; `conditions.any`: ao menos uma precisa passar. Se ambos existem, os dois grupos devem passar.
- Campos ausentes nunca satisfazem condições, inclusive `neq`.
- A ação exige um canal suportado e `template_id`; a execução não deve presumir que esse identificador foi entregue ao provider.
- IDs de regra duplicados são rejeitados dentro do conjunto. Use novas versões em vez de sobrescrever regras publicadas.

## Campanhas e endpoints

As rotas têm prefixo `/api/v1/agents/retention/campaigns` e são isoladas por tenant.

- `POST /`: cria uma campanha na versão 1 em estado `draft`.
- `GET /`: lista campanhas; `?status=draft|active|paused` filtra pelo estado.
- `GET /{campaign_id}`: consulta uma versão da campanha.
- `POST /{campaign_id}/versions`: cria a próxima versão imutável em estado `draft`.
- `PATCH /{campaign_id}/status`: ativa, pausa ou devolve uma versão a `draft`.
- `POST /{campaign_id}/simulate`: avalia regras e devolve as decisões, sem envio.
- `POST /{campaign_id}/run-dry-run`: passa decisões elegíveis pelo orquestrador em modo dry-run; nenhuma mensagem real é enviada.

## Salvaguardas da etapa 3.1

- A avaliação falha de forma segura: nível de risco deve ser `baixo`, `medio` ou `critico`, e score deve ser numérico, finito e estar entre 0 e 100. Dados de risco ausentes ou inválidos bloqueiam a elegibilidade, com `blocked_reason=missing_risk_data`.
- Opt-out bloqueia a campanha; ausência de telefone e e-mail também bloqueia ação de contato.
- Ativar uma versão pausa as outras versões ativas com o mesmo `tenant_id` e `slug` na mesma transação.
- Um índice único parcial no PostgreSQL impede duas versões ativas, inclusive em ativações concorrentes. A migração normaliza dados antigos mantendo ativa a versão mais alta antes de criar o índice.
- As versões continuam escopadas por tenant. A idempotência e o dry-run do orquestrador permanecem obrigatórios para a execução segura.

## Escopo

Esta etapa não habilita envios reais nem altera as credenciais dos providers. O envio real depende de uma etapa futura com prioridades de regras, templates efetivos, limites operacionais e testes dedicados.
