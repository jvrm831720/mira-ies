# Fase 7 — correlação de callbacks e persistência do envio

**Data da revisão:** 2026-10-27  
**Base de código:** `main`; documentação registrada somente em `docs/business-rules-audit-2026-10`.  
**Método:** inspeção estática de `backend/app/services/delivery_webhooks.py`, `backend/app/api/delivery_webhooks.py`, `backend/app/agents/orchestrator.py`, `backend/app/services/provider_guard.py`, `backend/app/models/intervention.py` e amostra dos testes de segurança/consentimento. Nenhum teste foi executado nesta fase; nenhum provedor, banco de produção/staging ou serviço externo foi acionado. Nenhuma alteração funcional foi feita.

## RET-16 — Callback pode corresponder ao log de outro provedor

**Evidência direta no código**

Em `apply_delivery_event()`, a consulta começa com `InterventionLog.tenant_id == tenant_id`. Se `event.external_id` estiver presente, acrescenta `InterventionLog.external_id == event.external_id`; se não estiver, tenta `event.idempotency_key`. A consulta não filtra por `InterventionLog.provider` e prioriza `external_id` mesmo quando também há uma chave de idempotência. Depois ordena por `created_at DESC` e limita o resultado a um registro.

O endpoint `receive_delivery_webhook()` aceita nomes como `evolution`, `resend`, `twilio`, `whatsapp`, `email` e `sms`. No envio, `orchestrator.py` grava o provedor efetivo retornado pelo agente; para WhatsApp, esse valor pode ser `waha` ou `evolution`. Portanto, os nomes de rota e os nomes persistidos não são necessariamente idênticos, e uma correção futura não deve presumir comparação literal sem uma regra de canonicalização.

**Cenário de risco**

Se dois logs do mesmo tenant tiverem o mesmo `external_id` e forem de provedores distintos, o callback pode selecionar o log mais recente, ainda que o provedor do evento não corresponda ao provedor gravado nesse log. O risco é especialmente relevante para eventos `opted_out`, pois o código aplica a alteração de preferência usando o aluno e o canal do log encontrado.

**Classificação:** risco confirmado por análise estática; colisão e efeito incorreto não foram reproduzidos dinamicamente. Não afirmar exploração ocorrida.

**Cobertura consultada:** `test_agent_delivery_safety.py` testa normalização de payloads de Evolution, Resend e Twilio e distingue eventos `delivered/read`; `test_consent_governance.py` cobre opt-out por webhook e auditoria de preferências. Na amostra lida, não foi encontrado teste que crie dois logs do mesmo tenant com `external_id` igual e provedores diferentes e verifique qual log é atualizado. Essa conclusão limita-se aos arquivos consultados.

**Teste de regressão recomendado:** criar dois logs sintéticos no mesmo tenant, com o mesmo `external_id` e provedores diferentes; enviar evento normalizado para cada provedor e comprovar que somente o log correto é atualizado. Incluir alias de provedor (`whatsapp` versus `waha/evolution`) e caso em que payload traz simultaneamente `external_id` e `idempotency_key`. Para opt-out, verificar que nenhum aluno/canal não relacionado é alterado.

## RET-17 — Janela entre aceite do provedor e persistência local sem reconciliação identificada

**Evidência direta no código**

1. `_reserve_send_log()` cria e faz commit de `InterventionLog` com `status="sending"` antes da chamada externa.
2. `_send_with_guard()` chama `agent.send(..., idempotency_key=...)`. Após receber um resultado, atualiza o estado da chave Redis para `sent`, `unknown` ou libera a chave em falha definitiva.
3. Só depois de `_send_with_guard()` retornar, `RetentionOrchestrator.run()` grava no log o status final, o provedor, o `external_id` e `delivery_status`, e executa `session.commit()`.
4. Se o processo terminar abruptamente após o provedor aceitar a mensagem, mas antes de o resultado ser retornado/persistido, o registro SQL pode permanecer em `sending`; a chave Redis pode permanecer como `sending` até expirar. Não foi identificado, nos arquivos examinados, um reconciliador que consulte o provedor ou resolva automaticamente esse estado.
5. Em uma execução posterior que reutilize a mesma chave, o orquestrador encontra o log existente; se seu status for `sending` ou `unknown`, conta o resultado como incerto e interrompe a tentativa, sem reconciliação visível nesse caminho.

**Limites e controles existentes**

- A reserva no banco antes do envio evita que uma repetição simples faça uma nova chamada quando encontra o log em estado `sending`.
- A chave de idempotência é passada ao agente/provedor e a proteção Redis usa `SET NX`; a efetividade da idempotência remota depende do suporte e da semântica de cada provedor, não comprovados por esta leitura.
- O teste `test_ambiguous_provider_result_does_not_fallback_to_email` cobre um timeout ambíguo retornado pelo agente, não a morte abrupta do processo depois do aceite remoto e antes do commit SQL.

**Classificação:** janela de consistência confirmada por análise estática; não foi reproduzida falha de processo nem aceite remoto. A ausência de reconciliador está limitada aos caminhos e arquivos examinados.

**Teste de regressão recomendado:** usar agente falso, sem rede, que registre localmente uma aceitação sintética e force uma exceção/interrupção antes da persistência SQL. Confirmar o estado do log e da chave Redis; depois reiniciar o fluxo com a mesma chave e verificar se há recuperação/reconciliação ou se o caso permanece indefinidamente incerto. Não usar provedores reais. Se houver um mecanismo de reconciliação fora dos arquivos consultados, localizá-lo e incluí-lo na evidência antes de fechar o achado.

## Resumo de status

| Achado | Evidência | Dinâmica | Próxima validação |
|---|---|---|---|
| RET-16 — correlação por `external_id` sem provedor | Confirmado por leitura do código | Não executada | Colisão sintética entre provedores e aliases |
| RET-17 — aceite remoto antes do commit local | Janela entre operações confirmada no fluxo | Não executada | Falha controlada com agente falso, sem rede |

**Conclusão:** a consulta de callback não usa o provedor como parte da correlação observada; a semântica dos aliases precisa ser explicitada antes de definir a regra de correção. O envio também tem uma janela entre o efeito externo e a persistência local; os controles de idempotência mitigam algumas repetições, mas não demonstram reconciliação do estado ambíguo. Esta fase é documental e estática: não implementa correções nem declara cenários reproduzidos.
