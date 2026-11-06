# Wave 5 — Central de Serviços Acadêmicos

## Entrega

A MIRA reutiliza a solicitação criada pelo aluno em `/api/v1/student-portal/services/requests`. O mesmo registro `mira_student_service_requests` agora percorre uma operação institucional auditável.

**Tela institucional:** `/academico/servicos`. **Portal do Aluno:** `/portal` → Serviços → Solicitações.

### Processo operacional

1. O aluno envia um pedido. Seu identificador e tenant vêm exclusivamente da sessão revogável do Portal do Aluno; não vêm de parâmetros do formulário.
2. A equipe vê a fila no workspace correto. Atribuir exige `students.edit`, membro ativo no mesmo tenant, prioridade e prazo UTC válido. A primeira atribuição muda `submitted → in_review`.
3. A equipe responde em comentários visíveis ao aluno ou notas internas. Anexos seguem a mesma regra de visibilidade. Histórico de mudanças, comentários e anexos são append-only no PostgreSQL.
4. Um aprovador com `critical.manage` escolhe `approved` ou `rejected` e informa a justificativa (visível ao aluno). Transições são pessimisticamente bloqueadas com `SELECT FOR UPDATE`.
5. Para pedidos de declaração, histórico ou matrícula: após aprovação, a equipe gera rascunho com modelo institucional, revisa e publica no fluxo documental existente. **A solicitação não pode ser concluída antes da publicação.**
6. O aluno acompanha respostas, documentos publicados, anexos e atualizações; pode responder e anexar enquanto o pedido está aberto.
7. O responsável atribuído e o aluno recebem **notificações internas**, consultáveis em suas próprias sessões. Nenhum provedor externo é invocado.

### Estados

`submitted → in_review → approved → completed`

`submitted` e `in_review` podem ser cancelados; `in_review` pode ser rejeitado; `approved` pode ser cancelado. Estados terminais não aceitam edição, comentários ou novos anexos.

### Modelo de dados / migration

A migration `064_academic_services_central` adiciona responsável via `mira_memberships`, prioridade, prazo, data de conclusão e vínculo de documento; cria comentários, anexos, notificações e modelos. Relações entre entidades são amarradas ao `tenant_id`; todas as tabelas novas usam PostgreSQL RLS e FORCE RLS. Eventos e evidências possuem triggers de imutabilidade.

### Permissões

| Operação | Permissão existente |
| --- | --- |
| Ver fila, conteúdo e notificações | `students.sensitive.view` |
| Atribuir, comentar, anexar, gerar rascunho | `students.edit` |
| Aprovar/rejeitar/concluir e publicar documento | `critical.manage` |
| Criar/editar modelos | `settings.manage` |

Os endpoints institucionais também requerem sessão humana e workspace de instituição de ensino. O Portal do Aluno usa sessão independente e identidade derivada somente do cookie autenticado; os anexos internos não são visíveis a estudantes.

### Limites de anexos

Arquivos binários PDF/JPG/PNG: até **256 KiB** por arquivo, até **5 arquivos** por solicitação, validados por tipo declarado e assinatura de formato. Os binários ficam no PostgreSQL sob RLS; downloads exigem sessão, são `attachment` (não inline) e retornam `no-store`, `nosniff` e CSP sandbox.

**Para arquivos maiores e liberação ampla em produção:** prever object storage privado, antivírus/varredura de conteúdo, quotas e retenção/LGPD. A implementação atual não alega varredura antimalware externa.

### Documentos

Os modelos substituem somente variáveis permitidas:
`{{student_name}}`, `{{registration}}`, `{{organization_name}}`, `{{today}}`, `{{request_subject}}`, `{{request_description}}`. Não há execução de expressões ou HTML. O resultado é **texto**, não PDF oficial. A emissão verificável (attestation) da Wave 4 é um fluxo separado e não é chamada automaticamente.

### Homologação e rollout

- Backend protegido pelos flags existentes: `NATIVE_ACADEMIC_ENABLED`, `STUDENT_PORTAL_ENABLED`, `NATIVE_ACADEMIC_SERVICES_ENABLED`. Não alterar esses flags sem aprovação.
- Aplicar `alembic upgrade head` em banco de homologação e testar migração 063, RLS com role não-superuser e a conexão com o Portal.
- Validar responsividade e acessibilidade da fila no preview.
- Nenhum envio WhatsApp/email, reconciliação financeira, pagamento, liberação de assinatura ou deploy em produção faz parte desta entrega.
- A validação automática no CI utiliza PostgreSQL 16, Ruff, pytest, frontend lint, testes, TypeScript e Next build.

## API — principais endpoints

Instituição (prefixo `/api/v1/native-academic/services`):
`GET /queue`, `GET /staff`, `GET /requests/{id}/detail`, `POST /requests/{id}/assign`, `POST /requests/{id}/review`, `POST /requests/{id}/comments`, `POST /requests/{id}/attachments`, `GET /requests/{id}/attachments/{file_id}`, `GET /templates`, `POST /templates`, `PUT /templates/{id}`, `POST /requests/{id}/document-draft`, `POST /documents/{id}/publish`, `GET /notifications`, `POST /notifications/{id}/read`.

Portal do Aluno (prefixo `/api/v1/student-portal/services`):
`POST /requests`, `GET /requests`, `GET /requests/{id}/history`, `GET /requests/{id}/detail`, `POST /requests/{id}/comments`, `POST /requests/{id}/attachments`, `GET /requests/{id}/attachments/{file_id}`, `GET /notifications`, `POST /notifications/{id}/read`.
