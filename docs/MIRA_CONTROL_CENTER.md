# MIRA Control Center — Escopo e arquitetura

## Objetivo

Criar uma console administrativa exclusiva para o time interno da MIRA, com visão 360° da operação técnica, clientes, segurança, retenção e gestão comercial/financeira. O Control Center não deve reutilizar a sessão comum de um usuário de instituição como autorização administrativa.

## Direção arquitetural

- Desenvolvimento isolado em branch, sem alterações diretas na `main`.
- Interface interna separada logicamente da aplicação do cliente; preferencialmente app/deploy administrativo próprio.
- Backend administrativo autenticado e autorizado no servidor. O frontend nunca recebe segredo administrativo nem credenciais de provedores.
- Reutilizar entidades e métricas existentes quando possível, evitando cópias divergentes de organizações, intervenções e telemetria.
- Tenant scoping obrigatório em consultas operacionais e validação explícita de permissões para ações cross-tenant.

## Módulos

### 1. Visão 360° / Operação
- Saúde da API, banco, Redis, workers, filas e dead letters.
- Disponibilidade de provedores, falhas, retries, latência e alertas.
- Mensagens enviadas/entregues/rejeitadas, engajamento e custos estimados.
- Filtros por organização, canal, provedor e período.

### 2. Organizações / clientes
- Criar e editar organização, estado de implantação e status comercial.
- Suspender, reativar e encerrar com confirmação reforçada.
- Plano associado, limites, consumo, datas de contrato e histórico.
- Exclusão lógica/desativação como padrão; exclusão física só em fluxo excepcional, com autorização reforçada e política de retenção/LGPD.

### 3. Membros e acessos
- Convidar, ativar, desativar e remover membros.
- Papéis por organização e permissões internas globais separadas.
- Revogar sessões e registrar alterações de privilégio.
- MFA para equipe interna e princípio do menor privilégio.

### 4. Canais e integrações
- Estado e configuração de WhatsApp, e-mail e SMS por organização.
- Provedor primário/fallback, limites e custos unitários.
- Verificação de conexão e histórico de falhas.
- Segredos sempre mascarados; alteração via secret manager/fluxo seguro, nunca recuperados em texto puro no browser.

### 5. Auditoria e logs
- Registro append-only de ações administrativas: ator, timestamp UTC, organização-alvo, ação, resultado, motivo, request/correlation ID e metadados minimizados.
- Auditoria de login, acesso negado, alterações de membros, plano, preço, canal, exportação e ações destrutivas.
- Nunca registrar senhas, tokens, chaves, corpo integral de mensagens ou dados pessoais desnecessários.
- Busca e filtros com acesso restrito e política de retenção.

### 6. Planos, preços e contratos
- CRUD de planos, preço mensal/anual, moeda, limites, recursos e período de teste.
- Condições específicas por cliente, desconto, vigência e motivo da exceção.
- Histórico versionado de preços; mudanças não alteram retroativamente contratos ativos sem ação explícita.
- Datas de início, renovação, vencimento e encerramento.

### 7. Cobranças e links de pagamento
- Cadastrar link de pagamento manual ou gerar por gateway integrado.
- Associar cobrança a organização, contrato, valor, moeda, vencimento e referência externa.
- Status: rascunho, pendente, pago, vencido, falhou, cancelado e reembolsado quando suportado.
- Webhooks assinados e idempotentes para reconciliar status. Não confiar em retorno do browser como prova de pagamento.
- Não armazenar dados de cartão. Credenciais do gateway no backend/secret manager.

### 8. Vencimentos e receita
- Filas de vencimento em 7, 15 e 30 dias; vencidos e renovações em negociação.
- Alertas e atribuição de responsável comercial.
- MRR/ARR estimados, contratado, faturado, recebido, pendente e inadimplência claramente separados.
- Receita por plano/cliente e histórico de cobranças, com filtros por período.
- Notificações comerciais configuráveis, sem envio automático a cliente até habilitação explícita.

### 9. Retenção e resultados
- Desfechos acadêmicos associados a intervenções.
- Métricas por cliente/canal/provedor, custo estimado e engajamento.
- Exibir claramente que atribuição observacional não comprova causalidade.

## Papéis sugeridos

- **Super Admin:** acesso global e ações críticas.
- **Operações:** saúde de serviços, filas, provedores e canais; sem acesso irrestrito a dados financeiros ou exportações.
- **Financeiro/Comercial:** planos, preços, contratos, cobranças, links e renovações.
- **Suporte:** consulta limitada por organização, sem acesso a segredos nem exclusões.
- **Auditoria/Leitura:** visualização de logs e relatórios, sem mutações.

Permissões devem ser aplicadas no backend por endpoint/ação, não apenas escondendo botões na interface. Ações de alto impacto devem pedir confirmação, motivo e, quando apropriado, aprovação de segunda pessoa.

## Entidades sugeridas (a validar contra o schema existente)

- `AdminPrincipal` / identidade interna e associação de papéis.
- `AdminAuditEvent` com trilha append-only.
- `Plan` e `PlanVersion`.
- `OrganizationSubscription` / contrato, vigência, preço negociado e renovação.
- `Invoice` / cobrança e referência do gateway.
- `PaymentLink` / URL, expiração e estado.
- `PaymentProviderEvent` / eventos externos idempotentes.
- `OrganizationChannelConfig` / estado e metadados não secretos dos canais.

Antes de criar migrações, conferir as entidades atuais de tenant, auth, billing e connector para estender o modelo em vez de duplicá-lo.

## Plano de implementação

1. Inspecionar modelos existentes de tenant, auth, billing e connectors; desenhar fronteira administrativa e threat model.
2. Implementar autenticação interna, RBAC, trilha de auditoria e APIs administrativas tenant-safe.
3. Construir a aplicação interna com visão global e detalhe por organização.
4. Implementar membros e configurações de canal.
5. Implementar catálogo de planos, contratos, vencimentos e links de pagamento.
6. Integrar gateway de pagamento escolhido e validar webhooks assinados/idempotentes.
7. Adicionar alertas, dashboards, testes de isolamento, auditoria e cenários de falha.
8. Executar lint, testes backend, build frontend e revisão de segurança antes do merge.

## Critérios de aceite

- Um usuário de cliente não consegue acessar nem chamar APIs administrativas.
- Nenhuma consulta cross-tenant ocorre sem permissão explícita e auditada.
- Alterações de plano/preço e ações de organização deixam trilha de auditoria.
- Mudanças de preço não alteram contratos antigos silenciosamente.
- Pagamento só é marcado como confirmado após evento verificado do gateway ou reconciliação confiável.
- Vencimentos são calculados em timezone definido e testados nos limites de data.
- Nenhum segredo ou payload sensível aparece em logs ou respostas administrativas.
- Testes de autorização negativa, idempotência de webhook, auditoria e build passam.

## Decisões ainda necessárias

- Confirmar gateway de pagamento (por exemplo, Stripe, Asaas, Mercado Pago ou integração manual inicial).
- Definir se o Control Center será um app separado no mesmo repositório ou repositório próprio.
- Definir se a primeira fase inclui cobrança integrada ou apenas cadastro/gestão de links externos.
