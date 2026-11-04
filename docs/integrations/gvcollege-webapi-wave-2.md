# GVcollege WebAPI — Wave 2 (manifesto e prontidão institucional)

## Objetivo

A Wave 2 acrescenta um manifesto declarativo por tenant e um avaliador de
prontidão para a futura homologação. Como a MIRA ainda não possui credenciais
nem contratos de views fornecidos por uma instituição cliente, esta etapa
não tenta conectar-se a ambientes reais e não inventa o mecanismo de
autenticação ou o schema acadêmico/financeiro.

## O que foi implementado

- Manifesto por tenant que reutiliza a configuração HTTPS, allowlist e
  contratos explícitos de views da Wave 1.
- Referência opaca a provedor/cofre de segredos. O manifesto não recebe nem
  persiste senha, token ou headers de autenticação.
- Gates independentes para endpoint/allowlist, referência de autenticação,
  aprovação institucional das views, confirmação das chaves de paginação,
  política de egress e validação TLS.
- Relatório de prontidão com estados: `pending_configuration`,
  `pending_institution_validation`, `ready_for_homologation` e
  `homologated`.
- Evidência referenciada obrigatória para declarar homologação.

## O que não foi implementado

- Persistência de configuração/segredos em banco.
- Integração com um cofre específico (Cloudflare, Vault ou outro).
- Descoberta remota de views ou teste contra API real.
- Worker, scheduler, ingestão, sincronização ou endpoints operacionais.
- Ativação de conexão ou deploy.

O campo `sync_permitted` permanece falso nesta wave, inclusive quando um
manifesto declara evidência de homologação. Isso é intencional: não existe
executor GVcollege nesta etapa.

## Checklist para uma futura instituição

1. Fornecer URL e versão da WebAPI instalada.
2. Confirmar com GVDASA/IES o mecanismo de autenticação e o ciclo de vida das
   credenciais.
3. Aprovar os nomes das views e os campos, tipos e regras de exposição.
4. Confirmar chave única e estável para ordenação/paginação de cada view.
5. Validar filtros, datas, fuso horário, atualização e exclusões.
6. Validar certificado TLS e política de egress/DNS no ambiente de execução.
7. Executar homologação com dados e autorização da instituição e guardar a
   referência da evidência.

## Maturidade comercial

A classificação correta após esta wave é **suporte técnico implementado**,
não integração homologada. Formulação comercial recomendada:

> A MIRA possui uma camada técnica preparada para conectar-se à WebAPI do
> GVcollege, com consultas estruturadas, paginação e configuração por
> instituição. A homologação depende do ambiente, da autenticação e dos
> contratos de dados de cada instituição.

Não afirmar que a MIRA já sincroniza dados de uma instituição GVDASA/GVcollege.
