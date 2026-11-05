# Integração Composio → MIRA → Disparos (leitura real, segura e auditável)

## O que foi integrado

O backend agora possui execução real de ferramentas Composio **somente de leitura**
para importar dados normalizados. As credenciais OAuth permanecem sob custódia
do Composio. A MIRA usa o `composio_user_id` da organização já provisionado
em `tenant_composio_sessions`, verifica a conta remota e o toolkit,
confere `tenant_composio_accounts` e `tenant_composio_toolkit_policies`
e cria uma sessão Composio **com apenas o toolkit, a ferramenta e a conta
conectada selecionados**. Não oferece um proxy genérico do SDK ou do LLM.

Documentação oficial:
- https://docs.composio.dev/docs/configuring-sessions
- https://docs.composio.dev/docs/how-composio-works
- https://docs.composio.dev/reference/sdk-reference/python/session

Fluxo operacional:

1. A organização conecta um sistema na tela de integrações Composio.
2. Um usuário com `data.import` e MFA/AAL2 escolhe conta, ferramenta de
   leitura, argumentos, caminho para os registros e mapeamento dos campos.
3. `POST /api/v1/dispatch/composio/imports` verifica **todas** as políticas
   e o schema atual da ferramenta. A leitura usa `session.execute()` do
   Composio, com `result_type='completed'` para sucesso.
4. Até 100 registros e 256 KB são normalizados, com ID estável do sistema
   remoto e referência inequívoca ao destinatário MIRA.
5. Os campos mapeados são criptografados em
   `dispatch_source_observations` (PostgreSQL, RLS ENABLE+FORCE). A importação
   recebe um registro idempotente em `dispatch_source_import_runs`.
6. No rascunho de uma campanha cuja origem é essa conta e ferramenta,
   `POST /api/v1/dispatch/composio/campaigns/{id}/stage` tenta associar os
   registros importados à fila **somente se** houver base de contato individual
   vigente e destinatário validado na MIRA; cobrança exige, além disso, uma
   obrigação aberta que já exista no livro financeiro autorizado.
7. Aprovação, agendamento e disparo continuam submetidos ao motor
   de dispatch, aos controles por finalidade/canal e às respectivas flags.

O motor **não cria consentimento**, não interpreta planilha ou CRM como prova
de dívida e não envia SMS, WhatsApp ou e-mail em chamadas de importação.

## Configuração (backend Render / ambiente de homologação)

```env
COMPOSIO_ENABLED=true
COMPOSIO_API_KEY=<segredo de projeto>
COMPOSIO_IDENTITY_SECRET=<segredo estável de identidade>
COMPOSIO_ALLOWED_TOOLKITS=<slugs dos toolkits previamente aprovados>

# A execução genérica de tools pode continuar DESATIVADA.
COMPOSIO_TOOL_EXECUTION_ENABLED=false

# Flag distinta e restrita para importar dados via ferramentas somente leitura.
DISPATCH_COMPOSIO_INGESTION_ENABLED=false
DISPATCH_COMPOSIO_INGESTION_READ_TOOLS=<SOMENTE_TOOLS_DE_LEITURA_REVISADAS>
DISPATCH_COMPOSIO_DATA_KEY=<chave Fernet criptográfica>
```

Por padrão a funcionalidade está **OFF** e nenhuma chave foi configurada
nesta PR. Somente habilitar em homologação depois de verificar a conta e
os schemas de ferramentas. Não coloque chaves reais no GitHub.

Exige explicitamente:
- allowlist global de toolkits Composio;
- toolkit e tool habilitados no workspace;
- conta real ativa e pertencente à identidade Composio do tenant;
- ferramenta de leitura sem verbos mutadores no identificador;
- allowlist separada `DISPATCH_COMPOSIO_INGESTION_READ_TOOLS`;
- usuário humano com permissão `data.import` e AAL2;
- limites de volume (100 registros/256 KB por chamada; 60/h por tenant);
- idempotência de requests;
- chave `DISPATCH_COMPOSIO_DATA_KEY` (Fernet);
- auditoria sem payload de contatos nem respostas brutas dos provedores.

O nome da ferramenta **não basta** para provar ausência de efeitos colaterais;
o administrador deve verificar documentação e schema do toolkit específico
antes de incluí-la na allowlist.

## Endpoints

| Método | Endpoint | Função |
|---|---|---|
| GET | `/api/v1/dispatch/sources` | Contas e ferramentas autorizadas do workspace |
| POST | `/api/v1/dispatch/composio/imports` | Executa ferramenta real de leitura e importa |
| GET | `/api/v1/dispatch/composio/imports` | Estado, contagens, erro genérico e histórico |
| GET | `/api/v1/dispatch/composio/observations` | Agregados sem PII dos dados importados |
| POST | `/api/v1/dispatch/composio/campaigns/{id}/stage` | Vincula somente destinatários elegíveis |
| GET | `/api/v1/dispatch/campaigns` | Execuções compartilhadas |

### Exemplo de payload

**Atenção:** os nomes abaixo são ilustrativos. Cada toolkit tem um schema
próprio; escolha a tool do catálogo vivo que realmente disponibilize os
registros esperados.

```json
{
  "connected_account_id": "ca_exemplo",
  "tool_slug": "CRM_LIST_CONTACTS",
  "arguments": {"limit": 100},
  "rows_path": "items",
  "record_id_field": "id",
  "subject_ref_field": "external_ref",
  "subject_type": "external",
  "record_type": "contact",
  "field_map": {
    "email": "email",
    "name": "name"
  }
}
```

Enviar `Idempotency-Key` com uma chave aleatória de 16–120 caracteres.
O frontend gera essa chave e oferece a tela
`/disparos/importacoes` para selecionar conta, ferramenta,
mapear campos e executar/acompanhar as leituras.

Para fontes financeiras, o mapeamento pode incluir
`"obligation_ref": "external_id"`. Isso **não** transforma a
observação em uma obrigação verificada: a MIRA exige que a obrigação
existente no ledger autorizado esteja atualizada no momento da campanha.

## Segurança de dados

- A normalização importa **somente os campos explicitamente mapeados**.
- Respostas brutas Composio não são armazenadas nem devolvidas por APIs.
- O conteúdo persistido é criptografado com Fernet e vinculado a
  `tenant_id`, `connected_account_id`, `tool_slug` e `source_record_id`.
- `payload_hash` e `source_version` permitem sincronização incremental
  sem duplicar registros; resultados inalterados renovam a observação.
- Uma observação só pode ser usada para montar audiência se for recente,
  e sempre depende de autorização independente por pessoa e canal.
- Revogação da conexão/policy entre leitura e persistência é revalidada.
- Composio não substitui validação nativa de webhooks de provedores de envio.
- Os dados financeiros não são tomados como verdade somente por virem de
  uma integração, e não há reconciliação automática do pagamento nesta wave.

## Limites antes da produção

Esta implementação estabelece **execução real sob autorização + importação
estruturada + vínculo à fila**. Ainda não oferece sincronização periódica
sem intervenção humana, atualização automática do ledger financeiro, cobertura
total dos schemas de todas as ferramentas Composio ou homologação com contas
reais de clientes. Essas etapas requerem seleção dos toolkits concretos,
contratos de dados verificáveis, política do cliente e testes sandbox.

**Nunca afirmar que contas reais foram sincronizadas a partir de um teste
com o SDK simulado.** O teste isolado comprova os contratos locais; o
cenário remoto exige uma conexão Composio de homologação.

Nenhum deploy, alteração de configuração operacional ou disparo real é parte
desta PR.
