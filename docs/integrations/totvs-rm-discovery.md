# Discovery de integração — TOTVS Gestão Educacional (Linha RM)

**Status:** discovery documental inicial — não homologado  
**Escopo desta etapa:** leitura e avaliação de fontes públicas oficiais; nenhum endpoint foi chamado contra uma instituição.  
**Modo de integração proposto:** somente leitura. Não enviar POST, PUT ou DELETE para o RM.

## 1. Por que avaliar o TOTVS RM

O TOTVS Gestão Educacional (Linha RM) possui documentação pública separada para cadastro de alunos, contratos, cursos, frequência, notas/faltas e parcelas. A documentação confirma uma superfície REST baseada em DataServers, mas a configuração é vinculada ao ambiente RM da instituição. Isso torna a integração relevante, porém exige validar primeiro a topologia de rede e as permissões locais.

Fontes oficiais:
- [Portal de documentação do TOTVS Educacional](https://tdn-homolog.totvs.com/display/public/LRM/Educacional)
- [Serviço REST — Linha RM](https://tdn-homolog.totvs.com/pages/releaseview.action?pageId=338376631)
- [Cadastro — Serviço REST](https://tdn-homolog.totvs.com/pages/releaseview.action?pageId=320373485)
- [Nota/Falta de Etapa do Aluno (REST)](https://tdn-homolog.totvs.com/pages/viewpage.action?pageId=590621544)
- [Parcelas do Contrato](https://tdn-homolog.totvs.com/display/public/LRM/Parcelas+do+Contrato)
- [TOTVS Educacional — produto e módulos](https://produtos.totvs.com/ficha-tecnica/tudo-sobre-o-totvs-educacional/)

## 2. O que a documentação confirma

### Infraestrutura e contexto

A documentação REST da Linha RM descreve o serviço `RMSRestDataServer`, normalmente hospedado no Host RM. Os exemplos usam a porta HTTP 8051 e URLs locais como `http://localhost:8051/rmsrestdataserver/rest/<DataServer>`. O serviço identifica a base por `DefaultDB` no arquivo de configuração do Host.

As requisições precisam receber contexto nos headers:
- `CODCOLIGADA`
- `CODFILIAL`
- `CODTIPOCURSO`
- `CODSISTEMA`

As páginas específicas de DataServer documentam autenticação Basic com usuário e senha do RM. Portanto, não presumir OAuth, API key, JWT, URL pública ou acesso direto pela internet.

**Implicação arquitetural:** a MIRA em cloud não deve tentar acessar `localhost` nem expor diretamente o Host RM. A integração provavelmente precisará de um agente/conector instalado na rede da IES ou de um canal privado aprovado pela instituição, com saída HTTPS controlada. A topologia e a forma segura de conectividade ainda precisam ser confirmadas com TI da IES.

### Recursos com evidência documental

| Domínio | Recurso/DataServer | Evidência pública | Limite conhecido |
|---|---|---|---|
| Alunos | Cadastro — serviço REST; página filha “Alunos (Rest)” | O índice oficial lista o recurso | A página específica não pôde ser validada nesta rodada; método de listagem, filtros, paginação e campos precisam ser confirmados |
| Notas/faltas | `EduAlunoEtapaData` | GET por chaves `CODCOLIGADA`, `CODETAPA`, `TIPOETAPA`, `IDTURMADISC`, `RA` | A documentação consultada diz que não há listagem de vários registros nessa rota |
| Parcelas | `EduParcelaData` | GET de lista com `start` e `limit`; exemplo de retorno inclui RA, contrato, período, valor e vencimento | Situação/baixa financeira não foi confirmada como parte desse DataServer; não calcular saldo ou atraso apenas com o exemplo |
| Cursos, contratos, frequência | Recursos listados no índice de Cadastro — Serviço REST | A documentação do produto/índice aponta esses domínios | Contratos, chaves, campos, filtros e cobertura por versão ainda precisam de leitura específica |

A documentação da parcela mostra consulta de lista em `/rmsrestdataserver/rest/EduParcelaData?start=3&limit=2`. O exemplo inclui `RA`, `CODCONTRATO`, `IDPERLET`, `VALOR` e `DTVENCIMENTO`. Esses campos são evidência de estrutura, não um contrato universal de todas as instalações.

## 3. Mapeamento preliminar para a MIRA

| Campo canônico MIRA | Possível fonte RM | Regra inicial |
|---|---|---|
| `matricula` | `RA` | Preservar como string; nunca remover zeros à esquerda |
| `curso` | vínculo de matrícula/curso | Resolver por chave e preservar o código externo |
| `status_aluno` | situação de matrícula/contrato | Não mapear enum sem tabela oficial e exemplos da instalação |
| `saldo_devedor` | parcelas + baixa/lançamentos financeiros | Não calcular até identificar valor líquido, pagamento parcial, bolsas, cancelamentos, estornos e renegociações |
| `dias_atraso_boleto` | parcelas + situação financeira + vencimento | Calcular apenas para parcela comprovadamente em aberto e vencida, usando data de referência explícita |
| `recorrencia_atrasos` | histórico de parcelas/transações | Desconhecido até validar estados e histórico; parcelas abertas atuais não provam recorrência |
| `nota_media` | notas/faltas por etapa/disciplina | Não agregar em média do aluno sem regra de pesos, etapas, exames e aprovação da IES |
| `presenca_percentual` | frequência diária ou por etapa | Confirmar escala, denominador, faltas justificadas e período de apuração |
| `dias_sem_login` | fonte de autenticação/portal/AVA | Não identificada nesta rodada; manter desconhecido |

## 4. Riscos e decisões de arquitetura

1. **Conectividade:** o exemplo oficial usa Host local. Precisamos de topologia aprovada pela IES; não abrir a porta 8051 à internet.
2. **Credenciais:** Basic Auth é documentado. Usar credencial técnica de menor privilégio, segredo cifrado em repouso, rotação e redaction total de headers/logs.
3. **Contexto multiempresa:** `CODCOLIGADA`, `CODFILIAL`, `CODTIPOCURSO` e `CODSISTEMA` são obrigatórios no contexto. A configuração deve ser por tenant e por combinação autorizada; não inferir valores.
4. **Paginação:** `start/limit` aparece no recurso de parcelas. Limites máximos, ordenação estável e paginação para os demais recursos ainda não foram confirmados.
5. **Escopo somente leitura:** embora os DataServers aceitem verbos de escrita, a MIRA deve usar somente GET. Bloquear POST/PUT/DELETE no cliente HTTP, não apenas na interface.
6. **Semântica acadêmica:** nota/falta por etapa não equivale automaticamente a média global ou presença consolidada.
7. **Proveniência:** armazenar IDs externos, coligada/filial/tipo de curso, origem e timestamp real de observação por recurso. Não transformar `RECMODIFIEDON` em observação de todos os atributos sem validação.

## 5. Plano de homologação técnica

Antes de implementar o conector:
- Obter uma IES piloto com TOTVS RM e autorização formal de acesso somente leitura.
- Confirmar versão/release, módulos instalados, URL interna do Host, porta, TLS/rede privada e política de acesso remoto.
- Criar usuário técnico sem permissão de escrita e confirmar autenticação Basic.
- Confirmar valores de contexto e escopo permitido por coligada, filial, sistema e tipo de curso.
- Obter exemplos anonimizados de respostas GET para alunos, matrículas/contratos, parcelas, notas e frequência.
- Testar paginação, filtros, limites, timeout, 401/403, indisponibilidade e retomada.
- Confirmar como o RM representa parcelas pagas, parcialmente pagas, canceladas, renegociadas, estornadas e bolsas.
- Confirmar regras de notas, etapas, exames e frequência com o responsável acadêmico.
- Confirmar se existe fonte confiável de último login no Portal/AVA.

## 6. Critério de decisão

**Prosseguir para um adapter read-only** somente quando houver:
- conectividade privada aprovada;
- credencial técnica read-only;
- consulta de roster de alunos com chave estável;
- paginação/extração em lote demonstrada;
- vínculo entre aluno, matrícula/contrato e período letivo;
- semântica financeira suficiente para separar aberto, pago, cancelado e renegociado.

Se o RM não oferecer uma consulta de roster em lote adequada, avaliar um processo de exportação controlada ou um agente local que leia os DataServers autorizados. Não recorrer a acesso direto ao banco sem autorização e documentação de esquema.

## 7. Resultado desta rodada

O TOTVS RM é um candidato forte para a próxima integração, mas a documentação consultada ainda não é suficiente para construir um sincronizador seguro e completo. A evidência mais concreta nesta rodada é a consulta paginada de parcelas e a consulta de nota/falta por chave composta. A consulta de roster em lote, o contrato de autenticação/configuração por instituição e a semântica de status acadêmico/financeiro são os principais gates.

**Status:** discovery inicial concluído; implementação e homologação pendentes.
