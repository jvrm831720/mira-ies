# Eventos de retenção (Mira)

Cada intervenção gera um **evento auditável** em `intervention_logs`.

## Ciclo

1. **Decisão** — `decision_reason` + `decision_context` (score, canais, opt-out)
2. **Execução** — `status`, `channel`, `delivery_status`
3. **Desfecho** — `outcome` (preenchido depois, manual ou importação)

## Outcomes válidos

| Valor | Significado |
| --- | --- |
| `responded` | Aluno respondeu ao contato |
| `no_response` | Sem resposta no período |
| `stayed` | Permaneceu matriculado |
| `dropped` | Evadiu / cancelou |
| `transferred` | Encaminhado a atendimento humano |
| `unknown` | Indefinido |

`null` = ainda pendente de desfecho.

## API

```http
GET  /api/v1/agents/retention/logs?outcome=pending
PATCH /api/v1/agents/retention/logs/{id}/outcome
{
  "outcome": "stayed",
  "note": "Confirmado no diário de classe",
  "source": "manual"
}
```

## Por que isso importa

Sem desfecho ligado à tentativa, o modelo preditivo não aprende o que funcionou.
Com o trio decisão → envio → outcome, a Mira fecha o learning loop do MVP.
