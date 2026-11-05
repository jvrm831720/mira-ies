# MIRA Dispatch — alinhamento com a arquitetura do workspace

## Decisão de produto

**Dispatch não é um produto de cobrança separado.** É a camada de execução
compartilhada de comunicações da MIRA, utilizada pelos módulos de permanência,
acadêmico, atendimento e cobrança. O tamanho da audiência não altera a
infraestrutura: individual, segmentada e em escala usam as mesmas regras
de autorização, outbox, isolamento, idempotência e monitoramento.

```text
Fontes do workspace
  ├─ Dados já normalizados / importados na MIRA
  ├─ Conectores nativos (p.ex. JACAD, SophiA, Sponte, Omie)
  └─ Composio (contas e ferramentas permitidas por tenant)
                    │
                    ▼
Contexto normalizado + decisões e regras do módulo de origem
                    │
            Aprovação preexistente
                    │
                    ▼
         Dispatch outbox PostgreSQL
     (individual, segmentado, alto volume)
                    │
       Elegibilidade + autorização + origem
                    │
                    ▼
       Workers + provedores autorizados
                    │
                    ▼
       Eventos, resultado e conciliação
```

## Componentes usados — não duplicar

- **Catálogo e autenticação Composio**: `TenantComposioAccount`,
  `TenantComposioToolkitPolicy`, allowlist global e gateway existente.
  Nenhuma credencial OAuth é copiada para o disparador.
- **Conectores nativos**: suas tabelas de conexão verificadas são consultadas
  pelo mesmo tenant, sem criar credenciais/SDKs paralelos.
- **Importação MIRA**: `UploadBatch`, dados estudantis e bases já normalizadas.
  Fonte manual pode apontar para um lote de upload daquele tenant.
- **Permanência**: `RetentionCampaignProposal`, snapshot imutável,
  revisão, atestado, aprovação e modelos aprovados da MIRA. O dispatch materializa
  o resultado para execução sem reabrir revisão ou criar uma segunda campanha
  independente.
- **Autorização individual**: `dispatch_authorizations` com `source`,
  `evidence_ref`, propósito e expiração; a conexão do workspace, sozinha,
  nunca autoriza contato com uma pessoa.

## Contratos implementados nesta PR

`GET /api/v1/dispatch/sources`: retorna as origens visíveis na organização:
`kind`, `reference`, `name`, `connected`, `can_bind`, `tools`,
`automatic_ingestion`, `note`. A lista não contém credenciais.

`POST /api/v1/dispatch/campaigns`: agora aceita:
- `source_kind`: `manual`, `native` ou `composio`
- `source_ref`: ID do lote existente, slug nativo ou connected account ID;
- `source_tool_slug`: exigido para o vínculo de origem Composio, e precisa
  estar selecionado na política vigente do tenant.

A origem é resolvida exclusivamente no servidor. Não se aceita `tenant_id`
enviado pelo cliente como autoridade. A origem é revalidada ao aprovar,
agendar, iniciar e imediatamente antes de cada envio. Revogação de conta ou
policy bloqueia uma entrega pendente. **Esses campos registram origem e
permissões, não significam que o dispatch leu dados de uma ferramenta remota.**

`POST /api/v1/dispatch/campaigns/from-retention-proposal` recebe:
```json
{"proposal_id": "<id da proposta aprovada>", "template_id": "<id do modelo aprovado>"}
```
- Reutiliza a aprovação, identidade do aprovador e atestado da proposta.
- Valida hash do snapshot, versão de audiência e canal recomendado.
- Exige modelo aprovado para permanência e evidência individual vigente.
- Gera uma única execução no outbox com índice único
  `(tenant_id, origin_proposal_id)`, idempotente em retries.
- Revalida o vínculo e o hash na hora do disparo.
- Não cria nova revisão/aprovação de campanha. Iniciar/agendar continuam
  operações explícitas com permissão `campaigns.execute`.
- Não envia nenhuma mensagem na chamada HTTP.

`dispatch_campaigns` é agora um registro de **execução operacional**
quando `source_kind='retention_proposal'`, não fonte de verdade sobre
revisão institucional. O restante do sistema conserva campanhas manuais
com quatro-olhos e intervenções individuais com modelo pré-aprovado.

## O que Composio faz (e o que não faz) neste estágio

Esta PR **usa as contas e políticas reais do Composio** para selecionar e
revalidar o vínculo de contexto. Ela **não executa ferramentas Composio**,
não lê resultados delas, não sincroniza automaticamente valores financeiros
e não transforma um `tool_slug` selecionado em permissão de contato.
A política `COMPOSIO_TOOL_EXECUTION_ENABLED` permanece sob o controle
separado do Composio. A execução externa de tools requer implementação
do executor autorizado com approval gate e auditoria.

Da mesma forma, um conector nativo é uma origem de dados autorizada quando
seu estado foi verificado; a normalização/ingestão precisa ser feita por
suas próprias rotinas, não pelo worker de disparos.

## Regras por finalidade

| Finalidade | Autoridade do processo | Destinatário | Evidência antes de enviar |
|---|---|---|---|
| Permanência | Proposta MIRA aprovada ou campanha autorizada | Aluno ou contato identificado | Consentimento/base de contato vigente por canal e finalidade |
| Acadêmico | Regra de comunicação e modelo aprovado | Aluno | Autorização por finalidade e canal |
| Atendimento | Atividade/intervenção e modelo aprovado | Aluno ou contato | Autorização + supressões |
| Cobrança | Base de obrigação + campanha aprovada | Devedor/contato | Obrigação aberta e atualizada, autorização e canal permitido |

Cobrança por WhatsApp permanece bloqueada. Não usar ausência de dado de
pagamento como evidência de dívida em aberto, nem status `configured`
como teste bem-sucedido de um conector.

## Cenários de teste adicionados

1. Conta Composio de outro tenant não pode ser usada na campanha atual.
2. Ferramenta fora da política do workspace é negada.
3. Conta Composio revogada bloqueia a origem.
4. Conector nativo só é vínculo elegível após teste de conexão.
5. Lote manual de outro tenant não é origem válida.
6. Materialização de proposta aprovada preserva aprovador e snapshot.
7. Retry com mesma proposta é idempotente.
8. Proposta revogada ou alterada deixa de autorizar execução.
9. O disparador não chama SDK Composio implicitamente.
10. As proteções anteriores de volume, finanças, supressão e envios
    desativados permanecem intactas.

## Gate de merge e operação

O código foi publicado na PR #150. **Não foi realizado merge ou deploy.**
A migration 055 foi editada na branch porque ainda não foi homologada em
produção; nenhuma outra migration foi alterada nesta integração.

Antes do merge: executar Alembic, Ruff, Pytest em PostgreSQL com papel sem
BYPASSRLS, lint/TypeScript/build do frontend e simulações concorrentes no
HEAD final. GitHub Actions e Vercel não devem ser interpretados como aprovados
quando um limite de execução impede os jobs de rodar.

Nenhum flag de execução real, de Composio ou de provedor deve ser ativado
somente por causa deste alinhamento.
