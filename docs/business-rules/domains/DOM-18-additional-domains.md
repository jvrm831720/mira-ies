# DOM-18 — Outros domínios descobertos

## RB-EXT-001 — Inventário evolutivo
- Decisão APROVADA pelo prompt fundador; implementação PARCIALMENTE IMPLEMENTADA; validação NÃO TESTADA.
- Norma: serviço, entidade ou fluxo relevante não fica fora do catálogo por não constar do escopo inicial.
- Descobertas: conectores ERP/LMS, smart import, campanhas versionadas, fila Redis/dead-letter, webhooks, métricas de providers, outcomes para alvo evasion_90d_v1, faturamento manual, autenticação interna e governança de treino.
- Evidência: docs/CONECTORES.md, docs/INGESTAO_E_PREDICAO.md, docs/RETENTION_RULE_ENGINE.md, docs/AGENTES.md, docs/MODELO_HIBRIDO.md e modelos/serviços correspondentes.
- Aceite: cada novo domínio recebe ID, regra, status e evidência. Risco P2.

## Escopo não verificado nesta fase
Gestão formal de incidentes; backup/restore; solicitações de titulares; contratos completos de integrações; limites comerciais por instituição; SLA e política de incidentes. Não declarar auditoria completa enquanto não forem examinados.
