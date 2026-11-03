# Wave RM 2.9 — Worker e executor read-only

## Escopo entregue

- Worker standalone com allowlist explícita de tenants, validação de UUID, polling limitado e encerramento gracioso.
- Executor nativo read-only para o primeiro contrato de roster: DataServer `EduAlunoData`.
- Consulta REST GetAll por `start` e `limit`, sem SOAP, escrita no RM ou endpoint arbitrário.
- Segredos resolvidos em runtime pelo módulo `totvs_rm_env_secret_provider`; nunca entram no payload do job ou no PostgreSQL.
- HTTPS obrigatório, host allowlist, sem redirects, sem proxy herdado do ambiente, Basic Auth e cabeçalhos de contexto allowlisted.
- Resposta limitada por bytes, timeout e lista JSON estrita. Formatos diferentes são rejeitados até homologação.
- Validação de `CODCOLIGADA` e `RA`; RA é preservada como texto.
- Minimização de dados: somente `CODCOLIGADA` e `RA` são persistidos no snapshot de roster; os demais campos retornados pelo DataServer são descartados.
- Checkpoint persistente por página, retomada de staging em retry e publicação somente após extração completa.
- Sem inferência de exclusão: a reconciliação não remove registros porque a semântica de exclusão do RM ainda não foi homologada.
- Estado `publishing` cria uma fronteira atômica: cancelamento antes dela interrompe o job; depois dela, a API responde conflito e aguarda a publicação terminar.

## Configuração do worker

Execute o worker em processo separado da API, dentro da rede privada aprovada para alcançar o RM e o PostgreSQL.

Variáveis obrigatórias:

- `RM_SYNC_ENABLE_EXECUTOR=true`: kill switch explícito para habilitar a leitura.
- `RM_SYNC_EDUALUNODATA_CONTRACT_CONFIRMED=true`: confirmação formal de que o GetAll, paginação, cabeçalhos de contexto e formato JSON foram homologados naquela instalação.
- `DATABASE_URL`: conexão PostgreSQL usada pelo worker.
- `RM_SYNC_WORKER_TENANT_IDS`: UUIDs dos tenants explicitamente autorizados, separados por vírgula.
- `RM_SYNC_ALLOWED_HOSTS`: hosts exatos permitidos para conexões RM, separados por vírgula.

Segredos por tenant e coligada, provisionados no secret manager do ambiente:

- `RM_CONN_<TENANT_UUID_COM_UNDERSCORES>_<COLIGADA>_BASE_URL`
- `RM_CONN_<TENANT_UUID_COM_UNDERSCORES>_<COLIGADA>_USERNAME`
- `RM_CONN_<TENANT_UUID_COM_UNDERSCORES>_<COLIGADA>_PASSWORD`
- Opcional: `..._CODFILIAL`, `..._CODTIPOCURSO`, `..._CODSISTEMA`

Exemplo de nomes (valores fictícios; não inserir segredos em arquivos):

- `RM_CONN_00000000_0000_0000_0000_000000000001_1_BASE_URL`
- `RM_CONN_00000000_0000_0000_0000_000000000001_1_USERNAME`
- `RM_CONN_00000000_0000_0000_0000_000000000001_1_PASSWORD`

Sem as duas flags de homologação, o executor falha fechado e não consulta o RM. A URL deve usar HTTPS e o hostname deve constar exatamente em `RM_SYNC_ALLOWED_HOSTS`. Porta 8051 é aceita para instalações que a utilizem, mas não deve ser publicada na internet. O worker deve alcançar o RM por VPN, túnel privado ou conector local aprovado pela IES.

Comando:

```bash
cd backend
python -m app.rm_sync_worker --once
python -m app.rm_sync_worker --poll-seconds 2
```

Use `--once` para smoke tests de fila sem deixar um processo residente. O modo contínuo encerra de forma graciosa entre jobs ao receber SIGINT/SIGTERM.

## Contrato de executor customizado

Quando `RM_SYNC_EXECUTOR_MODULE` aponta para um executor próprio, ele deve expor a função assíncrona:

```python
async def execute_rm_sync_job(job, heartbeat, cancelled, attach_snapshot, before_publish):
    ...
```

- `heartbeat()`: renova a lease e retorna `False` quando o worker perdeu a posse.
- `cancelled()`: informa se o operador solicitou cancelamento.
- `attach_snapshot(run_id)`: associa o snapshot ao job ainda em execução.
- `before_publish()`: tenta atravessar a fronteira atômica de publicação. Deve retornar `True` antes de qualquer commit de snapshot; `False` significa cancelamento solicitado.
- O repositório de snapshot também deve validar `job_id` e `worker_id` na transação final. Não publique fora dessa fronteira.

## Contrato do secret provider

O módulo padrão lê os segredos do ambiente. Para usar Vault, AWS Secrets Manager, Azure Key Vault ou outro cofre, configure `RM_SYNC_CONNECTION_PROVIDER_MODULE` para um módulo confiável que exponha:

```python
def resolve_rm_connection(*, tenant_id: str, coligada_id: str, source_name: str) -> dict:
    return {
        "base_url": "https://host-rm-aprovado:8051",
        "username": secret_username,
        "password": secret_password,
        "context_headers": {
            "CODCOLIGADA": coligada_id,
            "CODFILIAL": "1",
            "CODTIPOCURSO": "1",
            "CODSISTEMA": "S",
        },
    }
```

O provider deve ser síncrono, não deve registrar credenciais em logs e deve retornar somente os quatro campos do contrato. A allowlist de host continua sendo validada pelo executor.

## Limites e homologação obrigatória

Este executor cobre somente `EduAlunoData` e assume que o endpoint REST GetAll da instalação responde com uma lista JSON. A documentação genérica do RM não prova que o DataServer, a operação GetAll, os cabeçalhos de contexto ou o formato de resposta estejam habilitados em cada IES.

Antes do primeiro job institucional:

1. Confirmar com a IES o DataServer, URL, WSDL/REST, operação GetAll e formato real da resposta.
2. Confirmar usuário de serviço read-only e permissões mínimas.
3. Confirmar `CODCOLIGADA`, `CODFILIAL`, `CODTIPOCURSO` e `CODSISTEMA` exigidos.
4. Confirmar a paginação e que a extração cobre todo o roster sem omissões.
5. Testar primeiro com tenant/coligada de homologação e dados sintéticos ou autorizados.
6. Só então liberar o tenant no `RM_SYNC_WORKER_TENANT_IDS` e o host na allowlist.

Não existe teste de conexão real nesta entrega. Não há acesso a credenciais ou dados reais, deploy, nem ativação de worker em produção. Outros DataServers, sync incremental e inferência de exclusões permanecem bloqueados até contratos específicos serem homologados.
