# Wave 0.5 — Dispatch & Campaign Operations

## Base, ownership and gate

- Repositório: `jvrm831720/mira-ies`.
- Base da branch: `main` em `208ec56091cdc5be606c60cc94e8942bc105dc3c` (Wave 0.3 já integrada).
- Branch: `feat/product-design-wave-0-5-dispatch`.
- Trabalho paralelo: PR #174 (Record Experience) **ainda aberta**, Data Hub 0.4 em outra IA. Não editar `/campanhas/page.tsx`, `/disparos/importacoes`, `/conectores`, `/importar`, `/importacoes`, `components/record`, `components/object-index`, `components/workflows`, Composio, migrations, workers nem motor de execução.
- A MIRA **não possui isolamento entre merge e publicação**: Render `mira-api-testes` em `main` com `autoDeploy=yes`/commit e start command que tenta `alembic upgrade head`. Vercel publica `main` como `production`; `.github/workflows/deploy-cloudflare.yml` também tem `push: main` para `frontend/**`. **Não mesclar sem gate de release verificado.**
- Nenhuma alteração de ambiente, envio real, gatilho de worker, banco, migration ou deploy feita nesta Wave.

## E1 — Discovery: fontes de verdade

Documentação inspecionada: `docs/DISPATCH_PLATFORM_ALIGNMENT.md`, `docs/DISPATCH_PLATFORM_WAVES_1_4.md`, `docs/DISPATCH_COMPOSIO_INGESTION.md`, `docs/DISPATCH_SOURCE_SIGNING.md`, `docs/waves/WAVE0_3_WORKFLOW_EXPERIENCE.md`, `docs/DESIGN_SYSTEM.md`.

Capturas inspecionadas: `Attio(5).zip` (13 HTMLs) e `Attio (CRM)(8).zip` (8 HTMLs + ZIP aninhado). Padrões observados: índice com visualizações, painel lateral de empresa, lista compacta, navegação contextual, inspectores e densidade. São referências de linguagem e interação. Não reutilizar código, marca nem ativos.

### Contratos reais auditados

| Objeto/fluxo | Endpoint/serviço existente | Permissão | Limite observado |
|---|---|---|---|
| Origens | `GET /api/v1/dispatch/sources` | `campaigns.view` | metadata; não executa tool Composio |
| Campanhas operacionais | `GET /api/v1/dispatch/campaigns` | `campaigns.view` | 50 recentes por padrão (max 100), sem offset/count |
| Campanha / itens | `GET /api/v1/dispatch/campaigns/{id}` | `campaigns.view` | até 100 itens; sem paginação global |
| Métricas | `GET /api/v1/dispatch/metrics` | `campaigns.view` | agregado tenant-wide; accepted inclui sent/delivered/read/replied |
| Respostas | `GET /api/v1/dispatch/campaigns/{id}/replies` | `campaigns.view` | eventos persistidos |
| Modelos | `GET/POST /api/v1/dispatch/templates`; approve | view/create/approve | aprovação humana existente |
| Provedores | `GET/PUT /api/v1/dispatch/providers`, verify/activate/disable | `settings.manage` | Resend e Twilio (sem expor segredos) |
| Novo rascunho | `POST /api/v1/dispatch/campaigns` | `campaigns.create` | somente draft; valida source, perfil e política |
| Destinatários | `POST /api/v1/dispatch/campaigns/{id}/targets` | `campaigns.edit` | autorização por pessoa, máximo 1000 |
| Aprovação / agendamento / execução | `POST /campaigns/{id}/approve`, `/schedule`, `/{action}` | approve/execute | MFA, consentimento, políticas e flags no servidor |
| Contato individual | `POST /api/v1/dispatch/interventions` | `campaigns.execute` | Idempotency-Key e autorização vigente obrigatória |
| Recuperação | `GET /api/v1/dispatch/recovery/summary` | `audit.view` | apenas recebimentos conciliados |
| Propostas de permanência | `/agents/retention/campaigns/intelligence/proposals` | coordinator + MFA onde aplicável | entidades distintas de campanhas do ledger |
| Importação Composio | `/api/v1/dispatch/composio/*` | `data.import`/view/edit | separado da UI desta Wave |
| Workflows | `/workflows` | `campaigns.view` | não é um motor novo de execução |

Backend revisado: `dispatch.py`, `dispatch_providers.py`, `dispatch_integrations.py`, `dispatch_interventions.py`, `dispatch_composio.py`, `dispatch_native_webhooks.py`, `delivery_webhooks.py`, `retention_campaigns.py`, `retention_campaign_execution.py`, `retention_campaign_proposal_workflow.py`, `retention_campaign_scheduling.py`, `dispatch_core.py`, `dispatch_sources.py` e `dispatch_delivery.py`.

## E2–E6 — Experiência implementada

- **`/disparos`**: MIRA Operação, navegação interna, visão executiva usando métricas reais, priorização de campanhas, verificação de heartbeat do worker.
- **Campanhas de Dispatch**: índice usando `ObjectDataTable` da Wave 0.1, seleção e filtro local sobre a amostra claramente identificada. Propostas continuam em `/campanhas`, não se fundem ao índice de objetos operacionais.
- **Campaign Builder**: 5 telas (objetivo, origem/audiência, canal/modelo, regras, revisão). Somente cria **rascunho** via POST real quando o usuário tem `campaigns.create`, fonte permitida, modelo aprovado, finalidade compatível e confirmação explícita. Nunca cria audiência fictícia, aprovação, agendamento nem envio.
- **Campaign Detail**: drawer contextual acessível, lazy-load de detalhe, itens e tentativas, respostas reais sob demanda, identificação de proposta vinculada pelo `origin_proposal_id`. Sem acesso indevido a observações internas, `subject_ref` ou `last_error` brutos na UI.
- **Control Center**: listas de operações e métricas reais, escolha de campanha, estados de fila/erro/worker e navegação ao drawer. Sem polling agressivo nem ações de execução por engano.
- **Biblioteca `/disparos/modelos`**: pesquisa, filtros por finalidade/canal/estado e preview sem interpolar dados pessoais. Gestão existente preservada em `/disparos/modelos/gerenciar`.
- **Provedores `/disparos/provedores`**: diferenças entre configurado, última verificação, ativo e operacional não confirmado. Gestão existente preservada em `/disparos/provedores/gerenciar`.
- **Resultados**: fila, pós-envio agregado, falhas, simulação e respostas com semântica rigorosa; recebimentos somente via `audit.view`. Não inventa entrega/leitura/pagamento.
- **Console legado `/disparos/console`**: conserva todos os fluxos já existentes de intervenção individual, inclusão de audiência, aprovação e agendamento; deep links `/disparos?mode=individual&student=...` e `?proposal=...` direcionados ao console preservando parâmetros.
- **Links profundos e dependências**: `/campanhas`, `/workflows`, `/disparos/importacoes`, `/retencao/logs` continuam independentes.

## E7 — Dependências futuras

- PR #174 Record Experience deve ser integrada antes de substituir o drawer isolado de Dispatch por `RecordDrawer`.
- Wave 0.4 Data Hub deverá fornecer fontes homologadas/selecionáveis e prévia autoritativa de elegibilidade, sem criar outra importação.
- API atual de campanhas retorna **50 por padrão**, no máximo 100 e sem `total`/offset. API de detalhe retorna até 100 itens; a UI informa que filtros e paginação locais se aplicam apenas à amostra.
- Não há API segura de contagem de elegíveis sem estágio/autorização. Builder apresenta **A verificar** e não calcula globais a partir de client-side rows.
- Backend só envia e-mail/SMS ao vivo quando habilitado; WhatsApp não é canal operacional no fluxo atual. Não oferecer WhatsApp no novo construtor sem adaptador verificado.
- Provedores: configuração/homologação só se confirmam por endpoints existentes; tela não chama verify, activate, disable.
- O frontend não oferece edição de campos oficiais nem inferência de recovery.

## E8 — Segurança e qualidade

- Frontend usa `api.me()`, `getVisibleNavigation` e `hasNavigationPermission` para `campaigns.view`, `campaigns.create`, `audit.view`, `settings.manage`; queries isoladas por `tenant_id` e `user_id`.
- Rejeitar operações de criação sem fonte, template e finalidade compatíveis no cliente; autorização e fonte rechecadas pelo servidor.
- Recebimentos: `dispatchApi.financial()` só se `audit.view` e aba Resultados. Nenhuma consulta financeira em overview.
- Nenhum worker, endpoint backend ou envio acionado automaticamente; não alterar flags `DISPATCH_LIVE_ENABLED`, `DISPATCH_WORKER_ENABLED` ou `DISPATCH_DRY_RUN_DEFAULT`.
- UX acessível: labels, foco, Escape e foco contido no drawer, sem fechar/aprovar por efeitos de renderização.
- Testes isolados do produto: filtros de canal, fontes/templates autorizados, contagens de amostra, semântica de estado, ausência de execução automática nos componentes de leitura.
- Validar no HEAD: ESLint, TypeScript, Node tests, Next build, backend Pytest/Ruff/Alembic (sem alterações no backend), diff de arquivos paralelos e QA visual autenticado quando houver ambiente.

## E9–E10 — Gate final

1. PR da branch isolada para revisão.
2. CI final completo aprovado no exato HEAD.
3. Confirmar ausência de conflitos e mudanças concorrentes em Record/Data Hub.
4. **Merge condicionado ao controle de releases**. Render atualmente segue `main` com autoDeploy por commit e start com Alembic; Vercel e Cloudflare também acompanham `main`. **Nenhum merge em `main` sem isolamento verificável**. Não mudar serviços de produção sem autorização expressa.

## Banco auditado (leitura, sem DDL)

Projeto `mira-testes`: Alembic `066_object_index_views` observado em 06/11/2026. O advisor de segurança Supabase acusa RLS desabilitado em `retention_campaign_proposals` no schema `public` (e outras advertências com naturezas distintas). Corrigir em Wave de hardening do banco depois de examinar grants, triggers, políticas e caminhos de acesso; não executar migração nesta Wave.

