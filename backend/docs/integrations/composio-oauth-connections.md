# Composio Wave 2 — conexões OAuth e sessões

## Objetivo

Permitir que cada instituição **conecte contas externas** via Composio Connect Link, com isolamento por tenant, anti-CSRF e fail-closed. Credenciais OAuth **nunca** passam pela MIRA.

## Endpoints (`settings.manage`)

| Método | Rota | Função |
|--------|------|--------|
| `POST` | `/api/v1/integrations/composio/session` | Provisiona identidade opaca do tenant |
| `POST` | `/api/v1/integrations/composio/connections/start` | Gera Connect Link (após policy + allowlist) |
| `POST` | `/api/v1/integrations/composio/connections/complete` | Consome `state` e registra conta **após verificação remota** |
| `GET` | `/api/v1/integrations/composio/connections?sync=` | Lista contas (opcional sync remoto) |
| `DELETE` | `/api/v1/integrations/composio/connections/{id}` | Desabilita local + tenta revogar remoto |

## Hardening (Wave 2.1)

1. **Verificação remota obrigatória** — `complete` consulta a Composio e exige que a conta exista, pertença ao `composio_user_id` do tenant e bata com o toolkit do state.
2. **Consumo atômico do state** — `SELECT ... FOR UPDATE` antes de marcar `consumed`, impedindo double-spend concorrente.
3. **Callback só do servidor** — `callback_url` do cliente foi removido; usa exclusivamente `COMPOSIO_CALLBACK_URL`.
4. **Revogação honesta** — uso local é sempre bloqueado; a resposta distingue `remote_status=revoked|failed|skipped` e não declara sucesso remoto sem confirmação.

## Pré-condições para `start`

1. `COMPOSIO_ENABLED` + API key + identity secret.
2. Toolkit na allowlist global (`COMPOSIO_ALLOWED_TOOLKITS`).
3. Policy do tenant com `is_enabled=true` e `tool_slugs` não vazio.
4. `auth_config_id` válido no projeto Composio.
5. `COMPOSIO_CALLBACK_URL` HTTPS configurado no backend.

## State anti-CSRF

- Tabela `tenant_composio_oauth_states` (migration **048**), RLS ENABLE+FORCE.
- Token opaco de uso único, TTL 15 minutos, claim com lock de linha.
- Callback deve devolver o mesmo `state` ao endpoint `complete`.
- State de outro tenant é rejeitado (lookup sempre filtra `tenant_id` do `AuthContext`).

## Limites desta onda

- Não executa tools.
- Não aplica policy de tools à sessão de agente ainda.
- Não processa webhooks de triggers.
- `auth_config_id` continua configurado no painel Composio; a MIRA não cria auth configs.

## Variáveis

- `COMPOSIO_CALLBACK_URL` — URL HTTPS padrão de retorno (única origem aceita).
- Demais: as da fundação (`ENABLED`, `API_KEY`, `IDENTITY_SECRET`, `ALLOWED_TOOLKITS`).
