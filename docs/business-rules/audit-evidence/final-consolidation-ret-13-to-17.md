# Consolidação de auditoria — RET-13 a RET-17 e critério de retomada do produto

**Data:** 2026-10-27  
**Base funcional examinada:** `main`; documentos de auditoria mantidos somente em `docs/business-rules-audit-2026-10`.  
**Objetivo:** encerrar esta rodada documental com uma decisão operacional sobre o que pode avançar no produto e o que continua bloqueando operações reais.

## Escopo e limites

Esta consolidação sintetiza as evidências registradas nas fases anteriores. Os achados abaixo derivam de inspeção estática. **Não houve reprodução dinâmica de RET-13 a RET-17 nesta rodada.** Não foram executados testes, enviados mensagens, acionados provedores, acessados bancos de staging/produção ou realizados deploys. Nenhuma funcionalidade, migration ou configuração foi alterada.

“Confirmado por código” significa que a sequência/condição descrita foi observada na implementação. Não significa que uma falha em ambiente real foi reproduzida, explorada ou que seu impacto tenha sido medido.

## Matriz consolidada

| ID | Evidência estática | Impacto potencial | Prioridade operacional | Validação pendente |
|---|---|---|---|---|
| RET-13 — TTL do job versus data agendada | O registro do job recebe TTL padrão de 86.400 s enquanto o ID pode ficar no conjunto de agendados até uma data futura. | Se a data ultrapassar a validade do registro, o hash pode expirar antes da execução; a promoção pode remover o ID sem recuperar o job. | **Alta para jobs agendados**; não bloqueia desenvolvimento de UI. | Teste com relógio/Redis isolado e TTL menor que o prazo agendado; confirmar política de retenção. |
| RET-14 — enqueue não atômico | Persistência do hash e inclusão em fila/conjunto ocorrem em comandos separados. | Uma interrupção no intervalo pode deixar registro sem gatilho de execução, caso não exista reconciliador alternativo. | **Média-alta para confiabilidade operacional**; não bloqueia UI sem execução real. | Injetar falha entre operações em ambiente isolado; verificar reconciliador e recuperação. |
| RET-15 — promoção de ID sem registro | A promoção remove IDs vencidos; quando o hash não existe, ainda pode adicionar o ID à fila pronta. | Trabalho sem registro persistido é consumido sem processamento útil e perde a oportunidade de recuperação por esse caminho. | **Alta para confiabilidade de fila**, especialmente em conjunto com RET-13. | Teste com ID vencido sem hash; definir comportamento explícito de descarte, recuperação e métricas. |
| RET-16 — correlação de callback sem filtro de provedor | A busca filtra tenant e ID externo, mas não provedor; prioriza ID externo e escolhe o registro mais recente. | Em colisão entre provedores no mesmo tenant, evento pode atualizar log errado; para `opted_out`, pode afetar preferência de aluno/canal não relacionado. | **Bloqueador para confiar em callbacks de opt-out em operação real** até teste e correção/mitigação validados. | Dois logs sintéticos com mesmo ID externo e provedores diferentes; aliases; ambos IDs no payload; verificar que só o destino correto muda. |
| RET-17 — aceite do provedor antes do commit local | O log é reservado como `sending`; a chamada ao agente ocorre antes da persistência final de status/ID externo. Não foi identificado reconciliador nos caminhos examinados. | Queda após aceite remoto e antes do commit pode deixar o estado local ambíguo; repetição pode ficar parada em `sending/unknown` sem reconciliação visível. | **Bloqueador para declarar confiável o envio autônomo em operação real** até recuperação/idempotência serem demonstradas. | Agente falso, sem rede, com aceite sintético e interrupção antes do commit; reiniciar com a mesma chave e observar reconciliação. |

## Decisão: o que bloqueia e o que pode avançar

### Pode avançar agora

- Front-end e UX de **Visão geral**, **Alunos**, **Central de trabalho**, **Intervenções** e **Resultados**.
- Melhorias de legibilidade dos indicadores, explicação dos scores, priorização e feedbacks de estado.
- Importação guiada com preview, validação, mapeamento, deduplicação, histórico e mensagens de erro.
- Protótipo e demonstração comercial usando dados sintéticos ou previamente controlados, com limites de capacidade explicitados.
- Componentes de interface para estados pendentes, falhas, consentimento, ausência de dados e resultado inconclusivo.

Essas atividades não devem chamar provedores reais nem transformar estados ambíguos em “sucesso”. A UI precisa representar fielmente os estados do backend e não deve mascarar ausência de score, consentimento ou confirmação de entrega.

### Bloqueado até validação

- **Envio autônomo real** de intervenções de retenção apresentado como confiável, enquanto RET-17 não tiver estratégia de reconciliação/recuperação demonstrada.
- **Aplicação operacional de callbacks de opt-out** sem validação da correlação do destinatário (RET-16). Até lá, não confiar em eventos ambíguos para alterar preferências reais.
- Declarações de que a fila garante recuperação de jobs, execução exatamente uma vez ou confiabilidade completa enquanto RET-13 a RET-15 não forem testados e tratados.
- Qualquer alegação de segurança multi-tenant universal ou conformidade regulatória derivada apenas desta amostra.

Esses bloqueios não impedem criar telas, fluxos de demonstração ou contratos de interface. Impedem tratar comportamentos ainda não validados como garantia operacional.

## Critério de encerramento desta rodada

A rodada documental pode ser considerada **consolidada**, sem significar que os riscos foram corrigidos ou que o produto está liberado para produção, quando:

1. RET-13 a RET-17 estiverem registrados com evidência, impacto, classificação estática/dinâmica e teste pendente.
2. O status de teste estiver explícito como “não executado” até existir evidência real de ambiente isolado.
3. Os bloqueadores para operação real estiverem separados das tarefas de front-end.
4. O PR #48 continuar aberto, sem merge, até revisão e autorização explícita do responsável.
5. A próxima etapa do produto começar em uma branch de trabalho própria, sem alterações funcionais em `main` até autorização expressa.

## Próxima sequência recomendada

1. Revisar esta matriz e os documentos de evidência RET-13 a RET-17.
2. Encerrar a rodada documental como **“consolidada com validações dinâmicas pendentes”**, não como “auditoria técnica completa”.
3. Retomar o front-end em uma branch separada, priorizando painel executivo e operação, com fixtures/dados de demonstração e sem envio real.
4. Planejar os testes isolados de RET-13 a RET-17 como trabalho técnico separado, antes de liberar os caminhos operacionais afetados.

**Status final desta consolidação:** documental; nenhuma correção funcional aplicada; nenhuma validação dinâmica executada; nenhuma autorização de produção concedida.
