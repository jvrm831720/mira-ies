# MIRA — Wave 2: Object Index refinado

## Escopo implementado

- A mesma tabela genérica ObjectDataTable é utilizada em Alunos e Casos Financeiros.
- Densidade confortável/compacta, com seleção por checkbox na página carregada.
- Fixação de até 3 colunas, dimensionamento por mouse, toque e teclado (separador com aria-valuenow).
- Ordem múltipla de até 3 campos: clique na coluna para prioridade simples, Shift+clique para adicionar; menu "Ordenar" permite editar, remover e limpar critérios.
- Setas verticais navegam pelas linhas com foco, Enter abre registro e Espaço seleciona; elementos interativos internos conservam seus atalhos.
- Propriedades de apresentação (sorts, density, pinned, widths) disponíveis em URLs de views; parsing permite somente colunas autorizadas e limites de tamanho.
- Vistas pessoais passam a armazenar configurações tipadas opcionais de sort múltiplo, densidade, fixação e larguras sem migration (JSONB existente). Os objetos/versões anteriores seguem válidos.
- Ações em massa recebem exclusivamente os objetos da página carregada; seleção é descartada em alterações de página, filtro, ordenação, view ou workspace.
- Um total global só aparece quando a API responde com um total inteiro verificado e o índice não for uma prévia parcial; caso contrário mostra número carregado e não inventa quantidade global.

## Backend

- Novo parser compartilhado de sorts em backend/app/services/object_index_sorting.py. Campos e direções estão em allowlists estáticas por objeto, com até 3 campos. Desempate por ID garante paginação determinística.
- GET /api/v1/object-index/students passa a aceitar optional sorts=nome:asc,curso:desc; mantém sort legado. Os checks de RBAC vetam risk_score para cargos sem students.sensitive.view.
- GET /api/v1/collections/cases passa a aceitar sorts e filtros JSON de propriedades selecionadas, sempre com tenant e SQL parametrizado.
- Novo compiler de filtros financeiros em backend/app/services/collection_index_filters.py: external_ref, status, balance, source, updated_at, operadores permitidos por tipo e máximo 8 filtros; concatenação de expressões SQL é somente sobre símbolos declarados estaticamente.
- A mesma condição de consulta alimenta contagem e linhas, sobre a base completa autorizada; nunca há paginação antes de filtrar/ordenar.
- Os parâmetros legados (status, statuses, sort, desc) permanecem disponíveis.

## Integridade

- Workspaces institucionais podem continuar acessando Cobrança quando a licença e audit.view permitem; nenhum novo botão executa cobranças ou pagamentos.
- Filtros e ordenação de risco permanecem invisíveis para cargos não autorizados no frontend e bloqueados pelo backend, inclusive se digitados na URL.
- Os campos de visão são metadados de apresentação, não SQL arbitrário.
- Seleção é exclusivamente por IDs presentes na página e não promete execução em massa de toda a carteira.
- 10 mil registros sintéticos são usados em teste unitário de sort local; testes de integração criam múltiplas páginas e tenants no Postgres.

## Validação

Frontend: npm test ; npm run lint ; npx tsc --noEmit ; npm run build.
Backend: pytest -q tests/test_object_index_wave2_contracts.py tests/test_object_index_wave2_integration.py tests/test_object_index_wave01.py tests/test_collections_wave07.py ; ruff check app/api/object_index.py app/api/collections.py app/api/object_views.py app/services/object_index_sorting.py app/services/collection_index_filters.py.

QA manual:
1. Alunos, com perfil admin: ajustar filtros/colunas, ordenar por 2+ campos, avançar páginas, recarregar e conferir URL/contagem.
2. Alunos, com viewer sem students.sensitive.view: score ausente, ordenação/filtros negados por 403.
3. Cobrança, com carteira contendo 100+ casos: filtrar status+origem+saldo, ordenar por saldo+referência e verificar conteúdo entre páginas.
4. Tabela: alternar densidade, fixar/desafixar colunas, redimensionar com mouse/toque/teclado, navegação por teclado com leitor de tela.
5. Selecionar uma página, mudar filtros ou página e confirmar que nenhuma seleção persiste.
6. Repetir com 2 tenants e cargo customizado.
7. Preview limitado deve dizer "total não verificado"; não apresentar contagem global presumida.

## Gates

Não declarar tests/CI/build/QA aprovados sem logs reais.
O merge da Wave 2 requer testes de integração no Postgres, validação front-end e revisão do comportamento de deploy (Vercel/Cloudflare).
Nenhuma migration ou API externa de pagamento foi executada nesta Wave.
