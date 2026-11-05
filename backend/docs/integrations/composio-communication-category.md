# Categoria 1 — Comunicação

A primeira categoria funcional do catálogo MIRA separa integrações Composio de canais nativos que a MIRA já opera.

## Toolkits Composio classificados como Comunicação

A classificação MIRA é aplicada por slug, sem alterar o catálogo oficial do Composio:

| Toolkit slug | Ferramenta | Uso |
| --- | --- | --- |
| `gmail` | Gmail | Caixa de entrada, pesquisa, rascunhos e e-mail |
| `outlook` | Outlook | E-mail corporativo |
| `slack` | Slack | Mensagens e colaboração interna |
| `microsoft_teams` | Microsoft Teams | Chat, colaboração e reuniões |
| `zoom` | Zoom | Reuniões |
| `zoom_chat` | Zoom Team Chat | Mensagens de equipe |
| `aircall` | Aircall | Telefonia e operações de contato |

Os slugs são identificadores de toolkit; as ações concretas devem sempre ser obtidas do catálogo vivo do Composio. Não fixar tool slugs de ações nesta camada. O catálogo pode mudar e cada ação precisa de seleção explícita na policy do tenant.

## Canais nativos MIRA

Estes canais não devem ser duplicados como integrações Composio nesta etapa:

| Canal | Provedores existentes | Configuração considerada |
| --- | --- | --- |
| WhatsApp | WAHA, Evolution API | URL e API key |
| E-mail transacional | Resend | API key e remetente |
| SMS | Twilio | Account SID, Auth Token e número de origem |

A API retorna apenas se cada provedor parece configurado. Ela nunca retorna credenciais ou valores de segredo. Gmail/Outlook representam caixas de correio conectadas pelo usuário; Resend é o canal transacional nativo da MIRA. São usos diferentes e podem coexistir.

## API

- `GET /integrations/composio/catalog/categories`: retorna categorias MIRA e os canais nativos.
- `GET /integrations/composio/catalog`: continua retornando o catálogo vivo; toolkits de Comunicação recebem `mira_category=communication` e `mira_channel`.

## Segurança e limites

- A classificação não habilita toolkit, conta ou ferramenta.
- A allowlist global, a policy do tenant, a conta conectada, o schema vivo e o approval gate continuam obrigatórios.
- A execução Composio permanece desligada por padrão.
- Não habilitar envio de mensagens, SMS ou chamadas por esta classificação.
- Ações de leitura, rascunho e escrita serão selecionadas por tool slug em etapa própria; ações com efeito externo continuam sujeitas ao approval gate.
- A classificação de WhatsApp, Resend e Twilio como canais nativos não os torna executáveis via Composio.
