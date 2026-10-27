# Critérios de aceite e cenários de teste

Esta lista é a base mínima de regressão. “Passou no CI” comprova somente o teste automatizado executado naquele commit; não comprova staging, provedor real ou produção.

## Segurança e isolamento (P0)

- [ ] Tenant A não lê/atualiza/exporta aluno, lote, campanha, intervenção, job, evento ou artefato pertencente ao tenant B.
- [ ] IDs/slug/tenant_id manipulados em URL, corpo, query e arquivo não alteram o tenant resolvido no servidor.
- [ ] Token de cliente/API key não acessa Control Center; token interno não substitui identidade institucional.
- [ ] Usuário inativo, tenant inativo, sessão expirada/revogada e MFA incompleto são rejeitados.
- [ ] Todas as rotas de escrita são testadas por papel autorizado e não autorizado.
- [ ] Erros de recurso alheio não revelam se o recurso existe.

## Importação (P1/P0 para identidade)

- [ ] Prévia não cria lote nem altera aluno/preferência.
- [ ] Matrícula como texto preserva zeros à esquerda.
- [ ] Matrícula ausente/nome ausente rejeitam linha sem afetar linhas independentes seguras.
- [ ] Duplicatas no arquivo são reportadas de forma determinística.
- [ ] Duas colunas não alimentam silenciosamente o mesmo campo.
- [ ] Valor vazio não apaga dado existente; opt-out explícito é tratado separadamente.
- [ ] Conflito de identidade não é importado automaticamente.
- [ ] Arquivos complementares são bloqueados até haver contrato de relação e prévia consolidada.
- [ ] Falha parcial/repetição não duplica ou deixa lote em estado enganoso.

## Predição e modelos

- [ ] Score sempre dentro de 0–100 e nível conforme a faixa documentada (0–39 baixo; 40–69 médio; 70–100 crítico), se essas faixas forem a regra vigente.
- [ ] Ausência de feature não é rotulada como risco baixo sem regra aprovada.
- [ ] Score expõe modelo/versão/escopo; versão ausente falha de forma segura.
- [ ] Explicação não apresenta score como probabilidade calibrada sem evidência de calibração.
- [ ] Alvo `evasion_90d_v1` só rotula ativo negativo quando observação ocorre no dia 90 ou depois; transferência é concorrente sem rótulo.
- [ ] Divisão temporal evita vazamento por matrícula e respeita maturação do alvo.
- [ ] Modalidade B nunca contribui ao treino global; treino local exige autorização própria.
- [ ] Mudança A→B bloqueia novo uso global e marca runs pendentes para revisão; tratamento de modelos existentes depende de decisão formal.
- [ ] Ativação/rollback preserva auditoria e versão exata usada.

## Intervenções e canais

- [ ] Risco baixo não dispara campanha automatizada conforme regra documentada.
- [ ] Opt-out global prevalece sobre preferências por canal/finalidade.
- [ ] Anti-spam por canal (default 48h) e limite semanal (default 3) são aplicados por tenant/aluno.
- [ ] Timeout/erro ambíguo vira `unknown`, não dispara fallback imediato que possa duplicar mensagem.
- [ ] Chave de idempotência repetida retorna mesma execução/job dentro do escopo do tenant.
- [ ] Webhook inválido é rejeitado; replay de evento é deduplicado; callback de tenant A não altera tenant B.
- [ ] `sent`, `delivered`, `read`, resposta e retenção não são confundidos.
- [ ] Dry-run não chama provedores reais; configuração de canal não é mostrada como conectividade verificada.

## Control Center e faturamento

- [ ] Login sem MFA não emite sessão administrativa.
- [ ] Código expirado/reutilizado ou acima do limite de tentativas é rejeitado.
- [ ] Redis/e-mail indisponível falha fechado no MFA.
- [ ] RBAC negado resulta em 403 e deixa evento quando aplicável.
- [ ] Atualização de papel/status invalida sessão antiga.
- [ ] Marcação de pagamento manual é distinguida de confirmação por gateway.
- [ ] Não existe processamento de cartão nem confirmação por retorno de navegador.
- [ ] Valores anteriores/novos auditados sem segredos.

## Operação/observabilidade

- [ ] Retry tem limite/backoff; esgotamento produz dead-letter consultável apenas pelo tenant.
- [ ] Correlation ID permite ligar requisição, job, intervenção e webhook.
- [ ] Estado de sucesso só é emitido após persistência/ack confirmado.
- [ ] Restore/rollback é exercitado em staging antes de release com migração.
- [ ] Testes usam banco isolado e nunca credenciais de produção.

## Execução real nesta auditoria

Não executei a suíte completa localmente nem acessei staging. A execução GitHub Actions #328 (PR #47, antes do merge) foi observada com jobs `lint-and-test` e `frontend-check` aprovados. Isso valida os checks daquele commit, não toda esta matriz.



## Novos critérios de regressão — isolamento e governança (2026-10-27)

1. **Isolamento de risco:** criar aluno/lote no tenant A; tentar consultar o risco individual, resumo, críticos e scoring do lote como tenant B. Esperado: 404 para recurso individual/lote não pertencente e respostas de listas/resumo sem registros de A.
2. **Política futura:** criar política `shared_training` efetiva e uma política `institution_only` com vigência futura. Antes da vigência, a política atual permanece ativa; após a vigência, a nova política bloqueia compartilhamento.
3. **Autorização local independente:** uma política de compartilhamento não concede automaticamente treino institucional; exigir autorização local válida e elegibilidade.
4. **Guard compartilhado atômico em termos de decisão:** uma instituição contribuinte não autorizada bloqueia o conjunto inteiro; não descartar silenciosamente o tenant negado.

**Teste novo:** `backend/tests/test_governance_audit_edges.py`. A inclusão do teste não significa que foi executado/aprovado; consultar GitHub Actions da PR. Testes existentes relacionados: `test_training_policy.py`, `test_shared_training_guard.py`, `test_institutional_training_authorization.py`, `test_governance_e2e.py`.
