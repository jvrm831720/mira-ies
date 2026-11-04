# Canvas — Wave 1: read-only REST foundation

## Scope

This wave adds a small asynchronous Canvas REST client for controlled discovery
and read-only retrieval. It does not connect to a live institution and does not
persist data, calculate risk scores, enqueue jobs, or trigger webhooks.

## Contract and authentication

- API root: `https://<institution-host>/api/v1/` (subpath installations are supported).
- Authentication: OAuth2 access token sent as `Authorization: Bearer <token>`.
- HTTPS is mandatory. Redirects are disabled and requests have a finite timeout.
- The access token must be provisioned by the institution with the minimum
  required scopes. Endpoint visibility also depends on the Canvas role and
  institutional account/course permissions.

## Implemented GET allowlist

| Resource | Method | Path |
|---|---|---|
| Courses | GET | `/courses` |
| Course users | GET | `/courses/:course_id/users` |
| Enrollments | GET | `/courses/:course_id/enrollments` |
| Assignments | GET | `/courses/:course_id/assignments` |
| Assignment submissions | GET | `/courses/:course_id/assignments/:assignment_id/submissions` |
| Missing submissions | GET | `/users/:user_id/missing_submissions` |

Only these paths are accepted. There are no write methods or generic arbitrary
URL methods. Numeric identifiers are validated before request construction.

## Pagination and transport safety

- Pagination is bounded by `max_pages` (default 10, maximum 100).
- A `rel="next"` link is followed only when it remains on the configured
  origin and under the configured `/api/v1/` path.
- Redirects are not followed.
- 401/403 responses become sanitized authentication errors.
- Non-JSON responses and unexpected pagination payloads become contract errors.
- No token is added to query strings or logged by this client.

## Validation

Tests use `httpx.MockTransport`; they do not contact Canvas or require a token.
They cover HTTPS validation, bearer authentication, GET-only path allowlisting,
ID validation, pagination limits, external pagination link rejection, and
sanitized authentication errors.

## Not included / next gates

- No production credentials, institution sandbox, or live API calls.
- No persistence, student identity reconciliation, scoring, background worker,
  scheduled sync, or webhook registration.
- No assumption that all listed endpoints are enabled for every institution.
- Before institutional validation, confirm the institution's Canvas host,
  OAuth2 registration, scopes, account/course roles, SIS identifier policy,
  rate limits, and data-use authorization.
- A future ingestion wave must define tenant isolation, audit trail, field
  minimization, retention, and an explicit SIS-to-MIRA student mapping contract.
