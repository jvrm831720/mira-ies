# Rastreabilidade: regra → código → teste

**Commit analisado:** e25858b4cb12dab781b19e0ed46cf193007fb520 (main, 2026-10-27). A matriz é inicial e cobre evidências localizadas; não afirma que todas as rotas foram auditadas.

| Regra | Evidência de implementação | Testes relacionados | Situação e lacuna |
|---|---|---|---|
| RB-SEC-001 | models/tenant.py, models/student.py, services/tenant.py | test_retention_campaign_isolation.py, test_retention_campaign_security.py, test_governance_e2e.py | Parcial; faltam todos endpoints, exports, jobs e conectores |
| RB-AUT-001 | models/control_center.py, api/control_center_auth.py | test_control_center_auth.py | Parcial; staging e concorrência MFA pendentes |
| RB-RBAC-001 | api/control_center_admin.py, api/control_center_auth.py | test_control_center_auth.py, test_mira_admin_governance.py | Parcial; matriz completa de endpoints não produzida |
| RB-AUD-001 | models/control_center.py, models/consent.py, api/control_center_admin.py | test_mira_admin_governance.py, test_consent_governance.py | Parcial; append-only, retenção e atomicidade pendentes |
| RB-IMP-001 | services/ingestion.py, api/upload.py | test_upload_api.py, test_smart_import_api.py | Parcial; multi-file sem join consolidado |
| RB-RSK-001 | ml/scoring.py, ml/rules.py, api/scoring.py | test_rules.py, test_scoring_api.py, test_ml_evaluation.py | Parcial; calibração e copy de UI não auditadas completamente |
| RB-INT-001/002 | agents/orchestrator.py, services/consent.py, services/delivery_webhooks.py | test_agent_delivery_safety.py, test_consent_topic_rules.py, test_waha_provider.py | Parcial; provider real/staging pendente |
| RB-ANA-001 | models/intervention.py, docs/RETENTION_EVENTS.md | test_retention_observability.py | Parcial; fórmula/denominador por KPI não catalogados integralmente |
| RB-GOV-001/002 | services/training_policy.py, models/data_governance.py, models/institutional_training_authorization.py | test_training_policy.py, test_shared_training_guard.py, test_institutional_training_authorization.py | Parcial; decisão por amostra no pipeline sem auditoria persistente comprovada |
| RB-GOV-003/004 | api/scoring.py, api/outcomes.py, models/tenant.py | test_governance_e2e.py, test_model_lifecycle.py | Parcial; transição A→B não revisa comprovadamente runs pendentes |
| RB-CC-001/002 | api/control_center_admin.py, models/control_center.py | test_mira_admin_governance.py, test_import_structure_and_finance.py | Parcial; cobrança é manual e há gaps de staging |
| RB-API-001/RB-REL-001 | services/connectors/, services/retention_queue.py, api/delivery_webhooks.py | test_connectors_transform.py, test_retention_queue_reliability.py | Parcial; contrato de cada integração e caos/rede pendentes |
| RB-UX-001 | frontend/src/app/(app)/*, frontend/src/lib/api.ts | Não localizado teste E2E global | Não verificada globalmente |
| RB-PRI-001 | models/student.py, models/intervention.py, models/tenant.py | Testes parciais de consentimento | Política de retenção/expurgo e direitos não verificados |

## Evidência de CI disponível
GitHub Actions run #328, associado à PR #47 antes do merge: jobs `lint-and-test` e `frontend-check` concluíram com sucesso. Isso não prova execução de toda a matriz, nem validação em staging/produção.

## Método de conclusão por regra
Para marcar uma regra como validada, registrar commit, teste nominal, cenário coberto, resultado, ambiente e link do run. Testes que não foram executados nesta auditoria não são inferidos como aprovados a partir do nome do arquivo.



## Adendo de auditoria dirigida (2026-10-27)

| Regra | Evidência examinada | Teste de regressão adicionado | Estado após adendo |
|---|---|---|---|
| RB-SEC-004 | `backend/app/api/scoring.py`; `score_batch` recebe tenant do contexto | `backend/tests/test_governance_audit_edges.py::test_risk_endpoints_do_not_disclose_another_tenants_student_or_batch` | Implementação evidenciada no escopo dos endpoints selecionados; teste passou no GitHub Actions run #331. Não representa cobertura total. |
| RB-GOV-005 | `backend/app/services/training_policy.py` seleciona registros com `effective_at <= now` | `backend/tests/test_governance_audit_edges.py::test_future_dated_policy_does_not_take_effect_early` | Regra implementada no resolver; teste passou no GitHub Actions run #331 (commit 34388663091e8701f05ee776326ab20fe51bbf8b). |
| RB-GOV-006 | `resolve_institutional_training_authorization`, `tenant_train.py`, testes de autorização | `test_institutional_training_authorization.py` (existente) | Parcialmente coberta; ainda falta comprovar todos os caminhos de treino e auditoria persistente por execução. |

**Novo arquivo de teste:** `backend/tests/test_governance_audit_edges.py`. Nenhum arquivo de aplicação ou migration foi alterado nesta etapa.


## Adendo — evidências da fase 3 (2026-10-27)

| Regra | Evidência examinada | Teste/validação | Estado e lacuna |
|---|---|---|---|
| RB-GOV-007 | `backend/app/api/scoring.py::retrain_model` retorna HTTP 409 para treino global legado | `backend/tests/test_governance_audit_edges.py::test_legacy_global_training_endpoint_fails_closed` foi adicionado; execução no CI do HEAD atual ainda não confirmada | Bloqueio evidenciado nesse endpoint; inventário de todos os caminhos de treino global pendente |
| RB-GOV-008 | `backend/app/ml/tenant_train.py::train_tenant_model` verifica autorização local antes do treino e filtra eventos por tenant | Testes de autorização existentes; cobertura de todos os chamadores pendente | Parcial; persistência da decisão por run/dataset não comprovada |
| RB-GOV-009 | `backend/app/services/shared_training_guard.py::require_shared_training_authorization` bloqueia lista vazia e qualquer tenant negado | `test_shared_training_guard.py` listado na suíte existente; resultado específico não reexecutado nesta fase | Parcial; chamada obrigatória por todos os pipelines não demonstrada |
| RB-SEC-005 | `backend/app/main.py` registra os routers da superfície principal da API | Inspeção do registro de routers, sem teste abrangente | Inventário de superfície iniciado; validação rota a rota pendente |

Não inferir aprovação de teste a partir de sua existência. A validação específica deve ser vinculada ao run/commit que efetivamente a executou.


**Atualização de validação (HEAD `15e39bceaf5492dbf98125d68e4c938c3d9341f4`):** foi adicionado teste de regressão para o HTTP 409 do endpoint legado de treino global. A existência do teste não é evidência de execução; aguardar CI deste HEAD.
