# Segurança de acesso interno — MIRA Control Center

## Decisão confirmada

A console terá autenticação própria para a equipe interna da MIRA, independente das contas e dos papéis dos usuários de instituições. Login por e-mail e senha, com MFA obrigatório para todos os acessos administrativos. Não reutilizar `X-Admin-Secret`, `SECRET_KEY`, API keys de tenants ou contas de clientes como credenciais do browser.

## Fluxo de autenticação

1. O operador informa e-mail e senha em uma tela interna dedicada.
2. O backend valida credenciais com hash resistente a brute force, limitação de tentativas, mensagens de erro que não revelem a existência da conta e logs sem dados sensíveis.
3. Mesmo com senha correta, a sessão administrativa não é emitida antes de concluir MFA.
4. MFA deve usar TOTP (aplicativo autenticador) ou mecanismo equivalente com verificação no servidor. Códigos de recuperação devem ser de uso único, armazenados como hashes e entregues uma única vez.
5. Sessão curta e revogável, cookies `HttpOnly`, `Secure`, `SameSite` quando usar cookie; proteção CSRF se aplicável. Nunca guardar tokens privilegiados em localStorage.
6. MFA obrigatório em cada nova sessão administrativa; exigir nova autenticação/MFA para ações críticas, como desativar organização, alterar papéis privilegiados ou registrar cobrança como paga.
7. Processo de recuperação de MFA precisa de verificação reforçada e trilha de auditoria; suporte não pode simplesmente desabilitar MFA sem aprovação.

## Identidade e RBAC

Criar entidade interna separada, por exemplo `AdminPrincipal`, sem `tenant_id` de cliente e sem usar o papel `User.role == admin` como substituto.

Papéis iniciais:
- `super_admin`: administração global, concessão de papéis e ações críticas.
- `operations`: saúde da plataforma, canais, filas e diagnóstico.
- `finance`: planos, preços, contratos, cobranças e renovações.
- `support`: consulta limitada e suporte por organização.
- `auditor`: leitura de logs e relatórios sem mutações.

RBAC deve ser validado em cada endpoint no backend, com política de ação e recurso. A interface pode esconder ações, mas isso nunca é controle de segurança. Ações cross-tenant exigem permissão explícita e registram o tenant alvo.

## Auditoria

Eventos append-only devem conter ator interno, ação, alvo, organização afetada, resultado, horário UTC, request/correlation ID e justificativa quando aplicável. Registrar login bem-sucedido/falhado, MFA, recuperação, concessão/revogação de papéis, leitura/exportação sensível, edição de plano/preço, link/cobrança, suspensão e exclusão lógica de organização.

Não registrar senha, OTP, segredo TOTP, token de sessão, chave de API, link contendo credenciais, dados de cartão ou conteúdo completo de mensagens. Não oferecer endpoint de alteração/exclusão de eventos. Limitar acesso à consulta de auditoria e definir retenção.

## Modelo de dados sugerido

- `AdminPrincipal`: e-mail normalizado único, nome, hash de senha, papel/estado, MFA habilitado, segredo TOTP protegido por criptografia de aplicação/KMS, versão de autenticação, contadores de falha e timestamps.
- `AdminRecoveryCode`: hash de código de recuperação, uso único e data de consumo.
- `AdminAuditEvent`: ator, ação, alvo, tenant alvo opcional, motivo, resultado, request ID, metadados minimizados e timestamp.
- Opcionalmente `AdminSession` se a revogação por sessão exigir persistência; caso contrário, versão de autenticação para revogar todas as sessões.

## Ordem segura de implementação

1. Revisar convenções atuais de migrations Alembic e testes; identificar o head real antes de criar migration.
2. Criar modelos/migration e testes de persistência para identidade interna, MFA e auditoria.
3. Implementar enrollment TOTP, confirmação, login em duas etapas, rate limiting e recuperação.
4. Criar dependência `require_admin_permission` independente de `get_current_tenant`.
5. Testar explicitamente que token de cliente, API key de tenant e segredo administrativo antigo não dão acesso à console.
6. Implementar primeiro os endpoints de leitura e depois mutações financeiras/organizacionais.
7. Testar autorização negativa por papel, tenant alvo, MFA ausente, sessão expirada/revogada, brute force e eventos de auditoria.
8. Executar testes backend, lint e build frontend; revisar diff e resultados do CI antes de qualquer merge/deploy.

## Critérios de aceite

- Senha correta sem MFA válido nunca emite sessão administrativa.
- Conta interna é separada das contas de cliente.
- Cada endpoint administrativo valida papel no servidor.
- Usuários de clientes e API keys de tenant não conseguem usar endpoints administrativos.
- Ações sensíveis e falhas de autenticação relevantes geram eventos de auditoria sem segredos.
- Recuperação de MFA não permite bypass por suporte comum.
- Nenhuma alteração chega à `main` ou produção antes de revisão e CI verde.
