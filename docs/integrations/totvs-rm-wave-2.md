# Wave RM 2 — Validação de contrato e semântica financeira

**Status:** implementação de proteção semântica + discovery documental complementar.  
**Base:** Wave RM 1 (transporte REST/SOAP e adapter read-only).  
**Não homologado:** nenhuma instância de cliente foi acessada; códigos e payloads abaixo não são universais.

## 1. Resultado da descoberta complementar

A documentação de suporte TOTVS confirma que o lançamento financeiro pode ter baixa parcial. Ao concluir uma baixa parcial, o lançamento passa ao estado "Parcialmente Baixado", um item de baixa é criado e a diferença continua pendente. Portanto, tratar qualquer lançamento não totalmente baixado como "em aberto" perde informação financeira relevante.

Fontes:
- [Baixa Parcial de Lançamentos Financeiros — Central TOTVS](https://centraldeatendimento.totvs.com/hc/pt-br/articles/360025753331-Cross-Segmentos-Backoffice-Linha-RM-FIN-Baixa-Parcial-de-Lan%C3%A7amentos-Financeiros)
- [Confirmação de matrícula por pagamento — Central TOTVS](https://centraldeatendimento.totvs.com/hc/pt-br/articles/6305062805143-TOTVS-Educacional-Educacional-Edu-Como-utilizar-processo-de-confirma%C3%A7%C3%A3o-de-matr%C3%ADcula-por-pagamento-de-forma-automatizada)

A documentação de confirmação de matrícula usa \`FLAN.STATUSLAN = 1\` para lançamento baixado e \`FLAN.STATUSLAN <> 1\` para não baixado nesse processo específico. Isso não comprova que todos os demais códigos sejam "em aberto", nem documenta uma tabela universal de estados para todas as versões/parametrizações.

A documentação de suporte também confirma operações de renegociação de parcelas, mas não define um contrato de API universal que permita inferir renegociação apenas a partir do payload de parcelas:
- [Renegociação de contrato no Portal do Cliente — Central TOTVS](https://centraldeatendimento.totvs.com/hc/pt-br/articles/360034709913-RM-TIN-PDC-Como-é-feita-a-Renegociação-de-Contrato-no-Portal-do-Cliente-PDC)

## 2. Mudança técnica entregue nesta wave

Foi adicionado \`totvs_rm_finance.py\`, um contrato de classificação de status financeiro configurado pela instituição:

- Só classifica códigos que a IES mapeou e homologou.
- \`UNKNOWN\` é o resultado padrão para campo ausente, nulo ou código não mapeado.
- Não presume que \`STATUSLAN != 1\` significa parcela em aberto.
- Suporta estados explícitos: \`open\`, \`partially_paid\`, \`paid\`, \`cancelled\`, \`renegotiated\`, \`reversed\`.
- Não calcula saldo, valor pago, atraso ou recorrência.
- O mapeamento é imutável após criação e deve ser isolado por configuração/tenant no próximo passo de integração.

**Importante:** os códigos de exemplo nos testes são dados sintéticos para provar o contrato. Não representam códigos oficiais RM.

## 3. Matriz de evidência e gates

| Domínio | Evidência disponível | O que ainda não pode ser afirmado | Gate para homologação |
|---|---|---|---|
| Cadastro de aluno | \`EduAlunoData.ReadRecord\` por chave composta \`CODCOLIGADA;RA\` | Listagem completa de alunos ou paginação de roster | Demonstrar endpoint/consulta em lote ou exportação controlada, com contagem e paginação |
| Parcelas | \`EduParcelaData\` com exemplo de \`start/limit\`, valor e vencimento | Situação financeira completa, valor líquido, baixa parcial e histórico | Amostras anonimizadas de parcela + lançamento + itens de baixa |
| Baixa parcial | Processo TOTVS cria item de baixa e mantém diferença pendente | Como esses itens são expostos pelo endpoint habilitado na IES | Confirmar DataServer/rota e campos de baixa |
| Renegociação | Processo funcional existe no ecossistema RM | Como distinguir parcela original, acordo, parcelas substitutas, acordo pendente/cancelado/efetivado pela API | Confirmar chaves e relações de origem/destino com a IES |
| Cancelamento/estorno | Há processos distintos e parametrizados | Código universal ou equivalência entre cancelamento, estorno e reversão | Obter tabela/códigos da versão e exemplos reais anonimizados |
| Notas/frequência | Recursos por chaves de etapa/disciplina documentados | Média global e percentual de presença universal | Validar regra acadêmica, denominador e período com responsável da IES |
| Último login | Não identificado na documentação consultada | \`dias_sem_login\` | Identificar fonte autorizada de portal/AVA/autenticação |

## 4. Critérios financeiros para a MIRA

A MIRA não deve derivar \`saldo_devedor\` a partir de \`VALOR\` e \`DTVENCIMENTO\` de parcelas sem cruzar os lançamentos e seus itens de baixa.

Antes de calcular indicadores financeiros, a IES deve confirmar:
1. Qual é a chave estável entre parcela, lançamento financeiro, baixa e item de baixa.
2. Como são representados pagamento integral e parcial.
3. Como são representados descontos, bolsas, juros, multas e abatimentos.
4. Como renegociações vinculam parcelas originais e novas.
5. Como cancelamentos, estornos e exclusões são representados.
6. Qual data de referência e fuso devem ser usados para atraso.
7. Se o valor retornado é bruto, líquido, atualizado ou histórico.

Até essa confirmação, a ingestão deve preservar o payload bruto e a proveniência, sem converter valores em saldo ou inadimplência.

## 5. Segurança e isolamento

- A configuração do mapa de status deve pertencer a uma instituição/tenant e nunca ser compartilhada implicitamente.
- A origem, versão do RM, DataServer/rota, coligada, filial, tipo de curso e instante de observação devem acompanhar cada lote.
- Credenciais técnicas read-only e conectividade privada aprovada continuam obrigatórias.
- O conector não deve consultar diretamente o banco RM nem expor a porta do Host à internet.
- Nenhuma escrita deve ser adicionada ao RM nesta integração.

## 6. Testes adicionados

- Status explicitamente mapeado.
- Status desconhecido e campo ausente permanecem \`UNKNOWN\`.
- Baixa parcial, cancelamento, renegociação e estorno exigem mapeamento explícito.
- Campo de status inválido rejeitado.
- Mapa imutável após construção.

## 7. Próximos passos dentro da Wave RM 2

1. Validar a correção do teste de redirect SOAP e manter a Wave RM 1 verde.
2. Acrescentar fixtures anonimizadas/sintéticas de parcelas, lançamentos e itens de baixa sem inventar códigos RM.
3. Definir a estrutura de configuração tenant-scoped para os mapeamentos homologados.
4. Investigar uma rota de roster em lote e provar paginação, ordenação estável e retomada.
5. Só então desenhar o sincronizador e os mapeamentos canônicos.

**Decisão atual:** continuar com contrato seguro e ingestão bruta. Não liberar sincronização financeira nem scoring baseado em saldo/atraso até a homologação das semânticas.
