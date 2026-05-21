# Structurebase

Flask property listing app for sale, rent, and operations workflows across Nigeria, prepared for a starter production stack:

- `Render` for app hosting
- `MongoDB Atlas` for the primary database
- `Cloudinary` for image storage when you are ready
- local SQLite and local uploads still available for fallback development

## What Changed

- Database backend now auto-selects:
  - `MongoDB Atlas` when `STRUCTUREBASE_MONGODB_URI` is set
  - `SQLite` when it is not
- Upload storage now auto-selects:
  - `Cloudinary` when `CLOUDINARY_URL` or explicit Cloudinary credentials are set
  - local `static/uploads` when they are not
- Added `render.yaml` and `/healthz` for Render deployment
- Added a SQLite-to-Mongo migration script

## Local Run

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
$env:PORT="8000"
python app.py
```

Open [http://localhost:8000](http://localhost:8000).

## Default Local Admin Credentials

- Username: `admin`
- Password: `change-me-structurebase`

Change these before public deployment.

## Environment Variables

Start from `.env.example`.

Core:

- `STRUCTUREBASE_SECRET`
- `STRUCTUREBASE_ENV`
- `STRUCTUREBASE_STRICT_STARTUP_CHECKS`
- `STRUCTUREBASE_TRUST_PROXY_COUNT`
- `STRUCTUREBASE_LOG_LEVEL`
- `STRUCTUREBASE_ADMIN_USERNAME`
- `STRUCTUREBASE_ADMIN_PASSWORD`
- `STRUCTUREBASE_CONTACT_EMAIL`
- `STRUCTUREBASE_CONTACT_PHONE`
- `STRUCTUREBASE_CONTACT_PHONE_RAW`
- `STRUCTUREBASE_WHATSAPP_PHONE`
- `STRUCTUREBASE_SITE_NAME`

Database:

- `STRUCTUREBASE_DATABASE_BACKEND`
  - use `auto` locally
  - use `mongodb` on Render when Atlas is ready
- `STRUCTUREBASE_MONGODB_URI`
- `STRUCTUREBASE_MONGODB_DB_NAME`
- `STRUCTUREBASE_MONGODB_COLLECTION`

Storage:

- `STRUCTUREBASE_STORAGE_BACKEND`
  - use `auto` or `local` until Cloudinary is ready
  - use `cloudinary` when Cloudinary is configured
- `CLOUDINARY_URL`
- `STRUCTUREBASE_CLOUDINARY_CLOUD_NAME`
- `STRUCTUREBASE_CLOUDINARY_API_KEY`
- `STRUCTUREBASE_CLOUDINARY_API_SECRET`
- `STRUCTUREBASE_CLOUDINARY_FOLDER`

Temporary mail placeholders:

- `STRUCTUREBASE_SMTP_HOST`
- `STRUCTUREBASE_SMTP_PORT`
- `STRUCTUREBASE_SMTP_USERNAME`
- `STRUCTUREBASE_SMTP_PASSWORD`
- `STRUCTUREBASE_SMTP_FROM_EMAIL`

## Starter Stack Setup

### 1. MongoDB Atlas

Your part:

- Create an Atlas cluster
- Create a database user
- Allow Render outbound access in Atlas network settings
- Copy the connection string
- Set:
  - `STRUCTUREBASE_DATABASE_BACKEND=mongodb`
  - `STRUCTUREBASE_MONGODB_URI=<your atlas uri>`
  - `STRUCTUREBASE_MONGODB_DB_NAME=structurebase`

Notes:

- Atlas usually gives a `mongodb+srv://...` URI, which is supported here
- On first run with an empty Mongo database, the app seeds the sample listings automatically

### 2. Cloudinary

Optional for phase 1, but recommended before serious listing volume.

Your part:

- Create or confirm your Cloudinary product environment
- Copy either the full `CLOUDINARY_URL` or the cloud name, API key, and API secret
- Choose an upload folder for listing media
- Set:
  - `STRUCTUREBASE_STORAGE_BACKEND=cloudinary`
  - `CLOUDINARY_URL=cloudinary://...`
  - or:
    - `STRUCTUREBASE_CLOUDINARY_CLOUD_NAME=...`
    - `STRUCTUREBASE_CLOUDINARY_API_KEY=...`
    - `STRUCTUREBASE_CLOUDINARY_API_SECRET=...`
  - `STRUCTUREBASE_CLOUDINARY_FOLDER=structurebase/listings`

If these are not present, uploads continue using local disk.

### 3. Render

Your part:

- Push this repo to GitHub
- Create a new Render Web Service from the repo
- Render will detect `render.yaml`, or you can configure manually:
  - Build command: `pip install -r requirements.txt`
  - Start command: `waitress-serve --listen=0.0.0.0:$PORT wsgi:app`
- Add the environment variables from `.env.example`
- Health check path: `/healthz`

Notes:

- Free tier cold starts are expected
- You will get an `onrender.com` URL until you buy a domain

## Migrating Existing SQLite Data To MongoDB

If you have local data you want to carry over:

```powershell
python scripts/migrate_sqlite_to_mongodb.py
```

This reads `data/structurebase.db` and upserts each row into MongoDB using `public_id=legacy-<sqlite-id>`.

## Current Production Behavior

- Local sample images still ship with the app
- Uploaded images can now resolve correctly from either local storage or Cloudinary
- Listing routes support both legacy SQLite integer IDs and Mongo-style string IDs

## Recommended Next Steps After Starter Stack

- Replace single shared admin login with real user accounts and roles
- Move login rate limiting to a durable shared store
- Add real server-side enquiry handling before you rely on Gmail
- Add error monitoring and database backups
- Add background job processing for email delivery and retries
- Add a staging environment before public launch
