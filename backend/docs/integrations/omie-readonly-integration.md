# Omie — integração financeira nativa da MIRA (fase read-only)

## Estado

Esta branch implementa a fundação para uma conexão Omie direta, separada do catálogo Composio. A Categoria 9 apenas classifica o Omie como integração customizada; esta implementação adiciona uma API nativa da MIRA.

## Autenticação oficial

A documentação atual do Omie descreve uma integração criada em **Meus aplicativos**, com token de acesso e `refresh_token`. As chamadas usam `Authorization: Bearer`. O token dura 24 horas; a renovação usa:

`POST https://app.omie.com.br/api/portal/apps/{app_hash}/refresh-token/`

com `token` e `refresh_token` no corpo e sem cabeçalho Authorization. O novo par deve substituir o anterior. A MIRA guarda os tokens cifrados no backend e não os devolve à interface.

Fonte: https://api.omie.com.br/docs

## Escopo desta fase

- Configurar credenciais de um aplicativo Omie por tenant.
- Cifrar access token e refresh token com chave derivada de `SECRET_KEY`.
- Armazenar `app_hash`, tokens cifrados, expiração e status em tabela com RLS e isolamento por tenant.
- Renovar token automaticamente antes de expirar e persistir o par rotacionado.
- Validar a conexão com consultas de leitura.
- Consultar contas a receber (`ListarContasReceber`) e contas a pagar (`ListarContasPagar`) com paginação.
- Permitir desativar a conexão.

## Endpoints

Prefixo: `/api/v1/integrations/omie`

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/` | Estado da conexão, sem segredos |
| PUT | `/connection` | Configurar ou substituir credenciais |
| POST | `/test` | Testar permissões de leitura |
| GET | `/accounts-receivable?page=1&page_size=50` | Consultar contas a receber |
| GET | `/accounts-payable?page=1&page_size=50` | Consultar contas a pagar |
| DELETE | `/connection` | Desativar a conexão |

Todas as rotas exigem `settings.manage`. Respostas de consulta são provenientes do Omie e não são automaticamente persistidas nem usadas para scoring.

## Segurança

- Credenciais nunca são devolvidas pela API nem escritas em logs.
- A tabela é protegida por RLS e `tenant_id`.
- Host e caminhos da API são fixos; não há URL arbitrária configurável.
- Somente operações de leitura estão expostas. Nenhuma chamada para incluir, alterar, excluir, baixar, pagar, receber, conciliar, emitir boleto ou PIX foi implementada.
- Paginação tem limites de entrada.
- Erros do fornecedor são sanitizados antes de retornar ao cliente.
- 425, 429 e 503 são classificados como erros transitórios.
- A rotação de tokens é persistida no banco após a consulta.

## Próximas fases

1. Teste de conexão com credenciais de um aplicativo Omie de demonstração.
2. Mapeamento de campos financeiros para um contrato canônico da MIRA, com proveniência e qualidade explícitas.
3. Webhooks Omie para atualizações incrementais, com verificação/autenticidade e fila assíncrona.
4. Qualquer operação de escrita exige escopos e policies específicos, approval gate, idempotência e revisão humana; não faz parte desta fase.

## Limitações conhecidas

- A MIRA ainda não recebe credenciais reais; a instituição deve criar a integração no Omie e fornecer token, refresh token e app hash por canal seguro.
- Não existe sincronização automática ou ingestão para o modelo nesta fase.
- A documentação Omie informa que cada empresa corresponde a um aplicativo e que há limites de uso; respeitar as cotas e evitar polling agressivo.
