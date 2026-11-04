# Wave 13.1 — Governança de autorização e histórico imutável

## Escopo

Esta etapa endurece as estruturas existentes das modalidades A e B. Não cria uma segunda implementação de política e não inicia treinamento compartilhado.

- Modalidade A: `shared_training`, com autorização contratual explícita e evidência aprovada.
- Modalidade B: `institution_only`, sem contribuição para a MIRA Base.
- Treinamento institucional continua exigindo autorização institucional separada.
- Registros de política e autorização são históricos e append-only. Revogar cria um novo registro que supersede o anterior.
- Alterações de política exigem sessão interna MIRA com permissão `governance:write` e MFA recente.
- O contexto administrativo interno é definido no banco somente após validar a sessão independente do Control Center.

## Endpoints internos

- `POST /api/v1/admin/mira-governance/authorizations/shared`
- `POST /api/v1/admin/mira-governance/authorizations/shared/{policy_id}/revoke`
- `POST /api/v1/admin/mira-governance/authorizations/institutional`
- `POST /api/v1/admin/mira-governance/authorizations/institutional/{authorization_id}/revoke`

A criação de uma política compartilhada ou exclusiva registra a aprovação administrativa, referência contratual, versão, vigência, evidência e justificativa. A autorização de treinamento institucional exige referência independente de elegibilidade do conjunto de dados.

## Segurança do banco

A migration `040_governance_policy_hardening`:

- aplica `FORCE ROW LEVEL SECURITY` às políticas de uso de dados e autorizações institucionais;
- restringe linhas ao `app.tenant_id` autenticado ou ao contexto interno `app.is_mira_admin`;
- aplica RLS com `FORCE` a `training_events`;
- impede UPDATE e DELETE em registros históricos de política, autorizações e auditoria administrativa;
- permite cascatas de exclusão do tenant/admin sem abrir mutações diretas da aplicação.

O contexto `app.is_mira_admin` é definido pelo backend somente depois da validação da sessão administrativa. O cliente não envia esse valor.

## Precedência temporal

A resolução prioriza o registro mais recentemente criado e só considera registros cuja vigência já começou. Isso impede que uma autorização futura criada anteriormente reative consentimento após uma revogação posterior.

## Fora do escopo desta etapa

- Registro individual e imutável de cada contribuição elegível à MIRA Base.
- Pipeline de treinamento global que materialize apenas contribuições autorizadas.
- Registro próprio de execuções de treinamento.
- Aprovação, ativação e rollback de versões globais da MIRA Base.
- Interface administrativa para operar as novas ações.

Esses itens permanecem como gates das próximas etapas da Prioridade 13. Nenhuma migration será aplicada ao banco remoto nesta PR.
