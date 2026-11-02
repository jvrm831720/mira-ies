# Dossier técnico — integração nativa JACAD

**Status:** primeira implementação da conexão de leitura (pull), pendente de homologação com credenciais reais de uma instituição.  
**Referência consultada:** documentação pública SWA.JACAD, API REST (documentação geral 3.1.61.060; a página acadêmica pode exibir versão de módulo diferente).  
**Base de documentação:** https://auden-developer.jacad.com.br/docs

## 1. Visão geral

A MIRA conecta-se diretamente à API REST do ambiente JACAD da instituição. O cliente informa o endereço HTTPS do ambiente e um token de acesso criado no módulo **Integrações → API de Integração → Tokens de Acesso** do JACAD.

A integração inicial é somente leitura. A MIRA não cria nem altera alunos, matrículas, contratos, boletos, notas ou frequências no JACAD.

## 2. Autenticação

1. A instituição cria um token de acesso no sistema JACAD.
2. A MIRA envia `POST /api/v1/auth/token`, com a chave no header `token`.
3. A API devolve um JWT no campo `token` e o prazo em `expiresIn`.
4. As chamadas seguintes enviam `Authorization: Bearer <JWT>`.

A chave de acesso documentada tem limite de 40 caracteres. O JWT não é persistido pela MIRA. A chave de acesso é cifrada antes de ser gravada no banco. O valor original nunca é devolvido pela API da MIRA nem escrito em logs.

**Permissões:** o token JACAD deve ter apenas os módulos e operações de consulta necessários. A disponibilidade dos endpoints depende das permissões do usuário/token e dos módulos contratados pela IES.

## 3. Recursos oficiais relevantes

| Recurso | Endpoint documentado | Uso na MIRA |
|---|---|---|
| Autenticação | `POST /api/v1/auth/token` | Obter JWT |
| Alunos | `GET /api/v2/academico/alunos` | Identidade, RA, nome, e-mail, organização e datas de cadastro/alteração |
| Matrículas | `GET /api/v2/academico/matriculas` | Situação, aluno, RA, curso, turma e período letivo; consulta paginada por cursor |
| Notas | `GET /api/v1/academico/notas/consultar` | Notas por turma e disciplina do professor; exige identificadores de turma e disciplina |
| Resumo financeiro por matrícula | `GET /api/v2/financeiro/matriculas/resumo-financeiro` | Situação consolidada, contrato entregue, próxima parcela em aberto; exige `idOrg` |
| Contratos de matrícula | `GET /api/v1/financeiro/contratos-matricula` | Relação de contratos por aluno/matrícula; paginação `currentPage` |
| Parcelas do contrato | `GET /api/v1/financeiro/contratos-matricula/{idContrato}/parcelas` | Detalhe de vencimento, valor, valor pago e situação de cada parcela |

Documentação consultada:
- Autenticação: https://auden-developer.jacad.com.br/docs/auth
- Acadêmico: https://auden-developer.jacad.com.br/docs/academico
- Financeiro: https://auden-developer.jacad.com.br/docs/financeiro

## 4. Paginação e limites

A consulta v2 de alunos documenta `pageSize` até 5.000 e retorna um objeto `page` com `idCursor` e `idCursorProximo`. A implementação usa o cursor retornado para continuar a leitura, com limite defensivo de páginas e registros para evitar loops ou sincronizações ilimitadas.

Outros recursos documentam paginação por `currentPage` e `pageSize`; os limites variam por endpoint (há endpoints v1 com máximo 500). Cada recurso deve respeitar o limite publicado em sua própria documentação. O endpoint v2 de alunos aceita `idCursor` (inicia em 0) e a resposta devolve `idCursorProximo`. A documentação também informa limite técnico de 10 requisições por segundo por IP e quota horária por token (o exemplo padrão é 1.000 requisições por hora, sujeito à configuração da instituição). O worker usa concorrência limitada, um limitador Redis compartilhado de até 9 requisições por segundo por IP e uma margem conservadora de 900 requisições por token em janela móvel de uma hora. Ao atingir a quota conservadora, o job é pausado e retomado após a janela, sem consumir uma tentativa de falha.

## 5. Mapeamento acadêmico e financeiro

A sincronização agora consulta três conjuntos de dados em sequência: cadastro de alunos, matrículas e resumo financeiro por matrícula. O `idOrg` é obrigatório para a sincronização completa porque o endpoint financeiro exige esse filtro.

| Campo JACAD | Campo canônico MIRA | Regra |
|---|---|---|
| `ra` | `matricula` | Preferido como identificador externo |
| `idAluno` | `matricula` | Fallback técnico quando RA não existe |
| `nome` | `nome` | Obrigatório para ingestão |
| `email` | `email` | Opcional |
| `dataAlteracao` | — | Data de alteração do registro, não é observação de cada atributo |
| Matrículas: `idMatricula`, `idAluno`, `status`/`statusMatricula`, `curso`, `turma`, `periodoLetivo`, `idPeriodoLetivo`, `matriz`, `idCursoMatriz`, `unidadeFisica`, `idUnidadeFisica`, `dataMatricula`, `dataAtivacao`, `dataTrancamento`, `idContrato`, `contratoEntregue` | `status_aluno`, `curso`, `turma` + metadados acadêmicos | Junta por `idAluno` (fallback RA); prioriza matrícula `ATIVA`; preserva o contexto adicional em `raw_data.jacad.matriculas` |
| Resumo: `situacaoFinanceira` | `status_financeiro` | Apenas os estados documentados: `VENCIDO`, `EM_ABERTO`, `PAGO`, `SEM_FINANCEIRO` |
| Resumo: `dataVencimentoParcela` | `dias_atraso_boleto` | Só calcula quando `situacaoFinanceira=VENCIDO`; diferença entre data atual da sincronização e vencimento da parcela aberta de menor vencimento |
| Resumo: `statusContrato`, `contratoEntregue`, `valorParcela` | Metadado de origem | Situação/entrega do contrato e valor da parcela aberta de menor vencimento; ficam em `raw_data.jacad` e não alimentam saldo total |

O identificador interno JACAD deve ser preservado no payload bruto. Não substituir o RA por `idAluno` quando o RA existir.

### Metadados acadêmicos adicionais

A sincronização também preserva, por matrícula, o contexto que a API entrega: período letivo, matriz curricular, unidade física/campus, datas de matrícula/ativação/trancamento, ID do contrato e indicador de entrega do contrato. Esses atributos ficam em `students.raw_data.jacad.matriculas`; não são convertidos em indicadores preditivos sem uma regra de negócio validada.

## 6. Limites semânticos e confiabilidade preditiva

O cadastro de alunos e o resumo financeiro enriquecem a cobertura, mas não fornecem, por si só, os sete atributos preditivos obrigatórios da MIRA.

- `dataAlteracao` descreve alteração do registro; não prova quando cada campo foi observado.
- `dataCriacao` não representa último acesso.
- A lista de alunos não prova dias sem login, frequência, média, reprovações ou recorrência de atraso. O resumo financeiro fornece evidência para situação financeira e, quando vencido, para calcular dias desde o vencimento da parcela aberta mais antiga informada.
- O resumo financeiro por matrícula é uma evidência explícita de situação (`VENCIDO`, `EM_ABERTO`, `PAGO`, `SEM_FINANCEIRO`) e da próxima parcela em aberto. O detalhe de parcelas expõe vencimento, valor, valor pago e situação.
- Não inferir recorrência de atraso a partir de um resumo consolidado: a contagem histórica precisa ser derivada de parcelas/transações com regras de cancelamento, renegociação e baixa confirmadas.
- Notas e resultados por disciplina são consultados e preservados por turma, disciplina e período; ainda exigem regra institucional para agregação por aluno.
- A frequência reportada por disciplina é preservada, mas sua escala e regra de consolidação precisam ser homologadas. Acesso/último login ainda exige uma fonte de leitura específica.

Portanto, o primeiro sync não inventa valores preditivos nem gera score automático. Campos sem evidência permanecem desconhecidos e o motor de risco continua sujeito ao bloqueio de cobertura/frescor da Wave 3.

## 7. Estratégia de sincronização

### Primeira carga e sincronização completa
- A API responde imediatamente com um ID de job; o processamento ocorre em segundo plano no worker Redis já usado pela MIRA.
- Consulta paginada de alunos, matrículas e resumo financeiro por matrícula (v2).
- Consulta dos detalhes de parcelas por contrato, em lotes com concorrência configurável e limitada.
- Descoberta das disciplinas por turma e consulta em lote das matrículas-disciplina por código de disciplina do professor. Isso evita uma chamada por matrícula.
- Consulta das notas por avaliação uma vez por combinação única de turma e disciplina do professor.
- Persistência incremental por lote. O checkpoint só é marcado depois do commit no banco; se uma chamada falhar, a retomada pula os itens já persistidos.
- Checkpoints de contratos, disciplinas e avaliações ficam no Redis por até sete dias. O job também expõe etapa, percentual, contadores, erro e resultado.
- Retry automático com backoff para falhas transitórias e retomada manual do último checkpoint após falha definitiva.
- Limitador distribuído no Redis respeita a quota por IP e aplica margem conservadora à quota horária por token.
- Preservação seletiva dos campos financeiros e acadêmicos em `students.raw_data.jacad`; não armazena payload integral.
- Proveniência registra `source_type=jacad_api` e horário de importação. Como `dataAlteracao` não é timestamp de observação por campo, `observed_at` permanece desconhecido.
- Score automático permanece desabilitado.

### Incremental
A API documenta filtros de alteração em alguns recursos, como `dataAlteracaoInicio`/`dataAlteracaoFim` em alunos e matrículas. A implementação inicial ainda faz leitura paginada completa. O incremental será habilitado somente depois de homologar o comportamento do cursor e dos filtros de alteração no ambiente real da IES.

### Reconciliação e exclusões
A primeira versão não desativa alunos ausentes de uma resposta nem interpreta ausência como exclusão. Exclusões, transferências e status de matrícula precisam ser reconciliados com endpoint e regra específicos.

### Frequência operacional
A sincronização é iniciada sob demanda e executada pelo processo `PYTHONPATH=. python -m app.worker`. O worker deve estar ativo no ambiente de execução; caso contrário, o job permanece na fila. O estado e os checkpoints são mantidos no Redis por até sete dias. A sincronização incremental por data de alteração e o agendamento periódico ainda dependem de homologação da cadência e dos filtros do ambiente real.

## 8. Segurança

- HTTPS obrigatório.
- Somente hosts sob `.jacad.com.br` são aceitos nesta versão.
- Redirects HTTP desabilitados.
- Credenciais cifradas em repouso com chave derivada do segredo de aplicação.
- Isolamento por tenant em tabela própria com RLS.
- Endpoints de configuração, teste e sync exigem papel de coordenador ou administrador.
- Respostas e logs não expõem token ou JWT.

## 9. Recursos adicionais identificados e decisão de escopo

A expansão já consulta esses recursos em segundo plano:
- **Parcelas por contrato:** `GET /api/v1/financeiro/contratos-matricula/{idContrato}/parcelas`. Os campos `idTransacao`, `valor`, `valorPago`, `situacao`, `dataVencimento` e `dataPagamento` são preservados em `raw_data.jacad.installments_by_contract`. A MIRA ainda não converte `situacao` em estados financeiros canônicos nem calcula saldo/recorrência sem homologar cancelamento, renegociação, baixa e estorno.
- **Disciplinas de turma:** `GET /api/v1/academico/turmas/{idTurma}/disciplinas` descobre os códigos `idDisciplinaProfessor`. A consulta `GET /api/v1/academico/disciplinas/{idDisciplinaProfessor}/matriculas` retorna em lote os estudantes da disciplina e campos como `mediaFinal`, `notaFinal`, `notaExame`, `frequencia`, `quantAulas` e `quantFaltas`. Esses registros ficam em `raw_data.jacad.academic_disciplines_by_class_discipline`.
- **Notas por avaliação:** `GET /api/v1/academico/notas/consultar` é consultado por combinação única de turma e disciplina do professor. `mediaMatriculaDisciplina`, status e `itensNotas` ficam em `raw_data.jacad.assessment_notes_by_class_discipline`.
- **Frequência:** o campo `frequencia` e as quantidades de aulas/faltas são preservados por disciplina, mas não são convertidos em `presenca_percentual` enquanto a escala, as faltas transferidas e as regras da IES não forem homologadas.
- **Média acadêmica:** notas e médias permanecem no nível da disciplina/período. A MIRA não calcula uma média institucional única sem conhecer pesos, conceitos, exames e regras de aprovação.
- **Acesso/último login:** ainda não foi identificado um endpoint de leitura que represente último acesso do aluno ao AVA/portal com semântica adequada.

O worker usa lotes e concorrência limitada; os checkpoints são gravados após persistência, permitindo retomada. A integração permanece somente leitura.

## 10. Homologação pendente

Para declarar a conexão validada em produção, é necessário testar com um ambiente real ou sandbox autorizado pela JACAD:
- URL do ambiente e token com permissão de consulta;
- quantidade de alunos e comportamento de paginação/cursor;
- campos reais e diferenças entre versões/instalações;
- escopos/permissões do token;
- limites de taxa e respostas 401/403/429;
- matrículas e resumo financeiro com dados reais;
- consulta detalhada de parcelas por contrato e homologação dos estados de situação;
- regras de saldo total e recorrência (cancelamentos, renegociações, baixas);
- notas e frequência;
- cadência e semântica dos timestamps por campo.

**Conclusão:** a conexão nativa sincroniza cadastro, matrículas, resumo e parcelas financeiras, disciplinas, resultados acadêmicos e notas por avaliação. Os dados detalhados são preservados com checkpoints e limites de taxa. Saldo total, recorrência, média institucional, frequência canônica e acesso continuam sem inferência até homologação das regras e semântica da instalação. O score automático permanece desabilitado.
