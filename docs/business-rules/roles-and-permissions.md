# Papéis e permissões — matriz preliminar

**Status:** análise estática parcial. Os nomes abaixo foram encontrados em documentação ou esquemas; não assumir que todos os perfis têm implementações consistentes.

## Identidades separadas

- Aplicação institucional: `User` em `backend/app/models/auth.py`, com `tenant_id`, `role`, `is_active` e `auth_version`.
- Control Center: `AdminPrincipal` em `backend/app/models/control_center.py`, com identidade própria, papel, estado e versão de autenticação. O fluxo não deve tratar `User.role=admin` como administrador global.

## Matriz observada (não substitui revisão endpoint a endpoint)

| Perfil | Escopo observado/documentado | Leitura | Escrita | Lacunas |
|---|---|---|---|---|
| `super_admin` | Global Control Center | Global conforme permissões atribuídas | `orgs:write`, `members:write` no mapa atual; outras ações dependem do mapa | Confirmar matriz completa e segregação de funções |
| `operations` | Operação, filas, canais | Saúde/diagnóstico conforme mapa | Não presumir escrita global | Verificar ações por endpoint |
| `finance` | Cobrança/planos | Financeiro | `billing:write` conforme mapa/documentação | Não há processamento de pagamento; confirmar ações permitidas |
| `support` | Suporte limitado | Por organização/escopo autorizado | Sem exclusões/segredos por intenção | Limites de acesso a PII precisam de teste |
| `auditor` | Auditoria/relatórios | Leitura | Sem mutações por intenção | Verificar todos os endpoints |
| `admin` institucional | Tenant próprio | Não determinada globalmente | Papel permitido no esquema | Não equivale a super_admin |
| `coordinator` | Tenant próprio | Operação acadêmica conforme UI/rotas | Não determinada completamente | Validar por ação |
| `operator` | Tenant próprio | Operação conforme UI/rotas | Não determinada completamente | Validar por ação |
| `viewer` | Tenant próprio | Leitura conforme UI/rotas | Deve ser negada por regra proposta | Confirmar autorização no backend |
| Contas de serviço/API key | Tenant associado | Rotas de integração autorizadas | Escopo de integração | Rotação e escopos granulares não verificados |

## Evidências

- `backend/app/api/control_center_admin.py`: dependências `admin_permission("orgs:read")`, `members:read`, `billing:read/write`, `audit:read`; mutações de organização e membro usam permissões específicas.
- `backend/app/api/control_center_auth.py`: autenticação interna independente, MFA e sessão administrativa.
- `backend/app/models/auth.py`: papéis institucionais são texto com default `coordinator`, não enum no modelo.
- `docs/CONTROL_CENTER_INTERNAL_AUTH.md`: papéis internos documentados.

## Critérios de aceite

1. Cada endpoint protegido tem uma permissão explícita de recurso/ação e teste negativo.
2. Token institucional, API key de tenant e sessão interna não são intercambiáveis.
3. Usuário não pode alterar seu próprio papel/tenant via payload.
4. IDs manipulados não permitem ação fora do escopo autorizado.
5. Elevação de privilégio, desativação e revogação de sessão geram auditoria.
6. A interface pode ocultar ações, mas o backend continua a rejeitar chamadas diretas.

## Pendências

A matriz completa precisa ser gerada a partir de todos os endpoints e dependências; a tabela é um inventário preliminar, não certificação de RBAC.
