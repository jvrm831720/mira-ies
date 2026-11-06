# Wave 4D-B — Asaas oficial: runbook de homologação e go-live

## Resultado de código
A MIRA possui integração nativa com a API Asaas, independente das integrações
Composio usadas para ingestão financeira. Uma instituição pode ter **múltiplas
fontes financeiras** no mesmo workspace; a MIRA deduplica cobranças por
`(tenant, student, correlation_key)` quando o cliente declara a mesma obrigação
em mais de um ERP/importação. Em produção, ausência de correlação bloqueia
emissão. Não usamos nomes de alunos para inferir equivalência financeira.

O único dado financeiro que a IES cadastra na configuração de recebimentos é
**o walletId da carteira Asaas recebedora**. Esse dado é versionado por
workspace e não muda conforme o ERP de origem. O backend nunca aceita do
aluno campos de split, destinatário, valor, dados de API ou endereço remoto.
Para cada cobrança, aplica:

```json
{
  "split": [{ "walletId": "<carteira da IES homologada>", "percentualValue": 100 }]
}
```

São **100% do líquido** após tarifas Asaas, não 100% do bruto.
Conta emissora e recebedora devem ter walletIds diferentes. A emissora deve
possuir a função Split habilitada pelo Asaas, e a IES precisa de uma conta
Asaas própria e ativa; simples cadastro de walletId não autoriza transferência.

## Provisionamento e autorização
- `ASAAS_MODE=sandbox` por padrão. Chaves e webhook tokens por ambiente,
  hosts oficiais fixos, HTTPS, timeout, sem redirects ou proxies dinâmicos.
- `ASAAS_SANDBOX_ENABLED=false`, `ASAAS_PRODUCTION_ENABLED=false`,
  `ASAAS_WALLET_REVIEW_ENABLED=false` por padrão.
- `ASAAS_SANDBOX_ISSUER_WALLET_ID` e
  `ASAAS_PRODUCTION_ISSUER_WALLET_ID` são separados; cada ambiente
  valida sua própria carteira recebedora.
- `NATIVE_ACADEMIC_ENABLED`, `NATIVE_ACADEMIC_SERVICES_ENABLED` e
  `STUDENT_FINANCE_RECONCILIATION_ENABLED` precisam estar ativas em
  tenants homologados. Ativação geral da API exige aprovação separada.
- `ASAAS_SANDBOX_API_KEY`, `ASAAS_PRODUCTION_API_KEY`,
  `ASAAS_SANDBOX_WEBHOOK_TOKEN`, `ASAAS_PRODUCTION_WEBHOOK_TOKEN`
  e `ASAAS_WORKER_SECRET` devem ser geridos por secret store no Render,
  nunca enviados ao frontend ou commitados.
- `ASAAS_PRODUCTION_ENABLED=true` sozinho **não basta**:
  `APP_ENV=production`, chave e webhook válidos, configuração de carteira
  emissora, carteira IES verificada no ambiente, permissão institucional
  `critical.manage` e sessão MFA AAL2 ainda são necessários.
- Toda homologação de carteira exige um revisor diferente de quem a cadastrou,
  uma referência de evidência operacional, flag de revisão separada e trilha
  append-only com hash da referência. **O aplicativo não consegue verificar
  automaticamente a titularidade bancária apenas a partir do walletId**.
- As cobranças são criadas a partir do cadastro institucional do aluno:
  nome e CPF com dígitos validadores. CPF ausente interrompe o processo.
  Não pedimos que a IES informe esse dado na tela de Split; ele pertence ao
  cadastro acadêmico e ao contexto de cobrança autorizado.

## Ciclo das cobranças
1. Operador institucional com MFA prepara obrigação mais recente e elegível.
   Valor é o saldo devido calculado pelo servidor; vencimento deve ocorrer
   nos próximos 180 dias.
2. Uma `financial_key` única por obrigação/workspace impede duplicidade
   entre fontes Composio e CSV correlacionadas.
3. Criação de cliente Asaas usa `externalReference` estável. A cobrança
   recebe referência externa única, carteira destino congelada e
   `creation_state=prepared` em PostgreSQL.
4. Autorização de emissão é uma ação explícita. Em produção, o usuário
   autorizador deve ser diferente do criador. A MIRA reconfirma saldo,
   walletId, versão da homologação, ambiente e carteira da emissora.
5. A MIRA grava `creation_state=submitting` e **confirma a transação
   no banco antes de POST /payments**. Em timeout/5xx não refaz POST:
   estado `unknown`, `reconciliation_required=true` e busca manual
   pelo `externalReference`.
6. A resposta do provedor deve concordar com valor, cliente, método,
   identificador interno e destinatário do Split de 100%. Dados divergentes
   bloqueiam liberação e exigem reconciliação humana.

## Webhooks, liquidação e estornos
- Endpoint oficial: `POST /api/v1/webhooks/asaas/payments`.
- Validar o cabeçalho **`asaas-access-token`** (igualdade em tempo
  constante com token secreto por ambiente) antes de buscar qualquer tenant.
- Webhook compartilhado da conta emissora: a referência da cobrança
  previamente registrada determina o tenant; nunca confiar em
  `tenant_id` vindo do corpo do evento.
- Eventos sem cobrança conhecida recebem resposta retryable, não são
  descartados nem geram vínculo por aproximação.
- Persistir evento mínimo (ID, tipo, ID Asaas, split ID opcional, hash
  bruto do payload), sem armazenar payload com dados pessoais.
- `event_id` global único, log append-only, resposta idempotente em
  reentregas. Somente o worker autorizado aplica o evento.
- Worker: `POST /api/v1/webhooks/asaas/worker/{tenant_uuid}`, cabeçalho
  `X-MIRA-Asaas-Worker-Secret` armazenado em secret store. Configurar
  scheduler confiável (ex.: Render Cron) **por tenant**, com retries,
  observabilidade, quotas e alertas; endpoint nunca exposto no frontend.
- O worker reconsulta estado oficial Asaas antes de conciliar,
  evitando aceitar ordem de webhook como autoridade temporal.
- Pagamento recebido (`RECEIVED`) e Split liquidado (`DONE` ligado
  àquela cobrança, wallet ID da IES e split ID) são **dois fatos
  independentes**. MIRA não atualiza o ERP/registro original sem uma
  política de writeback homologada.
- Splits `PENDING`, `AWAITING_CREDIT`, `CANCELLED`, `REFUSED`
  ou `REFUNDED` nunca contam como liquidados.
- Em estorno/chargeback, o serviço reconsulta o provedor e pode
  **reverter os campos de confirmação** na projeção da cobrança. Auditoria
  do histórico de eventos permanece imutável.

## Operação e lançamento (bloqueios externos)
O código **não está homologado operacionalmente em produção** até concluir:
1. Asaas habilitar o Split na conta emissora e confirmar as tarifas,
   restrições, modalidade de conta e condições comerciais.
2. Criar e testar contas sandbox, IES recebedora sandbox e emissora
   sandbox, wallets diferentes, tokens, notificações e callback.
3. Aplicar migrations 063/064 no banco alvo com backup e validação RLS;
   validar privilégios e credenciais do Render, sem BYPASSRLS.
4. Executar teste integrado real em sandbox Asaas: provisionar cliente,
   criar Pix/boleto sintéticos, verificar 100% split e reproduzir
   `PAYMENT_RECEIVED`, `PAYMENT_SPLIT_DONE`, estorno, duplicidade,
   webhook fora de ordem, conta revogada e timeout.
5. Revisar LGPD (dados bancários, CPF do aluno, retenção e contratos);
   ativar alertas para `unknown`, `review`, `MISMATCH` e backlog
   do worker. Estabelecer plano de incidentes, conciliação manual,
   retries e reconciliação diária das entradas financeiras.
6. Obter aprovação operacional explícita da MIRA e da IES para um piloto
   de baixa exposição, com rollback das flags. Não habilitar cobranças
   em produção a partir do merge.

Fontes oficiais de referência:
- https://docs.asaas.com/docs/split-de-pagamentos
- https://docs.asaas.com/docs/split-faq
- https://docs.asaas.com/reference/listar-splits-pagos
- https://docs.asaas.com/reference/recuperar-um-unico-split-pago
- https://docs.asaas.com/docs/webhooks
