# Wave RM 2.6 — Orquestração durável de sincronizações

## Objetivo

Executar snapshots RM por jobs persistidos, com concorrência controlada, retry classificado, retomada por checkpoint e cancelamento cooperativo. A fila usa PostgreSQL. Redis pode ser usado futuramente apenas como sinal de despertar; não é a fonte de verdade do estado.

## Arquitetura

- Tabela rm_sync_jobs: fila durável, idempotência, tentativas, disponibilidade, lease e estado de cancelamento.
- Tabela rm_sync_job_events: histórico append-only de eventos operacionais.
- RMPostgresSyncQueue: criação do escopo antes da primeira execução, enqueue, claim com FOR UPDATE SKIP LOCKED, heartbeat, cancelamento, retry, histórico e métricas.
- RMSyncWorker: executa um job por vez por worker e chama um executor injetado.
- app.rm_sync_worker: processo standalone, independente do processo HTTP.
- Cada claim recebe um tenant_id explicitamente autorizado. O worker configura app.tenant_id antes de consultar filas e não faz bypass do RLS.
- Índice parcial único por tenant + coligada impede jobs simultâneos da mesma coligada, mesmo quando tentam sincronizar DataServers/entidades diferentes.

## Estados

queued → running → succeeded

running → retry_wait → running

queued/retry_wait → cancelled

running → cancel_requested → cancelled

running → failed para falhas permanentes ou limite de tentativas.

Jobs com lease expirado podem ser reclamados por outro worker. O worker renova o lease automaticamente a cada 30 segundos e o executor também deve chamar heartbeat e consultar cancelamento entre páginas. O worker antigo perde o direito de heartbeat/finalização quando o worker_id muda. Se o heartbeat retornar false, o executor deve interromper o processamento e não publicar o snapshot.

## Retry e classificação

- Timeout, conexão indisponível e RMTransientJobError: retry.
- Erros de autenticação, mapeamento, validação e erros desconhecidos: falha permanente por padrão.
- Backoff exponencial: 15s, 30s, 60s... limitado a 30 minutos.
- max_attempts configurável por job (1–12).
- Mensagens brutas de exceção e respostas da origem não são persistidas; somente códigos de erro controlados e mensagens genéricas são armazenados.
- request rejeita nomes de campos comuns de segredo. Credenciais devem ser resolvidas pelo executor em cofre/configuração segura e nunca passadas na fila.

## Execução do worker

A partir de backend/:

    RM_SYNC_EXECUTOR_MODULE=app.integrations.rm_executor
    RM_SYNC_WORKER_TENANT_IDS=<tenant-uuid-1>,<tenant-uuid-2>
    PYTHONPATH=. python -m app.rm_sync_worker

O módulo indicado deve expor uma função assíncrona:

    async def execute_rm_sync_job(job, heartbeat, cancelled, attach_snapshot) -> dict | None:
        ...

O executor recebe o job sem credenciais e deve:

1. Resolver configuração e credenciais do tenant em fonte segura.
2. Recuperar job.snapshot_run_id/checkpoint existente ou iniciar um run usando RMPostgresSnapshotRepository; após criar o run, chamar attach_snapshot(run_id) antes de extrair páginas.
3. Chamar heartbeat e verificar cancelamento entre páginas.
4. Persistir cada página e checkpoint antes de avançar. Se heartbeat retornar false, interromper sem publicar.
5. Validar completude e reconciliar.
6. Publicar somente pelo método transacional finalize_run.
7. Retornar {"snapshot_run_id": "..."} após publicação.

Sem RM_SYNC_EXECUTOR_MODULE ou sem RM_SYNC_WORKER_TENANT_IDS, o processo falha ao iniciar. Isso é intencional: não há DataServer financeiro homologado nem armazenamento de credenciais RM configurado nesta wave. Nenhum endpoint RM é presumido.

## Observabilidade

- history(tenant_id, scope_id) retorna histórico resumido por escopo.
- events(tenant_id, job_id) retorna eventos de execução.
- metrics(tenant_id) retorna contagem por estado, profundidade da fila, jobs ativos e duração média das execuções concluídas.
- Eventos incluem enfileiramento, início, recuperação de lease, retry, cancelamento e conclusão/falha.
- Logs não incluem payloads de alunos, dados financeiros ou credenciais.

## Segurança e concorrência

- RLS + FORCE RLS nas duas tabelas novas.
- FK composta mantém tenant_id consistente com escopo e eventos.
- O worker não consulta a fila globalmente: a lista de tenants autorizados é configurada por ambiente.
- FOR UPDATE SKIP LOCKED distribui jobs entre workers.
- Lock/advisory lock por tenant + coligada durante enqueue e índice parcial único impedem jobs concorrentes da mesma coligada, inclusive entre entidades diferentes.
- Cancelamento é cooperativo: uma página/solicitação de rede já em andamento pode terminar; o executor deve parar antes de iniciar a próxima e jamais publicar após cancelamento.
- O worker renova o lease automaticamente a cada 30 segundos; o executor mantém heartbeat/cancelamento como checkpoints cooperativos. Falhas na renovação bloqueiam a publicação.

## Limites desta entrega

- Não implementa endpoint HTTP para administrar jobs; a camada de serviço está pronta para ser exposta em uma etapa de API/RBAC.
- Não configura um serviço de worker no Cloudflare nem altera deploy.
- Não implementa executor RM financeiro concreto, porque endpoints, campos e credenciais por instalação ainda exigem homologação.
- O worker exige RM_SYNC_WORKER_TENANT_IDS com os tenants autorizados; cada claim aplica o contexto RLS daquele tenant, sem bypass global.
- Não promete execução exactly-once. A garantia é entrega at-least-once com idempotência no job e replay seguro nas páginas; o executor deve usar os checkpoints persistidos.
- Nenhum dado ou ambiente real de IES foi acessado.
