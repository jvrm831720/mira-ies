# MIRA — Wave 6 · Busca Universal federada

## Objetivo

Ampliar a Command Palette existente para descobrir **alunos, casos financeiros,
trabalho humano, visualizações salvas, propostas de campanhas e páginas
autorizadas** a partir da mesma experiência.

O backend federado é **somente leitura**. Busca não envia comunicações,
não inicia campanhas, não edita registros nem executa operações financeiras.

## Provedores

| Provedor | Fonte | Permissão efetiva | Destino |
|---|---|---|---|
| Alunos | students (nome/matrícula) | students.view | /alunos/{id} |
| Casos financeiros | dispatch_obligations (referência/vínculo) | audit.view | /cobranca/casos/{id} |
| Meu Trabalho | work_activities (título) | access.operator + students.view | /trabalho?activity={id} |
| Views | mira_object_views (nome + escopo permitido) | grant específico do objeto | /alunos, /cobranca, /campanhas?saved_view={id} |
| Campanhas | retention_campaign_proposals (título) | campaigns.view | /campanhas?proposal={id} |
| Páginas | getVisibleNavigation do usuário | permissões, módulos, perfil e features | rota original |

Os provedores de registros aplicam **tenant_id** na consulta e retornam somente
campos seguros de identificação. A view pessoal é visível apenas ao proprietário;
uma view de workspace só é visível aos usuários autorizados e não pode
expor metadados sensíveis sem students.sensitive.view. Os dados de configuração
da view e os payloads dos registros não são retornados.

A navegação é um provedor **local, permission-filtered**, porque suas rotas
dependem também de módulo e feature flags do frontend. O cliente cruza o
resultado do servidor com essas rotas e rejeita href não pertencentes a
resolvers explicitamente reconhecidos. O servidor continua sendo responsável
pela autorização do registro ao abrir o destino.

## Contrato da API

GET /api/v1/search/universal?q=marina&limit=5&providers=students,work

- Exige sessão humana autenticada com MFA, nunca API key de serviço.
- q: 2 a 80 caracteres, validado após trim.
- providers: somente uma lista de provedores conhecidos, sem duplicatas
  e sem seleção livre de tabelas.
- limit: de 1 a 8 por provedor; cinco provedores remotos, no máximo 40
  resultados por chamada. Nenhum campo "total global" é inventado.
- count_scope: bounded_matches_only.
- Cada provedor roda isoladamente em um savepoint e com statement_timeout
  de 500 ms. A mesma AsyncSession é usada sequencialmente para preservar o
  contexto RLS, sem consultas concorrentes no mesmo banco.
- Na falha de um provedor, status "unavailable" e partial=true;
  **nenhuma mensagem de SQL ou dado interno** sai da resposta.
- Os resultados são ordenados por score de correspondência e exibidos com
  rótulo de categoria e subtítulo desambiguador.
- kind="navigate" e actions_executed=false: a paleta só navega.

## Aproximação, latência e migração

Migration **072_federated_search** habilita o pg_trgm e acrescenta índices GIN
de buscas por nome/referência nas fontes existentes. A busca combina igualdade,
prefixo, contém e similaridade trigrama, com limites de linhas e tempo
por provedor; não realiza busca em JSONB sensível nem varredura irrestrita de
payloads. Não replica dados, não altera modelos de registros e não reescreve
configurações existentes.

## UX e navegação

- Ctrl/⌘ + K abre; ↑/↓ escolhem; Enter abre; Escape fecha; Tab mantém
  foco dentro do diálogo e retorna o foco ao fechar.
- Debounce de 180 ms, cancelamento por AbortSignal, cache com tenant+usuário+
  termo, nunca compartilhar entre workspaces.
- Estados de carregamento, vazio, erro e falha parcial, sempre com navegação
  local autorizada disponível como fallback.
- /trabalho?activity abre o WorkItemInspector sem editar a atividade.
- /campanhas?proposal resolve o ID somente contra propostas já autorizadas
  retornadas pela API do módulo; não agenda ou executa campanha.
- ?saved_view aplica a configuração apenas após a API da view verificar
  propriedade, escopo, schema_version e campos sensíveis; o URL não carrega
  colunas ou filtros arbitrários.

## Testes e gates

Backend: tests/test_universal_search_wave6.py
- cinco provedores reais em PostgreSQL, dados de dois tenants, RBAC custom
  mínimo, views sensíveis, API keys proibidas, falha parcial sem vazamento,
  busca aproximada por termo com digitação incorreta, tamanho/limites de busca;
- Alembic 072 com pg_trgm e índices em PostgreSQL não-superusuário.

Frontend: tests/universal-search-wave6.test.mjs
- rotas permitidas por módulo, rejeição de href externo ou injetado,
  no side effects, teclado/acessibilidade, fuzzy local, debounce e cache escopado,
  destino do trabalho, campanhas e view.

Validar também CI geral do backend e frontend, captura visual, dois tenants,
perfis com grants diferentes e latência p95 real sobre bases representativas.
Nenhuma migration foi executada no banco real durante a abertura deste PR.

## Limites atuais

- A busca de campanhas cobre as propostas persistidas (não todos os objetos
  históricos de campanhas de dispatch). Expansões devem adicionar um provider
  explícito e manter sua permissão original.
- Resultados não incluem snippets pessoais, scores, mensagens, saldos nem
  registros brutos. O destino faz a consulta completa com RBAC/RLS.
- Contagens globais e busca em todos os conteúdos de arquivos não fazem
  parte desta wave. O usuário vê resultados limitados, identificados como tal.

A validação de produção requer deploy e teste autenticado. Merge da PR não
prova que o build externo de Cloudflare foi publicado.
