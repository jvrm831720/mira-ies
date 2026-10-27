# Decisões abertas, conflitos e riscos

Prioridade de acordo com o prompt fundador: P0 risco crítico; P1 alto; P2 médio; P3 baixo. A classificação orienta correção futura, não autoriza mudança funcional.

## P0 — resolver antes de ampliar dados/modelos

1. **Cobertura multi-tenant integral.** Evidência: vários modelos carregam tenant_id e testes isolam campanhas, mas a auditoria de todos os endpoints, exports, conectores, jobs, webhooks e consultas não foi concluída. Responsável: Engenharia/Segurança. Decisão pendente: critérios mínimos de release.
2. **Governança de treino compartilhado.** Resolver política fail-closed existe; falta evidência de auditoria persistente de cada decisão e proveniência por run/dataset. Responsável: ML/Engenharia. Não declarar controle completo até validar todos os callers.
3. **Mudança de modalidade A→B.** Bloquear contribuições futuras é diferente de retirar influência de modelos já treinados. Definir tratamento de runs pendentes, modelos afetados, rollback/retrain/unlearning e obrigação contratual. Responsáveis: fundador + assessoria jurídica/técnica.
4. **Preferências/opt-out.** Confirmar prevalência global e por canal/finalidade em todos os conectores, importações, campanhas e callbacks. Testar sem envio real.

## P1 — alto impacto

5. **Importação de múltiplas bases.** Documentação afirma pré-validação individual, sem join consolidado/atomicidade. Definir tipos de arquivo, identidade, conflito por linha e recuperação.
6. **Autenticação Control Center em staging.** Documentação lista testes pendentes: MFA concorrente, bloqueio/desbloqueio, revogação, cookies/domínio real, Resend/Redis e auditoria persistida.
7. **Auditoria administrativa.** Confirmar atomicidade mutação+evento, integridade append-only, retenção/expurgo e registro de leituras/exportações sensíveis.
8. **Score/calibração e copy.** Confirmar calibração, validade por coorte, freshness, drift e que score não é apresentado como probabilidade causal.
9. **Providers reais e recuperação de envio.** Testar callbacks, assinatura, idempotência, timeout ambíguo, fallback e reconciliação em sandbox/staging.
10. **Retenção e descarte de dados.** Definir inventário por categoria, prazo aprovado, backups, logs, exports e snapshots de treino; não inventar prazo legal.
11. **Central de trabalho.** Definir se existe caso/tarefa formal com responsável, SLA, transições e reabertura ou se a tela agrega alunos/intervenções.

## P2 — comportamento ambíguo

12. **Faturamento:** docs conceituais descrevem catálogo/versionamento de plano, contratos e estados como overdue/refunded; schema atual tem AdminBillingRecord único por tenant e payment_status pendente/pago. A decisão confirmada é cobrança manual; não implementar gateway sem aprovação.
13. **Papéis:** documentação lista super_admin, operations, finance, support, auditor; a matriz completa de permissões e todos os perfis institucionais não foi verificada endpoint a endpoint.
14. **KPI:** falta catálogo de fórmula/denominador, timezone, janela, filtros, origem e limites de atribuição para todos os indicadores.
15. **Desativação institucional:** definir efeito sobre jobs já enfileirados, webhooks, sessões, canais e artefatos.

## Recomendações que ainda não são decisões aprovadas
- Dupla aprovação/reautenticação para ações críticas selecionadas.
- Estado “dados insuficientes/desconhecido” explícito para scoring.
- Catálogo obrigatório de KPIs com snapshot reproduzível.
- Política de exclusão lógica por padrão com inventário de dependências.
- Teste de restore e plano de rollback em staging antes de releases com migrações.

## Decisões que exigem fundador/responsável de produto
- Quais decisões acadêmicas exigem revisão humana obrigatória.
- Política A→B para modelos já influenciados e runs pendentes.
- Contrato e finalidade permitida para cada categoria de dado de treino.
- Semântica de Central de trabalho/casos e SLAs.
- Métricas oficiais de retenção e metodologia de atribuição.
- Ações que exigem dupla aprovação e matriz final de papéis.
- Política comercial/financeira além do registro manual atual.

## Dependências jurídicas/contratuais
Revisão especializada para base legal/finalidade, evidência de autorização de treino, revogação, retenção, exclusão, direitos de titulares, transferências a provedores e uso de modelos já treinados. Este documento não declara conformidade com a LGPD.
