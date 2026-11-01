# Wave 2.3 — consulta e explicabilidade de grupos

A API mantém os endpoints existentes `GET /api/v1/student-groups/catalog` e `/summary` e acrescenta:

- `GET /api/v1/student-groups/{group_id}`: regra de inclusão em linguagem clara, sinais e fontes, métricas de `TRUE`/`FALSE`/`INDETERMINATE`, cobertura, limitações e `evaluated_at`.
- `GET /api/v1/student-groups/{group_id}/members?limit=50&cursor=...`: somente alunos ativos do tenant autenticado com avaliação definitivamente `TRUE` para o grupo. `limit` aceita 1–100; sem valor usa 50.

As rotas exigem o papel mínimo `viewer`. O tenant é extraído apenas do contexto autenticado. O payload do membro usa somente `student_id` e `name` para identificação, mais a avaliação, evidências e limitações do grupo. `matched_signals` contém os sinais definitivamente ativos; `signals` também expõe estados `FALSE` e `INDETERMINATE` relevantes, sem tratá-los como ativos.

## Cursor e consistência

A ordenação é crescente por `student_id`, chave única e estável, usando keyset (`id > after_id`) no banco, sem `OFFSET`. O cursor é um token HMAC com validade de uma hora, vinculado ao tenant autenticado, grupo, versão do catálogo e tamanho da página. Cursor malformado, adulterado ou incompatível retorna HTTP 400; cursor expirado retorna HTTP 410. Não há filtros de cliente nesta versão.

A avaliação é sob demanda e não materializa associações. `evaluated_at` é o instante da avaliação, não a recência dos dados de origem. Não há snapshot transacional entre requisições: alterações nos dados podem mudar os membros/estados durante a navegação. O limite provisório configurável de candidatos por requisição é `STUDENT_GROUP_MAX_STUDENTS` (padrão 10.000); quando o endpoint de membros atinge esse teto sem confirmar o fim, responde `truncated: true`, `has_more: null` e inclui cursor de continuação. Em páginas normais, o ponto keyset fica após o último membro retornado; numa varredura truncada de grupo esparso, o cursor registra o último candidato avaliado como checkpoint e também assina o último membro retornado. Esse valor não é SLO de produção.

O grupo `missing_score` descreve lacuna de cobertura e não deve ser interpretado como baixo risco. Para `multiple_active_signals`, a resposta mostra os cinco sinais operacionais e indica quais estados `TRUE` satisfizeram o limiar; sinais indeterminados nunca contam como ativos.
