# Gestão de mudanças das regras de negócio

## Alteração de regra
1. Localizar o ID estável no catálogo; se for nova regra, reservar ID exclusivo do domínio.
2. Descrever motivo, problema, responsável, data e decisão proposta.
3. Marcar status de decisão (APROVADA/RECOMENDAÇÃO/PENDENTE/SUBSTITUÍDA) sem inferir aprovação.
4. Mapear efeitos em API, UI, modelo de dados, migrações, jobs, integrações, permissões, métricas e regras dependentes.
5. Definir critérios de aceite positivos, negativos, borda, repetição, concorrência e recuperação.
6. Implementar somente após aprovação exigida; atualizar testes, evidências e matriz de rastreabilidade.
7. Validar em ambiente seguro; registrar commit, run de CI e ambiente. Não equiparar CI a staging.
8. Atualizar documentação no mesmo PR da mudança, incluindo status e decisão anterior.
9. Para regras substituídas, manter o ID antigo como SUBSTITUÍDA e apontar para a regra sucessora; não reutilizar IDs.
10. Para migrações e operações críticas, anexar plano de backup/restore e rollback testado antes de produção.

## Revisão e aprovação
- Regras de produto/resultado: responsável de produto/fundador.
- Segurança, isolamento, autenticação e autorização: Engenharia + Segurança; risco P0 requer revisão explícita.
- Uso de dados, compartilhamento e retenção: responsável de produto + engenharia + revisão jurídica/contratual quando aplicável.
- Métricas: dono de analytics e produto, com fórmula e denominador documentados.

## Política de release
- PR isolada, CI verde e diff revisado.
- Nenhuma migration aplicada em produção como parte da documentação.
- Nenhum merge/deploy automático por esta documentação.
- Rollback de modelo ou aplicação não substitui avaliação de dados já usados em treinamento.
- Falha ou evidência ausente mantém status de validação como parcial/não testada.

## Histórico desta documentação
- 2026-10-27: fase 1 de auditoria documental criada na branch docs/business-rules-audit-2026-10 a partir de main commit e25858b4cb12dab781b19e0ed46cf193007fb520. Nenhuma funcionalidade, banco, configuração de produção ou integração foi alterada.
