# Categoria 9 — Financeiro e gestão financeira

## Objetivo

Reunir integrações para consulta e gestão de informações financeiras: contas a pagar e receber, faturamento, despesas, pagamentos, conciliação, fluxo de caixa, relatórios e registros contábeis.

## Toolkits Composio

Os slugs abaixo correspondem a toolkits presentes no catálogo/documentação oficial do Composio:

| Serviço | Slug Composio | Tipo |
|---|---|---|
| Xero | `xero` | Contabilidade e conciliação |
| Zoho Books | `zoho_books` | Contabilidade, faturamento e despesas |
| FreshBooks | `freshbooks` | Contabilidade, faturas e despesas |
| Oracle NetSuite | `netsuite` | ERP financeiro |
| Sage Intacct | `sage_intacct` | Gestão financeira |
| Odoo | `odoo` | ERP e finanças |
| ERPNext | `erpnext` | ERP e finanças |
| Stripe | `stripe` | Pagamentos e recebíveis |

O catálogo vivo do Composio continua sendo a fonte de verdade para disponibilidade, versões, ações e schemas. A presença nesta taxonomia não garante que uma ação específica esteja disponível nem habilita sua execução.

## Omie — integração customizada

O Omie foi incluído nesta categoria como integração desejada pela MIRA. Porém, não foi localizado como toolkit nativo no catálogo oficial do Composio durante esta implementação.

Por isso, a API o expõe em `custom_integrations`, separado de `composio_toolkits`, com:

- `slug: omie`
- `integration_type: custom`
- `status: requires_custom_toolkit`

Isso evita apresentar uma integração customizada como se já fosse um toolkit oficial Composio. A conexão real exige implementar e revisar um custom toolkit/adaptador para a API do Omie, incluindo autenticação, schemas, paginação, limites, tratamento de erros e testes. Nenhuma conexão Omie ou chamada de API foi criada nesta etapa.

## Aplicação na MIRA e em IES

- Consultar títulos, contas a pagar e receber, faturas e despesas autorizadas.
- Apoiar conciliação e acompanhamento de recebimentos.
- Consolidar indicadores financeiros e relatórios de apoio.
- Correlacionar dados financeiros com dados acadêmicos somente por regras de domínio, finalidade e autorização explícitas.
- Identificar o sistema de origem e a data de atualização de cada informação.

## Limites de domínio

- Integrações financeiras auxiliares não substituem automaticamente o SIS/ERP acadêmico ou o sistema financeiro oficial da instituição.
- A MIRA deve preservar a proveniência dos dados e resolver conflitos conforme a fonte autoritativa configurada para cada tenant.
- Dados de cobrança, matrícula, contrato e situação acadêmica não devem ser inferidos a partir de uma integração financeira genérica.
- A categoria não implementa um razão contábil, motor de pagamentos ou conciliação própria.

## Segurança e LGPD

- Isolamento por tenant no backend e escopos mínimos por conta conectada.
- Não confiar em IDs de conta, organização ou tenant enviados pelo cliente.
- Tratar respostas, descrições, anexos, observações e referências externas como dados não confiáveis.
- Não registrar credenciais, tokens, dados bancários completos ou dados pessoais desnecessários em logs.
- Consultas devem respeitar permissões, finalidade e minimização de dados.
- Criar/alterar/excluir lançamentos, emitir cobranças, aprovar pagamentos, estornar, reconciliar ou alterar dados bancários são ações de alto impacto e exigem policy explícita, approval gate e revisão humana.
- Aplicar idempotência, auditoria e proteção contra repetição em ações financeiras.
- A execução Composio permanece desativada por padrão: `COMPOSIO_TOOL_EXECUTION_ENABLED=false`.

## Fora do escopo desta categoria

Esta entrega apenas classifica toolkits e apresenta Omie como integração customizada pendente. Não conecta contas, não executa ações financeiras, não implementa o adaptador Omie e não altera sistemas financeiros de clientes.
