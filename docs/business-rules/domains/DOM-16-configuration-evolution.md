# DOM-16 — Configuração, ambientes e evolução

## RB-ENV-001 — Regras e releases são versionados
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: regras de campanha, alvos e modelos precisam de versão e histórico; migrações precisam ter grafo consistente antes de release.
- Evidência: backend/app/models/retention_campaign.py, backend/app/ml/targets.py, backend/alembic/versions/, .github/workflows/ci.yml.
- Aceite: CI verifica grafo Alembic, lint e testes; versões anteriores continuam identificáveis para reproduzir análise.
- Risco P1; política de feature flags e compatibilidade entre ambientes não foi inventariada por completo.

## RB-ENV-002 — Ambiente de desenvolvimento não é produção
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: defaults de desenvolvimento, credenciais e bypasses não podem ser aceitos em produção; segredos vêm de configuração segura e nunca do frontend.
- Evidência: .env.example, docs/AUTH.md, docs/CONTROL_CENTER_INTERNAL_AUTH.md, backend/app/core/config.py (confirmar caminho no inventário final).
- Aceite: configuração de produção falha com segredo fraco/ausente e não permite bypass de autenticação. Risco P0/P1; auditoria de todas as variáveis pendente.
