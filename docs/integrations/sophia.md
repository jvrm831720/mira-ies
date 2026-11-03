# Integração SophiA (Prima) — dossier técnico e plano de homologação

**Status:** descoberta técnica iniciada; implementação da API bloqueada até receber a documentação da instalação/versão da instituição.  
**Branch:** `feat/sophia-native-integration`  
**Modo previsto:** somente leitura.

## 1. Identificação do produto

O nome SophiA é usado em mais de um produto/módulo. Este dossier trata do ERP acadêmico **SophiA Gestão Escolar Web**, da Prima, e não presume compatibilidade com SophiA Biblioteca Web/Philos.

A instituição precisa confirmar:
- produto e edição exatos (Gestão Escolar Web, versão/build);
- URL/base URL da instalação;
- versão e disponibilidade do módulo Web API;
- módulos/recursos licenciados e habilitados;
- documentação técnica correspondente à instalação.

## 2. Evidências públicas e limites

### Confirmado por fontes públicas
- O site oficial da SophiA descreve um ecossistema com APIs RESTful/Web Services e processo de avaliação/homologação técnica de parceiros.
- A documentação pública de integração da Agenda Edu para SophiA Gestão Escolar informa que o módulo API deve ser habilitado pelo fornecedor e que a instituição disponibiliza URL, usuário e senha da integração.
- O repositório MIRA já contém um transformer legado `SophiaConnector` em `backend/app/services/connectors/erp.py`, com aliases de campos como `cod_aluno`, `nome`, `curso`, `serie`, `media`, `frequencia` e `vl_atraso`. Esses aliases são apenas heurísticas históricas; **não são um contrato oficial nem evidência de que os endpoints retornem esses campos**.

### Ainda não confirmado
Não há documentação pública oficial consultada que permita afirmar, para a versão de Gestão Escolar Web da instituição:
- rotas e métodos exatos para alunos, matrículas, cursos, turmas, notas, frequência ou financeiro;
- formato de autenticação, token, expiração/renovação e escopos;
- parâmetros e mecanismo de paginação;
- filtros incrementais, ordenação ou timestamps por campo;
- limites de requisição, quotas ou política de retry;
- semântica de situação financeira, parcelas, notas, frequência e status acadêmicos.

**Não implementar chamadas com endpoints presumidos.** A documentação pública encontrada para SophiA Biblioteca Web/Philos pertence a outro produto e não deve ser reutilizada como contrato da API do ERP.

## 3. Fontes consultadas

1. SophiA — Parcerias e Integrações (site oficial): https://sophia.com.br/integracoes/
   - Descreve APIs RESTful/Web Services e avaliação técnica de parceiros.
2. Agenda Edu — Como habilitar a integração SophiA <> Agenda Edu:
   https://atendimento.agendaedu.com/hc/pt-br/articles/11104377528987-Como-habilitar-a-integra%C3%A7%C3%A3o-SophiA-Agenda-Edu
   - Orienta habilitar o módulo API e obter URL, login e senha na área de integrações. Fonte de terceiro; útil para requisitos operacionais, não para definir o contrato da API.
3. Agenda Edu — Como solicitar a integração:
   https://atendimento.agendaedu.com/hc/pt-br/articles/12935986823067-Como-solicitar-a-integra%C3%A7%C3%A3o-do-sistema-de-gest%C3%A3o-SophiA-com-a-Agenda-Edu
   - Confirma dependência do módulo API, credenciais e parametrização com a instituição.
4. Repositório MIRA — `backend/app/services/connectors/erp.py`
   - Transformer legado; não representa documentação oficial do fornecedor.

## 4. Pacote necessário para homologação

Solicitar à instituição/Prima por canal seguro:
- documentação da API da **mesma versão** instalada;
- URL de base e ambiente (produção/homologação, se houver);
- mecanismo de autenticação e processo de rotação/revogação;
- usuário técnico dedicado, somente leitura, com escopo mínimo;
- lista de módulos/recursos autorizados;
- exemplos sanitizados de request/response para cada recurso;
- política de paginação, filtros, limites, timeout e erros;
- confirmação do fuso horário e semântica dos timestamps;
- dicionário de dados e regras de negócio para status acadêmico/financeiro;
- confirmação formal de que a conta pode consultar dados necessários à MIRA.

Não enviar senha ou token em issue, PR, chat, log ou arquivo versionado. Credenciais reais serão cadastradas apenas pelo fluxo seguro da MIRA após implementação e revisão.

## 5. Contrato de dados a validar

| Domínio | Dados desejados | Condição para mapear |
|---|---|---|
| Identidade | código do aluno, matrícula/RA, nome | chave estável e escopo da instituição confirmados |
| Vínculo | matrícula, curso, turma, unidade/campus, período, status | distinguir aluno de matrícula e múltiplos vínculos |
| Financeiro | parcelas, vencimento, valor, situação, pagamentos | estados documentados; não inferir pago/aberto por ausência |
| Frequência | aulas previstas, presentes/faltas, disciplina, período | denominador e granularidade confirmados |
| Desempenho | avaliações/notas, escala, disciplina, período | pesos, escala e agregação confirmados |
| Acesso | último login/evento | timestamp e definição do evento explicitamente fornecidos |

Todos os campos devem preservar valor bruto, origem e proveniência. Ausência de dado permanece desconhecida; não preencher com zero ou valor favorável.

## 6. Arquitetura prevista (após validação do contrato)

- Uma conexão por tenant, com credenciais cifradas no backend.
- URL HTTPS validada e protegida contra SSRF; redirects desabilitados.
- Cliente HTTP assíncrono com timeout, limites configuráveis, retry seletivo e respeito a `Retry-After`.
- Teste de conexão que valida autenticação e acesso mínimo aos recursos habilitados, sem baixar uma base completa.
- Worker Redis com jobs assíncronos, checkpoints persistidos após gravação, retomada e idempotência.
- Watermark independente por recurso somente se a API oferecer filtro incremental confiável.
- Isolamento por tenant no backend e no banco (RLS/FORCE RLS, conforme padrão atual).
- Segredos nunca retornados à UI ou registrados em logs.
- Escrita na API do fornecedor proibida.

## 7. Sequência de implementação

1. **Discovery/homologação:** obter contrato oficial e exemplos sanitizados da instalação real.
2. **Contrato e testes de fixture:** validar paginação, autenticação, schemas e semântica com payloads sem dados pessoais.
3. **Backend:** cliente somente leitura, criptografia de credenciais, modelo/configuração por tenant, migration RLS, rotas de teste e sync.
4. **Pipeline:** mapeamento canônico, proveniência por campo, fila/checkpoints, limites e retomada.
5. **Frontend:** configurar conexão, testar, exibir cobertura/progresso e erros seguros.
6. **Validação:** testes unitários, integração simulada, isolamento multi-tenant, CI e revisão de segurança.
7. **Homologação real:** sync controlada de pequeno volume, conferência de contagens e semântica com a instituição.
8. **Ativação:** somente após revisão; não habilitar scoring automaticamente.

## 8. Critérios de aceite

- Endpoints e schemas vêm da documentação da versão homologada, sem suposições.
- Conexão e sincronização são isoladas por tenant.
- Segredos cifrados e nunca expostos.
- Sync somente leitura, paginada, retomável e idempotente.
- Nenhum truncamento silencioso quando a paginação falhar.
- Dados desconhecidos/inválidos não são convertidos em valores favoráveis.
- Proveniência e timestamps de observação são preservados; horário de importação não substitui observação.
- Testes cobrem autenticação, erros, rate limit, paginação, checkpoint, retry, tenant isolation e mapeamento.
- Scoring permanece desabilitado para atributos não homologados.

## 9. Próxima dependência externa

A implementação do cliente real depende de receber a documentação técnica e exemplos sanitizados da API SophiA Gestão Escolar Web usada por uma instituição. Até lá, esta branch contém apenas o dossier e não deve criar credenciais, migrations, endpoints presumidos ou sincronizações reais.
