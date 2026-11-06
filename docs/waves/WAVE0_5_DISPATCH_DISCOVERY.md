# Discovery técnico — Wave 0.5: Dispatch & Campaign Operations

**Status:** preparação de produto; **nenhuma execução, disparo ou cobrança autorizada por este documento.**

## Objetivo

Consolidar a operação de campanhas, audiências, modelos, canais, provedores, agendamentos, aprovações, execuções e histórico, seguindo a densidade visual e a configuração progressiva da Attio. A MIRA já possui motor de Dispatch e contratos de permanência: **não construir outro executor**.

## Contratos realmente presentes no backend

### Dispatch (prefixo `/api/v1/dispatch`)

- `GET /sources`: fontes e capacidades, incluindo nativas/Composio sob políticas já existentes.
- `GET /campaigns` e `GET /campaigns/{campaign_id}`: índice e detalhe operacional.
- `POST /campaigns`: criação explícita, fora de qualquer leitura do Data Hub.
- `POST /campaigns/from-retention-proposal`: materialização de proposta sob validação e autorização.
- `POST /campaigns/{campaign_id}/targets`: staging de público, não envia mensagens.
- `POST /campaigns/{campaign_id}/approve`: aprovação real.
- `POST /campaigns/{campaign_id}/schedule`: agendamento real, não implica entrega.
- `POST /campaigns/{campaign_id}/{action}`: controle operacional, requer regras.
- `GET /campaigns/{campaign_id}/replies`, `GET /metrics`: observabilidade e resposta.

### Propostas de permanência

`retention_campaign_proposal_workflow.py` já implementa edição, envio para revisão, solicitação de mudanças, ateste de autorização, aprovação e trilha auditável. `retention_campaign_scheduling.py` implementa agendamento e remoção de agendamento. **O Workflow Canvas 0.3 apenas representa estados, não substitui esses contratos.**

### Canais e integrações

- `dispatch_providers.py`: listagem, configuração, verificação, ativação e desativação de contas de provedor.
- `dispatch_native_webhooks.py`: eventos nativos verificados de Resend e Twilio.
- `dispatch_integrations.py`: obrigações, contatos externos e resultados financeiros conciliados com evidência.
- `dispatch_composio.py`: ingestão de contexto de ferramentas Composio aprovadas; execução remota não deve ser generalizada.
- `dispatchApi` no frontend já tipa campanhas, provedores, templates, importações Composio e resultados.

## Telas propostas

1. **Campaign Index:** tabela de campanhas, estado, audiência, canais, dono e progresso com filtros RBAC; reusar Object Index.
2. **Campaign Detail:** Record Experience de campanha com abas Resumo, Público, Mensagens, Aprovações, Agendamento, Execução e Resultados.
3. **Audience & Segments:** origem e elegibilidade verificadas, bloqueios de consentimento, deduplicação, teto de volume e amostra sem exposição de dados sensíveis.
4. **Templates:** biblioteca com estado draft/approved/retired, versão, contexto/canal e aprovação, sem edição silenciosa de template aprovado.
5. **Providers:** credenciais nunca expostas, status de homologação, limites, saúde e histórico verificados pelo servidor.
6. **Approval Center:** responsabilidades, ateste, MFA/AAL2, RBAC e cadeia de auditoria; não confundir edição com permissão para enviar.
7. **Schedule:** fuso, janela, idempotência, confirmação humana, parâmetros reais do backend.
8. **Execution Monitor:** progresso e estados nativos do motor, filas, falhas, tentativas, resultados de provedores, backoff e DLQ quando realmente disponíveis.
9. **Run Detail / Events:** logs e webhooks sanitizados, identidade de execução, transições verificáveis, correlação por IDs persistidos.
10. **Outcome & Finance:** métricas de entrega e conciliação financeira somente de provedores verificados; separar pagamento de evento de comunicação.

## Entidades e limites

`Campaign Definition` não equivale a `Approved Campaign` nem a `Execution`; uma aprovação não prova envio, um agendamento não prova job executado, um webhook recebido não prova conciliação de pagamento. Exibir evidência, status e timestamps de cada transição, sem equivalências inventadas.

Não duplicar processamento de lotes, webhooks, políticas anti-spam, mecanismos de consentimento, idempotência ou validação de integração. O frontend apenas orquestra contratos autorizados.

## Autorização e isolamento obrigatórios

- `tenant_id` e autorização efetiva no backend para todas as ações, com testes de dois tenants e usuário não superuser / sem BYPASSRLS.
- `campaigns.view`, `campaigns.edit`, `campaigns.approve`, `campaigns.execute` efetivos por cargo personalizado e contexto; UI apenas reflete o que o servidor impõe.
- Aprovação de ações sensíveis separada de execução; exigência de MFA e revisão humana onde o contrato define.
- Proibição de disparos e cobranças reais em CI/QA, mocks e ambientes de desenvolvimento com dry-run comprovável.
- Segredos, tokens de provedores, contatos e respostas brutas nunca expostos em logs de UI ou ferramentas.
- Repetição/retry de operações com efeitos reais exige confirmação, idempotência e autorização.
- Ferramentas Composio: allowlist/policy/escopo, sem execução arbitrária.

## Sequência recomendada

- **0.5.1 — Índice + detalhe** a partir de `dispatchApi`, sem novo endpoint.
- **0.5.2 — Público e modelos** com elegibilidade, consentimento e versões.
- **0.5.3 — Aprovação e agenda** com estados e confirmação reais.
- **0.5.4 — Monitor de execução** e histórico detalhado.
- **0.5.5 — Provedores e webhooks** com diagnóstico sem exposição de segredos.
- **0.5.6 — Gates**: testes frontend/backend, PostgreSQL/RLS, acessibilidade, QA autenticado, proteção contra execução acidental e verificação do release.

## Dependências abertas

É necessária a confirmação do workspace Render para inspecionar `mira-api-testes`; validar provedores homologados, configuração de filas e política real de publicação. A sequência de produto pode continuar em branch isolada enquanto o gate operacional estiver pendente.
