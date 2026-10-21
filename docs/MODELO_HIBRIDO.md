# Modelo Hibrido C — Learning Loop

## Visao

```
Score (base global) → TrainingEvent (snapshot features)
                              ↓
                    POST /outcomes (label real)
                              ↓
              tenant_model_ready quando houver volume
                              ↓
                    (futuro) fine-tune por IES
```

## Endpoints

```
POST /api/v1/tenants
GET  /api/v1/tenants
GET  /api/v1/tenants/{slug}/learning
POST /api/v1/outcomes
GET  /api/v1/training-events
```

## Alvo supervisionado: evadiu ou trancou em 90 dias

Cada rótulo pertence a um `TrainingEvent` (snapshot real de pontuação) e usa `scored_at` como data de referência. Envie `observed_at` como a data em que o resultado foi observado — não a data em que o lote foi importado. O evento precisa existir; pontue o aluno antes de registrar o resultado. Para vincular uma pontuação específica, envie `training_event_id` retornado por `GET /api/v1/training-events`; sem ele, a API usa o snapshot mais recente da matrícula. Quando um ID é enviado, a API rejeita IDs inexistentes ou que não correspondam à matrícula/tenant.

```bash
curl -X POST http://localhost:8000/api/v1/outcomes \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_slug": "default",
    "outcomes": [
      {"matricula": "2024001", "outcome": "evadiu", "observed_at": "2026-10-05T12:00:00Z"},
      {"matricula": "2024002", "outcome": "ativo", "observed_at": "2026-10-20T12:00:00Z"}
    ]
  }'
```

Definição versionada `evasion_90d_v1`:

- `evadiu` ou `trancou` até 90 dias após `scored_at` → positivo (`1`). Se o evento ocorrer depois da janela → negativo (`0`) para este alvo de 90 dias.
- `ativo` só vira negativo (`0`) quando observado no 90º dia ou depois. Observações anteriores ficam pendentes, sem rótulo.
- `concluiu` e `formou` → negativo (`0`), desde que a observação não seja anterior à pontuação.
- `transferiu` é registrado como desfecho concorrente e fica sem rótulo; não entra no treino.
- Resultados sem data de observação ou sem snapshot de pontuação não geram rótulo treinável. `labeled_at` registra a importação e `outcome_at` registra a data observada.

Registros rotulados pela regra anterior permanecem no histórico, mas não contam para prontidão nem são usados em novos treinos. Aplique a migração `alembic upgrade head` antes de implantar a versão nova.

## Limiares

- >= 200 eventos rotulados
- >= 20 labels positivos

Dados brutos isolados por tenant_id. Modelo base e global.
