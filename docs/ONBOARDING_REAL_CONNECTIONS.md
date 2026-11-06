# Conexões reais durante o onboarding da MIRA

## Fluxo

1. Site e dados institucionais; descrição; responsável.
2. Etapa 4 cria o workspace com `/api/v1/onboarding/complete` e aplica a exigência de MFA. Sem tenant e sessão, nenhuma conexão pode ser iniciada.
3. Etapa 5 carrega o catálogo nativo (`/api/v1/connectors`) e Composio (`/api/v1/integrations/composio/catalog`), autorização habilitada e contas registradas por tenant.
4. Para OAuth, `/api/v1/integrations/composio/onboarding/auth-options` lista apenas configurações OAuth habilitadas e toolkits na allowlist. `/onboarding/connections/start` valida sessão humana MFA/AAL2, `settings.manage`, correspondência toolkit/auth config, e allowlist global, antes de criar Connect Link.
5. Depois da autorização do provedor, `/integrations/composio/callback` lê `state` e `connected_account_id`, chama `/api/v1/integrations/composio/connections/complete`, que valida token single-use e titularidade da conta no Composio, e retorna ao onboarding.
6. Conectores nativos usam suas telas de configuração existentes, em outra aba; o usuário volta e atualiza o estado. É permitido pular a etapa.

## Requisitos de homologação

Configurar no backend `COMPOSIO_ENABLED=true`, `COMPOSIO_API_KEY`, `COMPOSIO_IDENTITY_SECRET`, `COMPOSIO_ALLOWED_TOOLKITS` e `COMPOSIO_CALLBACK_URL=https://<origem-frontend>/integrations/composio/callback`, com URLs HTTPS e configurações OAuth habilitadas na conta Composio. O frontend deve encaminhar `/api/v1/*` ao backend autenticado. Confirmar redirecionamento HTTPS, cookies/armazenamento e retorno de sessão nos domínios reais.

**Importante:** conectar não habilita `TenantComposioToolkitPolicy`, ferramentas, campanhas, sincronizações ou disparos. Esses controles continuam independentes e fechados por padrão. `allow_multiple=True` permite autorizar outra conta do mesmo toolkit; escolha de conta para execução deverá obedecer às políticas existentes.

**Limitação:** esta UI apresenta fluxos OAuth hospedados pelo Composio e links para configuração nativa. Testes automatizados não substituem homologação real de cada provedor com credenciais válidas. O recurso fica bloqueado se as variáveis, auth configs ou allowlist estiverem ausentes.

## Cenários de aceite

- Usuário sem MFA não acessa o início de conexão OAuth.
- Toolkit fora da allowlist é rejeitado antes de gravar estado.
- Auth config inválido ou de outro toolkit é rejeitado.
- Callback sem `state` ou conta remota não ativa não confirma conexão.
- Mesmo workspace pode autorizar mais de uma conta por toolkit.
- Falha Composio não impede concluir o onboarding e ir para o workspace.
- Tenant diferente não lê nem confirma contas de outro workspace.
- Um conector configurado nunca é exibido como conectado sem evidência de autenticação.
