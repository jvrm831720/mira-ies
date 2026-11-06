# Catálogo central de regras de negócio

Catálogo de referência da fase 1. Os IDs são estáveis; o detalhamento por domínio está em `domains/DOM-XX-*.md`. Os status refletem apenas o escopo inspecionado em 2026-10-27, commit `e25858b4cb12dab781b19e0ed46cf193007fb520`.

| ID | Regra | Domínio | Decisão | Implementação | Validação | Prioridade |
|---|---|---|---|---|---|---|
| RB-CON-001 | Priorizar retenção real sobre métrica de envio | DOM-01 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P1 |
| RB-SEC-001 | Contexto tenant resolvido no servidor; não confiar no tenant do payload | DOM-02 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P0 |
| RB-AUT-001 | Control Center tem identidade administrativa separada | DOM-03 | APROVADA | IMPLEMENTADA — EVIDÊNCIA ENCONTRADA | TESTADA PARCIALMENTE | P0 |
| RB-RBAC-001 | Toda ação protegida valida permissão no backend | DOM-04 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P0 |
| RB-AUD-001 | Ações administrativas sensíveis deixam trilha minimizada | DOM-05 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P1 |
| RB-IMP-001 | Prévia de importação não persiste dados | DOM-06 | APROVADA | IMPLEMENTADA — EVIDÊNCIA ENCONTRADA | TESTADA PARCIALMENTE | P1 |
| RB-IMP-002 | Matrícula é chave explícita de identidade no tenant | DOM-06 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P0 |
| RB-RSK-001 | Score e faixa de risco têm limites definidos | DOM-07 | APROVADA | IMPLEMENTADA — EVIDÊNCIA ENCONTRADA | TESTADA PARCIALMENTE | P1 |
| RB-OPS-001 | Caso/fila de trabalho tem ciclo de vida próprio do cadastro de aluno | DOM-08 | PENDENTE | NÃO VERIFICADA | NÃO TESTADA | P2 |
| RB-INT-001 | Opt-out global bloqueia contato automatizado | DOM-09 | APROVADA | IMPLEMENTADA — EVIDÊNCIA ENCONTRADA | TESTADA PARCIALMENTE | P0 |
| RB-INT-002 | Envio, entrega, leitura, resposta e retenção são estados distintos | DOM-09/10 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P1 |
| RB-ANA-001 | KPI tem fórmula, período, filtro e denominador definidos | DOM-10 | RECOMENDAÇÃO | PARCIALMENTE IMPLEMENTADA | NÃO TESTADA | P1 |
| RB-GOV-001 | Treinamento compartilhado exige política aprovada e elegibilidade | DOM-11 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P0 |
| RB-GOV-002 | Treino institucional exige autorização independente | DOM-11 | APROVADA | IMPLEMENTADA — EVIDÊNCIA ENCONTRADA | TESTADA PARCIALMENTE | P0 |
| RB-CC-001 | Control Center é interno; cobrança atual é registro manual | DOM-12 | APROVADA | IMPLEMENTADA — EVIDÊNCIA ENCONTRADA | TESTADA PARCIALMENTE | P1 |
| RB-API-001 | Integração autenticada tem escopo por tenant e erros seguros | DOM-13 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P0 |
| RB-UX-001 | Interface não pode afirmar sucesso sem confirmação do backend | DOM-14 | APROVADA | NÃO VERIFICADA | NÃO TESTADA | P1 |
| RB-REL-001 | Falhas assíncronas precisam de retry limitado e dead-letter consultável com isolamento | DOM-15 | APROVADA | IMPLEMENTADA — EVIDÊNCIA ENCONTRADA | TESTADA PARCIALMENTE | P1 |
| RB-ENV-001 | Migração e liberação exigem CI e validação do ambiente-alvo | DOM-16 | APROVADA | PARCIALMENTE IMPLEMENTADA | TESTADA PARCIALMENTE | P1 |
| RB-PRI-001 | Coleta, retenção e exclusão devem ser documentadas sem inventar prazos legais | DOM-17 | APROVADA | PARCIALMENTE IMPLEMENTADA | NÃO TESTADA | P1 |
| RB-EXT-001 | Domínio adicional é inventariado quando houver funcionalidade própria | DOM-18 | APROVADA | PARCIALMENTE IMPLEMENTADA | NÃO TESTADA | P2 |

## Inventário por domínio

- DOM-01 Constituição e identidade
- DOM-02 Instituições e isolamento
- DOM-03 Autenticação e sessões
- DOM-04 Usuários, perfis e permissões
- DOM-05 Governança e auditoria
- DOM-06 Importação, qualidade e identidade
- DOM-07 Risco e priorização
- DOM-08 Casos e Central de trabalho
- DOM-09 Intervenções, campanhas e agentes
- DOM-10 Resultados e analytics
- DOM-11 Governança de dados e modelos
- DOM-12 Control Center e faturamento
- DOM-13 Integrações e processamento assíncrono
- DOM-14 Interface e estados
- DOM-15 Observabilidade e continuidade
- DOM-16 Configuração e evolução
- DOM-17 Privacidade e ciclo de vida
- DOM-18 Outros domínios descobertos

Este catálogo não afirma que o inventário de regras está completo. A contagem crescerá durante a auditoria detalhada; novas regras devem receber IDs exclusivos por domínio.
