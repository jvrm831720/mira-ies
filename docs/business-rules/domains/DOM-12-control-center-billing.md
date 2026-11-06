# DOM-12 — Control Center e faturamento

## RB-CC-001 — Console interno
Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE. O Control Center é interno e não faz parte da experiência comercial institucional. Evidência: docs/MIRA_CONTROL_CENTER.md, backend/app/models/control_center.py, backend/app/api/control_center_admin.py e control_center_auth.py. Risco P0 se houver mistura de identidades.

## RB-CC-002 — Financeiro manual
Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE. A primeira fase registra plano, link HTTPS, vencimento e status manual; não processa cartão nem confirma pagamento via navegador. Evidência: backend/app/models/control_center.py, backend/app/api/control_center_admin.py, docs/CONTROL_CENTER_MANUAL_BILLING.md. Um registro por tenant. Pendência: modelo atual é mais simples que estados conceituais descritos em documentação antiga; ver decisões abertas. Risco P1.
