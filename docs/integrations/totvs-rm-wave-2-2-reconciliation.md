# TOTVS RM — Wave 2.2: reconciliação financeira

**Status:** camada pura de reconciliação implementada com contratos configuráveis e fixtures sintéticas.  
**Não homologado:** DataServers, nomes de campos, chaves e códigos da instituição.

## 1. Evidência funcional TOTVS

A documentação da Central Financeira do RM descreve que uma parcela pode ter **mais de um lançamento financeiro vinculado**, por exemplo, quando existem responsáveis financeiros diferentes ou lançamentos de bolsa de crédito. A interface também distingue parcelas sem lançamento, parcelas com lançamentos e os status apresentados para os lançamentos.

A documentação de baixa parcial informa que o RM cria um **item de baixa** no lançamento e mantém a diferença pendente. Portanto, a relação financeira que precisa ser reconstruída é:

\`Parcela → 1..N Lançamentos → 0..N Itens de baixa\`

Fontes oficiais:
- [Central Financeira — Linha RM](https://tdn-homolog.totvs.com/display/public/LRM/Central%2BFinanceira)
- [Baixa Parcial de Lançamentos Financeiros](https://centraldeatendimento.totvs.com/hc/pt-br/articles/360025753331-Cross-Segmentos-Backoffice-Linha-RM-FIN-Baixa-Parcial-de-Lan%C3%A7amentos-Financeiros)
- [Cálculo do Valor Líquido do Lançamento](https://centraldeatendimento.totvs.com/hc/pt-br/articles/30530902727191-Cross-Segmentos-Backoffice-Linha-RM-FIN-Como-o-RM-realiza-o-C%C3%A1lculo-do-Valor-L%C3%ADquido-do-Lan%C3%A7amento)
- [Geração de Lançamentos](https://tdn-homolog.totvs.com/pages/releaseview.action?pageId=425459455)
- [Pagamento a maior/menor e Conta Corrente do Aluno](https://tdn-homolog.totvs.com/pages/releaseview.action?pageId=4814905)

A TOTVS também informa que o valor líquido do lançamento é dinâmico e não fica armazenado em uma tabela específica. Ele pode variar com juros, multas, descontos, vínculos e outros valores. Por isso, esta entrega **não calcula saldo devedor** somando ou subtraindo campos presumidos.

## 2. Implementação

Novo módulo: \`backend/app/services/connectors/totvs_rm_reconciliation.py\`.

A função \`reconcile_financial_records()\` recebe três coleções brutas e seus contratos de campos configurados pela instituição:

- Parcelas: identificador, RA, contrato, vencimento e valor nominal.
- Lançamentos: identificador, referência à parcela, RA, contrato, valor original, vencimento e mapa de status homologado.
- Itens de baixa: identificador, referência ao lançamento, valor, data e mapa de tipo de evento homologado.

O resultado é um grafo tipado e sem payloads brutos. O adapter não persiste dados e não executa chamadas de rede nesta etapa.

### Regras aplicadas

1. Uma parcela pode se relacionar com vários lançamentos.
2. Cada lançamento precisa referenciar uma parcela, RA e contrato compatíveis.
3. Cada item de baixa precisa referenciar um lançamento.
4. Relações órfãs são devolvidas em listas de diagnóstico; não são descartadas silenciosamente.
5. IDs duplicados, referências inconsistentes, valores negativos, NaN, infinito e formatos monetários ambíguos interrompem a reconciliação.
6. Valores monetários usam \`Decimal\`; strings com vírgula são rejeitadas até que o formato da origem seja configurado explicitamente.
7. Datas permanecem como texto de origem. Nenhum formato ou fuso horário é presumido.
8. Status de lançamento e tipo de evento de baixa só são classificados quando existe mapeamento explícito da IES.
9. Pagamentos, estornos e eventos desconhecidos são totalizados separadamente por lançamento.

## 3. O que a camada deliberadamente NÃO calcula

- Saldo devedor ou valor líquido.
- Atraso, dias em atraso ou inadimplência.
- Valor pago líquido após estornos.
- Desconto, bolsa, juros, multa ou abatimento.
- Valor em aberto após renegociação.
- Saldo da Conta Corrente do Aluno.
- Estado efetivo de acordo/renegociação.

Mesmo que o total dos itens de baixa esteja disponível, não subtraímos estornos automaticamente: a relação entre um estorno e a baixa original precisa ser comprovada. Pagamento a maior/menor pode gerar débito ou crédito na Conta Corrente do Aluno; essa movimentação não pode ser tratada como baixa simples sem mapear o ledger correspondente.

## 4. Testes sintéticos

Arquivo: \`backend/tests/test_totvs_rm_reconciliation.py\`.

Cobertura:
- Uma parcela com múltiplos lançamentos.
- Lançamento com múltiplos itens de baixa.
- Baixa parcial, pagamento, estorno e evento desconhecido.
- Lançamentos sem parcela e itens sem lançamento.
- Bloqueio de vínculo cruzado entre aluno/contrato.
- Bloqueio de IDs duplicados.
- Valores inválidos e formatos ambíguos.
- Status/eventos sem homologação permanecem UNKNOWN.
- Preservação do RA com zeros à esquerda e das datas de origem.
- Imutabilidade do mapa de eventos.

Os códigos dos testes são sintéticos e não representam códigos RM oficiais.

## 5. Gaps para integração real

Antes de ligar esta camada a qualquer DataServer, a instituição precisa fornecer ou confirmar:

1. DataServer/endpoint e versão RM para parcelas, lançamentos, itens de baixa e Conta Corrente do Aluno.
2. Chaves estáveis e campos de relacionamento entre essas entidades.
3. Como o RM representa cancelamento de lançamento, cancelamento de baixa, estorno e baixa pendente.
4. Relação entre parcelas originais e lançamentos/parcelas de acordo.
5. Relação de baixa com pagamento original e reversões.
6. Composição de valores: bruto, líquido, desconto, bolsa, juros, multa, abatimentos e integração financeira.
7. Campos de data, formato, fuso e política de corte.
8. Permissões mínimas read-only e allowlist de campos.

## 6. Critério de aceite

A Wave 2.2 está pronta para revisão de código, não para homologação do ERP. O aceite de integração exige uma amostra anonimizada ou uma extração controlada que permita reconciliar:
- contagem de parcelas;
- contagem de lançamentos por parcela;
- contagem e soma de itens de baixa por lançamento;
- órfãos e duplicidades;
- casos de baixa parcial, estorno, acordo e conta corrente.

**Decisão:** manter a saída como grafo de origem e totais descritivos. Nenhum saldo ou feature de inadimplência deve alimentar o scoring da MIRA até a validação das regras e relações financeiras da IES.
