# Wave 1.4B — Agendamento explícito

## Escopo

- Persiste data/hora com offset UTC explícito e nome de fuso IANA.
- Confere se o offset informado corresponde ao fuso na data selecionada.
- Só permite agendar propostas aprovadas.
- Permite remover o agendamento e retornar a proposta ao estado `approved`.
- Lista o cronograma do tenant, ordenado pela próxima data.
- Registra criação e remoção do agendamento na trilha append-only existente.
- Exige perfil admin, sessão humana e MFA AAL2 para criar ou remover agendamentos.

## Limites de segurança

- Não cria scheduler, fila, worker, job ou integração de canal.
- Não dispara mensagens nem inicia execução ao chegar a data/hora.
- Não altera o snapshot ou hash imutável da audiência.
- Não aplica migrations ao banco de dados.
- O campo `execution_enabled` permanece `false`; `dispatch_created` também é `false`.

## API

- `POST /api/v1/agents/retention/campaigns/intelligence/proposals/{proposal_id}/schedule`
- `DELETE /api/v1/agents/retention/campaigns/intelligence/proposals/{proposal_id}/schedule`
- `GET /api/v1/agents/retention/campaigns/intelligence/schedule`

O corpo do POST recebe `scheduled_for` em ISO 8601 com offset explícito e `schedule_timezone` com nome IANA, por exemplo `America/Sao_Paulo`.

## Próxima etapa

Depois da revisão e CI desta wave, a Wave 1.4C pode implementar execução simulada, idempotência e revalidação de elegibilidade. Execução real permanece fora do escopo.
