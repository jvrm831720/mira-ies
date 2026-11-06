# MIRA — Wave 0.2: Record Experience

Data: 2026-11-06
Branch: feat/product-design-wave-0-2-record-experience
Dependência concluída por operação concorrente: Wave 0.1, PR #171, mesclada em main em a53c0c7953af73517e16d8f28c8adbc2b9f144d6 em 06/11/2026. A PR #174 agora tem base main; o merge da #171 não foi executado por esta IA. A conexão Git da Vercel comprovadamente publicou main em production anteriormente; releases continuam bloqueados neste fluxo e o autoDeploy de Render ainda requer confirmação do workspace pelo usuário. As correções posteriores ao merge #171 (Object Index RBAC e filtros sensíveis) permanecem nesta PR #174.

## Referências e discovery

Pacotes HTML Attio (CRM)(6).zip e Attio(3).zip inspecionados. Capturas específicas: Google - Attio (05_11_2026 14：54：50).html; Google - Attio (05_11_2026 14：00：25).html; Empresas | Todas as Empresas. Evidências HTML: overlay identificado, "Detalhes do registro", "Ver todos os valores", "Atividade" e lista no contexto da abertura. Padrões inspiram composição; nenhum código, ativo ou marca da Attio foi copiado. Fonte de verdade: docs/DESIGN_SYSTEM.md e docs/waves/WAVE0_APP_SHELL.md.

A implementação de StudentDrawer e /alunos/[id] usa GET /students/{id}/risk. A ficha original contém comunicação, log de retenção, opt-out, prévia de mensagem sem envio e painel acadêmico condicional. StudentWorkTimeline e workApi.getTimeline() mostram risk_assessment, intervention_log, work_activity, engagement_event. A API do org/me informa permissões efetivas. Campanhas preservam a aprovação, o agendamento e o formulário existentes.

## Componentes compartilhados

- record-types.ts: RecordIdentity, RecordPropertyGroup, RecordActivityEvent, RecordRelation, RecordAction, RecordSection.
- record-preview.tsx: referência compacta opcional.
- record-drawer.tsx: overlay responsivo com trap de foco, Escape, fechar e abrir página.
- record-page.tsx e record-heading.tsx: ficha completa e identidade consistente.
- record-properties.tsx: propriedades tipadas; editar apenas com callback permitido.
- record-activity.tsx e record-activity-utils.ts: cronologia de eventos reais, sem mensagens/notas internas.
- record-relations.tsx: vínculos com links apenas quando disponíveis e autorizados.
- record-actions.tsx: ações explicitamente habilitadas.
- record-sections.tsx: abas acessíveis com teclado.
- student-record-data.ts e student-record-activity.tsx: adaptadores específicos do aluno.

Demonstrações: StudentDrawer + página completa /alunos/[id]; preview de Propostas de Campanhas usando RecordDrawer/RecordProperties/RecordActivity/RecordSections sem alterar o motor.

## Segurança e performance

Nenhuma migration nem API de escrita acadêmica/financeira na Wave 0.2. Campos oficiais e risk-score são apenas leitura. Dados financeiros, médias, frequência, risco e timeline estão atrás de students.sensitive.view; edição das preferências usa students.edit. Ausência de score não equivale a baixo risco. O endpoint institucional `GET /students/{id}/risk` agora exige `students.view` para sessão humana e faz projeção no servidor: viewer/operator sem `students.sensitive.view` não recebem score, SHAP, notas, indicadores acadêmicos privados, situação financeira nem preferências de comunicação na resposta. Cargos personalizados respeitam grants efetivos, sem herdar admin; chaves de integração legadas mantêm contrato anterior. Testes `backend/tests/test_record_rbac_wave02.py` cobrem esses casos. Trata-se de mudança intencional de exposição de dados para sessões humanas sem permissão sensível. A timeline ignora eventos desconhecidos e não serializa refs.payload, notas internas ou mensagens. Consultas TanStack Query usam as chaves existentes, e o shell esvazia cache na troca de workspace; timeline somente é montada ao abrir a seção. As relações não inventam IDs inexistentes. A edição de atributos genéricos não é exposta sem endpoint e callback aprovados.

Fora de escopo: Portal do Aluno, sessão estudantil, execução de disparos, Workflow Experience da IA 02, mutações acadêmicas, pagamentos e contatos reais.

## QA / aceite e publicação

CI no HEAD final obrigatório: ESLint, testes Node, TypeScript, build Next.js, Ruff, pytest e Alembic. QA desktop/mobile em navegador autenticado não pode ser declarado se não houver ambiente autorizado. A PR #171 já consta como integrada por outra operação. A PR #174 agora usa main como base e deve ter CI final no HEAD, revisão de permissões e QA autenticado antes de qualquer merge. Nenhuma alteração de configuração de publicação ou deploy/migration de produção foi executada nesta Wave.
