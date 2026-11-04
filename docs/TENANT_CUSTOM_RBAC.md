# RBAC institucional — cargos personalizados

## Modelo de autorização

Cada cargo personalizado pertence a um único `tenant_id` e contém:
- nome e descrição;
- cargo-base (`viewer`, `operator` ou `coordinator`);
- conjunto de permissões estáveis do catálogo;
- estado ativo/desativado.

O cargo-base é um teto de privilégio. O cargo personalizado pode retirar acessos e conceder permissões dentro desse teto, mas não pode criar um papel `admin` nem conceder uma permissão acima do seu nível-base. O papel administrativo principal permanece reservado ao bootstrap/provisionamento institucional existente.

## Catálogo inicial

As chaves são versionáveis e independentes dos rótulos da interface:
- acesso: `access.viewer`, `access.operator`, `access.coordinator`;
- painel: `dashboard.view`;
- alunos: `students.view`, `students.sensitive.view`, `students.create`, `students.edit`, `students.delete`;
- campanhas: `campaigns.view`, `campaigns.create`, `campaigns.edit`, `campaigns.approve`, `campaigns.execute`, `campaigns.delete`;
- equipe: `members.view`, `members.manage`, `permissions.manage`;
- administração: `settings.manage`, `audit.view`, `critical.manage`;
- dados: `data.view`, `data.import`.

A autenticação central resolve a permissão específica por recurso e método em toda requisição autenticada com cargo personalizado. Rotas conhecidas usam chaves por módulo/ação; rotas de leitura ainda não mapeadas exigem `access.viewer` e mutações não mapeadas exigem `critical.manage` (falha fechada por padrão). Novos endpoints devem adotar `require_permission` ou adicionar um mapeamento explícito antes de liberar a funcionalidade.

## API

- `GET /api/v1/org/roles/catalog`
- `GET /api/v1/org/roles`
- `POST /api/v1/org/roles`
- `PATCH /api/v1/org/roles/{role_id}`
- `POST /api/v1/org/roles/{role_id}/duplicate`
- `POST /api/v1/org/roles/{role_id}/deactivate`
- `GET /api/v1/org/roles/{role_id}/members`
- `POST /api/v1/org/members/{user_id}/role`
- `GET /api/v1/org/members/{user_id}/permissions`
- `GET /api/v1/org/role-audit`

## Controles

- Todas as consultas e mutações filtram por `tenant_id`; as tabelas novas usam RLS com `FORCE ROW LEVEL SECURITY`.
- Cargos não podem ser atribuídos entre instituições.
- A atribuição invalida sessões anteriores via `auth_version`.
- Mutação de cargo e atribuição exigem administrador humano ou delegado com `permissions.manage`, MFA AAL2 recente e sessão válida.
- Delegados só podem criar, editar, duplicar, desativar e atribuir cargos com permissões contidas no próprio conjunto efetivo; não podem elevar o cargo-base do destinatário.
- Usuários administrativos principais não podem receber cargo personalizado pela API.
- Convites não podem conceder `admin` a não administradores; concessão de admin exige MFA recente.
- Um cargo atribuído não pode ser desativado enquanto houver membros ativos associados.
- A revogação de cargo personalizado retorna ao papel de menor privilégio (`viewer`).
- A auditoria registra criação, edição, duplicação, desativação e atribuição/revogação. O banco impede UPDATE/DELETE direto na tabela de auditoria, exceto operações referenciais em cascata.

## Recuperação administrativa

O papel `admin` existente não é editável nem pode ser convertido em cargo personalizado por esta funcionalidade. Um trigger no banco impede rebaixar, desativar ou excluir o último administrador ativo de um tenant. A recuperação de credenciais usa o fluxo existente de redefinição de senha por e-mail e os códigos de recuperação MFA; se ambos forem perdidos, é necessário um processo de suporte com verificação de identidade fora de banda. A atribuição de cargos não altera nem desativa administradores principais.

## Migration

A migration `039_tenant_custom_rbac` cria as tabelas e referências necessárias. Ela é versionada no repositório, mas não é aplicada automaticamente por esta alteração. Não foi executado deploy nem alteração do banco remoto.
