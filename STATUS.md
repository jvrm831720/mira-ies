# Project Beacon — Status da Codebase

**Ultima atualizacao:** 19 de Outubro de 2026 (Segunda — Conectores ERP/LMS)  
**Sprint:** 19/10 → 23/10  
**Banco:** Supabase Cloud  
**Versao:** 0.3.0

---

## Legenda

| Simbolo | Significado |
|---------|-------------|
| ✅ | Implementado |
| 🟡 | Parcial |
| ⬜ | Nao iniciado |
| ❌ | Fora do escopo desta semana |

---

## Fase 01 — Ingestao (endurecida) ✅

| Item | Status | Observacao |
|------|--------|----------|
| Upload CSV/XLSX | ✅ | Multi-encoding |
| Normalizacao de colunas | ✅ | 50+ aliases ERP |
| Validacao / dedupe / quality | ✅ | |
| Persistencia Supabase | ✅ | |
| Auto-score apos upload | ✅ | |

---

## Conectores ERP/LMS (Ingestao multi-fonte) ✅

| Item | Status | Observacao |
|------|--------|----------|
| Catalogo GET /connectors | ✅ | |
| JACAD | ✅ | /connectors/jacad/students |
| Sponte | ✅ | /connectors/sponte/students |
| SophiA (Prima) | ✅ | /connectors/sophia/students |
| GVcollege (GVdasa) | ✅ | /connectors/gvcollege/students |
| WPensar / Isaac | ✅ | /connectors/wpensar/students |
| Moodle | ✅ | engagement + webhook |
| Canvas | ✅ | engagement + webhook |
| JSON canonico | ✅ | POST /ingest/students |
| Webhooks ERP | ✅ | /webhooks/erp/{id} |
| Pipeline unificado | ✅ | transform → persist → score |

---

## Fase 02 — Motor Preditivo ✅

| Item | Status |
|------|--------|
| XGBoost + SHAP Top 3 | ✅ |
| Risk Score 0-100 | ✅ |
| Endpoints de risco | ✅ |

---

## Fase 03 — Dashboard ⬜

## Fase 04 — WhatsApp ⬜

## Fase 05 — Demo ⬜

---

## Documentacao

- README.md
- STATUS.md
- docs/MOTOR_PREDITIVO.md
- docs/INGESTAO_E_PREDICAO.md
- docs/CONECTORES.md

---

## Como validar

```bash
curl http://localhost:8000/api/v1/connectors

curl -X POST http://localhost:8000/api/v1/connectors/jacad/students \
  -H "Content-Type: application/json" \
  -d '[{"codigoAluno":"2024001","nomeAluno":"Ana Silva","diasAtraso":18,"mediaGeral":6.8}]'
```
