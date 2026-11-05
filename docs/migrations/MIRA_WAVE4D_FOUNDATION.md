# MIRA Wave 4D-A — Asaas Split Payment (sandbox, sem movimentação)

## Decisão comercial e técnica
O único dado de destino solicitado à IES é o **walletId** da conta Asaas recebedora.
Não é uma conta bancária, agência, chave Pix ou API key. Se a instituição ainda
não possui conta Asaas, será preciso criar/ativar a conta e obter o walletId,
antes da etapa de homologação.

O workspace tem **uma única carteira de destino** em
`mira_asaas_workspace_destinations`, independentemente de quantos ERPs,
contas Composio, arquivos CSV ou perfis de conciliação estiverem conectados.

Configuração de Split para **todas** as cobranças emitidas pela conta
emissora Asaas da MIRA, após homologação:

```json
{
  "split": [
    {
      "walletId": "<walletId_validado_da_IES>",
      "percentualValue": 100
    }
  ]
}
```

A regra é server-side, inalterável pela IES, operador ou aluno.
**100% é o valor líquido** (`netValue`) após as taxas do Asaas, não 100%
do valor bruto pago pelo aluno. O saldo líquido não destinado ao Split
permanece na conta emissora; com 100% para a IES, o sistema não
configura comissão ou retenção adicional na conta emissora. A cobrança
é emitida por uma conta Asaas separada da carteira de destino: a conta
emissora nunca pode ser usada como destinatário.

### Por que não usar apenas a conta bancária?
O Split oficial da Asaas exige que cada favorecido tenha uma **conta Asaas
e um walletId**. A conta bancária cadastrada para saques dentro da Asaas
não é a chave da requisição de Split.

Referências oficiais:
- https://docs.asaas.com/docs/split-de-pagamentos
- https://docs.asaas.com/docs/split-faq
- https://docs.asaas.com/docs/split-em-cobrancas-avulsas
- https://docs.asaas.com/reference/recuperar-walletid

## Onboarding da IES
Na tela `/conectores/financeiro/pagamentos`:
1. A IES cola o walletId da sua carteira Asaas (UUID).
2. Confirma ser titular e ter permissão de recebimento.
3. Salva. A carteira fica como `pending` de verificação por padrão.
4. A MIRA verifica titularidade, igualdade de CNPJ/organização e habilitação
   do Split na conta emissora por um fluxo de homologação separado.
5. Somente após verificação oficial, controles de risco e testes de PSP,
   o serviço de pagamentos reais poderá ser habilitado.

É proibido marcar uma carteira como verificada com base apenas no UUID
digitado ou em dados importados. A verificação operacional e técnica ainda
não está implementada; a API não oferece à própria IES uma ação para
promover `pending` a `verified`.

`PUT /api/v1/native-academic/finance/payments/asaas/destination` exige
MFA AAL2 e `settings.manage`; mudanças têm `expected_version`.
Alterar o walletId revoga verificação anterior e mantém um histórico
dos rascunhos com o destinatário congelado no momento da preparação.

`GET /api/v1/native-academic/finance/payments/asaas/destination`
retorna somente configuração do workspace autenticado.

`POST /api/v1/native-academic/finance/payments/asaas/split-preview`
permite simular um Split sobre a última obrigação financeira de qualquer
perfil do mesmo workspace, sem executar chamadas ao Asaas, gerar Pix ou
boleto, disparar pagamento ou confirmar quitação.

## Motor de auditoria da Wave 4D-A
- `mira_asaas_workspace_destinations`: carteira e status da homologação
  isolados por workspace, FORCE RLS.
- `mira_payment_provider_profiles`: estrutura de laboratório para
  adaptadores por fonte; **não** é configuração que a IES precisa preencher
  na nova tela de recebedor Asaas.
- `mira_student_payment_intents`: rascunhos sem execução,
  `destination_wallet_id` e saldo congelados, idempotência,
  FKs por tenant, histórico imutável.
- `mira_student_payment_evidence`: eventos sintéticos autenticados por
  HMAC MIRA de laboratório. Um `paid_reported` de sandbox não é
  comprovação do Asaas nem liquidação bancária.

Migration `063_payment_sandbox` e testes PostgreSQL da Wave 4D.
Nenhuma tabela é alterada pelo cliente em runtime. Mapeamentos de ERPs,
fontes e workflows seguem orientados por metadados da Wave 4C.

## Webhooks e PSP homologado: etapas posteriores
O Asaas usa seu próprio token de autenticação de Webhook enviado no header
`asaas-access-token`; ele **não** equivale à assinatura HMAC de laboratório.
O contrato real deve usar token próprio do Webhook, não a API key do Asaas,
e validar o evento contra a conta emitente, a cobrança e o destinatário.
Consultar a API oficial quando necessário para confirmar estado.

Eventos a conciliar separadamente:
- `PAYMENT_CREATED` — cobrança emitida;
- `PAYMENT_CONFIRMED` — pagamento confirmado, saldo ainda indisponível;
- `PAYMENT_RECEIVED` — valor disponível para recebimento;
- `PAYMENT_SPLIT_DONE` — Split liquidado individualmente;
- `PAYMENT_SPLIT_CANCELLED`, `PAYMENT_SPLIT_DIVERGENCE_BLOCK` e
  `PAYMENT_SPLIT_DIVERGENCE_BLOCK_FINISHED` — exceções relevantes;
- estorno/refund/chargeback — precisam reverter o status e
  manter a trilha de auditoria.

O Split ocorre no momento da liquidação pela Asaas, não em agendamento
próprio da MIRA. A partir de 28/09/2026, Asaas também oferece
mecanismo **opcional** de aprovação de Split via Webhook de validação,
que deve ser analisado na homologação.

A emissão futura deverá usar o campo `split` em
`POST /v3/payments` (cobrança avulsa), informando cliente, valor,
modalidade e vencimento de forma verificada, nunca valores/recipient
arbitrários do navegador.

Referências oficiais:
- https://docs.asaas.com/docs/webhook-para-cobrancas
- https://docs.asaas.com/docs/webhooks-faq
- https://docs.asaas.com/changelog/valida%C3%A7%C3%A3o-de-saque-via-webhook-para-liquida%C3%A7%C3%A3o-de-splits-de-pagamento

## Controles de ambiente
- `NATIVE_ACADEMIC_ENABLED=false`
- `NATIVE_ACADEMIC_SERVICES_ENABLED=false`
- `STUDENT_FINANCE_RECONCILIATION_ENABLED=false`
- `STUDENT_PAYMENTS_SANDBOX_ENABLED=false`
- `STUDENT_PAYMENTS_SANDBOX_WEBHOOKS_ENABLED=false`
- `STUDENT_PAYMENTS_SANDBOX_HMAC_SECRET=`
- `STUDENT_PAYMENTS_ASAAS_ISSUER_WALLET_ID=`

Sem executores de pagamento via Composio. Composio permanece como fonte
de registros financeiros autorizados, enquanto o **Asaas será o gateway de
pagamento nativo**. A receita líquida pertence à carteira da IES.
Todos os testes usam dados sintéticos. Nenhum merge desta Wave
autoriza deploy, migration do Supabase ou cobranças em produção.
