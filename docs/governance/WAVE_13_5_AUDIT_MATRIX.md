# Prioridade 13 — Wave 13.5: matriz de auditoria ponta a ponta

## Objetivo

Demonstrar, com testes reais e invariantes de serviço/banco, que:

1. Instituição autorizada (modalidade A) produz contribuição sanitizada elegível.
2. Modalidade B é tecnicamente incapaz de contribuir (serviço + ausência no dataset compartilhado).
3. Contribuições de um tenant não se confundem com as de outro (chave isolada por `tenant_id`).
4. Revogação impede reuso no dataset compartilhado e em runs.
5. Histórico de elegibilidade é auditável (append-only no desenho de serviço).
6. Training run shared revalida política e exige contribuições elegíveis.
7. MIRA Base só registra candidato a partir de run `shared_base` **succeeded**.
8. Ativação é exclusiva; rollback restaura versão anterior com evento append-only.

## Artefatos por wave

| Wave | Artefato principal |
| --- | --- |
| 13.1 | Políticas A/B, autorização institucional, FORCE RLS, append-only |
| 13.2 | `eligible_contributions`, sanitizer, hard block B |
| 13.3 | `training_runs`, `training_dataset_snapshots` imutáveis |
| 13.4 | `mira_base_lifecycle_events`, activate/rollback |
| 13.5 | Matriz E2E + testes de isolamento |

## Matriz de ameaças coberta

| Ameaça | Controle | Teste |
| --- | --- | --- |
| Modalidade B entra no treino compartilhado | `assess_contribution` + `require_shared_training_authorization` | `test_wave13_5_modality_b_*` |
| Dados com identificadores no dataset | `contribution_sanitizer` | Wave 13.2 + E2E eligible path |
| Cross-tenant contribution mix-up | Unique `(tenant_id, key, hash)` | `test_wave13_5_two_tenants_isolation_*` |
| Revogação ignorada | Status `revoked` + dataset builder | isolation + revocation test |
| Run sem política vigente | Guard no create run | modality B run block |
| Candidato de run falho | `register_base_candidate` exige `succeeded` | candidate requires succeeded |
| Duas bases ativas | activate retira anterior + unique index | lifecycle chain |

## RLS (quando migration aplicada)

| Tabela | Política esperada |
| --- | --- |
| `eligible_contributions` | tenant_id = `app.tenant_id` OR `app.is_mira_admin` |
| `training_dataset_snapshots` | admin only |
| `training_runs` | admin OR tenant próprio |
| `mira_base_lifecycle_events` | admin only |

`FORCE ROW LEVEL SECURITY` em todas as tabelas acima.

## Critério de conclusão da Prioridade 13

- [x] 13.1 autorizações e hardening
- [x] 13.2 contribuições elegíveis + sanitização + block B
- [x] 13.3 runs + snapshots imutáveis
- [x] 13.4 lifecycle MIRA Base
- [x] 13.5 auditoria E2E (esta wave)

**Operacional:** nenhuma migration aplicada remotamente; nenhum deploy nesta etapa.
