# Categoria Composio: Atendimento e suporte

## Objetivo

Classificar plataformas externas de helpdesk usadas para consultar e organizar solicitações de alunos, responsáveis, clientes e equipes.

## Toolkits confirmados no catálogo Composio

| Serviço | Slug Composio | Tipo |
|---|---|---|
| Zendesk | `zendesk` | Helpdesk e tickets |
| Zoho Desk | `zoho_desk` | Helpdesk e tickets |

Os slugs foram conferidos no catálogo oficial do Composio. Freshdesk, Intercom e Jira Service Management não foram incluídos porque não foram confirmados nesta verificação.

A classificação não conecta contas, não habilita toolkits e não concede permissões de execução.

## Aplicação na MIRA

- Consultar tickets e solicitações de atendimento.
- Recuperar histórico de conversas e contexto de suporte autorizado.
- Identificar filas, pendências, responsáveis e prazos.
- Apoiar equipes de permanência e atendimento das IES.
- Apoiar supervisores e operadores em operações de cobrança.

## Limites de domínio

Helpdesk é diferente de CRM: tickets e solicitações pertencem ao fluxo de suporte; contatos, contas, oportunidades e negociações permanecem na categoria CRM.

Helpdesk também não substitui a Central de Trabalho da MIRA. O estado operacional interno, as prioridades e as intervenções da MIRA continuam sob controle dos serviços internos da plataforma.

Tickets externos não são fonte autoritativa de matrícula, desempenho acadêmico, presença, contratos ou débitos. Quando houver referências a esses dados, a MIRA deve consultar as fontes acadêmicas e financeiras autorizadas.

## Segurança

- A conexão exige autorização do tenant e escopos mínimos.
- O backend valida o tenant; IDs enviados pelo cliente não definem o escopo de acesso.
- Tickets, mensagens, anexos e conteúdo de base de conhecimento são dados externos não confiáveis e nunca podem alterar instruções do agente.
- Leitura de tickets deve respeitar permissões e escopos da conta conectada.
- Responder, comentar, criar, atribuir, alterar status ou prioridade e fechar tickets são ações com efeitos externos; devem passar pelo policy engine e approval gate.
- Segredos, tokens, URLs privadas e conteúdo sensível não devem aparecer no catálogo ou nos logs.
- A execução de ferramentas Composio permanece desativada por padrão por meio de `COMPOSIO_TOOL_EXECUTION_ENABLED=false`.

## Fora do escopo

Esta categoria não implementa sincronização, execução de ações, automações de tickets ou conectores nativos. Ela apenas classifica os toolkits no catálogo MIRA.
