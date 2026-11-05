# Categoria 2 — CRM e relacionamento

A segunda categoria do catálogo MIRA reúne CRMs usados para manter o histórico de relacionamento e organizar contatos, contas, negociações e atividades.

## Toolkits Composio classificados como CRM

| Toolkit slug | Ferramenta | Aplicação |
| --- | --- | --- |
| `hubspot` | HubSpot | Contatos, empresas, negócios, tickets e atividades |
| `salesforce` | Salesforce | Contas, contatos, leads, oportunidades, tarefas e casos |
| `pipedrive` | Pipedrive | Pessoas, organizações, leads, negócios e atividades |
| `dynamics365` | Dynamics 365 | Contas, contatos, leads, oportunidades, casos e tarefas |

Os quatro slugs foram conferidos na documentação/catálogo atual do Composio. O catálogo vivo e os schemas continuam sendo a fonte de verdade para as ações disponíveis e para autenticação.

**RD Station:** não foi incluído como toolkit Composio nesta entrega porque não foi possível confirmar um toolkit correspondente no catálogo oficial atual. Não devemos apresentar uma integração como disponível sem suporte verificável. Pode ser avaliado depois como integração nativa específica, se houver API e autenticação aprovadas.

## Aplicação na MIRA

### Instituições de ensino
- Consultar histórico de relacionamento e contatos de alunos/responsáveis.
- Registrar interações e encaminhamentos.
- Criar tarefas de acompanhamento para equipes de permanência.
- Consultar tickets e casos relacionados a atendimento.
- Associar intervenções a contatos e registros existentes.

### Empresas de cobrança educacional
- Consultar histórico de tentativas de contato e negociações.
- Localizar contatos, empresas e responsáveis pela carteira.
- Registrar atividades e resultados de negociação.
- Acompanhar oportunidades/negócios e tarefas dos operadores.
- Consultar casos e solicitações relacionados à cobrança.

O CRM não substitui o SIS nem o sistema financeiro. Identidade acadêmica, matrícula, contrato, títulos e situação financeira continuam vindo das integrações nativas e fontes oficiais da organização. O CRM fornece contexto de relacionamento e execução operacional.

## API

- `GET /integrations/composio/catalog/categories` retorna Comunicação e CRM.
- `GET /integrations/composio/catalog` classifica os toolkits CRM com `mira_category=crm` e `mira_channel=crm`.

## Segurança e limites

- Classificar um toolkit não o habilita.
- Nenhuma conta é conectada automaticamente.
- O tenant precisa habilitar o toolkit e selecionar explicitamente os tool slugs validados pelo catálogo vivo.
- Ações de consulta, criação, atualização e exclusão devem ser tratadas conforme risco; alterações e operações externas continuam sujeitas ao approval gate humano já implementado.
- Nenhum tool slug de ação ou schema é fixado nesta camada.
- A execução Composio permanece desabilitada por padrão.
