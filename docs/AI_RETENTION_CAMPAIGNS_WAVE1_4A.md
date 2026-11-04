# Campanhas inteligentes — Wave 1.4A

## Objetivo

A Wave 1.4A estabelece o modelo de ciclo de vida operacional das propostas de
campanha. Esta etapa não agenda jobs, não cria filas, não chama provedores e
não envia mensagens.

## Estados

- `draft`: proposta em elaboração.
- `in_review`: proposta em revisão.
- `changes_requested`: ajustes solicitados.
- `approved`: proposta aprovada e com atestado institucional registrado.
- `scheduled`: campanha preparada para uma janela futura.
- `running`: execução em andamento.
- `paused`: execução interrompida de forma controlada.
- `completed`: execução encerrada.
- `cancelled`: campanha cancelada.
- `failed`: execução encerrada por falha não recuperada.

## Regras de transição

A máquina de estados está em `app.services.campaign_lifecycle`. Ela é pura:
não acessa banco, não publica eventos e não executa transições por conta própria.
As próximas etapas devem invocá-la dentro de transações com lock da proposta,
verificação de tenant, autorização e auditoria.

Transições permitidas:

- `draft -> in_review`
- `in_review -> changes_requested | approved`
- `changes_requested -> draft`
- `approved -> scheduled | cancelled`
- `scheduled -> approved | running | cancelled`
- `running -> paused | completed | cancelled | failed`
- `paused -> running | cancelled | failed`

Estados `completed`, `cancelled` e `failed` são terminais nesta versão.

## Persistência

A migração `036_retention_campaign_lifecycle` adiciona timestamps operacionais,
metadados de fuso horário e índice parcial para campanhas agendadas. Data/hora
e fuso devem ser persistidos juntos. O timestamp deve ser timezone-aware; o
fuso IANA será validado pela camada de agendamento na Wave 1.4B.

## Limites de segurança

- O snapshot de audiência e seu hash continuam imutáveis.
- Aprovação e atestado institucional da Wave 1.3 continuam obrigatórios.
- O estado `approved` não autoriza execução automática.
- Nenhum scheduler, worker ou adaptador de canal é habilitado nesta etapa.
- A execução e o envio reais permanecem desabilitados.
