# Conectores de Ingestao — ERPs e LMS

## Visao geral

O Beacon aceita dados de multiplas fontes, todas normalizadas para o schema canonico interno.

```
ERP / LMS / JSON  →  Conector  →  Schema canonico  →  Supabase  →  Risk Score + SHAP
```

## Catalogo

| ID | Sistema | Categoria |
|----|---------|-----------|
| `jacad` | JACAD | ERP |
| `sponte` | Sponte | ERP |
| `sophia` | SophiA (Prima) | ERP |
| `gvcollege` | GVcollege (GVdasa) | ERP |
| `wpensar` / `isaac` | WPensar / Isaac | ERP |
| `moodle` | Moodle | LMS |
| `canvas` | Canvas | LMS |
| `generic` | JSON canonico | Generico |

Legados sem API → upload de planilha (`POST /api/v1/upload`).

## Endpoints

```
GET  /api/v1/connectors
GET  /api/v1/connectors/{id}
POST /api/v1/connectors/{id}/students
POST /api/v1/connectors/{id}/sync
POST /api/v1/connectors/{id}/engagement
POST /api/v1/connectors/{id}/financial
POST /api/v1/ingest/students
POST /api/v1/webhooks/moodle
POST /api/v1/webhooks/canvas
POST /api/v1/webhooks/erp/{id}
```

## Exemplo JACAD

```bash
curl -X POST http://localhost:8000/api/v1/connectors/jacad/students \
  -H "Content-Type: application/json" \
  -d '[{"codigoAluno": "2024001", "nomeAluno": "Ana Silva", "diasAtraso": 18, "frequencia": 72.5, "mediaGeral": 6.8}]'
```

## Schema canonico

```bash
curl -X POST http://localhost:8000/api/v1/ingest/students \
  -H "Content-Type: application/json" \
  -d '{"students": [{"matricula": "2024001", "nome": "Ana Silva", "dias_atraso_boleto": 18}], "source": "meu_etl"}'
```
