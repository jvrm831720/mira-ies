# Wave 0.8 — MIRA Sidebar (referência visual Attio)

## Referência inspecionada

Três arquivos SingleFile “Home - Attio” de 06/11/2026 (12:09:30, 12:09:36 e 12:09:41 BRT), capturados do mesmo workspace. Renderizados offline em navegador Chromium com viewport 1440 × 900. Os estados observados foram:

1. Sidebar padrão e página Home.
2. Sidebar com painel de Inbox aberto.
3. Sidebar com menu de workspace/conta expandido.

Nenhum código proprietário, imagem de marca, fonte embutida ou classe CSS ofuscada do material foi copiado para o produto.

## Especificação visual observada

| Elemento | Referência | Implementação MIRA |
|---|---|---|
| Sidebar expandida | ~275 px | 275 px |
| Fundo | `#0B0C0D` | `#0B0C0D` |
| Header | ~48 px | 48 px |
| Busca | ~30 px | 30 px |
| Linha do item | ~28–29 px | 29 px |
| Tipografia | Inter, 14 px nos links | Inter, 14 px nos links |
| Cabeçalho dos grupos | Inter, 12 px, discreto | Inter, 12 px |
| Seleção | Fundo cinza-carvão | `#1B1C1F` |
| Menu de workspace | Popover escuro à esquerda | Popover escuro contextual |
| Rodapé | Ações e progresso da conta | Convite e conta reais, sem trial fictício |

## Mapeamento de conteúdo para a MIRA

A referência usa Home, Tasks, Notes, Emails, Calls, Reports, Sequences, Workflows e os grupos Records e Lists. Esses nomes foram adaptados às rotas reais e autorizadas da MIRA:

- **Atalhos:** Início, Central de trabalho, Monitoramento, Resultados e Workflows.
- **Registros:** Alunos, Gestão acadêmica e Casos financeiros.
- **Listas e jornadas:** Grupos, Campanhas, Intervenções, Jornadas e Serviços.
- **Operação:** Disparos e Histórico de contatos.
- **Dados:** Data Hub, Integrações, Fontes financeiras, Importar e Importações.
- **Conta/workspace:** configurações, membros, cargos, plano e sair.

O Command Palette continua permitindo localizar todas as rotas autorizadas, mesmo as que não estão na seção de atalhos.

A navegação de Educação não bloqueia mais a rota de Cobrança quando o workspace institution possui, explicitamente, o módulo billing e permissão audit.view. A página aplica a mesma autorização.

## Restrições

- Não criar Inbox, notificações, trial ou ações inexistentes para replicar o screenshot.
- Não modificar a UI interna do Portal do Aluno.
- Não alterar autenticação, endpoints, migrations ou políticas backend.
- Não liberar operações reais de cobrança por mudança de navegação.
- Não assumir que design visual aprovado equivale à homologação operacional.

## Checklist de QA antes de integração

- [ ] Comparação visual autenticada em 1440 × 900 com a referência SingleFile.
- [ ] Sidebar recolhida no desktop e scroll vertical das seções.
- [ ] Mobile, backdrop, Escape e retorno de foco.
- [ ] Troca de workspace, menu de conta e saída.
- [ ] Busca Ctrl+K/Cmd+K com permissões.
- [ ] Educação com billing: aparece e abre Cobrança quando autorizado.
- [ ] Educação sem billing: Cobrança ausente.
- [ ] Cargo personalizado sem audit.view: Cobrança ausente.
- [ ] Flags acadêmicas desligadas: não exibir links acadêmicos.
- [ ] Lint, testes, TypeScript e build no HEAD final.

A fidelidade foi baseada nos estados e na geometria disponíveis dos três arquivos. Não há evidência de outros estados responsivos da Attio nos anexos.
