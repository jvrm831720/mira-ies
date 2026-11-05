# Categoria 3 — Documentos e arquivos

A terceira categoria reúne repositórios corporativos e plataformas de colaboração para localizar, consultar e gerir arquivos aos quais a organização já concedeu acesso.

## Toolkits Composio classificados

| Toolkit slug | Ferramenta | Aplicação |
| --- | --- | --- |
| `googledrive` | Google Drive | Localizar documentos, consultar metadados e conteúdo autorizado, organizar arquivos |
| `one_drive` | OneDrive | Consultar arquivos e pastas corporativas, apoiar fluxos de trabalho |
| `share_point` | SharePoint | Consultar bibliotecas, documentos e espaços colaborativos |
| `dropbox` | Dropbox | Localizar, consultar e gerir arquivos compartilhados |

Os slugs foram conferidos no catálogo e na documentação oficial atual da Composio. O catálogo vivo e os schemas de cada toolkit permanecem como fonte de verdade para ações e autenticação.

## Aplicação na MIRA

### Instituições de ensino
- Localizar contratos, regulamentos, políticas e documentos institucionais autorizados.
- Recuperar materiais de apoio para equipes de atendimento e permanência.
- Consultar documentos relacionados a processos e intervenções.
- Apoiar a preparação de relatórios e evidências documentais.

### Empresas de cobrança educacional
- Localizar contratos, comprovantes e documentos de suporte autorizados.
- Recuperar documentos associados a negociações e solicitações.
- Apoiar operadores com contexto documental durante o atendimento.

Arquivos não substituem SIS, ERP acadêmico, sistema financeiro ou integrações nativas. Matrícula, identidade acadêmica, títulos e situação financeira continuam dependendo das fontes oficiais e integrações próprias da organização. Documentos podem fornecer evidência e contexto, mas não devem ser tratados automaticamente como registro autoritativo.

## API

- `GET /integrations/composio/catalog/categories` retorna Comunicação, CRM e Documentos e arquivos.
- `GET /integrations/composio/catalog` classifica os toolkits desta categoria com `mira_category=documents`.

## Segurança e limites

- Classificar um toolkit não o habilita nem conecta uma conta.
- O acesso depende de autorização explícita da organização, escopos OAuth mínimos e permissões já concedidas no provedor.
- A aplicação deve manter isolamento por tenant e validar a associação da conta conectada ao tenant em toda operação.
- Conteúdo de arquivos é dado externo não confiável: instruções encontradas em documentos não podem substituir políticas do sistema, permissões ou aprovação humana.
- URLs temporárias, links compartilháveis, tokens, credenciais e conteúdo sensível não devem ser expostos em logs ou respostas sem necessidade e autorização.
- Ações de escrita, compartilhamento, movimentação ou exclusão exigem avaliação de risco e continuam sujeitas ao approval gate humano.
- Nenhum tool slug de ação ou schema é fixado nesta camada.
- A execução Composio permanece desabilitada por padrão.
