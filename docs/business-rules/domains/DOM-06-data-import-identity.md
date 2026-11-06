# DOM-06 — Importação, qualidade e identidade

## RB-IMP-001 — Preview sem persistência
- Decisão APROVADA; implementação IMPLEMENTADA — EVIDÊNCIA ENCONTRADA; validação TESTADA PARCIALMENTE.
- Norma: preview normaliza e valida sem criar lote/aluno ou alterar preferência; confirmação explícita é necessária para gravar.
- Exceções: cabeçalho duplicado, campo destino inválido e duas colunas para o mesmo campo devem bloquear mapeamento ambíguo.
- Aceite: comparar banco antes/depois da prévia; nenhuma alteração persistida.
- Evidência: backend/app/services/ingestion.py, backend/app/api/upload.py, docs/INGESTAO_E_PREDICAO.md, docs/IMPORT_PLAYBOOK_AUDIT.md, tests test_upload_api.py/test_smart_import_api.py. Risco P1.

## RB-IMP-002 — Matrícula é chave textual dentro do tenant
- Decisão APROVADA; implementação PARCIALMENTE IMPLEMENTADA; validação TESTADA PARCIALMENTE.
- Norma: matrícula como texto, preservando zeros à esquerda, é a chave de correspondência; nunca inferir identidade por nome/telefone/e-mail.
- Efeitos: atualizar matrícula existente preserva ID e relacionamentos; dados vazios não apagam campos existentes; opt-out explícito tem tratamento separado.
- Aceite: tenant A não encontra matrícula de B; linha sem matrícula/nome é descartada; conflito de identidade nunca é importado acidentalmente.
- Evidência: backend/app/services/ingestion.py, backend/app/models/student.py. Risco P0; constraints e conectores precisam de revisão completa.

## RB-IMP-003 — Multi-arquivo não implica junção
- Decisão APROVADA como limite atual; desenho futuro PENDENTE. Implementação NÃO IMPLEMENTADA para join consolidado; validação TESTADA PARCIALMENTE.
- Norma: preview multi-file atual valida arquivos individualmente; file_roles não comprova junção/atomicidade.
- Evidência: docs/IMPORT_PLAYBOOK_AUDIT.md. Pendente: contratos de arquivo, conflitos por linha e recuperação de falha parcial. Risco P1.
