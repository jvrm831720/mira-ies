# MIRA Educação Nativa + Portal do Aluno — Wave 1

Data: 2026-11-05. Branch: `feat/native-academic-student-portal-wave1`.

## Decisão arquitetural

**Produto único:** Vercel (Next.js + proxy) → Render (FastAPI) →
PostgreSQL existente da MIRA (Supabase). Nenhum processo Frappe,
MariaDB, Redis novo ou Docker é requerido para esta primeira Wave.

Esta implementação original **não copia literalmente** os repositórios
GPL do ERPNext/Education; migra conceitos, contratos e capacidades
desejadas para a stack MIRA. A migração de funcionalidades restantes
deverá ser feita com revisão de licença e proveniência por módulo.
O código já entregue nas PRs #146/#147/#152 **não deve ser mesclado**
junto com esta Wave sem revisão de escopo e conflito de migrations.

## Módulos e equivalência funcional (Wave 1)

| Ecossistema Frappe | Nova MIRA | Estado |
| --- | --- | --- |
| Student | `students` já existente | Reutilizado |
| Program Enrollment | `mira_academic_records.kind=enrollment` | Backend + portal somente leitura |
| Student Attendance | `kind=attendance` | Backend + portal somente leitura |
| Assessment Result | `kind=assessment` | Backend + portal somente leitura |
| Fees | `kind=fee` | **Snapshot informativo**; não é conta reconciliada |
| Portal estudante | `/portal` + `/api/v1/student-portal` | Convite manual de uso único |
| Identidade | Sessão do portal separada da sessão institucional | Implementado em código |
| Permissões e auditoria | Tenant FK composto + RLS; convite e sessão rastreáveis | Exige testes PostgreSQL reais |

A primeira Wave **não** inclui grade horária, docentes,
disciplinas/currículo, inscrições em provas, frequência granular
por aula assinada, boletins validados, emissão de documentos,
Pix, boleto, quitação, acordos, notificações ou mensagens.

## Back-end

Migration `056_native_academic_portal`, dependente de
`055_eligible_contrib_revocation`, cria:

- `mira_academic_records`: dados acadêmicos com `source=manual`,
  tipo, referência única e campos tipados, sem JSON arbitrário.
- `mira_student_portal_invites`: código de alta entropia armazenado
  apenas por hash, expira em 15 minutos, uso único, emitente rastreável.
- `mira_student_portal_sessions`: sessão revogável, expira em 8 horas,
  token armazenado apenas por hash.
- As três tabelas têm `ENABLE/FORCE ROW LEVEL SECURITY` com
  `app.tenant_id` da transação e FKs compostas que impedem associação
  de estudantes de outra instituição.

A migration assegura `UNIQUE(students.tenant_id, students.id)`.
**Pré-validar** a existência/duplicidade e tamanho da tabela na base
antes de executar `ALTER TABLE students` em produção, para evitar
surpresas com locks. Não foi aplicada em nenhum banco.

Rotas institucionais:

- `GET /api/v1/native-academic/status` — disponibilidade e tipo de backend.
- `GET /api/v1/native-academic/students/{id}/records?kind=...`
  — funcionários com `students.sensitive.view`.
- `PUT /api/v1/native-academic/students/{id}/records` — ingestão
  manual, autenticada por sessão humana e permissão `students.edit`.
  Referências `source_record_id` idempotentes dentro do tenant e tipo.
- `POST /api/v1/native-academic/students/{id}/portal-invites`
  — apenas sessão humana com `settings.manage`; não faz envio real.

Rotas exclusivas do aluno:

- `POST /api/v1/student-portal/claim` — resgata código de uso único.
- `GET /api/v1/student-portal/me` — perfil acadêmico minimizado.
- `GET /api/v1/student-portal/records?kind=...` — registros do aluno
  exclusivamente pelo vínculo da sessão, **sem** query de aluno arbitrário.
- `POST /api/v1/student-portal/logout` — revoga sessão.
  
A sessão fica em cookie `HttpOnly; SameSite=Lax`, `Secure` em
ambientes não-dev, host-only no domínio da Vercel. O proxy Next.js só
encaminha o cookie para a rota do Portal do Aluno; nunca para as rotas
administrativas. Ações POST exigem `X-Mira-Portal-Action: 1`.

## Frontend

- `/portal`: layout isolado (sem `AuthGate` administrativo);
  login com convite individual, resumo institucional, matrículas,
  frequência, avaliações, mensalidades informativas e logout.
- Ficha `/alunos/[id]`: painel de registros acadêmicos nativos e
  emissão manual de convite apenas para admins elegíveis.
- Ícones via adaptador Untitled UI da MIRA; UX branco com hierarquia
  premium.
- Nunca exibir `risk_score`, SHAP, saldo devedor agregado,
  campanhas, mensagens, números de telefone, avaliações de risco ou
  dados de outros alunos.
- Sem código externo ou tokens Frappe no browser.

## Segurança / condições para habilitar

Configuração inicial e segura (Render):
```env
NATIVE_ACADEMIC_ENABLED=false
STUDENT_PORTAL_ENABLED=false
```

**Não habilitar** antes de:

1. Aplicar a migration em PostgreSQL descartável com usuário de
   teste sem `BYPASSRLS`. Verificar `FORCE RLS` e FK com dois tenants.
2. Rodar Ruff, pytest e testes frontend, `tsc --noEmit` e
   `npm run build`; verificar o proxy cookie na Vercel Preview.
3. Verificar emissão / resgate / expiração / replay / logout /
   revogação da sessão e proteção CSRF/CORS de ponta a ponta.
4. Adicionar limitação de taxa, recuperação de acesso e política de
   **verificação real da titularidade do e-mail ou matrícula** antes
   de entregar convites de alunos reais. O botão de convite manual
   **não prova posse do e-mail**.
5. Validar logs sem tokens, auditoria de acesso, retenção e LGPD.
6. Confirmar origem acadêmica, consentimento/legitimidade e regras de
   pagamento, sem assumir que status de Fee representa quitação.
7. Garantir que toda migração pendente da `main` seja compatível;
   executar CI final no HEAD do PR, sem limite de GitHub Actions.

**Até fechar os gates acima, utilizar apenas dados sintéticos.**
Esta PR é uma **fundação funcional em código não homologada**,
não uma implantação pronta para receber alunos reais.

## Próximas Waves

**Wave 2 — domínio acadêmico completo:** programas/cursos, disciplinas,
turmas, períodos, vínculos docentes, calendário, frequência por aula,
avaliações publicadas e importação conectada aos SIS já suportados.

**Wave 3 — Portal do Aluno real:** convite com identidade comprovada,
login por OTP/MFA conforme risco, permissões documentais, histórico,
requisição acadêmica, atendimento e preferências LGPD.

**Wave 4 — financeiro:** obrigações tipadas, faturamento, conciliação,
Pix/boleto, webhooks assinados, estados não ambíguos, acordos e recibos,
sempre com autorização explícita e ambiente homologado.

## Validação local quando houver PostgreSQL de teste

```bash
cd backend
python -m compileall -q app/api/native_academic.py app/models/native_academic.py \
  alembic/versions/056_native_academic_portal.py tests/test_native_academic_portal.py
ruff check app/api/native_academic.py app/models/native_academic.py tests/test_native_academic_portal.py
alembic heads
# somente banco descartável, nunca produção:
alembic upgrade head
pytest -q tests/test_native_academic_portal.py

cd ../frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build
```

Desabilitar `AUTO_MIGRATE` no serviço Render quando for necessário
separar explicitamente migrações e deploy. **Não alterar** essa chave
no serviço atual sem auditoria; a inicialização existente pode
tentar executar Alembic automaticamente.
