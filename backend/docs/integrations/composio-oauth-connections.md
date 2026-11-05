# Composio Wave 2 — conexões OAuth e sessões

## Objetivo

Permitir que cada instituição **conecte contas externas** via Composio Connect Link, com isolamento por tenant, anti-CSRF e fail-closed. Credenciais OAuth **nunca** passam pela MIRA.

## Endpoints (`settings.manage`)

| Método | Rota | Função |
|--------|------|--------|
| `POST` | `/api/v1/integrations/composio/session` | Provisiona identidade opaca do tenant |
| `POST` | `/api/v1/integrations/composio/connections/start` | Gera Connect Link (após policy + allowlist) |
| `POST` | `/api/v1/integrations/composio/connections/complete` | Consome `state` e registra conta |
| `GET` | `/api/v1/integrations/composio/connections?sync=` | Lista contas (opcional sync remoto) |
| `DELETE` | `/api/v1/integrations/composio/connections/{id}` | Revoga local + remoto |

## Pré-condições para `start`

1. `COMPOSIO_ENABLED` + API key + identity secret.
2. Toolkit na allowlist global (`COMPOSIO_ALLOWED_TOOLKITS`).
3. Policy do tenant com `is_enabled=true` e `tool_slugs` não vazio.
4. `auth_config_id` válido no projeto Composio.
5. Callback HTTPS (ou `localhost` em development).

## State anti-CSRF

- Tabela `tenant_composio_oauth_states` (migration **048**), RLS ENABLE+FORCE.
- Token opaco de uso único, TTL 15 minutos.
- Callback deve devolver o mesmo `state` ao endpoint `complete`.
- State de outro tenant é rejeitado (lookup sempre filtra `tenant_id` do `AuthContext`).

## Limites desta onda

- Não executa tools.
- Não aplica policy de tools à sessão de agente ainda.
- Não processa webhooks de triggers.
- `auth_config_id` continua configurado no painel Composio; a MIRA não cria auth configs.

## Variáveis

- `COMPOSIO_CALLBACK_URL` — URL HTTPS padrão de retorno.
- Demais: as da fundação (`ENABLED`, `API_KEY`, `IDENTITY_SECRET`, `ALLOWED_TOOLKITS`).
