# GVcollege WebAPI — Wave 1 (contrato e transporte)

## Objetivo e escopo

Esta wave entrega a base segura e somente de leitura para consultar views publicadas pela WebAPI do GVcollege. Ela **não** implementa sincronização, ingestão de alunos, mapeamento acadêmico/financeiro universal, worker, ativação ou deploy.

Referência pública do fornecedor: [WebAPI do cliente — GVDASA](https://github.com/GVDASA/GVmobileDevGuide/blob/master/docs/webapi_cliente.md).

## Contrato documentado pelo fornecedor

A documentação informa que:

- A WebAPI consulta views customizadas no SQL Server da instituição.
- As views devem estar no schema `dbo` e usar o prefixo `GVMVW_`.
- A rota é `/api/views/<nome-da-view>`; o nome enviado à API omite `dbo.GVMVW_`.
- O subconjunto OData documentado inclui `$orderby`, `$select`, `$skip`, `$top` e `$filter`.
- `$orderby` é obrigatório.
- O limite documentado é de 1.000 registros por consulta. A paginação usa `$skip` e `$top`.

A documentação pública consultada **não define** autenticação, host/porta padrão, contrato de views de aluno/matrícula/financeiro/notas/frequência, semântica de atualização, cursor incremental, snapshot consistente ou exclusões. Não presumimos nenhum desses itens.

## Configuração por instituição

Cada instância de `GvcollegeInstitutionConfig` representa um tenant e contém:

- `tenant_id`: tenant proprietário da conexão.
- `base_url`: URL HTTPS da instalação.
- `allowed_hosts`: allowlist exata de hostnames.
- `views`: registro explícito de views homologadas para aquele tenant.
- `page_size`: entre 1 e 1.000.
- limites de timeout e tamanho máximo de resposta.

Cada `GvcollegeViewContract` declara o nome curto da view, os campos de origem permitidos, o mapeamento de campos e uma `pagination_key` que a instituição deve confirmar como única e estável. A view não pode ser escolhida pelo usuário final nem por payload arbitrário.

Exemplo ilustrativo (não representa um schema padrão do produto):

```python
GvcollegeInstitutionConfig(
    tenant_id="tenant-uuid",
    base_url="https://webapi.instituicao.edu.br",
    allowed_hosts=frozenset({"webapi.instituicao.edu.br"}),
    views={
        "pessoa": GvcollegeViewContract(
            view_name="Pessoa",
            source_fields=("CodigoPessoa", "NomePessoa", "Email"),
            pagination_key="CodigoPessoa",
            field_mapping={
                "external_person_id": "CodigoPessoa",
                "name": "NomePessoa",
            },
        )
    },
)
```

A configuração ilustrativa exige validação do administrador técnico da instituição. Não criar uma view com esse nome sem confirmar sua existência e seus campos no ambiente do cliente.

## Transporte e segurança

- Apenas HTTPS; URLs com userinfo, query ou fragmento são rejeitadas.
- Hostname deve corresponder exatamente à allowlist institucional.
- IPs literais privados, loopback, link-local, reservados e unspecified são rejeitados.
- Redirects HTTP são bloqueados.
- Timeout e tamanho máximo da resposta são limitados.
- Apenas GET é implementado; não há métodos de escrita.
- Views e campos são allowlisted no contrato; nomes e identificadores são validados.
- Filtros são construídos por `ODataFilter`, com campo e operador allowlisted e escape de aspas. Não aceitar filtro OData bruto.
- Cabeçalhos de autenticação são injetados por um provedor externo de segredos; não são persistidos nesta wave nem definidos por suposição. O mecanismo real deve ser confirmado com GVDASA/IES antes de homologação.
- A allowlist de hostname não substitui controles de egress/DNS. O ambiente de execução deve bloquear loopback, redes privadas, link-local e endpoints de metadata, inclusive após resolução DNS.

## Paginação e consistência

O cliente exige `$orderby` pela `pagination_key` única homologada e usa `$skip`/`$top` com limite máximo 1.000. A documentação não promete snapshot transacional. Se registros forem inseridos/alterados entre páginas, paginação por offset pode duplicar ou omitir linhas. Para sincronização operacional, a instituição deve confirmar a chave, a ordenação, a estabilidade dos dados e eventual estratégia de janela/snapshot. A Wave 1 não declara extração incremental completa.

## Próximas validações antes de ingestão

1. Confirmar versão instalada da WebAPI, URL, TLS e autenticação com fornecedor/IES.
2. Receber lista aprovada de views e respectivos campos, tipos, chaves e cardinalidade.
3. Confirmar chave única estável e ordenação para cada view.
4. Confirmar semântica de filtros, datas, fuso horário, atualização e exclusão.
5. Criar fixtures sintéticas por contrato e testar com ambiente de homologação autorizado.
6. Só então projetar a Wave 2: repositório de configuração/segredos por tenant, descoberta controlada e sincronização paginada com auditoria.

Nenhuma credencial real foi utilizada. Nenhuma conexão institucional foi executada. Nenhum deploy ou ativação em produção foi realizado.
