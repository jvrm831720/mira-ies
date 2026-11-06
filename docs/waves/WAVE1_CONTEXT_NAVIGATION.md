# MIRA — Wave 1 | Contexto e Navegação

## Escopo e estado

- Branch isolada: feat/wave-1-navigation-context
- Base auditada: main em 12af20bf7d11a562b266f9fa9ee61ba99c6e1db3
- Nenhuma mudança em autenticação, onboarding, Portal do Aluno, backend, migrations, envios ou pagamentos.
- Não fazer merge ou deploy automático; validar no HEAD final.

## Mudanças implementadas

1. src/lib/navigation-context.ts: contrato de contexto de apresentação via URL para Object Index: view, busca, filtros, ordenação, colunas, página, tamanho e registro UUID. Deserialização valida campos, operadores, views, limites e IDs. Deep links antigos tab, q e risk continuam suportados.
2. src/components/layout/navigation-context-provider.tsx: infraestrutura compartilhada de navegação e sessão, com useObjectNavigationState (URL + histórico) e useObjectScrollRestoration (posição de rolagem após carregamento da lista).
3. App Shell: Provider sob AuthGate; troca de workspace limpa estado de rolagem junto com o cache.
4. /alunos: filtros, página, tamanho, colunas e seleção do drawer passam a ser refletidos na URL. Back/Forward e atualização reconstroem o estado.
5. /alunos/[id]: expansão do drawer carrega destino de retorno seguro da view original. Retornos externos e caminhos de outras páginas são rejeitados.
6. /cobranca: contexto da listagem e caso selecionado são preservados, mantendo API e permissões atuais.
7. Tests: frontend/tests/navigation-context.test.mjs verifica roundtrip, campos autorizados, legacy links, retorno seguro e isolamento de scroll por tenant.

## Segurança

- URL contém apenas estado de apresentação, nunca autorização. O backend segue como fonte de verdade para tenant, RBAC e dados sensíveis.
- IDs selecionados precisam de sintaxe UUID, mas o backend valida identidade e acesso real.
- Filtros têm limites de tamanho, operadores e campos permitidos.
- SessionStorage armazena apenas coordenada vertical e timestamp, em chave hash por tenant:user e URL; não armazena registros nem conteúdo dos filtros.
- Scroll com TTL de 30 minutos; invalidação na troca de workspace.
- Retorno da ficha só pode levar para /alunos no mesmo domínio.

## Limites intencionais

- Navegação sequencial entre itens ainda depende de cursor remoto estável (Wave 4).
- Saved views mantêm escopo pessoal e estado de rótulo local; Wave 3 adicionará resolução de ID de view e compartilhamento.
- Integração de navegação contextual aplicada apenas aos índices Alunos e Cobrança nesta Wave; demais telas mantidas.
- Busca global, workflow e portal não mudam.
- QA visual autenticado e performance com datasets grandes requerem execução real; não considerar homologados apenas pelo código.

## Gate de qualidade

Executar na pasta frontend: npm ci, npm test, npm run lint, npx tsc --noEmit e npm run build.

Executar QA autenticado:
- Admin de IES: filtro, página, abrir drawer, expandir ficha, voltar e recuperar view.
- Operador sem dados sensíveis: backend bloqueia score e filtros não autorizados.
- Cobrança: status, busca, ordenação, caso selecionado, F5 e Back.
- Duas instituições e um workspace de cobrança, com troca de tenant.
- Desktop, tablet, mobile, foco, teclado, Escape e condições de erro.

Não mesclar nem publicar antes de CI no HEAD final, revisão de mudanças e QA autenticado.
