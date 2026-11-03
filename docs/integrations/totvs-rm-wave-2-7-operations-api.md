# Wave RM 2.7 — API de operações e monitoramento

## Objetivo

Expor as operações da fila durável TOTVS RM por uma API autenticada e isolada por tenant. Esta wave não cria um executor RM nem ativa sincronizações em ambiente real.

## Rotas

Prefixo: `/api/v1/integrations/totvs-rm`

| Método | Rota | Ação |
|---|---|---|
| GET | `/scopes` | Lista escopos da instituição autenticada |
| POST | `/sync` | Cria escopo, se necessário, e enfileira snapshot completo |
| GET | `/jobs` | Lista jobs com filtros e paginação |
| GET | `/jobs/{job_id}` | Consulta job e eventos |
| POST | `/jobs/{job_id}/cancel` | Solicita cancelamento seguro |
| POST | `/jobs/{job_id}/retry` | Reenfileira job que terminou com falha |
| GET | `/metrics` | Métricas da fila da instituição |

## Autenticação e autorização

- Todas as rotas exigem `require_min_role("coordinator")`.
- Papéis coordinator e admin podem operar; operator e viewer recebem 403.
- Sessões humanas continuam sujeitas às regras globais de MFA da MIRA.
- A API key de integração existente autentica no contexto de um único tenant e recebe papel admin no contrato atual.
- Todas as consultas de fila usam o tenant_id extraído da autenticação; nenhum endpoint aceita tenant_id fornecido pelo cliente.
- O serviço abre suas próprias transações e define `app.tenant_id` antes de consultar tabelas protegidas por RLS.
- A FK composta e as consultas tenant-scoped impedem consultar jobs de outra instituição; IDs inexistentes em outro tenant retornam 404.

## Criar uma sincronização

Exemplo:

    POST /api/v1/integrations/totvs-rm/sync
    Authorization: Bearer <sessao-ou-api-key>
    Idempotency-Key: rm-ies-001-alunos-2026-11-03

    {
      "coligada_id": "001",
      "source_name": "EduAlunoData",
      "entity_name": "students",
      "schema_version": "v1",
      "page_size": 500,
      "max_attempts": 5
    }

A API cria/recupera o escopo e enfileira apenas `mode=full_snapshot`. Não aceita URL, usuário, senha, token, credencial, SQL, nome de tenant ou payload de registros RM. O executor homologado resolve configuração e credenciais em fonte segura.

A chave de idempotência é obrigatória no header `Idempotency-Key`. Repetição com o mesmo escopo e o mesmo conteúdo retorna o job original. Reutilização da chave com conteúdo diferente retorna 409.

Identificadores de coligada, DataServer, entidade e schema aceitam somente caracteres alfanuméricos, ponto, sublinhado, dois-pontos e hífen. `page_size` fica entre 1 e 1000; `max_attempts`, entre 1 e 12.

## Listagem, histórico e métricas

- `GET /jobs` aceita `status`, `coligada_id`, `limit` (1–200) e `offset`.
- `GET /jobs/{job_id}` retorna metadados operacionais, somente o resumo permitido do request (mode/page_size) e eventos append-only com detalhes internos sensíveis removidos. IDs de job são validados como UUID.
- `GET /scopes` mostra escopos e o snapshot publicado atualmente.
- `GET /metrics` retorna contagem por status, profundidade da fila, jobs ativos e duração média.
- Erros retornam códigos controlados; respostas brutas do RM e stack traces não são expostos.

## Cancelamento

- Jobs queued/retry_wait passam diretamente a cancelled.
- Jobs running passam a cancel_requested; o worker e o executor interrompem entre páginas.
- Uma requisição repetida não deve publicar nem criar uma segunda execução.
- Cancelar não apaga páginas ou eventos já persistidos. O snapshot staging não é publicado por causa do cancelamento.

## Nova tentativa manual

- Somente jobs failed podem ser reenfileirados.
- Jobs queued, running, retry_wait, cancel_requested, cancelled e succeeded não aceitam retry manual.
- Limite de três novas tentativas manuais por job.
- A operação respeita o lock por tenant + coligada; não inicia se já existir job ativo na coligada.
- O mesmo job e checkpoint são preservados; tentativas anteriores ficam registradas nos eventos.
- Cada retry registra actor_user_id quando a ação vem de uma sessão humana.

## Auditoria

Enfileiramento, cancelamento e retry manual registram actor_user_id quando disponível e actor_type (user ou api_key) nos detalhes do evento. Cancelamentos repetidos são idempotentes e não duplicam eventos. A API não altera nem remove eventos existentes. O histórico é sempre filtrado por tenant e job.

## Limites e operação

- Não há executor RM financeiro homologado nesta entrega.
- O worker continua exigindo `RM_SYNC_EXECUTOR_MODULE` e `RM_SYNC_WORKER_TENANT_IDS`.
- A API não configura worker, credenciais, rede privada ou DataServer.
- Não foram acessados ambientes reais ou dados de instituições.
- Não houve migration nesta wave; as tabelas são as entregues na Wave RM 2.6.
- Não houve deploy.
