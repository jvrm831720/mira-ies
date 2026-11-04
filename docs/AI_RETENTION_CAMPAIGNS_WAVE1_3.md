# Campanhas inteligentes — Wave 1.3

## Entrega
- Edição controlada de título, objetivo, estratégia, canais, cadência e briefing.
- O snapshot da audiência, grupos de origem, hash, motor e contagens permanecem imutáveis.
- Revisão humana com estado `in_review`.
- Solicitação de ajustes com estado `changes_requested`; a edição seguinte retorna a proposta para `draft`.
- Aprovação restrita a usuários humanos com MFA AAL2 e papel `admin`.
- Separação de funções: o criador não pode revisar, atestar autorização ou aprovar a própria proposta.
- Declaração explícita da instituição sobre base/referência de autorização antes da aprovação.
- Trilha append-only para edição, submissão à revisão, solicitação de ajustes, atestado institucional e aprovação.
- Auditoria e consultas sempre limitadas ao tenant.

## Endpoints
- `PATCH /api/v1/agents/retention/campaigns/intelligence/proposals/{id}`
- `POST /api/v1/agents/retention/campaigns/intelligence/proposals/{id}/review`
- `POST /api/v1/agents/retention/campaigns/intelligence/proposals/{id}/request-changes`
- `POST /api/v1/agents/retention/campaigns/intelligence/proposals/{id}/authorization-attestation`
- `POST /api/v1/agents/retention/campaigns/intelligence/proposals/{id}/approve`
- `GET /api/v1/agents/retention/campaigns/intelligence/proposals/{id}/audit`

## Salvaguardas
- O atestado institucional registra uma declaração e uma referência documental; não é validação jurídica automática nem substitui análise jurídica/contratual.
- Aprovação não autoriza envio, agendamento, execução ou chamada de provedores.
- A resposta mantém `execution_enabled=false`.
- Propostas aprovadas ficam bloqueadas para edição; uma alteração exige fluxo de nova proposta/revisão, preservando o histórico.
- A migração adiciona campos de workflow e tabela de auditoria com trigger de imutabilidade e RLS por tenant.

## Fora do escopo
- Agendamento, disparo, pausa/retomada de campanhas.
- Integração com provedores de e-mail, WhatsApp ou SMS.
- Confirmação jurídica de consentimento/base legal.
