# Histórico de avaliações e Monitoramento de risco

## Objetivo e auditoria do fluxo atual

A tela **/monitoramento** anterior consultava o resumo do score atual, alunos e logs de retenção. Esses dados não formavam uma trajetória histórica de avaliações. O fluxo real de avaliação em lote é **backend/app/ml/scoring.py::score_batch**, chamado pelos endpoints **POST /api/v1/score/batch/{batch_id}** e **POST /api/v1/score/pending**.

O score efetivo exibido no aluno é calculado pelo modelo selecionado (**resolve_scoring_model**), regras de negócio e ajuste dinâmico de engajamento. A versão e o escopo do modelo são preservados no snapshot do aluno e em cada nova avaliação. O serviço **refresh_engagement_profile** também pode alterar o score quando eventos de engajamento mudam o ajuste dinâmico; quando o score/classificação efetivamente muda, ele registra uma nova avaliação. Consultas de histórico nunca disparam scoring.

**POST /api/v1/predict** é uma previsão ad hoc sem aluno persistido e não entra no histórico. **POST /api/v1/predict/what-if** é uma simulação e também não é uma avaliação histórica.

## Persistência

A migration **019_risk_assessment_history** cria **risk_assessments**, com:
- UUID da avaliação e UUID da execução de scoring;
- tenant_id, student_id e lote de origem opcional;
- evaluated_at do cálculo real;
- score final (0–100), classificação, escopo e versão do modelo;
- score base e ajuste dinâmico;
- versão explícita da semântica de score/classificação, independente da versão do artefato de modelo;
- snapshot de features, explicação preservada quando disponível e contexto de origem.

A avaliação é gravada na mesma transação que atualiza o score do aluno. O índice composto tenant/aluno/data suporta consultas históricas. Uma constraint única por scoring_run_id e aluno evita duplicação dentro da mesma execução. O fluxo normal ignora alunos já pontuados. Reavaliações com force=true exigem o cabeçalho Idempotency-Key; retries com a mesma chave reutilizam a execução já gravada e não duplicam o histórico.

## Histórico anterior

TrainingEvent possui timestamps, versão e score ajustado do modelo, mas não preserva o ajuste dinâmico aplicado ao score final exibido, nem a explicação original de forma consistente. Por isso a migration **não converte automaticamente esses eventos** para risk_assessments: essa conversão produziria uma trajetória que poderia divergir do score final real. O histórico confiável começa com avaliações gravadas pelo novo fluxo; não se inventam pontos anteriores.

## Segurança e governança

- Todos os endpoints usam get_current_tenant e filtram por tenant autenticado.
- A tabela possui FK composta (tenant_id, student_id) para impedir associação cruzada entre tenant e aluno.
- A migration ativa e força RLS em risk_assessments, com política baseada em current_setting('app.tenant_id', true).
- O backend define esse contexto transacional após autenticação; serviços de scoring e refresh de engajamento também o definem porque podem ser chamados por processos internos.
- Nenhuma leitura de histórico autoriza treinamento. A tabela não é conectada a nenhum pipeline de treinamento compartilhado. A política de dados dos tenants continua sendo aplicada pelos gates existentes em qualquer pipeline de treinamento.

O teste de integração via Base.metadata.create_all não simula por si só a política RLS criada pela migration; a validação final da migration/RLS deve ocorrer num banco de staging com alembic upgrade head.

## Contratos

### GET /api/v1/risk/history

Parâmetros:
- from, to: timestamps ISO-8601; padrão: últimos 90 dias.
- course: filtro parcial por curso.
- risk_level: baixo, medio ou critico.
- page, page_size: paginação das avaliações (1–200).

Retorna contagem de avaliações, alunos com avaliação, série semanal, distribuição representativa por semana, movimentações e avaliações paginadas. A série de score usa a média das últimas avaliações por aluno em cada semana, agrupada por escopo/versão do modelo; não mistura versões. Cada aluno contribui com uma avaliação representativa por semana para a distribuição. A consulta temporal usa até 5.000 registros recentes e sinaliza truncamento; a lista de movimentações limita a 500 casos priorizados.

### GET /api/v1/students/{student_id}/risk/history

Retorna trajetória do aluno autorizado, avaliações paginadas e intervenções/desfechos no mesmo período. Aluno inexistente ou pertencente a outro tenant retorna 404. A consulta não calcula score novo.

Erros: 401 para falta/invalidade de credenciais; 404 para aluno fora do tenant; 422 para período inválido ou classificação desconhecida; 5xx para falhas de persistência/consulta.

## Comparação

A versão de semântica atual é **risk-score-v1**: escala operacional 0–100, baixo abaixo de 40, moderado a partir de 40 e crítico a partir de 70. Ela deve ser incrementada quando mudar a escala, os limiares ou a regra de classificação, mesmo que o artefato do modelo mantenha a mesma versão. O score tem escala operacional de 0 a 100; quanto maior, maior o risco. A variação só é calculada quando versão e escopo do modelo são idênticos e estão presentes. delta = score atual - score anterior; delta positivo indica aumento de risco, negativo redução. Delta exatamente zero é classificado como “sem mudança relevante”; nenhum limiar não-zero é apresentado como cientificamente validado. Versões/escopos incompatíveis são classificados como mudança de modelo e não recebem delta. Ausência de avaliação não é convertida em score zero.

## Explicabilidade e intervenções

Os fatores são retornados apenas se tiverem sido preservados na avaliação. Quando SHAP não foi executado no lote, a avaliação registra explicitamente que a explicação está indisponível; o endpoint histórico não recalcula fatores com o modelo atual. Logs de intervenção são ligados por tenant e student_id, e apresentados como eventos temporais, sem inferir causalidade nem substituir desfechos de permanência/evasão.

## Limitações que permanecem

- A série temporal agregada tem limite operacional de 5.000 avaliações por consulta; acima disso, a interface avisa que a série e as movimentações podem estar parciais.
- Movimentações são limitadas a 500 casos por resposta; paginação dedicada da fila pode ser necessária em instituições de grande porte.
- A migration e o comportamento RLS ainda precisam ser aplicados e validados em staging. Nenhum deploy é declarado por esta documentação.
