# Deployment and Staging Guide

This document describes recommended steps to deploy `Structurebase` to a staging environment and production, and lists checks to perform before giving the site to a client for testing.

## Quick start (Railway)
- Start command: `waitress-serve --listen=0.0.0.0:$PORT wsgi:app`
- Create one Railway web service for client testing: `structurebase-staging`.
- Later, create a separate service/project for production.
- Use separate environment variables for each service. Do NOT commit secrets to the repo.
- Paste the service variables from `RAILWAY_ENVIRONMENT.txt` into Railway Variables, then replace every placeholder value.

## Recommended client-testing path
Use Railway for the client staging link.

Why:
- The Flask app runs as a normal Python web service instead of a static/serverless app.
- `/healthz` is already configured as the health check.
- The repo has `railway.json`, `.python-version`, `runtime.txt`, `Procfile`, and a WSGI start command.

If Railway returns `502`, treat the service as unhealthy and inspect deploy logs before testing login. The usual causes are missing variables, MongoDB Atlas network access, wrong MongoDB credentials, or a partial SMTP configuration.

## Required environment variables (minimum)
- `STRUCTUREBASE_ENV=production`
- `STRUCTUREBASE_SECRET` (long random)
- `STRUCTUREBASE_DATABASE_BACKEND=mongodb`
- `STRUCTUREBASE_MONGODB_URI` (must start with `mongodb://` or `mongodb+srv://`)
- `STRUCTUREBASE_MONGODB_DB_NAME=structurebase`
- `STRUCTUREBASE_STORAGE_BACKEND=cloudinary`
- `CLOUDINARY_URL` (must start with `cloudinary://`)
- `STRUCTUREBASE_ADMIN_USERNAME` and `STRUCTUREBASE_ADMIN_PASSWORD`
- `STRUCTUREBASE_SESSION_COOKIE_SECURE=1`

## Atlas / Network access
- Ensure MongoDB Atlas network access allows connections from your hosting provider. For a quick test you can allow 0.0.0.0/0 temporarily; for production, restrict to provider IP ranges or use VPC peering.

## Health and smoke checks
- Health endpoint: `/healthz` — checks DB and storage availability.
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
- Store secrets in Railway Variables; do not use `.env` in repo.

## Staging for client testing
- Use the `structurebase-staging` service as the client test instance.
- Railway should deploy from the clean GitHub repo, not the older local folder with unpushed changes.
- Create a test admin user and share credentials with the client.
- Ask the client to test the critical flows: login, create listing, upload image, generate document, submit enquiry.
- Keep production separate from staging. Do not give clients the production URL until staging passes smoke checks and critical-flow testing.

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
