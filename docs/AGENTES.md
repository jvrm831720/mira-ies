# Sistema Multiagente de Retenção

Arquitetura: **Motor Preditivo → Agente Orquestrador → WhatsApp | E-mail | SMS**

O Orquestrador busca alunos elegíveis de um tenant (sempre isolado por `tenant_id`), decide o
canal de contato, aplica uma régua anti-spam, delega a um dos 3 agentes de canal e registra
tudo em `intervention_logs`. Por padrão, roda em **modo dry-run**: nenhuma mensagem real é
enviada — tudo é simulado e logado, para demo e validação sem depender de WhatsApp/e-mail/SMS
de verdade.

## Arquitetura

```
backend/app/agents/
  base.py              # SendResult, MessageContext, protocolo ChannelAgent
  orchestrator.py       # RetentionOrchestrator + preview_message
  rules.py              # decide_channels() e check_anti_spam() — logica pura, testavel sem DB
  templates.py          # mensagens PT-BR por canal/risco, com fallback para dados ausentes
  channels/
    whatsapp.py          # normaliza telefone BR, delega a dry_run ou evolution
    email.py             # valida e-mail, delega a dry_run ou resend
    sms.py                # trunca a 160 chars, delega a dry_run ou twilio
  providers/
    dry_run.py            # provider padrao: loga e simula sucesso
    evolution.py           # WhatsApp real (Evolution API) — so ativa com EVOLUTION_API_URL
    resend_provider.py     # E-mail real (Resend) — so ativa com RESEND_API_KEY
    twilio_provider.py     # SMS real (Twilio) — so ativa com as 3 credenciais Twilio
backend/app/services/
  delivery_webhooks.py     # normaliza eventos de entrega e descadastro
  provider_guard.py        # rate limit Redis + circuit breaker fail-closed
```

Orquestrador procedural (sem LangGraph) por decisão pragmática: o fluxo é simples o bastante
(`fetch_eligible → decide_channel → render → send → log`) que uma dependência nova e mais
superfície de CI não se justificavam no MVP. A interface de `RetentionOrchestrator.run()` é
estável o suficiente para trocar a implementação interna por um grafo LangGraph depois, sem
mudar a API.

## Decisão de canal

`risk_level == "baixo"` nunca dispara.

Para `critico`/`medio`, `decide_channels()` retorna uma **lista ordenada de canais candidatos**
(não um único canal): o orquestrador tenta cada um até o primeiro envio bem-sucedido. Isso
cobre tanto "não tem telefone" quanto "WhatsApp falhou no envio, tenta o próximo":

- **crítico**: `whatsapp` (se tiver telefone) → `email` (se tiver e-mail) → `sms` (se tiver telefone)
- **médio**: `email` por padrão; com `prefer_whatsapp_medio=true`, tenta `whatsapp` primeiro

Se nenhum canal for viável (sem telefone nem e-mail), o aluno é pulado com
`skip_reason="missing_contact"`.

Se `Student.communication_opt_out=true`, nenhum canal é consultado ou enviado. O
orquestrador grava um `InterventionLog` com `status="skipped"` e
`skip_reason="communication_opt_out"`, permitindo auditoria sem gerar contato. A preferência
pode ser importada por CSV/XLSX ou conector genérico e alterada pela API tenant-scoped:
`PATCH /api/v1/students/{student_id}/communication-preferences` com
`{"opt_out": true|false}`.

## Anti-spam

Duas regras independentes (configuráveis via env, ver abaixo):

- **Por canal**: não recontatar o mesmo aluno no mesmo canal em menos de
  `AGENTS_MIN_HOURS_BETWEEN_CONTACT` horas (default 48h). Só bloqueia aquele canal — o
  orquestrador ainda tenta o próximo candidato.
- **Por aluno**: no máximo `AGENTS_MAX_CONTACTS_PER_WEEK` mensagens (qualquer canal) por
  aluno a cada 7 dias (default 3).

Só contam para as duas regras envios com status `sent` ou `dry_run` (tentativas que falharam
ou foram puladas não contam).

## Modelo de dados

`InterventionLog` (`backend/app/models/intervention.py`, tabela `intervention_logs`):

| Campo | Observação |
|---|---|
| `tenant_id`, `student_id`, `matricula` | sempre vinculado ao tenant — nunca cross-tenant |
| `channel` | `whatsapp\|email\|sms`, ou `null` quando nenhum canal era viável |
| `status` | `planned\|sending\|sent\|dry_run\|unknown\|failed\|skipped` |
| `message_preview` | **até 120 caracteres**, nunca o corpo completo (evita logar PII desnecessário) |
| `skip_reason` / `error` | motivo do skip (anti-spam, missing_contact, risco baixo) ou erro de envio |
| `correlation_id` / `idempotency_key` | correlação e chave única por mensagem, isoladas por tenant |
| `job_id` / `campaign_id` | origem assíncrona e campanha lógica da intervenção |
| `delivery_status` | `queued\|submitted\|delivered\|read\|failed\|rejected\|bounced\|unknown` |
| `delivery_event_id` / `delivery_updated_at` | deduplicação e auditoria do último callback |

`Student` ganhou telefone/e-mail e a preferência global de comunicação:
`communication_opt_out` (boolean) e `communication_opted_out_at` (timestamp). A preferência
é global para WhatsApp, e-mail e SMS e pode ser revogada pela mesma API.
Aceitos via upload CSV/XLSX (aliases: `telefone`, `celular`, `whatsapp`, `phone`, `contato` /
`email`, `e_mail`, `opt_out`, `optout`, `nao_contatar`, `do_not_contact`) e via conector genérico
(`POST /api/v1/ingest/students`). Os conectores ERP/LMS específicos também mapeiam os campos
nativos de telefone/e-mail para o schema canônico.

Migrações: `backend/alembic/versions/002_agents_and_contact_fields.py`,
`backend/alembic/versions/005_student_communication_opt_out.py` e
`backend/alembic/versions/006_safe_agent_delivery.py`.

## Configuração (`.env`)

Tudo tem default seguro — nenhuma credencial é obrigatória para rodar em dry-run.

```bash
AGENTS_DRY_RUN_DEFAULT=true        # false em producao quando os providers reais estiverem prontos
AGENTS_MIN_HOURS_BETWEEN_CONTACT=48
AGENTS_MAX_CONTACTS_PER_WEEK=3
AGENTS_PROVIDER_TIMEOUT_SECONDS=15
AGENTS_RATE_LIMIT_ENABLED=true
AGENTS_RATE_LIMIT_PER_TENANT_PER_MINUTE=60
AGENTS_RATE_LIMIT_PER_CHANNEL_PER_MINUTE=60
AGENTS_RATE_LIMIT_PER_PROVIDER_PER_MINUTE=120
AGENTS_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
AGENTS_CIRCUIT_BREAKER_OPEN_SECONDS=60

# WhatsApp real (opcional — sem isso, cai em dry-run automaticamente)
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=

# E-mail real (opcional)
RESEND_API_KEY=
EMAIL_FROM=

# SMS real (opcional)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM=
```

`GET /api/v1/agents/status` mostra qual provider está ativo por canal (`dry_run` ou o real),
sem expor as credenciais.

Cada execução aceita `Idempotency-Key`. O orquestrador gera uma chave determinística por
aluno/canal, grava a reserva em `sending` antes da chamada externa e propaga a chave aos
providers. Timeout, erro de transporte, resposta 5xx ou resposta malformada ficam como
`unknown`: não há fallback imediato para outro canal e o envio pode ser reconciliado por
webhook, evitando duplicidade.

## API

As rotas operacionais exigem `X-API-Key` (`Depends(get_current_tenant)`) e são isoladas por
tenant. Os callbacks de provider não usam API key: usam `X-Beacon-Signature` e `tenant_id`
na URL, com o `webhook_secret` do tenant.

### `POST /api/v1/agents/retention/run`

```bash
curl -X POST http://localhost:8000/api/v1/agents/retention/run \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{
    "risk_levels": ["critico"],
    "limit": 50,
    "dry_run": true,
    "channels": ["whatsapp", "email", "sms"]
  }'
```

```json
{
  "tenant_id": "...",
  "dry_run": true,
  "students_evaluated": 1,
  "by_channel": { "whatsapp": { "sent": 0, "dry_run": 1, "skipped": 0, "failed": 0 } },
  "totals": { "sent": 0, "dry_run": 1, "skipped": 0, "failed": 0 }
}
```

### `GET /api/v1/agents/retention/logs?limit=50&channel=whatsapp&status=dry_run`

Lista o histórico de intervenções do tenant (mais recentes primeiro).

### Fila assíncrona

Para execuções maiores, use `POST /api/v1/agents/retention/enqueue`. A rota retorna `202` e
um `job_id`; o tenant pode consultar `GET /api/v1/agents/retention/jobs/{job_id}`. Envie
`Idempotency-Key` para que uma repetição da mesma requisição retorne o mesmo job, sem criar
uma segunda execução.

```bash
curl -X POST http://localhost:8000/api/v1/agents/retention/enqueue \
  -H "X-API-Key: $API_KEY" -H "Idempotency-Key: rodada-2026-10-21" \
  -H "Content-Type: application/json" \
  -d '{"risk_levels":["critico"],"limit":50,"dry_run":true}'
```

O worker consome Redis, abre uma sessão de banco por job e tenta novamente falhas com backoff
exponencial. Os defaults são 3 tentativas e atrasos de 5s, 10s e 20s; o estado fica disponível
por 24 horas. Após esgotar as tentativas, o job é enviado para a fila
`RETENTION_DEAD_LETTER_QUEUE_NAME` e fica consultável em
`GET /api/v1/agents/retention/dead-letter`. Execute a partir de `backend`:

```bash
PYTHONPATH=. python -m app.worker
```

### `GET /api/v1/agents/retention/preview/{student_id}`

Monta a mensagem do canal prioritário **sem enviar nem gravar log** — útil para a coordenação
revisar o texto antes de rodar de verdade.

```bash
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/api/v1/agents/retention/preview/<student_id>
```

### `GET /api/v1/agents/status`

Mostra config de anti-spam e qual provider está ativo por canal.

### Webhooks de entrega

Cada provider pode chamar `POST /api/v1/agents/webhooks/{provider}/{tenant_id}` com JSON
assinado por `X-Beacon-Signature` usando o `Tenant.webhook_secret`. O endpoint normaliza
Evolution, Resend e Twilio para `submitted`, `delivered`, `read`, `failed`, `rejected`,
`bounced`, `invalid` e `opted_out`, deduplica eventos e ativa o opt-out do aluno quando
recebe uma solicitação de descadastro.

## Modo dry-run vs. produção

- **Dry-run (padrão)**: nenhuma chamada de rede para WhatsApp/e-mail/SMS acontece. Tudo é
  logado em `intervention_logs` com `status="dry_run"` e `provider="dry_run"`. Seguro para
  demo e para rodar contra dados reais sem risco de incomodar ninguém.
- **Produção**: configure as credenciais do provider desejado (Evolution/Resend/Twilio) e
  passe `dry_run: false` na chamada (ou configure `AGENTS_DRY_RUN_DEFAULT=false`). Se as
  credenciais de um canal não estiverem configuradas, aquele agente cai em dry-run
  automaticamente mesmo com `dry_run=false` — nunca tenta enviar sem credencial.

## Limitações conhecidas (fora do escopo desta entrega)

- Providers reais ainda precisam de testes de contrato contra contas sandbox/produção segura;
  o sistema continua em dry-run por padrão.
- RBAC fino, campanhas agendadas completas e dashboard operacional ficam para as próximas
  fases; a API já expõe correlação, entrega e dead-letter para operação segura.
