# Integração SophiA (Prima) — dossier técnico e plano de homologação

**Status:** descoberta técnica iniciada; implementação da API bloqueada até receber a documentação da instalação/versão da instituição.  
**Branch:** `feat/sophia-native-integration`  
**Modo previsto:** somente leitura.

## 1. Identificação do produto

O nome SophiA é usado em mais de um produto/módulo. Este dossier trata do ERP acadêmico **SophiA Gestão Escolar Web**, da Prima, e não presume compatibilidade com SophiA Biblioteca Web/Philos.

A instituição precisa confirmar:
- produto e edição exatos (Gestão Escolar Web, versão/build);
- URL/base URL da instalação;
- versão e disponibilidade do módulo Web API;
- módulos/recursos licenciados e habilitados;
- documentação técnica correspondente à instalação.

## 2. Evidências públicas e limites

### Confirmado por fontes públicas
- O site oficial da SophiA descreve um ecossistema com APIs RESTful/Web Services e processo de avaliação/homologação técnica de parceiros.
- A documentação pública de integração da Agenda Edu para SophiA Gestão Escolar informa que o módulo API deve ser habilitado pelo fornecedor e que a instituição disponibiliza URL, usuário e senha da integração.
- O repositório MIRA já contém um transformer legado `SophiaConnector` em `backend/app/services/connectors/erp.py`, com aliases de campos como `cod_aluno`, `nome`, `curso`, `serie`, `media`, `frequencia` e `vl_atraso`. Esses aliases são apenas heurísticas históricas; **não são um contrato oficial nem evidência de que os endpoints retornem esses campos**.

### Ainda não confirmado
Não há documentação pública oficial consultada que permita afirmar, para a versão de Gestão Escolar Web da instituição:
- rotas e métodos exatos para alunos, matrículas, cursos, turmas, notas, frequência ou financeiro;
- formato de autenticação, token, expiração/renovação e escopos;
- parâmetros e mecanismo de paginação;
- filtros incrementais, ordenação ou timestamps por campo;
- limites de requisição, quotas ou política de retry;
- semântica de situação financeira, parcelas, notas, frequência e status acadêmicos.

**Não implementar chamadas com endpoints presumidos.** A documentação pública encontrada para SophiA Biblioteca Web/Philos pertence a outro produto e não deve ser reutilizada como contrato da API do ERP.


## 2A. Descoberta adicional: guia público da API Web v1

Foi localizado um documento intitulado **“API Web de Integração do SophiA — Versão 1.0”**, publicado em uma plataforma de terceiros (Scribd), não no domínio oficial da Prima. Ele descreve especificamente SophiA Gestão Escolar Web e exige que o módulo Web API esteja habilitado. É uma evidência técnica útil para discovery, mas não deve ser tratado como documentação oficial atual nem como prova de compatibilidade com a instalação de qualquer cliente.

### O que o guia v1 descreve

- API REST, com payloads e respostas em JSON ou XML.
- Cabeçalhos `User-Agent`, `Host`, `Content-Type`, `Accept` e `Token`.
- Autenticação `POST /Autenticacao/PostAutenticacao`, com usuário e senha de integração.
- Token atrelado ao endereço IP do equipamento que o solicitou; o token é renovado a cada requisição e expira após 20 minutos sem uso.
- Recursos documentados incluem:
  - `GET /Unidade/GetUnidades`
  - `GET /Curso/GetCursos`
  - `GET /FichaFinanceira/GetFichaFinanceira?codigo={codigo}`
  - `GET /Nota/ListarNotasRecentes?codigo={codigo}`
  - `GET /Boletim/GetFiltroBoletim?codigo={codigo}`
  - `GET /Aviso/GetAvisos`
  - além de recursos de boleto, calendário, campanhas, prospectivos e autenticação de pessoa.
- A ficha financeira retorna itens com `IdTitulo`, `DataPagamento`, `DataVcto`, `Pago`, `ValorPago` e `ValorPrevisto`; datas usam o formato legado Microsoft JSON Date.
- Notas recentes incluem disciplina, etapa, turma, descrição e nota; o exemplo contém valores sentinela como `-1` e notas em string com vírgula decimal, que exigem parsing e semântica validados.

### Limitação decisiva para a MIRA

O guia v1 encontrado **não documenta um endpoint de listagem/exportação de todos os alunos nem de matrículas**. As chamadas de boletim, notas e ficha financeira dependem de um `codigo` interno do aluno. O documento também não descreve paginação ou sincronização incremental.

Portanto, não é correto implementar uma carga institucional em massa com base apenas nesse guia. A autenticação IP-bound também exige que autenticação e chamadas subsequentes saiam pelo mesmo IP público estável; não podemos compartilhar tokens entre workers com egressos diferentes.

**Conclusão técnica:** o guia v1 permite projetar um adaptador read-only para consultas pontuais por código interno, mas não comprova que a API seja suficiente para o caso de uso de sincronização institucional da MIRA. Precisamos confirmar se existe API de integração/extração mais recente ou endpoints adicionais habilitados no produto/versão da instituição.

Fonte secundária localizada: https://pt.scribd.com/document/592604325/Integracao-API-Web (50 páginas; “API Web de Integração do SophiA”, versão 1.0). Não reproduzir nem incorporar o documento integral ao repositório.

## 3. Fontes consultadas

1. SophiA — Parcerias e Integrações (site oficial): https://sophia.com.br/integracoes/
   - Descreve APIs RESTful/Web Services e avaliação técnica de parceiros.
2. Agenda Edu — Como habilitar a integração SophiA <> Agenda Edu:
   https://atendimento.agendaedu.com/hc/pt-br/articles/11104377528987-Como-habilitar-a-integra%C3%A7%C3%A3o-SophiA-Agenda-Edu
   - Orienta habilitar o módulo API e obter URL, login e senha na área de integrações. Fonte de terceiro; útil para requisitos operacionais, não para definir o contrato da API.
3. Agenda Edu — Como solicitar a integração:
   https://atendimento.agendaedu.com/hc/pt-br/articles/12935986823067-Como-solicitar-a-integra%C3%A7%C3%A3o-do-sistema-de-gest%C3%A3o-SophiA-com-a-Agenda-Edu
   - Confirma dependência do módulo API, credenciais e parametrização com a instituição.
4. Guia “API Web de Integração do SophiA”, versão 1.0, cópia em plataforma de terceiros: https://pt.scribd.com/document/592604325/Integracao-API-Web
   - Evidência secundária de uma API REST v1, autenticação IP-bound e recursos pontuais. Não comprova compatibilidade atual nem cobertura de exportação em massa.
5. Repositório MIRA — `backend/app/services/connectors/erp.py`
   - Transformer legado; não representa documentação oficial do fornecedor.

## 4. Pacote necessário para homologação

Solicitar à instituição/Prima por canal seguro:
- documentação da API da **mesma versão** instalada;
- URL de base e ambiente (produção/homologação, se houver);
- mecanismo de autenticação e processo de rotação/revogação;
- usuário técnico dedicado, somente leitura, com escopo mínimo;
- lista de módulos/recursos autorizados;
- exemplos sanitizados de request/response para cada recurso;
- política de paginação, filtros, limites, timeout e erros;
- confirmação do fuso horário e semântica dos timestamps;
- dicionário de dados e regras de negócio para status acadêmico/financeiro;
- confirmação formal de que a conta pode consultar dados necessários à MIRA.

Não enviar senha ou token em issue, PR, chat, log ou arquivo versionado. Credenciais reais serão cadastradas apenas pelo fluxo seguro da MIRA após implementação e revisão.

## 5. Contrato de dados a validar

| Domínio | Dados desejados | Condição para mapear |
|---|---|---|
| Identidade | código do aluno, matrícula/RA, nome | chave estável e escopo da instituição confirmados |
| Vínculo | matrícula, curso, turma, unidade/campus, período, status | distinguir aluno de matrícula e múltiplos vínculos |
| Financeiro | parcelas, vencimento, valor, situação, pagamentos | estados documentados; não inferir pago/aberto por ausência |
| Frequência | aulas previstas, presentes/faltas, disciplina, período | denominador e granularidade confirmados |
| Desempenho | avaliações/notas, escala, disciplina, período | pesos, escala e agregação confirmados |
| Acesso | último login/evento | timestamp e definição do evento explicitamente fornecidos |

Todos os campos devem preservar valor bruto, origem e proveniência. Ausência de dado permanece desconhecida; não preencher com zero ou valor favorável.

## 6. Arquitetura prevista (após validação do contrato)

- Uma conexão por tenant, com credenciais cifradas no backend.
- URL HTTPS validada e protegida contra SSRF; redirects desabilitados.
- Cliente HTTP assíncrono com timeout, limites configuráveis, retry seletivo e respeito a `Retry-After`.
- Teste de conexão que valida autenticação e acesso mínimo aos recursos habilitados, sem baixar uma base completa.
- Worker Redis com jobs assíncronos, checkpoints persistidos após gravação, retomada e idempotência.
- Watermark independente por recurso somente se a API oferecer filtro incremental confiável.
- Isolamento por tenant no backend e no banco (RLS/FORCE RLS, conforme padrão atual).
- Segredos nunca retornados à UI ou registrados em logs.
- Escrita na API do fornecedor proibida.

## 7. Sequência de implementação

1. **Discovery/homologação:** obter contrato oficial e exemplos sanitizados da instalação real.
2. **Contrato e testes de fixture:** validar paginação, autenticação, schemas e semântica com payloads sem dados pessoais.
3. **Backend:** cliente somente leitura, criptografia de credenciais, modelo/configuração por tenant, migration RLS, rotas de teste e sync.
4. **Pipeline:** mapeamento canônico, proveniência por campo, fila/checkpoints, limites e retomada.
5. **Frontend:** configurar conexão, testar, exibir cobertura/progresso e erros seguros.
6. **Validação:** testes unitários, integração simulada, isolamento multi-tenant, CI e revisão de segurança.
7. **Homologação real:** sync controlada de pequeno volume, conferência de contagens e semântica com a instituição.
8. **Ativação:** somente após revisão; não habilitar scoring automaticamente.

## 8. Critérios de aceite

- Endpoints e schemas vêm da documentação da versão homologada, sem suposições.
- Conexão e sincronização são isoladas por tenant.
- Segredos cifrados e nunca expostos.
- Sync somente leitura, paginada, retomável e idempotente.
- Nenhum truncamento silencioso quando a paginação falhar.
- Dados desconhecidos/inválidos não são convertidos em valores favoráveis.
- Proveniência e timestamps de observação são preservados; horário de importação não substitui observação.
- Testes cobrem autenticação, erros, rate limit, paginação, checkpoint, retry, tenant isolation e mapeamento.
- Scoring permanece desabilitado para atributos não homologados.

## 9. Próxima dependência externa

A implementação do cliente real depende de receber a documentação técnica e exemplos sanitizados da API SophiA Gestão Escolar Web usada por uma instituição. Até lá, esta branch contém apenas o dossier e não deve criar credenciais, migrations, endpoints presumidos ou sincronizações reais.


## 10. Relatórios e extração operacional

A documentação pública oficial de suporte do SophiA Gestão Escolar descreve relatórios que podem ser gerados pela interface:

- **Alunos por turma:** acessar Turmas, usar Busca avançada para filtrar período/situação, selecionar as turmas, abrir Relatórios e escolher “Alunos da turma”. A documentação orienta visualizar o relatório.
  Fonte: https://suporte.sophia.com.br/bc/SG/SEIW/comoimprimirarelacaodealunosporturma.htm
- **Matrículas e rematrículas por período:** acessar Relatórios > Acadêmico > “Matrículas e rematrículas por período”, parametrizar e visualizar; o tipo distingue matrícula nova de rematrícula.
  Fonte: https://suporte.sophia.com.br/bc/SG/SEIW/como_imprimir_a_relacao_de_mat.htm
- **Planilha acadêmica:** relatório flexível por turma, com seleção de campos por aluno e disciplina. A documentação lista média, média final, faltas, percentual de faltas, presenças, percentual de frequência, situação acadêmica, aulas dadas e tarefas. O fluxo documentado termina em “Visualizar”.
  Fonte: https://suporte.sophia.com.br/bc/SG/SEIW/como_imprimir_a_planilha_acade.htm

### O que isso comprova — e o que não comprova

Comprova que a interface possui relatórios operacionais para consultar alunos por turma, matrículas/rematrículas e dados acadêmicos. Não comprova:
- exportação nativa CSV/XLSX desses relatórios;
- execução agendada ou entrega automática;
- extração consolidada de todas as turmas/períodos em um único arquivo;
- presença de uma chave estável de matrícula em todos os relatórios;
- disponibilidade dos campos financeiros detalhados em exportação;
- mecanismo de delta/alterações desde a última extração.

**Decisão:** considerar relatórios como caminho de discovery para uma carga inicial assistida, mas não prometer automação ou tratar PDF/relatório impresso como contrato de dados. Antes de construir um adaptador, é necessário confirmar no produto instalado se o relatório pode ser exportado em formato tabular (CSV/XLSX) e quais colunas/chaves são selecionáveis. Se só houver impressão/PDF, isso não atende sozinho ao requisito de ingestão recorrente confiável.

## 11. Auditoria do pipeline de importação MIRA

A inspeção do código da branch `main` identificou que o pipeline genérico atual já aceita CSV, XLS e XLSX, detecta abas, permite mapeamento manual de colunas e oferece prévia sem persistência antes da confirmação. A importação individual usa os campos canônicos definidos em `backend/app/services/ingestion.py`; matrícula e nome são obrigatórios, e os demais campos são opcionais. A prévia informa correspondências existentes e a persistência atualiza registros pela matrícula, preservando valores existentes quando as células recebidas estão vazias.

Arquivos inspecionados:
- `frontend/src/components/import/ImportWizard.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/types/api.ts`
- `backend/app/api/upload.py`
- `backend/app/services/ingestion.py`
- `backend/app/services/connectors/base.py`

### Campos canônicos que podem receber relatórios SophiA

| Campo MIRA | Evidência potencial no relatório SophiA | Condição |
|---|---|---|
| `matricula` | código/RA do aluno | confirmar identificador e estabilidade |
| `nome` | nome do aluno | confirmar presença e cabeçalho |
| `curso` | curso | confirmar se o relatório selecionado inclui |
| `turma` | turma | confirmar formato e cardinalidade |
| `status_aluno` | situação acadêmica | mapear apenas após validar os valores reais |
| `nota_media` | média/média geral | confirmar escala, etapa e agregação |
| `presenca_percentual` | percentual de frequência | confirmar denominador e período |
| `reprovacoes` | não comprovado nos relatórios consultados | não inferir a partir de situação acadêmica |
| campos financeiros | não comprovados nos relatórios consultados | requer relatório financeiro próprio e dicionário de dados |
| `dias_sem_login` | não comprovado nos relatórios consultados | requer evento/timestamp de acesso definido |

O importador possui aliases de cabeçalho e permite mapeamento manual, mas isso não resolve diferenças semânticas. Em especial, a planilha acadêmica permite selecionar dados por aluno e disciplina; não se deve importar uma média por disciplina como se fosse média geral do estudante sem regra de agregação confirmada.

### Inconsistência encontrada no fluxo de múltiplos arquivos

Na versão inspecionada de `main`, a UI oferece os papéis `academico`, `historico` e `matriculas`, mas o backend de prévia/confirmação múltipla aceita papéis diferentes (`cadastro`, `alunos`, `financeiro`, `engajamento`, `desempenho`; a prévia também contém `cursos`). Portanto, selecionar alguns papéis apresentados na UI pode resultar em “tipo de base desconhecido”. A lista de papéis da prévia e da confirmação também não é idêntica.

Esse ponto precisa ser corrigido e coberto por testes antes de recomendar a importação multi-arquivo para um pacote SophiA. Não foi alterado nesta PR de discovery.

### Recomendação de ingestão para SophiA

1. Preferir um único CSV/XLSX tabular de cadastro/matrículas com uma linha por vínculo de matrícula, desde que a chave seja estável e a cardinalidade seja definida.
2. Usar o importador individual existente para a primeira prova de conceito, com prévia, mapeamento explícito e scoring automático desabilitado até a homologação dos atributos.
3. Importar financeiro, frequência e desempenho como bases complementares somente depois de definir a chave de junção, granularidade temporal e regras de consolidação.
4. Não usar nomes como chave de junção; não colapsar múltiplas matrículas de um mesmo aluno sem regra de negócio aprovada.
5. Não tratar ausência de coluna/valor como zero, presença, aprovação ou adimplência.
6. Manter origem, arquivo, período de referência e data de extração rastreáveis. Uma nova carga deve ser comparada com a anterior antes de substituir atributos.

**Conclusão do pipeline:** MIRA já possui um caminho de importação manual estruturado que pode servir como ponte para SophiA, mas a extração tabular do fornecedor e a consistência do modo multi-arquivo ainda precisam ser comprovadas/corrigidas. Não é necessário criar um segundo importador SophiA antes de testar o formato real exportado.
