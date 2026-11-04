# Central de Trabalho — contrato operacional

A Central reúne **atividades humanas** da equipe, separadas dos registros de envio automatizado (`InterventionLog`). O estado de uma atividade não representa entrega de mensagem nem resultado de permanência do estudante.

## Origem e prioridade

`work_activities.origin_type` diferencia `manual` de `campaign`. Atividades criadas a partir de um log de intervenção herdam a campanha quando o log aponta para uma campanha pertencente ao mesmo tenant. `campaign_id` mantém o vínculo direto; tarefas manuais não recebem esse vínculo. A prioridade aceita `low`, `normal`, `high` e `urgent`; novas tarefas usam `normal` por padrão. A fila prioriza urgência e, em seguida, prazo.

## Geração de tarefas por campanha

Uma campanha ou fluxo interno pode chamar `POST /api/v1/work/activities/campaign-generated` quando uma regra de negócio exigir intervenção da equipe (por exemplo, encaminhamento acadêmico ou contato humano). A chamada gera uma atividade por estudante da audiência explícita, com vínculo à campanha, prioridade, responsável e prazo opcionais.

```json
{
  "campaign_id": "UUID-da-campanha",
  "generation_key": "versao-3-regra-contato-humano-execucao-2026-11-04",
  "student_ids": ["UUID-do-aluno-1", "UUID-do-aluno-2"],
  "title": "Realizar contato acadêmico",
  "description": "Investigar barreira de permanência e registrar encaminhamento.",
  "activity_type": "contact",
  "priority": "high",
  "assignee_user_id": null,
  "due_at": "2026-11-06T18:00:00Z"
}
```

`generation_key` identifica de forma estável a geração dentro da campanha. Repetir a mesma combinação de campanha, chave e estudante reutiliza a atividade existente, sem duplicá-la; uma chave nova permite um novo ciclo de trabalho. São aceitos até 100 estudantes por chamada e todos os IDs precisam pertencer ao tenant autenticado. O endpoint valida a campanha, aplica o mesmo isolamento multi-tenant e grava o evento de criação.

**Salvaguarda:** uma simulação (`simulate`) ou execução em `dry_run` de comunicação não cria tarefas automaticamente. O chamador deve acionar este endpoint apenas quando a regra executável configurar uma ação humana, para que teste/previsão não gere trabalho real.

## API da fila

- `GET /api/v1/work/activities`: filtros `status`, `assignee`, `origin_type`, `priority`, `student_id`, `intervention_log_id` e `overdue_only`.
- `GET /api/v1/work/activities/mine`: fila ativa do usuário autenticado.
- `GET /api/v1/work/activities/summary`: contadores não limitados por paginação para pendentes, atrasadas, concluídas nos últimos sete dias, sem responsável, pendentes de campanha e urgentes.
- `POST /api/v1/work/activities` e `PATCH /api/v1/work/activities/{id}`: criação/edição; mudanças relevantes são gravadas no histórico.
- `POST /api/v1/work/activities/{id}/result` e `GET /api/v1/work/activities/{id}/events`: registro de resultado e consulta do histórico append-only.
- `GET /api/v1/students/{id}/work-timeline`: atividades e eventos na ficha do estudante.

A listagem e a agregação são sempre limitadas ao tenant da sessão. Atividades concluídas/canceladas permanecem disponíveis no filtro de status e não podem ser editadas ou reabertas.
