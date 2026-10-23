# Ingestão de Dados + Análise Preditiva

## Fluxo completo

```
Planilha ERP → Upload → Normalização → Validação/Limpeza
                                      → Deduplicação
                                      → Persistência (Supabase)
                                      → Feature Engineering
                                      → XGBoost (Risk Score)
                                      → SHAP (Top 3 fatores)
                                      → Atualização no banco
```

---

## Colunas da planilha

### Obrigatórias
| Coluna     | Descrição                    |
|------------|------------------------------|
| `matricula` | Identificador único do aluno |
| `nome`     | Nome completo                |

### Recomendadas
| Coluna                | Descrição                    |
|-----------------------|------------------------------|
| `dias_atraso_boleto`  | Dias de atraso do boleto     |
| `recorrencia_atrasos` | Quantas vezes atrasou antes  |
| `dias_sem_login`      | Dias sem acesso ao AVA/LMS   |
| `presenca_percentual` | % de presença (0–100)        |
| `nota_media`          | Média geral (0–10)           |
| `reprovacoes`         | Quantidade de reprovações    |
| `semestre`            | Semestre/período atual       |

Endpoint: `GET /api/v1/upload/expected-columns`

## Importação guiada (Smart Import determinístico)

A tela de importação segue um fluxo de três etapas: selecionar o arquivo, revisar a prévia e confirmar o processamento. Não usa IA nem envia o conteúdo a serviços externos para descobrir colunas.

1. **Auto-mapeamento por aliases:** cabeçalhos normalizados (acentos, espaços e maiúsculas/minúsculas) são comparados com uma lista mantida em código. Exemplos: `Student ID` → `matricula`, `Full Name` → `nome`, `Email Address` → `email`, `Course Name` → `curso`.
2. **Mapeamento manual:** qualquer coluna pode ser associada a um campo suportado ou marcada como “não importar”. Não é permitido mapear silenciosamente duas colunas para o mesmo campo.
3. **Prévia sem persistência:** `POST /api/v1/upload/preview` mostra colunas reconhecidas, linhas válidas/descartadas, duplicatas no arquivo, correspondências por matrícula existentes no tenant, amostra de dados e alertas. Aceita `multipart/form-data` com `file` e, opcionalmente, `column_mapping` como JSON serializado.
4. **Confirmação:** o upload real recebe o mesmo `column_mapping`; compartilha as regras de normalização/validação da prévia, registra o lote e opcionalmente calcula score.
5. **Deduplicação e atualização:** a matrícula é a chave de correspondência, sempre combinada com o `tenant_id` da sessão. Reimportar a matrícula existente atualiza o registro, preserva o ID e o histórico ligado a ele e move o vínculo para o lote mais recente. Matrículas de outras instituições nunca são consideradas correspondências.
6. **Proteção contra limpeza acidental:** células vazias não apagam valores existentes durante uma atualização. Um valor de opt-out explícito (`true`/`false`) é respeitado; se a coluna não vier ou estiver vazia/ilegível, a preferência atual é preservada.

A resposta da prévia não cria lotes nem alunos. Campos obrigatórios são `matricula` e `nome`; linhas sem eles são descartadas e descritas no relatório. E-mails inválidos e números impossíveis geram avisos; valores numéricos fora dos limites do domínio são limitados pelas mesmas regras da ingestão.

O relatório final inclui `rows_created`, `rows_updated`, `rows_discarded`, `duplicates_removed`, `quality_score` e avisos. `GET /api/v1/upload/expected-columns` devolve os aliases e os rótulos de campos para integrar clientes da API.

**Extensão futura de IA:** o contrato separa sugestões (`mapped_columns`) do mapeamento confirmado (`column_mapping`). Uma sugestão baseada em IA poderá ser adicionada como provedor opcional posteriormente; o comportamento atual é determinístico e não requer chaves, chamadas externas ou serviços de IA.

---

## O que a ingestão faz

1. Encoding (UTF-8, Latin-1, CP1252)
2. Normalização de nomes de colunas
3. Aliases de ERP (50+)
4. Validação de ranges
5. Descarte de linhas inválidas
6. Deduplicação por matrícula
7. Relatório de qualidade (quality_score 0–100)

---

## Risk Score

- 0–39 → **baixo**
- 40–69 → **médio**
- 70–100 → **crítico**
