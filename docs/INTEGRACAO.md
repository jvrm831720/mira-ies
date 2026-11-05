# Guia de integração (patch no repositório mira-ies)

O pacote espelha os caminhos do repositório. Copie cada arquivo para o mesmo
caminho e aplique os 4 ajustes abaixo.

## 1. `backend/app/main.py` — registrar os routers

```python
from app.api import (
    ...,  # imports existentes
    smart_import, custom_fields,
)
# junto dos demais include_router:
app.include_router(smart_import.router, prefix="/api/v1", tags=["Importacao Inteligente"])
app.include_router(custom_fields.router, prefix="/api/v1", tags=["Campos Customizados"])
```

## 2. `backend/app/models/student.py` — coluna JSONB

```python
# junto das demais colunas de Student:
custom_fields: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
```

(A migration `054` já cria a coluna com `server_default='{}'`; em development o
`create_all` usa o model, por isso o model precisa do campo.)

## 3. Alembic — conferir a cabeça

```bash
cd backend
alembic heads        # se não for 053_merge_heads, ajuste down_revision na 054
alembic upgrade head
```

## 4. Expor `custom_fields` na ficha/lista do aluno (opcional, recomendado)

No endpoint de detalhe do aluno (e na lista), inclua no dict de resposta:

```python
"custom_fields": s.custom_fields or {},
```

## Testes

```bash
cd backend
pytest tests/test_smart_import.py -q
```

## Endpoints novos

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/v1/import/preview` | Dry-run: mapeamento fuzzy + validação linha a linha |
| POST | `/api/v1/import/apply` | Upsert idempotente (header `Idempotency-Key`) |
| GET | `/api/v1/custom-fields` | Lista campos customizados do tenant |
| POST | `/api/v1/custom-fields` | Cria campo (papel operator+) |
| PATCH | `/api/v1/custom-fields/{id}` | Edita label/opções/flags/desativa |
| DELETE | `/api/v1/custom-fields/{id}` | Exclui se sem uso (senão 409) |