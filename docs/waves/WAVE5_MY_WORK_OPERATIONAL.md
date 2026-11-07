# MIRA — Wave 5 · Meu Trabalho operacional

## Objetivo
Centralizar tarefas humanas existentes em **WorkActivity**. WorkActivityEvent continua sendo o histórico append-only e **não** é confundido com InterventionLog (envio), Outcome (permanência), pagamento ou recebimento financeiro.

## Quatro perspectivas
- **Para mim** (mine): abertas e em andamento atribuídas ao usuário autenticado.
- **Equipe** (team): abertas e em andamento atribuídas a outros membros da instituição.
- **Sem responsável** (unassigned): abertas e em andamento disponíveis para atribuição.
- **Histórico** (history): concluídas ou canceladas. Não é o histórico de envios.

GET /api/v1/work/inbox?view=mine&offset=0&limit=25 devolve total integral, has_more e next_offset. GET /api/v1/work/inbox/counts devolve quatro contagens sem limite de 100 itens. A consulta é tenant-scoped, com ordenação estável e limites de página no servidor.

## Priorização explicável
A API usa somente campos existentes e armazenados: prioridade atribuída (urgent/high/normal/low), vencimento, prazo nas próximas 24 horas, status de atribuição e origem campanha. Nunca interpreta risco do aluno como prioridade ou prevê pagamento.

Ordem estável: nível registrado, vencimento, prazo, data de criação e ID. A interface mostra os motivos documentados retornados pelo backend; não calcula score próprio.

## Fluxo de trabalho
1. Operador entra em **Meu Trabalho** (a central legada permanece em seção expansível), escolhe uma das quatro perspectivas e abre uma atividade.
2. O WorkItemInspector mostra situação, responsável, prazo, razões da prioridade e histórico.
3. Para a tarefa sem responsável, o operador usa **Assumir**. Só uma pessoa pode assumir uma atividade; a transação usa SELECT FOR UPDATE e incremento monotônico de revision. Tentativas concorrentes encontram 409.
4. O responsável registra um resultado humano com nota: done, unreachable, referred ou deferred.
5. done/unreachable/referred concluem o **trabalho humano**, não o contato ou a cobrança. deferred exige nova data futura e mantém a atividade aberta.
6. O resultado e a transição são gravados **atomicamente** como um evento human_result_resolved append-only com operation_key, actor_user_id, status antes/depois, nota e motivo. A revisão cresce.
7. Um retry com a mesma operation_key e mesmo payload não duplica evento; conflito de revisão ou reutilização da chave com conteúdo diferente resulta em 409.
8. A UI invalida a fila e o resumo, preserva a perspectiva e apresenta a próxima atividade disponível na página.

## Segurança
- Sessão humana real é obrigatória; GET exige permissão de leitura operacional (students.view) e POST exige students.edit, mantendo RBAC atual da rota /work.
- O backend valida tenant mesmo com ID conhecido e valida assignee_user_id antes de resolver. Quem não é responsável pode inspecionar no contexto da equipe, mas não concluir.
- A MIRA mantém RLS/FORCE RLS de work_activities e work_activity_events e trigger append-only existente. Nenhuma regra de acesso é relaxada.
- A interface não oferece ações automáticas de envio, cobrança ou pagamento.
- Resultados humanos não alteram InterventionLog.outcome, status de envio nem eventos de recuperação financeira.
- Operações de gravar usam expected_revision e operation_key; o backend segura row lock no registro até o commit.

## Migração
Alembic 071_work_inbox:
- work_activities.revision INT NOT NULL DEFAULT 1 CHECK >= 1;
- work_activity_events.operation_key VARCHAR(80) nullable;
- índice único parcial (tenant_id, activity_id, operation_key), somente quando operation_key IS NOT NULL;
- índice de paginação por tenant/estado/responsável/prazo/ID;
- backfill implícito de revision=1 sem reescrever registros anteriores;
- rollback bloqueia destruição de evidências de idempotência.

O CI limpa colunas criadas antecipadamente pelo bootstrap legado antes de executar a migração 071 no banco descartável, sem modificar o banco de produção.

## Testes
- backend/tests/test_work_inbox_wave5.py: quatro perspectivas, paginação com >25 registros, totais globais, prazos e razões, dois tenants, sessão humana, 409, claim, atribuição, idempotência de claim e resolução, outcome sem pagamento, deferred, concorrência simultânea, evento único por operação.
- frontend/tests/work-inbox-wave5.test.mjs: contrato das quatro visões, paginação, seleção sequencial, chave de retry, bloqueio de edição/atribuição, explicação e paridade dos painéis legados.
- Preservar backend/tests/test_work_activities_api.py, test_work_activity_transitions.py e frontend existente.

Gates obrigatórios: Alembic upgrade, Ruff, pytest completo, npm test, ESLint, TypeScript, build, snapshots e QA autenticado em dois tenants. Falha externa da Cloudflare deve ser verificada separadamente; merge de código não implica deploy.

### QA manual
- Dois operadores abrem a mesma atividade; um resolve e o outro recebe 409, sem segundo evento.
- Evento gravado, tarefa concluída e próximo item da fila visível sem recarregar a tela inteira.
- Duplo clique/reenvio de rede com mesma chave retorna replay, sem duplicar resultado.
- Adiar sem nova data deve falhar; com data deve manter a atividade na fila de pendentes.
- Operador tenta resolver item atribuído a outro usuário e recebe 403.
- Nenhuma ação humana modifica status de disparos ou recebimento financeiro.
