# Auditoria da importação MIRA — primeira fase

## O que já existe na `main`

- Upload de um arquivo CSV, XLSX ou XLS por operação.
- Limite de tamanho aplicado no backend e validação de extensão.
- Prévia sem persistência definitiva em `POST /api/v1/upload/preview`.
- Mapeamento determinístico por aliases conhecidos e possibilidade de ajuste manual.
- Validação de campos obrigatórios (matrícula e nome), avisos de qualidade e amostra de linhas.
- Detecção de matrículas repetidas no arquivo e correspondências com registros da mesma instituição.
- Persistência/upsert e consulta individual do estado do lote por `GET /api/v1/upload/status/{batch_id}`.
- O modelo `UploadBatch` já registra nome do arquivo, instituição, estado, totais, timestamps e erro.

## O que esta PR acrescenta

- Endpoint paginado `GET /api/v1/upload/history`, filtrado pelo `tenant_id` autenticado.
- Página `/importacoes` com estados de carregamento, erro, vazio, status e totais reais do servidor.
- Acesso ao histórico a partir da tela de importação.

## Lacunas identificadas para fases seguintes

1. Upload e análise de vários arquivos numa mesma operação.
2. Classificação explícita dos tipos de base e relacionamentos confiáveis entre arquivos.
3. Prévia final com contagem de criar, atualizar, ignorar, rejeitar e pendências calculada por operação.
4. Correções por linha e exportação de relatório de erros.
5. Persistência de uma execução de importação com chave de idempotência, progresso real, recuperação após falha parcial e reprocessamento seguro.
6. Histórico detalhado de uma operação, incluindo responsável, relatório de validação e navegação aos registros afetados.
7. Mapeamentos reutilizáveis por instituição.
8. Validação de conteúdo real do arquivo, política de retenção dos arquivos originais e revisão do ciclo de vida de armazenamento.

## Regra de integridade importante

A implementação atual de ingestão consolida duplicidades internas pela matrícula e usa a última ocorrência. Antes de transformar esse comportamento em uma política configurável, a interface deve explicá-lo e o backend deve expor os registros afetados de forma auditável.

## Escopo e honestidade da interface

Esta fase não habilita importação de múltiplas bases nem declara que uma base está pronta para análise de risco apenas por ter sido enviada. A página de histórico mostra somente estados e contagens existentes no servidor; não simula progresso nem resultados que o backend não fornece.
