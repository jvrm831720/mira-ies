# Constituição e princípios da MIRA

**Estado:** consolidação provisória; confirmar com a Constituição canônica quando localizada.  
**Base:** missão do prompt de auditoria; README e documentos de produto da branch `main`.

## Identidade do produto

A MIRA é descrita no README como plataforma B2B para inteligência, prevenção de evasão e retenção no ensino superior: análise de risco, fatores explicativos e apoio a intervenções por canais digitais. O Control Center é ferramenta interna de administração e governança, não módulo comercial entregue a instituições.

## Princípios normativos

| ID | Princípio | Decisão | Evidência/limite |
|---|---|---|---|
| RB-CON-001 | Retenção e persistência são resultados de negócio prioritários; entrega de mensagem é métrica intermediária. | APROVADA (prompt fundador) | `docs/RETENTION_EVENTS.md`, `backend/app/models/intervention.py`; atribuição causal continua limitada. |
| RB-CON-002 | IA apoia decisão; não substitui automaticamente responsabilidade humana em decisões relevantes. | APROVADA (prompt fundador) | Limites de uso final e revisão humana ainda precisam de contratos de produto específicos. |
| RB-CON-003 | Complexidade técnica deve ser escondida do usuário sem ocultar estados reais, limitações e erros. | APROVADA (prompt fundador) | A interface precisa ser auditada fluxo a fluxo; não há teste global de consistência. |
| RB-CON-004 | Explicabilidade deve ser proporcional à relevância e ao impacto da decisão. | APROVADA (prompt fundador) | Motor expõe fatores SHAP; adequação/calibração estatística por coorte não foi comprovada nesta fase. |
| RB-CON-005 | Privacidade, isolamento institucional, autorização no backend e segurança por padrão. | APROVADA (prompt fundador) | Há tenant_id em modelos e dependências de autenticação; cobertura ponta a ponta não foi comprovada. |
| RB-CON-006 | Estados operacionais precisam ser explícitos e verificáveis; sucesso só após confirmação. | APROVADA (prompt fundador) | Filas e status de intervenção existem; semântica varia entre fluxos e exige revisão. |
| RB-CON-007 | Falhas devem recuperar-se sem duplicar ações ou corromper histórico. | APROVADA (prompt fundador) | Idempotência e retries existem em alguns caminhos; não universalmente verificados. |
| RB-CON-008 | Regras, modelos e resultados históricos devem ser versionados quando necessário à reprodutibilidade. | APROVADA (prompt fundador) | Versões de campanha, modelos e alvo aparecem no código; proveniência completa ainda é lacuna. |
| RB-CON-009 | Previsão, evidência e fato confirmado são conceitos distintos. | APROVADA (prompt fundador) | Necessita revisão de todos os rótulos e mensagens da interface. |
| RB-CON-010 | Dados ausentes não equivalem a resultado negativo. | APROVADA (prompt fundador) | O alvo de evasão 90d já diferencia observação imatura; revisar outras features e rotas. |

## Hierarquia das fontes

1. Constituição e decisão explicitamente aprovada pelo fundador/responsável do produto.
2. Registro de decisão aprovado e posterior.
3. Regra normativa deste catálogo aprovada.
4. Código atual como evidência de implementação.
5. Testes como evidência limitada aos cenários executados.
6. Documentação antiga/proposta, que pode estar desatualizada.

O prompt da auditoria estabelece os princípios acima, mas a Constituição canônica não foi localizada na árvore de arquivos examinada. Não atribuir a ela um caminho ou texto que não foi encontrado.

## Limites da atuação

A MIRA deve apoiar instituições no entendimento e prevenção de evasão e retenção. Os critérios exatos de uso em decisões de alto impacto, limites contratuais por tipo de aluno, revisão humana obrigatória e responsabilidade final precisam ser detalhados e aprovados antes de tratar a previsão como autorização para uma ação automática.
