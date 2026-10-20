# Project Beacon

**Plataforma de Predição e Retenção Ativa de Alunos**

MVP SaaS que une **Análise Preditiva de Evasão** + **Sistema Multiagente de Retenção**, focado em PMEs educacionais.

> Identifica alunos em risco → explica os fatores (SHAP) → dispara comunicação personalizada.

```
Motor Preditivo → Agente Orquestrador → WhatsApp | E-mail | SMS
```

Ver `docs/AGENTES.md` para a arquitetura completa do sistema multiagente de retenção.

---

## Objetivo do MVP (Sprint 19–23 Out 2026)

1. Upload de planilha (CSV/XLSX)
2. Risk Score 0–100 + Top 3 fatores SHAP
3. Dashboard para coordenação
4. Sistema multiagente de retenção (Orquestrador + WhatsApp/E-mail/SMS, modo dry-run)

---

## Stack

| Camada | Tecnologia |
|--------|------------|
| Backend | FastAPI + Python |
| ML | XGBoost + SHAP |
| Banco | Supabase (PostgreSQL) |
| Frontend (próximo) | Streamlit → Next.js |
| Agentes de Retenção | Orquestrador próprio (dry-run) + Evolution API (WhatsApp) / Resend (e-mail) / Twilio (SMS), todos opcionais |

---

## Como rodar

```bash
cp .env.example .env
# Cole a DATABASE_URL do Supabase (postgresql+asyncpg://...)

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### Teste rápido

```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -F "file=@data/sample/alunos_exemplo.csv"

curl http://localhost:8000/api/v1/risk/summary
curl http://localhost:8000/api/v1/risk/critical
```

---

## Endpoints principais

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/v1/upload` | Upload + score automático |
| GET | `/api/v1/risk/summary` | Contagem por nível |
| GET | `/api/v1/risk/critical` | Fila de críticos |
| GET | `/api/v1/students/{id}/risk` | Ficha + SHAP |
| POST | `/api/v1/predict` | Predição avulsa |
| GET | `/api/v1/model/info` | Metadados do modelo |
| POST | `/api/v1/agents/retention/run` | Roda o Orquestrador (dry-run por padrão) |
| GET | `/api/v1/agents/retention/logs` | Histórico de intervenções |
| GET | `/api/v1/agents/retention/preview/{id}` | Mensagem sem enviar |

---

## LGPD

- Base legal: Art. 7º V e IX
- Minimização de dados
- Opt-out nos canais de mensagem

Veja `STATUS.md` para o progresso do sprint.
