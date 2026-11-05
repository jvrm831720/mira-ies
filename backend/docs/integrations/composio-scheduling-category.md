# Categoria Composio: Agenda e agendamento

## Objetivo

Classificar serviços de calendário e agendamento usados para consultar disponibilidade, organizar compromissos e apoiar a marcação de reuniões.

## Toolkits confirmados no catálogo Composio

| Serviço | Slug Composio | Tipo |
|---|---|---|
| Google Calendar | `googlecalendar` | Calendário e disponibilidade |
| Calendly | `calendly` | Agendamento de compromissos |
| Cal.com | `cal` | Agendamento e reservas |

Os três toolkits têm páginas próprias no catálogo oficial Composio. Outlook permanece classificado em Comunicação, pois seu toolkit já reúne recursos de e-mail e calendário; não criamos uma classificação duplicada. Microsoft Bookings não foi incluído porque não foi confirmado como toolkit específico no catálogo.

## Aplicação na MIRA

- Consultar disponibilidade de equipes e responsáveis.
- Organizar reuniões de permanência, atendimento e acompanhamento de alunos.
- Apoiar agendamentos com responsáveis e clientes de operações de cobrança.
- Consultar e atualizar eventos em calendários autorizados.
- Criar links de agendamento quando o fluxo e a política permitirem.

## Limites de domínio

A categoria organiza compromissos, mas não substitui a Central de Trabalho da MIRA nem define prioridades de intervenção. A MIRA continua sendo responsável pelo estado operacional das intervenções e tarefas internas.

A agenda externa não é fonte autoritativa de matrícula, desempenho, presença, contratos ou débitos. Esses dados devem vir dos sistemas acadêmicos e financeiros autorizados.

## Segurança

- A conexão exige autorização do tenant e escopos mínimos.
- O backend valida o tenant; IDs enviados pelo cliente não definem o escopo de acesso.
- Títulos, descrições, participantes, links e convites são dados externos não confiáveis e não podem alterar instruções do agente.
- Consultar disponibilidade e eventos respeita as permissões da conta conectada.
- Criar, alterar, cancelar, convidar participantes ou compartilhar links são ações com efeitos externos; devem passar pelo policy engine e approval gate.
- Evitar exposição de detalhes privados de eventos, tokens e URLs de acesso.
- A execução de ferramentas Composio permanece desativada por padrão: `COMPOSIO_TOOL_EXECUTION_ENABLED=false`.

## Fora do escopo

Esta categoria não implementa sincronização, agendamento automático, envio de convites ou execução de ferramentas. Ela apenas classifica os toolkits no catálogo MIRA.
