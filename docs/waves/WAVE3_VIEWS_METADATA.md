# MIRA — Wave 3 · Views e metadados

## Objetivo

Views são metadados de consulta e apresentação; não copiam, alteram ou
desnormalizam registros de alunos, cobrança, campanhas ou outros objetos.

A Wave 3 se apoia no Object Index server-side da Wave 2 e preserva os
campos customizados já mantidos em \`custom_field_definitions\` (Wave 054).
Não cria um segundo mecanismo de campos nem promete filtragem de
propriedades que as APIs de cada objeto ainda não suportam.

## Contratos e permissões

- **personal**: visível somente ao proprietário e ao usuário autenticado
  no mesmo tenant; outras pessoas não podem consultar por ID.
- **workspace**: visível para membros autenticados daquele tenant **que
  tenham permissão de leitura do objeto**; views com filtros, ordenação,
  colunas ou rótulos sensíveis também exigem
  \`students.sensitive.view\`.
- **Compartilhar**: somente o proprietário com
  \`permissions.manage\` ou perfil administrativo/coordenador embutido.
  Outra pessoa pode duplicar para sua área pessoal, mas não alterar a view
  original. Compartilhar nunca concede acesso a registros.
- **Favorito**: por usuário + tenant; favoritos não duplicam views.
- **Rótulos**: \`property_labels\` (schema V1) altera texto da view,
  sem mudar chave canônica, payload de registros, valor, categoria de
  sensibilidade, filtros remotos ou permissões.
- **Catálogo**: \`GET /api/v1/object-views/metadata?object_key=...\` 
  lista propriedades nativas autorizadas, operadores e capacidade real de
  filtragem/ordenação. O registry de campos customizados permanece no
  fluxo próprio; não surgem filtros remotos fictícios.

## Revisões

Há duas versões independentes:

1. \`config_version\`: schema da configuração, preservado como **1**. O
   parser adiciona defaults explícitos quando uma view antiga V1 omite
   propriedades novas, mas não reescreve o JSON original ao listar.
   Versões incompatíveis retornam \`schema_status=unsupported\`,
   \`config=null\`; o frontend desabilita aplicar/alterar até resolver.
2. \`revision\`: incremento monotônico da edição; começa em 1. Um
   \`expected_revision\` obsoleto produz **409 VIEW_REVISION_CONFLICT**,
   inclusive em compartilhamento, restauração e exclusão.

O histórico em \`mira_object_view_revisions\` é append-only por política
RLS: revisões originais não podem ser atualizadas/apagadas diretamente.
Restaurar uma revisão anterior cria uma **nova** revisão com conteúdo
validado contra o catálogo, sem retroceder o contador.

## Rotas

| Método | Rota | Operação |
| --- | --- | --- |
| GET | \`/api/v1/object-views?object_key=students\` | pessoais + compartilhadas autorizadas |
| POST | \`/api/v1/object-views\` | criar pessoal |
| GET | \`/api/v1/object-views/metadata?object_key=students\` | catálogo permitido |
| GET | \`/api/v1/object-views/{id}\` | ler autorizada |
| PUT | \`/api/v1/object-views/{id}\` | editar com revisão esperada |
| DELETE | \`/api/v1/object-views/{id}?expected_revision=...\` | excluir como proprietário |
| POST | \`/api/v1/object-views/{id}/share\` | alternar personal/workspace com revisão |
| POST | \`/api/v1/object-views/{id}/duplicate\` | duplicar configuração como pessoal |
| PUT/DELETE | \`/api/v1/object-views/{id}/favorite\` | favoritar/desfavoritar |
| GET | \`/api/v1/object-views/{id}/revisions\` | histórico do proprietário |
| POST | \`/api/v1/object-views/{id}/restore\` | restaurar snapshot em nova revisão |

## Migração aditiva

\`backend/alembic/versions/070_object_view_collaboration.py\` (revises
\`069_onboarding_logo\`):

- \`mira_object_views\`: adiciona \`scope='personal'\`,
  \`revision=1\`, \`is_sensitive=false\` e índice por tenant/objeto.
- Backfill de flags conservadoras para views antigas com campos de risco.
- Evolui a constraint de tipos, incluindo \`collections\` (já presente
  na API do Index).
- Cria \`mira_object_view_revisions\` e
  \`mira_object_view_favorites\` com FKs tenant-aware,
  RLS e grants fechados a Data API pública.
- Preserva views antigas em schema 1, criando snapshot inicial de cada
  view com seus dados reais, sem copiar objetos de negócio.
- Rollback recusa destruir compartilhamentos, favoritos ou revisões
  criadas após migração. Exige exportação consciente antes.

Nenhum DDL executado diretamente no banco de produção nesta PR.

## QA / gates

Executar backend com os bancos efêmeros já provisionados pelo CI:

\`\`\`bash
cd backend
ruff check app/api/object_views.py app/models/object_view.py tests/test_object_views_wave3.py
pytest -q tests/test_object_views_wave3.py tests/test_object_index_wave01.py \
  tests/test_object_index_wave2_integration.py
\`\`\`

Frontend:

\`\`\`bash
cd frontend
npm ci
npm run lint
npm test
npx tsc --noEmit
npm run build
\`\`\`

QA autenticado:
- Coordenador IES cria, renomeia, edita rótulos de propriedades, salva
  nova revisão, compartilha e restaura sem duplicar aluno.
- Segundo usuário da mesma IES vê apenas views compartilhadas,
  favorita, duplica para pessoal e **não** consegue editar original.
- Outro tenant não vê nem por consulta direta ao banco, mesmo com
  UUID conhecido.
- Perfil sem \`students.sensitive.view\` não vê views nem metadados
  contendo score/risco; tentativa de criação/consulta recebe 403/404.
- Dois editores simultâneos (ou abas) devem receber 409 na revisão velha.
- Legacy V1 continua aplicável após conversão explícita de defaults;
  config futura V2 não deve ser aplicada silenciosamente.
- Desktop/móvel: menu, diálogo, foco, acessibilidade e QR de auditoria
  de revisões. Nenhuma mudança em login, onboarding, pagamentos ou Portal.

**Gates de release:** CI de frontend e backend, migrations no banco
descartável, revisão de RLS não-superuser, QA autenticado e checagem dos
builds externos. Sem evidência de testes, não declarar homologado.
