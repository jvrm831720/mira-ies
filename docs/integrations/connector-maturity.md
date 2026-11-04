# Catálogo de integrações — maturidade técnica

Este catálogo separa capacidade implementada de homologação em ambiente real.
Uma biblioteca, adapter ou cliente HTTP não significa que exista conexão
operacional com um cliente.

## Estados

| Estado | Significado | Comunicação externa |
|---|---|---|
| Em desenvolvimento | Trabalho técnico ainda incompleto. | Não anunciar como disponível. |
| Suporte técnico implementado | Cliente, adapter ou fluxo técnico existe e possui testes, mas depende de configuração/validação institucional. | Pode ser descrito como suporte técnico, com ressalva de homologação. |
| Homologada em ambiente real | Integração validada com autorização, credenciais, contrato de dados e evidência de execução em ambiente institucional. | Pode ser anunciada como homologada, dentro do escopo validado. |

## Inventário conhecido

| Plataforma | Capacidade registrada | Estado |
|---|---|---|
| TOTVS RM | Cliente REST/SOAP, extração configurável e componentes de sincronização/financeiro. Instalação real e contrato do cliente ainda exigem validação. | Suporte técnico implementado |
| SophiA Gestão Escolar | Cliente nativo da API, fila/worker, snapshots e isolamento por tenant. Credenciais e ambiente institucional ainda não homologados. | Suporte técnico implementado |
| JACAD | Conector de API e sincronização em background. Homologação real depende de instalação e credenciais do cliente. | Suporte técnico implementado |
| Sponte | Conector da API Sponte BI, extração paginada e sincronização em background. Homologação real depende do cliente. | Suporte técnico implementado |
| GVDASA / GVcollege | Cliente WebAPI read-only, contratos de views por tenant, OData restrito e manifesto de prontidão. Sem credenciais ou views reais de cliente. | Suporte técnico implementado |
| WPensar / Isaac | Suporte a transformação de payload; sem cliente nativo de API e sincronização pull. | Em desenvolvimento |
| Moodle | Suporte a webhook/transformação; sem cliente nativo pull. | Em desenvolvimento |
| Canvas | Suporte a webhook/transformação; sem cliente nativo pull. | Em desenvolvimento |
| JSON genérico | Transformação de payload e rota de ingestão genérica. Não equivale a conector nativo de ERP. | Suporte técnico implementado |

## Regras de governança

- Não promover uma integração para homologada sem evidência de teste em ambiente real autorizado.
- Não inventar autenticação, endpoint, views, campos ou semântica de negócio.
- Registrar escopo homologado por versão, instituição e contrato de dados.
- Credenciais devem permanecer em provedor de segredos; nunca em documentação, fixtures ou logs.
- A classificação do catálogo é técnica e não substitui validação comercial, contratual, LGPD ou de segurança.
- Atualizar este documento quando uma wave for integrada à branch principal. PRs abertas devem ser identificadas como trabalho em revisão, não como capacidade já disponível em produção.
