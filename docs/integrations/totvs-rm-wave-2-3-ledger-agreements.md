# TOTVS RM — Wave 2.3: Conta Corrente, acordos e reversões

**Status:** contratos puros e testes sintéticos implementados.  
**Não homologado:** DataServers, campos, códigos, chaves e semânticas de nenhuma instalação RM.

## 1. Objetivo

A Wave 2.2 construiu o grafo parcela → lançamentos → itens de baixa. Esta wave adiciona três domínios que precisam ser reconciliados separadamente antes de qualquer cálculo de posição financeira:

1. Movimentos da Conta Corrente do Aluno.
2. Acordos e vínculos entre obrigações originais e substitutas.
3. Relação explícita entre um estorno e o item de pagamento original.

A implementação não afirma que esses domínios tenham um DataServer, campo ou código universal. A IES deve fornecer o contrato homologado.

## 2. Conta Corrente do Aluno

Novo contrato: \`RMLedgerMovementFields\`.

Cada movimento é representado por:
- ID de origem;
- RA e contrato;
- valor monetário;
- direção classificada por mapa explícito: débito, crédito ou UNKNOWN;
- referência bruta opcional à origem.

A reconciliação agrupa os movimentos por RA + contrato e apresenta totais descritivos separados:
- total de débitos;
- total de créditos;
- total com direção desconhecida;
- quantidade de movimentos.

**Não calcula saldo líquido.** Não presume que um crédito seja pagamento, que um débito seja mensalidade, nem que a referência de origem aponte para um lançamento ou baixa específico. O significado desses movimentos depende da configuração financeira da IES.

## 3. Acordos e obrigações

Novos contratos:
- \`RMAgreementFields\`;
- \`RMAgreementLinkFields\`.

O grafo permite representar:
- registro do acordo;
- status do acordo, mapeado pela IES;
- vínculo com obrigação original;
- vínculo com obrigação substituta;
- tipo da obrigação vinculada: parcela ou lançamento.

A camada valida se a obrigação existe no conjunto reconciliado e se RA/contrato coincidem com o acordo. Relações sem acordo, sem obrigação ou com tipo/papel desconhecido são reportadas. Não são convertidas em relações válidas por heurística.

O código não presume que toda renegociação gere uma nova parcela, nem que o acordo substitua imediatamente a obrigação original. A semântica de vigência, cancelamento, quebra, quitação e reativação deve ser mapeada com a instituição.

## 4. Reversões

Novo contrato: \`RMReversalLinkFields\`.

Para cada item classificado como estorno, a camada procura a referência explícita ao item de pagamento original. O vínculo só é aceito quando:
- o item de origem existe;
- o item de origem está classificado como pagamento;
- ambos pertencem ao mesmo lançamento financeiro.

Estornos sem referência e referências inválidas são expostos em diagnósticos separados. O valor do estorno não é subtraído automaticamente do pagamento original. Também não é presumida equivalência entre cancelamento de baixa, estorno bancário, devolução e reversão contábil.

## 5. Segurança semântica

- Mapas de códigos são imutáveis e configurados por contrato da IES.
- Código sem mapeamento permanece UNKNOWN.
- Valores usam Decimal e devem chegar em formato decimal canônico.
- Valores negativos, não finitos e IDs duplicados são rejeitados.
- RA permanece string para preservar zeros à esquerda.
- Referências de origem são preservadas como texto, sem inferência.
- Nenhuma chamada de rede, persistência, escrita no RM ou cálculo de saldo foi adicionado.
- A aplicação deve fornecer os registros já isolados por tenant; RA + contrato não substituem tenant_id nem RLS.

## 6. Testes sintéticos

Arquivo: \`backend/tests/test_totvs_rm_ledger.py\`.

Cobertura:
- acordo com obrigação original e substituta;
- status, tipo e papel desconhecidos;
- acordo ou obrigação ausente;
- bloqueio de vínculo entre aluno/contrato diferentes;
- totais separados de débito, crédito e direção desconhecida;
- valores inválidos e IDs duplicados;
- estorno vinculado ao pagamento original;
- estorno sem referência e referência inválida;
- mapa imutável e UNKNOWN reservado.

Os códigos e registros dos testes são sintéticos. Não representam valores oficiais RM.

## 7. Gaps para homologação

A instituição ainda precisa confirmar:
1. DataServer/rota e versão para Conta Corrente do Aluno.
2. Chaves e semântica de cada tipo de movimento (débito, crédito, transferência, baixa, estorno, ajuste).
3. Relação de movimento com contrato, lançamento, item de baixa e origem.
4. Data efetiva, competência, vencimento, moeda e regra de corte.
5. Entidades e chaves de acordo/renegociação.
6. Relações entre obrigações originais, obrigações substitutas e lançamentos gerados.
7. Estados de proposta, aprovação, efetivação, quebra, cancelamento e quitação.
8. Identificador do pagamento original em eventos de estorno e tratamento de estornos parciais/múltiplos.
9. Amostras anonimizadas e totais de controle fornecidos ou aprovados pela IES.

## 8. Critério de aceite

A Wave 2.3 está pronta para revisão do contrato de código, não para homologação RM. A integração exige reconciliação com uma extração controlada:
- totais de débito/crédito por aluno e contrato comparados à tela/relatório de Conta Corrente;
- acordos com suas obrigações de origem e destino;
- pagamentos com estorno total, parcial e múltiplo;
- movimentos órfãos, duplicados e sem classificação;
- contagens e somas validadas pelo responsável financeiro da IES.

**Decisão:** manter três resultados separados e descritivos. Não gerar saldo, atraso, inadimplência ou feature financeira para scoring até a homologação das regras e dos relacionamentos.
