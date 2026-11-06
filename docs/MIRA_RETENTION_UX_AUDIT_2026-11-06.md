# MIRA · Redesign de retenção orientado a registros (P0 → P3)
**Branch:** `feat/mira-retention-product-ux-20261106`  
**Base:** `main` em 2026-11-06. **Status:** entrega incremental para revisão; NÃO homologada.

## Referência de produto
Os arquivos HTML de referência do Attio foram examinados como repertório de interação, sem incorporação de códigos, ícones, conteúdos, layouts ou assets de terceiros. O eixo principal da MIRA continua **aluno → avaliação → timeline → intervenção → permanência**.

## P0 — Fundamento visual
- **Arquivos:** `frontend/src/app/globals.css`, `frontend/tailwind.config.ts`, `frontend/src/components/ui/button.tsx`, dashboards, Data Hub, inteligência, atividades, telas de alunos/trabalho/retenção.
- **Decisão:** tokens semânticos do produto alimentam as classes Tailwind; aliases HSL da base foram retirados. Botões suportam `primary`, `secondary`, `ghost`, `danger` com aliases legados para compatibilidade.
- **Antes → depois:** azul, tinta e bordas divergentes inline → `var(--color-blue)`, `var(--color-ink)`, `var(--color-border)`; tela escura obsoleta do overview removida; motion lento de 260 ms ajustado para 180 ms.
- **Estado:** **parcial**. Restam cores literais em páginas acadêmicas, financeiras, disparos e autenticação; a exigência "zero hex fora de tokens" não foi atingida. O escopo de auth/onboarding mantém sua identidade escura.

## P1 — Componentização e tabelas
- **Arquivos:** `frontend/src/components/work/work-activities-panel.tsx`, `work-activity-labels.ts`, `work-activity-detail-parts.tsx`, `work-queue-summary.tsx`, `work-queue-filters.tsx`, `object-index.tsx`.
- **Decisão:** extrair scorecard, filtros, rótulos e detalhes sem reescrever endpoints. `ObjectIndex` passa a aceitar ações da seleção atual e próxima ação de empty state.
- **Antes → depois:** painel com aproximadamente 1.071 linhas → componentes de fila separados e painel menor, mantendo contratos; barra genérica de seleção → encaixe reutilizável de ações.
- **Estado:** **parcial**. Restam criação/edição de atividades e detalhe para extrair; propagação do ObjectIndex para financeiro e tipografia exaustiva pendentes.

## P2 — Fluxo adaptado à retenção
- **Arquivos:** `command-palette.tsx`, `sidebar.tsx`, `students-list-page.tsx`, `risk-trend.tsx`, `risk-movements-feed.tsx`, `student-drawer.tsx`, `student-risk-factors.tsx`, `student-campaigns-panel.tsx`, `critical-list.tsx`, `frontend/src/app/(app)/page.tsx`, `frontend/src/app/(app)/retencao/page.tsx`, `frontend/src/lib/retention-selection.ts`.
- **Decisão:** busca global de alunos somente para quem já pode acessar Alunos; tendências somente com avaliações comparáveis; SHAP exposto apenas quando o backend fornece; nenhuma métrica ou fator inventado.
- **Antes → depois (descrição visual):**
  1. `⌘K`: links de módulos → links de módulos, ações autorizadas e alunos por nome/matrícula.
  2. Lista: score isolado → score com delta e feed resumido de movimentações; seleção → entrada para planejar retenção.
  3. Ficha: resumo genérico → Resumo da IA com top-3 fatores, tendência; abas Timeline de contatos, Acadêmico-financeiro, Campanhas e Contato.
  4. Central: painel de métricas sem ação → cartão de itens urgentes levando ao filtro prioritário, contexto SHAP protegido por RBAC.
- **Fluxo de seleção:** até 100 IDs na página → handoff via `sessionStorage` com escopo `tenantId`/`userId` e validade de 10 min → `/retencao?source=selection` → planejar nome, canais, grupos e simulação. O backend continua responsável por consentimento, limites e permissões. **Não foi criado envio real.**
- **Estado:** frontend conectado aos contratos existentes. **Não afirmamos execução E2E homologada contra um backend real**. Fila de alunos sem contato há 7 dias não possui implementação completa verificada.

## P3 — Feedback e confiabilidade
- **Arquivos:** `object-index.tsx`, `work-activities-panel.tsx`, `work-queue-summary.tsx`, `students-list-page.tsx`, `frontend/tests/retention-selection.test.mjs`, `frontend/tests/retention-product-experience.test.mjs`.
- **Decisão:** toasts em criação/registro de trabalho e persistência de visões, estados de carregamento, falha segura de seleção e opções de recuperação.
- **Antes → depois:** operações sem confirmação unificada → feedback contextual, estados vazios com ação e skeleton na fila.
- **Estado:** **parcial**: todos os caminhos de ação/empty/skeleton do produto ainda precisam de inventário.

## Segurança, testes e promoção
- Não há mudanças de contrato/backend nesta PR; arquivos de RLS/segurança de outro trabalho foram excluídos da branch.
- Respeitar `students.sensitive.view`, `campaigns.create`, `campaigns.view`. A UI não é a fronteira de autorização.
- Adicionados testes: expiração/isolamento do handoff, comparabilidade do score, verificação de transpilação dos componentes e guards de tema/segurança.
- **Evidência local limitada:** três testes de handoff executados em cópia equivalente da lógica passaram; **a suíte completa `node --test` e o build Next.js no HEAD ainda NÃO foram executados com sucesso**.
- O GitHub não apresentou execução de Actions para a branch; status de Vercel indicou limite de builds. Não fazer merge/deploy de produção sem gates válidos.
- Não há screenshots reais: previews não foram geradas pelo ambiente de CI; os itens antes/depois acima são descrições do diff.

### Próximos gates obrigatórios
1. Executar `npm ci && npm test && npm run lint && npx tsc --noEmit && npm run build` no `frontend` da PR.
2. Validar manualmente perfil coordenador × viewer em dois tenants: busca, SHAP, campanha e expiração da seleção.
3. Exercitar o fluxo seleção → /retencao → dry-run contra API sandbox. Confirmar zero envios reais.
4. Fechar cores remanescentes, tipografia, financeiro ObjectIndex e submódulos do painel de trabalho antes de declarar P0–P3 concluídos.
