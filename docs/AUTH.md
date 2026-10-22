# Autenticação — Mira

A aplicação oferece sessões de usuário por e-mail e senha, código temporário no e-mail via Resend ou código temporário no WhatsApp via WAHA/Evolution. Cada conta pertence a uma única instituição (`tenant`). As senhas são armazenadas com scrypt; códigos e tokens são guardados somente como hashes e expiram. Sessões são assinadas e expiram após uma hora. A redefinição de senha invalida as sessões anteriores.

As rotas principais ficam sob `/api/v1/auth`:

- `POST /login/password` recebe `email` e `password` e retorna `access_token`.
- `POST /whatsapp/request` recebe `phone` e solicita um código temporário.
- `POST /whatsapp/verify` recebe `phone` e `code` e retorna `access_token`.
- `POST /email/request` recebe `email` e solicita um código temporário via Resend.
- `POST /email/verify` recebe `email` e `code` e retorna `access_token`.
- `POST /password/forgot` recebe `email` e inicia recuperação sem revelar se a conta existe.
- `POST /password/reset` recebe `token` e `new_password`.
- `POST /admin/users` provisiona uma conta vinculada a `tenant_slug`.

Use as sessões nas rotas protegidas com:

```http
Authorization: Bearer <access_token>
```

As API keys legadas continuam aceitas nas integrações via `X-API-Key` ou `Authorization: Bearer <api_key>`.

## Provisionar uma conta

Primeiro, a instituição precisa existir como tenant. Em desenvolvimento, o tenant `default` é criado no bootstrap. Para criar uma conta no PowerShell:

```powershell
$body = @{
  tenant_slug = "default"
  display_name = "Nome do usuário"
  email = "usuario@instituicao.edu.br"
  password = "UmaSenhaForte#2026"
  phone = "+5511999999999"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/api/v1/auth/admin/users" `
  -ContentType "application/json" `
  -Headers @{ "X-Admin-Secret" = $env:SECRET_KEY } `
  -Body $body
```

A senha precisa ter pelo menos 12 caracteres. O telefone é opcional para acesso por senha, mas necessário para login via WhatsApp. Em `APP_ENV=development`, o header pode ser omitido. Fora de development, `X-Admin-Secret` deve ser igual a `MIRA_ADMIN_SECRET` (ou, se não definido, `SECRET_KEY`). Configure um `MIRA_ADMIN_SECRET` longo e distinto em produção; proteja e rotacione esse segredo e nunca o envie no frontend.

## Envio de mensagens

Configure o backend com as variáveis abaixo. `EMAIL_FROM` deve ser um remetente/domínio verificado na conta Resend, e `MIRA_PUBLIC_URL` deve ser a URL HTTPS pública da aplicação em produção. Os valores não devem ser commitados no Git.

```dotenv
APP_NAME=Mira
MIRA_PUBLIC_URL=http://localhost:3000
MIRA_ADMIN_SECRET=
DATABASE_SSL_REQUIRE=true
RESEND_API_KEY=
EMAIL_FROM=
WHATSAPP_PROVIDER=evolution
EVOLUTION_API_URL=
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=
WAHA_API_URL=
WAHA_API_KEY=
WAHA_SESSION=default
```

`WHATSAPP_PROVIDER` escolhe exatamente um provedor ativo (`evolution` ou `waha`); não há fallback automático, para evitar enviar uma mensagem duplicada quando o resultado de um provedor for incerto. Evolution precisa de `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE`. WAHA precisa de `WAHA_API_URL`, `WAHA_API_KEY` e `WAHA_SESSION`; o cliente envia para `POST /api/sendText`, usando `X-Api-Key` e um `chatId` E.164 terminado em `@c.us`. Ambas as configurações podem coexistir para alternância pela variável `WHATSAPP_PROVIDER`.

Sem `RESEND_API_KEY` e `EMAIL_FROM`, o endpoint de recuperação retorna `503`. Sem a URL e a chave do provedor WhatsApp selecionado, a solicitação de código retorna `503`. Configure os serviços no `.env` local do backend ou no ambiente de implantação. Nunca versione chaves reais.

Para subir a versão gratuita de teste isolada e criar uma conta de demonstração, siga [DEPLOY_RENDER_SUPABASE.md](./DEPLOY_RENDER_SUPABASE.md). O bootstrap não registra chaves de API de produção nos logs.

## Webhooks e chaves legadas

Cada tenant pode continuar usando sua API key (`bkn_...`) em `X-API-Key`. A chave é gerada na criação do tenant e não é armazenada em texto puro. No modo development, `DEV_API_KEY` padrão é `bkn_dev_change_me_in_production`.
