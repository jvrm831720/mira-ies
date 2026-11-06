# Motor Frappe embarcado — distribuição própria da MIRA

## Objetivo

Reutilizar o máximo de código executável, **não reimplementar ERP e Educação**: Frappe Framework + ERPNext + Education são a pilha operacional escolhida. As demais fontes são opcionais. O frontend Next.js e o núcleo de inteligência FastAPI continuam sendo MIRA; o código Frappe é operado e hospedado por nós, sob as licenças upstream. Não é uma integração com o SaaS de terceiro.

## Obter o código-fonte completo

```bash
git clone --recurse-submodules https://github.com/jvrm831720/mira-ies.git
# ou, após git pull no seu checkout:
git submodule update --init --recursive
python scripts/verify_frappe_vendor.py --require-checkout
```

Cada submódulo é fixado em commit exato de `vendor-lock.json`. Não utilizar `git submodule update --remote` automaticamente: isso muda a versão sem revisão. Não rodar instaladores diretamente contra a infraestrutura MIRA já existente.

## De onde vem cada funcionalidade

| Recurso MIRA | Código upstream reaproveitado | Estratégia |
|---|---|---|
| DocTypes, custom fields, Data Import, workflows, permissions, jobs | `framework` | Usar runtime Frappe completo |
| Contabilidade, impostos, Sales Invoice, Price Lists, Payment Entry | `erpnext` | Estender e configurar, não clonar regras para FastAPI |
| Estudantes, matrículas, frequência, avaliações, grades, fees | `education` | Instalar app junto ao ERPNext no mesmo site |
| Portal de alunos | Education portal + MIRA Next.js | Adaptar visual e fazer mediação autorizada das APIs |
| Documentos, comprovantes | Frappe print formats; `print_designer` opcional | Só emitir comprovante após pagamento confirmado |
| Gateways | `payments` opcional | Pix apenas quando gateway brasileiro homologado suportar |
| Componentes | `frappe-ui` (Vue) | Reutilizar tokens/assets compatíveis; não importar Vue em React |
| Infra de implantação | `frappe_docker` | Base para imagens e serviços próprios da MIRA |

## Arquitetura de instalação (planejada, não executada)

```
MIRA Next.js  --->  MIRA FastAPI (sessão, tenant, autorização, logs)
                         | serviço interno isolado / ACL / identidade
                         v
MIRA Education Engine (Frappe + ERPNext + Education)
                         |-- site por instituição ou isolamento equivalente testado
                         |-- banco operacional + Redis + workers próprios
                         |-- pagamentos e PDFs somente após homologação
MIRA PostgreSQL permanece fonte dos modelos preditivos e auditoria MIRA.
```

**Importante:** incluir o código via submódulos **não** instala nem habilita o runtime, não cria sites e não sincroniza alunos. Antes do primeiro deployment: validar compatibilidade das versões pinadas; mapear identidade matrícula/student ID; autenticação e autorização de portal (nunca credencial administrativa no navegador); site por IES; idempotência de pagamentos; políticas de LGPD; backups; testes de integração e revisão de licenças.

Padrão do Frappe para instalação isolada: `bench init --frappe-branch version-15`, adicionar ERPNext e Education via Bench, `bench new-site`, `bench --site <site> install-app`. Usar fontes **locais, pinadas** para criar imagens próprias, com procedimento reprodutível, não versões flutuantes.

**Não mesclar** a branch experimental `feat/frappe-ies-backoffice-foundation`: ela fazia só conexão read-only a Frappe externo e não representa a estratégia de distribuição de código integral.
