# Autenticacao — Project Beacon

## Modelo

- Cada **tenant** possui uma **API key** (`bkn_...`).
- A key e gerada em `POST /api/v1/tenants` e **exibida uma unica vez**.
- So o **hash** HMAC-SHA256 fica no banco (`api_key_hash`).
- Rotas de dados exigem:

```
X-API-Key: bkn_...
```

Ou: `Authorization: Bearer bkn_...`

## Rotas publicas

- `GET /`, `GET /docs`, `GET /openapi.json`
- `GET /api/v1/connectors` (catalogo)
- `GET /api/v1/model/info` (opcional)

## Desenvolvimento

```bash
export DEV_API_KEY=bkn_dev_change_me_in_production
curl -H "X-API-Key: $DEV_API_KEY" http://localhost:8000/api/v1/tenants
```

## Criar tenant (producao)

```bash
curl -X POST http://localhost:8000/api/v1/tenants \
  -H "Content-Type: application/json" \
  -H "X-Admin-Secret: $SECRET_KEY" \
  -d '{"slug":"ies-alfa","name":"IES Alfa"}'
```

Guarde `api_key` e `webhook_secret` — nao serao reexibidos.

## Isolamento

- `tenant_slug` no body nao pode divergir da key.
- Risk/alunos filtram por `tenant_id` da key.
