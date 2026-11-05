# Importação Inteligente + Schema Adaptativo

A inteligência que o Frappe entrega com Data Import + Metadata, replicada na stack da MIRA
**sem DDL em runtime**: o schema se adapta por tenant via registry + JSONB.

## Fluxo

```
[ Planilha CSV/XLSX ]
        │  POST /api/v1/import/preview        (dry-run, zero escrita)
        ▼
[ Mapeamento fuzzy + validação linha a linha ]
        │  usuário confirma/ajusta o de-para na UI
        │  colunas novas → "criar campo customizado" inline
        ▼
[ POST /api/v1/import/apply + Idempotency-Key ]   (upsert, idempotente)
        ▼
[ students: INSERT de novos · UPDATE de existentes · custom_fields (JSONB) ]
```

## Módulos

| Arquivo | Papel |
|---|---|
| `backend/app/services/smart_import.py` | Fuzzy matching de cabeçalhos, validação em memória, upsert por chave |
| `backend/app/services/custom_fields.py` | Registry por tenant + coerção/validação de valores por tipo |
| `backend/app/models/custom_field.py` | `CustomFieldDefinition` (tenant × target × name único) |
| `backend/app/api/smart_import.py` | `POST /import/preview` e `POST /import/apply` |
| `backend/app/api/custom_fields.py` | CRUD de campos customizados + catálogo |
| `backend/alembic/versions/054_...` | Tabela + `students.custom_fields` (GIN) |

## Decisões

- **JSONB + registry, nunca ALTER TABLE em runtime.** Multi-tenant em tabelas
  compartilhadas torna colunas por tenant impraticáveis; o JSONB com GIN
  (`jsonb_path_ops`) sustenta filtros e o check de uso (`has_key`).
- **Aliases canônicos vêm de `app.services.ingestion.COLUMN_ALIASES`** — mesma
  fonte do upload legado, sem divergência de comportamento.
- **Confiança do mapeamento:** alias exato = 100% · ≥ 0,85 auto-aceito ·
  0,55–0,85 vai para "sugestões" (confirmação humana) · abaixo = não mapeado.
- **Upsert idempotente** por `Idempotency-Key` → `batch_id` determinístico
  (uuid5), mesmo padrão do `confirm-multiple`. Chave de negócio: `matricula`.
- **Opt-out:** se a linha traz `communication_opt_out=true`, o timestamp de
  descadastro é registrado; a trilha de consentimento segue em
  `consent_audit_events` (mesmo serviço das preferências).

## Tipos de campo customizado

`text` · `integer` · `number` (formato BR, ex.: `1.234,56`) · `boolean`
(`sim/não`) · `date` (`AAAA-MM-DD` ou `DD/MM/AAAA`) · `enum` (opções fixas).

Campos marcados `is_pii=true` herdam minimização e TTL dos logs de intervenção.

## Segurança

- Todas as rotas exigem `X-API-Key` e são isoladas por `tenant_id`
  (`get_current_tenant`); escrita exige papel `operator`+ (`require_min_role`).
- Exclusão de campo customizado é bloqueada (409) se houver alunos com valor;
  a saída é desativação (`PATCH active=false`).

## Frontend

`SmartImportWizard` (passo de mapeamento com confiança, criação inline de
campo customizado) + `smart-import-api.ts`. Para adotar no `ImportWizard`
atual, substitua o passo de envio pelo preview → mapping → apply.