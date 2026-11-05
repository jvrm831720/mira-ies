# Integração do Smart Import na MIRA

## Situação na branch `feat/smart-import-adaptive-schema`

O pacote foi **integrado ao código**. Não é necessário copiar arquivos manualmente.

- `/importar` usa `SmartImportWizard` como fluxo principal.
- `/importar/multiplos` preserva o importador legado para múltiplas bases.
- `backend/app/main.py` registra os routers de importação e campos personalizados.
- `Student.custom_fields` usa JSONB e está registrado no metadata do SQLAlchemy.
- A migration `054_smart_import_custom_fields` depende de `053_merge_heads`.
- Não foi feita migração em nenhum banco de produção nem deploy.

## APIs

| Método | Caminho | Comportamento |
| --- | --- | --- |
| POST | `/api/v1/import/preview` | Dry-run, mapeamento automático/manual, erros de linha |
| POST | `/api/v1/import/apply` | Escrita idempotente por matrícula |
| GET | `/api/v1/custom-fields` | Lista somente campos do tenant |
| POST | `/api/v1/custom-fields` | Cria uma definição de campo |
| PATCH | `/api/v1/custom-fields/{id}` | Atualiza ou desativa |
| DELETE | `/api/v1/custom-fields/{id}` | Exclui somente se não houver valores em alunos |

O acesso exige autenticação. Para sessões humanas, a permissão é `data.import`; chaves institucionais de API verificadas também são aceitas, preservando o contrato das integrações.

## Verificações obrigatórias antes do merge

O GitHub Actions pode estar indisponível por limite de execução. Nesse caso, **não inferir sucesso de checks ausentes**.

Com PostgreSQL descartável/local configurado (nunca produção):

```bash
cd backend
python -m pip install -r requirements.txt
PYTHONPATH=. alembic heads
PYTHONPATH=. alembic upgrade head
ruff check app
PYTHONPATH=. pytest tests/test_smart_import.py tests/test_smart_import_endpoints.py -q
PYTHONPATH=. pytest -q
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm test
npx tsc --noEmit
npm run build
```

A validação deve usar o **HEAD definitivo**, sem aproveitar resultado de commit anterior. O teste do backend depende de PostgreSQL real, conforme `backend/tests/conftest.py`, e precisa de um usuário sem superpoderes e sem `BYPASSRLS` para as validações de isolamento.

## Limites importantes

- A coluna customizada é acessada pelo motor de importação, mas sua exibição na ficha individual do aluno exige revisão de permissões para dados pessoais antes de ser adicionada.
- A importação não representa consentimento para contato. Opt-outs afirmativos são preservados e auditados.
- Sem deploy ou execução de `alembic upgrade head` no banco real até aprovação operacional.
