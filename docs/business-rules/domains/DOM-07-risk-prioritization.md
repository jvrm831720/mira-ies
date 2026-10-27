# DOM-07 — Inteligência, risco e priorização

## RB-RSK-001 — Faixas de score explícitas
- Decisão APROVADA na documentação atual; confirmar versão canônica. Implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE.
- Norma: score 0–100; docs atuais indicam 0–39 baixo, 40–69 médio e 70–100 crítico.
- Ator/dados: scoring, regras, SHAP, Student.risk_score/risk_level e versão de modelo. Dados inválidos/ausentes seguem tratamento explícito.
- Aceite: testar 0,39,40,69,70,100 e entradas ausentes/inválidas.
- Evidência: backend/app/ml/scoring.py, backend/app/ml/rules.py, backend/app/api/scoring.py, docs/MOTOR_PREDITIVO.md, tests test_rules.py/test_scoring_api.py. Risco P1; calibração por coorte não auditada profundamente.

## RB-RSK-002 — Score não é probabilidade sem validação
- Decisão APROVADA (prompt fundador); implementação PARCIALMENTE IMPLEMENTADA; validação NÃO TESTADA para copy global.
- Norma: não rotular score como probabilidade individual calibrada sem evidência estatística apropriada; métricas de validação não provam causalidade.
- Aceite: API/UI mostram versão e limites; auditoria de copy e drift.
- Evidência: backend/app/ml/model.py, backend/app/api/scoring.py, docs/MOTOR_PREDITIVO.md. Risco P1.

## RB-RSK-003 — Desconhecido não é baixo
- Decisão APROVADA (prompt fundador); implementação NÃO VERIFICADA globalmente; validação NÃO TESTADA.
- Norma: dados insuficientes/desatualizados não devem virar risco baixo por padrão.
- Evidência a revisar: backend/app/ml/features.py e scoring.py. Pendente: frescor, elegibilidade e estados de insuficiência. Risco P1.
