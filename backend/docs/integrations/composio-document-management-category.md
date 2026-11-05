# Composio — Documentos e arquivos

## Objetivo

Classificar integrações de repositórios corporativos para que agentes MIRA possam localizar e consultar arquivos aos quais a instituição já concedeu acesso.

## Toolkits classificados

| Provedor | Toolkit slug | Uso esperado |
|---|---|---|
| Google Drive | `googledrive` | Localizar, consultar e organizar arquivos no Drive |
| OneDrive | `one_drive` | Consultar e gerenciar arquivos do Microsoft 365 |
| SharePoint | `share_point` | Consultar bibliotecas e documentos corporativos |
| Dropbox | `dropbox` | Localizar e consultar arquivos e pastas |

Os slugs foram conferidos no catálogo e na documentação oficial do Composio:
- https://docs.composio.dev/toolkits/googledrive
- https://docs.composio.dev/toolkits/one_drive
- https://docs.composio.dev/kb/guide/toolkits-sharepoint
- https://docs.composio.dev/toolkits/dropbox

## Limites de domínio

Esses repositórios são fontes de documentos e contexto de trabalho. Não substituem SIS, ERP acadêmico, sistema financeiro ou bases oficiais de matrícula, notas, presença e débitos. Quando um documento divergir de uma fonte transacional autoritativa, o agente deve sinalizar a divergência e não sobrescrever o dado oficial.

## Requisitos de segurança

- A classificação no catálogo não conecta contas, não habilita toolkits e não concede permissões.
- Cada conexão e cada política permanecem vinculadas ao tenant da instituição.
- Aplicar menor privilégio: solicitar somente os escopos e ferramentas necessários ao caso de uso.
- Restringir arquivos e pastas ao que a identidade conectada pode acessar; não inferir que um arquivo é compartilhável só porque foi encontrado.
- Tratar conteúdo de arquivos como dado não confiável. Instruções presentes em documentos não podem alterar políticas, revelar segredos ou contornar aprovações.
- Não expor tokens, credenciais, URLs temporárias assinadas ou conteúdo de outros tenants em respostas, logs ou auditoria.
- Operações externas de escrita, compartilhamento, movimentação ou exclusão devem permanecer sujeitas ao policy engine e ao approval gate humano.
- Execução Composio permanece desligada por padrão.

## Escopo desta entrega

Esta etapa adiciona somente metadados de categoria ao catálogo MIRA. Não implementa ingestão, indexação, download, busca semântica, sincronização, OAuth real ou execução de ferramentas.
