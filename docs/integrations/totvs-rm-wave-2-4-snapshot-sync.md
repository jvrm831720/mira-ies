# TOTVS RM — Wave 2.4: snapshots seguros e reconciliação

**Status:** motor puro + testes sintéticos. Não há persistência, chamadas RM ou homologação de instalação.

## Objetivo

Preparar a sincronização financeira sem fingir que o RM oferece cursor incremental, ordenação estável, snapshot consistente ou exclusão lógica universal. A implementação oferece staging paginado, checkpoint, replay idempotente e diff entre snapshots completos.

## Contrato da origem

`RMSourceSyncContract` exige:
- nome da origem e entidade;
- campos de identidade estáveis e compostos quando necessário;
- declaração explícita de suporte a snapshot completo;
- para incremental: cursor homologado e campos de ordenação estável.

A tentativa de declarar incremental sem cursor e ordenação é rejeitada. A Wave 2.4 não implementa incremental até a IES comprovar esses recursos no DataServer/versão usados.

## Escopo e isolamento

Cada execução carrega `tenant_id`, `coligada_id`, origem, entidade e versão do schema. O contrato exige que o campo da coligada faça parte da identidade composta; cada linha é rejeitada se informar outra coligada ou omitir esse campo. A reconciliação bloqueia comparação entre escopos diferentes. A identidade do registro vem dos campos homologados (por exemplo, CODCOLIGADA + ID), nunca de RA isolado.

O contrato em memória não substitui RLS, `tenant_id` no banco, autorização do conector ou auditoria no backend. O chamador deve persistir escopo e staging sob isolamento do tenant.

## Staging e checkpoint

- Cada página tem offset, próximo offset, quantidade e fingerprint.
- A próxima página precisa começar no checkpoint esperado.
- Replay idêntico de uma página já recebida (incluindo o indicador de continuação) é idempotente.
- Replay divergente, página fora de ordem, identidade duplicada e payload não JSON são rejeitados.
- O run só pode ser finalizado após a origem indicar fim da extração.
- A quantidade final pode ser comparada ao total esperado, quando a origem fornecer esse controle.

O retorno de cada função é imutável. O adaptador de persistência deve gravar página + checkpoint na mesma transação. Em falha, retomar do último checkpoint confirmado.

## Publicação e reconciliação

`finalize_snapshot_run` produz um snapshot comprometido somente após extração completa. `reconcile_snapshots` classifica identidades como:
- adicionadas;
- atualizadas;
- inalteradas;
- removidas.

**Remoção é conservadora:** só é reportada quando o chamador declara snapshot completo e autoritativo **e** o contrato da origem registra `deletion_semantics_confirmed=True), após homologação com a IES. Uma página parcial, falha de rede, extração filtrada ou contrato sem semântica de exclusão confirmada nunca gera tombstone. Mesmo após homologação, a aplicação operacional deve auditar antes de propagar exclusões.

## Limitações conhecidas

- Offset pagination não garante snapshot consistente se registros mudarem durante a leitura.
- Sem campo de atualização estável, não há cursor incremental seguro.
- Sem contrato de exclusão, ausência no resultado não prova exclusão.
- O motor não persiste, não agenda jobs, não chama DataServer e não faz upsert em tabelas MIRA.
- A publicação atômica, lock por escopo, RLS, auditoria e recuperação após restart pertencem à próxima camada de persistência.
- Não calcula saldo, pagamento líquido, atraso ou inadimplência.

## Homologação exigida

A IES deve confirmar DataServer, chave composta, filtros por coligada, paginação, ordenação, consistência durante leitura, total de controle, exclusões e política de corte. Para incremental, deve provar cursor monotônico/estável, atualização retroativa e tratamento de exclusões.

## Testes sintéticos

Cobertura: paginação e checkpoint, replay idempotente e replay divergente (incluindo metadados), páginas fora de ordem, identidade duplicada/ausente, registro de outra coligada, JSON inválido, divergência de contagem, diff add/update/unchanged/remove, bloqueio de tombstone sem semântica homologada, isolamento tenant/coligada e gate de cursor incremental.
