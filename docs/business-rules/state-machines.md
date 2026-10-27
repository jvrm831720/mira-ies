# Máquinas de estado — inventário inicial

Este arquivo separa estados observados no código/documentação de estados normativos propostos. Transições não verificadas são pendentes; nomes de status em colunas de texto não garantem constraint no banco.

## Instituição

- **Implementado:** `Tenant.is_active` booleano.
- **Transição observada:** ativa ↔ inativa via atualização administrativa; autenticação comum rejeita instituição inativa segundo `docs/CONTROL_CENTER_SECURITY_REVIEW.md`.
- **Pendente:** efeitos sobre jobs, tokens, campanhas, integrações e dados existentes ao desativar/encerrar.

## Usuário institucional

- **Implementado:** `is_active`, `auth_version`, `failed_login_attempts`, `locked_until`.
- **Regra documentada:** mudança de papel/status incrementa `auth_version`, invalidando tokens antigos.
- **Pendente:** fluxo completo de desbloqueio, revogação de sessões individuais e concorrência.

## Convite de organização

- **Implementado no modelo:** `pending`, `expires_at`, `accepted_at`, token armazenado como hash.
- **Normativo a validar:** pendente → aceito uma única vez antes da expiração; expirado/revogado deve bloquear aceitação.
- **Não inferir:** se há todos os estados de cancelamento/reenvio e auditoria em cada transição sem revisar a rota e testes completos.

## Importação

- **Implementado:** prévia, validação, lote e atualização por matrícula dentro do tenant; lote possui `status`, `processed_rows`, `error_message`.
- **Pendente:** máquina formal para received → validated → processing → completed/partial/failed/cancelled e garantias atômicas; não assumir que todos esses estados existem.

## Risco/modelo

- **Implementado:** `ModelArtifact.lifecycle_status`, `is_active`, `scope`, `version`; campanhas têm `draft`, `active` e `archived`.
- **Implementado/testado parcialmente:** ciclo candidato/aprovação/ativação/rollback com testes de governança E2E no CI da PR #47, merge commit `e25858b4cb12dab781b19e0ed46cf193007fb520`.
- **Pendente:** política de retirada de modelo influenciado por dados cuja autorização foi revogada; auditoria de cada decisão de treinamento no pipeline.

## Intervenção

- **Estados documentados:** `planned`, `sending`, `sent`, `dry_run`, `unknown`, `failed`, `skipped`.
- **Entrega:** `queued`, `submitted`, `delivered`, `read`, `failed`, `rejected`, `bounced`, `unknown`.
- **Regra:** envio não significa entrega; entrega não significa leitura, resposta ou retenção.
- **Pendente:** validar todas as transições possíveis por provider e consistência entre status de execução e status de entrega.

## Job assíncrono

- **Documentado:** enqueue → processamento; retry com backoff; dead-letter após esgotar tentativas; consulta isolada por tenant; TTL operacional de 24h.
- **Pendente:** garantir reconciliação após crash entre chamada externa e gravação de status.

## Cobrança no Control Center

- **Implementado:** um `AdminBillingRecord` por instituição; status de pagamento `pending|paid`; status de plano `active|paused|cancelled`.
- **Decisão:** status pago é registro manual, não confirmação de gateway.
- **Conflito:** documentação conceitual antiga cita estados `draft/overdue/cancelled/refunded`; o modelo atual tem conjunto menor. O código é a evidência de comportamento atual; ampliar estados exige decisão e implementação.

## Treinamento e autorização

- **Política compartilhada:** `shared_training` / `institution_only`, com effective_at, expiração e revogação.
- **Autorização institucional:** registro separado e independente.
- **Pendente:** fila de treinamentos em andamento e procedimento operacional explícito ao mudar modalidade A→B.

## Critério geral de aceite

Para cada máquina, criar testes de transição válida, transição inválida, repetição, concorrência, estado terminal, falha e recuperação. Até lá, este documento é inventário, não especificação completa de todas as transições.
