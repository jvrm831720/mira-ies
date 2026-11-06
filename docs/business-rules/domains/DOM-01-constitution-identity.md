# DOM-01 — Constituição, identidade e princípios

Auditoria em andamento. A Constituição canônica separada não foi localizada na árvore examinada. Fontes: README.md, docs/MOTOR_PREDITIVO.md, docs/AGENTES.md e prompt do fundador.

## RB-CON-001 — Medir retenção real, não apenas entrega
- Decisão APROVADA (prompt fundador); implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: distinguir atividade do canal, engajamento e resultado acadêmico; mensagem enviada/entregue não comprova retenção.
- Dados/atores: coordenação e analytics; InterventionLog, delivery_status, outcome e timestamps.
- Aceite: entrega sem outcome não conta como retenção confirmada; outcome ausente permanece desconhecido.
- Evidência: backend/app/models/intervention.py, docs/RETENTION_EVENTS.md. Risco P1; atribuição causal permanece pendente.

## RB-CON-002 — IA apoia a decisão humana
- Decisão APROVADA; implementação NÃO VERIFICADA globalmente; validação NÃO TESTADA.
- Norma: score e recomendação não são fatos; ações acadêmicas de alto impacto não devem ser automáticas sem política aprovada.
- Evidência: backend/app/api/scoring.py, backend/app/ml/explain.py. Pendente: fundador definir decisões que exigem revisão humana.

## RB-CON-003 — Estados e falhas explícitos
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: distinguir sucesso, falha, pendência, desconhecido e parcial; não afirmar conclusão sem confirmação.
- Evidência: backend/app/services/retention_queue.py, backend/app/models/intervention.py. Risco P1; auditar mensagens de sucesso em todas as telas.
