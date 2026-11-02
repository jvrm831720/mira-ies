# Integração nativa Sponte BI

## 1. Fonte oficial e autenticação

- Base URL fixa: `https://sponte-bi.sponteweb.com.br`.
- Autenticação: header `x-api-key`; a chave é exclusiva por cliente e deve ser cifrada em repouso.
- Cada requisição informa `CodCliSponte`, `DataExtracao`, `PageNumber` e `PageSize`.
- `PageSize` máximo documentado: 1.000.
- Envelope paginado: `currentPage`, `totalPages`, `pageSize`, `totalCount`, `items`, `hasPrevious`, `hasNext`.
- Defasagem de dados documentada: D-1.
- Limite documentado: 1.000 requisições por minuto por API Key.

Fonte: https://sponte-bi.sponteweb.com.br/docs

## 2. Endpoints usados pela MIRA

| Endpoint | Conteúdo | Uso |
|---|---|---|
| `/api/v1/extracoes/alunos` | Cadastro, situação, contato, responsável, funcionário e exclusão | Identidade do aluno e atualização cadastral |
| `/api/v1/extracoes/contratos` | Matrícula, contrato, aluno, curso/turma, datas e situação | Vínculo aluno-curso e estado da matrícula |
| `/api/v1/extracoes/contratosturmasestagios` | Relação contrato/turma/estágio/curso | Complemento de contexto acadêmico |
| `/api/v1/extracoes/contasreceber` | Parcelas, vencimento, pagamento, valores, situação e contrato | Inadimplência, recorrência e saldo |
| `/api/v1/extracoes/notas` | Avaliação, nota, média, semestre, ano e situação didática | Histórico de desempenho |
| `/api/v1/extracoes/fatofrequenciaalunosativos` | Snapshots de frequência por aluno/contrato | Frequência e tendência temporal |
| `/api/v1/extracoes/fatoalunosativos` | Snapshots de contratos vigentes e situação | Cobertura e histórico de alunos ativos |
| `/api/v1/extracoes/followups` | Atendimentos e contatos com alunos | Histórico de intervenções |

Todos os endpoints de extração documentados usam paginação e `DataExtracao`. Os endpoints de fatos são snapshots; não devem ser somados entre datas como se fossem eventos.

## 3. Incrementalidade e consistência

- Primeira coleta: data inicial configurável, com padrão recomendado pela documentação de `2025-01-01`.
- Coletas seguintes: watermark independente por endpoint.
- Como `DataExtracao` é uma data sem horário e a API tem defasagem D-1, a consulta incremental usa sobreposição de um dia.
- Upsert/deduplicação por identificadores do fornecedor (`AlunoID`, `ContratoID`, `contaReceberID`, `notaDetalheID`, e chaves de snapshot).
- Watermark só avança depois de todas as páginas do endpoint terem sido persistidas.
- Registros com `excluido` são preservados como excluídos e não alimentam indicadores.
- Reprocessar a janela de sobreposição é seguro e idempotente.

## 4. Semântica dos indicadores

### Financeiro
A documentação descreve `Situacao = 'Pendente'` para parcelas em aberto, `DataVencimentoParcela` para vencimento, `ValorTotalParcela` e `ValorPagoParcela`. A MIRA pode calcular:
- dias de atraso: maior atraso entre parcelas pendentes vencidas;
- recorrência: quantidade de parcelas pendentes vencidas;
- saldo devedor: soma de `max(0, ValorTotalParcela - ValorPagoParcela)` nas parcelas pendentes não excluídas.

Os valores de outras situações não serão reinterpretados sem homologação.

### Acadêmico
Notas são preservadas por avaliação, turma, estágio, semestre e ano. Não será criada média global sem regra institucional de pesos, escalas, recuperação e aprovação.

### Frequência
O endpoint de fatos retorna snapshots semanais com `aulasAssistidas`, `aulasTotais` e `totalFaltas`. A MIRA mantém a série temporal e usa o snapshot mais recente por aluno/contrato. Percentual de presença só é calculado quando `aulasTotais > 0` e os campos são válidos; snapshots não são somados entre semanas.

### Limites conhecidos
- A API BI documentada não apresenta um campo confiável de último login; `dias_sem_login` permanece desconhecido.
- `reprovacoes` depende de enumeração documentada para `situacaoDidatica`; não será inferida a partir de texto desconhecido.
- O score automático permanece bloqueado enquanto a cobertura dos sete campos preditivos e a semântica institucional não estiverem homologadas.

## 5. Segurança e operação

- Somente leitura; nenhuma escrita na Sponte.
- API key cifrada e nunca devolvida ao frontend ou registrada em logs.
- `CodCliSponte` e chave isolados por tenant.
- Worker Redis assíncrono, concorrência limitada, checkpoints por endpoint/página, retry e retomada.
- Watermarks por endpoint são persistidos por instituição.
- Estado do job não substitui os dados normalizados e auditáveis no Postgres.
- Homologação real depende de API key e código de cliente autorizados por uma instituição Sponte.
