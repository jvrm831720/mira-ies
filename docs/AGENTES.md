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
| `status` | `planned\|sent\|dry_run\|failed\|skipped` (`planned` reservado para uma futura fila assíncrona — não usado no fluxo síncrono atual) |
| `message_preview` | **até 120 caracteres**, nunca o corpo completo (evita logar PII desnecessário) |
| `skip_reason` / `error` | motivo do skip (anti-spam, missing_contact, risco baixo) ou erro de envio |

`Student` ganhou duas colunas opcionais: `telefone` (varchar 30) e `email` (varchar 255).
Aceitos via upload CSV/XLSX (aliases: `telefone`, `celular`, `whatsapp`, `phone`, `contato` /
`email`, `e_mail`) e via conector genérico (`POST /api/v1/ingest/students`). Conectores
ERP/LMS específicos (JACAD, Sponte, Moodle, etc.) ainda não extraem telefone/e-mail do payload
nativo — é um próximo passo natural, por conector, conforme a necessidade real de cada
integração (o campo já existe no schema canônico, só falta o `pick()` em cada conector).

Migração: `backend/alembic/versions/002_agents_and_contact_fields.py`.

## Configuração (`.env`)

Tudo tem default seguro — nenhuma credencial é obrigatória para rodar em dry-run.

```bash
AGENTS_DRY_RUN_DEFAULT=true        # false em producao quando os providers reais estiverem prontos
AGENTS_MIN_HOURS_BETWEEN_CONTACT=48
AGENTS_MAX_CONTACTS_PER_WEEK=3

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

## API

Todas as rotas exigem `X-API-Key` (`Depends(get_current_tenant)`) e são isoladas por tenant.

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

### `GET /api/v1/agents/retention/preview/{student_id}`

Monta a mensagem do canal prioritário **sem enviar nem gravar log** — útil para a coordenação
revisar o texto antes de rodar de verdade.

```bash
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/api/v1/agents/retention/preview/<student_id>
```

### `GET /api/v1/agents/status`

Mostra config de anti-spam e qual provider está ativo por canal.

## Modo dry-run vs. produção

- **Dry-run (padrão)**: nenhuma chamada de rede para WhatsApp/e-mail/SMS acontece. Tudo é
  logado em `intervention_logs` com `status="dry_run"` e `provider="dry_run"`. Seguro para
  demo e para rodar contra dados reais sem risco de incomodar ninguém.
- **Produção**: configure as credenciais do provider desejado (Evolution/Resend/Twilio) e
  passe `dry_run: false` na chamada (ou configure `AGENTS_DRY_RUN_DEFAULT=false`). Se as
  credenciais de um canal não estiverem configuradas, aquele agente cai em dry-run
  automaticamente mesmo com `dry_run=false` — nunca tenta enviar sem credencial.

## Limitações conhecidas (fora do escopo desta entrega)

- Conectores ERP/LMS específicos ainda não mapeiam telefone/e-mail do payload nativo.
- Sem fila/retry assíncrono — o `run` é síncrono dentro da própria request HTTP; para volumes
  grandes de alunos, mover para um worker (Redis já está no `docker-compose.yml`) é o próximo
  passo natural.
- Sem opt-out de aluno registrado explicitamente (hoje o controle é só a régua anti-spam).
- Dashboard/dashboard de acompanhamento das intervenções fica para a Fase 03.
