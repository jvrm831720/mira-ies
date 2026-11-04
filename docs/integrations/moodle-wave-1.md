# Moodle — Wave 1: Web Services read-only

## Contrato e escopo

O Moodle oferece Web Services externos com protocolo REST. Cada instalação controla quais funções estão disponíveis no serviço externo e quais permissões são concedidas ao usuário/token. A documentação gerada pela própria instalação é a fonte final para confirmar as funções habilitadas.

Fontes oficiais:
- https://moodledev.io/docs/6.0/apis/subsystems/external
- https://docs.moodle.org/503/en/How_to_enable_web_services_for_an_external_system
- https://docs.moodle.org/501/en/Web_services_FAQ

## Implementado

- Cliente HTTP assíncrono para `/webservice/rest/server.php`.
- Exige HTTPS; suporta Moodle instalado em subpath.
- Token enviado no corpo POST, não na URL.
- `moodlewsrestformat=json`.
- Redirects desabilitados, timeout finito e erros sanitizados.
- Allowlist estrita de funções de leitura:
  - `core_webservice_get_site_info`
  - `core_user_get_users_by_field`
  - `core_enrol_get_users_courses`
  - `core_completion_get_activities_completion_status`
- Helpers tipados para informações do site, busca por identificadores conhecidos, cursos do usuário e status de conclusão de atividades.
- Serialização de arrays no formato de parâmetros REST do Moodle.
- Testes com MockTransport; sem token real e sem chamadas externas.

## Segurança e governança

- Nenhuma função de escrita, criação, atualização ou exclusão está na allowlist.
- Não há descoberta ampla de todos os usuários. A busca de usuários exige identificadores conhecidos.
- Token não aparece na URL nem em mensagens de erro.
- A MIRA deve receber um token dedicado, de serviço externo dedicado, com somente as funções e capacidades necessárias.
- Cada instituição deve confirmar sua documentação de API local, versão do Moodle, funções permitidas e política de acesso.
- Não assumir que os quatro métodos estarão habilitados em todas as instalações.
- Nenhuma persistência, sincronização em background, scoring ou associação acadêmica foi incluída nesta wave.

## Limites de homologação

Não houve chamada ao sandbox ou ambiente institucional. O conector é uma base técnica testada com respostas simuladas. A homologação exige URL institucional, token de serviço de leitura e confirmação das funções habilitadas.

## Próximas etapas

1. Validar compatibilidade com a versão Moodle de uma instituição.
2. Confirmar as funções do serviço externo e as permissões mínimas.
3. Executar teste autorizado com token de leitura.
4. Mapear usuários/cursos/conclusões para o contrato canônico MIRA sem assumir que conclusão de atividade equivale a frequência ou nota.
5. Projetar ingestão paginada e persistência com isolamento por tenant, auditoria e idempotência.
