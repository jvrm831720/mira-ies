# Wave 4D-A — Fundamentos seguros de pagamentos (somente sandbox)

## Objetivo
A MIRA continua metadata-driven e multi-origem. Um workspace pode registrar
quantos perfis de PSP forem necessários, ligados a perfis financeiros
independentes da Wave 4C (Composio ou CSV). A configuração de fontes NÃO
significa autorização para executar transações.

## Entregue em código
- Migration 063: perfis de PSP em sandbox, propostas institucionais de pagamento e
  eventos de aprovação append-only, RLS/FORCE RLS, FKs compostas tenant+ID.
- Valor derivado da **observação mais recente** da fonte financeira do próprio
  workspace, sem campos de valor informados pelo browser. Somente BRL, obrigação
  aberta, vencida ou pagamento parcial informado; proíbe desconhecida, disputada,
  cancelada e relato de pagamento integral.
- Propostas idempotentes, exclusivas por conector+obrigação, com fingerprint da
  observação, vínculo ao aluno ativo e recomprovação antes de aprovar.
- Workflow institucional fixo `draft → awaiting_approval → approved` ou
  cancelamento. Aprovação exige outro operador com permissão `critical.manage`
  e MFA AAL2. A trilha não pode ser editada ou apagada.
- APIs de cadastro de PSPs, preparação, aprovação, consulta e histórico.
  POST /execute existe apenas para retornar 503; **nenhum PSP é invocado**.
- Todo conector começa desabilitado em modo sandbox, sem credenciais de cobrança.

## O que não foi implementado nesta etapa
- Pix, boletos, cartões, cobranças reais, checkout ou comprovantes.
- Confirmação de liquidação, consulta verificável ao PSP, assinaturas de webhook,
  tratamento de estornos/chargebacks e reconciliação bancária. Essas funções
  dependem de escolher e homologar adaptadores específicos de PSP.
- Nenhuma autorização de escrita Composio foi acrescentada; a integração
  financeira pela Composio segue limitada a leitura verificada (Wave 4C).

## Gates para Wave 4D-B
1. Definir PSPs piloto por workspace e especificação oficial dos contratos.
2. Integrar credenciais por tenant com criptografia, rotação e separação sandbox/live.
3. Implementar adaptadores sob allowlist, autenticação e regras de autorização.
4. Verificar webhook oficial com assinatura, replay/timestamp, account_id e
   evento deduplicado; consultar fonte primária para confirmar liquidação.
5. Registrar eventos append-only sem inferir quitação por webhook genérico,
   valores insuficientes ou registro de Composio 'reported_paid'.
6. Testar Pix/boletos sandbox, estornos, duplicidade, concorrência,
   timeouts, reconciliação e LGPD.
7. Habilitar por tenant só após homologação jurídica, operacional e de PSP.

## Release
Configuração `STUDENT_PAYMENT_PREPARATION_ENABLED=false` por padrão,
além das flags nativas e da conciliação financeira.
O merge não autoriza deploy, migration em Supabase nem operação financeira real.
