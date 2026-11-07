# MIRA — Wave 7: Integração, performance e homologação

Natureza: gates de release e evidências automatizadas; não é um deploy. Base: Wave 6 na main, commit 606c6de27240363395929df0106223f45f95a4de.

## Contratos preservados

| Experiência | UI e APIs | Fonte de verdade |
| --- | --- | --- |
| App Shell | Sidebar, AuthGate, NavigationContextProvider | org/me, membership, roles, módulos |
| Object Index | ObjectIndex, ViewManager | índices remotos e views com revision |
| Ficha 360 | StudentDrawer, CollectionCaseDrawer, RecordPage | aluno e obrigação financeira (domínios distintos) |
| Meu Trabalho | WorkInbox, WorkItemInspector | WorkActivity + evento append-only |
| Busca Universal | CommandPalette, search/universal | providers, tenant/RBAC, pg_trgm |

A MIRA não se transforma em ERP acadêmico, não mistura resultado humano com pagamento ou disparo e mantém o Control Center interno.

## Seis jornadas

J01: sessão MFA AAL2 -> App Shell -> workspace autorizado; segundo tenant segregado.

J02: Object Index -> filtro -> view pessoal/compartilhada; paginação e campos sensíveis protegidos.

J03: aluno -> Ficha 360; risco só com grant e acesso cruzado negado.

J04: caso financeiro -> Ficha 360; status e saldos de origem, nenhum pagamento ou conciliação simulados.

J05: Meu Trabalho -> assumir -> resolver -> histórico e próxima atividade; evento único, reenvio idempotente, ausência de side effects financeiros.

J06: Ctrl/Command+K -> pesquisa federada -> navegação; cinco providers, páginas autorizadas, erro parcial, teclado e zero execução crítica.

Testes reais: backend/tests/test_wave7_authenticated_journeys.py usa FastAPI real, PostgreSQL e tokens MFA assinados. O conjunto backend/tests/test_wave7_live_browser.py executa as seis jornadas em desktop (1440x900) e mobile (390x844) via Chromium Playwright e encaminha as chamadas do browser ao FastAPI por ASGI; não simula as respostas da API. A integração direta ASGI não substitui smoke test de frontend/Render efetivamente publicados.

Evidências: wave7-artifacts/wave7-evidence.json, screenshots por jornada/viewport, relatórios axe e integration-decision.json. O gate backend/scripts/wave7_release_gate.py exige as 12 combinações (6 x 2), isolamento entre tenants, RBAC, tolerância a falhas e nenhuma mutação crítica indevida.

## Performance e acessibilidade

O runner mede tempo de página e duração das chamadas à API e calcula p95 por nearest rank. Limites iniciais de CI para impedir travamentos evidentes: página p95 <= 12000 ms e API p95 <= 2500 ms no Next em modo de produção local, com dados sintéticos. Não são SLA nem métrica de produção. Registrar p50/p95/p99 em staging com volume representativo, amostras, tempo, erros, EXPLAIN sanitizado, planos de índices e capacidade.

Axe-core testa WCAG A/AA no navegador. Violações serious ou critical bloqueiam o gate, com seletores e sumários registrados em relatório de teste; falhas não são silenciadas. Testar teclado, foco, navegação, dispositivos móveis e desktop.

## Rollout e paridade

NEXT_PUBLIC_MIRA_UNIFIED_ROLLOUT:
- off: Central clássica expandida e busca local de páginas autorizadas;
- canary: somente tenants explicitamente listados em NEXT_PUBLIC_MIRA_CANARY_TENANTS, IDs UUID separados por vírgula;
- on: experiência unificada atual para quem já tem acesso.

Sem lista válida, canary falha fechado. São flags de exposição da interface, não de autorização. Como são NEXT_PUBLIC, alterar exige novo build do frontend. Ordem de rollout: off -> canary de dois workspaces homologados -> on mediante aprovação.

Não remover WorkActivitiesPanel, drawer legado ou navegação anterior sem comprovar a paridade funcional das rotas. A antiga busca de alunos da Command Palette foi substituída pelo provider federado; a busca própria do Object Index continua, pois serve a filtros diferentes. A decisão central de RBAC passa pelo helper has_effective_permission de app/core/auth.py, evitando regras conflitantes para views e pesquisa. Compartilhamento de views mantém política especial da Wave 3 para coordenadores/admins ou permissão custom explícita.

## Compatibilidade e ambientes (observações somente leitura)

Supabase mira-testes: a revisão Alembic consultada já é 072_federated_search, pg_trgm está instalada e sete índices de busca estão presentes. Foram confirmados RLS e FORCE RLS nas tabelas de views, trabalho, campanhas e obrigações financeiras verificadas. Não foram realizadas migrations reais por esta Wave 7.

Vercel mira-ies: existem builds preview READY anteriores nesta branch, sem comprovação de produção no SHA final. Render exige confirmação do workspace antes de inspecionar serviços, não selecionado automaticamente. O check externo Cloudflare tinha falhas nas Waves anteriores. Logo, não declarar frontend, backend ou produção sincronizados sem evidência do commit publicado.

backend/scripts/wave7_schema_preflight.py consulta revision, índices, extensão, FORCE RLS, role e tamanhos de tabelas, apenas via SELECT e sem expor credenciais ou registros dos clientes. A CI roda no banco migrado descartável antes de recriar o banco dos testes ORM. Revision divergente, índice ausente ou RLS incompleto bloqueiam. Índices GIN trigram de migração 072 são criados não-concorrentemente; em bases grandes exigem análise de lock e janela de manutenção.

## Gates GO/NO_GO

O gate de integração exige 12 cenários aprovados, MFA, isolamento, RBAC, falha parcial, zero efeitos críticos imprevistos, métricas válidas e zero violações graves. A decisão é computada dos arquivos de evidência, não de caixas marcadas manualmente.

O gate de produção exige, adicionalmente, métricas reais em staging, compatibilidade N-1/N verificada, backup restaurado em ensaio, health do Render no commit exato, frontend READY na revisão exata, checks externos obrigatórios, rollback ensaiado e autorização humana. Falta de evidência significa NO_GO. Merge no GitHub não publica por si só.

## Rollback

1. Congelar rollout e registrar SHA dos artefatos, config e revisão do banco.
2. Desativar a exposição unificada (off) com build compatível ou reimplantar versão anterior validada, sem contornar RBAC.
3. Pausar somente automações afetadas usando os mecanismos autorizados existentes.
4. Preservar o schema expandido 070/071/072 se compatível; não executar downgrade destrutivo automático, especialmente por causa das chaves de idempotência e eventos de auditoria.
5. Caso haja incompatibilidade de dados, plano de restauração requer backup recuperável e aprovação específica; nunca apagar eventos de pagamento/disparo.
6. Revalidar health, login MFA, dois tenants, busca, fila humana e métricas antes de reabrir canary.

Este documento especifica o processo. Aprovação de publicação só pode ser concedida após os gates e evidências do ambiente efetivo.
