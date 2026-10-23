# Motor de regras da régua de retenção

O motor em `backend/app/agents/rule_engine.py` é puro: valida e avalia JSON sem acessar banco, ORM ou canais de envio. As campanhas e versões são persistidas por tenant em `retention_campaigns`.

## Regras

- Campos permitidos: `risk_level`, `risk_score`, `days_since_contact`, `opt_out`, `has_phone` e `has_email`.
- Operadores: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in` e `not_in`.
- `conditions.all`: todas precisam passar; `conditions.any`: ao menos uma precisa passar. Se ambos existem, os dois grupos devem passar.
- Campos ausentes nunca satisfazem condições, inclusive `neq`.
- Cada regra aceita `priority` como inteiro >= 0; se omitida, usa 100 para compatibilidade. Prioridade maior é avaliada primeiro; empates são resolvidos por `id` em ordem lexicográfica.
- A decisão executável usa somente a primeira regra correspondente nesta ordem. As demais regras continuam registradas na avaliação com status de correspondência e marcação da escolhida.
- O par `(channel, template_id)` precisa existir no registry de templates implementados. IDs desconhecidos e combinações de canal/template inválidas são rejeitados ao criar/ativar a campanha.
- IDs atuais: `retention_v1` para os três canais; `critico_v1`, `whatsapp_critical_v1` e `whatsapp_default_v1`; `score_alto_v1`, `email_critical_v1` e `email_default_v1`; `sms_default_v1`.
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

## Execução previsível — etapa 3.2

- O canal da ação vencedora é o único canal tentado para aquele aluno; a execução não volta para a heurística geral nem faz fallback para outro canal.
- O `template_id` é resolvido por um registry allowlist. Corpo e, no e-mail, assunto são renderizados pelo template registrado; o ID efetivamente usado é persistido em `intervention_logs.template_id`.
- Simulação e dry-run retornam `selected_rule` e `rule_evaluations` por aluno. O log salva campanha/versão, prioridade, regra escolhida, avaliação ordenada, canal, template e assunto efetivo do e-mail.
- A execução usa uma ação selecionada por aluno, idempotência estável e as proteções existentes de opt-out e anti-spam.

## Escopo

Os envios reais continuam desabilitados no endpoint de campanhas. Novos templates precisam ser implementados e incluídos no registry antes de poderem ser selecionados.
