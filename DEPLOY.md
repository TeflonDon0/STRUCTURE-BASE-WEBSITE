# Deployment and Staging Guide

This document describes recommended steps to deploy `Structurebase` to a staging environment and production, and lists checks to perform before giving the site to a client for testing.

## Quick start (Render / Railway)
- Start command: `waitress-serve --listen=0.0.0.0:$PORT wsgi:app`
- Create two services: `structurebase-staging` and `structurebase-prod`.
- Use separate environment variables for each service. Do NOT commit secrets to the repo.

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
- Store secrets in Render/Railway secret store; do not use `.env` in repo.

## Staging for client testing
- Use the `structurebase-staging` service as the client test instance.
- Prefer Render for the first client-testing deployment because this repo already includes `render.yaml`, `runtime.txt`, `Procfile`, and a WSGI start command. Railway can work, but only after its variables and MongoDB network access are proven with the smoke check.
- Create a test admin user and share credentials with the client.
- Ask the client to test the critical flows: login, create listing, upload image, generate document, submit enquiry.
- Keep production separate from staging. Do not give clients the production URL until staging passes smoke checks and critical-flow testing.

## Rollback and runbook
- Keep a simple rollback process: redeploy previous commit from Render UI or Git tag.
- Document how to rotate keys, restore backups, and escalate incidents in `RUNBOOK.md`.

## Notes
- Always validate `CLOUDINARY_URL` and `STRUCTUREBASE_MONGODB_URI` formats before deploying.
- Enable continuous deployment to staging, and manual promotion to production.
