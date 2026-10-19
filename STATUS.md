# Project Beacon — Status da Codebase

**Última atualização:** 19 de Outubro de 2026 (Segunda — Ingestão + Predição endurecidas)  
**Sprint:** 19/10 → 23/10  
**Banco:** Supabase Cloud  
**Versão:** 0.2.1

---

## Legenda

| Símbolo | Significado |
|---------|-------------|
| ✅ | Implementado |
| 🟡 | Parcial |
| ⬜ | Não iniciado |
| ❌ | Fora do escopo desta semana |

---

## Fase 01 — Ingestão (endurecida) ✅

| Item | Status | Observação |
|------|--------|----------|
| Upload CSV/XLSX | ✅ | Multi-encoding (UTF-8, Latin-1, CP1252) |
| Normalização de colunas | ✅ | 50+ aliases de ERPs brasileiros |
| Validação de ranges | ✅ | Presença 0–100, nota 0–10, etc. |
| Descarte de linhas inválidas | ✅ | Sem matrícula/nome |
| Deduplicação por matrícula | ✅ | Mantém última ocorrência |
| Relatório de qualidade | ✅ | quality_score 0–100 + warnings |
| `GET /upload/expected-columns` | ✅ | Documentação para a secretaria |
| Persistência Supabase | ✅ | UploadBatch + Student |
| Auto-score após upload | ✅ | Default `auto_score=true` |

---

## Fase 02 — Motor Preditivo (endurecido) ✅

| Item | Status | Observação |
|------|--------|----------|
| Feature engineering (12 features) | ✅ | 7 originais + 5 derivadas |
| Defaults conservadores | ✅ | Não inflacionam risco quando falta dado |
| XGBoost + treino sintético | ✅ | Auto-treino no startup |
| Risk Score 0–100 + níveis | ✅ | baixo / medio / critico |
| SHAP Top 3 (robusto) | ✅ | Compatível com várias versões do SHAP |
| Explicação em português | ✅ | Frase legível para coordenação |
| Persistência score + SHAP | ✅ | |
| Endpoints de risco | ✅ | summary, critical, ficha, predict |
| Feature importance global | ✅ | `GET /model/feature-importance` |
| Sample data (25 alunos) | ✅ | Casos variados de risco |

---

## Fase 03 — Dashboard ⬜

| Item | Status |
|------|--------|
| Streamlit consumindo as APIs | ⬜ |
| Visão consolidada | ⬜ |
| Fila de críticos | ⬜ |
| Ficha + SHAP | ⬜ |

---

## Fase 04 — WhatsApp ⬜

| Item | Status |
|------|--------|
| Evolution API / WAHA | ⬜ |
| Disparo para críticos | ⬜ |

---

## Fase 05 — Demo ⬜

---

## Documentação

- `README.md` — visão geral + como rodar
- `STATUS.md` — este arquivo
- `docs/MOTOR_PREDITIVO.md` — detalhes do modelo
- `docs/INGESTAO_E_PREDICAO.md` — fluxo completo, colunas, qualidade

---

## Como validar agora

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Colunas esperadas
curl http://localhost:8000/api/v1/upload/expected-columns

# Upload + score
curl -X POST "http://localhost:8000/api/v1/upload" \
  -F "file=@../data/sample/alunos_exemplo.csv"

# Resumo
curl http://localhost:8000/api/v1/risk/summary

# Críticos
curl http://localhost:8000/api/v1/risk/critical

# Importância das features
curl http://localhost:8000/api/v1/model/feature-importance
```
