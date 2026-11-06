# MIRA — Wave P1 | Portal do Aluno: Product Experience

## Escopo, origem e isolamento

- Base: `main` em `d2c3a1f3fe61e7ac3e40b15489a363781b31ad51` (Wave 0.0 já mesclada).
- Branch: `feat/product-design-student-portal`. Não altera componentes `object-index/`, a página administrativa `/alunos`, sidebar institucional, autenticação, esquema do banco ou regras de negócio. Duas APIs estudantis recebem somente uma restrição de visibilidade de observações institucionais, sem mudar a forma das respostas.
- Referências visuais: ZIPs de HTML da Attio (Empresas, registro com inspector e workflows). Adotados composição compacta, hierarquia concisa, navegação lateral discreta, superfícies paper-white, status contextual, foco por teclado e baixa ornamentação. Nenhum código/asset/branding proprietário foi reutilizado.
- Design System: `docs/DESIGN_SYSTEM.md`, Wave 0.0, guia acadêmico Wave 5/6.

## Discovery — contratos preservados

| Domínio | Frontend existente | API utilizada | Segurança / limite |
| --- | --- | --- | --- |
| Sessão | `/portal/page.tsx` | `/api/v1/student-portal/me`, `/claim`, `/logout` | Convite por fragmento, removido da URL; cookie revogável; ação exige cabeçalho contextual |
| Registros institucionais | `/portal/page.tsx` | `/student-portal/records?kind=...` | Retorna exclusivamente estudante autenticado; `fee` é snapshot, sem comprovar quitação |
| Aulas e eventos | `/portal/page.tsx` | `/student-portal/schedule`, `/calendar` | Retorna apenas registros publicados; endpoint pode falhar fechado em homologação |
| Notas e frequência | `/portal/page.tsx` | `/student-portal/report-card`, `/attendance` | Somente registros publicados, sem editar notas/chamadas |
| Matrícula/rematrícula | `/portal/academic-operations-panel.tsx` | `/student-portal/academic-operations/*` | Solicitação é distinta de efetivação; backend valida vínculo, vagas e elegibilidade |
| Requerimentos | `/portal/student-services-panel.tsx` | `/student-portal/services/requests`, `/detail`, `/history`, `/comments`, `/attachments` | Detalhe e anexos limitados à identidade da sessão; timeline exibe apenas estados/datas |
| Documentos | `/portal/student-services-panel.tsx` | `/student-portal/services/documents`, `/proof`, `/api/v1/public/academic-documents/verify` | Prévia textual não é PDF assinado; verificação de integridade não equivale à assinatura |
| Financeiro | `/portal/student-services-panel.tsx` | `/student-portal/services/financial`, `/asaas/charges`, `/instructions` | Snapshot financeiro separado da cobrança emitida; pagamento e split só confirmados por indicadores de backend |

Os endpoints vêm de `academic_portal.py`, `academic_operations.py`, `student_services.py`, `student_service_operations.py`, `student_payments.py` e `student_document_attestation.py`. O frontend não recebe `tenant_id`/`student_id` livre para construir URLs de terceiros.

## Experiência implementada

- **PortalShell independente**: sidebar desktop, header compacto, rolagem horizontal de navegação móvel, atalhos de seção, skip link, estados `aria-current`, foco visível e baixo movimento.
- **Início**: saudação com nome e instituição reais, resumo de curso, matrícula, semestre, status, frequência/média somente se fornecidos, próximas aulas filtradas por data real e até 3 solicitações recentes do endpoint oficial. Evita alegar que aulas históricas são eventos futuros.
- **Minha jornada**: identidade acadêmica, matrículas registradas e o painel de matrícula/rematrícula e histórico operacional já autorizado.
- **Disciplinas**: notas e frequência divulgadas pela instituição, com classificação clara dos registros adicionais, mantendo operações somente de leitura.
- **Calendário**: alternância entre aulas e eventos, datas informadas pela API, sem inventar calendário semanal/recorrência.
- **Solicitações**: listagem e composição explícita de novo requerimento, comentários/anexos existentes, histórico em timeline com status e data. Notas internas de eventos institucionais não são renderizadas **nem serializadas ao estudante**; permanecem no contrato institucional. Testes cobrem a política fail-closed.
- **Documentos**: listas, verificação de integridade e prévia textual reais, sem afirmar que há PDF assinado.
- **Financeiro**: separação de registros financeiros informativos, cobranças oficiais Asaas e registros históricos; mantém confirmação do repasse distinta da confirmação do pagamento.
- **Minha conta**: dados associados à sessão e ação de logout existente.

As views continuam na rota única `/portal` (navegação interna por estado). Deep links de seção, virtualização, downloads PDF oficiais e um calendário semanal dependem de escopo específico.

## Estados e limites

- A implementação trata carregamento, erro, vazio, módulo em homologação, sessão expirada, envio e confirmação após resposta real do servidor.
- O componente de serviços tem `initialView` e `standalone` para ser reutilizado por seção sem replicar integrações.
- As listagens respeitam os limites atuais da API (por exemplo, até 100 solicitações). Não mostram totais ilimitados como exaustivos.
- Nenhum registro fictício. Nenhum disparo, cobrança, criação de Pix, mudança de destino/split, migração ou deploy de produção.
- Se um módulo estiver desabilitado, manter estado de indisponibilidade em vez de simular sucesso.

## Quality gate antes de merge

1. CI frontend: `npm ci`, lint, `node --test`, `npx tsc --noEmit`, build.
2. CI backend: Ruff, Alembic, testes, incluindo suites de sessão do Portal, operações acadêmicas, serviços, documentos e pagamentos. Sem banco de produção.
3. Testes de regressão: `backend/tests/test_student_portal_event_visibility_wavep1.py` (somente observações do próprio estudante podem ser divulgadas).
4. QA autenticado em desktop (1280px), tablet e mobile (375px) com estudante com e sem dados; testar convite, troca de seção, sessão expirada, solicitação, comentários, anexos e downloads autorizados.
5. Verificar casos de erro 401/403/503, registro ausente, notas não publicadas, ausência de valor financeiro, ambiente sandbox e confirmações distintas.
6. Revisar diff e status final do CI no HEAD da PR. Sem merge por bypass administrativo.

Sem QA autenticado real, registrar essa limitação; capturas HTML de referência não são evidência de implantação da MIRA.
