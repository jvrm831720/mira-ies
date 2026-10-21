# Project Beacon — Status da Codebase

**Ultima atualizacao:** 21 de Outubro de 2026 (Quarta — Entrega segura v0.5.0)
**Sprint:** 19/10 → 23/10  
**Banco:** Supabase Cloud  
**Versao:** 0.5.0-safe-delivery

## Fase 01 — Ingestao ✅
## Conectores ERP/LMS ✅
## Fase 02 — Motor Preditivo ✅
## Learning Loop (Modelo Hibrido C) ✅

| Item | Status |
|------|--------|
| Artefatos base e por tenant em storage persistente configurável | ✅ |
| Migração automática de `backend/models/trained` para `MODEL_STORAGE_DIR` | ✅ |

## Sistema Multiagente de Retencao (Orquestrador + WhatsApp/E-mail/SMS) ✅ MVP dry-run

| Item | Status |
|------|--------|
| Orquestrador (decide canal, anti-spam, persiste InterventionLog) | ✅ |
| Agentes WhatsApp/E-mail/SMS (dry-run por padrao) | ✅ |
| Providers reais opcionais (Evolution/Resend/Twilio, atras de env vars) | ✅ (contrato protegido; APIs reais ainda não validadas) |
| Colunas telefone/email no Student + migracao Alembic 002 | ✅ |
| API `/api/v1/agents/*` protegida por tenant | ✅ |
| Conectores ERP/LMS extraindo telefone/email do payload nativo | ✅ |
| Fila assincrona / retry (Redis) para volumes grandes | ✅ |
| Opt-out explicito de aluno + bloqueio auditavel | ✅ |
| Idempotência por mensagem + correlation/job/campaign ID | ✅ |
| Reserva antes do envio e bloqueio de fallback ambíguo | ✅ |
| Webhooks de entrega normalizados e deduplicados | ✅ |
| Rate limit por tenant/canal/provider + circuit breaker Redis | ✅ |
| Retry com fila dead-letter | ✅ |
| Ver `docs/AGENTES.md` | |

## Seguranca / Auditoria

| Item | Status |
|------|--------|
| API Key por tenant (X-API-Key) | ✅ |
| Isolamento query por tenant_id | ✅ |
| score_batch ownership check | ✅ |
| force_activate bloqueavel em prod | ✅ |
| model_scope + disclaimer sintetico | ✅ |
| Webhook HMAC (X-Beacon-Signature) | ✅ |
| CORS restrito fora de debug+dev | ✅ |
| SHAP off no batch (sob demanda) | ✅ |
| Alembic baseline + create_all so em dev | ✅ |
| Testes (aliases, rules, security) | ✅ |
| JWT / autenticacao de usuario | ✅ |
| RBAC fino por papel/permissao | ⬜ |
| Dashboard (Fase 03) | ⬜ |
| Model artifacts em storage duravel | ✅ |

## Documentacao
- docs/AUTH.md, MODELO_HIBRIDO.md, MOTOR_PREDITIVO.md, CONECTORES.md, AGENTES.md
