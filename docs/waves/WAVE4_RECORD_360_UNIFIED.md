# MIRA — Wave 4 · Ficha 360 unificada

## Escopo

Base: Wave 3 (main e54ab7cd). Não altera onboarding, autenticação, predição, disparos, cobranças, gateways ou operações financeiras.

A Wave 4 preserva o domínio de cada objeto enquanto padroniza a moldura operacional: drawer, página, propriedades, relações, timeline, estados assíncronos, ações autorizadas e retorno à lista.

| Capacidade | Aluno | Caso financeiro |
|---|---|---|
| Preview | StudentDrawer → RecordDrawer (mantido) | CollectionCaseDrawer → RecordDrawer |
| Ficha completa | /alunos/[id] → RecordPage (mantido) | /cobranca/casos/[id] → RecordPage |
| Adaptador | student-record-data | collection-record-data |
| Propriedades/relações | Record360Overview | Record360Overview |
| Timeline | StudentRecordActivity | CollectionCaseRecord, até 100 eventos |
| Ações | Atualizar, contato somente com autorização; consentimento legado com students.edit | Apenas Atualizar; nenhuma edição ou execução |

## Paridade e segurança

- A ficha do aluno mantém risco, fatores, score, campanhas, comunicação, permissões e auditoria de consentimento.
- O componente antigo collection-case-detail.tsx permanece no repositório para comparação/rollback; a listagem passa a usar RecordDrawer.
- As relações com subject_ref são informativas. Referência externa de aluno não é necessariamente UUID da MIRA, portanto não gera link automático.
- Saldos, estados e eventos financeiros são projeções somente leitura de GET /api/v1/collections/cases/{id}, condicionadas a audit.view e ao tenant do servidor.
- Não existe ação de editar saldo, criar acordo, cobrar ou pagar na ficha financeira. A lista de campos editáveis do adaptador é vazia.
- Eventos exibem metadados limitados às fontes documentadas. Os 100 eventos máximos e a flag payment_events_limited geram nota de cobertura parcial. Dados de origem não equivalem a comprovante bancário.
- Busca, ordenação, filtro e paginação permanecem processados no servidor da listagem.
- A permissão da lista, drawer e página de cobrança é a mesma função canReadCollectionRecord; API e RLS prevalecem sobre o frontend.

## Retorno ao contexto

- collectionDetailHref só monta o detalhe para UUID validado.
- collectionReturnHref aceita unicamente /cobranca com query; descarta o parâmetro record e rejeita URLs externas, caminhos diferentes e fragments.
- O RecordDrawer restaura o foco ao fechar, mas não durante expansão para página completa.
- Estado contextual permanece na URL de origem, sem guardar dados do registro no endereço.

## Testes e aceite

Frontend: frontend/tests/record-360-wave4.test.mjs e regressões anteriores record-experience.test.mjs, navigation-context.test.mjs.
Backend: tests/test_record_rbac_wave02.py e tests/test_collections_wave07.py.

Executar frontend npm test, npm run lint, npx tsc --noEmit e npm run build. Executar backend pytest de casos financeiros e RBAC.

Verificar em duas instituições/workspaces: abrir drawer, expandir, voltar mantendo filtros e página; ausência de dados; timeline com limite; perfil negado; nenhuma edição financeira; ações do aluno mantidas apenas quando autorizadas; Back/Forward, foco e teclado.

Os componentes legados devem ser mantidos até a validação autenticada em produção; o PR não executa migrações nem deploys.
