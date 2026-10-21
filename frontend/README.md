# Beacon Frontend

Interface SaaS (Next.js 15 + TypeScript + Tailwind + TanStack Query) para o Project Beacon.

## Telas

- `/login` — API key (`X-API-Key`)
- `/` — Command Center (KPIs + críticos)
- `/alunos` — lista filtrável
- `/alunos/[id]` — ficha (score, fatores, preview de contato)
- `/importar` — upload CSV/XLSX + auto-score
- `/retencao` — régua com dry-run por padrão
- `/retencao/logs` — InterventionLog
- `/config` — providers, disclaimer do modelo, logout

## Pré-requisitos

1. Backend Beacon rodando (`http://localhost:8000`)
2. Tenant com API key válida (ex.: `DEV_API_KEY` / tenant `default`)

## Rodar

```bash
cd frontend
cp .env.example .env.local   # ajuste NEXT_PUBLIC_API_URL se preciso
npm install
npm run dev
```

Abra http://localhost:3000 e entre com a API key.

## Variáveis

| Var | Default |
|-----|---------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |

## Stack

Next.js App Router · React 19 · Tailwind · shadcn-style UI · TanStack Query · Sonner

Auth: API key no `localStorage`, enviada em todo request como `X-API-Key`.
