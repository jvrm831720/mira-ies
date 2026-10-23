# Motor de regras da régua de retenção

O motor em `backend/app/agents/rule_engine.py` é puro: valida e avalia JSON sem acessar banco, ORM ou canais de envio. As campanhas e versões são persistidas por tenant em `retention_campaigns`.

## Regras

- Campos permitidos: `risk_level`, `risk_score`, `days_since_contact`, `opt_out`, `has_phone` e `has_email`.
- Operadores: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in` e `not_in`.
- `conditions.all`: todas precisam passar; `conditions.any`: ao menos uma precisa passar. Se ambos existem, os dois grupos devem passar.
- Campos ausentes nunca satisfazem condições, inclusive `neq`.
- Cada regra aceita `priority` como inteiro >= 0; se omitida, usa 100 para compatibilidade. Prioridade maior é avaliada primeiro; empates são resolvidos por `id` em ordem lexicográfica.
- A decisão executável usa somente a primeira regra correspondente nesta ordem. As demais regras continuam registradas na avaliação com status de correspondência e marcação da escolhida.
- O par `(channel, template_id)` precisa existir no registry de templates implementados. IDs desconhecidos e combinações de canal/template inválidas são rejeitados ao criar/ativar a campanha.
- IDs atuais: `retention_v1` para os três canais; `critico_v1`, `whatsapp_critical_v1` e `whatsapp_default_v1`; `score_alto_v1`, `email_critical_v1` e `email_default_v1`; `sms_default_v1`.
- IDs de regra duplicados são rejeitados dentro do conjunto. Use novas versões em vez de sobrescrever regras publicadas.

## Campanhas e endpoints

As rotas têm prefixo `/api/v1/agents/retention/campaigns` e são isoladas por tenant.

- `POST /`: cria uma campanha na versão 1 em estado `draft`.
- `GET /`: lista campanhas; `?status=draft|active|paused` filtra pelo estado.
- `GET /{campaign_id}`: consulta uma versão da campanha.
- `POST /{campaign_id}/versions`: cria a próxima versão imutável em estado `draft`.
- `PATCH /{campaign_id}/status`: ativa, pausa ou devolve uma versão a `draft`.
- `POST /{campaign_id}/simulate`: avalia regras e devolve as decisões, sem envio.
- `POST /{campaign_id}/run-dry-run`: passa decisões elegíveis pelo orquestrador em modo dry-run; nenhuma mensagem real é enviada.

## Salvaguardas da etapa 3.1

- A avaliação falha de forma segura: nível de risco deve ser `baixo`, `medio` ou `critico`, e score deve ser numérico, finito e estar entre 0 e 100. Dados de risco ausentes ou inválidos bloqueiam a elegibilidade, com `blocked_reason=missing_risk_data`.
- Opt-out bloqueia a campanha; ausência de telefone e e-mail também bloqueia ação de contato.
- Ativar uma versão pausa as outras versões ativas com o mesmo `tenant_id` e `slug` na mesma transação.
- Um índice único parcial no PostgreSQL impede duas versões ativas, inclusive em ativações concorrentes. A migração normaliza dados antigos mantendo ativa a versão mais alta antes de criar o índice.
- As versões continuam escopadas por tenant. A idempotência e o dry-run do orquestrador permanecem obrigatórios para a execução segura.

## Execução previsível — etapa 3.2

- O canal da ação vencedora é o único canal tentado para aquele aluno; a execução não volta para a heurística geral nem faz fallback para outro canal.
- O `template_id` é resolvido por um registry allowlist. Corpo e, no e-mail, assunto são renderizados pelo template registrado; o ID efetivamente usado é persistido em `intervention_logs.template_id`.
- Simulação e dry-run retornam `selected_rule` e `rule_evaluations` por aluno. O log salva campanha/versão, prioridade, regra escolhida, avaliação ordenada, canal, template e assunto efetivo do e-mail.
- A execução usa uma ação selecionada por aluno, idempotência estável e as proteções existentes de opt-out e anti-spam.

## Etapa 3.3 — Testes de integração e operação

### Executar testes

A suíte de backend usa PostgreSQL real (UUID/JSONB e índices parciais), não SQLite. Execute em PowerShell na raiz do repositório:

```powershell
docker compose up -d db redis
cd backend
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+asyncpg://beacon:beacon_secret@127.0.0.1:5433/beacon"
$env:DATABASE_URL_SYNC = "postgresql://beacon:beacon_secret@127.0.0.1:5433/beacon"
$env:PYTHONPATH = "."
ruff check app
pytest -v
```

O `conftest.py` deriva e cria automaticamente o banco isolado `beacon_test` a partir de `DATABASE_URL`; no CI, o serviço PostgreSQL é preparado no workflow. Não execute estes testes com credenciais de produção.

### Matriz de regressão

| Área | Cenários automatizados |
|---|---|
| Isolamento multi-tenant | Orquestrador não retorna alunos de outro tenant; preview retorna 404 para aluno alheio; campanhas com o mesmo slug coexistem por tenant; consulta, simulação, ativação, criação de versão e execução de campanha alheia retornam 404. |
| Dados de risco | Nível ausente/inválido e score ausente/fora de 0–100 bloqueiam a elegibilidade. |
| Regras | Prioridade descendente, desempate estável por ID, prioridade inválida, campos/operadores não permitidos e prioridade padrão. |
| Canal e template | Regra vencedora determina um único canal; pares channel/template não registrados são rejeitados; template e assunto selecionados ficam no log. |
| Anti-spam e opt-out | Recontato pelo mesmo canal dentro da janela é ignorado; opt-out impede contato; a decisão deixa motivo legível no histórico. |
| Idempotência | Reexecutar uma campanha não duplica o registro de dry-run para a mesma ação; a segunda tentativa fica registrada como bloqueada pelo anti-spam. |
| Versionamento | Ativação pausa a versão anterior e índice do banco impede duas versões ativas da mesma campanha. |

### Contrato de auditoria

Logs de execução incluem `tenant_id`, `campaign_id`, versão da campanha, `idempotency_key`, canal, `template_id`, regra selecionada, prioridade, regras avaliadas, motivo da decisão e estado da entrega. O preview da mensagem é truncado; evite colocar dados pessoais em nomes/descrições de regra ou nos motivos.

### Limites conhecidos

- A execução de campanha permanece em `dry_run=True`; estes testes não autorizam nem demonstram envio real a provedores.
- A prova de idempotência garante uma única ação de dry-run na mesma janela de execução; não substitui testes de caos/rede com providers reais.
- O CI testa o modelo e as rotas contra PostgreSQL. Redis/filas e callbacks de providers exigem testes adicionais de ambiente quando a integração real for planejada.

## Escopo

Os envios reais continuam desabilitados no endpoint de campanhas. Novos templates precisam ser implementados e incluídos no registry antes de poderem ser selecionados.
