# Importação Inteligente da MIRA

O novo importador principal aceita CSV e Excel e oferece **mapeamento assistido, prévia sem escrita, validação por linha e confirmação explícita**.

## Fluxo

1. O operador envia um CSV ou Excel em `/importar`.
2. `POST /api/v1/import/preview` detecta colunas por aliases e similaridade.
3. O usuário revisa o de-para, confirma ou cria campos personalizados do tenant.
4. Se o mapeamento foi alterado, a prévia é executada novamente.
5. Depois de confirmação explícita, `POST /api/v1/import/apply` grava a importação.
6. A página `/importacoes` registra os lotes; `/importar/multiplos` mantém o fluxo multiarquivo.

## Arquitetura

- `backend/app/services/smart_import.py`: mapeamento fuzzy, validação determinística e upsert de alunos.
- `backend/app/services/custom_fields.py`: registry de campos, coerção de tipos e nomes canônicos.
- `backend/app/models/custom_field.py`: definições limitadas ao tenant.
- `backend/app/api/{smart_import,custom_fields}.py`: endpoints autenticados.
- `backend/alembic/versions/054_smart_import_custom_fields.py`: tabela de definições protegida por RLS e coluna JSONB indexada em alunos.
- `frontend/src/components/import/SmartImportWizard.tsx`: UI de mapeamento, revisão e confirmação.

Os campos extras ficam em `students.custom_fields` (JSONB), **sem DDL dinâmico por tenant**. O índice GIN usa a classe padrão `jsonb_ops` para permitir a checagem de existência de chave (`has_key`).

## Política de integridade

- Chave de negócio: **matrícula**. Matrículas repetidas no arquivo são rejeitadas.
- Valores numéricos não finitos, inteiros fracionários e valores acima dos limites do banco são rejeitados.
- Se algum campo mapeado é inválido, toda a linha é rejeitada, sem atualização parcial.
- Aluno novo sem nome é rejeitado; uma matrícula existente pode receber atualização parcial.
- O motor não escolhe arbitrariamente entre registros existentes ambíguos com a mesma matrícula.
- `Idempotency-Key` é escopada por tenant; o replay exige a mesma impressão digital de arquivo e mapeamento.
- `communication_opt_out=true` é auditado. Valores falsos importados **não desativam** um opt-out anterior.

## Permissões e privacidade

- Sessões humanas exigem `data.import`; chaves institucionais autenticadas são permitidas.
- A tabela `custom_field_definitions` usa `FORCE ROW LEVEL SECURITY`, com política por `app.tenant_id`.
- O campo `is_pii` identifica uma definição de dado pessoal, mas **não implementa por si só** retenção/TTL ou autorização de leitura. A exposição desses valores na ficha do aluno deve ter controle de acesso próprio.
- A prévia é dry-run e não grava alunos ou lotes.

O código está pronto na PR, mas só deve ser mesclado depois da validação da migration e dos testes no HEAD definitivo. Consulte `docs/INTEGRACAO.md`.
