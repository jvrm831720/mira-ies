# Fixtures sintéticas para validação do importador individual

> **Aviso:** estes arquivos são inteiramente sintéticos. Não foram exportados do SophiA e não representam um layout oficial homologado. Os nomes de coluna foram inspirados nos tipos de informação descritos na documentação secundária e nas telas/relatórios públicos consultados.

## Arquivos

- `sophia_alunos_sintetico.csv`: cadastro tabular com delimitador ponto e vírgula, UTF-8 BOM, matrícula com zeros à esquerda, semestre ordinal, status acadêmico, moeda e decimais com vírgula, além de células vazias.
- `sophia_academico_sintetico.csv`: exemplo de dados acadêmicos agregados por aluno. Inclui `-1` na média para exercitar o tratamento conservador de sentinela.

## Limites de interpretação

- O relatório acadêmico SophiA pode apresentar notas por disciplina/etapa. Uma coluna genérica `Nota` não prova que o valor seja média geral do aluno. O importador não deve inferir essa equivalência.
- A média `-1` aparece em exemplo secundário da API, mas sua semântica não está homologada. O importador deve ignorá-la e emitir aviso, nunca convertê-la em nota zero.
- Campos vazios significam desconhecido/não fornecido. Não devem ser preenchidos com zero, presença de 100%, nota 10 ou outro valor favorável.
- O arquivo de cadastro é deliberadamente tabular e usa uma chave estável sintética (`Matrícula`). A existência de um identificador estável no arquivo real ainda precisa ser confirmada.
- Os arquivos não validam a API, autenticação, paginação, sincronização incremental, exportação real ou compatibilidade de qualquer versão instalada do SophiA.

## Execução

A suíte `backend/tests/test_sophia_synthetic_import.py` envia os fixtures ao endpoint individual `/api/v1/upload/preview`, testa a inspeção e a prévia de XLSX multia­bas gerado em memória e verifica que a prévia não persiste registros.
