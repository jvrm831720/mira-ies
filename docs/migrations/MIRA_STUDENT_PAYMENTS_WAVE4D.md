# Wave 4D-A — Asaas Split Payment: preparação segura

## Decisão de produto

- O Asaas é o único PSP desta Wave. A IES informa apenas o
  **walletId de sua própria conta Asaas** e, se houver várias integrações
  financeiras, seleciona a origem pertinente.
- A MIRA não coleta conta bancária, agência, chave Pix ou API key da IES.
  O eventual saque/transferência para o banco da IES é administrado dentro da
  própria conta Asaas, de acordo com suas regras, cadastros e homologação.
- O split futuro da cobrança avulsa emitida pela conta operadora da MIRA é:

  `{"split":[{"walletId":"<walletId-validado-da-IES>","percentualValue":100}]}`

  Trata-se de **100% do netValue**, depois das tarifas Asaas. A conta
  emissora da cobrança **não** pode ser o próprio destino.
  Sem taxa/plano próprios, a plataforma retém 0% do líquido do split.

- A configuração de split nas contas Asaas precisa ser habilitada pelo
  titular via Integrações → Segurança. Uma conta de destino precisa ser
  uma conta Asaas, e seu `walletId` não comprova titularidade.
- A MIRA registra o destino como `pending` (ainda não verificado).
  Um walletId válido em formato UUID **não** significa que pertence à IES.
  A verificação do titular deverá ocorrer pelo onboarding/homologação Asaas.
- Se a própria IES emitir a cobrança em sua conta Asaas, **não** se
  aplica split para a mesma carteira; o modo direto exigirá adapter próprio.

## Metadados e isolamento

- Cada workspace pode ter múltiplas integrações Composio/CSV, cada qual com
  perfis de mapeamento, e mais de um vínculo de pagamento Asaas.
- Os perfis de pagamento mantêm vínculo tenant+finance_profile+walletId,
  sem compartilhamento cruzado.
- A regra do repasse NÃO é configurável pelo cliente: 100% do líquido
  permanece fixo no motor. Não aceitamos splits arbitrários ou chaves de
  terceiros em payload de usuário.
- Migration 063: conectores Asaas sandbox, ordens de preparo, eventos
  de aprovação append-only com RLS/FORCE RLS e FKs compostas tenant+ID.
- Ordem financeira sempre é derivada da fonte mais recente da Wave 4C.
  Sem valor informado pelo navegador, sem status unknown/reported_paid
  interpretado como cobrança devida, sem fonte de outro tenant.
- Aprovação por duas pessoas distintas com MFA AAL2, trilha auditável,
  idempotência e revalidação de valores.

## Contratos oficiais e diferenças importantes

- Cobrança avulsa: campo `split`, com `walletId` e
  `percentualValue: 100` (percentual aplicado ao `netValue`).
- Checkout Asaas é um produto distinto que utiliza o campo `splits`.
- Para acompanhar a quitação financeira, `PAYMENT_RECEIVED` indica
  saldo disponível **na conta de emissão**, mas não prova que a IES recebeu
  seu split. A conclusão do split é sinalizada pelo
  `PAYMENT_SPLIT_DONE` (por `additionalInfo.splitId`).
- `PAYMENT_CONFIRMED` não implica disponibilidade do saldo;
  `PAYMENT_REFUNDED`, chargebacks e divergências exigem reversão/conferência.
- O webhook Asaas exige `authToken` próprio e o header
  `asaas-access-token`; os eventos têm `id` para idempotência.
  Verificar conta emissora, evento, cobrança, splitId, destinatário,
  netValue, chargeback e informação da API antes de lançar liquidação
  ou repasse definitivo no Portal do Aluno.

Fontes Asaas:
- https://docs.asaas.com/docs/split-de-pagamentos
- https://docs.asaas.com/docs/split-em-cobrancas-avulsas
- https://docs.asaas.com/reference/recuperar-walletid
- https://docs.asaas.com/docs/webhook-para-cobrancas
- https://docs.asaas.com/docs/faq-de-webhooks

## Ativado apenas em código

- `STUDENT_PAYMENT_PREPARATION_ENABLED=false` por padrão;
  também exigidas as flags nativas e da conciliação.
- O conector Asaas nasce sandbox, disabled e `pending`.
- O endpoint `POST .../orders/{id}/execute` retorna HTTP 503.
- Não há POST /v3/payments, checkout, QR Pix, boleto, cartão nem
  processamento real de evento Asaas nesta Wave 4D-A.
- A interface avisa que o split é somente uma configuração prevista,
  não um repasse concluído.

## Gates para Wave 4D-B

1. Receber credenciais sandbox da conta operadora da plataforma.
2. Verificar o walletId de cada IES por relação oficial autorizada,
   subconta ou conta Asaas conectada; KYC/ownership e split habilitado.
3. Integrar emissão sandbox com API Asaas para Pix/boletos,
   `split` fixo de 100%, idempotência e rate limits.
4. Registrar `payment.id`, `split.id`, emissor, destinatário e
   hashes de provas, sem expor dados sensíveis ao cliente.
5. Criar webhook autenticado por token com persistência e reprocessamento
   idempotente e checagem oficial da fonte antes de confirmar liquidação.
6. Simular divergência de split, boleto vencido, pagamento parcial,
   retentativas, reembolsos, chargebacks e cancelamento.
7. Liberação posterior por workspace com aprovação operacional,
   jurídico/contratual e PSP. Nunca habilitar cobrança real só pelo merge.

**Observação:** GitHub merge, deploy Render/Vercel e migration Supabase
continuam gates distintos.
