# Beacon Frontend

Interface SaaS do Project Beacon (Next.js 15 + TypeScript + Tailwind).

## Setup

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Abra http://localhost:3000 e entre com a API key do tenant (`X-API-Key`).

Backend default: `http://localhost:8000`.

## Telas

| Rota | Função |
|------|--------|
| `/login` | API key |
| `/` | Central de comando |
| `/alunos` | Lista filtrável |
| `/alunos/[id]` | Ficha + preview |
| `/importar` | Upload CSV/XLSX |
| `/retencao` | Régua dry-run |
| `/retencao/logs` | Logs |
| `/config` | Providers e sair |
