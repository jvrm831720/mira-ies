# Plano de hardening de egress e SSRF

## Estado

Auditoria estática inicial concluída em 2026-11-04. Este documento é um plano de implementação, não uma declaração de que a proteção contra SSRF está concluída.

Nenhuma chamada a APIs institucionais foi executada. Nenhuma migration, alteração de infraestrutura ou deploy foi realizado.

## Achados confirmados no código

| Componente | Controles existentes | Lacuna |
|---|---|---|
| Canvas | HTTPS; paths REST limitados; redirects desativados; links de paginação restritos à mesma origem | O hostname configurado não é comparado a uma allowlist institucional explícita e não há pinning/validação do IP efetivamente conectado |
| Moodle | HTTPS; função REST em allowlist; redirects desativados | O hostname configurado não é comparado a uma allowlist institucional explícita e não há pinning/validação do IP efetivamente conectado |
| GVcollege | HTTPS; allowlist exata de hostname; rejeição de IP literal privado/reservado; redirects bloqueados | A validação de IP literal não protege contra resolução DNS para endereço proibido nem DNS rebinding |
| TOTVS RM worker | HTTPS (HTTP somente em development com flag); allowlist explícita; portas restritas; redirects desativados | A allowlist é validada antes da conexão, mas o endereço resolvido/conectado não é validado ou fixado no mesmo ato |
| SophiA | HTTPS; rejeição de IP literal e alguns nomes locais; allowlist exata via `SOPHIA_ALLOWED_HOSTS` em método separado | É necessário garantir que a validação runtime seja chamada por todos os caminhos antes de qualquer autenticação/requisição; não há validação do IP conectado |
| JACAD | HTTPS; domínio restrito a `jacad.com.br` e subdomínios | A restrição de domínio não protege contra DNS rebinding ou resolução para destino privado |
| Sponte | O cliente limita a origem ao domínio esperado (ver implementação e testes do cliente) | Verificar o destino de rede efetivo e a aplicação uniforme da política |
| Transporte REST genérico | HTTP/HTTPS com HTTP inseguro exigindo opção explícita; redirects desativados; path relativo | Sem allowlist de host, validação do destino resolvido ou política de egress comum |
| SOAP TOTVS | HTTP/HTTPS com HTTP inseguro exigindo opção explícita; redirects desativados; operação ReadRecord apenas | Sem allowlist de host ou validação do destino resolvido/conectado |

## Objetivos de segurança

1. **Autorização de destino por tenant:** cada integração deve ter host, porta e, quando necessário, caminho/origem aprovados por configuração administrativa confiável. Não aceitar allowlist vinda de payload de job, webhook ou usuário não autorizado.
2. **Normalização inequívoca:** normalizar hostname (IDNA, lowercase, trailing dot), porta e esquema antes da comparação. Comparação de hostname deve ser exata; não usar sufixo permissivo que aceite domínios como `instituicao.example.attacker.test`.
3. **DNS validado no momento da conexão:** resolver A e AAAA no fluxo de conexão; rejeitar respostas proibidas; conectar ao endereço validado sem uma segunda resolução implícita. Preservar hostname original para TLS SNI e validação do certificado. Revalidar em novas conexões e após expiração/renovação de DNS.
4. **Bloqueio de destinos não autorizados:** por padrão negar loopback, link-local, multicast, unspecified, reserved, metadata e redes privadas. Se uma IES exigir endpoint privado/on-premises, permitir somente por rota privada/VPN/gateway dedicado, com CIDR e tenant explicitamente aprovados; não abrir exceção global.
5. **Egress de rede como defesa independente:** aplicar política de saída no runtime/infraestrutura que bloqueie destinos internos e metadata, com exceções explícitas para rotas institucionais aprovadas. A política de aplicação não substitui firewall/egress gateway.
6. **Redirects e credenciais:** manter redirects desativados. Se um fluxo futuro exigir redirect, revalidar cada salto e nunca encaminhar credenciais entre origens. Não seguir redirect para host diferente.
7. **Proxies:** definir explicitamente se proxy de ambiente é permitido. Não permitir que variáveis de ambiente alterem silenciosamente o caminho de egress; usar somente proxy/gateway administrado e aprovado.
8. **Limites operacionais:** manter timeout finito, limite de bytes, paginação limitada, métodos/endpoints allowlisted e erros sanitizados.
9. **Auditoria:** registrar tenant, integração, hostname aprovado, decisão, IP efetivo e motivo de bloqueio sem registrar tokens, headers de autenticação ou payloads pessoais.

## Estratégia de implementação por ondas

### Wave E0 — inventário e contratos (esta etapa)
- Mapear todos os clientes HTTP, SOAP, workers e pontos de configuração.
- Separar clientes com host fixo/provedor, host configurável por tenant e endpoints privados/on-premises.
- Definir contrato de destino por tenant e política para integrações privadas.
- Não alterar a semântica de conectores nem chamar endpoints reais.

### Wave E1 — política central e validação de configuração
- Criar um módulo central de política de destino.
- Exigir allowlist explícita para Canvas, Moodle, transporte REST genérico e SOAP.
- Garantir que a validação SophiA seja obrigatória antes de autenticação e chamadas.
- Manter os controles específicos existentes (JACAD, Sponte, GVcollege, TOTVS) sem enfraquecê-los.
- Testar URLs malformadas, userinfo, portas, IP literals, IPv4/IPv6, IDNA, trailing dot, suffix bypass, localhost, metadata e redirects.
- Esta onda reduz configuração arbitrária, mas **não deve ser rotulada como mitigação completa de DNS rebinding**.

### Wave E2 — transporte com resolução/pinning seguro
- Implementar transporte HTTP cuja resolução, validação e conexão sejam uma única operação controlada.
- Validar todas as respostas A/AAAA e fixar o endereço aprovado para a conexão.
- Preservar Host/SNI e verificação TLS do hostname original.
- Impedir fallback para resolução DNS não validada.
- Testar rebinding entre resolução e conexão, múltiplos registros A/AAAA, IPv4-mapped IPv6, timeouts DNS e falha do resolver.
- Usar transporte de teste determinístico; testes não dependem de rede externa.

### Wave E3 — egress de infraestrutura
- Identificar o runtime real de cada worker/backend e sua topologia de rede.
- Configurar e testar firewall/egress gateway para negar metadata, loopback e redes internas por padrão.
- Para IES on-premises, aprovar rotas privadas por tenant via VPN/gateway dedicado.
- Confirmar que nenhum runtime alternativo ou tarefa agendada contorna a política.
- Esta etapa exige acesso e decisão sobre a infraestrutura de execução; não pode ser comprovada apenas por testes unitários.

### Wave E4 — integração, observabilidade e rollout
- Rodar testes de contrato e regressão para todos os conectores.
- Verificar isolamento tenant, logs de auditoria e mensagens sanitizadas.
- Habilitar em modo deny-by-default após inventário das configurações existentes.
- Não migrar clientes existentes para hosts não verificados nem permitir fallback aberto.
- Fazer rollout controlado somente após aprovação e plano de rollback.

## Critérios de aceite

- Nenhuma URL arbitrária fornecida por payload/job pode definir destino.
- Todo destino configurável está associado a allowlist exata e tenant.
- Resolução e conexão usam o mesmo IP validado; testes demonstram resistência a DNS rebinding.
- IPv4 e IPv6 proibidos são bloqueados, incluindo metadata/link-local e formas mapeadas.
- TLS valida o hostname original e redirects não atravessam origens.
- Integrações on-premises funcionam somente por exceção de rede explicitamente aprovada.
- Testes cobrem todos os clientes de saída, não apenas Canvas/Moodle.
- Logs não contêm segredos nem dados pessoais.
- Infraestrutura de egress foi testada no runtime efetivo; sem isso, o status deve permanecer "proteção de aplicação implementada; egress de rede não verificado".

## Fora de escopo / decisões preservadas

- Não alterar `communication_opt_out`. Ausência de informação não é autorização de contato; política depende de decisão explícita de produto.
- Não alterar rotação de segredos SophiA nesta sequência.
- Não habilitar escrita em conectores.
- Não chamar APIs de IES, não executar homologação institucional, não aplicar migrations e não fazer deploy nesta etapa.
