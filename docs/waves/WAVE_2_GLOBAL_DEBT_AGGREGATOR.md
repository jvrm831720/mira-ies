# Wave 2 — agregador de pendências de múltiplos workspaces

**Dependência obrigatória:** PR #209 / Wave 1. A branch desta Wave foi criada
a partir de `feat/portal-global-identity-wave1`, ainda não integrada à `main`.
Nunca publicar a Wave 2 sem migrar 073 antes de 074.

## Garantias

1. Um CPF digitado não vincula automaticamente aluno e dívidas. Só a identidade
   comprovada por fornecedor independente da Wave 1 habilita leitura e consentimento.
2. Uma instituição, autenticada com MFA AAL2 e `settings.manage`, pode
   preparar uma concessão para um único `student_id` do próprio workspace
   e um `account_id` global fornecido pela pessoa, mediante referência de
   evidência institucional. Não há busca pública por CPF.
3. Cada concessão começa `pending`. A pessoa autenticada e verificada deve
   aceitá-la explicitamente; antes disso, o agregador não retorna valores.
4. Cada snapshot vem de observações financeiras que correspondem **simultaneamente**
   a `tenant_id` do ator e `student_id` indicado, sob RLS.
   Não existe SELECT multi-tenant no endpoint global.
5. O usuário pode revogar consentimento e a instituição pode revogar a concessão.
   Revogação impede leituras futuras; dados de snapshot continuam no banco
   até retenção/expurgo regulado (a implementar).
6. O endpoint global devolve até 500 registros autorizados, com `workspace_id`,
   saldo observado e data de observação. Não efetua cobrança, renegociação ou Pix.
   O valor é **snapshot histórico**, nunca saldo atual garantido.

## Endpoints
- Instituição: `POST /api/v1/native-academic/global-debt/grants`,
  `POST /api/v1/native-academic/global-debt/grants/{id}/revoke`.
- Aluno: `GET /api/v1/global-portal/debts/consents`,
  `POST /api/v1/global-portal/debts/consents/{id}/accept`,
  `POST /api/v1/global-portal/debts/consents/{id}/revoke`,
  `GET /api/v1/global-portal/debts`.
- Página `/portal/pendencias` (somente visualização com consentimento).
- Feature flag `GLOBAL_STUDENT_DEBT_AGGREGATION_ENABLED=false` por padrão.

## Pendências para homologação antes da ativação
- Homologar Wave 1, fornecedor de prova de titularidade, recuperação e retificação.
- Implementar jornada institucional de concessão com comprovação da associação
  entre pessoa verificada e matrícula; UUID e referência documental não são,
  isoladamente, prova suficiente de titularidade.
- Exibir identidade clara do credor e escopo da autorização **antes** do aceite,
  não apenas uma referência opaca; sem isso, consentimento não é informado.
- Implementar atualização/reconciliação de snapshots com dados financeiros atuais,
  exclusão/retenção e política de contestação.
- Garantir que duplicidades entre fontes sejam reconciliadas antes de calcular
  total consolidado. Nesta Wave, nenhum total agregado é calculado.
- Verificar RLS com papéis distintos em PostgreSQL real e testes E2E
  multi-tenant (tentativa de IDOR, revogação concorrente e CPF incorreto).
- Não habilitar feature flag antes dos gates acima.

## Observação
A migração 074 cria tabelas aditivas e FORCE RLS. O rollback é bloqueado
quando houver concessões existentes. A PR é intencionalmente draft.
