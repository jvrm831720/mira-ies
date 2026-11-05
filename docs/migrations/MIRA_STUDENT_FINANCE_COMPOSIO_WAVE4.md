# MIRA Education — Wave 4B: Composio Financial Read Bridge

## Arquitetura
A MIRA reutiliza a conexão OAuth e o executor Composio existentes na `main`.
A instituição escolhe uma conta financeira conectada e uma ferramenta **de leitura**
que esteja na allowlist global, na policy do tenant e na allowlist específica
`STUDENT_FINANCE_COMPOSIO_READ_TOOLS`. O servidor valida o usuário MFA AAL2,
o workspace IES, a titularidade remota da conta e o schema atual da ferramenta.

O resultado é limitado a 100 itens / 256 KB, com campos financeiros tipados
e vínculo pelo UUID **MIRA** do aluno, sem correspondência por nome ou CPF.
A persistência usa `mira_student_financial_references` (Wave 3), com origem
separada por conta/ferramenta e `mira_student_financial_sync_runs` (migration 060)
para histórico e idempotência. O Portal mostra snapshots, **não reconciliação**.

## Requisitos de ativação em homologação
- `NATIVE_ACADEMIC_ENABLED=true`
- `STUDENT_PORTAL_ENABLED=true`
- `NATIVE_ACADEMIC_SERVICES_ENABLED=true`
- `COMPOSIO_ENABLED=true`, API key, identity secret e OAuth de tenant
- `COMPOSIO_ALLOWED_TOOLKITS` explicitamente preenchido
- `STUDENT_FINANCE_COMPOSIO_ENABLED=true`
- `STUDENT_FINANCE_COMPOSIO_READ_TOOLS` explicitamente preenchido
- Policy Composio da conta permitindo apenas ferramentas de leitura

Essas flags seguem desabilitadas por padrão. `DISPATCH_COMPOSIO_INGESTION_ENABLED`
e `COMPOSIO_TOOL_EXECUTION_ENABLED` não são necessários nessa rota: uma nova
política financeira independente protege a leitura. **Não há ferramenta de
escrita, cobrança ou pagamento nesta Wave 4B.**

Omie permanece integração nativa/customizada, porque não há toolkit Composio
confirmado no catálogo interno; não se deve inventar um slug.

## Gates
1. Passar Alembic 060, RLS/FORCE RLS e teste com usuário sem BYPASSRLS.
2. Validar contas reais, schema de ferramentas e conteúdo sintético em sandbox.
3. Revisar idempotência, cota, revogação OAuth e separação de dois tenants.
4. Só então ligar a leitura para uma instituição piloto e homologar mapeamentos.
5. Webhooks e conciliação assinada de origem, boletos e Pix ficam em outra wave.
