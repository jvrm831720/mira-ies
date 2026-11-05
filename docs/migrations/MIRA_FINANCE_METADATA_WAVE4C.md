# Wave 4C — MIRA Metadata-Driven Financial Reconciliation

## Objetivo
A MIRA adapta-se ao workspace com **metadados versionados**, sem `if tenant == X`,
sem forks por cliente e sem DDL gerada a partir de dados de usuários.

Um workspace pode manter **várias origens simultâneas**:
- duas ou mais contas Composio (mesmo toolkit ou toolkits distintos), vinculadas à
  identidade Composio e às políticas do próprio tenant;
- quantos perfis de importação CSV forem necessários, cada um com suas próprias
  colunas e nomes;
- perfis múltiplos sobre a mesma conta Composio, quando precisarem de mapeamentos
  ou processos diferentes.

A Wave 4C é especializada em registros financeiros de estudantes. O registro
genérico de integrações MIRA continua disponível a outros tipos de workspace; a
reconciliação financeira acadêmica só abre em IES com RBAC institucional.

## Quatro camadas de adaptação — desenho seguro

1. **Dados / schema lógico:** `mira_finance_source_profiles` armazena
   `field_map`, `status_map`, `student_lookup` e `mapping_version` em JSONB.
   A tabela canônica e o contrato da API permanecem estáveis. Já existe em
   `custom_field_definitions` e `students.custom_fields` a abordagem de campos
   personalizados sem migrações por cliente. Novas entidades só exigem migration
   de produto, nunca DDL disparada pelo workspace em tempo de execução.
2. **Processos:** `review_workflow` declarativo define estados, rótulos e
   transições da revisão humana por perfil (máximo de oito etapas). O executor
   interpreta esses metadados sem executar Python/Javascript arbitrário.
   Revisão **não pode** definir o estado de pagamento ou liquidar dívidas.
3. **Entrada e interface:** editor de perfis com mapeamento coluna→campo,
   sugestões heurísticas com confirmação humana, preview dry-run, CSV UTF-8
   limitado, reuso do executor Composio com allowlist/schema/titularidade.
   Importações são acionadas explicitamente, não automáticas.
4. **Isolamento:** seis tabelas com PostgreSQL ENABLE/FORCE RLS,
   `app.tenant_id` transaction-local, FKs compostas tenant+id para perfil,
   aluno e lote. Endpoints exigem membership e MFA AAL2, RBAC por operação.
   Importações e revisões críticas são auditadas. O motor não cria um
   Frappe-site separado por tenant: usa isolamento lógico PostgreSQL/RLS,
   enquanto a futura infraestrutura Frappe multi-site permanece um
   projeto independente em homologação.

## Motor de conciliação e limites de verdade

- O workspace configura explicitamente o vínculo `student_reference`:
  UUID de estudante MIRA ou relação externa revisada por humano
  (escopo por perfil). Jamais fuzzy matching por nome/CPF/valor.
- Cada registro contém origem, mapping version, estado declarado, total,
  valor informado como pago, vencimento, referência externa,
  opcional `source_updated_at` e chave de correlação declarada.
- Status desconhecido permanece `unknown`. Estado `PAGO` configurado como
  `reported_paid` significa **pagamento informado pela fonte**, não
  liquidação verificada. `settlement_confirmed` permanece `false`.
- Uma chave de correlação é **opcional e explícita**; somente dados do mesmo
  aluno e mesma chave podem ser apresentados lado a lado.
- Conflitos de status, total ou valor pago são destacados no painel para
  revisão. Consistência entre duas fontes também **não** comprova liquidação.
- Observações e batches são append-only com trigger no PostgreSQL;
  ingestões são transacionais, com `Idempotency-Key`, fingerprint de
  conteúdo, histórico do mapping e bloqueio de revisões mais antigas
  de fonte com timestamps verificáveis.
- O estado institucional do caso de revisão é configurável por metadados,
  rastreado em `mira_finance_review_events` e não altera snapshots
  nem saldo financeiro.
- Os snapshots de cada origem usam `source=profile_<UUID>`, garantindo
  que um ERP não sobrescreva outro na tabela
  `mira_student_financial_references`.

## Endpoints
Prefixo: `/api/v1/native-academic/finance/reconciliation`

- `GET/POST /profiles`, `PUT /profiles/{id}` — configuração versionada e
  ativação explícita, RBAC `settings.manage` nas mutações.
- `POST /profiles/{id}/student-links` — vínculo humano do identificador
  externo, sem troca silenciosa.
- `POST /suggest-headers`, `POST /profiles/{id}/preview` — sugestão
  não autoritativa e simulação sem persistência.
- `POST /profiles/{id}/import`, `POST /profiles/{id}/import-csv` —
  lotes manuais idempotentes (100 registros; CSV 512 KB UTF-8).
- `POST /profiles/{id}/sync` — Composio com ferramenta read-only
  permitida pela allowlist global, toolkit, conta e policy do tenant,
  verificando o schema atual da ferramenta e identidade remota.
- `GET /profiles/{id}/batches`, `GET /profiles/{id}/observations` —
  auditoria / proveniência institucional.
- `GET /discrepancies` — comparação de até 1.000 observações recentes.
- `POST /profiles/{id}/review-cases`,
  `POST /review-cases/{id}/transition`,
  `GET /review-cases/{id}/history` — workflow de revisão
  (RBAC `critical.manage`, versionamento, auditoria).

## Flags e homologação
Padrão **desabilitado**:
- `NATIVE_ACADEMIC_ENABLED=false`
- `NATIVE_ACADEMIC_SERVICES_ENABLED=false`
- `STUDENT_FINANCE_RECONCILIATION_ENABLED=false`
- `STUDENT_FINANCE_COMPOSIO_ENABLED=false`

Composio exige também suas flags/segredos, `COMPOSIO_ALLOWED_TOOLKITS`,
`STUDENT_FINANCE_COMPOSIO_READ_TOOLS`, OAuth do tenant, toolkit policy e
verificação remota. Não existem tool slugs imaginários. Omie segue o contrato
de integração nativa/customizada vigente.

A migration **062_finance_reconcile** é validada em PostgreSQL descartável
por usuário sem superusuário e sem BYPASSRLS. O merge **não** implica rodar
migration em Supabase, liberar deploy, ativar flags nem acessar contas reais.

## Pontos deliberadamente fora desta entrega
- Confirmar liquidação bancária, assinatura/webhook de PSP, estornos
  e conciliação contra extrato/comprovante homologados.
- Criar cobranças, gerar boletos, Pix, transferências ou movimentar dinheiro.
- Server Scripts Python injetáveis em produção compartilhada; qualquer
  automação configurável futura requer DSL sandboxed com quotas, auditoria
  e permissões, não `exec` de código fornecido por cliente.
- Execução agendada de sincronizações: necessita scheduler/worker com
  idempotência, quotas e circuit-breakers por origem.
- Múltiplas moedas e geração de entidades SQL arbitrárias em runtime.
- Vincular dívidas ao módulo comercial de cobrança sem política de
  propósito, consentimento, legalidade e segregação apropriada.
- Homologar Frappe/ERPNext/Education: PRs correspondentes continuam
  independentes da API financeira MIRA.

## Checklist antes de produção
1. Confirmar Head único Alembic, migration 062 e FORCE RLS nas seis tabelas.
2. PostgreSQL com dois tenants, dois perfis, mesmo ID externo e vínculo humano.
3. Configuração e importação Composio reais apenas em sandbox e com dados sintéticos.
4. Simular revogação OAuth, retries, importação duplicada, registros fora de ordem,
   dados ausentes, estados desconhecidos e correlação divergente.
5. Validar UI: perfis múltiplos, roles, versionamento concorrente, importação
   preview/apply, erros e visualização honesta no Portal do Aluno.
6. Aprovação operacional por fonte e tenant, após política de LGPD e minimização.
