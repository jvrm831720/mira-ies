# Composio — arquitetura de integração da MIRA

## Objetivo e limite desta entrega

A fundação inicial foi ampliada com o SDK Python, consulta dinâmica do catálogo e política persistida por instituição. A integração permanece desativada por padrão. Esta onda ainda não cria sessões remotas, não conecta contas externas e não executa ferramentas.

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
- O identificador é derivado de `tenant_id` com HMAC e `COMPOSIO_IDENTITY_SECRET`, dedicado e estável (não depende da rotação de `SECRET_KEY`). Não usar e-mail, nome, slug, identificador fornecido pelo navegador ou ID global compartilhado.
- A identidade é determinística para que sessões e conexões sejam reutilizadas entre requisições.
- Conexões de colaboradores individuais exigem um modelo separado e explícito. Não reutilizar automaticamente a conexão pessoal de um membro como conexão institucional.
- O backend sempre deriva o tenant do `AuthContext`. Nunca aceitar `tenant_id`, `composio_user_id` ou `connected_account_id` como autoridade enviada pelo cliente.

## Catálogo dinâmico e exposição por instituição

- O backend consulta o catálogo vivo pelo SDK Python oficial (`composio==0.31.0`); não há lista fixa de fornecedores.
- `GET /api/v1/integrations/composio/catalog` retorna o catálogo e a política da instituição autenticada.
- `PUT /api/v1/integrations/composio/catalog/{toolkit_slug}/policy` persiste a habilitação do toolkit e a seleção explícita de tool slugs.
- A política é isolada por tenant, protegida por RLS e começa desabilitada. Um toolkit só pode ser habilitado com ao menos uma ferramenta selecionada.
- O catálogo não é uma autorização de execução. O frontend futuro poderá editar a seleção, mas o backend permanece a autoridade.
- Os endpoints exigem papel admin e respondem com erro fechado quando o Composio está desativado ou sem credenciais.

## Dados persistidos

Migration `045_composio_foundation` cria:

- `tenant_composio_sessions`: identidade opaca por tenant e referência da sessão Composio.
- `tenant_composio_accounts`: toolkit, connected account, auth config e metadados não secretos.
- `tenant_composio_tool_audit`: ator, toolkit/tool, estado, aprovação, fingerprint e duração da execução.
- Migration `046_composio_toolkit_policies`: seleção de toolkits e ferramentas habilitadas por tenant.

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
- `COMPOSIO_IDENTITY_SECRET=` — segredo dedicado e estável para derivar IDs opacos; não reutilizar `SECRET_KEY` e não rotacionar sem plano de migração de identidades.
- `COMPOSIO_CALLBACK_URL=` — callback HTTPS da aplicação quando o fluxo OAuth for implementado.
- `COMPOSIO_ALLOWED_TOOLKITS=` — allowlist inicial explícita, vazia por padrão.

O SDK oficial está integrado ao backend, mas só é instanciado quando `COMPOSIO_ENABLED`, `COMPOSIO_API_KEY` e `COMPOSIO_IDENTITY_SECRET` estão configurados. Nenhuma chamada é feita sem essa configuração.

## Ondas de implementação após esta fundação

1. **Conexões:** endpoints admin para iniciar OAuth, callback, listar/revogar contas; tudo tenant-scoped.
2. **Policy Engine:** classificação de risco, RBAC por ferramenta, aprovação humana e aplicação da seleção ao contexto de sessão.
3. **Execução:** gateway backend-only, validação de argumentos, approval gate, idempotência, rate limits e auditoria append-only.
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

- Python SDK / quickstart: https://pypi.org/project/composio/
- Configuring sessions: https://docs.composio.dev/docs/configuring-sessions
- Authentication and user identity: https://docs.composio.dev/docs/authentication
- Configuring sessions and tool discovery: https://docs.composio.dev/docs/configuring-sessions
- Tools API and execution: https://docs.composio.dev/reference/api-reference/tools
