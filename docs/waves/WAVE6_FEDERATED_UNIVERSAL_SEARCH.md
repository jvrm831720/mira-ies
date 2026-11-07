# MIRA — Wave 6: Busca Universal federada

## Produto e escopo

A Command Palette existente (**Ctrl/Cmd+K**) agora consulta a API federada e integra cinco providers de objetos e a navegação já autorizada no sidebar:

| Provider | Origem do servidor | Projeção de resposta | Destino |
|---|---|---|---|
| Alunos | `Student` | id, nome, matrícula e curso | `/alunos/{id}` |
| Casos financeiros | `dispatch_obligations` | id, referência, estado de origem | `/cobranca/casos/{id}` |
| Meu Trabalho | `WorkActivity` | id, título e estado humano | `/trabalho?activity={id}` (apenas inspeção) |
| Views | `ObjectView` | id, nome, domínio e escopo | Índice de objeto com `saved_view={id}` |
| Campanhas | `RetentionCampaignProposal` | id, título, revisão e estado | `/campanhas?proposal={id}` (somente inspeção) |
| Páginas | Menu filtrado por permissão, perfil, módulo e feature | label e rota | Rota autorizada |

**Não substitui os endpoints existentes.** A busca não grava cópias de registros, configurações de view, embeddings ou payloads sensíveis. O portal do aluno e o Control Center interno não participam do catálogo federado.

## Contrato API

`GET /api/v1/search?q=termo&per_provider=5`

- Exige **sessão humana válida**; chave de integração não pode consultar o índice agregado.
- 2–80 caracteres para a consulta; limite 1–6 por provider.
- Retorna `results`: apenas `provider`, `id`, `title`, `subtitle`, `href`, `rank`, `match` e `action=navigate`.
- `providers` representa apenas providers efetivamente autorizados, `unavailable` contém fontes autorizadas com erro, `partial=true` explicita consulta incompleta.
- `count_scope=bounded_matches`: **não apresenta total global** ou promete cobertura exaustiva.
- Consultas são tenant-scoped com filtros SQL bindados e RLS existente. Cada provider usa SAVEPOINT isolado, timeout SQL local de 400 ms, teto 24 candidatos exatos e 80 candidatos aproximados. No máximo 30 resultados agregados.
- Campos sensíveis (risco, SHAP, telefone, e-mail, dívida, regras de campanhas e JSON das views) **não são projetados**.
- O provider de views respeita dono ou escopo workspace, `is_sensitive`, grant de domínio e RLS com `app.view_sensitive`.
- Trabalho humano exige `students.view`, `students.edit` e acesso operacional (cargos embutidos operator+ ou concessões explícitas); casos financeiros exigem `audit.view`; propostas de campanhas exigem coordenador/admin em cargos embutidos ou `campaigns.view` efetivo em cargos personalizados, igual ao endpoint real.
- Exceções não entram no payload da resposta. Falha em um provider não impede os demais.
- Ordenação lexical: exata, prefixo, contém e similaridade com Python `SequenceMatcher`; nenhuma probabilidade de cobrança, evasão ou envio é inferida.
- Busca aproximada é **best effort** dentro de candidatos SQL restritos ao tenant, baseados nos dois primeiros caracteres. Não é busca fonética ou varredura global. Um registro antigo fora do teto de candidatos pode não aparecer. Não foi incluída extensão no PostgreSQL ou migration.

## Segurança da interface

O cliente exige Bearer Token (não aceita API key na busca), cancela requests antigos e diferencia resultados por `provider:id`. Compara URLs recebidas com um **allowlist exato** de formatos e com as rotas que o sidebar já autoriza naquele workspace. URLs externas, fragments, parâmetros de ação, IDs não UUID e caminhos de outros módulos são descartados antes de mostrar a opção.

As teclas existentes continuam funcionais: Ctrl/Cmd+K, ↑/↓, Enter, Escape e Tab/focus trap. A expansão da atividade abre somente a inspeção autorizada do Meu Trabalho. Resultados de campanhas navegam para a lista; **não aprovam, executam ou disparam campanhas**. A interface mostra fontes parciais sem transformar prévias em totais.

## Limitações declaradas

- A busca consulta propostas de campanhas de permanência realmente exibidas em `/campanhas`, não as regras legadas de `RetentionCampaign`; campanhas de dispatch são um domínio separado e não têm provider nesta wave.
- Views dos objetos com uma rota sem resolver a view diretamente podem abrir o índice de domínio sem aplicar automaticamente a configuração. Views de alunos e cobrança usam o parâmetro `saved_view` suportado.
- Resultados aproximados não são completos quando o tenant tem mais registros compatíveis que o limite de candidatos; se necessário, uma wave posterior poderá introduzir índice trigram após homologação do banco.

## Testes e aceitação

- `backend/tests/test_universal_search_wave6.py`: dois tenants, concessões RBAC, sessão humana obrigatória, projeções mínimas, cinco domínios, erro parcial, consultas aproximadas, escapes SQL e limites.
- `frontend/tests/universal-search-wave6.test.mjs`: contrato executável de URLs (incluindo URLs maliciosas), navegação autorizada, teclado, cancelamento, deep links e ausência de mutações.
- CI separado para teste focado, seguido do pytest completo, Ruff, lint/TypeScript/build frontend e capturas visuais.
- QA autenticado: testar viewer, operador, coordenador, cargo personalizado e dois workspaces. Repetir consulta com fonte indisponível e verificar degradação sem dado sensível ou contagem falsa.
- Falha no Cloudflare Workers Builds exige homologação independente; merge de código não comprova deploy.

Sem migrações de dados, alterações de RLS ou execução financeira nesta wave.
