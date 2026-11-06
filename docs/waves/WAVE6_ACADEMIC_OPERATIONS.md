# Wave 6 — Jornadas acadêmicas completas

## Dependência e ativação
PR Wave 6 depende da Wave 5 (#165). O banco deve ter a revisão **064_academic_services_central** antes de **065_academic_operations**.

O módulo novo é isolado pelo flag `NATIVE_ACADEMIC_OPERATIONS_ENABLED=false` por padrão, além de `NATIVE_ACADEMIC_ENABLED` e `NATIVE_ACADEMIC_CATALOG_ENABLED`. O Portal do Aluno continua exigindo `STUDENT_PORTAL_ENABLED`.

A experiência não é criada a partir de dados fictícios. A MIRA utiliza somente o catálogo, as matrículas e os lançamentos confirmados de cada instituição. Os registros legados permanecem no banco, mas os lançamentos diretos de matrícula, nota e presença pelo importador são bloqueados quando o novo flag estiver habilitado.

## Experiência institucional
Acesso: `/academico/jornadas` no menu **Acadêmico → Jornadas acadêmicas**. Abas:

- **Regras**: configurar versão de política institucional, nota mínima, frequência mínima, quantidade de disciplinas, janela de matrícula, tratamento de faltas justificadas e permissão de rematrícula. Criação de rascunho exige `settings.manage`, publicação exige `critical.manage`. Versões publicadas são imutáveis.
- **Grade curricular**: cadastrar e publicar uma matriz por curso, com disciplina obrigatória, período e pré-requisito. Várias matrizes coexistem; cada vínculo mantém sua versão. Dependências cíclicas e pré-requisitos de outros cursos são rejeitados.
- **Matrículas**: buscar aluno ativo, vincular a curso e matriz publicados; receber solicitações da secretaria e do próprio aluno; justificar e aprovar/rejeitar como ato humano. Cada aprovação revalida a política vigente, oferta, vagas, duplicatas e pré-requisitos, com bloqueio transacional nas turmas.
- **Ofertas**: abrir ou fechar turmas existentes e configurar capacidade, sob aprovação institucional. Vagas sem limite definido são informadas como tal; não são inventadas.
- **Diário de classe**: lançar notas (inicialmente rascunho), publicar notas da avaliação com todos os alunos, registrar presença/falta/justificativa em aulas publicadas e verificar a integridade antes de encerrar a turma.
- **Históricos**: resultados finalizados por aluno, com versão da regra acadêmica e percentual da nota e frequência. Não equivalem a documento oficial.

## Experiência do aluno
Em `/portal`, a seção **Sua jornada acadêmica** mostra vínculos reais, períodos disponíveis, ofertas abertas, solicitação de matrícula/rematrícula, status e decisão da secretaria, e histórico de disciplinas encerradas.

O aluno não escolhe `student_id` nem `tenant_id` nos endpoints do portal: a identidade é derivada da sessão estudantil revogável. O envio exige o cabeçalho anti-CSRF do portal. Contestações e exceções são direcionadas a **Serviços do aluno → Revisão acadêmica**, já existente na Wave 5.

## Motor de regras e integridade

Política versionada, por tenant, com campos tipados:
`passing_percent`, `min_attendance_percent`, `max_classes_per_term`, `excused_excluded`, `allow_reenrollment`, `enrollment_opens_on`, `enrollment_closes_on`.

- Nova matrícula é **solicitada**, não confirmada automaticamente. A aprovação usa `SELECT FOR UPDATE` no pedido e nas turmas ordenadas para conferir capacidade de forma serializada.
- O primeiro pedido aprovado para um vínculo de curso é matrícula; nos períodos seguintes, rematrícula, quando permitida.
- Matrícula em disciplina com pré-requisito só é possível após **resultado final imutável** de aprovação na disciplina anterior. Uma presença desconhecida ou nota ausente nunca conta como aprovação.
- A nota final é a soma das pontuações / soma das pontuações máximas das avaliações **publicadas**; a frequência decorre das aulas **publicadas** com registros individuais. Ausência de qualquer lançamento torna o resultado **incompleto**, não zero nem aprovado.
- Justificativas podem ser removidas do denominador somente conforme a política publicada. Se não houver aula computável, o cálculo falha de modo seguro.
- Encerramento da turma exige todas as avaliações, notas e aulas publicadas e toda a frequência registrada. O resultado final preserva um snapshot da política aplicada e não pode ser editado ou excluído pelo fluxo regular.
- Publicação tardia em turma encerrada é bloqueada no catálogo, mesmo para registros legados.
- A matriz e a regra são imutáveis depois de publicadas (triggers PostgreSQL).

## Banco e segurança

Migration `065_academic_operations`:
- `mira_academic_policies`
- `mira_academic_curricula`
- `mira_academic_curriculum_items`
- `mira_academic_student_programs`
- `mira_academic_enrollment_requests`
- `mira_academic_enrollment_request_classes`
- `mira_academic_class_outcomes`
- `mira_academic_operation_events`

Todas as tabelas possuem FKs compostas por `tenant_id`, RLS habilitada e forçada, e policies dependentes de `app.tenant_id`. Auditorias e resultados finais usam triggers de imutabilidade. O vínculo (tenant, turma, aluno) do resultado final é protegido também por FK com a matrícula de turma.

As operações institucionais exigem sessão humana **MFA AAL2**, além de permissões RBAC existentes:
- ver fila, turma e histórico: `students.sensitive.view`;
- criar matrícula, registrar chamada/notas: `students.edit`;
- decidir, publicar, encerrar e ofertar turma: `critical.manage`;
- definir política e matriz: `settings.manage`.

## Limites conscientemente explícitos

- A primeira entrega suporta até 30 disciplinas por pedido, 300 alunos por diário, 100 avaliações e 150 aulas por turma. O fechamento falha em vez de processar uma parte da turma.
- A média final usa a soma das pontuações das avaliações; regras complexas de pesos, recuperação, equivalência de estudos, dependência/cursar novamente, aproveitamento de créditos e currículos especiais exigem uma futura política aprovada e verificada.
- Um pedido por vínculo/curso/período; rejeições ou exceções exigem requerimento formal na Wave 5, em vez de reenvio silencioso.
- Não há integração automática financeira nem bloqueio por pagamento sem uma fonte homologada; não é correto inferir adimplência.
- Sem envio de e-mail, WhatsApp, publicação de PDF oficial, assinaturas eletrônicas ou deploy automático de migrations.

## API

Instituição: prefixo `/api/v1/native-academic/operations`.
`GET /overview`; `POST /policies`, `POST /policies/{id}/publish`;
`POST /curricula`, `GET /curricula/{id}`, `POST /curricula/{id}/publish`;
`GET /students/search?q=`, `GET /students/{id}/programs`, `POST /programs/enroll`;
`POST /classes/{id}/offer`, `GET /programs/{id}/offers?term_id=`;
`GET/POST /enrollment-requests`, `POST /enrollment-requests/{id}/decide`;
`GET /classes/{id}/roster`, `POST /classes/{id}/grades`,
`POST /classes/{id}/grades/publish`, `POST /classes/{id}/attendance`,
`GET /classes/{id}/closing-preview`, `POST /classes/{id}/close`;
`GET /students/{id}/transcript`.

Portal: prefixo `/api/v1/student-portal/academic-operations`:
`GET /programs`, `GET /terms`, `GET /programs/{id}/offers?term_id=`,
`GET/POST /enrollment-requests`, `GET /transcript`.

## Validação obrigatória
- PostgreSQL 16 e migrations encadeadas **063 pagamentos → 064 serviços → 065 operações**; nenhuma migração em produção é automática nesta PR.
- Testes de regras, tentativa entre tenants, lista de presença desconhecida, matrículas, vagas, pré-requisitos, publicação de notas, encerramento e histórico.
- CI Ruff, pytest completo, frontend ESLint, TypeScript e Next.js build no HEAD final.
- Depois de aprovação da Wave 5 e da Wave 6, validar dados e fluxos com uma instituição piloto antes de ativar o flag em produção.
