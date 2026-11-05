# MIRA Education Engine — conexão Backend Render ⇄ Frappe próprio

**Estado:** bridge read-only implementado em branch de PR; sem integração homologada a uma instalação real de Frappe, sem migração/deploy e sem alteração na interface. O código upstream está na PR #146 via Git submodules pinados, não roda automaticamente no Render.

## 1. Topologia de implantação

```text
Aluno/Secretaria -> MIRA Next.js (Vercel)
                      | mesmo domínio: /api/v1/...
                      v
                  Proxy Next.js (já existe, route.ts)
                      | MIRA_API_URL (somente no servidor Vercel)
                      v
                  MIRA FastAPI (Render web service)
                      | sessão MIRA -> tenant -> permissão -> vínculo aluno
                      | segredos só no backend, sem acesso direto do browser
                      v
                  Frappe gateway (Render private service / rede privada)
                      | site_name fixo por IES
                      +-> Site IES A: Frappe + ERPNext + Education
                      +-> Site IES B: Frappe + ERPNext + Education
                      | MariaDB por site, Redis, workers RQ, Nginx/Gunicorn separados
                      v
                  Backend operacional e financeiro controlado pela MIRA
```

- **Vercel** permanece apenas no frontend Next.js. O proxy de `frontend/src/app/api/v1/[...path]/route.ts` já encaminha as chamadas autenticadas à API Render sem cache de PII. Não adicionar `FRAPPE_API_KEY` nem URL privada do Frappe como `NEXT_PUBLIC_*`.
- **Render** continua executando o FastAPI. Criar uma instalação **separada** do Frappe (pelo menos gateway web/private service, Redis e RQ workers e banco MariaDB compatível). Não instalar MariaDB/Frappe dentro do processo FastAPI nem apontar Frappe ao PostgreSQL atual da MIRA.
- O Render pode prover rede privada para conectar dois serviços na mesma área de rede; obter o **endereço efetivo** do serviço no painel Render. O domínio `frappe.internal` abaixo é apenas um exemplo, não um endpoint provisionado.
- Usar imagens/instalação a partir das fontes pinadas em `vendor/frappe/` (PR #146), documentando quaisquer patches internos. O deployment Frappe Docker é multi-service; verificar infraestrutura, compatibilidade dos apps e licenças antes de produção.
- Um site do Frappe por IES, vinculado unicamente a um tenant MIRA. Um site não pode pertencer simultaneamente a duas IES. Rejeitar a troca silenciosa do site após vinculação.
- O proxy Frappe Nginx **deve respeitar a seleção de site autorizada** (Host e `X-Frappe-Site-Name`). É obrigatório validar o roteamento e a separação com 2 sites reais antes de permitir qualquer acesso a dados de clientes.

Documentação infraestrutura:
- https://render.com/docs/private-services
- https://frappe.github.io/frappe_docker/01-getting-started/00-introduction.html

## 2. Ambiente Render — API MIRA (não Vercel)

Configurar apenas depois de disponibilizar/homologar o serviço privado:

```env
MIRA_EDUCATION_ENGINE_ENABLED=false
MIRA_EDUCATION_ENGINE_URL=http://frappe.internal:8080
MIRA_EDUCATION_ENGINE_ALLOWED_SITES=ies-a.interno.example,ies-b.interno.example
```

O `URL` é uma **origem operacional fixa**, definida pelo deploy; nunca enviada pelo usuário ou por request. Em produção só é aceito HTTPS ou HTTP com hostname terminando em `.internal` para serviços privados. Em desenvolvimento são permitidos localhost/loopback.

`ENABLED` fica `false` por padrão. Depois da homologação, o operador configura o URL real, as IES permitidas e ativa `true`. Mesmo com ambiente ativo, cada IES exige configuração, verificação e habilitação explícitas.

Reutilizar a `SECRET_KEY` já existente da API apenas como base da criptografia de credenciais, **estável e secreta**, sob gestão segura do Render. Não registrar chaves em commits ou chats. Planejar rotação com recriptografia antes de trocar a chave.

### Banco e migrations

A migration `055_education_engine_bridge` adiciona somente três tabelas ao PostgreSQL MIRA:
- `tenant_education_engine_connections`: site exclusivo por tenant + credenciais cifradas + status.
- `tenant_education_engine_students`: vínculo explícito do ID MIRA para o ID Frappe, com FK composta de tenant e constraint de unicidade.
- `tenant_education_engine_audit`: auditoria de configurações e vínculos, append-only sob PostgreSQL RLS.

Nenhuma tabela operacional do ERPNext/Education é copiada para o PostgreSQL MIRA. Não aplicar migration de produção automaticamente. Validar `alembic heads`, testar em PostgreSQL descartável e planejar rollback/backup primeiro. A aplicação em produção exige autorização explícita.

## 3. API existente no Render — todas sob /api/v1/education-engine

| Método e rota | Permissão MIRA | Função |
|---|---|---|
| GET `/connection` | `settings.manage` | Estado sem exibir credenciais |
| PUT `/connection` | `settings.manage` | Configura o site autorizado + token restrito; deixa desativado |
| POST `/connection/verify` | `settings.manage` | Testa credencial e identidade do serviço |
| POST `/connection/enable` | `settings.manage` | Habilita só após verificação recente |
| DELETE `/connection` | `settings.manage` | Desabilita a conexão sem apagar histórico |
| PUT `/student-links` | `settings.manage` | Vincula aluno MIRA ao `Student.name` real após verificação remota |
| GET `/students/{id}/profile` | `students.sensitive.view` | Campos mínimos de cadastro do Student |
| GET `/students/{id}/attendance` | `students.sensitive.view` | Student Attendance |
| GET `/students/{id}/grades` | `students.sensitive.view` | Assessment Result |
| GET `/students/{id}/enrollments` | `students.sensitive.view` | Program Enrollment |
| GET `/students/{id}/fees` | `students.sensitive.view` | Fees: **snapshot não conciliado** |
| GET `/audit` | `audit.view` | Auditoria de operações da conexão |

- Todas as operações que chegam ao Frappe usam somente **GET** e recursos em allowlist; nunca expõem um proxy arbitrário `/api/method/*`, Payment Entry ou chamadas de cobrança.
- API keys de integração legadas **não recebem acesso de administrador**; endpoints de configuração exigem sessão autorizada.
- Dados vindos do Frappe são filtrados no backend por aluno remoto vinculado à IES. A API reduz os campos retornados aos necessários para a ficha e não confia em filtros do navegador.
- Página limitada a 100 registros, sem redirects, sem proxy externo, resposta limitada a 1 MiB, timeouts definidos, códigos de erro genéricos; não registrar respostas remotas que contenham PII.
- Os IDs são vinculados manualmente e explicitamente por um administrador. **Nunca** ligar alunos automaticamente apenas por CPF, e-mail, nome ou matrícula sem processo de reconciliação institucional.

Exemplo de payload administrativo (valores fictícios):
```json
{"site_name":"ies-a.interno.example","api_key":"TOKEN_RESTRITO","api_secret":"SEGREDO_RESTRITO"}
```

A chamada `PUT /connection` só funciona para sites previamente incluídos em `MIRA_EDUCATION_ENGINE_ALLOWED_SITES`. Em seguida: `POST /connection/verify`, `POST /connection/enable` e `PUT /student-links` com `student_id` UUID da MIRA e `frappe_student_id` do Education.

O token do Frappe deve pertencer a um **service account por instituição, somente leitura e com permissões mínimas nos DocTypes necessários**. Nunca usar Administrator. Verificar permissões na instalação real, pois alguns DocTypes Education não têm leitura configurada para todos os papéis por padrão.

## 4. Próxima wave: frontend de alto padrão

Depois de haver uma instalação Frappe real e testes locais com duas IES, consumir **somente** esta API MIRA no frontend:

1. Configurações → Integrações: card MIRA Education Engine, estado `não configurado / configurado / verificado / habilitado / erro`, verificação e eventos de auditoria; credenciais nunca exibidas.
2. Ficha do Aluno Attio-style: abas Identificação, Acadêmico, Frequência, Notas, Financeiro, Atividade; preservar indicadores MIRA e exibir estados vazios/erros honestos.
3. Financeiro institucional: lista de Fees, situação e proveniência; sem botões de quitação/pagamento antes de reconciliar o provedor.
4. Portal do Aluno: autenticação própria do pagador e autorização por sujeito, contratos, PDFs e notificações; não reutilizar o endpoint administrativo da ficha como se fosse um endpoint público.
5. Fluxos transacionais: cotação de acordo, Pricing Rules, Payment Intent, webhook assinado e idempotente, reconciliação, emissão de recibo só após liquidação validada, auditoria imutável.

Não confundir **fatura do aluno** com **assinatura SaaS da MIRA** (`/fatura`).

## 5. Testes locais (sem GitHub Actions)

```powershell
git fetch origin
git switch --track origin/feat/mira-education-engine-bridge
git submodule update --init --recursive
# Backend Docker PostgreSQL local, banco de teste descartável, nunca produção
cd backend
python -m ruff check app/api/education_engine.py app/models/education_engine.py app/services/education_engine_client.py app/services/education_engine_secrets.py
python -m pytest -q tests/test_education_engine_bridge.py
python -m alembic heads
```

A verificação de integração de verdade exige a instalação privada do motor e contas/credenciais de **teste**, segredos fora do repositório, duas IES isoladas, leitura de casos conhecidos e revisão por responsável de TI. Não houve teste com um motor hospedado nem deploy Render/Vercel nesta PR.
