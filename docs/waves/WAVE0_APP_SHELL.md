# Wave 0.0 — Fundação Visual e App Shell

## Escopo e referências (05/11/2026)

- Fonte de verdade: docs/DESIGN_SYSTEM.md e os arquivos MIRA_Plano_Migracao_UX_Attio_v1(1).md e MIRA_Blueprint_Product_Design_2026(1).md.
- Referência direta inspecionada: Attio (CRM)(5).zip, 8 páginas HTML + Attio.zip aninhado; Attio(2).zip, 13 HTMLs. O ZIP aninhado corresponde ao segundo e não representa telas adicionais.
- Estados observados: shell da lista de Empresas (busca, objetos, grupos, cabeçalho de lista), registro de Google em overlay, painel com inspector do workflow, configurações do workspace. Capturas registradas em 05/11/2026.
- Adotado: sidebar compacta, switcher, agrupamento de links, busca acionada por teclado, header de baixa altura, selecionado discreto, tipografia concisa, densidade regular.
- Não adotado: nomes, logotipos, ícones proprietários, HTML/CSS/JS da Attio, objetos CRM sem correspondente real e assistentes decorativos. O código nesta PR é original MIRA.

## Decisões da implementação

1. Um único catálogo tipado para sidebar e Command Palette em components/layout/navigation.ts. Ele contém somente URLs já presentes em (app) e exige permissão explícita; nenhuma carteira, contato ou resultado de cobrança hipotético é apresentado.
2. Workspace switcher conserva GET /api/v1/org/workspaces e POST /api/v1/org/workspaces/switch. A troca revoga/renova sessão conforme o backend já existente; o frontend limpa cache e atualiza o contexto da página.
3. A resposta existente GET /api/v1/org/me ganha campo aditivo enabled_modules, derivado de mira_module_entitlements ativos (enabled/trial e não expirados) exclusivamente no tenant da sessão. Isso evita navegação em módulos bloqueados sem alterar a autenticação. Dados financeiros e acadêmicos permanecem sob autorização no backend.
4. Perfil institution vê Alunos, Inteligência e Acadêmico quando o módulo permanence está ativo; perfil collection/billing vê apenas Operação compartilhada, Dados e Workspace, sem apresentar telas de carteira ainda inexistentes. Operação comercial depende do módulo billing; Educação de permanence.
5. Permissões efetivas fornecidas pela sessão prevalecem. Cargos customizados sem lista de grants falham fechados. Fallback para cargos internos legados só quando custom_role_id não existe.
6. O header deixa de listar notificações de exemplo e de afirmar que suporte foi enviado quando existia somente localStorage. Até haver API de inbox global, mostra indisponibilidade verificável. A Command Palette busca **páginas autorizadas**, não dados nem ações inventadas.
7. Canvas branco #FFFFFF, superfície #F8F9FA, tinta #101112, secundário #505967, bordas #E6E7EA, azul de foco/seleção #266DF0 e CTA near-black; tokens CSS compartilhados. Sem afetar a superfície Auth.
8. Iconografia preservada em @/components/ui/icons (Untitled UI). Layout usa landmarks semânticos, skip link, aria-current, labels, estados de loading/erro/vazio e foco no teclado.
9. Transições 180ms e preferência prefers-reduced-motion já definida em globals.css. Sidebar responsiva com drawer mobile, overlay e modo recolhido desktop. Tabs usam setas/Home/End; Dialog recebe focus trap.

## Antes → depois

| Aspecto | Antes | Depois |
|---|---|---|
| Sidebar | Workspace/Permanência/Acadêmico/Ações/Dados/Plano com permissões parciais | Início/Alunos/Inteligência/Operação/Acadêmico/Dados/Configurações, com filtragem de perfil, grants e entitlements |
| Busca | Resultado inicial por Enter; sem seleção por seta | Cmd/Ctrl+K, setas, Enter, Esc, resultado com categoria, foco/restauração e estado vazio |
| Switcher | Implementado, aparência e estados parcialmente hardcoded | Contratos preservados e UI por tokens; loading, erro, troca e estado atual |
| Header | Título maior, notificações fabricadas, "suporte enviado" local | Header compacto, breadcrumb contextual, zero feed fictício |
| Design tokens | Valores de neutros diferentes de DESIGN_SYSTEM.md | Valores canônicos alinhados; componentes compartilhados refinados |
| Mobile | Sidebar em overlay | Navegação responsiva com fechamento explícito, skip link e foco visível |

## Limites honestos / próximos gates

- Esta Wave não adiciona carteiras, contatos ou casos de Cobrança: o menu só os mostrará após existirem rotas operacionais e políticas autorizadas.
- A entitlement permanence **não equivale** à flag runtime NATIVE_ACADEMIC_OPERATIONS_ENABLED. O novo campo available_features de org/me inclui flags reais para catálogo, jornadas e serviços; a navegação acadêmica só mostra rotas com flags ativas. Páginas e APIs preservam seus bloqueios próprios e nenhuma capacidade é habilitada por esta PR.
- Busca global: apenas rotas existentes. Busca de registros 360 e ações depende de APIs e escopo de autorização próprio; não há dados mockados.
- Notificações globais: sem API conectada nesta Wave. O header informa a limitação.
- Capturas HTML foram inspecionadas como evidência de referência, mas não há screenshot do novo app autenticado produzido nesta PR. QA visual final exige preview autenticado com Educação, Cobrança, viewer e custom RBAC, desktop e mobile.
- Sem mudanças em onboarding, Portal do Aluno, regras financeiras, dispatch ou autenticação; nenhuma ação externa real.
- Validar no head final: npm ci, npm run lint, npm test, npx tsc --noEmit, npm run build; backend Ruff, pytest e migrations CI. Não executar deploy/migrations de produção.

## Matriz mínima de QA manual

- Admin IES com permanence/data: acessar páginas acadêmicas, trabalho, dados, workspace e trocar workspace.
- Viewer IES: somente links permitidos, sem acadêmico sensível e sem ações de administração.
- Custom role com data.view: apenas integrações e histórico de dados, sem importação nem equipe.
- Cobrança com billing: operações genéricas, sem links de Alunos/Acadêmico; ausência de carteiras não é disfarçada.
- Workspaces múltiplos: alternar com novo token; erro mantém sessão atual; troca reavalia permissões e módulos.
- Cmd/Ctrl+K, setas, Enter, Esc, foco visível; busca vazia; teste em largura 375px e 1280px e motion reduzida.
