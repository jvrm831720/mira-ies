# Resultados de permanência

A área **Resultados de permanência** (`/resultados`) separa desfechos educacionais confirmados dos indicadores operacionais de contato. O histórico de mensagens continua disponível em **Histórico de contatos** (`/retencao/logs`).

## Fonte acadêmica e ingestão

A tabela `academic_outcomes` mantém o histórico canônico de desfechos por tenant, matrícula, período letivo, data observada e fonte. O vínculo com `student_id` e o curso são preservados quando disponíveis. Um snapshot de risco prévio não é obrigatório para gravar o desfecho acadêmico.

### Endpoint

`POST /api/v1/academic-outcomes` recebe lotes autenticados no contexto do tenant (1 a 2.000 itens). Exemplo:

```json
{
  "outcomes": [
    {
      "matricula": "2025001842",
      "outcome": "rematriculado",
      "observed_at": "2026-08-12T14:30:00Z",
      "academic_period": "2026.2",
      "source": "jacad",
      "source_record_id": "matricula-739201-2026.2",
      "course": "Enfermagem"
    }
  ]
}
```

`source_record_id` deve ser o identificador estável do registro na origem. A combinação tenant + fonte + identificador torna reentregas idempotentes; uma correção recebida com a mesma chave atualiza o registro. Se a matrícula ainda não corresponder a um cadastro MIRA, o outcome continua sendo armazenado com a matrícula, curso opcional e fonte. Um `student_id` informado precisa pertencer ao tenant e corresponder à matrícula.

Outcomes aceitos: `rematriculado`, `ativo`, `evadiu`, `trancou`, `concluiu`, `formou` e `transferiu`. O status externo do SIS não deve ser convertido sem um mapeamento institucional validado. Em particular, ausência de matrícula, registro ou atualização não é evasão.

Quando há um `TrainingEvent` anterior compatível, o importador também tenta atualizá-lo para o learning loop. A ausência desse snapshot não impede o armazenamento e a mensuração do outcome acadêmico. Outcomes enviados pelo endpoint legado `POST /api/v1/outcomes` continuam sujeitos às validações de treinamento e snapshots desse fluxo.

### Conectores

A ingestão acadêmica oferece um contrato estável para conectores SIS/ERP e importadores institucionais. Os conectores existentes preservam dados de matrícula e período em seus snapshots; eles não devem alimentar outcomes por inferência automática de status ainda não homologado. Para ativar a publicação automática por fonte, o mapeamento entre os status oficiais do fornecedor e a taxonomia acima precisa ser validado com a IES. Até lá, a integração pode publicar registros confirmados usando o endpoint documentado.

## Consulta e filtros

`GET /api/v1/outcomes/analytics` aceita:

- `days`: janela de observação, de 1 a 1.095 dias (padrão: 365);
- `academic_period`: período acadêmico exato informado pela origem;
- `course`: curso;
- `campaign_id`: campanha associada a envio nos 90 dias anteriores;
- `channel`: `whatsapp`, `email` ou `sms`.

A resposta contém as seções `educational`, `operational` e `comparison`. O período letivo filtra os outcomes educacionais; métricas operacionais são agrupadas por mês-calendário. Um mês-calendário não é tratado como semestre/período letivo.

## Definições dos indicadores

- **Permanência observada:** desfechos `rematriculado`, `ativo`, `concluiu` ou `formou` entre outcomes decisivos confirmados.
- **Evasão/saída observada:** `evadiu` ou `trancou` entre outcomes decisivos confirmados.
- **Taxa de permanência:** permanência observada dividida pela soma de permanência e evasão/trancamento observados. Transferências, outcomes sem classificação decisiva e ausência de outcome ficam fora do denominador.
- **Rematrículas confirmadas:** contagem direta de outcomes `rematriculado`. A participação de rematrículas no painel usa como denominador apenas outcomes decisivos; não é uma taxa de rematrícula da população elegível.
- **Cobertura do período/fonte:** proporção dos outcomes registrados que carregam o respectivo campo. Não representa cobertura de toda a população estudantil.
- **Histórico por estudante:** mostra eventos acadêmicos recentes (até 100 linhas na interface); o agregado de taxas mantém no máximo o outcome mais recente por estudante e período letivo. Sem período informado, a deduplicação para agregados fica restrita ao mesmo dia e não inventa um período acadêmico.

Os indicadores operacionais — enviados, entregues, engajamento, falha e estudantes contactados — descrevem o processo de contato, não a permanência acadêmica.

## Associação e comparação de grupos

A associação de outcomes a campanhas/canais considera registros com status `sent` nos 90 dias anteriores ao timestamp do outcome. Essa associação temporal não demonstra efeito da intervenção.

A comparação observacional entre estudantes com envio e estudantes sem envio no período só apresenta taxas se houver pelo menos 30 outcomes decisivos elegíveis em cada grupo, pelo menos 10 por faixa de risco basal (crítico, médio ou baixo) em suporte comum e ao menos 80% do grupo exposto coberto por essas faixas. A taxa do grupo sem envio é padronizada à distribuição de risco basal do grupo exposto. Exposições mistas e risco basal ausente são excluídos da comparação. Se os critérios não forem atendidos, as taxas e diferenças são suprimidas e a resposta explica o motivo.

Mesmo quando exibida, a diferença é **descritiva**, sem intervalo de confiança ou afirmação causal. A análise não controla confundidores que não estejam medidos; decisões sobre eficácia de estratégia exigem desenho de avaliação adequado, por exemplo grupo de comparação planejado ou experimento institucional aprovado.

## Segurança e isolamento

Os dados são associados ao tenant autenticado, consultados por `tenant_id` e armazenados em tabela com política RLS na migração `037_academic_outcomes`. `source_record_id` não deve conter segredo ou dado pessoal além do identificador necessário para reconciliação.
