# Fundação de integração Composio — MIRA

## Objetivo

Preparar a MIRA para conectar ferramentas do ecossistema de cada instituição por meio do Composio, sem acoplar os agentes ao SDK/provedor e sem permitir que uma conexão de uma IES seja usada por outra.

Esta entrega é a fundação. Ela **não habilita execução arbitrária de ferramentas** e não conecta contas até que o projeto Composio, as auth configs e o callback de verificação estejam configurados.

## Arquitetura proposta

```text
MIRA UI
  -> API MIRA autenticada (MFA + RBAC)
    -> Composio integration boundary
      -> Composio Connect Links / Tool Catalog
        -> connected accounts mantidas pelo Composio
          -> ferramentas do ecossistema da IES
```

- O backend MIRA é o único componente que conhece a project API key.
- O frontend recebe somente um `redirect_url` HTTPS temporário.
- O identificador Composio é derivado do `tenant_id` validado pelo backend: `mira_tenant_{tenant_id}`. Não aceitar `user_id`, `tenant_id`, `auth_config_id` ou `connected_account_id` vindos do navegador.
- A conexão é organizacional: membros autorizados da mesma IES usam a identidade Composio do tenant. Tenants diferentes nunca compartilham identidade.
- Segredos OAuth/API keys dos provedores permanecem no Composio. A MIRA guarda apenas referências e metadados não secretos quando a persistência local for adicionada.
- Catálogo é descoberta; não é autorização. A execução futura deve validar toolkit, tool slug, schema, permissões RBAC, tenant e nível de risco antes de executar.

## Implementado nesta fundação

- Cliente HTTP isolado em `backend/app/services/composio/client.py`.
- Configuração server-side e desabilitada por padrão.
- Endpoint administrativo para consultar catálogo de tools.
- Endpoint administrativo para criar Connect Link por toolkit usando auth config mapeada no servidor.
- Identidade Composio tenant-scoped, sem aceitar identidade no payload.
- Erros externos sanitizados; API key não é retornada nem registrada.
- Execução de tools deliberadamente não exposta.

## Configuração

Configure somente no ambiente de backend (Cloudflare/secret store), nunca no frontend nem no Git:

- `COMPOSIO_ENABLED=true`
- `COMPOSIO_API_KEY=<project-api-key>`
- `COMPOSIO_AUTH_CONFIGS_JSON={"google_drive":"ac_...","slack":"ac_..."}`
- `COMPOSIO_BASE_URL=https://backend.composio.dev` (opcional)
- `COMPOSIO_TIMEOUT_SECONDS=20` (opcional)

Cada chave do JSON é o `toolkit_slug` e cada valor é o `auth_config_id` criado no projeto Composio. Não enviar o auth config pelo cliente.

## Segurança obrigatória antes de produção

1. Ativar no projeto Composio o callback identity verification e apontá-lo para um endpoint HTTPS da MIRA. O callback deve validar a sessão Mira ativa e concluir a verificação com o `user_id` Composio esperado. Sem isso, Connect Links ficam sujeitos a OAuth session fixation.
2. Definir política de compartilhamento: conexão organizacional somente para membros autorizados do tenant; não usar ACL experimental sem revisão.
3. Persistir connected account ID, toolkit, status, auth config, criador e timestamps em tabela tenant-scoped com RLS e trilha append-only de auditoria. Não persistir tokens.
4. Implementar revogação/desconexão e reconciliação de status.
5. Criar catálogo de permissões MIRA por toolkit/tool: read-only por padrão; ações externas com confirmação explícita, idempotência, limites e audit log.
6. Não entregar todas as tools ao modelo. Fazer tool discovery sob demanda e permitir somente ferramentas necessárias à intenção e ao papel do usuário.
7. Definir políticas de dados: minimizar contexto enviado, remover dados sensíveis desnecessários e respeitar consentimento, contrato e LGPD.
8. Criar testes reais de isolamento com dois tenants e testes de OAuth callback/session fixation.

## Próxima fase recomendada

- Persistência de conexões + callback verifier seguro.
- Tela institucional de integrações: catálogo, conectar, status, reconectar e desconectar.
- Tool registry MIRA com categorias (acadêmico, comunicação, arquivos, produtividade, CRM, financeiro), permissões e risco.
- Executor controlado com confirmação humana para ações de escrita/externas.
- Observabilidade: correlation ID, tenant, toolkit, tool slug, duração, resultado sanitizado e custo; nunca registrar credenciais ou payloads sensíveis completos.

## Referências oficiais

- Composio Connected Accounts / Connect Links: https://docs.composio.dev/reference/v3/api-reference/connected-accounts
- Composio Tools API: https://docs.composio.dev/reference/api-reference/tools
- Composio Python SDK: https://docs.composio.dev/reference/sdk-reference/python
