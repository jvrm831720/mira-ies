# MIRA Dispatch — guia de produto, arquitetura e prontidão operacional

> PR #150. **Implementação de código; não é homologação de produção.**
> O envio ao vivo e o worker ficam desligados por padrão. Não aplicar migration
> em produção nem acionar clientes antes do checklist de liberação.

## 1. Um motor para três modalidades

| Modalidade | Quem inicia | Como é aprovada | Exemplos |
|---|---|---|---|
| `individual` | Operador com `campaigns.execute` | Modelo aprovado por outro usuário + autorização vigente individual, com fonte confiável | Acompanhamento de um aluno, convite à tutoria, contato de permanência |
| `targeted` | Criador de campanha | Segundo usuário aprova a audiência e atesta finalidade; cada destinatário tem sua própria autorização | Alunos com risco de evasão, grupo de rematrícula |
| `bulk` | Criador de campanha | Mesma aprovação de campanha, lotes e controles ampliados | Comunicações institucionais amplas, cobrança por canal permitido |

**O motor não é sinônimo de disparo em massa.** A intervenção individual
é registrada no mesmo ledger e na mesma fila com a mesma auditoria/limites,
mas não exige que o operador crie uma campanha. O modelo é previamente
revisado, e nenhum operador pode se autoaprovar um modelo novo.

Finalidades: `retention`, `academic`, `service`, `collections`.
Permissão de finalidade não é implícita. Autorizações são por
`tenant + pessoa + canal + finalidade + evidência + prazo`.

## 2. Implementação no repositório

- Migration `055_dispatch_platform` (após `054_smart_import_custom_fields`):
  15 tabelas SQL-only com `FORCE ROW LEVEL SECURITY`: `dispatch_campaigns`,
  `dispatch_items`, `dispatch_events`, `dispatch_inbound`,
  `dispatch_authorizations`, `dispatch_approved_templates`,
  `dispatch_provider_accounts`, `dispatch_suppressions`,
  `dispatch_worker_heartbeats`, `dispatch_rate_buckets`,
  `dispatch_source_credentials`, `dispatch_source_nonces`,
  `dispatch_external_contacts`, `dispatch_obligations` e
  `dispatch_payment_events`. Auditoria e pagamentos têm trigger append-only.
- `app.services.dispatch_core`: audiência, campanhas, workflow de aprovação,
  agendamento, deduplicação, consultas tenant-scoped.
- `app.services.dispatch_interventions`: modelos reutilizáveis, autorização
  por pessoa, single-message idempotente e integração de permissões.
- `app.dispatch_worker`: worker PostgreSQL independente, `SKIP LOCKED`,
  leases com fencing, retry seletivo, horários locais e limitação global
  por destinatário/canal entre campanhas.
- `app.services.dispatch_delivery`: consentimento, política de canal, dados
  financeiros atuais, taxa e envio com credenciais verificadas por tenant.
- `app.services.dispatch_providers`: credenciais criptografadas com chave
  dedicada, verificação de domínio e remetente, ativação com quatro olhos.
- `app.api.dispatch_native_webhooks`: assinatura nativa Resend/Svix
  e Twilio com secret específico do workspace.
- `app.services.dispatch_receipts`: reconciliação de webhooks que chegam
  antes do commit de `provider_message_id`.
- `app.services.dispatch_ingress_security`: credenciais HMAC por tenant/fonte/escopo,
  aprovação por segundo administrador, assinatura do payload e nonce anti-replay.
- `app.api.dispatch_integrations`: fatos de obrigação e pagamento com
  fonte, versão monotônica e evidência, contatos externos criptografados,
  respostas e reconciliação manual de resultados incertos.
- Frontend: `/disparos`, `/disparos/modelos`, `/disparos/provedores`.
  A navegação permanece alinhada à biblioteca de ícones Untitled UI.

## 3. Mecanismos de segurança

**Opt-in independente:** `DISPATCH_WORKER_ENABLED=false`,
`DISPATCH_DRY_RUN_DEFAULT=true`, `DISPATCH_LIVE_ENABLED=false`,
`DISPATCH_LIVE_TENANTS=`, `DISPATCH_LIVE_CHANNELS=`.
Todos devem ser configurados explicitamente antes de qualquer envio.

O envio real só é contemplado para Resend (e-mail) e Twilio (SMS).
Cobrança via WhatsApp está bloqueada. WhatsApp de retenção/atendimento
permanece apenas simulado neste motor, apesar de existirem provedores legados.

**Fontes confiáveis:** API key de tenant sozinha não autoriza escrever
fatos de pagamento, contatos ou consentimento. Cada conector é
registrado para escopo `financial`, `contacts`, `authorization` ou
`delivery`, recebe uma chave HMAC separada (revelada uma única vez),
e precisa de ativação por outro administrador. Assinaturas usam
timestamp (±5 minutos), nonce de uso único e hash do corpo HTTP
original. Ver `docs/DISPATCH_SOURCE_SIGNING.md`.

**Consentimento e autorização:** a MIRA não considera ausência de opt-out,
preferências importadas com padrão favorável ou um atestado geral de proposta
como prova de consentimento por canal. O conector autorizado deve registrar
um `dispatch_authorizations` com `status=granted`, fonte aprovada,
`verified_at`, `expires_at`, finalidade e `evidence_ref`.
Antes do envio, o worker revalida autorização, destinatário, janela de
contato, supressão, limites e obrigação. Revogações prevalecem sobre
agendamentos antigos.

**Idempotência e confiabilidade:** envios em estado `sending` ao perder
o lease passam a `unknown` e NÃO retornam para o disparador. O sistema
mantém `Idempotency-Key` de intervenções individuais e deduplicação de
destinatários no PostgreSQL. Resultados incertos só podem ser conciliados
com evidência verificável.

**Financeiro:** só obrigações `open`, com saldo positivo e verificação
recente entram na execução; a confirmação de pagamento não é inferida
de entrega, leitura, resposta ou promessa. O conector deve informar
`source_version` crescente e `observed_at` com timezone; fatos fora de
ordem são rejeitados e dívidas encerradas não reabrem por atualização comum.
Pagamentos gravados têm evento externo único, evidência e valor positivo.

**Provedores por workspace:** ativação requer conta verificada e um segundo
administrador. Segredos ficam criptografados com `DISPATCH_PROVIDER_ENCRYPTION_KEY`.
A API não devolve segredos cadastrados. Para Resend são usados remetente
e domínio verificados; para Twilio, Account SID e número da conta.

**Webhooks:** assinatura e timestamp originais validados com SDKs
Resend/Svix e Twilio; o endpoint genérico HMAC permanece apenas para um
gateway interno previamente confiável. Eventos prematuros são guardados
sem conteúdo pessoal até que o ID de mensagem enviado seja persistido.

## 4. Preparação em sandbox (sem tocar produção)

Configure segredos no ambiente do backend e não no frontend:

```env
DISPATCH_WORKER_ENABLED=false
DISPATCH_DRY_RUN_DEFAULT=true
DISPATCH_LIVE_ENABLED=false
DISPATCH_LIVE_TENANTS=
DISPATCH_LIVE_CHANNELS=
DISPATCH_TRUSTED_AUTHORIZATION_SOURCES=
DISPATCH_PROVIDER_ENCRYPTION_KEY=
DISPATCH_SOURCE_ENCRYPTION_KEY=
DISPATCH_CONTACT_ENCRYPTION_KEY=
DISPATCH_WEBHOOK_SECRET=
DISPATCH_TWILIO_CALLBACK_BASE_URL=
```

Use chaves Fernet separadas, geradas localmente e armazenadas no secret manager:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

A base deve suportar PostgreSQL `FOR UPDATE SKIP LOCKED`, advisory locks,
políticas RLS e índices da migration 055. Execute em banco **descartável**:

```bash
cd backend
python -m pip install -r requirements.txt
PYTHONPATH=. alembic heads
PYTHONPATH=. alembic upgrade head
PYTHONPATH=. ruff check app/api/dispatch*.py app/services/dispatch*.py app/dispatch*.py
PYTHONPATH=. pytest tests/test_dispatch_platform.py -q
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m app.dispatch_readiness
```

Teste obrigatório de RLS em função de banco com `NOSUPERUSER` e
`NOBYPASSRLS`. Não declarar aprovado se teste for pulado.

```bash
cd frontend
npm ci
npm run lint
npm test
npx tsc --noEmit
npm run build
```

Com as validações concluídas e migration aplicada em **sandbox**, ligue
apenas o worker e mantenha `DISPATCH_LIVE_ENABLED=false` para ensaio:

```bash
cd backend
DISPATCH_WORKER_ENABLED=true PYTHONPATH=. python -m app.dispatch_worker --once
```

A API não inicia o worker automaticamente. Em Render, provisionar um
**Background Worker** separado da API, com banco e segredo apropriados.
Não duplicar o worker dentro de uma instância web.

## 5. Gate de go-live

1. CI backend/frontend no SHA final (ou validação manual equivalente, gravada
   com artefatos). No momento GitHub Actions e Vercel estão limitados por
   cobrança/build; ausência de check não é sucesso.
2. `app.dispatch_readiness --require-live` com banco real de staging,
   credenciais por tenant verificadas, heartbeat e controle de RLS.
3. Testar carga com **múltiplos processos concorrentes**; perda de conexão
   antes/depois de aceitar provedor; prioridade de STOP e pagamento;
   restarts, horários, retry backoff, limites e quotas.
4. Verificar validade jurídica da finalidade/canal, evidência de contato,
   política de tratamento e retenção LGPD, e onboarding de organizações.
5. Conectar **fontes reais autorizadas** para dados e autorização, validar
   monotonicidade dos eventos e configurar webhooks nativos por workspace.
6. Ativar gradualmente somente um tenant piloto e apenas canal aprovado:
   `DISPATCH_DRY_RUN_DEFAULT=false`, `DISPATCH_LIVE_ENABLED=true`,
   `DISPATCH_WORKER_ENABLED=true`, além de allowlists de tenant e canal.
   Não aplicar switches globais sem autorização operacional explícita.
7. Monitorar entregabilidade, recebimento, custos, incidentes e supressões.
   Ter um rollback por desativação do worker e dos provedores/tenants.

## 6. Dependências externas ainda não verificadas

**Nenhuma alteração nesta PR prova automaticamente a prontidão de produção.**
É indispensável homologar por tenant: credenciais reais, remetentes, domínios
e números; integração concreta ERP/financeiro; políticas por canal; limites
contratuais, nível de capacidade da instância Render e PostgreSQL; callback
URLs públicas; e indicadores de operações com clientes reais.

O motor de classificação de respostas é propositalmente conservador e não
negocia dívida automaticamente. A MIRA registra `human_review` e ações
sugeridas, não decisões financeiras de IA.

**Não executar merge, migration ou deploy em produção** antes do gate de
qualidade; não disparar mensagens reais por este PR.
