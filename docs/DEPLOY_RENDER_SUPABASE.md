# Deploy de teste: Render + Supabase Free

Este projeto fica preparado para **um ambiente de teste isolado**: frontend Next.js e API FastAPI no Render, com PostgreSQL no Supabase Free. O arquivo `render.yaml` cria os dois serviços no plano `free`; ele **não cria nem acessa** seu projeto Supabase, WAHA, Evolution ou Resend. Nenhum segredo deve ser colocado neste repositório.

## Antes de importar o Blueprint

1. No Supabase, use um projeto separado para teste/staging, não o banco de produção. No Dashboard do Supabase, abra **Connect → Session pooler** e copie a connection string completa. A Session Pooler é o modo recomendado para um backend persistente em rede IPv4 e aceita prepared statements; evite o Transaction Pooler para este backend.
2. No Render, importe `jvrm831720/project-beacon` como Blueprint usando `render.yaml`. Selecione a branch principal. O Render solicitará `DATABASE_URL`; informe a URL do pooler de teste, trocando o prefixo `postgresql://` por `postgresql+asyncpg://`. Mantenha host, porta, usuário e database exatamente como aparecem no Dashboard. Se a senha contiver caracteres especiais, faça URL-encode antes de inserir.
3. O Blueprint ativa `DATABASE_SSL_REQUIRE=true`, gera `SECRET_KEY` e `MIRA_ADMIN_SECRET` no Render, e executa `alembic upgrade head` antes do deploy. Isso cria/aplica o schema **no banco indicado em `DATABASE_URL`**.
4. O frontend usa um proxy Same-Origin no Next, e `BACKEND_API_URL` é ligado ao endereço privado do serviço API no Render. Não é necessário expor a chave do banco ou URL da API no JavaScript do browser.

A conexão Postgres é configurada somente pela variável `DATABASE_URL`; `DATABASE_URL_SYNC` é opcional e derivada para as migrações. Não use a connection string do Supabase no frontend.

## Variáveis para habilitar os canais

Adicione-as em **Render → serviço `beacon-api` → Environment** quando as respectivas credenciais estiverem prontas. Os segredos ficam no Dashboard do Render, nunca no Git, frontend ou mensagens.

| Variável | Valor/uso |
|---|---|
| `WHATSAPP_PROVIDER` | `waha` ou `evolution`; escolha apenas um ativo por vez. O Blueprint inicia com `evolution` para preservar a configuração histórica. |
| `WAHA_API_URL` | URL base do seu serviço WAHA no Render, sem `/api/sendText`. |
| `WAHA_API_KEY` | Chave de API WAHA (`X-Api-Key`). |
| `WAHA_SESSION` | Nome da sessão WAHA; normalmente `default`. |
| `EVOLUTION_API_URL` | URL base da Evolution API. |
| `EVOLUTION_API_KEY` | Chave da API Evolution. |
| `EVOLUTION_INSTANCE` | Nome da instância na Evolution. |
| `RESEND_API_KEY` | Chave privada Resend. |
| `EMAIL_FROM` | Remetente/domínio verificado no Resend, por exemplo `Mira <acesso@seudominio.com>`. |
| `MIRA_PUBLIC_URL` | URL HTTPS real do serviço `beacon-web` no Render; configure depois que o domínio for provisionado para que links de redefinição de senha funcionem. |

O backend não faz fallback automático entre WAHA e Evolution nem envia em duplicidade: alterar `WHATSAPP_PROVIDER` seleciona o destino para login e mensagens. Os endpoints de código por e-mail usam Resend; recuperação de senha por e-mail continua enviando um link de uso único.

## Criar conta de demonstração sem misturar dados

Após o primeiro deploy e a migração do **banco de teste**, o app cria o tenant `default`. Crie um usuário de teste com um e-mail e, para validar WhatsApp, um número controlado por você. A rota administrativa exige o segredo do Render fora de `APP_ENV=development`:

```bash
curl -X POST "https://<URL-DA-API>/api/v1/auth/admin/users" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Secret: $MIRA_ADMIN_SECRET" \
  -d '{"tenant_slug":"default","display_name":"Conta de teste","email":"<EMAIL-DE-TESTE>","password":"<SENHA-DE-12-CARACTERES-OU-MAIS>","phone":"<TELEFONE-DE-TESTE>"}'
```

Não publique o valor de `MIRA_ADMIN_SECRET` nem a senha. O código de e-mail e o OTP de WhatsApp são reais quando esses provedores estiverem configurados, então use somente um endereço/telefone de teste que você controla. O OTP expira em cinco minutos e só pode ser usado uma vez.

## Custos e limitações do plano gratuito

- Os dois serviços de app no Blueprint são fixados em `free`, mas o Render pode suspender serviços gratuitos após inatividade; a primeira visita pode demorar a acordar. Os limites gratuitos são compartilhados conforme as regras atuais da conta/workspace.
- O banco continua sujeito às cotas e regras de pausa do Supabase Free. A connection string deve vir do painel; credenciais inventadas ou coladas no arquivo não funcionam.
- O filesystem dos serviços gratuitos é efêmero. `MODEL_STORAGE_DIR=/tmp/model_artifacts` é intencional: artefatos/modelos locais podem desaparecer em reinícios, então não trate o serviço como armazenamento persistente.
- O blueprint não inclui um worker/Redis, pois isso exigiria infraestrutura adicional. O login, a API síncrona e a UI não dependem da fila; processamento assíncrono da régua precisa de uma decisão separada de infraestrutura.
- WAHA em hospedagem gratuita pode sofrer com suspensão/armazenamento efêmero do provedor de hospedagem. Verifique a persistência da sessão WhatsApp no serviço WAHA existente e confirme que o uso atual não exige uma instância sempre ligada.

Fontes oficiais: [Render Blueprints](https://render.com/docs/blueprint-spec), [limites dos serviços gratuitos Render](https://render.com/docs/free), [Supabase — conexão ao Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres) e [WAHA — envio de mensagens](https://waha.devlike.pro/docs/how-to/send-messages/).
