# Wave 0.4 — Data Hub & Integrations Experience

**Branch:** `feat/product-design-wave-0-4-data-hub`  
**Base:** main / Record Experience (reconciliar antes do merge)  
**Princípio:** dados verificáveis; nenhuma conexão, sincronização, execução ou qualidade inferida de um item no catálogo.

## Discovery e decisões

Revisados os fluxos existentes `/conectores`, `/conectores/financeiro`, `/importar`, `/importacoes`, `/disparos/importacoes` e o app shell. O Smart Import atual já possui preview, mapeamento e confirmação idempotente. Não criar segundo importador nem reimplementar ações de integrações.

Capturas fornecidas da Attio: densidade reduzida, navegação hierárquica, divisões por contexto, ações discretas, painéis claros. A interface MIRA é original, respeita `#FFFFFF`, `#F8F9FA`, bordas `#E6E7EA`, texto `#101112`, azul `#266DF0`, ícones Untitled UI.

## Entregue

- `/dados`: hub com seis seções e navegação local — visão geral, conexões, explorar integrações, importações/histórico, qualidade de dados e configurações.
- Visão geral: contagem do **catálogo de conectores**; **somente** conexões nativas JACAD/Sponte configuradas; erros verificados nessas conexões; amostra dos últimos 30 uploads. Valores indisponíveis não são apresentados como zero.
- Conexões: estados separados `não configurado`, `desativado`, `configurado`, `autenticado`, `sincronizando`, `sincronizado`, `erro` e `desconectado`, conforme campos reais das duas APIs de conexão. Erros de consulta são diferentes de ausência de configuração.
- Catálogo: dados de `GET /api/v1/connectors`, busca por nome/categoria/descrição, categorias descritivas. Estar no catálogo **não** equivale a estar conectado.
- Importações: histórico `GET /api/v1/upload/history`; quando autorizado por `campaigns.view`, histórico `GET /dispatch/composio/imports`. Fontes não relacionadas não são ligadas artificialmente. Detalhe mostra identificador, estado bruto normalizado apenas para UI, horários, contagens e falha conhecida.
- Qualidade: somente falhas de upload, processamento parcial em lotes concluídos e falhas de sincronização explicitamente registradas. Não inventa um score de qualidade ou uma leitura de completude institucional.
- Acesso direto aos fluxos existentes: configurar conexão, importação inteligente e histórico detalhado.
- Sidebar: uma entrada `/dados` condicionada a `data.view`, sem excluir as rotas legadas.
- Testes unitários de classificação de estados, impossibilidade de inferência de conectividade, detecção de problemas e ausência de mutações no hub.

## Contratos e autorização

| Capacidade | Contrato atual | Segurança | Na Wave |
|---|---|---|---|
| Catálogo nativo | `GET /api/v1/connectors` | `data.view` | leitura |
| JACAD | `GET /api/v1/integrations/jacad` | autorização backend | leitura |
| Sponte | `GET /api/v1/integrations/sponte` | autorização backend | leitura |
| Uploads | `GET /api/v1/upload/history` | `data.view` | leitura |
| Importações Composio | `GET /dispatch/composio/imports` | `campaigns.view` | leitura condicional |
| Smart Import | `/importar` e APIs atuais | `data.import` + confirmação | reutilizado, não duplicado |
| Configuração nativa | `/conectores` | RBAC, autenticação própria | reutilizada |
| Financeiro | `/conectores/financeiro` | controles atuais | permanece no módulo |
| Mapeamento de objetos | configurações específicas atuais | servidor é autoridade | somente link/descrição |
| Execução Composio | policy engine / allowlists | aprovação específica | indisponível neste hub |

**Multi-tenant:** todas as queries usam a sessão atual, são condicionadas a `data.view`, e suas query keys incluem `tenant_id`. A segurança real depende do backend e de políticas RLS existentes, não da interface. O catálogo é diferente da lista de instâncias de conexão; **não criar unicidade de conexão por workspace**.

## Limitações honestas

- Os contratos atuais não oferecem um índice universal de todas as conexões, sincronizações ou proveniência de dados do workspace. A amostra JACAD/Sponte não representa todos os conectores.
- O histórico de upload é paginado e a visão usa os 30 registros mais recentes. A ausência de falhas nessa amostra não comprova qualidade de dados integral.
- No histórico Composio não é possível inferir integração com campanhas específicas nem execução de ferramenta externa. Erros potencialmente sensíveis não são renderizados literalmente.
- Não há operação para selecionar/editar ferramentas Composio, configurar mapeamentos globais ou repetir uma importação neste hub.
- Não houve novo endpoint, tabela, migration, mudança de provedor ou execução operacional.
- QA de navegação autenticada só deve ser marcado completo com evidência de ambiente e usuários de teste.

## Gate de release

1. ESLint, `node --test`, TypeScript e Next.js build no HEAD.
2. CI backend de regressão, pytest/PostgreSQL/RLS e Alembic.
3. Confirmar que o diff não contém chamadas `POST/PUT/PATCH/DELETE` para imports, dispatch, ferramentas ou pagamentos.
4. Inspecionar compatibilidade com a versão Alembic realmente publicada, e confirmar ausência de uma migration nova.
5. Fazer merge normal somente após checks verdes e ausência de incompatibilidade conhecida.
6. Verificar qualquer deploy automático resultante sem confundir merge com publicação ou health de produção.

## Próxima Wave — 0.5 Dispatch & Campaign Operations

Discovery: consolidar campanhas, público/segmentos, modelos, canais/provedores, aprovações, agendamentos, filas, execuções, webhooks e resultados no motor existente. Reusar `dispatchApi`, contratos de propostas de permanência e `Workflow Experience`. Não implementar outro motor nem executar/envia mensagens reais em testes. Tratar `approved`, `scheduled`, `running`, `completed` e resultados por contratos específicos, sem equivalências falsas.
