# Contrato de ingestão de features (modelo preditivo)

## Objetivo

Toda integração — conector nativo (Sophia, Jacad, Sponte, RM, Canvas…) **ou** Composio — pode atuar em dois eixos:

1. **Tool / ação** (agente, campanhas, OAuth) — política de toolkit/tools.
2. **Fonte de dados** (features do motor preditivo, sinais, treinamento) — este contrato.

Uma ferramenta existir no catálogo Composio **não** autoriza escrita de features. Só fontes explicitamente habilitadas em `tenant_integration_data_sources`, com `feature_keys` permitidas, podem gerar `student_feature_observations`.

## Fluxo

```text
Connector nativo / adapter Composio
        │
        v
Transform → FeatureObservationInput (feature_key allowlisted)
        │
        v
assert_source_may_write_feature (fail-closed)
        │
        v
student_feature_observations (RLS, idempotente por observation_key)
        │
        v
Agregação / snapshot → students.* | signals | training dataset
```

## Tabelas (migration 047)

- `tenant_integration_data_sources` — política por tenant (`source_kind`, `source_key`, `is_enabled`, `feature_keys`).
- `student_feature_observations` — observações tipadas, com `student_id` ou `subject_ref`, `reliability`, `observed_at`.

Ambas com RLS ENABLE + FORCE e isolamento por `app.tenant_id`.

## Regras de segurança

- `tenant_id` sempre do contexto autenticado / job — nunca autoridade do cliente.
- Allowlist global de `feature_key` no contrato + lista opcional por fonte.
- Payload JSONB não deve guardar credenciais nem dumps brutos de API.
- Idempotência diária por hash (`observation_key`) evita duplicar re-syncs.

## Próximos passos

- Persistência async (repository) e API admin para habilitar fontes.
- Mappers por conector (Sophia → nota_media, etc.) e por toolkit Composio marcado `data_source`.
- Job que materializa a observação mais recente em colunas de `students` / features de treino.
- Extensão do catálogo de sinais para consumir observações externas com `reliability`.
