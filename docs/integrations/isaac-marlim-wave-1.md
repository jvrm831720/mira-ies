# Isaac / Marlim — Wave 1: consulta read-only de conciliação

## Escopo e distinção de produtos

Este conector trata exclusivamente da API pública **Marlim & Isaac Pagamentos**.
Ela não é a API acadêmica do WPensar e não deve ser usada para inferir matrícula,
frequência, notas ou situação de inadimplência no ERP.

A documentação pública confirma:
- Sandbox: `https://sandbox.api.isaac.marlim.co`
- Produção: `https://api.isaac.marlim.co`
- Autenticação por header `api_key`
- Consulta de conciliação: `POST /v1/conciliation`
- Corpo com `date_created`, `with_transactions`, `page` e `count` (máximo 100)
- Resposta com totais pagos/estornados, transferências e transações pagas/estornadas.

Fonte oficial: https://api.isaac.marlim.co/

## Implementado nesta wave

- Cliente HTTP assíncrono com hosts fixos de sandbox/produção.
- Header de autenticação conforme documentação.
- Redirects desabilitados e timeout configurável.
- Única operação remota permitida: leitura de conciliação.
- Data de consulta exige timezone explícito e é convertida para UTC.
- Paginação explícita, com `count` limitado a 100.
- Tipagem estrita dos valores monetários em centavos.
- Erros HTTP e de contrato sanitizados.
- Parser retorna apenas identificadores de transação/item, valores e timestamps.
- Dados pessoais do pagador e dados do cartão presentes no payload original não são copiados para os objetos de domínio.

## Limites

- Nenhum endpoint de criação de parceiro, link de pagamento, transação ou estorno.
- Nenhuma chamada à produção ou sandbox foi executada.
- Nenhuma API key real foi usada.
- Nenhuma persistência, conciliação contábil, scoring ou associação automática com aluno.
- O `item_id` só pode ser associado a uma cobrança da MIRA quando existir um contrato institucional explícito que defina essa chave.
- A consulta de conciliação não é um extrato completo de inadimplência nem substitui o ERP acadêmico.

## WPensar

O transformer atual do WPensar continua sem cliente nativo de leitura. A documentação pública consultada não define endpoints REST, autenticação e paginação para extração de alunos/financeiro. Não criar cliente WPensar até receber contrato oficial de API ou documentação técnica fornecida pela instituição/fornecedor.

## Próximas etapas

1. Validar o contrato com equipe técnica da Isaac/Marlim.
2. Receber chave de sandbox e executar teste autorizado.
3. Definir contrato de `item_id` com o ERP/cliente para reconciliar cobranças.
4. Persistir eventos financeiros com tenant isolation, idempotência e auditoria.
5. Manter WPensar em trilha separada até documentação oficial da API acadêmica.
