# Contrato de dados para importação da MIRA

## Objetivo

Definir o que a importação atual consegue validar e quais regras precisam existir antes de combinar arquivos de origens diferentes. Este documento descreve o código atual; não habilita persistência de múltiplas bases.

## O que o modelo atual suporta

A ingestão normaliza cabeçalhos por aliases determinísticos, aceita mapeamento manual e transforma as linhas em um registro de aluno. Os campos canônicos estão definidos em `backend/app/services/ingestion.py`.

| Grupo lógico | Campos canônicos existentes | Situação atual |
| --- | --- | --- |
| Identidade | `matricula`, `nome` | Obrigatórios para cada arquivo pré-validado |
| Cadastro | `curso`, `turma`, `semestre`, `forma_ingresso` | Opcionais no registro de aluno |
| Financeiro | `dias_atraso_boleto`, `recorrencia_atrasos` | Opcionais no registro de aluno |
| Engajamento | `dias_sem_login`, `presenca_percentual` | Opcionais no registro de aluno |
| Desempenho acadêmico | `nota_media`, `reprovacoes` | Opcionais no registro de aluno |
| Contato e preferência | `telefone`, `email`, `communication_opt_out` | Opcionais; opt-out exige cuidado para não sobrescrever consentimento |

Esses grupos são uma classificação lógica dos campos que já existem, não tipos de arquivo implementados. Hoje, cada arquivo enviado para `POST /api/v1/upload/preview-multiple` é validado como se fosse uma planilha de alunos e precisa conter matrícula e nome. O parâmetro `file_roles` é devolvido na resposta, mas ainda não controla o mapeamento nem valida relacionamentos.

## Chave de relacionamento

- A única chave que o fluxo atual usa para encontrar um aluno existente é `matricula`, sempre escopada ao `tenant_id` autenticado.
- A matrícula é lida como texto para preservar zeros à esquerda.
- Nome, e-mail, telefone, curso ou turma não devem ser usados como chaves de junção implícitas.
- Antes de combinar arquivos, a MIRA deve normalizar a matrícula com uma regra documentada, identificar matrículas ausentes e duplicadas em cada arquivo e mostrar correspondências e não correspondências.
- Se uma instituição não tiver uma matrícula estável e compartilhada entre suas bases, a combinação deve ser bloqueada ou encaminhada para configuração explícita; não se deve adivinhar a identidade do aluno.

## Regras de integridade a definir na implementação

1. **Tipo de arquivo:** permitir que o usuário declare a finalidade de cada arquivo, mas validar o conteúdo contra os campos esperados desse tipo.
2. **Identidade:** um arquivo de cadastro pode exigir matrícula e nome; arquivos complementares devem poder trazer matrícula e somente os campos do seu domínio, sem exigir um nome repetido.
3. **Conflitos:** quando dois arquivos trazem valores diferentes para o mesmo aluno e campo, não escolher silenciosamente um deles. Mostrar o conflito e exigir uma regra explícita de precedência ou revisão.
4. **Duplicidades:** sinalizar matrícula repetida dentro de um arquivo e entre arquivos. Não aplicar automaticamente a regra atual de “última ocorrência vence” entre fontes diferentes.
5. **Campos vazios:** manter a regra atual de que valores ausentes não devem apagar dados existentes; tratar separadamente valores explícitos de consentimento e opt-out.
6. **Isolamento:** toda consulta e escrita deve continuar limitada à instituição autenticada.
7. **Prévia consolidada:** apresentar contagens de criar, atualizar, manter, rejeitar e revisar, com os motivos por arquivo e por matrícula.
8. **Persistência:** só habilitar importação conjunta depois que a operação consolidada puder ser gravada de forma idempotente, auditável e segura diante de falha parcial.

## Estado da funcionalidade

### Implementado

- Prévia de um arquivo com mapeamento determinístico e manual.
- Validação de matrícula e nome, normalização de campos conhecidos, avisos e detecção de duplicidades dentro do arquivo.
- Consulta de correspondências existentes por matrícula e instituição.
- Endpoint de pré-validação de até 10 arquivos, sem persistência.
- Interface para selecionar arquivos e visualizar os resultados individuais da pré-validação.

### Ainda não implementado

- Tipos de base com contratos de campos distintos.
- Arquivos complementares sem coluna de nome.
- Junção e validação cruzada entre arquivos.
- Resolução de conflitos entre fontes.
- Prévia consolidada de uma operação conjunta.
- Persistência atômica/idempotente de múltiplas bases e recuperação de falhas parciais.

## Critério de aceite da próxima fase técnica

Antes de implementar a junção, adicionar testes para: arquivo complementar sem nome; matrícula com zeros à esquerda; matrícula ausente; duplicidade dentro e entre arquivos; conflito de valores para o mesmo campo; aluno que só aparece em uma base; isolamento entre instituições; e ausência total de gravações durante a prévia.

**Não declarar uma operação conjunta válida nem permitir sua confirmação até que esses critérios estejam cobertos por código e testes.**
