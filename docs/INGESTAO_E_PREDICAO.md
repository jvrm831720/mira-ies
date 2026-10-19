# Ingestão de Dados + Análise Preditiva

## Fluxo completo

```
Planilha ERP → Upload → Normalização → Validação/Limpeza
                                      → Deduplicação
                                      → Persistência (Supabase)
                                      → Feature Engineering
                                      → XGBoost (Risk Score)
                                      → SHAP (Top 3 fatores)
                                      → Atualização no banco
```

---

## Colunas da planilha

### Obrigatórias
| Coluna     | Descrição                    |
|------------|------------------------------|
| `matricula` | Identificador único do aluno |
| `nome`     | Nome completo                |

### Recomendadas
| Coluna                | Descrição                    |
|-----------------------|------------------------------|
| `dias_atraso_boleto`  | Dias de atraso do boleto     |
| `recorrencia_atrasos` | Quantas vezes atrasou antes  |
| `dias_sem_login`      | Dias sem acesso ao AVA/LMS   |
| `presenca_percentual` | % de presença (0–100)        |
| `nota_media`          | Média geral (0–10)           |
| `reprovacoes`         | Quantidade de reprovações    |
| `semestre`            | Semestre/período atual       |

Endpoint: `GET /api/v1/upload/expected-columns`

---

## O que a ingestão faz

1. Encoding (UTF-8, Latin-1, CP1252)
2. Normalização de nomes de colunas
3. Aliases de ERP (50+)
4. Validação de ranges
5. Descarte de linhas inválidas
6. Deduplicação por matrícula
7. Relatório de qualidade (quality_score 0–100)

---

## Risk Score

- 0–39 → **baixo**
- 40–69 → **médio**
- 70–100 → **crítico**
