# Evidências dirigidas — caminhos de treino e superfície multi-tenant

**Data da revisão:** 2026-10-27  
**Base de código inspecionada:** `main` em `e25858b4cb12dab781b19e0ed46cf193007fb520`. A documentação deste arquivo é entregue na branch `docs/business-rules-audit-2026-10`; nenhuma alteração de aplicação é proposta aqui.

## Escopo e limite da evidência

Esta revisão rastreia os pontos de entrada de treinamento que foram localizados e uma amostra de superfícies API/assíncronas com risco de fronteira entre instituições. É uma auditoria dirigida, **não** uma certificação de que todos os caminhos ou todos os filtros multi-tenant foram verificados. O resultado deve ser usado como inventário para a próxima rodada de testes.

## Governança de treinamento — caminhos identificados

| ID | Caminho | Evidência observada | Status / lacuna |
|---|---|---|---|
| TRN-01 | `backend/app/api/scoring.py::retrain_model` — `POST /model/train` | O endpoint retorna HTTP 409 e informa que o treino global legado está bloqueado. | **Evidência encontrada.** Testar que a rota permanece bloqueada em todos os ambientes de aplicação. |
| TRN-02 | `backend/app/ml/tenant_train.py::train_tenant_model` | Resolve autorização institucional separada antes do treino; carrega eventos filtrados por `tenant.id`; depois resolve política para `institutional_training`; cria `ModelArtifact` como candidato inativo. | **Parcialmente coberto.** A política é verificada, mas a decisão de autorização/política e a referência exata de dataset não são visivelmente gravadas como um evento imutável associado ao `run_id` no trecho inspecionado. |
| TRN-03 | `backend/app/services/shared_training_dataset.py::build_shared_training_events` | Chama `require_shared_training_authorization` antes de consultar `TrainingEvent`; só consulta tenants autorizados e eventos rotulados com a definição de alvo vigente. | **Evidência encontrada no ponto de entrada conhecido.** É necessário provar que todo consumidor futuro/indireto usa este construtor e que não há outro caminho que materialize dados para o treino global. |
| TRN-04 | `backend/app/services/shared_training_guard.py::require_shared_training_authorization` | Exige lista de tenants contribuintes não vazia, evidência de elegibilidade e bloqueia a operação inteira se um tenant for negado. | **Parcialmente coberto.** O guard retorna decisões em memória; retorno de decisão não equivale a auditoria persistida por execução/dataset. |
| TRN-05 | `backend/app/services/training_policy.py::resolve_training_policy` | Seleciona a política efetiva e aplica negação por padrão ao treino compartilhado; políticas futuras não devem ser aplicadas antes de `effective_at`. | **Teste de regressão existente.** CI #331 passou no commit `34388663091e8701f05ee776326ab20fe51bbf8b`; CI #332 também passou no commit documental `2dfb700094831fb50be7aef7e4de771bc26fe98f`. |
| TRN-06 | `backend/app/api/outcomes.py::train_tenant_endpoint` | Endpoint de treino institucional chama o fluxo de treino por tenant. | **Ponto de entrada de API identificado.** Confirmar autorização de papel/tenant e comportamento após revogação em teste de integração. |
| TRN-07 | `backend/app/api/mira_admin.py` — `/runs`, `/datasets`, `/authorizations`, `/audit` | Existem leituras administrativas para runs, datasets, autorizações e auditoria com permissões dedicadas. | **Evidência de consulta, não prova de completude.** Confirmar se cada run inclui policy/authorization IDs, dataset fingerprint, contributing tenant IDs, decisão efetiva e versão contratual. |

### Critérios obrigatórios ainda sem comprovação integral

1. Um inventário automatizado de referências a funções de treino, estimadores, serialização de modelos e criação de datasets não deve encontrar caminhos compartilhados sem gate.
2. Toda execução deve persistir, antes de ler/materializar dados e antes de ajustar o modelo, a decisão por tenant e finalidade, os IDs de políticas/autorização, vigência, referência contratual, elegibilidade, dataset fingerprint e lista de contribuintes.
3. A autorização deve ser revalidada no limite da execução; um job enfileirado não deve manter permissão que foi revogada antes de começar.
4. Se qualquer instituição contribuinte não estiver autorizada, a execução compartilhada inteira deve falhar sem materializar parcialmente os dados.
5. A mudança A→B deve bloquear contribuições novas e disparar revisão rastreável de jobs pendentes e modelos já influenciados. A política de retreino, rollback, unlearning ou tratamento contratual continua sendo decisão aberta; não presumir que retirar dados do próximo dataset apaga influência anterior.
6. Separar explicitamente baseline global sintético, treino institucional exclusivo e treino compartilhado autorizado. A existência de um modelo base sintético não prova que todos os pipelines futuros estejam livres de dados de tenants.

## Superfície multi-tenant examinada

| Área | Arquivos/pontos examinados | Evidência observada | Lacuna / próximo teste |
|---|---|---|---|
| Scoring e risco | `backend/app/api/scoring.py`, `backend/app/ml/scoring.py` | Consulta individual, lote e eventos de treino usam tenant; endpoints selecionados têm teste de tentativa de acesso cruzado em `test_governance_audit_edges.py`. | Cobrir todos os endpoints, combinações de filtros, IDs inválidos/estrangeiros e respostas de erro sem vazamento. |
| Resultados e modelos | `backend/app/api/outcomes.py` | Busca de eventos e artefatos filtra por tenant; rotas de ciclo de vida verificam artefato e tenant. | Testar todas as rotas de aprovar/ativar/rollback/desativar e acesso a modelos base versus tenant. |
| Campanhas de retenção | `backend/app/api/retention_campaigns.py`, `backend/app/api/retention_campaign_execution.py` | Helpers de busca, campanhas e logs usam tenant. | Cobrir campanha de outro tenant, IDs de aluno cruzados, dry-run/simulate/run e mutações de versão/status. |
| Agentes e fila | `backend/app/api/agents.py`, `backend/app/services/retention_queue.py` | A fila grava `tenant_id`; `get_job` pode exigir correspondência de tenant; logs operacionais registram tenant e status sem conteúdo de mensagem. | Testar job/status/dead-letter cruzado, corrida de idempotência, retry e revalidação do tenant antes da execução. |
| Ingestão e conectores | `backend/app/api/connectors.py`, `backend/app/services/connectors/pipeline.py`, `backend/app/api/upload.py` | Pipeline exige `tenant_id`; os conectores autenticados passam o tenant do contexto de autenticação. | Inventariar importações, arquivos temporários, listagem/download de lotes e toda operação de ingestão em testes cruzados. |
| Webhooks de entrega | `backend/app/api/delivery_webhooks.py`, `backend/app/services/delivery_webhooks.py` | Endpoint recebe `tenant_id`, valida assinatura com segredo do tenant e atualiza logs usando filtro de tenant. | Testar assinatura ausente/inválida, tenant inexistente, IDs de log estrangeiros, replay/idempotência e eventos de status inesperados. |
| Organização/membros | `backend/app/api/org.py` | Consultas de membros e convites são filtradas por tenant; aceitação de convite resolve o tenant do convite. | Testar convite adulterado, expirado/revogado, troca de tenant e IDs de usuário de outra organização. |
| Administração de governança | `backend/app/api/mira_admin.py` | Rotas exigem permissões administrativas de leitura de governança/auditoria. | Confirmar matriz de permissões e isolamento por papel; acesso administrativo global é intencional e deve ser auditado. |

## Plano de teste priorizado

- **P0 — isolamento:** para cada endpoint com identificador de recurso, repetir chamadas com credenciais do tenant A e ID criado pelo tenant B; confirmar 404/403 ou resposta vazia conforme contrato, sem campos, contagens ou metadados de B.
- **P0 — treino compartilhado:** tenants A e B contribuem; revogar B ou mudar B para modalidade exclusiva; execução deve falhar antes da materialização/ajuste e gerar registro durável da negação.
- **P0 — fila:** enfileirar enquanto A está autorizado, revogar antes do processamento e verificar bloqueio/reconciliação do job.
- **P0 — proveniência:** criar run e verificar que o registro contém decisão, política/autorização, versão contratual, fingerprint do dataset, contribuintes, versão do código/modelo e estado de aprovação/ativação.
- **P1 — webhooks/conectores:** tenant A não consegue associar eventos ou ingestão a recursos de B, mesmo conhecendo IDs.
- **P1 — exportações e dados derivados:** mapear e testar cada export, download, analytics, dead-letter, log administrativo, backup e artefato derivado.
- **P1 — regressão de autorização:** executar os testes relevantes após alterações em modelos, migrations, routers, workers ou pipelines.

## Decisão e status

- **Decisão:** as modalidades A/B e a separação de autorização institucional/compartilhada continuam sendo o padrão documentado.
- **Implementação:** há gates em pontos identificados; cobertura integral e auditoria durável por execução/dataset não estão comprovadas.
- **Validação:** CI #331 e #332 passaram; isso valida os checks executados, não todos os critérios acima nem staging/produção.
- **Mudança A→B:** continua decisão pendente do responsável de produto/fundador com assessoria jurídica/técnica.
