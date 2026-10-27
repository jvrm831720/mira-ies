# Cloudflare Workers deployment (Next.js / OpenNext)

This frontend is deployed from the `frontend/` directory using the OpenNext Cloudflare adapter.

## Cloudflare Workers Builds settings

- Repository: `jvrm831720/mira-ies`
- Production branch: `main`
- Root directory / working directory: `frontend`
- Build command: leave empty if the deploy command runs the full build
- Deploy command: `npm run deploy`
- Preview deployments: enabled while testing
- Cloudflare Access: leave disabled unless access is intentionally restricted

The `deploy` script runs `opennextjs-cloudflare build` and then deploys through Wrangler. Do not use only `npx wrangler deploy`, because the OpenNext build must run first.

## Environment variables

Configure required variables in Cloudflare Workers Builds / Worker settings, not in committed files.

- `NEXT_PUBLIC_API_URL`: the public base URL for the MIRA API. Set it to the correct deployed API URL before building. Do not use `http://localhost:8000` in production.
- Add any other variables required by the app only after checking their usage. Secrets must be stored as encrypted secrets, not as public variables.

Never expose Supabase `service_role` credentials in a `NEXT_PUBLIC_*` variable or browser code.

## Test before production

1. Install dependencies and regenerate `package-lock.json` from this directory using `npm install`.
2. Run `npm run lint`.
3. Run `npm run build`.
4. Run `npm run preview` and test login, dashboard, student details, imports, API calls and tenant-level access.
5. Only then configure production deployment on `main`.

Keep Vercel connected as a rollback option until the Cloudflare deployment is verified.
