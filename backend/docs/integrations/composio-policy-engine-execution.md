# Composio Wave 3 — policy engine e execução controlada

## Status

Wave 3 iniciada em `feat/composio-policy-engine-approval-gate`, baseada na `main` em `19517f9698149cea842607cb0cda0a1007568a5a`.

**Checkpoint 3.0 (fundação):** a migration `049_composio_tool_approvals`, o modelo ORM de aprovações, a FK composta tenant+conta e a flag `COMPOSIO_TOOL_EXECUTION_ENABLED=false` foram adicionados. Ainda não há endpoint de execução nem chamada ao SDK nesta entrega. A migration não foi aplicada a nenhum banco.

Esta primeira entrega define o contrato de segurança antes de habilitar qualquer chamada externa. **A execução permanece desabilitada por padrão.** A existência de uma conta OAuth ou a seleção de uma ferramenta no catálogo não concede, isoladamente, autorização para executá-la.

## Objetivo

Criar um caminho único e verificável para uma chamada Composio:

`request → tenant policy → connected account → tool schema → risk policy → approval → execution gate → Composio → audit`

Nenhum agente, endpoint ou worker pode chamar o SDK diretamente fora desse caminho.

## Fontes de autorização (todas obrigatórias)

1. **Configuração global:** `COMPOSIO_ENABLED=true`, API key e identity secret válidos.
2. **Allowlist global de toolkits:** toolkit explicitamente presente em `COMPOSIO_ALLOWED_TOOLKITS`.
3. **Policy do tenant:** `tenant_composio_toolkit_policies.is_enabled=true` e tool slug presente em `tool_slugs`.
4. **Conta conectada:** conta local ativa, do mesmo tenant e do mesmo toolkit; nunca aceitar `connected_account_id` arbitrário sem resolver a linha local.
5. **Schema atual:** tool slug deve existir no toolkit indicado. Argumentos serão validados contra o schema obtido do catálogo confiável.
6. **Identidade:** tenant e usuário são derivados do `AuthContext`; campos enviados pelo cliente não podem sobrescrever tenant, usuário Composio ou conta.
7. **Aprovação:** Wave 3 começa com aprovação humana obrigatória para todas as execuções. Nenhuma classificação de risco pode reduzir esse requisito nesta primeira versão.

Se qualquer fonte estiver ausente, inconsistente ou indisponível, negar a chamada sem tentar executar.

## Approval gate

- Solicitações são persistidas como `pending_approval` com tenant, ator, toolkit, tool, conta, fingerprint e prazo de expiração.
- A carga de argumentos não deve aparecer em logs nem na tabela append-only de auditoria. Se for necessário persistir argumentos para execução posterior, usar envelope criptografado com chave derivada de segredo do servidor; nunca armazenar payload em texto puro.
- A aprovação exige sessão humana ativa, MFA AAL2 e permissão explícita `settings.manage`. API keys de integração não aprovam solicitações.
- O aprovador não pode ser o mesmo usuário que solicitou a execução (four-eyes).
- Aprovação é transacional e de uso único. Rejeição, expiração e revogação da conta invalidam a solicitação.
- A aprovação deve mostrar toolkit, ferramenta, conta, resumo dos argumentos com redação de campos sensíveis, efeitos esperados e prazo.
- Alterar argumentos, conta, ferramenta ou versão invalida a aprovação anterior e exige nova solicitação.

## Execução

- `COMPOSIO_TOOL_EXECUTION_ENABLED=false` é o padrão obrigatório.
- O executor será único e server-side. Não expor proxy execution genérico nem aceitar URLs, headers ou auth params arbitrários do modelo/frontend.
- Usar somente tool slug e versão obtidos de catálogo confiável; execução direta exige versão explícita e testada.
- Fixar a connected account resolvida no banco e o user id HMAC do tenant.
- Desabilitar retries automáticos para operações não idempotentes. Timeout ambíguo deve resultar em estado `unknown`/reconciliação, nunca repetição cega.
- Limitar tamanho de argumentos e resposta, timeout, concorrência e taxa por tenant.
- Não devolver tokens, credenciais, headers de autorização, nem respostas completas sem filtragem.
- Uma chamada aprovada não implica autorização para outras ferramentas ou para uma nova carga de argumentos.

## Auditoria

Usar `tenant_composio_tool_audit` como trilha append-only. Registrar apenas metadados:
- tenant, ator e aprovador;
- toolkit, tool e connected account;
- execution id, fingerprint e versão;
- status, timestamps, duração e código de erro normalizado;
- approval required/status.

Não gravar argumentos completos, respostas completas, tokens, e-mails, conteúdo de documentos ou dados pessoais. O fingerprint deve ser calculado sobre JSON canônico e nunca substituir a validação do payload.

## Estados propostos

Solicitação: `pending_approval → approved | rejected | expired | cancelled`.

Execução após aprovação: `queued → executing → succeeded | failed | unknown`.

Transições devem usar lock transacional/compare-and-set. Apenas uma execução pode consumir uma aprovação. Repetir o mesmo idempotency key retorna o registro existente e não dispara outra chamada.

## Isolamento e segurança

- Todas as tabelas novas devem ter RLS ENABLE + FORCE e policy baseada em `app.tenant_id`.
- Toda consulta e mutação deve filtrar `tenant_id` do contexto autenticado.
- FK composta deve impedir associar aprovação/execução a conta de outro tenant.
- Revogação local da conta bloqueia imediatamente novas execuções e cancela aprovações pendentes vinculadas.
- Não usar claims de `user_metadata` para autorização.
- Nenhum segredo do Composio deve ser persistido na MIRA.
- Não confiar em `tenant_id`, `user_id`, `composio_user_id`, `connected_account_id`, `toolkit_slug` ou versão enviados como autoridade pelo cliente.

## Escopo de implementação

### Wave 3.0 — policy + approval (primeiro merge)
- Serviço central de decisão fail-closed.
- Persistência de solicitações/aprovações com RLS.
- API para solicitar, revisar, aprovar/rejeitar e consultar status.
- AAL2 + four-eyes + idempotência + expiração.
- Auditoria append-only sem payload sensível.
- Executor ainda bloqueado por feature flag.

### Wave 3.1 — executor controlado (merge separado)
- Adapter SDK com versão explícita e sem retries automáticos.
- Validação de schema, limites e account binding.
- Execução apenas após aprovação válida e feature flag habilitada.
- Testes com mocks e sandbox Composio; nunca credenciais ou dados reais em CI.
- Testes cross-tenant, replay, concorrência, timeout ambíguo e revogação.

### Wave 3.2 — exposição ao agente
- Entregar ao agente apenas ferramentas aprovadas e conexões ativas.
- Ferramentas de escrita/efeito externo continuam com aprovação humana.
- Nenhuma ferramenta entra no contexto do agente só por estar no catálogo.
- UI de aprovações e trilha operacional somente após contrato backend estabilizado.

## Critérios de aceite

1. Execução negada com qualquer configuração ausente.
2. Execução negada com policy ausente, toolkit desabilitado, tool não selecionada ou conta inativa.
3. Solicitação cross-tenant não pode consultar nem usar conta de outro tenant.
4. A própria pessoa solicitante não consegue aprovar sua solicitação.
5. Aprovação sem AAL2, sessão humana ou permissão é negada.
6. Replay e duas aprovações/execuções concorrentes produzem no máximo uma execução.
7. Alterar payload invalida aprovação anterior.
8. Falha/timeout remoto não provoca retry automático.
9. Auditoria não contém payload, segredo ou resposta bruta.
10. Com `COMPOSIO_TOOL_EXECUTION_ENABLED=false`, nenhuma chamada de execução chega ao SDK.
11. Migration e RLS testadas em PostgreSQL com `mira_test_runner`, sem SUPERUSER/BYPASSRLS.
12. CI do HEAD exato aprovado antes de marcar a PR como ready.

## Referência técnica

O SDK Python documenta execução direta via `composio.tools.execute(tool_slug, arguments=..., connected_account_id=..., user_id=..., version=...)`. A versão da ferramenta é obrigatória para execução direta; a implementação deve fixar uma versão obtida do catálogo e validada em sandbox. Para agentes novos, a documentação Composio recomenda considerar sessões como caminho preferencial; a escolha do adapter final será validada contra a versão pinada no projeto (`composio==0.31.0`).

Referências:
- https://docs.composio.dev/reference/api-reference/tools
- https://docs.composio.dev/docs/tools-direct/executing-tools
- https://pypi.org/project/composio/0.31.0/


## Checkpoint Wave 3.0 — policy primitives

A camada `backend/app/services/composio/policy.py` agora contém:
- resolução fail-closed da policy global, policy do tenant, conta ativa tenant-scoped e ferramenta do catálogo atual;
- validação conservadora de argumentos contra um subconjunto explícito de JSON Schema; palavras-chave desconhecidas ou schemas incompatíveis são negados;
- fingerprint SHA-256 sobre tenant, conta, toolkit, tool, schema e argumentos canônicos;
- envelope AES-256-GCM com nonce aleatório e AAD vinculada ao tenant;
- preview com redação recursiva de campos sensíveis.

Testes unitários iniciais cobrem round-trip criptográfico, vinculação ao tenant, redação e rejeição de schema incompleto/não suportado.

**Ainda não entregue:** endpoints de solicitação/revisão/cancelamento, locks e idempotência transacional da API, auditoria dos eventos de approval, testes PostgreSQL/RLS e integração completa com o schema real de cada toolkit. A função de policy não executa tools. O executor permanece ausente e a feature flag continua false.
