# TOTVS RM — Wave 2.5: persistência de snapshots

**Status:** implementação PostgreSQL e testes de integração adicionados. Não há chamadas a uma instalação RM nem deploy.

## Componentes

- Migration `029_rm_snapshot_persistence`.
- Modelos `RmSyncScope`, `RmSyncRun`, `RmSyncPage` e `RmSyncRecord`.
- Repositório `RMPostgresSnapshotRepository`.
- Testes PostgreSQL em `test_totvs_rm_snapshot_repository.py`.

## Modelo persistido

| Tabela | Responsabilidade |
|---|---|
| `rm_sync_scopes` | Escopo tenant + coligada + origem + entidade + schema e ponteiro para snapshot atual |
| `rm_sync_runs` | Estado da execução, identidade, checkpoint, contagem, status e diff |
| `rm_sync_pages` | Página, offsets, fingerprint, metadados e payload recebido |
| `rm_sync_records` | Registros normalizados por identidade composta, isolados por execução |

As relações entre execução, página e registro usam chaves compostas com `tenant_id`. O banco também aplica RLS + FORCE RLS nas quatro tabelas.

## Transações e retomada

Cada método de escrita abre uma transação:
- `begin_run`: cria ou recupera o escopo, bloqueia a linha de escopo e impede duas execuções simultâneas em staging.
- `stage_page`: bloqueia a execução, valida o checkpoint usando o motor puro da Wave 2.4, grava página + registros + novo checkpoint na mesma transação.
- Replay idêntico não duplica registros; replay divergente falha.
- `get_checkpoint`: retorna o último offset confirmado, para retomada em outra sessão/processo.
- `finalize_run`: bloqueia primeiro o escopo e depois a execução, carrega o snapshot anterior, calcula o diff e troca o ponteiro atual na mesma transação.

A publicação é atômica: se validação, diff ou escrita falhar, a transação não substitui o snapshot atual. O snapshot anterior passa a `superseded` somente na mesma transação em que o novo passa a `committed`.

## Segurança e isolamento

O repositório define `app.tenant_id` com `set_config(..., true)` no início de cada transação. Toda leitura e escrita filtra também pelo tenant explícito. As tabelas usam RLS e FORCE RLS, com política vinculada ao tenant da sessão.

A conexão de banco usada pela aplicação deve ter permissões compatíveis com RLS. Não usar credenciais de superuser ou roles com `BYPASSRLS` no caminho operacional.

## Limites

- Não agenda jobs nem chama DataServer RM.
- Não implementa incremental nem cursor.
- Não propaga exclusões sem snapshot completo/autoritativo e semântica homologada.
- A paginação por offset continua sem garantia de snapshot consistente durante alterações na origem.
- O repositório persiste os registros de origem; não atualiza diretamente alunos, débitos, scores ou intervenções MIRA.
- A homologação de identidade e semântica continua sendo responsabilidade da IES.

## Validação

Testes de integração PostgreSQL cobrem:
- checkpoint persistido e retomada em uma nova sessão;
- replay idempotente de página;
- publicação de snapshot e supersessão do anterior;
- diff de inclusão, atualização e remoção autorizada;
- rollback quando o snapshot está incompleto;
- bloqueio de segunda execução staging no mesmo escopo;
- filtro de tenant na leitura de checkpoint.

O CI deve validar a migration graph, Ruff e a suíte pytest com PostgreSQL.
