# Motor de regras da régua de retenção — MVP

O motor está em `backend/app/agents/rule_engine.py`. Ele é uma função pura:
não consulta banco, não acessa dados de outro tenant e não envia mensagens.
Isso permite validar e testar a decisão antes de ligar persistência e execução.

## Exemplo de regra

```json
{
  "id": "critical_48h",
  "name": "Críticos sem contato",
  "version": 1,
  "conditions": {
    "all": [
      {"field": "risk_level", "op": "eq", "value": "critico"},
      {"field": "days_since_contact", "op": "gte", "value": 7},
      {"field": "opt_out", "op": "eq", "value": false}
    ]
  },
  "action": {"channel": "whatsapp", "template_id": "critico_v1"}
}
```

## Contrato atual

- Campos permitidos: `risk_level`, `risk_score`, `days_since_contact`, `opt_out`, `has_phone` e `has_email`.
- Operadores: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in` e `not_in`.
- `conditions.all`: todas precisam ser verdadeiras; `conditions.any`: ao menos uma precisa ser verdadeira. Se os dois grupos existirem, ambos precisam passar.
- Campos ausentes nunca satisfazem uma condição — inclusive `neq` — para evitar elegibilidade acidental com dados incompletos.
- Ação aceita canais `whatsapp`, `email`, `sms` e exige `template_id`.
- `version` deve ser um inteiro positivo. O chamador deve criar uma nova versão em vez de sobrescrever uma versão já publicada.
- Campos e operadores desconhecidos são rejeitados antes da avaliação. Não há `eval`, código executável ou acesso dinâmico a atributos do ORM.

## API e persistência

Esta entrega implementa a validação e a avaliação isoladas com testes unitários. Ainda não cria endpoints de CRUD, tabela de campanhas ou ativa o envio por regras. O próximo incremento deve persistir regras por `tenant_id`, manter versões imutáveis, gravar a versão e o motivo em `intervention_logs`, e oferecer simulação antes de chamar o orquestrador existente. Até lá, o endpoint operacional atual de retenção continua usando a lógica existente e `dry_run` por padrão.
