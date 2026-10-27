# Relatório executivo — auditoria de regras MIRA, fase 1

**Data:** 2026-10-27  
**Base:** `main` commit `e25858b4cb12dab781b19e0ed46cf193007fb520`  
**Branch documental:** `docs/business-rules-audit-2026-10`  
**Estado:** entrega parcial rastreável; auditoria completa ainda não concluída.

## Entregue nesta fase

- Índice e legenda de status.
- Constituição/princípios provisórios, catálogo inicial, matriz preliminar de papéis, inventário de máquinas de estado, governança de dados/modelos, critérios de aceite, rastreabilidade, decisões abertas e gestão de mudanças.
- Inventário inicial dos domínios DOM-01 a DOM-18.
- Identificação explícita de riscos P0/P1, conflitos documentais e decisões que exigem fundador ou revisão especializada.

## Principais achados

- O repositório contém mecanismos concretos de multi-tenancy, autenticação institucional e interna, ingestão, scoring, intervenções, campanhas versionadas, jobs, webhooks e governança de treino.
- A existência de tenant_id/modelos/rotas não prova isolamento universal; é necessário cobrir todos os endpoints e caminhos assíncronos.
- A política de treino fail-closed e a autorização institucional separada existem; a auditoria persistente de cada decisão no pipeline global não foi comprovada.
- A transição de modalidade A→B bloqueia futuras contribuições segundo a política, mas o tratamento de runs pendentes e influência de modelos existentes requer decisão formal.
- A importação multi-file pré-valida arquivos; não se deve presumir junção consolidada ou persistência atômica.
- O Control Center é interno e o faturamento atual é manual; não é gateway de pagamento.
- Staging hospedado, integrações reais e teste de recuperação não foram executados nesta auditoria.

## Contagens

Catálogo inicial: 21 regras transversais/representativas listadas no catálogo central. A documentação de domínio contém regras detalhadas iniciais e lacunas, mas a contagem completa por status não deve ser tratada como definitiva: os 18 domínios ainda não tiveram todas as rotas, jobs, configs, migrations e testes examinados individualmente. A contagem formal completa fica **pendente** para não produzir número enganoso.

## Validação executada

- Inspeção de arquivos e metadados de `main` via GitHub.
- CI GitHub Actions run #328 da PR #47, anterior ao merge: backend lint/test e frontend lint/build concluíram com sucesso.
- Não executei suíte local nesta tarefa; não acessei staging, produção, banco real, provedores ou contratos assinados.
- Links internos e referências serão revisados antes da abertura da PR.

## Garantias de escopo

Não houve alteração funcional, migration, escrita em banco, mudança de configuração de produção, merge na `main` ou deploy como parte desta auditoria. A documentação será entregue em branch separada para revisão. Não declarar a missão concluída enquanto houver domínios relevantes sem auditoria detalhada.



## Fase 2 — auditoria dirigida (2026-10-27)

A auditoria foi aprofundada nos dois riscos prioritários sem tocar na aplicação: isolamento institucional e governança de treinamento.

- Criado `backend/tests/test_governance_audit_edges.py` com cenários para negar leitura/scoring cross-tenant de aluno/lote e respeitar a data de vigência de uma política.
- Revisados `backend/app/api/scoring.py`, `backend/app/services/training_policy.py`, `backend/app/services/shared_training_guard.py`, modelos de política/autorização e testes existentes de governança.
- Evidência observada: endpoints de risco consultados filtram por tenant autenticado; o resolver ignora políticas futuras e o guard compartilhado bloqueia o lote inteiro se qualquer contribuinte for negado.
- Limitação crítica: o guard é uma função de serviço e não há, nesta inspeção, prova de que todos os caminhos futuros/indiretos a chamem; o retorno de decisão não equivale a uma trilha de auditoria persistida por run/dataset.
- GitHub Actions run #331 terminou com sucesso: lint/test do backend e lint/build do frontend passaram para o commit 34388663091e8701f05ee776326ab20fe51bbf8b. Staging/produção não foram acessados; CI verde não comprova comportamento em ambiente hospedado.
- Escopo respeitado: apenas teste e documentação nesta branch; nenhuma alteração funcional, migration, banco, `main` ou deploy.


## Fase 3 — caminhos de treinamento e superfície da API (2026-10-27)

A inspeção dirigida acrescentou evidência sobre três fronteiras de treinamento e iniciou o inventário da superfície multi-tenant:

- O endpoint legado `POST /api/v1/model/train` responde 409 e não executa retreinamento global.
- O serviço de treino institucional verifica autorização independente antes de atualizar prontidão e filtra eventos por tenant.
- O guard de treino compartilhado falha fechado para lista vazia/inválida e bloqueia a operação inteira quando qualquer instituição contribuinte é negada.
- O registro central da API mostra routers para upload, scoring, conectores, outcomes, agentes, campanhas, execução de campanhas, webhooks, autenticação, organização, billing e administração.

**Não significa conclusão:** ainda não está demonstrado que todos os callers de treino usam os gates, que as decisões são persistidas por run/dataset ou que todas as rotas/exports/workers/webhooks preservam isolamento. A regra de release permanece: não declarar governança compartilhada ou isolamento multi-tenant completos sem inventário e testes abrangentes.

Esta atualização é documental. Nenhum arquivo de aplicação, migration, banco, configuração de produção, `main` ou deploy foi alterado. O CI #332 aprovado pertence ao HEAD anterior; o novo commit documental precisa de sua própria verificação automatizada.
