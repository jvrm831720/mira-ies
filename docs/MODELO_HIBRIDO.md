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

## Registrar evasao

```bash
curl -X POST http://localhost:8000/api/v1/outcomes \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_slug": "default",
    "outcomes": [
      {"matricula": "2024001", "outcome": "evadiu"},
      {"matricula": "2024002", "outcome": "concluiu"}
    ]
  }'
```

Outcomes: evadiu/trancou/transferiu → label 1 | concluiu/ativo/formou → label 0

## Limiares

- >= 200 eventos rotulados
- >= 20 labels positivos

Dados brutos isolados por tenant_id. Modelo base e global.
