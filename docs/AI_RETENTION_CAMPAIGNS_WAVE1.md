# Campanhas inteligentes — Wave 1.1

## Objetivo

Começar a transformar sinais e grupos de alunos em oportunidades de retenção explicáveis, sem criar um segundo motor de campanhas e sem liberar disparos automáticos antes da governança.

## O que já existia na MIRA

- `retention_campaigns`: campanhas versionadas por tenant e regras validadas.
- `/agents/retention/campaigns/{id}/simulate`: simulação de elegibilidade.
- `run-dry-run`: passagem pelo orquestrador sem envio real.
- Catálogo virtual de sete grupos, com estados TRUE / FALSE / INDETERMINATE.
- Histórico de intervenções e governança de preferências/opt-out.

## Entrega desta wave

Endpoint autenticado:

`GET /api/v1/agents/retention/campaigns/intelligence/opportunities`

O endpoint usa o resumo canônico dos sete grupos e devolve briefs recomendados com:

- grupo de origem e versão do catálogo;
- quantidade encontrada e casos indeterminados;
- estimativa de alcance como limite superior não validado;
- objetivo, estratégia, canais sugeridos e cadência;
- briefing da mensagem, justificativa e salvaguardas.

A recomendação é baseada em sinais e regras determinísticas (`signals-and-rules-v1`). Esta wave não usa LLM para redigir mensagens. O campo `is_ai_generated_copy=false` torna essa limitação explícita.

## Salvaguardas

- O endpoint exige papel mínimo `coordinator`.
- Toda consulta é limitada ao tenant autenticado pelo serviço canônico de grupos.
- Os grupos podem se sobrepor; a contagem não deve ser somada como se fosse uma audiência única.
- O alcance é um limite superior. Ainda não desconta contatos inválidos, opt-out, preferências por canal ou contatos/intervenções recentes.
- `missing_score` gera ação interna de saneamento. Não autoriza comunicação automática e não significa baixo risco.
- Cobertura incompleta e estados indeterminados aparecem como salvaguardas.
- O endpoint não cria campanha, não aprova, não agenda e não envia mensagens.

## Próximas waves

### Wave 1.2 — proposta editável
- Criar proposta persistida a partir de uma oportunidade.
- Snapshot imutável do público, grupo e versão do catálogo/regra.
- Deduplicação entre grupos e validação de contato, consentimento, preferências e histórico.
- Estimativa de alcance validada e lista de bloqueios.

### Wave 1.3 — revisão e aprovação
- Edição de objetivo, público, canais, mensagens e régua.
- Estados de revisão, aprovação e rejeição.
- Permissão de aprovação separada da criação, com trilha de auditoria.
- Bloqueio de execução quando não houver aprovação válida.

### Wave 1.4 — execução governada
- Agendamento, pausa, cancelamento e retomada.
- Idempotência, limites por canal, opt-out e supressão de contatos recentes.
- Eventos de execução e métricas operacionais.

### Wave 1.5 — IA generativa e resultados
- Geração personalizada de mensagens com contexto permitido e templates aprovados.
- Justificativas ligadas a evidências rastreáveis.
- Medição de respostas, atendimentos e outcomes educacionais, sem atribuir causalidade indevida.

## Critérios para não avançar

Não habilitar envio real nesta wave. A execução real depende de aprovação, autorização backend, política por tenant, trilha de auditoria, consentimento, preferências e supressão de contatos recentes.
