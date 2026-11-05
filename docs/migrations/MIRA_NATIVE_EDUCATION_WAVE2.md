# MIRA Educação Nativa — Wave 2 (catálogo, aulas e boletim)

**Branch:** `feat/native-academic-curriculum-wave2` (sobre Wave 1 #154).  
**Destinos:** Next.js/Vercel + FastAPI/Render + PostgreSQL atual.  
**Sem** Frappe Bench, MariaDB, serviço ERPNext, envio ou cobrança real.

## Domínio acadêmico

Migration `057_native_academic_catalog`, dependente da 056:

| Tabela | Função | Regra de isolamento |
|---|---|---|
| `mira_academic_programs` | Curso/programa | Tenant + código único |
| `mira_academic_subjects` | Disciplinas ligadas a curso | FK composta tenant/curso |
| `mira_academic_teachers` | Docentes | Tenant + código funcional |
| `mira_academic_terms` | Períodos letivos | Datas válidas por tenant |
| `mira_academic_classes` | Turmas, docente, disciplina, período | FKs compostas |
| `mira_academic_class_enrollments` | Vínculo do aluno com turma | FK tenant/student e tenant/turma |
| `mira_academic_lessons` | Aula com início/fim e sala | Tenant/turma, publicação explícita |
| `mira_academic_attendance` | Presença/ausência/justificativa/sem registro | FKs compostas para turma/aula e aluno matriculado |
| `mira_academic_assessments` | Avaliação e nota máxima | Publicação explícita |
| `mira_academic_grades` | Nota por aluno e avaliação | FKs compostas e aprovação explícita |
| `mira_academic_calendar_events` | Eventos gerais e por turma | Escopo definido e publicação explícita |
| `mira_academic_catalog_audit` | Auditoria das importações e publicações | Append-only em API, RLS |

Todas as doze tabelas usam **ENABLE/FORCE RLS** e policy dependente de
`app.tenant_id` configurado após autenticação. A API também inclui o tenant
nas consultas e as FKs compostas rejeitam relações entre instituições.

## Endpoints

### Equipe institucional

- `GET /api/v1/native-academic/catalog/overview`
- `GET /api/v1/native-academic/catalog/drafts`
- `POST /api/v1/native-academic/catalog/batch`
  - Payload validado e limitado a 500 linhas por operação; todos os dados
    só podem ser criados pelo responsável institucional.
  - Registros de aulas, avaliações, notas e eventos entram em `draft`.
  - Não aceita `tenant_id` enviado pelo cliente: o tenant vem da sessão.
  - Erros de FK/duplicidade devem retornar 409; transação íntegra.
  - Lote é **create-only**, sem atualização ou exclusão de registros.
- `POST /api/v1/native-academic/catalog/{resource}/{id}/publish`
  - Exige permissão `critical.manage` e sessão humana.
  - Notas só são publicáveis depois de aprovação da avaliação vinculada.
  - Não altera outras integrações ou envia notificações.

### Portal do Aluno

- `GET /api/v1/student-portal/schedule` — horários de aulas publicadas.
- `GET /api/v1/student-portal/calendar` — eventos institucionais ou das
  turmas em que o estudante está vinculado.
- `GET /api/v1/student-portal/attendance` — entradas de chamada
  explicitamente registradas. **Não presume presença** por falta de dados.
- `GET /api/v1/student-portal/report-card` — notas publicadas em
  avaliações publicadas, do aluno autenticado. Não deriva média final.

**O aluno nunca informa `student_id`, `tenant_id` ou turma arbitrária.**
As consultas derivam apenas da sessão de portal validada na Wave 1.

## Experiência visual

`/academico` na navegação institucional:
- KPIs de cursos, disciplinas, docentes, turmas, aulas e notas;
- criação guiada de curso, disciplina, professor, período, turma, aula,
  avaliação e evento;
- fila de publicação separada, para aprovação;
- estados vazios, sem afirmar que integração está ativa quando desligada.

`/portal` (experiência separada):
- Horários, calendário, frequência por aula e boletim;
- Datas exibidas em pt-BR, sem armazenar datas locais sem fuso;
- Indicadores ausentes não são transformados em zero ou em situação boa;
- Apenas notas e aulas explicitamente publicadas.

## Flags e política de deploy

```env
NATIVE_ACADEMIC_ENABLED=false
STUDENT_PORTAL_ENABLED=false
NATIVE_ACADEMIC_CATALOG_ENABLED=false
```

As três opções permanecem **false** até executar migrations e testes.
O frontend recebe 503/empty states verídicos; sem dados inventados.

`frontend/vercel.json` desliga deployments automáticos na branch
`main` até aprovação de homologação. Não habilitar por descuido; na
primeira liberação autorizada, configurar `git.deploymentEnabled.main=true`
ou remover o override. Render pode ser impedido de auto-deploy no merge
com a mensagem `[skip render]`.

## Gates de validação

1. Executar Alembic `heads` e upgrade 056→057 em PostgreSQL descartável,
   com usuário não-superusuário sem BYPASSRLS.
2. Testar FK composta entre duas IES; negar enrollment de aluno de outro tenant
   e referências cruzadas em presença e notas.
3. Testar leitura apenas de calendário/turmas visíveis ao aluno da sessão;
   avaliações e notas não publicadas nunca podem aparecer.
4. Executar Ruff + pytest; TypeScript + lint + build Next.js;
   confirmar ausência de falhas RLS e compatibilidade dos componentes.
5. Testar rate limiting, emissão de convite, comprovação de titularidade,
   revogação e sessão; manter Portal desligado até isso passar.
6. Revisar catálogo de maturidade, origem SIS e legislação/termos
   para cada dado. Não afirmar homologia completa com ERPNext/Frappe.
7. Não executar migration, merge ou deploy de Wave 2 em produção sem
   verificação do HEAD final.

## Escopo ainda pendente

- UI operacional de lançamento de presença por turma e publicação de
  boletins com regras específicas por curso;
- médias ponderadas, faltas calculadas a partir de carga horária,
  históricos acadêmicos validados e homologação de certificados;
- documentos, solicitações, recuperação de conta/OTP com prova
  de identidade e serviços financeiros/Pix/boleto;
- auditoria append-only em nível de banco para o catálogo,
  políticas LGPD e provedor de comunicação de produção.

A Wave 2 cria uma base nativa **inicial** para estes fluxos, não a
totalidade das funcionalidades do Frappe Education.
