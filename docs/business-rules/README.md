# MIRA — Regras de negócio (fonte de trabalho versionada)

**Estado:** auditoria documental em andamento — não declarar completa.  
**Data:** 2026-10-27  
**Branch auditada:** `main`  
**Commit-base auditado:** `e25858b4cb12dab781b19e0ed46cf193007fb520`  
**Branch desta documentação:** `docs/business-rules-audit-2026-10`

## Objetivo e limites

Esta documentação separa decisão de negócio, implementação observável e validação. Ela consolida evidências encontradas no código e nos documentos existentes, sem tratar documentação antiga como prova automática de comportamento atual. Foi produzida por inspeção remota do repositório e dos arquivos listados em [rastreabilidade](implementation-traceability.md); não houve acesso a banco ou ambiente de staging.

**Não é uma declaração de prontidão de produção, conformidade jurídica ou auditoria exaustiva concluída.** O trabalho está na fase 1: inventário inicial dos 18 domínios, regras críticas identificadas e lacunas priorizadas. Cada domínio contém questões ainda não verificadas que precisam ser investigadas antes de marcar a auditoria completa.

## Navegação

- [Constituição e princípios](constitution-and-principles.md)
- [Catálogo central](business-rules-catalog.md)
- [Papéis e permissões](roles-and-permissions.md)
- [Máquinas de estado](state-machines.md)
- [Governança e ciclo de vida de dados/modelos](data-governance-and-lifecycle.md)
- [Critérios de aceite e testes](acceptance-criteria-and-tests.md)
- [Rastreabilidade código → testes](implementation-traceability.md)
- [Decisões e conflitos pendentes](open-decisions-and-conflicts.md)
- [Gestão de mudanças](change-management.md)
- [Relatório executivo da fase 1](executive-audit-report.md)
- [Domínios DOM-01 a DOM-18](domains/)

## Legenda obrigatória

### Status da decisão
- **APROVADA** — explicitamente estabelecida pelo responsável do produto/Constituição ou decisão registrada como confirmada.
- **RECOMENDAÇÃO** — proposta técnica ou de produto ainda sem aprovação.
- **PENDENTE** — evidência insuficiente ou decisão necessária.
- **SUBSTITUÍDA** — decisão antiga substituída, com referência à regra atual.

### Status de implementação
- **IMPLEMENTADA — EVIDÊNCIA ENCONTRADA** — código observado implementa a regra no escopo verificado.
- **PARCIALMENTE IMPLEMENTADA** — parte dos fluxos/cenários existe.
- **NÃO IMPLEMENTADA** — ausência verificada no escopo examinado.
- **CONTRADITÓRIA** — código/documentação implementam ou descrevem comportamentos incompatíveis.
- **NÃO VERIFICADA** — ainda não houve inspeção suficiente para concluir.

### Status de validação
- **TESTADA E APROVADA** — teste identificável passou.
- **TESTADA COM FALHA** — falha identificável.
- **TESTADA PARCIALMENTE** — só parte dos cenários foi coberta.
- **NÃO TESTADA** — não foi executada/confirmada evidência de teste relevante.

Implementação não implica teste; teste automatizado não implica staging nem produção.

## Como ler cada regra

Cada regra recebe ID estável e informa domínio, decisão, implementação, validação, intenção normativa, ator, condições/dados, fluxo, exceções, resultado, efeitos, permissões, falhas, critérios de aceite, cenários, evidências, dependências, risco, pendências e histórico. Na fase 1, algumas entradas resumem campos para evitar inventar comportamento; campos não determinados são explicitamente marcados. A expansão dos registros detalhados continua pendente.

## Precedência e resolução de conflitos

1. A decisão aprovada mais recente e rastreável prevalece sobre uma proposta antiga.
2. Código é evidência do comportamento implementado, não prova de que a regra esteja correta.
3. Documentação descreve intenção/decisão, não comprova implementação.
4. Teste comprova somente o cenário coberto no commit e ambiente em que foi executado.
5. Se não existir decisão aprovada que resolva o conflito, marcar **PENDENTE** e não escolher silenciosamente.

## Processo de alteração

Toda mudança deve atualizar o ID existente quando a regra evoluir, registrar motivo/autor/data, atualizar evidência e testes, revisar impactos nos domínios dependentes e obter aprovação do responsável de produto. Não reutilizar IDs removidos; marcar regras antigas como SUBSTITUÍDA e referenciar a sucessora. Ver [gestão de mudanças](change-management.md).

## Limitações da fase 1

- Constituição canônica separada não foi localizada entre os caminhos inspecionados; a seção de princípios consolida decisões explícitas do prompt do fundador e documentos de produto, identificando o que requer confirmação.
- O repositório é privado e foi inspecionado por arquivos, não por execução local de todos os testes.
- Não houve acesso ao staging, banco de produção, contratos assinados, logs reais ou credenciais de provedores.
- Não se declara auditoria completa nem conclusão jurídica.
