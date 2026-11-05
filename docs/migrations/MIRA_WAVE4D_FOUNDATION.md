# MIRA Education — Wave 4D-A: pagamentos em sandbox

## Estado e limites
Esta Wave implementa apenas **preparação e validação estrutural**, sem movimentação
financeira. Ela não chama API de checkout, cria Pix, emite boleto, gera links de
pagamento, realiza reembolso, autoriza desconto ou confirma liquidação.

A Wave 4C permanece fonte de verdade **informativa**. Um estado de cobrança
`reported_paid` ou um webhook assinado de laboratório `paid_reported` não
equivale a liquidação confirmada. O contrato de retorno mantém
`settlement_confirmed: false`, e a API não altera
`mira_finance_observations` nem `mira_student_financial_references`
durante as operações de sandbox.

## Modelo de adaptação multi-tenant
- `mira_payment_provider_profiles`: configurações individuais por
  workspace e perfil financeiro da Wave 4C. Um workspace pode configurar
  vários provedores e contas Composio simultaneamente. As conexões
  não são copiadas: usa-se o ID existente da conta com estado ativo.
- `mira_student_payment_intents`: rascunhos de método Pix/boleto, sempre
  com saldo calculado no servidor a partir da última observação da
  **mesma origem e do mesmo aluno**. O valor é congelado; o frontend não
  pode criar valores arbitrários, redirecionamentos ou códigos bancários.
- `mira_student_payment_evidence`: eventos sintéticos HMAC, identificados
  unicamente por workspace/provedor/evento. Nunca são o comprovante de
  liquidação do PSP; o payload completo não é persistido.
- Migration `063_payment_sandbox`: FKs compostas por tenant,
  `ENABLE/FORCE ROW LEVEL SECURITY` nas três tabelas, triggers
  que proíbem UPDATE e DELETE dos rascunhos e eventos. Todas as
  mutações críticas exigem AAL2 e RBAC institucional.

Os dados e as regras específicas do cliente são metadados versionados,
não forks, scripts Python arbitrários nem DDL disparada em runtime.
A API impede que a configuração de um provedor permita acessar
obrigações de outra origem ou alunos de outro tenant.

## Endpoints
Prefixo institucional:
`/api/v1/native-academic/finance/payments`

- `GET/POST /providers`: listar/criar perfis desabilitados.
- `PUT /providers/{id}/sandbox-enable`: habilitar *somente* sandbox
  quando a conta Composio pertence ao workspace e está ativa.
  Conectores customizados `custom_pending` não podem ser ativados.
- `POST /drafts`: rascunho idempotente, congelando o saldo observado
  e rejeitando estados desconhecidos, pagos, cancelados ou sem saldo.
- `GET /drafts`, `GET /drafts/{id}/events`: registros e auditoria.
- `GET /api/v1/student-portal/services/payments/drafts`: leitura
  **apenas dos próprios** rascunhos do estudante; sem ação de pagar.
- `POST /api/v1/payment-sandbox/events/{tenant_id}/{provider_id}`:
  recepção exclusiva de eventos **sintéticos de laboratório**.

## Contrato HMAC do laboratório
Usar exclusivamente `STUDENT_PAYMENTS_SANDBOX_HMAC_SECRET`, um segredo
aleatório forte de pelo menos 32 bytes, nunca uma chave de produção.
Nunca enviar ou revelar esse segredo no frontend.

O corpo JSON assinado tem exatamente estes campos:
`event_id`, `intent_id`, `account_id`, `state`, `amount`,
`currency`, `occurred_at`. `currency` deve ser `BRL`; `amount`
é uma string decimal explícita, e `occurred_at` usa ISO 8601 com fuso.
Estados permitidos: `created`, `processing`,
`partially_paid_reported`, `paid_reported`, `failed`,
`refunded_reported`, `chargeback_reported`.

Headers: `X-MIRA-Sandbox-Timestamp` (Unix seconds, dez dígitos) e
`X-MIRA-Sandbox-Signature` (`sha256=<64 hex>`).
A chave derivada é `HMAC_SHA256(master_secret, "mira:sandbox:"
+ tenant_uuid + ":" + provider_uuid)`. A assinatura é
`HMAC_SHA256(derived_key, "v1:" + timestamp + ":" + raw_body)`,
sem normalizar o JSON recebido.

Recusar assinatura errada, corpo maior que 16 KiB, timestamp fora da
janela de cinco minutos, conta revogada, vínculo de provedor diferente,
valor acima do saldo ou event_id repetido com hash divergente. A mesma
mensagem repetida tem resposta idempotente. Esses controles autenticam
somente o ambiente sintético: **não substituem a assinatura oficial
de Stripe, Asaas, Pagar.me, banco ou outro PSP**.

## Flags (todas desabilitadas por padrão)
- `NATIVE_ACADEMIC_ENABLED=false`
- `NATIVE_ACADEMIC_SERVICES_ENABLED=false`
- `STUDENT_FINANCE_RECONCILIATION_ENABLED=false`
- `STUDENT_PAYMENTS_SANDBOX_ENABLED=false`
- `STUDENT_PAYMENTS_SANDBOX_WEBHOOKS_ENABLED=false`
- `STUDENT_PAYMENTS_SANDBOX_HMAC_SECRET=`

Composio mantém conexão OAuth e validação de conta a partir da Wave 4C;
**não habilitar Composio tools de escrita/pagamento por causa desta Wave**.
Somente código, migrations e testes em CI. Não habilitar flags, executar
deploy ou migrar o Supabase sem gate e autorização separados.

## Wave 4D-B — homologação real (não entregue)
1. Escolha por workspace e contrato de um PSP/provedor específico; checar
   Pix, boleto, cartão, competência regulatória, tarifas, chargebacks e
   cadastros recebedores.
2. Implementar o adapter oficial por provedor, com credenciais
   individualizadas/criptografadas, anti-SSRF e validação de identidade.
3. Criar pagamentos com aprovação, limites, idempotência remota,
   bloqueio de tentativa dupla e reconciliação por transação externa.
4. Validar **webhook oficial do provedor**, reconsultar liquidação na fonte
   bancária quando necessário, tratar parcial, estorno, chargeback,
   falha, pagamento tardio e divergência.
5. Só elevar estado para `confirmed_settled` após prova do PSP
   homologado, conciliação e auditoria imutável.
6. Homologar em sandbox do PSP com dados sintéticos e depois com
   um piloto formalmente autorizado. Somente então expor "Pagar" ao aluno.

## Gates de revisão
- Migrations 063 e grafo Alembic no PostgreSQL de CI.
- FORCE RLS e policy tenant por tabela; triggers append-only.
- Testes com dois tenants, múltiplos provedores, mesma referência em
  origens diferentes, idempotência, assinatura adulterada, eventos
  fora da janela e replay.
- Frontend lint, TypeScript e build.
- Revisão de autorização, minimização de dados e logs sensíveis.
