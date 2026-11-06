# Wave 0.1 — Object Index & Data Experience

## Escopo e referências

- Branch base inspecionada: \`main\` em \`d2c3a1f3fe61e7ac3e40b15489a363781b31ad51\`.
- Wave 0.0: integrada (PR #168); app shell e design tokens reutilizados, não reimplementados.
- Referências locais inspecionadas em 06/11/2026: \`Attio (CRM)(6).zip\` (8 HTMLs e 1 ZIP aninhado), \`Attio(3).zip\` (13 HTMLs). As capturas de Empresas mostram barra de visualizações, cabeçalho compacto, contexto de importação/exportação, menu de ordenação, filtros e ação de nova empresa. As capturas Google mostram inspector do registro. Os estados observáveis foram usados como referência de organização; todo o código é original da MIRA.
- Fonte de verdade: \`docs/DESIGN_SYSTEM.md\`, \`docs/waves/WAVE0_APP_SHELL.md\`, \`MIRA_Plano_Migracao_UX_Attio_v1(1).md\` e Blueprint MIRA.

## Discovery de contratos existentes

- \`GET /api/v1/students\` aceita \`limit\` até 200, sem \`offset\`, paginação ou ordenação global. A tela antiga tentava 500 e depois filtrava 50 localmente — contagem não exaustiva.
- Novo \`GET /api/v1/object-index/students\`: paginação \`limit/offset\`, \`total\` filtrado, ordenação allowlisted, filtros AND tipados, \`view\` categórico, busca e tenant obrigatório. O endpoint legado e os consumidores existentes não foram alterados.
- \`GET /api/v1/native-academic/catalog/overview\` fornece **prévia** limitada a 100 turmas; o Object Index identifica explicitamente limites de filtros/busca locais. Nunca inventar turmas, docentes ou disciplinas ausentes.
- Campanhas usam propostas de permanência; não modificar aprovação, agendamento ou execução de mensagens. O novo índice é apenas a entrada exploratória para o editor já existente.
- \`/alunos?group=<id>\` redireciona à página de grupo com cursor da API oficial; nunca intersectar uma amostra global com uma amostra de membros como se fosse o total do grupo.

## Arquitetura

\`ObjectField<T>\` descreve propriedade estática autorizada pela tela, formatação e sort/filter declarativos.

\`ObjectIndexState\` descreve estado de view (busca, filtros AND, ordenação, colunas, paginação); \`ObjectDataTable<T>\` usa TanStack Table com \`getRowId\` estável, seleção de página, cabeçalhos e propriedades.

\`ObjectIndex<T>\` compõe header, visualizações, filtros, colunas, tabela, paginação, mensagens de prévia e ações seguras. A paginação é feita pela API para Alunos; Campanhas e Turmas usam dados contratualmente limitados, com transparência na UI.

\`mira_object_views\` guarda somente configuração: \`object_key\`, \`name\`, \`config\`, \`config_version\`, owner e tenant. Não guarda registros, SQL, valores de resultados ou PII. É **pessoal**, não compartilhada. Tem RLS forçado por \`app.tenant_id\` **e** \`app.user_id\`. Sem session de usuário ou permissão de objeto, operação negada. O servidor valida campos/operadores; alterações de view não criam autorização de leitura de dados.

O App Shell da Wave 0.0 continua gerindo autenticação, troca de workspace, permissões, feature flags e navegação. Os campos expostos pelos adaptadores de cada tela devem respeitar o contexto autorizado.

## Limitações explícitas

- Não foi criado motor de atributos dinâmicos/EAV, process entries, workflows ou atualizações de registros.
- Visualizações compartilhadas não são oferecidas: dependem de política de acesso e auditoria futura.
- A busca e filtragem de Campanhas e Turmas operam somente sobre os registros efetivamente devolvidos pelas respectivas APIs; aviso de prévia quando houver total superior ao limite da consulta.
- A ordenação de Turmas por colunas remotas ainda depende de suporte do catálogo acadêmico.
- Não introduzir envios, alterações acadêmicas nem pagamentos reais nesta Wave.
- QA visual autenticado e desempenho com bases grandes exigem ambiente de testes e medições verificáveis; não marcar como aprovado antes disso.

## Quality gate

- Backend: Ruff, Pytest no PostgreSQL sem superusuário, RLS de tenant/usuário, grafo Alembic e migração \`066_object_index_views\`.
- Frontend: lint, \`node --test\`, TypeScript \`tsc --noEmit\`, build Next.js.
- Verificar no navegador autenticado desktop, tablet e mobile, contraste/foco, navegação por teclado, seleção em página, filtros, menu de colunas, vistas salvas e alternância entre workspaces.
- **Nenhum deploy automático.** Merge apenas após validação no HEAD final e revisão do diff.
