# Wave 0.3 — Workflow Experience (preparação em branch isolada)

## Base, independências e gate de publicação
- Base inicial: `main` em `d2c3a1f3fe61e7ac3e40b15489a363781b31ad51`.
- Dependências: PR #171 (Object Index) e PR #172 (Student Portal) **ainda não integradas** no início desta Wave. Rebase/merge-base e CI final serão obrigatórios após a integração e a confirmação da IA 01 sobre publicação automática.
- **Não fazer merge/deploy/migration de produção.** O workflow GitHub `.github/workflows/deploy-cloudflare.yml` dispara em `push: main` para `frontend/**`, portanto até mesmo o merge de UI pode publicar sem autorização. `frontend/vercel.json` não desabilita o CI Cloudflare.
- Alteração compartilhada planejada: **uma entrada em `frontend/src/components/layout/navigation.ts`**, com `campaigns.view` e módulo `operations`. Exceção pontual documentada previamente para preservar o caminho de navegação; confirmar diff com o trabalho paralelo antes do merge.
- Não editar `frontend/src/components/object-index/`, `frontend/src/components/students/` nem fichas administrativas.

## Discovery — HTML da Attio fornecido
Arquivos de `Attio (CRM)(7).zip`: quatro capturas `Fluxo de trabalho sem título` de 05/11/2026, 13:06–13:20. Evidências extraídas das capturas (não são protótipos completos): abas Editor / Corridas / Configurações; estados Rascunho / Ao vivo e aviso de alterações não publicadas; canvas com gatilho e bloco; 100% de zoom, botão Organizar blocos; inspector contextual com campos, obrigatoriedade e próximo bloco; histórico vazio honesto; diagnóstico de erro por bloco. O ZIP não documenta execução real nem configurações de todos os gatilhos. Adotamos composição, hierarquia, densidade e feedback; componentes MIRA originais.

## Discovery — contratos reais da MIRA
| Fonte | Leitura disponível | Mutação real que já existe | Permissão/limite |
|---|---|---|---|
| Propostas de permanência | `GET /agents/retention/campaigns/intelligence/proposals` | `PATCH .../proposals/{id}` em draft/changes_requested | GET require_min_role coordinator. PATCH exige usuário humano MFA/AAL2, regras de revisão e revision. `execution_enabled: false`. |
| Auditoria de propostas | `GET .../proposals/{id}/audit` | nenhuma | Coordinator + humano MFA; eventos reais versionados. |
| Agendamento de proposta | `GET .../schedule` | agendar/remover via API existente | Apenas metadados; **não executa** nem dispara. |
| Disparos | `GET /dispatch/campaigns`, `GET /dispatch/campaigns/{id}` | ações explícitas no console atual | `campaigns.view`; detalhe usa tenant na consulta. Estados próprios, itens operacionais limitados a 100. Sem POST neste editor. |
| Histórico real de importação Composio | `GET /dispatch/composio/imports` | ingestão com política específica fora desta Wave | `campaigns.view`, tenant-scoped; cada run possui id/status/timestamps/contagens/erro. Não é execução da proposta de permanência e não deve aparecer como se fosse. |
| Aprovação Composio | `GET /integrations/composio/approvals` | review via políticas específicas | `settings.manage` e MFA; não habilitado como bloco executor. |

**Invariantes:** `proposal.status=approved` não comprova envio; `scheduled` não comprova job. Um dispatch vinculado a uma proposta somente é exibido como evidência se `dispatch.origin_proposal_id === proposal.id`. `dispatch.accepted` corresponde a itens em estados de aceitação configurados no serviço, não a recuperação financeira. Sem runs vinculados, UI declara ausência de evidência em vez de fabricar histórico.

## Estrutura de produto
1. **Index:** propostas de permanência para usuários coordinator/admin e campanhas de disparo para operadores com `campaigns.view`; filtros por categoria/estado e estados vazios/erros.
2. **Detail e canvas:** DAG de apresentação **determinístico**, derivado de registros existentes; não persistimos nós nem criamos uma definição versionada. Os blocos representam etapas de negócio e a evidência (registrado/aguardando/não disponível), não um motor conectado. Zoom, teclado, seleção, links externos.
3. **Node Inspector:** detalhes reais, dependências, permissão, estágio e origem. Edição apenas de campos efetivamente persistíveis de propostas draft via PATCH já existente; confirmação explícita e backend autoritativo; nenhuma operação sensível por arrastar bloco.
4. **History / Run Detail:** auditoria de propostas; itens de dispatch no detalhe; importações Composio como execuções reais **separadas**, identificador e erro conhecidos. Não relacionar Composio import a um workflow de permanência sem vínculo no backend.
5. **Permissions:** exibir explicitamente `campaigns.view`, `campaigns.edit`, `campaigns.approve`, `campaigns.execute`; ACL real aplicada pelos endpoints existentes. O editor jamais apresenta botão `Start/Send/Approve` que acione execução.
6. **Composio:** indicar ferramentas externas como futuro/indisponível; nenhum executor, nenhuma credencial nem toolkit genérico é exposto.

## O que NÃO será construído nesta etapa
- CRUD de definições gráficas arbitrárias (API não existe).
- Triggers novos, conectores executáveis, versões editoriais publicáveis, undo/redo persistente.
- Runs sintéticos, retries de entrega ou aprovações silenciosas.
- Histórico por etapa de uma execução de retenção se não houver um run-id correlacionado.
- Qualquer motor paralelo de cobrança ou disparo.

## QA e gates antes da revisão
- CI frontend: lint, `node --test`, TypeScript, build. CI backend: Alembic, RLS, Ruff e pytest no HEAD.
- Testes de regras de estado, permissão, nenhuma requisição de execução, existência de componentes e rotas.
- Checagem manual autenticada desktop/tablet/mobile e teclado, dados conhecidos/sujeitos a falha; **não afirmar QA visual até ser realizado**.
- Confirmar CI/head/rebase após #171 e #172; manter esta PR draft até essa etapa e o isolamento de publicação.
