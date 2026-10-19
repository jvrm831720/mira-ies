# Motor Preditivo de Risco — v0.3.1

## Arquitetura hibrida

```
Features (17) → XGBoost → Calibracao isotonica → Score 0-100
                                                    ↓
                                            Regras de negocio
                                                    ↓
                                         Score ajustado + acoes
                                                    ↓
                                              SHAP Top 3
```

## Niveis

| Score | Nivel | Acao |
|-------|-------|------|
| 0–39 | baixo | Monitoramento |
| 40–69 | medio | Preventivo |
| 70–100 | critico | Fila prioritaria |

## Features (17)

Originais, flags e interacoes (risco_financeiro, risco_engajamento, risco_academico, combo_critico, pressao_inicial).

## Endpoints

- POST `/predict` — predicao + regras + acoes
- POST `/predict/what-if` — simula intervencoes
- GET `/risk/critical` — fila critica + acoes
- GET `/model/info` — AUC, Brier, top features
- POST `/model/train` — retreino
