# MIRA Control Center — revisão de segurança pré-release

## Estado

A implementação está em uma branch de trabalho e a PR permanece em rascunho. **Não está aprovada para produção e não deve ser mesclada nem implantada antes de resolver os bloqueadores abaixo.**

## Controles implementados

- Autenticação administrativa independente do login comum do MIRA.
- MFA por e-mail com código de seis dígitos, expiração de cinco minutos, uso único, limite de tentativas e cooldown.
- Token de curta duração com emissor e audiência exclusivos do Control Center e validação de versão da sessão.
- Rate limiting via Redis com falha fechada quando o Redis está indisponível.
- RBAC no backend; as verificações da interface são apenas conveniência visual, não substituem autorização no servidor.
- Auditoria de login/MFA e alterações de membros, instituições e registros financeiros; metadados de auditoria são redigidos.
- Links de pagamento aceitam apenas HTTPS; nenhum pagamento é processado pelo Control Center.
- Estado de canais informa somente se há configuração presente. Não representa teste de conectividade.

## Bloqueadores antes do release

1. **Sessão via BFF:** o token administrativo agora é mantido em cookie HttpOnly, com Secure em produção, SameSite=Lax e expiração curta; o token não é devolvido ao JavaScript nem salvo em sessionStorage. O BFF também exige origem same-origin para requisições que alteram estado. Ainda é necessário validar a política de cookies e o domínio real de hospedagem em staging, e manter proteção contra XSS.
2. **Infraestrutura de autenticação:** confirmar Redis gerenciado, TLS quando aplicável, segredo forte e exclusivo, CORS_ORIGINS restrito aos domínios reais e HTTPS no frontend/backend.
3. **Rate limiting e proxies:** o login/MFA não usa mais request.client.host como chave de bloqueio compartilhada, pois o backend recebe chamadas server-to-server do BFF e pode ver o mesmo IP para todos. O limite é por identidade de conta, com chave HMAC no Redis, sem confiar em X-Forwarded-For. Em staging, verificar limites para duas contas independentes e confirmar comportamento contra tentativa distribuída; não adicionar limite por IP até existir uma cadeia de proxy confiável/allowlisted.
4. **E-mail MFA:** validar Resend e remetente em ambiente controlado, entregabilidade, monitoramento de falhas e processo seguro de recuperação de acesso.
5. **Banco/migrations:** a migration 012_control_center_admin depende de 011_retention_observability da branch base; a 013_control_center_billing depende da 012. Validar a sequência em uma cópia/staging do banco antes de qualquer merge e não aplicar downgrade destrutivo em produção sem backup/restore testado.
6. **Testes de integração:** adicionar/rodar cenários de concorrência de MFA, replay de código, bloqueio e desbloqueio, Redis indisponível, e-mail falho, token expirado/revogado, isolamento de permissões e auditoria de ações negadas.
7. **Operação:** criar o primeiro Super Admin pelo script de bootstrap, proteger a senha, confirmar que não existe outro admin inicializado indevidamente e documentar revogação/rotação de credenciais.
8. **Observabilidade:** configurar alertas para falhas repetidas de MFA, indisponibilidade de Redis/e-mail e mudanças de privilégios; garantir que logs não incluam senha, OTP, token, API key ou link com segredo.

## Revisão de segurança — 23/10/2026

### Correção aplicada nesta revisão

- O rate limit de autenticação usa somente identidade de conta (10 tentativas/5 minutos) no login e na verificação MFA. O teto por IP foi removido para evitar bloqueio coletivo quando vários administradores chegam pelo mesmo BFF. A identidade é protegida por HMAC na chave Redis; o sistema não confia em `X-Forwarded-For`.
- Testes cobrem chaves separadas por conta e falha fechada quando Redis está indisponível.

### Resultado da análise estática do fluxo

- **RBAC:** as mutações de instituição e membro exigem permissões `orgs:write` e `members:write`, concedidas apenas a `super_admin` no mapa atual de permissões do backend. A checagem visual no frontend não é a barreira de segurança.
- **Revogação de sessão de usuário:** a alteração de perfil/status incrementa `auth_version`; a autenticação comum compara essa versão e rejeita tokens antigos. Instituições inativas também são rejeitadas pelo fluxo de autenticação comum.
- **Cookies/CSRF:** o BFF usa cookie HttpOnly, SameSite=Lax, Secure em produção e valida Origin exata em métodos que alteram estado. A validação em navegador com o domínio real continua pendente.
- **Auditoria:** mudanças em instituição e membro registram ator, alvo, campos alterados e valores anteriores/posteriores. Não foi executado teste end-to-end em ambiente real para comprovar a persistência e consulta desses eventos.
- **Rate limit:** não há teto global por IP no fluxo de login/MFA; o limite por conta evita que o IP compartilhado do BFF bloqueie outros administradores. A proteção contra ataques distribuídos deve ser monitorada em staging e complementada na borda somente com IP de cliente fornecido por proxy confiável.

### Validação executada e pendente

- CI anterior ao ajuste de rate limit: frontend lint/build, Ruff, pytest e grafo de migrations passaram no run [40021139281](https://github.com/jvrm831720/mira-ies/actions/runs/40021139281).
- O commit que inclui a correção e seu teste precisa concluir a CI antes de ser considerado validado.
- **Ainda pendente — staging hospedado:** não há endpoint/credenciais de homologação disponíveis nesta execução. Portanto, não foi possível testar login → entrega real de e-mail MFA → cookie no domínio hospedado → consultas/mutações → auditoria, nem falhas reais de Redis/Resend. Essa etapa não pode ser declarada resolvida por testes unitários ou CI; executar quando o ambiente de staging estiver disponível.
- O diff branch/base informa que a branch de trabalho está divergente da base de PR; revisar a integração da migration `011_retention_observability` antes de aplicar as migrations ou integrar a PR.

## Limites atuais do MVP

- Instituições e membros têm consulta e ativação/desativação; o restante da gestão de cadastro deve evoluir conforme regras de negócio.
- O financeiro é manual, com um registro por instituição e status informado por operador; não confirma pagamentos automaticamente.
- Os avisos de vencimento são calculados e exibidos no painel; não há envio automático de lembretes.
- A tela de canais mostra configuração presente/ausente, não disponibilidade real dos fornecedores.

## Critério de liberação

- CI completa aprovada no commit final.
- Migrações validadas em staging com backup/restore testado.
- Revisão de segurança dos bloqueadores acima assinada.
- Revisão de negócio dos papéis/permissões e do fluxo manual de cobrança.
- Aprovação explícita antes de retirar o estado de rascunho, fazer merge ou iniciar deploy.
