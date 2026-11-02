# Dossier técnico — integração nativa JACAD

**Status:** primeira implementação da conexão de leitura (pull), pendente de homologação com credenciais reais de uma instituição.  
**Referência consultada:** documentação pública SWA.JACAD, API REST, versão exibida 3.1.61.060.  
**Base de documentação:** https://auden-developer.jacad.com.br/docs

## 1. Visão geral

A MIRA conecta-se diretamente à API REST do ambiente JACAD da instituição. O cliente informa o endereço HTTPS do ambiente e um token de acesso criado no módulo **Integrações → API de Integração → Tokens de Acesso** do JACAD.

A integração inicial é somente leitura. A MIRA não cria nem altera alunos, matrículas, contratos, boletos, notas ou frequências no JACAD.

## 2. Autenticação

1. A instituição cria um token de acesso no sistema JACAD.
2. A MIRA envia `POST /api/v1/auth/token`, com a chave no header `token`.
3. A API devolve um JWT no campo `token` e o prazo em `expiresIn`.
4. As chamadas seguintes enviam `Authorization: Bearer <JWT>`.

A chave de acesso documentada tem limite de 40 caracteres. O JWT não é persistido pela MIRA. A chave de acesso é cifrada antes de ser gravada no banco. O valor original nunca é devolvido pela API da MIRA nem escrito em logs.

**Permissões:** o token JACAD deve ter apenas os módulos e operações de consulta necessários. A disponibilidade dos endpoints depende das permissões do usuário/token e dos módulos contratados pela IES.

## 3. Recursos oficiais relevantes

| Recurso | Endpoint documentado | Uso na MIRA |
|---|---|---|
| Autenticação | `POST /api/v1/auth/token` | Obter JWT |
| Alunos | `GET /api/v2/academico/alunos` | Identidade, RA, nome, e-mail, organização e datas de cadastro/alteração |
| Matrículas | `GET /api/v2/academico/matriculas` | Situação e vínculo acadêmico; próxima etapa de enriquecimento |
| Notas | `GET /api/v1/academico/notas/consultar` | Notas por turma e disciplina do professor; exige identificadores de turma e disciplina |
| Contratos de matrícula | `GET /api/v1/financeiro/contratos-matricula` | Contratos; não equivale a contas vencidas nem prova dias de atraso |

Documentação consultada:
- Autenticação: https://auden-developer.jacad.com.br/docs/auth
- Acadêmico: https://auden-developer.jacad.com.br/docs/academico
- Financeiro: https://auden-developer.jacad.com.br/docs/financeiro

## 4. Paginação e limites

A consulta v2 de alunos documenta `pageSize` até 5.000 e retorna um objeto `page` com `idCursor` e `idCursorProximo`. A implementação usa o cursor retornado para continuar a leitura, com limite defensivo de páginas e registros para evitar loops ou sincronizações ilimitadas.

Outros recursos documentam paginação por `currentPage` e `pageSize`; os limites variam por endpoint (há endpoints v1 com máximo 500). Cada recurso deve respeitar o limite publicado em sua própria documentação.

## 5. Mapeamento inicial de dados

O primeiro fluxo sincroniza somente o cadastro de alunos:

| Campo JACAD | Campo canônico MIRA | Regra |
|---|---|---|
| `ra` | `matricula` | Preferido como identificador externo |
| `idAluno` | `matricula` | Fallback técnico quando RA não existe |
| `nome` | `nome` | Obrigatório para ingestão |
| `email` | `email` | Opcional |
| `dataAlteracao` | — | Data de alteração do registro, não é observação de cada atributo |

O identificador interno JACAD deve ser preservado no payload bruto. Não substituir o RA por `idAluno` quando o RA existir.

## 6. Limites semânticos e confiabilidade preditiva

A consulta de alunos não fornece, por si só, evidência suficiente para calcular os sete atributos preditivos obrigatórios da MIRA.

- `dataAlteracao` descreve alteração do registro; não prova quando cada campo foi observado.
- `dataCriacao` não representa último acesso.
- A lista de alunos não prova dias sem login, frequência, média, reprovações, recorrência de atraso ou dias de atraso.
- Contrato de matrícula não é sinônimo de parcela vencida.
- Notas são retornadas por turma/disciplina e precisam de regra documentada para agregação por aluno e período.
- Frequência e acesso exigem endpoints e semântica específicos, ainda a homologar.

Portanto, o primeiro sync não inventa valores preditivos nem gera score automático. Campos sem evidência permanecem desconhecidos e o motor de risco continua sujeito ao bloqueio de cobertura/frescor da Wave 3.

## 7. Estratégia de sincronização

### Primeira carga
- Consulta paginada do cadastro de alunos.
- Normalização para o schema canônico MIRA.
- Ingestão vinculada ao tenant autenticado.
- Score automático desabilitado nesta primeira fase.

### Incremental
A API documenta filtros de alteração em alguns recursos. A implementação inicial ainda faz leitura paginada completa. O incremental será habilitado somente depois de homologar o comportamento do cursor e dos filtros de alteração no ambiente real da IES.

### Reconciliação e exclusões
A primeira versão não desativa alunos ausentes de uma resposta nem interpreta ausência como exclusão. Exclusões, transferências e status de matrícula precisam ser reconciliados com endpoint e regra específicos.

### Frequência operacional
A primeira versão oferece teste e sincronização sob demanda. Agendamento, checkpoints persistidos, retentativas e reconciliação automática serão adicionados depois de medir limites e cadência no ambiente real.

## 8. Segurança

- HTTPS obrigatório.
- Somente hosts sob `.jacad.com.br` são aceitos nesta versão.
- Redirects HTTP desabilitados.
- Credenciais cifradas em repouso com chave derivada do segredo de aplicação.
- Isolamento por tenant em tabela própria com RLS.
- Endpoints de configuração, teste e sync exigem papel de coordenador ou administrador.
- Respostas e logs não expõem token ou JWT.

## 9. Homologação pendente

Para declarar a conexão validada em produção, é necessário testar com um ambiente real ou sandbox autorizado pela JACAD:
- URL do ambiente e token com permissão de consulta;
- quantidade de alunos e comportamento de paginação/cursor;
- campos reais e diferenças entre versões/instalações;
- escopos/permissões do token;
- limites de taxa e respostas 401/403/429;
- matrícula, financeiro, notas e frequência;
- cadência e semântica dos timestamps por campo.

**Conclusão:** a conexão nativa inicial de leitura de alunos pode ser configurada, testada e sincronizada pela MIRA. A cobertura acadêmica e financeira necessária à inteligência preditiva exige etapas específicas de homologação; não será simulada por mapeamentos presumidos.
