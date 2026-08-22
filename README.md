# Structurebase

Flask property listing app for sale, rent, and operations workflows across Nigeria, prepared for a starter production stack:

- `Render` for the current client-acceptance web service
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
- Added `railway.json`, `render.yaml`, and `/healthz` for deployment
- Added a SQLite-to-Mongo migration script

## Local Run

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
$env:PORT="8000"
python app.py
```

Open [http://localhost:8000](http://localhost:8000).

## Initial Local Super Admin

- Username: `admin`
- Password: `change-me-structurebase`

On the first run against an empty database, these values are converted into an individual `SUPER_ADMIN` account with a hashed password. They are not used as a shared account after staff records exist. Change them before public deployment and set `STRUCTUREBASE_INITIAL_ADMIN_NAME` and `STRUCTUREBASE_INITIAL_ADMIN_EMAIL` to the owner's identity.

Additional staff are invited from `Dashboard -> Team`. Invitation links are single-use and expire after `STRUCTUREBASE_STAFF_INVITATION_HOURS` (48 hours by default).

## Realtor / Marketing Partner Programme

- Public applications: `/partners/register`
- Partner sign-in: `/partners/login`
- Approved partner portal: `/partner`
- Each approved partner receives property-specific share links. The first valid partner touch per property is retained for 30 days; later competing codes cannot overwrite it.
- Attribution is resolved server-side when an enquiry or inspection is submitted. Public form fields cannot choose or replace the source partner.
- Staff review queue: `Dashboard -> Partners`

Partner accounts are stored separately from staff accounts and never inherit admin permissions. New applications start as `PENDING`; staff with `partners.approve` can approve, reject, suspend, or reactivate them through validated transitions. Partner-facing lead data is restricted to server-attributed records and masks customer contact details.

### Partner marketing toolkit

Approved partners can open `Partner portal -> Marketing materials` to copy attributed links, use device sharing, send prefilled WhatsApp messages, and download approved property media. The primary published image is available immediately. The `marketing_assets` store is ready for additional approved brochures, images, documents, and videos without exposing storage paths or internal property data.

Performance figures are derived from persisted partner actions and attributed referral, enquiry, inspection, and closed-deal records. They are operational counts, not estimated reach or vanity analytics.

## Commission Management

- Finance and administrator roles configure percentage or fixed rules with default, property, campaign, or partner scope.
- Rule selection is deterministic by priority and specificity. A rule snapshot is retained on each commission so later configuration changes cannot rewrite history.
- Attributed deals progress through `POTENTIAL`, `PENDING`, and `EARNED` as the lead reaches negotiation, deposit, and closed-won stages.
- Approval, rejection, adjustments, and payout evidence are separate permission-controlled actions with audit records.
- `PAID` records internal evidence only; the application does not initiate a bank transfer.

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
- `STRUCTUREBASE_ADMIN_PASSWORD_HASH`
- `STRUCTUREBASE_INITIAL_ADMIN_NAME`
- `STRUCTUREBASE_INITIAL_ADMIN_EMAIL`
- `STRUCTUREBASE_STAFF_INVITATION_HOURS`
- `STRUCTUREBASE_CONTACT_EMAIL`
- `STRUCTUREBASE_CONTACT_PHONE`
- `STRUCTUREBASE_CONTACT_PHONE_RAW`
- `STRUCTUREBASE_WHATSAPP_PHONE`
- `STRUCTUREBASE_SITE_NAME`
- `STRUCTUREBASE_PUBLIC_BASE_URL`
- `STRUCTUREBASE_SEARCH_INDEXING_ENABLED` (keep `0` for client acceptance; set `1` only on the final public domain)
- `STRUCTUREBASE_OFFICE_ADDRESS`
- `STRUCTUREBASE_COVERAGE_AREA`
- `STRUCTUREBASE_FOOTER_SUMMARY`

Database:

- `STRUCTUREBASE_DATABASE_BACKEND`
  - use `auto` locally
  - use `mongodb` on Render when Atlas is ready
- `STRUCTUREBASE_MONGODB_URI`
- `STRUCTUREBASE_MONGODB_DB_NAME`
- `STRUCTUREBASE_MONGODB_COLLECTION`
- `STRUCTUREBASE_MONGODB_ENQUIRIES_COLLECTION`
- `STRUCTUREBASE_MONGODB_CONTACTS_COLLECTION`
- `STRUCTUREBASE_MONGODB_LEAD_NOTES_COLLECTION`
- `STRUCTUREBASE_MONGODB_INSPECTIONS_COLLECTION`
- `STRUCTUREBASE_MONGODB_PARTNERS_COLLECTION`
- `STRUCTUREBASE_MONGODB_REFERRALS_COLLECTION`
- `STRUCTUREBASE_MONGODB_REFERRAL_EVENTS_COLLECTION`
- `STRUCTUREBASE_REFERRAL_ATTRIBUTION_DAYS` (defaults to `30`)
- `STRUCTUREBASE_MONGODB_COMMISSION_RULES_COLLECTION`
- `STRUCTUREBASE_MONGODB_COMMISSIONS_COLLECTION`

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
- Allow the Render service to reach Atlas through the selected Atlas network-access policy
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
- Create a new Render Blueprint or web service from the GitHub repo
- Render will detect `render.yaml` when using the Blueprint flow
- Confirm the start command is:
  - `waitress-serve --listen=0.0.0.0:$PORT wsgi:app`
- Add every `sync: false` value listed in `render.yaml`
- Health check path: `/healthz`

Notes:

- You will get an `onrender.com` URL until you connect a custom domain
- Keep the client test service separate from the future production service

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

- Replace acceptance inventory and representative media with client-approved live records
- Add the final public domain and enable search indexing only after launch approval
- Add error monitoring and database backups
- Add background job processing for email delivery and retries
- Add a staging environment before public launch
