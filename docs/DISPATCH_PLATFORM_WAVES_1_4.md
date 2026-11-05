# MIRA Dispatch Platform — Waves 1–4

Status: implementation on feature branch. **No live sending or production database upgrade in this delivery.**

## Source architecture and integration

Reviewed `CRM-DDM-2.zip`: the useful patterns are the independent worker,
batch claims (`batch-claim.ts`), lease ownership (`dispatch-worker.ts`),
uncertain-outcome reconciliation, per-channel rate policy, automatic pauses,
reply tracking, delivery ledger and telemetry. The MIRA implementation stays
**Python/FastAPI + PostgreSQL** and reuses existing provider adapters and Redis
provider protection rather than deploying a second NestJS runtime.

### Wave 1 — durable, tenant-scoped outbox

- `backend/alembic/versions/055_dispatch_platform.py`: dispatch campaigns,
  individual items, financial obligations, encrypted external contacts, immutable
  payment events and dispatch events, Redis-independent rate buckets, suppressions,
  gateway replies, and worker heartbeats. Tenant policies use
  `FORCE ROW LEVEL SECURITY`.
- `backend/app/services/dispatch_core.py`: create draft, stage up to 1000
  recipients/request, dedupe, record immutable events, enforce four-eyes
  approval, schedule/pause/resume/cancel.
- `backend/app/api/dispatch.py`: authenticated control plane.
- Human permission requirements: `campaigns.view`, `campaigns.create`,
  `campaigns.edit`, `campaigns.approve` and `campaigns.execute`.
  Institutional API keys **cannot create or approve campaigns**.

A campaign is not authorized merely because it contains recipients.
Approval requires a distinct authenticated user and an institutional evidence
reference. Collection recipients need a separately verifiable obligation.

### Wave 2 — independent, bounded worker

- `backend/app/dispatch_worker.py`: row-level `FOR UPDATE SKIP LOCKED`
  claims with lease tokens and owner fencing, at most 25 recipients/round,
  bounded concurrency, delayed retries, weekend/quiet-hour guard and
  crash recovery.
- `backend/app/services/dispatch_delivery.py`: tenant/channel token buckets
  plus the existing global Redis provider circuit-breaker guard.
- A crashed `leased` item can be queued again because no provider call started.
  A crashed `sending` item is marked **unknown**, never automatically resent.
- Confirmed transient provider failures may retry up to 3 total attempts with
  backoff; ambiguous failures never retry. High failure/unknown ratios auto-pause
  new starts. In-flight operations cannot be rolled back after provider acceptance.
- An empty running campaign is marked completed after all items become terminal.

### Wave 3 — channels, gateway and monitoring

- The new worker is **off** until `DISPATCH_WORKER_ENABLED=true`.
- Live delivery is **off** until `DISPATCH_LIVE_ENABLED=true` plus explicit
  `DISPATCH_LIVE_TENANTS` and `DISPATCH_LIVE_CHANNELS` allowlists.
  Current worker adapter supports **email/Resend** and **SMS/Twilio** only.
  Existing MIRA providers are reused. No channel auto-failover is attempted
  after an uncertain outcome.
- `POST /api/v1/dispatch/webhooks/{provider}` accepts a normalized event
  signed with HMAC-SHA256 using `DISPATCH_WEBHOOK_SECRET`.
  **It is not a direct provider webhook.** A separate gateway must verify the
  provider's native signature before re-signing for this endpoint.
  Payload fields: `tenant_id`, `provider_message_id`, `external_event_id`,
  `kind` (`delivered/read/reply/failed`), and optional `message`.
- Duplicated normalized events are idempotent; receipts are monotonic.
  Only categorized intents are persisted, never full incoming message text.
- `/disparos`: campaign list, audience preparation, proposal import, approval,
  scheduling and pause/cancel, worker heartbeat, counts, cost estimates,
  replies and reconciliation totals.

### Wave 4 — verified collections + assisted response

- Trusted tenant integration API keys can submit normalized `obligations`,
  encrypted external `contacts` and `payments`. Humans cannot mutate those
  financial evidence endpoints through a session.
- `dispatch_obligations` only remains send-eligible while **status=open**,
  balance is positive and verification is **under 15 minutes old**.
  Paid, disputed, cancelled or agreement items suppress queued sends.
- Payments use an append-only ledger with a unique external transaction ID;
  replaying an event with different amount or evidence is rejected.
- Reply classification is deterministic. Examples:
  `claims_paid -> reconcile_payment`,
  `dispute -> human_review`,
  `negotiate -> human_negotiation`,
  `opt_out -> suppress_contact`.
  There is **no autonomous promise, discount, settlement or payment-link creation**.
- STOP or wrong-recipient events persist a tenant-scoped suppression even if
  a connector later tries to reimport a contact.
- `unknown` provider outcomes can be resolved only by an authenticated,
  evidence-bearing connector at
  `POST /api/v1/dispatch/integrations/unknown-outcomes/reconcile`.
  They are never automatically requeued.
- Financial dashboard values are **verified, deduplicated payment facts**;
  they are **not attributed causally to the latest campaign**.

## WhatsApp and legal guard

The Dispatch Platform refuses collections through WhatsApp at both API and
worker policy levels. Even retention WhatsApp is simulation-only in this
implementation. Before operating any real channel, verify the provider's
current platform policies, a lawful contact basis, suppression lists, permitted
contact windows, privacy/retention requirements and local consumer protection.
An imported preference with absent consent is NOT proof of authorization.
The legacy MIRA defaults are intentionally *not* used as authorization here.

## Operational setup (non-production environment only)

Generate a contact-encryption key locally and store it in the backend secret
manager (never commit its value):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set `DISPATCH_CONTACT_ENCRYPTION_KEY` for external contacts, and set
`DISPATCH_WEBHOOK_SECRET` to a separate long secret for the trusted gateway.
The worker and live flags must remain OFF in all uncontrolled environments.

On a **disposable PostgreSQL** database:

```bash
cd backend
python -m pip install -r requirements.txt
PYTHONPATH=. alembic heads
PYTHONPATH=. alembic upgrade head
ruff check app/api/dispatch.py app/api/dispatch_integrations.py app/services/dispatch_core.py app/services/dispatch_delivery.py app/dispatch_worker.py
PYTHONPATH=. pytest tests/test_dispatch_platform.py -q
PYTHONPATH=. pytest -q
```

Use a PostgreSQL role with `NOSUPERUSER NOBYPASSRLS`; the RLS test skips
superusers rather than declaring a misleading success.

In the frontend:

```bash
cd frontend
npm ci
npm run lint
npm test
npx tsc --noEmit
npm run build
```

After disposable-DB validation, in a private sandbox set only
`DISPATCH_WORKER_ENABLED=true` and leave `DISPATCH_LIVE_ENABLED=false`.
The worker can then process only simulated deliveries:

```bash
cd backend
PYTHONPATH=. python -m app.dispatch_worker --once
```

No worker starts automatically from the API process. No migrations have been
applied to production by this implementation.

## Homologation before real sending

1. Verify migration 055 and all tests on the final PR HEAD, including
   concurrent claims and tenant isolation under non-bypass RLS.
2. Run high-volume simulations with multiple worker processes and restart
   during `leased` and `sending` states; verify no duplicate provider calls.
3. Test quiet hours, suppression, late payment arrival, partial payment,
   disputed debt and a provider timeout after acceptance.
4. Verify native provider webhook signatures in a separate gateway and
   map them to the normalized HMAC contract here.
5. Register actual connector-specific source authorization, evidence freshness
   and conflict rules (Omie/TOTVS/Isaac are not assumed interchangeable).
6. Obtain explicit organization/channel approval and a compliance review.
7. Only then evaluate a controlled live pilot. This code delivery does **not**
   activate such a pilot.

### Known boundaries

- No real connector credentials or real settlement evidence were supplied; API
  ingestion contracts are implemented, but customer payment reconciliation
  is **not** automatically synchronized with a live ERP.
- The gateway-to-provider native webhook verification component is an external
  integration contract and is **not** included.
- The initial intent classifier is conservative and rule-based. The human
  negotiation workflow is represented by recommended actions, not an AI bot
  permitted to agree to payment terms.
- Worker rate defaults are conservative and must be calibrated against actual
  provider contract quotas, deliverability and cost in homologation.
- Retention, encryption-key rotation and evidence expiration need operational
  ownership before commercial production release.

GitHub Actions may be unavailable because of billing limits. An absent check
does **not** constitute a passing check, and prior-commit results do not
validate the final HEAD. Do not merge solely on the basis of this document.
