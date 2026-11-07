# Portal MIRA único — Wave 1: identidade global

## Objetivo e isolamento
Criar identidade de pessoa física **separada** das identidades de membros dos workspaces.
Uma identidade global permite cadastro e autenticação por CPF e código enviado por e-mail,
mas **não** implica permissão para revelar saldos, credores, vínculos institucionais,
negociações ou acordos. Isso depende de comprovação independente de titularidade e
das Waves 2–4. O portal acadêmico anterior `/portal` permanece intacto enquanto
a migração B2C é homologada. Prévia da nova experiência: `/portal/acesso`.

## Contratos

- `POST /api/v1/global-portal/auth/register/request` — CPF, e-mail e WhatsApp;
  resposta neutra (202), sem revelar CPF cadastrado.
- `POST /api/v1/global-portal/auth/login/request` — CPF; código só enviado ao
  endereço cadastrado e validado, resposta neutra (202).
- `POST /api/v1/global-portal/auth/verify` — CPF e OTP numérico de 6 dígitos,
  TTL de 5 minutos, máximo 5 tentativas por código; emissão de sessão separada.
- `GET /api/v1/global-portal/auth/me` — apenas contatos da própria pessoa
  autenticada e estado de identidade, **nenhuma dívida**.
- `POST /api/v1/global-portal/auth/logout` — revoga sessão no servidor.
- `POST /api/v1/global-portal/auth/identity/attest` — contrato interno assinado
  de callback de um **prestador de comprovação de identidade independente**,
  desabilitado até homologação; não é verificação via CPF/e-mail.

A mutação via aplicação requer o cabeçalho `X-Mira-Global-Portal-Action: 1`.
O proxy Next.js encaminha exclusivamente o cookie `mira_global_student_session`
para caminhos `/global-portal`, e o cookie antigo só para `/student-portal`.
Sessões usam token aleatório, hash HMAC no banco, `HttpOnly`, `SameSite=Lax`,
`Secure` fora de desenvolvimento e expiração em 8h. Códigos são hash HMAC e
nunca persistidos em texto; CPF é representado por digest HMAC com chave privada.
Nenhum CPF, código ou token é retornado em logs de aplicação ou payloads de sucesso.

## Controles de segurança
1. Feature flag `GLOBAL_STUDENT_PORTAL_ENABLED=false` por padrão.
2. `GLOBAL_STUDENT_IDENTITY_SECRET` mínimo 32 caracteres, secreto e estável
   ao longo da vida dos registros. Rotacionar somente com plano de reindexação
   controlada de CPF; perder a chave impede a identificação de contas existentes.
3. Resend (`RESEND_API_KEY` e `EMAIL_FROM`) para OTP real. Sem credenciais o
   backend falha fechado (503), nunca retorna código em resposta.
4. Redis disponível e privado (`REDIS_URL`) para limites distribuídos por
   origem de rede e digest de CPF; indisponibilidade resulta em 503.
5. Tabelas globais usam FORCE RLS e política de transação
   `app.global_identity_service=enabled`, concedida somente no fluxo de
   autenticação global. Instalações com usuários DB distintos precisam
   provisionar explicitamente privilégios ao papel de serviço de identidade;
   em produção **recomenda-se fortemente papel DB separado** e auditoria de
   permissões. Nunca conceder SELECT ao usuário anônimo, aos perfis
   institucionais ou ao navegador.
6. Sem join de entidades globais a `students`, cobranças, `tenants`
   ou `dispatch_obligations`. Consentimento, origem e autorização por credor
   serão tratados somente em Wave 2.
7. Não liberar qualquer detalhe financeiro após confirmação de e-mail.
   `identity_verified=false` permanece até comprovação independente.

## Contrato de comprovação externa (não operacional sem fornecedor)

O callback exige `GLOBAL_STUDENT_IDENTITY_PROOF_ENABLED=true` e
`GLOBAL_STUDENT_IDENTITY_PROOF_SECRET` de 32+ caracteres, além do feature gate
principal. Payload obrigatório: `account_id` (UUID), `cpf_digest`,
`provider`, `verified_at` (ISO8601 com fuso) e `nonce` aleatório.
A assinatura HTTP `X-Mira-Identity-Signature` é
`v1=` + HMAC-SHA256(hex, `GLOBAL_STUDENT_IDENTITY_PROOF_SECRET`,
`account_id|cpf_digest|provider|verified_at(UTC ISO8601)|nonce`).
Aceita apenas timestamps dentro de 5 min, conta ativa com e-mail verificado,
CPF digest correspondente e nonce nunca utilizado. O recebimento é
registrado no ledger `mira_global_student_attestations`, sem payload de documento.
Este contrato **não é uma integração de KYC pronta**. Antes da ativação,
implementar o fluxo do fornecedor com evidência de correspondência entre
titular e CPF, segurança de chave, callback autenticado e testes E2E.
Não habilitar o sinalizador de prova sem essa integração.

## Modelagem
- `mira_global_student_accounts`: `cpf_digest` único, e-mail,
  WhatsApp e marcos separados de e-mail verificado e identidade verificada.
- `mira_global_student_challenges`: OTP de uso único, TTL, tentativas.
- `mira_global_student_sessions`: sessão revogável com hash do token.
- `mira_global_student_attestations`: ledger de nonces e fornecedor.
- Migração aditiva `073_global_student_identity`, sem transformar nem
  copiar registros existentes; rollback bloqueado se houver contas.

## Gates para produção B2C
- [ ] Integrar e homologar provedor independente de titularidade do CPF;
      construir solicitação de prova e fluxo de recuperação de conta.
- [ ] Homologar política de retenção/exclusão de CPF digest, e-mail, WhatsApp,
      consentimento/transparência e solicitações LGPD.
- [ ] Homologar proteção de cadastro indevido / sequestro de CPF por conta
      não titular; hoje o registro de e-mail **não** dá acesso a dívidas, mas
      recuperação de identidade e retificação de cadastro exigem fluxo próprio.
- [ ] Testar limites distribuídos sob proxy real, incluindo agrupamento de
      clientes no mesmo IP e resistência a ataques de enumeração por tempo.
- [ ] Validar privilégio do papel PostgreSQL, migrations e isolamento RLS
      com papel não privilegiado em ambiente de homologação.
- [ ] Homologar Resend, Redis, cookies no domínio oficial, recovery, acessibilidade
      mobile e trilha de auditoria sem PII.
- [ ] Somente após esses itens: ativar `GLOBAL_STUDENT_PORTAL_ENABLED`.
- [ ] Wave 2: agregação autorizada de pendências multi-tenant com prova forte
      e consentimento/política do credor; **não** disponível nesta Wave 1.

## Verificação de testes
`python -m pytest backend/tests/test_global_student_identity.py` a partir da
raiz, com `PYTHONPATH=backend`; `node --test src/app/portal/global-identity.test.mjs`
a partir de `frontend/`. A aprovação real da CI deve ser conferida no PR.
