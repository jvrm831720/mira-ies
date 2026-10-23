# Primeira fase — cobrança manual no MIRA Control Center

## Decisão confirmada

A primeira versão não integra gateway. O time interno cadastra links de pagamento já existentes e acompanha vencimentos e status manualmente. Não gerar links, não processar cartão e não inferir pagamento a partir de um clique ou retorno do navegador.

## Modelo de dados proposto

Validar os modelos atuais antes de criar migrações. Nomes conceituais:

### PlanVersion
- `id`, `plan_id`, `version`, `name`, `price_minor_units`, `currency`, `billing_cycle`, `limits_json`, `features_json`, `effective_from`, `created_by_admin_id`, `created_at`.
- Valor em unidade monetária mínima (por exemplo, centavos), não float.
- Imutável depois de publicada; alteração cria nova versão.

### OrganizationContract
- `id`, `tenant_id`, `plan_version_id`, `custom_price_minor_units`, `currency`, `starts_at`, `renews_at`, `ends_at`, `status`, `commercial_owner_admin_id`, `created_at`, `updated_at`.
- Mudança de preço exige ação explícita, vigência e motivo; manter o preço anterior no histórico.

### ManualInvoice
- `id`, `tenant_id`, `contract_id`, `amount_minor_units`, `currency`, `due_at`, `payment_url`, `status`, `paid_at`, `external_reference`, `notes_redacted`, `created_by_admin_id`, `updated_by_admin_id`, `created_at`, `updated_at`.
- Status inicial: `draft`, `pending`, `paid_manual`, `overdue`, `cancelled`.
- `paid_manual` deve aparecer na UI como confirmação manual, nunca como confirmação automática de gateway.
- Link externo só aceita HTTPS e comprimento limitado; evitar registrar query parameters sensíveis nos logs.
- Valor e moeda da cobrança ficam congelados após emissão; correção cria cancelamento e nova cobrança, com auditoria.

### AdminAuditEvent
- `id`, `actor_admin_id`, `action`, `target_type`, `target_id`, `tenant_id`, `reason`, `result`, `request_id`, `metadata_redacted`, `created_at`.
- Append-only para a aplicação; sem endpoint de edição/exclusão de eventos.
- Nunca incluir tokens, senhas, segredos, dados de cartão ou conteúdo integral de mensagens.

## Endpoints conceituais

Todos sob namespace administrativo isolado e autorizados no backend:
- `GET /admin/control-center/billing/summary`: contagens e totais separados por status.
- `GET /admin/control-center/invoices?due=overdue|7d|15d|30d&tenant_id=...`: lista paginada e filtrada.
- `POST /admin/control-center/invoices`: criar cobrança com organização, valor, moeda, vencimento, link e motivo.
- `PATCH /admin/control-center/invoices/{id}`: editar apenas campos permitidos antes da emissão; após emissão, usar fluxo de cancelamento/substituição.
- `POST /admin/control-center/invoices/{id}/mark-paid-manually`: exigir papel financeiro autorizado, motivo e confirmação; registrar evento de auditoria.
- `GET /admin/control-center/audit`: pesquisa paginada com autorização separada.

Não implementar esses endpoints até existir autenticação de equipe interna separada da autenticação tenant, RBAC no servidor e migração persistente. Não reutilizar o segredo administrativo global como credencial de browser.

## Regras de métricas

- **Contratado:** valor vigente dos contratos ativos.
- **Pendente:** soma de cobranças pendentes não vencidas.
- **Vencido:** cobranças pendentes com vencimento anterior ao momento atual.
- **Registrado como recebido manualmente:** soma de cobranças marcadas `paid_manual`, com aviso explícito de que não há confirmação automática.
- **MRR/ARR estimados:** normalizar contratos mensais/anuais; excluir cancelados e apresentar regras de cálculo.
- Usar timezone comercial configurado (padrão inicial `America/Sao_Paulo`) para rótulos de vencimento; armazenar timestamps em UTC.

## Segurança e testes obrigatórios

- Autorização administrativa independente do papel `admin` de um tenant.
- Testes negativos para sessão de cliente, suporte sem permissão financeira e tenant indevido.
- Auditoria de criação, edição, cancelamento e marcação manual como paga.
- Validação de URL HTTPS e bloqueio de esquemas como `javascript:` e `data:`.
- Testes de limites de data em 7/15/30 dias e mudança de mês/ano.
- Não expor notas internas ou dados comerciais a membros do cliente.
- Nenhuma migração destrutiva, merge ou deploy sem CI e revisão.
