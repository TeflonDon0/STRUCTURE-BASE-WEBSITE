# Deployment and Staging Guide

This document describes recommended steps to deploy `Structurebase` to a staging environment and production, and lists checks to perform before giving the site to a client for testing.

## Quick start (Render)
- Start command: `waitress-serve --listen=0.0.0.0:$PORT wsgi:app`
- Create one Render web service for client testing: `structurebase-staging`.
- Later, create a separate service/project for production.
- Use separate environment variables for each service. Do NOT commit secrets to the repo.
- Use `render.yaml` as the configuration contract and provide every value marked `sync: false` in the Render dashboard.

## Recommended client-testing path
Use Render for the client-acceptance link.

Why:
- The Flask app runs as a normal Python web service instead of a static/serverless app.
- `/healthz` is already configured as the health check.
- The repo has `render.yaml`, `.python-version`, `runtime.txt`, `Procfile`, and a WSGI start command.

If Render returns `502`, treat the service as unhealthy and inspect deploy logs before testing login. The usual causes are missing variables, MongoDB Atlas network access, wrong MongoDB credentials, or a partial SMTP configuration.

## Required environment variables (minimum)
- `STRUCTUREBASE_ENV=production`
- `STRUCTUREBASE_SECRET` (long random)
- `STRUCTUREBASE_DATABASE_BACKEND=mongodb`
- `STRUCTUREBASE_MONGODB_URI` (must start with `mongodb://` or `mongodb+srv://`)
- `STRUCTUREBASE_MONGODB_DB_NAME=structurebase`
- `STRUCTUREBASE_STORAGE_BACKEND=cloudinary`
- `CLOUDINARY_URL` (must start with `cloudinary://`)
- `STRUCTUREBASE_ADMIN_USERNAME` and `STRUCTUREBASE_ADMIN_PASSWORD`
- `STRUCTUREBASE_INITIAL_ADMIN_NAME` and `STRUCTUREBASE_INITIAL_ADMIN_EMAIL`
- `STRUCTUREBASE_SESSION_COOKIE_SECURE=1`
- `STRUCTUREBASE_PUBLIC_BASE_URL=https://your-client-acceptance-host.example`
- `STRUCTUREBASE_SEARCH_INDEXING_ENABLED=0`

The legacy admin variables are used only to bootstrap the first `SUPER_ADMIN` when the staff collection is empty. After that, authentication uses the hashed staff record in the database. Changing the environment password later does not overwrite an existing staff password.

For client acceptance, the initial admin name/email and public contact values may remain clearly marked, non-public placeholders. The smoke checker reports them as warnings while indexing is disabled, but they must be replaced before the final public launch.

## Phase 1 staff migration

1. Back up the production database.
2. Set the initial admin name and email to the owner's real identity.
3. Deploy once. Startup creates the staff, invitation, and durable login-attempt collections and bootstraps one super admin only when no staff records exist.
4. Sign in with the existing configured admin username and password. Existing pre-upgrade browser sessions are intentionally invalidated.
5. Open `Dashboard -> Team`, confirm the owner is the active super admin, then invite each staff member individually.
6. Confirm `Dashboard -> Audit` attributes new administrative actions to the signed-in staff member.

## Partner programme migration

1. Back up the database before deployment.
2. Deploy once; startup creates the partner collection/table and required unique/indexed fields.
3. Open `/partners/register` and submit a staging application.
4. Review it from `Dashboard -> Partners`, approve it, and verify the account can sign in at `/partners/login`.
5. Suspend the staging partner and confirm portal access stops immediately.
6. If SMTP is configured, confirm both the admin application alert and partner status email are delivered.

## Referral attribution migration

1. Back up the database before deployment.
2. Deploy once; startup creates the `referrals` and `referral_events` stores plus their lookup indexes.
3. Set `STRUCTUREBASE_REFERRAL_ATTRIBUTION_DAYS=30` and keep `STRUCTUREBASE_SECRET` stable, because it signs attribution cookies.
4. Approve a staging partner, open one portal-generated property link, and submit a test enquiry.
5. Confirm `Dashboard -> Referrals` shows the capture and that the lead displays the verified partner source.

## Commission engine migration

1. Back up the database before deployment.
2. Deploy once; startup creates the commission rule and commission stores with uniqueness and workflow indexes.
3. Sign in with a finance or administrator account and create at least one active rule under `Dashboard -> Commissions -> Manage rules`.
4. Move an attributed staging lead with a positive estimated value through Negotiation, Deposit paid, and Closed won.
5. Confirm the commission progresses through Potential, Pending, and Earned before separately testing approval and payout evidence recording.
6. Confirm no real payment is initiated; `Paid` represents a verified internal record only.

## Partner marketing tools migration

1. Back up the database before deployment.
2. Deploy once; startup creates `marketing_assets` and `partner_marketing_events` plus their lookup indexes.
3. Add `STRUCTUREBASE_MONGODB_MARKETING_ASSETS_COLLECTION` and `STRUCTUREBASE_MONGODB_PARTNER_MARKETING_EVENTS_COLLECTION` when using MongoDB, or keep their documented defaults.
4. Sign in as an approved staging partner and open `Partner portal -> Marketing materials`.
5. Copy one referral link, open it in a private browser, and submit a staging enquiry. Confirm the dashboard reports the recorded copy, referral view, and attributed lead without exposing internal notes.
6. Download the primary property image and verify the response is an attachment available only to an approved signed-in partner.

## Atlas / Network access
- Ensure MongoDB Atlas network access allows connections from your hosting provider. For a quick test you can allow 0.0.0.0/0 temporarily; for production, restrict to provider IP ranges or use VPC peering.

## Health and smoke checks
- Health endpoint: `/healthz` — checks application and database availability without exposing production configuration details.
- After deploy, confirm `/healthz` returns 200 and `status: ok`.
- Local env/config check:
  ```bash
  python scripts/deploy_smoke_check.py --env-file .env
  ```
- Full external connection check, when credentials are available locally:
  ```bash
  python scripts/deploy_smoke_check.py --env-file .env --connections
  ```
- Live deployment check:
  ```bash
  python scripts/deploy_smoke_check.py --skip-env --url https://your-staging-url.example
  ```

## Security & secrets
- Rotate and reissue any credentials accidentally posted in logs or chat.
- Create a dedicated, least-privilege MongoDB user for the app.
- Store secrets in Render environment variables; do not use `.env` in the repo.

## Staging for client testing
- Use the `structurebase-staging` service as the client test instance.
- Render should deploy from the clean GitHub repo and the `main` branch.
- Create a test admin user and share credentials with the client.
- Ask the client to test the critical flows: login, create listing, upload image, generate document, submit enquiry.
- Keep production separate from staging. Do not give clients the production URL until staging passes smoke checks and critical-flow testing.
- Keep `STRUCTUREBASE_SEARCH_INDEXING_ENABLED=0` during acceptance so search engines do not index temporary content or the Render hostname.

## Pre-client release gate
Do not share a staging link until all of these pass:

```bash
python -m py_compile app.py wsgi.py scripts/deploy_smoke_check.py
python scripts/deploy_smoke_check.py --env-file .env --connections
python scripts/deploy_smoke_check.py --skip-env --url https://your-staging-url.example
```

Expected live result:

```txt
[PASS] url_health: https://your-staging-url.example/healthz returned status=ok.
```

If the live check returns `502`, the app is not running. Check host deploy logs for MongoDB auth/IP allowlist errors, invalid environment variables, or failed startup checks.

## Rollback and runbook
- Keep a simple rollback process: redeploy previous commit from Render UI or Git tag.
- Document how to rotate keys, restore backups, and escalate incidents in `RUNBOOK.md`.

## Notes
- Always validate `CLOUDINARY_URL` and `STRUCTUREBASE_MONGODB_URI` formats before deploying.
- Enable continuous deployment to staging, and manual promotion to production.
