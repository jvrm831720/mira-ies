# Wave 0.6 · Experiência acadêmica

## Inventário inicial

| Área | Entrada institucional | Contratos existentes |
| --- | --- | --- |
| Cursos, disciplinas, docentes, turmas, períodos e calendário | /academico | /native-academic/catalog oferece overview, cadastro em lote, rascunhos e publicação |
| Matrizes, regras, oferta, matrículas e rematrículas | /academico/jornadas | /native-academic/operations oferece matrizes e regras publicáveis, ofertas e decisão de solicitações |
| Diário, notas, frequência e histórico | /academico/jornadas | /native-academic/operations oferece lista de alunos da turma, lançamento, fechamento e histórico |
| Solicitações e documentos | /academico/servicos | /native-academic/services oferece fila, detalhe, atribuição, comentários, anexos, notificações e modelos |
| Portal do Aluno | /portal | Rotas do portal para programas, ofertas, matrículas, histórico e serviços |

## Primeira entrega

A navegação contextual liga as três entradas institucionais e usa as disponibilidades retornadas por /org/me. A turma abre um registro de leitura a partir do Object Index e do Dialog compartilhados. O registro apresenta os vínculos carregados no catálogo e diferencia referências fora da prévia de vínculos ausentes. As chaves de consulta do catálogo e dos rascunhos incluem instituição e usuário.

O overview atual retorna totais institucionais e limita a prévia a 50 cursos, 50 períodos e 100 registros por tipo para disciplinas, professores e turmas. O índice de turmas aplica filtros à prévia. Uma listagem institucional completa depende de um contrato paginado.

Os modelos relacionais, as permissões do backend, as regras de publicação e as flags acadêmicas continuam sob os contratos existentes. A entrega não requer migration. A integração de registros com procedência do Data Hub e a validação do Portal ficam para as etapas seguintes.

Cursos, disciplinas, professores e períodos agora reutilizam a tabela do Object Index, com busca, ordenação e páginas de 25 registros no servidor. O endpoint reutiliza a autorização institucional e filtra por tenant antes de aplicar a paginação. Os totais gerais continuam vindo do overview. Turmas e seletores dos formulários continuam sujeitos aos limites da prévia.

## Gates pendentes

Paginação de turmas e seletores, visões salvas para os demais objetos, registros acadêmicos completos, refinamento das operações de sala e dos serviços, testes com dados sintéticos e duas instituições, validação de permissões, CI no HEAD final e verificação de release antes do merge.
