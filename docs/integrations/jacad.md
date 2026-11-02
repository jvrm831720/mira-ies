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

Outros recursos documentam paginação por `currentPage` e `pageSize`; os limites variam por endpoint (há endpoints v1 com máximo 500). Cada recurso deve respeitar o limite publicado em sua própria documentação. O endpoint v2 de alunos aceita `idCursor` (inicia em 0) e a resposta devolve `idCursorProximo`. A documentação também informa limite técnico de 10 requisições por segundo por IP e um filtro de negócio por token (padrão ilustrado de 1.000 requisições por hora, configurável pela instituição). A MIRA faz chamadas sequenciais, sem paralelismo nesta primeira versão.

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
- Notas são retornadas por turma/disciplina e precisam de regra documentada para agregação por aluno e período.
- Frequência e acesso exigem endpoints e semântica específicos, ainda a homologar.

Portanto, o primeiro sync não inventa valores preditivos nem gera score automático. Campos sem evidência permanecem desconhecidos e o motor de risco continua sujeito ao bloqueio de cobertura/frescor da Wave 3.

## 7. Estratégia de sincronização

### Primeira carga
- Consulta paginada do cadastro de alunos e matrículas (v2).
- Consulta paginada do resumo financeiro por matrícula (v2), com `idOrg` obrigatório.
- Junção por `idAluno`, com fallback de RA.
- Persistência de status acadêmico, curso/turma, situação financeira e dias de atraso quando a API informa vencimento de parcela vencida.
- Preservação mínima dos IDs JACAD e resumo da parcela em `raw_data.jacad`; sem armazenar a resposta integral.
- Proveniência registra `source_type=jacad_api` e horário de importação. Como `dataAlteracao` não é timestamp de observação por campo, `observed_at` permanece desconhecido.
- Score automático permanece desabilitado.

### Incremental
A API documenta filtros de alteração em alguns recursos, como `dataAlteracaoInicio`/`dataAlteracaoFim` em alunos e matrículas. A implementação inicial ainda faz leitura paginada completa. O incremental será habilitado somente depois de homologar o comportamento do cursor e dos filtros de alteração no ambiente real da IES.

### Reconciliação e exclusões
A primeira versão não desativa alunos ausentes de uma resposta nem interpreta ausência como exclusão. Exclusões, transferências e status de matrícula precisam ser reconciliados com endpoint e regra específicos.

### Frequência operacional
A primeira versão oferece teste e sincronização sob demanda. Agendamento, checkpoints persistidos, retentativas e reconciliação automática serão adicionados depois de medir limites e cadência no ambiente real.

## 8. Segurança

- HTTPS obrigatório.
- Somente hosts sob `.jacad.com.br` são aceitos nesta versão.
- Redirects HTTP desabilitados.
- Credenciais cifradas em repouso com chave derivada do segredo de aplicação.
- Isolamento por tenant em tabela própria com RLS.
- Endpoints de configuração, teste e sync exigem papel de coordenador ou administrador.
- Respostas e logs não expõem token ou JWT.

## 9. Recursos adicionais identificados e decisão de escopo

A documentação atual também expõe:
- **Notas por turma e disciplina:** `GET /api/v1/academico/notas/consultar`, com `mediaMatriculaDisciplina`, status da matrícula-disciplina e itens de avaliação. Exige os códigos da turma e da disciplina do professor. A MIRA ainda não agrega várias disciplinas/períodos em uma média única por aluno; não foi incluído no sync automático para evitar uma média sem regra institucional.
- **Parcelas por contrato:** `GET /api/v1/financeiro/contratos-matricula/{idContrato}/parcelas`, com valor, valor pago, vencimento, pagamento e situação. A consulta exige uma chamada por contrato. O endpoint foi identificado, mas não foi ativado em massa porque pode gerar milhares de chamadas por sincronização. Além disso, os valores possíveis de `situacao` e as regras de cancelamento, renegociação e baixa precisam ser homologados antes de calcular saldo ou recorrência.
- **Frequência:** a documentação consultada descreve operações de lançamento de frequência, mas não confirmou um endpoint de leitura agregado que permita calcular presença percentual de forma confiável.
- **Acesso/último login:** não foi identificado um endpoint acadêmico de leitura que represente último acesso do aluno ao AVA/portal com semântica adequada.

Esses recursos são candidatos para uma próxima expansão após homologação com uma IES. A integração permanece somente leitura.

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

**Conclusão:** a conexão nativa sincroniza cadastro, matrículas e resumo financeiro por organização. A situação financeira e os dias de atraso têm mapeamento explícito; recorrência, saldo total, notas, frequência e acesso continuam desconhecidos até homologação das fontes correspondentes. O score automático permanece desabilitado.
