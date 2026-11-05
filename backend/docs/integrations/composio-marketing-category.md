# Categoria Composio: Marketing institucional

## Objetivo

Classificar plataformas de marketing e engajamento usadas para organizar públicos, preferências de comunicação, campanhas e jornadas de relacionamento.

## Toolkits confirmados no catálogo oficial Composio

| Serviço | Slug Composio | Tipo |
|---|---|---|
| Mailchimp | `mailchimp` | E-mail marketing e campanhas |
| Brevo | `brevo` | Marketing multicanal |
| ActiveCampaign | `active_campaign` | Automação de marketing |
| Customer.io | `customerio` | Engajamento e jornadas |

Os slugs foram conferidos no catálogo e na documentação oficial Composio. Para Customer.io, usar o slug canônico `customerio`; a variante antiga `customer_io` aparece como nomenclatura substituída no changelog do Composio.

## Aplicação na MIRA

- Organizar campanhas institucionais e jornadas de relacionamento.
- Apoiar comunicação segmentada de permanência, matrícula, rematrícula e relacionamento.
- Consultar métricas de engajamento e desempenho de campanhas.
- Apoiar comunicação de cobrança somente quando houver base legal, finalidade e autorização adequadas.
- Manter histórico de campanhas como contexto auxiliar, sem substituir o histórico operacional da MIRA.

## Limites de domínio

Esta categoria é distinta de Comunicação (caixas de entrada, mensageria e colaboração), CRM (relacionamento individual e pipeline) e Atendimento (tickets e solicitações).

Plataformas de marketing não são fontes autoritativas de matrícula, situação acadêmica, presença, contratos ou débitos. A segmentação deve consumir dados autorizados e atualizados das fontes institucionais apropriadas.

## Segurança, LGPD e consentimento

- Aplicar isolamento por tenant no backend e escopos mínimos por conta conectada.
- Respeitar finalidade, base legal, preferências, opt-out, listas de supressão e consentimentos aplicáveis.
- Não inferir consentimento a partir da presença de um contato em uma lista.
- Não enviar dados acadêmicos, financeiros ou pessoais sensíveis para plataformas externas sem autorização e controles específicos.
- Tratar contatos, segmentos, templates, conteúdo de campanha, links e métricas externas como dados não confiáveis.
- Criar, editar, agendar, disparar, pausar ou cancelar campanhas; alterar listas; inscrever contatos em automações; e modificar preferências são ações com efeitos externos. Devem passar pelo policy engine e approval gate.
- Exigir revisão humana explícita antes de qualquer disparo para públicos reais. Pré-visualização e envio de teste devem ser separados do envio definitivo.
- Registrar ator, tenant, conta, toolkit, ação, público-alvo resumido, finalidade, decisão de aprovação e resultado sem armazenar conteúdo pessoal desnecessário.
- Não expor tokens, credenciais, links privados ou listas completas em logs.

A execução de ferramentas Composio permanece desativada por padrão: `COMPOSIO_TOOL_EXECUTION_ENABLED=false`.

## Fora do escopo

Esta categoria não implementa campanhas, sincronização de públicos, automações ou disparos. Ela apenas classifica os toolkits no catálogo MIRA.
