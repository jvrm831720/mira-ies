# Composio — arquitetura de integração da MIRA

## Objetivo e limite desta entrega

Esta entrega prepara a fundação da MIRA para receber o Composio. Ela **não ativa o Composio**, não cria sessões remotas, não conecta contas externas e não executa ferramentas. A integração permanece desativada por padrão até que as credenciais, políticas e fluxos de autorização sejam configurados.

O Composio é a camada de descoberta, autenticação e execução de ferramentas externas. A MIRA continua sendo a autoridade sobre identidade, tenant, permissões, contexto educacional, aprovação, política de dados e auditoria.

## Arquitetura alvo

```text
Usuário MIRA (MFA + RBAC)
        |
        v
MIRA API / Agent Orchestrator
        |
        +-- Context Builder (tenant-scoped)
        |
        +-- Tool Policy Engine (allowlist + risk class)
        |       |
        |       +-- Approval Gate (ações sensíveis)
        |
        +-- Composio Gateway (server-side only)
                |
                +-- Composio Session (identity per tenant)
                +-- Tool discovery / schema validation
                +-- Connected accounts / OAuth
                +-- Tool execution
        |
        v
Audit trail MIRA (metadata only; append-only)
```

## Identidade e isolamento

- O primeiro modelo é **workspace-owned / tenant-owned**: cada instituição tem uma identidade Composio estável e isolada.
- O identificador é derivado de `tenant_id` com HMAC e segredo do backend. Não usar e-mail, nome, slug, identificador fornecido pelo navegador ou ID global compartilhado.
- A identidade é determinística para que sessões e conexões sejam reutilizadas entre requisições.
- Conexões de colaboradores individuais exigem um modelo separado e explícito. Não reutilizar automaticamente a conexão pessoal de um membro como conexão institucional.
- O backend sempre deriva o tenant do `AuthContext`. Nunca aceitar `tenant_id`, `composio_user_id` ou `connected_account_id` como autoridade enviada pelo cliente.

## Dados persistidos

Migration `045_composio_foundation` cria:

- `tenant_composio_sessions`: identidade opaca por tenant e referência da sessão Composio.
- `tenant_composio_accounts`: toolkit, connected account, auth config e metadados não secretos.
- `tenant_composio_tool_audit`: ator, toolkit/tool, estado, aprovação, fingerprint e duração da execução.

Todas as tabelas têm RLS habilitado e forçado, com política baseada em `app.tenant_id`. A auditoria de execução é append-only. Não persistir access tokens, refresh tokens, API keys de terceiros, argumentos completos ou respostas completas nessas tabelas.

## Política de ferramentas

O catálogo amplo do Composio **não** significa que todas as ferramentas ficam automaticamente disponíveis ao agente.

Antes de habilitar execução real, implementar:

1. Allowlist de toolkits por tenant e por plano/contrato.
2. Allowlist de tool slugs por caso de uso e papel RBAC.
3. Classificação de risco: leitura, escrita reversível, escrita sensível e ação financeira/irreversível.
4. Aprovação humana obrigatória para ações sensíveis, envio externo, exclusão, alteração de permissões e operações financeiras.
5. Validação de schema e parâmetros no backend; o modelo não define a política.
6. Limites de taxa, timeout, idempotência e proteção contra replay.
7. Contexto mínimo necessário; nunca enviar base completa de alunos por padrão.
8. Política de retenção e redação de logs para dados pessoais e dados educacionais.

Ação de leitura também deve respeitar permissões e escopo de conta. Ações de escrita devem registrar intenção, decisão, aprovação e resultado sem guardar payload sensível bruto.

## Autenticação e credenciais

- A chave do projeto Composio fica somente no secret manager do backend como `COMPOSIO_API_KEY`.
- Não usar chave de organização quando uma chave de projeto com escopo mínimo for suficiente.
- Tokens OAuth/API das instituições permanecem sob custódia do Composio; MIRA armazena apenas IDs opacos e estado.
- O fluxo de conexão deve gerar Connect Link no backend e retornar ao frontend somente a URL de autorização e estado opaco.
- Callback/redirect deve usar URL HTTPS allowlisted da MIRA, com state anti-CSRF e validação de tenant/usuário.
- Nunca expor a chave Composio, sessão privilegiada ou ferramentas irrestritas ao navegador.

## Configuração

Variáveis reservadas:

- `COMPOSIO_ENABLED=false` — default fail-closed.
- `COMPOSIO_API_KEY=` — secret do backend; não versionar.
- `COMPOSIO_CALLBACK_URL=` — callback HTTPS da aplicação quando o fluxo OAuth for implementado.
- `COMPOSIO_ALLOWED_TOOLKITS=` — allowlist inicial explícita, vazia por padrão.

A fundação atual apenas valida a configuração e fornece uma identidade estável. O SDK oficial ainda não foi adicionado porque não há credencial, toolkit inicial ou fluxo de autorização aprovado nesta etapa.

## Ondas de implementação após esta fundação

1. **Provider SDK:** fixar versão compatível do SDK Python, criar cliente singleton, timeout e testes com mocks.
2. **Conexões:** endpoints admin para catálogo, iniciar OAuth, callback, listar/revogar contas; tudo tenant-scoped.
3. **Tool policy:** catálogo interno de toolkits/slugs permitidos, schemas validados e classificação de risco.
4. **Execução:** gateway backend-only, approval gate, idempotência, rate limits e auditoria append-only.
5. **Agente:** descoberta sob demanda de ferramentas autorizadas, sem carregar catálogo inteiro no prompt.
6. **Triggers:** webhooks com assinatura, replay protection, deduplicação e fila; nunca confiar no payload externo como contexto autorizado.
7. **E2E:** dois tenants, duas contas, tentativa de acesso cruzado, revogação, falha OAuth, tool read/write e aprovação.

## Critérios para ativação

- [ ] Credencial Composio criada e armazenada no secret manager.
- [ ] Toolkit(s) e escopos OAuth aprovados.
- [ ] RBAC e policy engine implementados e testados.
- [ ] Fluxo de conexão e revogação validado.
- [ ] Ações sensíveis bloqueadas sem aprovação humana.
- [ ] RLS validado com usuário de banco sem superuser e sem BYPASSRLS.
- [ ] Auditoria append-only testada.
- [ ] Testes E2E multi-tenant aprovados.
- [ ] Configuração de produção revisada antes de habilitar `COMPOSIO_ENABLED`.

## Referências oficiais

- Python SDK / quickstart: https://docs.composio.dev/docs/quickstart
- Authentication and user identity: https://docs.composio.dev/docs/authentication
- Configuring sessions and tool discovery: https://docs.composio.dev/docs/configuring-sessions
- Tools API and execution: https://docs.composio.dev/reference/api-reference/tools
