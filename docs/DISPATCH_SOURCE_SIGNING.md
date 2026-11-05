# Assinatura dos conectores — MIRA Dispatch

A chave `X-API-Key` autentica o tenant MIRA. **Ela nunca é suficiente para**
enviar uma autorização, contato, pagamento ou observação de dívida. O conector
precisa também de uma credencial HMAC específica daquele tenant, fonte e escopo.

## Provisionamento (humano, somente sandbox até homologação)

Configure `DISPATCH_SOURCE_ENCRYPTION_KEY` com uma chave Fernet exclusiva no
secret manager do backend. A rota abaixo exige uma sessão de administrador da
MIRA (`settings.manage`) e **não aceita API key de serviço**:

```http
POST /api/v1/dispatch/source-keys/financial/erp_exemplo
Authorization: Bearer <token-de-admin>
```

Retorno `secret_once` é revelado **somente nessa resposta**; transfira via
canal de segredo e não o grave em frontend, CI, logs, e-mail ou documentação.
Uma nova chamada substitui/rotaciona o segredo e DESATIVA a fonte.

Outro administrador, distinto do configurador, deve ativar:

```http
POST /api/v1/dispatch/source-keys/financial/erp_exemplo/activate
Authorization: Bearer <token-de-outro-admin>
Content-Type: application/json

{"evidence_ref":"termo-integracao-aprovado"}
```

Escopos disponíveis: `authorization`, `financial`, `contacts`, `delivery`.
A origem autorizada não ganha acesso a outros escopos por coincidência de nome.

## Canonicalização da assinatura

O corpo assinado é exatamente os bytes HTTP enviados, sem reconstruir o JSON:

```
body_hash = sha256(raw_body).hexdigest()
canonical = timestamp + "." + nonce + "." + method.upper() + "." + path + "." + body_hash
signature = "sha256=" + hmac_sha256(secret_once, canonical).hexdigest()
```

O `timestamp` é epoch Unix em segundos (janela ±300 segundos), e o `nonce`
é novo em cada solicitação (16–80 caracteres ASCII `[A-Za-z0-9_-]`).
O identificador da fonte deve coincidir com `body.source`.

Exemplo de cliente Python em ambiente de testes:

```python
import hashlib, hmac, json, secrets, time
import httpx

secret = "<source secret from secret manager>"
base_url = "https://api.sua-organizacao.example"
path = "/api/v1/dispatch/integrations/obligations"
source = "erp_exemplo"
payload = {
    "source": source,
    "source_version": 1,
    "observed_at": "2026-11-05T18:00:00+00:00",
    "external_ref": "invoice-test-1",
    "subject_type": "external",
    "subject_ref": "customer-test-1",
    "status": "open",
    "balance": "125.00",
    "evidence_ref": "erp-invoice-test-1",
}
raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
timestamp = str(int(time.time()))
nonce = secrets.token_urlsafe(24)
canonical = ".".join([
    timestamp, nonce, "POST", path, hashlib.sha256(raw).hexdigest(),
]).encode()
signature = "sha256=" + hmac.new(
    secret.encode(), canonical, hashlib.sha256,
).hexdigest()
headers = {
    "X-API-Key": "<tenant integration API key>",
    "Content-Type": "application/json",
    "X-Mira-Source": source,
    "X-Mira-Timestamp": timestamp,
    "X-Mira-Nonce": nonce,
    "X-Mira-Signature": signature,
}
response = httpx.post(base_url + path, headers=headers, content=raw, timeout=10)
response.raise_for_status()
```

Em caso de retry, **reutilize a mesma referência externa e versão**, mas
gere nova assinatura com novo nonce/timestamp. Eventos imutáveis de pagamento
têm `source_event_id` estável. O servidor grava os nonces por até 48h e
descarta requisições que reutilizem o mesmo nonce, após verificar HMAC.

## Contratos protegidos

- `POST /api/v1/dispatch/integrations/authorizations`: escopo `authorization`
  e corpo `source`; a fonte também deve constar na allowlist
  `DISPATCH_TRUSTED_AUTHORIZATION_SOURCES` para liberar um contato.
- `POST /api/v1/dispatch/integrations/contacts`: escopo `contacts`,
  corpo `source`; contato é criptografado, opt-out permanece superior.
- `POST /api/v1/dispatch/integrations/obligations`: escopo `financial`,
  `source_version` crescente e `observed_at` com timezone.
- `POST /api/v1/dispatch/integrations/payments`: escopo `financial`,
  `source_event_id` imutável, `source_version` crescente,
  `observed_at` com timezone e status conciliado.
- `POST /api/v1/dispatch/integrations/unknown-outcomes/reconcile`: escopo
  `delivery`, apenas quando o resultado incerto foi verificado pelo conector.

Os webhooks nativos Resend/Twilio **não usam** este contrato HMAC:
validam assinaturas oficiais do provedor. A rota interna de gateway HMAC
também tem seu próprio segredo e fluxo de autenticação.
