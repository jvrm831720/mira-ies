# MIRA Education Engine — implantação isolada no Render (staging)

> Status em 2026-11-05: o Blueprint `exs-dbmdppifngtc738pdda0` foi criado no workspace Render, mas seu **primeiro plano foi bloqueado por `need_payment_info`** para os quatro recursos. Nenhum serviço foi provisionado, nenhuma migration foi aplicada e o ambiente ainda não funciona remotamente. O Render não oferece MariaDB gerenciado.

## Recursos propostos (todos **novos**, separados de mira-api-testes)

| Recurso | Tipo | Plano | Persistência |
|---|---|---|---|
| mira-education-mariadb-staging | pserv, imagem MariaDB 11.8 | 1c-2g | 10 GB em /var/lib/mysql |
| mira-education-engine-staging | pserv, Docker Frappe+ERPNext+Education | 2c-4g | 10 GB em /home/frappe/frappe-bench/sites |
| mira-education-queue-staging | Render Key Value, noeviction | 256mb | journal-snapshot |
| mira-education-cache-staging | Render Key Value, allkeys-lru | 256mb | off (cache efêmero) |

Região: **Virginia** para manter a comunicação privada próxima ao backend MIRA existente. Deploys automáticos do engine ficam desligados. O Blueprint tem `autoSync=false` e usa `existingResources=create_new` para **não adotar ou alterar** serviços já existentes.

**Custo estimado se rodando 24h por ~30 dias**, conforme tabela pública do Render consultada em 2026-11-05: motor 2c-4g US$85 + MariaDB 1c-2g US$25 + 2 Key Value 256mb x US$10 + 2 discos de 10 GB x US$0,25/GB = **aprox. US$135/mês**, além de impostos, tráfego e outros consumos aplicáveis. A cobrança pode ser proporcional ao uso. Confirmar o valor na página de planejamento do Render antes de ativar. Não assumir que o usuário autorizou esta despesa apenas por solicitar um serviço funcional.

## Fonte executável

- Motor baseado na imagem oficial `frappe/erpnext:v15.124.3` com **Education** no commit `1f89e2e827d61f62f430a5343376837fdc43213f`.
- Não é idêntico aos commits pinados de Frappe e ERPNext em `vendor/frappe/vendor-lock.json`: a imagem oficial traz seu próprio par Frappe/ERPNext. Essa diferença deve ser revisada antes de promover para produção.
- Dockerfile: `infra/frappe-render/Dockerfile`; instalação inicial: `bootstrap.sh`; processos: `supervisord.conf`; blueprint: `infra/frappe-render/render.blueprint.yaml`.
- O serviço cria inicialmente **um site sandbox sem alunos reais**, `ies-sandbox.internal`, e instala ERPNext + Education. Outros sites não são criados automaticamente.

## O que impede a instalação agora

O workspace Render retornou `need_payment_info`. Somente o titular da conta deve cadastrar um método de pagamento em **Render Dashboard → Workspace / Billing**. Jamais fornecer número de cartão nesta conversa.

Após a conta aceitar serviços pagos:
1. Rodar `plan_blueprint` para o Blueprint `exs-dbmdppifngtc738pdda0`; confirmar recursos e custos com o usuário.
2. Aprovar a sincronização **após revisão e autorização**. O Render iniciará os deployments; esperar estado `live` de todos e examinar logs/health.
3. Checar a instalação `bench --site ies-sandbox.internal list-apps`: `frappe`, `erpnext`, `education`. Validar MariaDB, Redis cache/queue, Worker, scheduler, processos HTTP.
4. Criar conta de serviço **somente leitura** para cada IES, com permissões explícitas aos DocTypes `Student`, `Student Attendance`, `Assessment Result`, `Program Enrollment`, `Fees`; nunca usar `Administrator` no gateway. Chaves restritas, controladas por serviço e sem impressão em logs.
5. Testar `GET /api/method/frappe.auth.get_logged_user`, perfil e collections sob `X-Frappe-Site-Name: ies-sandbox.internal`; confirmar que um outro site não pode ser acessado por troca de header ou URL.
6. Só depois configurar a PR #147 no FastAPI Render (`MIRA_EDUCATION_ENGINE_ENABLED=true`, `MIRA_EDUCATION_ENGINE_URL=http://<hostname-privado>.internal:10000`, `MIRA_EDUCATION_ENGINE_ALLOWED_SITES=ies-sandbox.internal`). **Não ativar automaticamente; exige PR testada e migration revisada.**
7. Na API MIRA, configurar a conexão com a conta de serviço por tenant via endpoint administrativo, `verify` e `enable`; vincular ID do aluno MIRA ao `Student.name` Frappe e testar a ficha.
8. A PR #151 exibe o módulo sob demanda na Vercel, sem enviar segredos ao navegador.

Não habilitar disparos, webhooks financeiros, cobrança, Pix, notas fiscais, reconciliação ou quitação antes de integração e homologação com fontes oficiais.

## Limites desta topologia

Apenas **staging de baixa escala**. O engine combina gunicorn, filas, scheduler e socketio em uma instância isolada e tem um site de teste. Ela não é arquitetura de alta disponibilidade: serviços com discos não permitem scale-out e deploys podem gerar indisponibilidade. MariaDB autogerenciado precisa backup lógico regular e testes de restauração, além de snapshots de disco. O Render alerta contra usar snapshot de disco como único mecanismo de restauração de bancos customizados.

Para uso comercial em várias IES: revisar capacidade, políticas LGPD, backup/restore, monitoração, desastres, sincronização de permissões, importação incremental e isolamento efetivo do Frappe com 2 tenants reais. A primeira versão jamais deve ser anunciada como produção pronta sem esses gates.

## Gate de segurança financeiro

O Blueprint só possui `pserv` e Key Value novos, não cria Postgres novo nem modifica `mira-api-testes`, a Vercel ou o Supabase. Segredos são gerados pelo Render e a conexão DB utiliza referências internas. O MariaDB é exclusivo da infraestrutura Frappe, separado do PostgreSQL existente da MIRA.
