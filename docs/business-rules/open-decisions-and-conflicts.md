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



## Adendo após auditoria dirigida (2026-10-27)

### Isolamento institucional
- Foram examinados endpoints selecionados de risco em `backend/app/api/scoring.py`. Há filtros de tenant nos endpoints de resumo, lista de críticos e consulta individual; o scoring por lote recebe o tenant autenticado.
- Foi adicionado teste de regressão para tentar acessar aluno e lote de A usando credenciais de B.
- **Ainda pendente:** matriz completa de rotas, dependências, exportações, consultas de banco, workers, webhooks, integrações e tarefas assíncronas. A revisão dirigida agora tem inventário separado em [evidências de treino e superfície multi-tenant](audit-evidence/training-and-multitenant-surface.md), mas não é cobertura integral. CI #331 e #332 passaram; isso não substitui a cobertura restante nem staging.

### Governança de modelos
- O resolver considera somente políticas com vigência iniciada e bloqueia treino compartilhado quando não há política vigente aprovada, a política está revogada/expirada, o modo é privado ou o dataset é inelegível.
- O treino institucional consulta autorização local independente; testes existentes cobrem ausência, expiração, revogação e registros incompletos.
- Foi adicionado teste de política futura para verificar que não entra em vigor antes da data.
- **Ainda pendente P0:** persistência de decisões por run/dataset, prova de que todos os caminhos de treino compartilhado usam o guard, revalidação de jobs pendentes após mudança A→B e decisão sobre influência em modelos já treinados. Os testes documentados passaram no CI #331 e o commit documental passou no CI #332; os critérios de auditoria durável e cobertura integral continuam abertos.


## Adendo de evidências de código — 2026-10-27

### Governança de treino
- `POST /api/v1/model/train` responde HTTP 409 e bloqueia o retreinamento global legado (`backend/app/api/scoring.py::retrain_model`). Isso é um controle específico, não prova de que não existam outros caminhos.
- `train_tenant_model` verifica autorização institucional separada antes de atualizar prontidão, filtra eventos pelo tenant e avalia a política para finalidade local (`backend/app/ml/tenant_train.py`). Falta inventariar todos os chamadores desse serviço.
- `require_shared_training_authorization` bloqueia se a lista de contribuintes estiver vazia/inválida ou se qualquer tenant não estiver autorizado (`backend/app/services/shared_training_guard.py`). Ainda falta demonstrar a chamada obrigatória em todos os pipelines e jobs.
- **P0 permanece:** trilha durável por run/dataset, proveniência dos dados materializados, revisão de execuções pendentes em A→B e decisão formal sobre modelos já influenciados.

### Superfície multi-tenant
- `backend/app/main.py` registra routers de upload, scoring, conectores, outcomes, agentes, campanhas, execução de campanhas, webhooks de entrega, autenticação, organização, billing e administração interna.
- O registro de routers é apenas inventário inicial. A inspeção por endpoint de todos esses grupos, mais workers/exports/callbacks, ainda não foi concluída; risco P0 não deve ser rebaixado.

### Status de validação
- O CI #332 foi reportado como aprovado para o commit `2dfb700094831fb50be7aef7e4de771bc26fe98f`; esta rodada de documentação não modifica código de aplicação nem substitui a execução do CI para o novo HEAD.
- Nenhum staging, produção, banco real ou provedor externo foi acessado.
