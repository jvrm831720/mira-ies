# Mira Frontend

Interface SaaS (Next.js 15 + TypeScript + Tailwind + TanStack Query) para a Mira.

## Telas

- `/login` — e-mail e senha ou código de uso único via WhatsApp
- `/reset-password?token=...` — redefinição de senha por link enviado por e-mail
- `/` — Command Center (KPIs + críticos)
- `/alunos` — lista filtrável
- `/alunos/[id]` — ficha (score, fatores, preview de contato)
- `/importar` — upload CSV/XLSX + auto-score
- `/retencao` — régua com dry-run por padrão
- `/retencao/logs` — InterventionLog
- `/config` — providers, disclaimer do modelo, logout

## Pré-requisitos

1. Backend da Mira rodando (`http://localhost:8000`)
2. Usuário já cadastrado por uma instituição

## Rodar

```bash
cd frontend
cp .env.example .env.local   # ajuste NEXT_PUBLIC_API_URL se preciso
npm install
npm run dev
```

Abra http://localhost:3000 e entre com seu e-mail e senha ou via WhatsApp.

## Variáveis

| Var | Default |
|-----|---------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |

## Stack

Next.js App Router · React 19 · Tailwind · shadcn-style UI · TanStack Query · Sonner

Auth: token Bearer no `localStorage` com a chave `mira_access_token`, enviado nos requests autenticados.
