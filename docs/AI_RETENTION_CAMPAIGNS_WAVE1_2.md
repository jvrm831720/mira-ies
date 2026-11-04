# Campanhas inteligentes — Wave 1.2

## Entrega
- Propostas persistidas em `retention_campaign_proposals`, sempre em estado `draft`.
- Criação para um ou mais dos sete grupos, com deduplicação por `student_id`.
- Snapshot da audiência com grupos de origem, elegibilidade por canal, bloqueios, ação interna e data da intervenção recente.
- Hash SHA-256 canônico para verificar a integridade do snapshot.
- Trigger PostgreSQL impede alteração ou exclusão direta do snapshot, hash, grupos de origem, versão do catálogo, motor e contagens; exclusão em cascata por remoção do tenant permanece permitida.
- Tenant scoping em criação, listagem e leitura.
- Proposta registra objetivo, estratégia, canais, cadência e briefing derivados das oportunidades existentes.

## Validação de audiência
- A criação é recusada quando a avaliação de grupos está truncada ou incompleta.
- O motor canônico de grupos é reutilizado; somente estado `TRUE` entra no snapshot.
- Alunos presentes em vários grupos aparecem uma única vez, com todos os grupos confirmados.
- Opt-out global bloqueia contato.
- A elegibilidade calculada representa somente contato tecnicamente válido e preferências operacionais; não comprova consentimento nem base legal. Toda proposta declara `communication_authorization_status=not_verified` e exige revisão da instituição antes de qualquer futura aprovação.
- Preferências de canal/finalidade são aplicadas por `is_communication_allowed`.
- E-mail e telefone são validados sem persistir os valores de contato no snapshot.
- Intervenções `sent`, `sending` ou `unknown` nos últimos sete dias bloqueiam novos contatos nesta proposta.
- `missing_score` permanece ação interna e nunca libera outreach por si só.
- Contagens de alcance elegível, bloqueado e ação interna são separadas.

## Limites
- A proposta é um rascunho; não tem aprovação, agendamento nem execução.
- Nenhuma integração de canal é chamada e nenhum envio é possível por estes endpoints.
- Listagem e leitura também exigem papel `coordinator` ou superior.
- A proposta não constitui autorização legal para comunicação; a comprovação de base legal/consentimento ainda não existe neste modelo.
- O snapshot armazena somente o identificador interno do aluno e metadados de elegibilidade; não persiste matrícula, telefone, e-mail ou conteúdo de mensagem.
- A janela de supressão de sete dias é uma regra conservadora inicial, ainda configurável em wave posterior.
- O snapshot é consistente com a avaliação da requisição; mudanças concorrentes na base são detectadas por contagem e exigem nova geração.

## Endpoints
- `POST /api/v1/agents/retention/campaigns/intelligence/proposals` — recebe `group_ids`.
- `GET /api/v1/agents/retention/campaigns/intelligence/proposals` — lista até 100 propostas do tenant.
- `GET /api/v1/agents/retention/campaigns/intelligence/proposals/{proposal_id}` — lê uma proposta do tenant.
