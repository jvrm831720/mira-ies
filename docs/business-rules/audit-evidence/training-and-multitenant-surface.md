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

## Fase 4 — revisão por fronteiras de execução (2026-10-27)

### Achados adicionais sobre treinamento

| ID | Evidência examinada na main | Resultado verificável | Lacuna / decisão |
|---|---|---|---|
| TRN-08 | backend/app/services/shared_training_dataset.py::build_shared_training_events | Chama require_shared_training_authorization antes da consulta a TrainingEvent; consulta somente tenants autorizados e eventos rotulados com TARGET_DEFINITION_VERSION. | O construtor é um ponto de entrada protegido. Não foi provado que todo consumidor de dataset compartilhado use exclusivamente esse construtor. O baseline global atual é descrito como sintético; manter essa afirmação vinculada ao caminho examinado. |
| TRN-09 | backend/app/ml/tenant_train.py e backend/app/models/tenant.py::ModelArtifact | O treino local revalida autorização institucional no serviço, filtra eventos pelo tenant, cria artefato candidato inativo com run_id, versão e métricas. | No trecho de criação do artefato, não são gravados campos dedicados para policy ID, institutional authorization ID, fingerprint imutável do dataset ou lista exata de contribuintes. Métricas contêm contagens e definição do alvo, mas a trilha completa por run/dataset não ficou demonstrada. |
| TRN-10 | backend/app/api/outcomes.py::train_tenant_endpoint | Exige tenant autenticado e require_tenant_match antes de chamar o treino. | A rota usa get_current_tenant, não require_min_role ou _require_model_approver. Decidir explicitamente se uma credencial de API do tenant pode disparar treino, inclusive force=true sujeito à configuração. Não classificado como vulnerabilidade sem a política de acesso esperada. |

### Fronteiras multi-tenant com evidência positiva parcial

- **Conectores:** backend/app/api/connectors.py usa autenticação de tenant nos endpoints de ingestão e passa tenant_id/tenant_slug do contexto autenticado ao pipeline; rotas de webhook verificam assinatura antes de ingerir. O catálogo de conectores é público e aparenta retornar metadados estáticos, sem dados de tenant. Falta testar cada conector e serviço de destino.
- **Resultados de aprendizagem:** backend/app/api/outcomes.py compara o slug informado com o tenant autenticado; consultas de eventos, updates de outcomes e ciclo de vida dos artefatos incluem tenant nas consultas examinadas. A cobertura completa das rotas de lifecycle continua pendente.
- **Campanhas:** backend/app/api/retention_campaigns.py filtra campanhas por tenant e o avaliador seleciona alunos e logs de intervenção do tenant da campanha. Falta E2E cruzado para simulação, versões, status e execução.
- **Fila:** backend/app/services/retention_queue.py persiste tenant_id no job e get_job aceita filtro de tenant. A rota de status passa o tenant autenticado; a rota dead-letter lê IDs da fila global, mas só adiciona ao resultado jobs retornados por get_job(..., tenant_id=auth.tenant_id). Falta verificar o worker real, revalidação de autorização antes do efeito externo, retries e isolamento de logs.
- **Webhook de entrega:** backend/app/api/delivery_webhooks.py resolve o tenant ativo pelo ID do caminho, valida HMAC com o segredo desse tenant e encaminha o evento com esse tenant_id. Falta cobertura de assinatura inválida, replay/idempotência e confirmação de que todo lookup do evento de destino permanece tenant-scoped.
- **Upload:** rotas de histórico, status e listagem de alunos usam tenant autenticado; mutações de preferências consultam o aluno com ID e tenant. A auditoria não abrange todas as 898 linhas nem cada combinação de rota/filtro.

### Conclusão desta fase

A evidência examinada reforça que há controles concretos em vários caminhos, mas não autoriza concluir isolamento universal. Nenhum defeito de cross-tenant foi confirmado nesta amostra adicional; as lacunas indicadas são ausência de prova, teste ou decisão explícita, salvo se uma verificação posterior demonstrar comportamento incorreto.


## Fase 5 — ciclo de vida do worker de retenção (2026-10-27)

**Base inspecionada:** `main`; leitura estática de `backend/app/worker.py`, `backend/app/services/retention_queue.py`, `backend/app/agents/orchestrator.py`, `backend/app/core/auth.py` e testes de fila/entrega. Nenhum envio, serviço externo, banco de staging/produção ou alteração funcional foi executado. Esta seção registra evidência do código e lacunas de cobertura; não declara vulnerabilidade explorada.

### Evidências e achados

| ID | Controle/caminho | Evidência observada | Estado / impacto não comprovado |
|---|---|---|---|
| RET-01 | Consumo do worker — `backend/app/worker.py::run_worker` | O worker promove itens atrasados e consome IDs com `BLPOP`, chamando `process_retention_job`. Não há, no loop inspecionado, varredura de jobs persistidos em `running` nem re-enfileiramento de IDs abandonados. | **Lacuna concreta de recuperação no caminho inspecionado.** Se o processo cair após `BLPOP`, o ID já foi removido da fila. Não foi encontrado um mecanismo alternativo que recupere automaticamente o job; o resultado exato depende do ponto da queda e da expiração do registro. |
| RET-02 | Lock — `backend/app/services/retention_queue.py::process_retention_job` | Adquire lock com `SET ... EX 900 NX`, grava `running`, executa o orquestrador e apaga a chave no `finally`. Não foi observada renovação/heartbeat do lock. | **Lacuna concreta de lease/recuperação.** Uma execução que exceda 900 s pode perder o lock. Se o job for disponibilizado novamente enquanto a primeira execução continua, pode haver concorrência; não foi reproduzida execução duplicada. |
| RET-03 | Promoção de atrasados — `promote_due_retries` | Faz `ZRANGEBYSCORE`, depois `ZREM`, depois atualizações de estado e `RPUSH`, em comandos separados. | **Janela não atômica confirmada no código.** Queda após `ZREM` e antes de `RPUSH` pode remover o ID do conjunto atrasado sem colocá-lo na fila pronta. Chamadas concorrentes também podem ler os mesmos IDs antes da remoção e enfileirar duplicatas. Não há teste cobrindo falha entre comandos ou concorrência entre promotores. |
| RET-04 | Retry/DLQ | Exceções capturadas antes do limite de tentativas são agendadas com backoff exponencial; após esgotar tentativas, o job passa a `dead_letter` e seu ID é adicionado à fila DLQ. | **Caminho feliz coberto; recuperação de processo não.** Não foi observada reconciliação para job abandonado por queda abrupta, nem atomicidade entre gravar `dead_letter` e adicionar o ID à DLQ. |
| RET-05 | Instituição ativa na execução | `get_current_tenant` exige `Tenant.is_active == True` ao autenticar a requisição que enfileira o job. O worker usa o `tenant_id` persistido no job e instancia o orquestrador; não foi observada consulta/revalidação de `Tenant.is_active` no início do processamento. | **Não comprovado no limite assíncrono.** Uma instituição desativada depois do enqueue pode continuar com jobs pendentes executáveis, salvo controle externo não examinado. Não classificar como exploração confirmada. |
| RET-06 | Preferências imediatamente antes do envio | O orquestrador filtra alunos ativos por tenant e verifica opt-out/preferências no caminho de seleção; no trecho de envio examinado não foi encontrada uma segunda leitura explícita imediatamente antes da chamada externa. | **Janela de concorrência permanece.** Não há evidência de reprodução de envio após opt-out concorrente. |
| RET-07 | Callback de entrega | `apply_delivery_event` filtra o log por tenant, ignora repetição do último `event_id` e rejeita certas transições regressivas; opt-out consulta o aluno por ID e tenant. | **Controles positivos parciais.** O dedupe guarda o último ID de evento no log, não um registro global de todos os eventos vistos. Testes de replay fora de ordem, callbacks concorrentes, mesmo ID externo entre tenants e múltiplos eventos repetidos não foram identificados nesta amostra. |

### Cobertura de testes observada na main

- `backend/tests/test_retention_queue_reliability.py` cobre idempotência de enqueue por tenant, retry exponencial em exceção sintética, envio para DLQ após esgotar tentativas, promoção de um item vencido e isolamento na consulta de status.
- `backend/tests/test_agent_delivery_safety.py` cobre resultado de provedor ambíguo sem fallback para outro canal e reutilização de chave de idempotência para um envio já reservado.
- `backend/tests/test_consent_governance.py` cobre preferências granulares/auditadas, isolamento dos endpoints de preferência e aplicação de opt-out recebido por webhook.
- Na amostra de testes lida, **não foi encontrado** teste que simule: queda depois de `BLPOP`; job preso em `running`; lock expirado com execução ainda ativa; falha entre `ZREM` e `RPUSH`; dois promotores concorrentes; tenant desativado após enqueue; mudança de opt-out entre seleção e envio; crash após aceite do provedor antes de persistir o resultado; ou replay/concor­rência de callbacks. Esta afirmação limita-se aos arquivos examinados, não a todo o repositório.

### Matriz de status atualizada

| Controle | Estado |
|---|---|
| Filtro de aluno por tenant e `Student.is_active` | Comprovado no caminho de seleção |
| Autenticação da instituição ativa ao enfileirar | Comprovada na dependência de API inspecionada |
| Revalidação da instituição ativa pelo worker | Não identificada |
| Verificação inicial de opt-out/preferências | Comprovada |
| Revalidação imediatamente antes do envio | Não identificada |
| Retry por exceção capturada e DLQ após limite | Comprovado no caminho normal |
| Recuperação de job abandonado em `running` | Não identificada |
| Renovação/heartbeat do lock de 900 s | Não identificada |
| Promoção atômica de retries | Não; operações separadas observadas |
| Dedupe básico de callback e rejeição de alguns estados regressivos | Comprovado parcialmente |
| Replay concorrente/fora de ordem de callbacks | Cobertura insuficiente |

### Próximos testes de auditoria — sem alterar aplicação nesta fase

1. Teste controlado de worker interrompido após retirar o ID da fila e após gravar `running`; verificar se há mecanismo real de recuperação.
2. Teste de execução superior ao TTL do lock, com segunda tentativa concorrente, verificando se duas execuções podem avançar.
3. Injeção de falha entre `ZREM` e `RPUSH`, e execução concorrente de dois promotores; verificar perda/duplicação de IDs.
4. Enfileirar com tenant ativo e desativá-lo antes do processamento; observar se o worker bloqueia o job antes de qualquer efeito externo.
5. Mudar opt-out/preferência após a seleção do aluno e antes do envio; confirmar se o caminho real revalida a permissão.
6. Simular provedor aceitando a mensagem e timeout/quebra antes de persistir resultado; avaliar reconciliação e idempotência do provedor.
7. Repetir e reordenar callbacks, incluindo eventos concorrentes, e validar o estado final e o registro de engajamento.

**Conclusão desta fase:** há isolamento por tenant no caminho de seleção, idempotência e tratamento de erros no caminho normal. Contudo, a recuperação após consumo destrutivo da fila, a expiração do lock, a promoção não atômica de retries e a revalidação de permissões no limite de execução permanecem lacunas relevantes. Não foi realizado teste dinâmico e não se afirma que uma exploração ocorreu.


## Fase 6 — recuperação, concorrência e callbacks do worker (2026-10-27)

**Escopo:** leitura estática de `main`; nenhum teste foi executado nesta rodada, nenhum envio foi realizado e nenhum serviço externo ou banco de produção/staging foi acionado. Nenhum código funcional foi alterado. As conclusões abaixo distinguem comportamento diretamente observado de cenários condicionais.

### Produtores e consumidores encontrados

- `backend/app/api/agents.py::enqueue_retention` enfileira jobs usando o tenant autenticado; para `optimize_send_time`, seleciona alunos por tenant, verifica a permissão de comunicação no agendamento e cria um job por aluno com `scheduled_at`.
- `backend/app/worker.py::run_worker` promove itens vencidos e consome a fila por `BLPOP`, chamando `process_retention_job`.
- `backend/app/api/agents.py::retention_job_status` consulta o job com `get_job(job_id, tenant_id=auth.tenant_id)`.
- Na amostra de diretórios/arquivos consultada, não foi identificado outro scheduler de recuperação de jobs abandonados. Isso não prova sua inexistência em todos os componentes ou infraestrutura externa.

### Achados complementares

| ID | Caminho | Evidência observada | Avaliação |
|---|---|---|---|
| RET-08 | Propriedade do lock em `process_retention_job` | O lock usa valor constante `"1"`, TTL de 900 s e remoção incondicional via `DELETE` no `finally`. | Se a primeira execução ultrapassar o TTL, uma segunda execução adquirir o lock e a primeira terminar depois, o `finally` da primeira poderá apagar a chave da segunda. Risco de concorrência concreto no desenho, condicionado à expiração; não reproduzido. |
| RET-09 | Estado durante promoção de retries | `promote_due_retries` remove IDs vencidos do sorted set, altera para `queued` somente jobs com estado `scheduled`, mas faz `RPUSH` para a lista inteira de IDs retornados que ainda tenham registro. | Jobs em estados como `running`, `retrying` ou `completed` podem ser recolocados na fila se ainda estiverem no conjunto atrasado. O efeito final depende das guardas de `process_retention_job`; não foi reproduzido. |
| RET-10 | Autenticidade de webhook | `receive_delivery_webhook` verifica tenant ativo e assinatura HMAC sobre o corpo bruto com o segredo daquele tenant antes de normalizar/aplicar o evento. Segredo ausente falha fechado fora da exceção de desenvolvimento explicitamente configurada. | Controle positivo de autenticidade observado. |
| RET-11 | Replay de webhook | A verificação HMAC inspecionada não inclui timestamp, nonce ou janela de validade. O serviço calcula um ID/hash do evento e compara apenas com `log.delivery_event_id`, que representa o último evento registrado; também bloqueia algumas transições regressivas. | Não foi demonstrada proteção temporal contra replay. O dedupe do último evento e as regras de transição reduzem alguns efeitos, mas não equivalem a um registro de todos os eventos vistos nem a um mecanismo geral anti-replay. Sem teste dinâmico, não se afirma exploração confirmada. |
| RET-12 | Testes de webhook | `test_agent_delivery_safety.py` cobre normalização de payloads de provedores e distingue `delivered` de `read`; `test_security_pure.py` contém um teste HMAC puro que compara o cálculo esperado, mas não chama o endpoint real. | Na lista de testes consultada, não foi localizado teste de endpoint para assinatura inválida, segredo/tenant incorreto, replay, concorrência de callbacks ou transições fora de ordem. Limita-se aos arquivos consultados. |

### Revalidação do tenant e do consentimento no worker

- `get_current_tenant` verifica `Tenant.is_active` durante a requisição que cria o job. No caminho de execução do worker examinado, o `tenant_id` persistido é passado ao orquestrador sem uma nova leitura explícita do estado ativo do tenant.
- O fluxo de seleção de alunos verifica tenant, atividade do aluno, opt-out e preferências de comunicação. Não foi identificada uma segunda leitura explícita de consentimento imediatamente antes da chamada ao provedor.
- Ambos são limites de autorização relevantes em processamento assíncrono. A possibilidade de desativação/opt-out concorrente permanece um risco condicional; não há reprodução nesta auditoria.

### Cobertura verificada nesta rodada

- A listagem de `backend/tests` contém `test_retention_queue_reliability.py`, `test_provider_guard.py`, `test_agent_delivery_safety.py` e `test_consent_governance.py`, entre outros.
- Os testes de fila cobrem caminhos normais de retry, DLQ, promoção de item vencido e isolamento da consulta por tenant; os testes de guard cobrem `SET NX` e liberação após falha definitiva.
- Não foi executado pytest nesta rodada. Ausência de teste específico na amostra inspecionada não deve ser generalizada para qualquer teste ou mecanismo externo não consultado.

### Próximas verificações recomendadas

1. Testar em ambiente isolado a queda após `BLPOP` e verificar se jobs `running` são reconciliados por algum componente.
2. Testar expiração do lock e garantir que uma execução antiga não remova o lock de uma execução mais nova; avaliar lock com token de proprietário e renovação/lease.
3. Simular concorrência e falhas entre `ZREM`, atualização do estado e `RPUSH`; definir transição de estado válida antes de re-enfileirar qualquer ID.
4. Testar tenant desativado e opt-out alterado depois do enqueue/seleção, assegurando bloqueio antes de qualquer chamada externa.
5. Exercitar o endpoint de webhook com HMAC inválido, segredo incorreto, replay idêntico, replay antigo após outro evento e eventos concorrentes/fora de ordem.
6. Definir se o contrato dos provedores suporta consulta/reconciliação de mensagens aceitas sem confirmação local.

**Conclusão da Fase 6:** foram confirmados controles úteis de autenticação HMAC, isolamento por tenant em consultas específicas e idempotência básica de envio. Permanecem lacunas no caminho de recuperação do worker, na propriedade do lock, na atomicidade da promoção e na proteção geral contra replay de webhook. Os cenários de concorrência e falha continuam riscos potenciais até serem testados; não houve teste dinâmico nem correção nesta rodada.
