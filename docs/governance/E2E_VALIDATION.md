# Validação ponta a ponta — governança de modelos e dados

## Escopo do teste automatizado

O cenário de integração usa somente o banco de teste configurado por `backend/tests/conftest.py`; não aplica migrations nem escreve no Supabase de produção. Os testes criam dois tenants sintéticos e verificam:

1. **Modalidade A (compartilhamento autorizado):** apenas tenant com política vigente, evidência contratual e dataset elegível pode contribuir para treino da MIRA Base.
2. **Modalidade B (uso exclusivo):** contribuição ao treino compartilhado é negada; treino institucional continua condicionado à elegibilidade e à autorização institucional separada.
3. **Mudança A → B:** a política efetiva mais recente bloqueia futuras contribuições compartilhadas. A troca de política não desfaz influência de dados já usada em modelos existentes.
4. **Isolamento:** uma sessão de tenant A não pode aprovar ou ativar artefato pertencente ao tenant B, mesmo conhecendo seu ID.
5. **Ciclo de modelo:** candidato precisa de aprovação identificada antes de ativação; rollback reativa a versão anterior e registra o artefato de origem do rollback.

Execute no backend com PostgreSQL de teste e dependências instaladas:

```bash
pytest -q tests/test_governance_e2e.py tests/test_training_policy.py tests/test_model_lifecycle.py
```

## Tratamento obrigatório dos modelos treinados antes da mudança A → B

**Não considerar a troca de modalidade como apagamento retroativo da influência do modelo.** Para artefatos globais já treinados com dados da instituição, o fluxo operacional deve:

- suspender novas contribuições e bloquear/reavaliar execuções compartilhadas ainda pendentes;
- identificar artefatos e versões de dataset/execução que incluíram a instituição, mantendo uma trilha de proveniência;
- colocar versões potencialmente afetadas em revisão e impedir nova ativação até decisão documentada;
- avaliar, com jurídico/contratos e responsável de privacidade, se o compromisso aplicável exige re-treino sem os dados, técnica de unlearning validada ou outra medida contratualmente acordada;
- manter a versão atualmente servida ou substituí-la por versão segura conforme a decisão formal, com aprovação, motivo, auditoria e rollback testado.

Excluir linhas da próxima execução, isoladamente, **não** remove a influência estatística de um modelo já treinado. A escolha entre re-treino, unlearning e outras medidas é uma decisão jurídica/técnica documentada por contrato e avaliação de risco; não deve ser inferida pela interface.

## Limites da validação

Os testes automatizados validam regras e endpoints em PostgreSQL de teste, não um deploy real. Antes de liberar para clientes, executar também um ensaio controlado em ambiente de staging com duas instituições sintéticas, conferir as trilhas de auditoria e verificar que nenhuma rotina de treino compartilhado aceita dados de tenant B sem sua autorização. A mudança de modalidade e a revisão de execuções pendentes precisam estar ligadas ao fluxo operacional de produção antes de serem declaradas concluídas.
