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

1. **Armazenamento de sessão no navegador:** o token administrativo está em sessionStorage, acessível a JavaScript e portanto exposto caso exista XSS. Preferir cookie HttpOnly; Secure; SameSite ou um BFF antes de disponibilizar em produção.
2. **Infraestrutura de autenticação:** confirmar Redis gerenciado, TLS quando aplicável, segredo forte e exclusivo, CORS_ORIGINS restrito aos domínios reais e HTTPS no frontend/backend.
3. **IP e proxies:** confirmar como a hospedagem define request.client.host. Não confiar cegamente em cabeçalhos X-Forwarded-For; testar rate limiting no caminho real de produção.
4. **E-mail MFA:** validar Resend e remetente em ambiente controlado, entregabilidade, monitoramento de falhas e processo seguro de recuperação de acesso.
5. **Banco/migrations:** a migration 012_control_center_admin depende de 011_retention_observability da branch base; a 013_control_center_billing depende da 012. Validar a sequência em uma cópia/staging do banco antes de qualquer merge e não aplicar downgrade destrutivo em produção sem backup/restore testado.
6. **Testes de integração:** adicionar/rodar cenários de concorrência de MFA, replay de código, bloqueio e desbloqueio, Redis indisponível, e-mail falho, token expirado/revogado, isolamento de permissões e auditoria de ações negadas.
7. **Operação:** criar o primeiro Super Admin pelo script de bootstrap, proteger a senha, confirmar que não existe outro admin inicializado indevidamente e documentar revogação/rotação de credenciais.
8. **Observabilidade:** configurar alertas para falhas repetidas de MFA, indisponibilidade de Redis/e-mail e mudanças de privilégios; garantir que logs não incluam senha, OTP, token, API key ou link com segredo.

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
