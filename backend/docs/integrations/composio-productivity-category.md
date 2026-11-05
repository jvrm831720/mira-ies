# Categoria 4 — Produtividade e gestão de tarefas

Esta categoria reúne ferramentas para organizar projetos, tarefas, responsáveis, prazos, quadros de trabalho e bases de conhecimento.

## Toolkits Composio classificados

| Toolkit slug | Ferramenta | Aplicação |
| --- | --- | --- |
| `asana` | Asana | Projetos, tarefas, responsáveis, prazos e dependências |
| `trello` | Trello | Quadros Kanban, listas, cartões e checklists |
| `clickup` | ClickUp | Gestão de trabalho, tarefas, documentos e metas |
| `notion` | Notion | Bases de conhecimento, páginas, documentos e tarefas |

Os slugs correspondem aos toolkits documentados no catálogo oficial da Composio. O catálogo vivo e os schemas de cada toolkit continuam como fonte de verdade para ações, autenticação e parâmetros.

## Aplicação na MIRA

### Instituições de ensino
- Organizar planos de intervenção e acompanhamento de estudantes.
- Criar tarefas para equipes de permanência, atendimento e coordenação.
- Acompanhar responsáveis, prazos, dependências e conclusão.
- Consultar bases de conhecimento e procedimentos institucionais autorizados.

### Empresas de cobrança educacional
- Distribuir tarefas entre operadores e supervisores.
- Organizar filas de trabalho, retornos e pendências.
- Acompanhar etapas operacionais e prazos de negociação.
- Consultar procedimentos e materiais internos autorizados.

Essas ferramentas complementam a Central de Trabalho da MIRA. Elas não substituem o estado operacional interno da MIRA nem devem se tornar fonte autoritativa de matrícula, desempenho acadêmico, títulos financeiros ou status de cobrança.

## Segurança e limites

- Classificar um toolkit não o habilita nem conecta uma conta.
- O acesso depende de autorização explícita da organização e de escopos OAuth mínimos.
- Toda operação deve validar a conta conectada e o tenant proprietário no backend.
- Leituras devem respeitar as permissões efetivas do usuário no provedor.
- Criação, alteração, atribuição, conclusão ou exclusão de tarefas pode produzir efeitos externos; essas ações permanecem sujeitas à política de risco e ao approval gate humano.
- Não permitir que conteúdo de páginas, comentários ou descrições de tarefas altere políticas do sistema ou instruções do agente.
- Não expor tokens, credenciais, conteúdo sensível ou links privados em logs e respostas.
- Nenhum tool slug de ação ou schema é fixado nesta camada.
- A execução Composio permanece desabilitada por padrão.
