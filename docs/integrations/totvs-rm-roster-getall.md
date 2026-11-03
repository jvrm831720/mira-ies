# TOTVS RM — Descoberta e leitura GetAll de alunos

**Status:** implementação de leitura paginada filtrada; homologação de ambiente pendente.  
**Data:** 2026-11-03.

## Evidência oficial

A Central de Atendimento TOTVS documenta o serviço RESTful \`RMSRestDataServer\` e o método GetAll. A operação usa:
- \`start\`: índice inicial, começando em zero;
- \`limit\`: quantidade máxima de registros;
- \`filter\`: array JSON serializado, com a expressão de filtro no primeiro elemento e os valores dos parâmetros nos elementos seguintes.

Fontes:
- [Serviços RESTful no RM](https://centraldeatendimento.totvs.com/hc/pt-br/articles/22322698636823-Cross-Segmentos-Backoffice-RM-Integra%C3%A7%C3%A3o-API-Servi%C3%A7os-RESTful-no-RM)
- [GetAll e exemplo de filtro](https://centraldeatendimento.totvs.com/hc/pt-br/articles/4402117244311-Cross-Segmentos-Backoffice-RM-Integra%C3%A7%C3%A3o-API-Requisi%C3%A7%C3%A3o-REST-GetAll-e-Exemplo-de-Utiliza%C3%A7%C3%A3o-do-Filtro)
- [DataServer EduAlunoData para leitura/cadastro de alunos](https://centraldeatendimento.totvs.com/hc/pt-br/articles/360007744631-TOTVS-Educacional-Educacional-EDU-Dataserver-EduAlunoData-para-leitura-Cadastro-de-Alunos)

A documentação do \`EduAlunoData\` confirma o DataServer e a chave composta \`CODCOLIGADA;RA\` para ReadRecord. A documentação geral do GetAll mostra que a coleção de um DataServer pode ser consultada via REST com paginação e filtros. Ainda é necessário validar a disponibilidade de GetAll especificamente para \`EduAlunoData\` na versão e configuração da IES.

## Implementação

\`TotvsRMReadOnlyAdapter.iter_student_records()\` agora:
- consulta o caminho fixo \`EduAlunoData\`;
- gera o filtro \`CODCOLIGADA =:CODCOLIGADA\` usando apenas a coligada da configuração do conector;
- serializa o filtro em JSON compacto;
- usa \`start\` e \`limit\` por meio do paginador existente;
- projeta a resposta para apenas `CODCOLIGADA` e `RA`, descartando CPF, nome, e-mail, telefone, endereço e outros campos pessoais que possam vir no payload;
- rejeita registros fora da coligada solicitada ou sem RA;
- respeita \`max_pages\` e falha explicitamente se atingir o limite;
- não adiciona métodos de escrita.

O transporte aceita parâmetros extras de consulta para operações paginadas, mas impede que eles sobrescrevam \`start\` ou \`limit\`.

## Limites conhecidos

1. O endpoint e o DataServer precisam estar publicados e autorizados no ambiente da IES.
2. O usuário RM precisa ter permissão de leitura e acesso aos campos exigidos.
3. A documentação geral não garante que toda instalação retorne a mesma estrutura JSON. O leitor aceita uma lista JSON; envelopes de resposta precisam de contrato explícito antes de serem suportados.
4. O DataServer de aluno pode retornar dados pessoais e campos sensíveis. A documentação TOTVS orienta permissões específicas para campos sensíveis e acesso via WebService. A MIRA não deve solicitar permissão ampla de campos sensíveis para montar o roster; tanto `iter_student_keys()` quanto `read_student_record()` projetam a saída para somente `CODCOLIGADA` e `RA`, descartando CPF, nome, e-mail, telefone, endereço e demais campos. Acesso adicional exige finalidade, autorização e allowlist próprios.
5. Offset pagination não garante snapshot consistente se registros forem inseridos/removidos durante a varredura. Para sincronização incremental confiável, ainda precisamos identificar uma chave de ordenação estável e um campo de atualização ou estratégia de reconciliação.
6. A consulta por coligada não substitui isolamento por tenant na MIRA. O backend deve derivar e validar tenant/contexto no servidor.
7. Não foram consultados ambientes de cliente, bancos RM ou credenciais reais.

## Testes

- Serialização e envio do filtro por query string.
- \`start\`/\`limit\` preservados e parâmetros reservados protegidos.
- Resposta em lista JSON.
- Adapter sempre filtra pela \`CODCOLIGADA\` configurada.
- Preservação do RA como string continua coberta nos testes existentes.

## Gate para homologação

A instituição deve executar a consulta no Swagger/Postman ou cliente autorizado do RM e confirmar:
- resposta de \`GET /rmsrestdataserver/rest/EduAlunoData?start=0&limit=...\`;
- estrutura da resposta;
- quantidade de registros comparada à visão oficial do RM;
- filtros por coligada e permissões;
- comportamento ao paginar e ao alterar registros durante a varredura;
- disponibilidade de campo de atualização para sincronização incremental.

**Conclusão:** a rota GetAll é uma via documentada para descoberta e teste de listagem. A implementação MIRA é uma primeira leitura filtrada, não uma homologação de roster nem um sincronizador de produção.
