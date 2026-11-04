# GVcollege WebAPI — Wave 3: descoberta controlada e contrato de ingestão

## Objetivo

Preparar o contrato local de descoberta e normalização sem conexão institucional real. Esta wave usa somente definições e registros sintéticos.

## Descoberta controlada

- O catálogo é estático e versionado no código.
- Os identificadores `synthetic_students_v1` e `synthetic_financial_v1` são fixtures internos da MIRA; não são nomes de views do fornecedor.
- Cada campo declara tipo, nulabilidade, classificação de dados e permissão de seleção.
- A chave de paginação é declarada no contrato sintético. Isso não prova unicidade na base de uma instituição.
- Todas as views permanecem `fixture_only=true` e `institution_approved=false`.
- A descoberta não chama a API GVcollege nem tenta enumerar views remotas.

## Contrato de ingestão em dry-run

Cada registro aceito carrega tenant_id do contexto confiável, sistema de origem, identificador da view, versão do schema, identificador do registro, chave de idempotência, observed_at e ingested_at.

- Campos opcionais ausentes permanecem `null`; não são convertidos em zero, nota positiva, presença total ou ausência de atraso.
- Campos desconhecidos geram rejeição da linha para sinalizar drift de schema.
- Tipos inválidos, chaves ausentes, chaves repetidas no lote e tentativas de fornecer tenant_id no payload são rejeitados.
- A chave de idempotência é determinística para tenant, view, versão do schema e identificador de origem.
- `observed_at` é opcional. Quando informado, exige ISO-8601 com fuso horário. Não é inferido a partir de `ingested_at`.

## Limites de segurança

- O módulo de dry-run não recebe sessão SQLAlchemy, não faz HTTP, não grava dados e não executa scoring.
- Não reutilizar `connectors.pipeline.ingest_records` nesta etapa: ele persiste registros e pode executar scoring.
- Não habilitar scheduler, worker, sincronização, descoberta remota, endpoint operacional ou conexão com instituição.
- Nenhum dado pessoal ou institucional real deve ser colocado nos fixtures.
- Não considerar uma view aprovada ou homologada com base apenas no catálogo sintético.

## Próximas gates

1. Revisar contrato e classificação de dados com a equipe.
2. Adicionar fixtures sintéticos cobrindo schema drift e regras específicas por view.
3. Integrar o dry-run à camada de prévia somente após revisão de autorização e limites de payload.
4. Em wave separada, implementar persistência idempotente com RLS/tenant isolation e trilha de auditoria.
5. Só então planejar conexão real, após contrato institucional, segredo gerenciado, egress restrito, TLS e homologação.
