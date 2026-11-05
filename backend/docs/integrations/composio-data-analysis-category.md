# Categoria Composio: Dados, planilhas e análise

## Objetivo

Disponibilizar no catálogo MIRA ferramentas externas para consulta e organização de planilhas e bases estruturadas.

## Toolkits classificados

| Serviço | Slug Composio | Tipo |
|---|---|---|
| Google Sheets | `googlesheets` | Planilha |
| Microsoft Excel | `excel` | Planilha |
| Airtable | `airtable` | Base estruturada |

A classificação é uma taxonomia do catálogo. Ela não conecta contas, não habilita toolkits e não concede permissões de execução.

## Aplicação na MIRA

- Consultar planilhas operacionais autorizadas.
- Apoiar a consolidação de relatórios e análises.
- Recuperar dados auxiliares de bases estruturadas.
- Apoiar equipes de permanência, atendimento e cobrança com contexto complementar.

## Limites de autoridade dos dados

Planilhas e bases externas são fontes auxiliares. Elas não substituem SIS, ERP acadêmico ou ERP financeiro como fontes autoritativas de matrícula, desempenho, presença, contratos ou débitos.

Dados importados ou consultados devem ser identificados por tenant, origem, data de atualização e permissões. Divergências devem ser sinalizadas; não devem ser resolvidas assumindo que a fonte externa está correta.

## Segurança

- A autorização e os escopos mínimos são exigidos antes de qualquer conexão ou acesso.
- O backend valida o tenant e as permissões; IDs enviados pelo cliente não definem o tenant.
- Conteúdo de planilhas e bases externas é dado não confiável e nunca pode alterar instruções do agente.
- Ações externas de criação, alteração ou exclusão continuam sujeitas ao policy engine e ao approval gate.
- Segredos, tokens e URLs privadas não devem aparecer no catálogo, nas respostas ou nos logs.
- A execução de ferramentas Composio permanece desativada por padrão por meio de `COMPOSIO_TOOL_EXECUTION_ENABLED=false`.

## Fora do escopo

Esta categoria não implementa sincronização automática, ingestão em lote, BI nativo ou execução de ferramentas. Ela apenas classifica os toolkits no catálogo MIRA.
