# SophiA Gestão Escolar Web — integração nativa API v1

## Escopo

A MIRA possui cliente HTTP nativo somente leitura para o contrato API Web de Integração do SophiA Gestão Escolar Web v1.0. O cliente autentica com conta de serviço e consulta unidades, cursos, ficha financeira, boletim, notas recentes, filtro de boletim e boleto.

O contrato consultado não documenta listagem geral de alunos. As consultas acadêmicas/financeiras dependem de um `CodigoInterno` previamente conhecido e vinculado a um aluno MIRA. `Pessoa/PostPessoa` é escrita/inclusão, não descoberta.

## Wave 3 — fila e execução

- `POST /api/v1/integrations/sophia/sync/jobs` cria execução (HTTP 202).
- `idempotency_key` é única por tenant.
- `student_ids=[]` significa todos os alunos com vínculo explícito; uma lista preenchida restringe a execução aos alunos informados.
- `GET /api/v1/integrations/sophia/sync/jobs` lista execuções.
- `GET /api/v1/integrations/sophia/sync/jobs/{job_id}` retorna estado e eventos.
- `GET /api/v1/integrations/sophia/sync/students/{student_id}/resources` retorna os últimos recursos persistidos.
- Worker: `python -m app.services.connectors.sophia_sync_worker`; `--once` processa no máximo um job.
- Worker exige `SOPHIA_SYNC_WORKER_TENANT_IDS` com UUIDs explicitamente autorizados e `SOPHIA_ALLOWED_HOSTS` com os hosts DNS exatos homologados. A lista de hosts é obrigatória tanto para consultas diretas quanto para o worker.

A fila permite uma execução ativa por tenant, usa `FOR UPDATE SKIP LOCKED`, recupera leases sem heartbeat após três minutos e limita tentativas. Eventos de criação, início, recuperação, retry, sucesso e falha são auditados.

## Persistência e semântica

A migration `033_sophia_sync_jobs` cria fila, eventos e snapshots históricos imutáveis por aluno/recurso/execução. Todas as tabelas têm RLS e FORCE RLS. A chave composta tenant/aluno impede associar registros de outro tenant.

A MIRA preserva payloads como retornados pela origem. Valores `"-1"`, campos vazios e `null` não são convertidos em zero. Não calcula saldo devedor, inadimplência, média global ou risco a partir de payload bruto. Não infere exclusão de aluno.

Cada recurso é persistido em transação própria e cada execução mantém seu próprio snapshot, sem sobrescrever o histórico de execuções anteriores. Se uma chamada posterior falhar, o job não será marcado como sucesso; recursos já persistidos podem ser atualizados novamente no retry. A leitura do snapshot é tenant-scoped.

## Homologação obrigatória

1. Confirmar que o manual v1.0 ainda corresponde à versão instalada.
2. Confirmar URL/serial, usuário e senha de integração.
3. Garantir IP de saída estável e autorizado: o token SophiA é vinculado ao IP que autentica.
4. Validar uma matrícula conhecida e o respectivo `CodigoInterno`.
5. Comparar respostas com telas/relatórios reais para homologar semântica.
6. Só então permitir worker com allowlist restrita e observabilidade.

A API documentada não fornece sincronização completa de cadastro. A lista inicial de alunos deve vir de uma exportação/integração institucional autorizada. Nenhuma ativação em produção é feita nesta PR.

## Referência

Guia API Web SophiA v1.0 (espelho público, confirmar versão com Sophia/Prima): https://pt.scribd.com/document/592604325/Integracao-API-Web
