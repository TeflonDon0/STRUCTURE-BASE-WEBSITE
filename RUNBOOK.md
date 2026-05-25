# Structurebase Runbook

## Purpose

This runbook is the operational baseline for staging and production support. It covers deployment checks, incident response, backups, and verification steps for the Structurebase service.

## Service overview

- Application: Flask web service
- Start command: `waitress-serve --listen=0.0.0.0:$PORT wsgi:app`
- Health endpoint: `/healthz`
- Primary data store: MongoDB Atlas or SQLite fallback
- Storage: Cloudinary or local uploads fallback

## Deployment checklist

1. Confirm the repo is on the intended commit and the target service is correct.
2. Verify environment variables are set in the deployment platform, not in the repository.
3. Confirm `STRUCTUREBASE_ENV=production` for production deployments.
4. Confirm `STRUCTUREBASE_SECRET` is a long random value.
5. Confirm `STRUCTUREBASE_SESSION_COOKIE_SECURE=1` in production.
6. Confirm `STRUCTUREBASE_STRICT_STARTUP_CHECKS=1` for production.
7. Confirm the active database backend and storage backend match the intended environment.
8. Deploy, then verify `/healthz` returns `status: ok`.

## Monitoring and alerting

- Review application logs after each deploy.
- Treat any `5xx` response from `/healthz` as an incident.
- Monitor for repeated login failures, upload failures, and MongoDB connection errors.
- Keep the deployment platform’s log stream and metrics enabled for the service.

## Backup and recovery

- MongoDB Atlas: enable automated backups and verify retention policies.
- SQLite fallback: create an on-disk backup copy of `data/structurebase.db` before schema changes or major data migrations.
- Cloudinary or local uploads: verify the upload destination and keep a recent copy of uploaded media before destructive changes.

## Incident response

1. Confirm whether the incident is isolated to the app, database, or storage.
2. Check `/healthz` and recent deployment logs.
3. If the database is degraded, pause new writes and validate credentials, network access, and Atlas allowlists.
4. If uploads are failing, validate the active storage backend and credential format.
5. Roll back to the previous deploy if the new release is causing an outage.
6. Re-run smoke checks after recovery and capture the status in the incident notes.

## Smoke checks

- `python -m py_compile app.py wsgi.py scripts/deploy_smoke_check.py`
- `python scripts/deploy_smoke_check.py --env-file .env --connections`
- `python scripts/deploy_smoke_check.py --skip-env --url https://your-staging-url.example`

## Rollback steps

1. Redeploy the previous known-good commit.
2. Re-check `/healthz`.
3. Confirm the login page is reachable and the admin flow is usable.
4. Document the rollback reason and the impacted time window.

## Security notes

- Rotate secrets and database credentials if they were ever exposed in logs or chat.
- Keep the admin password out of source control and out of local `.env` files that are committed.
- If a default admin password is still present in production, the app should refuse login and you must rotate credentials immediately.
