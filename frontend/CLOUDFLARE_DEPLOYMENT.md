# Cloudflare Workers deployment (Next.js / OpenNext)

This frontend is deployed from the `frontend/` directory using the OpenNext Cloudflare adapter.

## Auto-deploy (recommended)

### A) GitHub Actions (repo)

On every push to `main` that touches `frontend/**`, the workflow
`.github/workflows/deploy-cloudflare.yml` runs `npm run deploy`.

**Required repository secrets** (Settings → Secrets and variables → Actions):

| Name | Description |
|------|-------------|
| `CLOUDFLARE_API_TOKEN` | API token with Workers Scripts Edit + Account read |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |

**Required variable or secret:**

| Name | Description |
|------|-------------|
| `NEXT_PUBLIC_API_URL` | Public API base URL (no trailing slash). Prefer a **Variable** if non-secret. |

Create the token at: Cloudflare Dashboard → My Profile → API Tokens → Create Token  
Use template **Edit Cloudflare Workers** (or custom: Account → Workers Scripts → Edit, Account → Account Settings → Read).

Manual run: Actions → **Deploy Cloudflare (frontend)** → Run workflow.

### B) Cloudflare Workers Builds (dashboard)

If the Worker is connected to GitHub in the Cloudflare UI:

1. Workers & Pages → **mira-ies** → Settings / Builds  
2. Production branch: **main**  
3. Root directory: **frontend**  
4. Build command: leave empty (or `npm ci`)  
5. Deploy command: **`npm run deploy`**  
6. Enable automatic deployments on push to production branch  
7. Set `NEXT_PUBLIC_API_URL` in Build environment variables  

Prefer **one** auto-deploy path (GitHub Actions **or** Workers Builds) to avoid double deploys.

## Cloudflare Workers Builds settings (reference)

- Repository: `jvrm831720/mira-ies`
- Production branch: `main`
- Root directory / working directory: `frontend`
- Deploy command: `npm run deploy`
- Preview deployments: optional while testing

The `deploy` script runs `opennextjs-cloudflare build` and then deploys through Wrangler. Do not use only `npx wrangler deploy` — the OpenNext build must run first.

## Environment variables

Configure required variables in Cloudflare Workers Builds / Worker settings or GitHub Actions secrets/vars — not in committed files.

- `NEXT_PUBLIC_API_URL`: public base URL for the MIRA API. Never use `http://localhost:8000` in production.
- Secrets must be stored as encrypted secrets, not as public variables.

Never expose Supabase `service_role` credentials in a `NEXT_PUBLIC_*` variable or browser code.

## Local deploy

```bash
cd frontend
npm ci
export CLOUDFLARE_API_TOKEN=...
export CLOUDFLARE_ACCOUNT_ID=...
export NEXT_PUBLIC_API_URL=https://api.seu-dominio.com
npm run deploy
```

## Test before production

1. `npm install` in `frontend/`
2. `npm run lint`
3. `npm run build`
4. `npm run preview` — login, dashboard, students, imports, API, tenant access
5. Then enable auto-deploy on `main`
