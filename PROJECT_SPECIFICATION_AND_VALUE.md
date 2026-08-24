# Structurebase Project Specification and Value

## Document purpose

This document records the implemented Structurebase product, its commercial value, architecture, operating model, deployment path, and remaining production dependencies. It is intended for the developer/agency owner and should be updated at each formal handover.

Prepared from the codebase as of 22 August 2026. Provider prices are estimates in USD, exclude taxes and currency conversion, and must be rechecked before purchase.

## 1. Product purpose

Structurebase is a full-stack real-estate discovery and operations platform for a Nigerian property business. It combines:

- a public property catalogue and conversion website;
- an internal CRM and property operations workspace;
- tenant maintenance intake;
- a controlled partner/referral programme;
- commission rules and approval records;
- branded PDF generation and document archiving;
- role-based staff access, analytics, and audit trails.

### Target users

- Nigerian property buyers, tenants, landlords, and prospective clients;
- Structurebase sales, property, operations, finance, marketing, and administrative staff;
- approved independent or company marketing partners;
- management reviewing inventory, pipeline, operations, and performance.

## 2. Business problems solved

- Scattered listings are centralised and controlled from one workspace.
- Public enquiries become structured leads instead of isolated messages.
- Inspections and follow-up dates become visible operational work.
- Tenant maintenance requests are standardised and prioritised.
- Charges, due dates, and payment states can be tracked consistently.
- Property documents can be produced from branded templates and retained in an archive.
- Partner introductions are attributable to server-verified referral records.
- Commission logic, adjustments, approvals, and payment evidence are separated and auditable.
- Individual staff accounts and permissions replace a shared back-office password.
- Management receives derived operational metrics rather than manual spreadsheets alone.

## 3. Implementation status at a glance

### Complete and testable

- responsive public website and property catalogue;
- search, multi-filter property discovery, sorting, and catalogue map;
- property detail, enquiry, inspection, WhatsApp/call, documentation, and payment-term presentation;
- admin dashboard and all core administration modules;
- listings CRUD and bulk inventory actions;
- lead/customer deduplication, pipeline, assignment, follow-up, notes, and activity;
- inspection scheduling and status workflow;
- tenant maintenance submission, image attachment, priority, assignment, and resolution workflow;
- finance charge records and payment status tracking;
- PDF preview, final generation, archive upload/download, filtering, and reuse;
- staff invitations, hashed passwords, roles, permissions, account disablement, and audit attribution;
- partner application, review, login, portal, share links, marketing materials, and performance counts;
- referral capture and 30-day signed attribution flow;
- commission rules, deterministic calculation snapshots, adjustments, approval, rejection, and recorded payout evidence;
- analytics, JSON export, SEO endpoints, health check, error pages, offline page, and service worker;
- SQLite/local storage for development and MongoDB Atlas/Cloudinary adapters for hosted environments;
- automated tests and deployment smoke-check scripts.

### Complete but dependent on final configuration/content

- outbound email requires a complete SMTP configuration;
- production database requires client-owned MongoDB Atlas credentials;
- durable hosted listing/maintenance images require client-owned Cloudinary credentials;
- durable archived/generated document files currently require a persistent filesystem because the document archive does not yet use Cloudinary;
- interactive maps require a valid Mapbox token and confirmed commercial licensing for real-estate use;
- public contact actions require real business email, phone, and WhatsApp details;
- staff bootstrapping requires the final owner name/email and strong initial credentials;
- sitemap/indexing requires the final public domain and launch approval;
- live inventory, photos, legal wording, payment plans, and verification claims require client approval.

### Not implemented as external money movement or legal assurance

- Finance and commission records do not charge cards, initiate bank transfers, or reconcile a bank account.
- PDF legal/transaction templates are drafting aids, not automated legal advice or execution services.
- Audit/export features do not replace provider-level backups, monitoring, or disaster-recovery infrastructure.

## 4. Public frontend capabilities

### Homepage and brand experience

- distinctive Structurebase visual system and responsive navigation;
- featured and completed-property presentation;
- homepage discovery and conversion routes;
- trust, verification, inspection, partner, and contact calls to action;
- configurable homepage and footer wording.

### Listings catalogue

- text search;
- purpose, availability, district, property type, price range, and bedroom filters;
- feature/verification filters supported by listing data;
- result sorting;
- responsive cards with Nigerian Naira pricing;
- map/list connection with selectable property markers;
- empty and fallback states.

### Property detail

- responsive gallery and property facts;
- price, suffix, availability, location, facilities, and amenities;
- documentation and payment terms;
- verification and market-readiness fields;
- enquiry and inspection conversion actions;
- WhatsApp and telephone actions when configured;
- location map where valid coordinates and Mapbox configuration exist.

### Public forms

- property enquiries;
- inspection requests;
- tenant maintenance requests with optional image;
- partner programme applications;
- server-side validation, CSRF protection, loading/success/error feedback, and duplicate protections where applicable.

### Informational and technical public routes

- About, Privacy, Terms, Offline;
- `robots.txt` and `sitemap.xml`;
- favicon, service worker, and health endpoint.

## 5. Admin/back-office capabilities

### Overview

- operational totals;
- action items and work queues;
- listing, lead, maintenance, finance, and document previews;
- partner and activity summaries according to permission.

### Listings

- create, edit, publish, unpublish, feature, unfeature, set availability, and delete where authorised;
- primary and gallery image management;
- property facts, facilities, verification, legal/documentation, payment, and map coordinates;
- search, saved views, filters, sorting, and bulk actions.

### Leads and customer records

- customer matching by normalised contact details;
- duplicate active-lead control by contact/property;
- pipeline stages from New to Closed won/lost or Archived;
- source, campaign, estimated value, staff assignment, follow-up date, internal summary, and chronological notes;
- linked inspections, verified partner attribution, commission record, and activity trail;
- optional admin and customer email resend controls.

### Inspections

- requested date/time, property, contact, lead, partner/referral, assignee, internal notes, and status;
- Requested, Confirmed, Rescheduled, Completed, Cancelled, and No-show workflow;
- filters and operational schedule presentation.

### Maintenance

- public intake with resident, unit, estate, contact, category, priority, description, and optional photo;
- status, owner, vendor, and internal-note management;
- New, Assigned, In Progress, and Resolved states;
- search, status, priority, assignee, and sort filters.

### Finance

- resident/unit/property charge records;
- Rent, Service Charge, Utility, Diesel Contribution, Prepaid Meter Token, and Other charge types;
- amount, due date, owner, note, and Due/Part Paid/Paid/Overdue states;
- summary totals, search, filters, sorting, and status update.

### Documents

- uploaded file archive with metadata;
- generated versus uploaded source and Final versus Filed status;
- search, document-type/source/status filters, and sorting;
- protected download and deletion;
- archive metadata editing without silently rewriting the stored PDF;
- “Use as new” payload reuse that retains the original document.

### PDF generation

- guided and advanced payload editors;
- inline preview loading, validation, success, and network-error handling;
- unsaved-change safeguards and explicit Final confirmation;
- PDF preview without persistence;
- final PDF persistence with template key, version, payload snapshot, and activity record;
- templates for billing, receipts, inspections, maintenance, notices, agreements, proposals, questionnaires, checklists, and letterhead use cases;
- Nigerian property compliance prompts on relevant templates.

### Partner programme

- public individual/company application;
- PENDING, APPROVED, SUSPENDED, and REJECTED controlled statuses;
- separate partner authentication and data boundary;
- approved-property catalogue, referral links, privacy-restricted leads/deals, commissions, payouts, profile, and marketing materials;
- native/device sharing, WhatsApp messaging, link copy, and approved asset download events;
- persisted activity-based performance metrics.

### Referral attribution

- validated partner codes and property-scoped links;
- signed, HTTP-only attribution cookie;
- first valid partner touch retained for the configured window (30 days by default);
- server-side resolution on enquiry/inspection submission;
- visit, lead, inspection, conversion, and expiry records;
- admin referral history and partner-limited visibility.

### Commissions

- percentage or fixed rules;
- Default, Property, Campaign, and Partner scopes;
- deterministic priority/specificity selection;
- immutable rule snapshot on each created commission;
- Potential, Pending, Earned, Approved, Paid, Rejected, and Cancelled states;
- controlled adjustment with reason;
- separate approval/rejection and payment-record permissions;
- payment reference and audit evidence without initiating a transfer.

### Team, audit, settings, analytics, and export

- individual staff invitation and acceptance;
- active/disabled account control;
- role/permission matrix;
- activity log with actor identity and record context;
- configurable public contact, coverage, homepage, footer, and communication presentation fields;
- communication preview;
- business analytics derived from current records;
- permission-protected JSON export.

## 6. Roles and permissions

| Role | Primary access |
|---|---|
| Super admin | All application permissions, including team administration, settings, audit, and export |
| Administrator | Broad operational access excluding staff invite/edit/disable |
| Property manager | Listings, inspections, maintenance, documents, and analytics |
| Sales manager | Leads/customers, inspections, partner/referral visibility, listings view, and analytics |
| Marketing manager | Listings view, partners, referrals, content permission, and analytics |
| Finance manager | Finance, documents view, commission management/approval/payment recording, and analytics |

Permissions are checked server-side by route decorators. Partner accounts are stored and authenticated separately and never inherit staff permissions.

## 7. Important workflows

### Inventory-to-enquiry

1. Staff creates and verifies a listing.
2. Staff publishes it.
3. A visitor searches and opens the property.
4. The visitor submits an enquiry or inspection request.
5. The system matches/creates the customer and lead.
6. Staff assigns an owner and progresses the lead.
7. Activity, partner attribution, and eligible commission state remain linked.

### Tenant operations

1. A resident submits a maintenance request.
2. The system records priority and optional image.
3. Operations assigns an owner/vendor.
4. Staff updates status and internal notes.
5. Resolution remains available for operational reporting.

### Document lifecycle

1. Staff selects a guided template or reuses a prior generated payload.
2. Staff enters current parties, references, dates, values, and clauses.
3. Preview renders without saving.
4. Validation errors remain inline and preserve work.
5. Staff reviews the PDF and confirms Final save.
6. The PDF, template version, payload snapshot, metadata, and activity record are archived.

### Partner-to-commission

1. An applicant registers and staff approves the account.
2. The partner shares a signed property referral link.
3. The first valid touch is retained for the attribution window.
4. An enquiry/inspection resolves attribution server-side.
5. A qualifying lead with a matching active rule receives a commission record and rule snapshot.
6. Deal milestones move the commission through controlled states.
7. Authorised finance staff approve and later record independent payment evidence.

## 8. Data model at a useful level

Both SQLite and MongoDB backends implement equivalent application records:

- listings;
- contacts/customers;
- enquiries/leads;
- lead notes;
- inspections;
- partners;
- referrals and referral events;
- commission rules and commissions;
- marketing assets and partner marketing events;
- maintenance tickets;
- financial records;
- documents;
- site preferences;
- staff users, invitations, and login attempts;
- activity/audit log.

Records use public identifiers rather than exposing internal database row IDs. MongoDB collections include indexes for public IDs, workflow states, dates, owners, listing/partner relationships, and uniqueness constraints. SQLite creates the corresponding tables and indexes for local development and fallback operation.

## 9. Backend and API functionality

- Flask server-rendered routes and form handlers;
- Waitress WSGI production process;
- HTML responses plus generator specification JSON, structured export JSON, health JSON, robots, sitemap, and service worker;
- server-side validation and normalisation;
- database abstraction supporting SQLite or MongoDB;
- image-media abstraction supporting local uploads or Cloudinary;
- ReportLab PDF generation and PyPDF-based test verification;
- SMTP email delivery through configured credentials;
- Mapbox token supplied to the public map experience;
- signed cookies and session-backed authentication.

This is not a separate public REST API product. Internal JSON endpoints and exports remain permission-controlled or purpose-specific.

## 10. Authentication and security

- Werkzeug password hashing for staff and partners;
- individual staff accounts and least-privilege roles;
- separate partner authentication;
- single-use hashed staff invitation tokens with expiry;
- CSRF token validation on state-changing forms;
- persistent login-attempt tracking and configurable lockout window;
- secure, HTTP-only, SameSite session cookies in production;
- signed referral cookies;
- server-side permission checks;
- safe return-target validation;
- upload type/size handling and generated filenames;
- startup configuration validation and strict production checks;
- security response headers including Content Security Policy controls;
- structured request/error logging without exposing production configuration in `/healthz`;
- audit records for significant administrative and commercial actions.

Final production security still requires unique secrets, limited provider credentials, account ownership, backup verification, logging review, and prompt credential rotation after any exposure.

## 11. SEO, accessibility, performance, and UX

### SEO

- semantic public headings and page titles;
- configurable canonical public base URL;
- `robots.txt` and `sitemap.xml`;
- deliberate search-indexing switch for staging versus production;
- noindex treatment for private/admin contexts;
- structured property content suitable for crawlable server-rendered pages.

### Accessibility and UX

- keyboard-operable navigation and native form controls;
- visible focus states;
- accessible labels, status regions, alerts, and validation feedback;
- reduced-motion handling in the styling layer;
- responsive desktop, tablet, and mobile layouts;
- loading, empty, success, error, offline, disabled, hover, and focus states;
- mobile navigation, back-to-top behavior, sticky/contextual actions, and no-horizontal-overflow verification;
- meaningful image alternative text inputs and lazy loading where appropriate.

### Performance

- server-rendered HTML with limited client JavaScript;
- WebP/static image assets and responsive presentation;
- lazy map initialisation and fallback messaging;
- lazy-loaded imagery where applicable;
- asset-version helpers and service-worker support;
- database indexes for principal queries;
- Waitress production serving and health checks.

## 12. Technical stack and architecture

| Layer | Implementation |
|---|---|
| Backend | Python 3.12, Flask 3.1 |
| Production server | Waitress |
| Templates | Jinja server-rendered HTML |
| Frontend | HTML, CSS, vanilla JavaScript |
| Local database | SQLite |
| Hosted database | MongoDB Atlas through PyMongo |
| Local media | Repository/local upload directories |
| Hosted image media | Cloudinary |
| Archived/generated files | Local `data/documents` filesystem; production requires a mounted persistent disk or a future object-storage adapter |
| PDF generation | ReportLab |
| PDF verification | PyPDF |
| Image processing | Pillow |
| Map | Mapbox GL JS/token configuration |
| Email | Standard SMTP |
| Tests | Pytest |
| Source/deploy | GitHub + Render configuration |

The application is a modular monolith: one Flask service owns public pages, admin/partner routes, business rules, storage/database adapters, and document generation. This is appropriate for the current scale and avoids premature distributed-system complexity.

## 13. Environment and configuration

Primary production settings are environment-driven. Important groups include:

- application environment, secret, proxy trust, logging, strict checks, and public base URL;
- MongoDB backend, URI, database name, and collection names;
- Cloudinary backend, URL/credentials, and folder;
- initial admin username/password/name/email and invitation expiry;
- secure-session and login-attempt controls;
- public contact, phone, WhatsApp, office, coverage, homepage, and footer information;
- Mapbox token;
- complete SMTP settings;
- search-indexing switch.

Real `.env` files and secrets must not be committed. `.env.example`, `render-env.example`, and `render.yaml` are configuration references only.

## 14. Recommended deployment workflow

### Recommended provider arrangement

The best current fit is:

- [GitHub](https://github.com/TeflonDon0/STRUCTURE-BASE-WEBSITE) for source control and release history;
- [Render Web Service](https://render.com/docs/your-first-deploy) for the Flask/Waitress application;
- [MongoDB Atlas](https://www.mongodb.com/atlas/database) for durable application data;
- [Cloudinary](https://cloudinary.com/pricing) for durable listing and maintenance images supported by the current adapter;
- a [Render persistent disk](https://render.com/docs/disks) mounted at `/opt/render/project/src/data` for the current document archive;
- [Mapbox](https://www.mapbox.com/pricing) for the current map implementation, subject to commercial real-estate licensing confirmation;
- client-owned SMTP or Google Workspace mailbox for application email;
- client-owned domain registrar/DNS provider for the final domain.

Cloudinary currently covers image uploads, not document PDFs or uploaded archive files. Do not use SQLite, local image uploads, or the document archive as durable storage on a free Render service: Render documents that free instances spin down after 15 minutes and lose local filesystem changes on restarts, redeploys, and spin-downs. See [Render free-service limitations](https://render.com/docs/free).

### Environment separation

Use three environments:

1. **Local development** — SQLite, local uploads, safe test credentials, indexing off.
2. **Staging/client acceptance** — separate Render service, separate Atlas database, separate Cloudinary folder, test contacts, indexing off. On a free service, document files are temporary and must not be treated as retained records.
3. **Production** — always-on Render service, production Atlas database, production Cloudinary folder, persistent `data` disk for document files, real contacts/domain, indexing enabled only after launch approval.

Never point staging and production at the same database or media folder.

### Git and release flow

1. Develop on a short-lived feature branch or the existing worktree.
2. Run automated tests and browser checks locally.
3. Open/review the diff and commit a focused change.
4. Push the branch to GitHub.
5. Merge the reviewed change to `main`.
6. Allow staging to auto-deploy from `main`.
7. Run deployment smoke checks and client acceptance tests on staging.
8. Create an annotated release tag such as `v1.0.0` after approval.
9. Deploy production manually from the exact approved commit/tag.
10. Verify health, login, public discovery, forms, uploads, document generation, attribution, and email.
11. Record the release, configuration changes, and rollback commit.

This avoids deploying unreviewed work directly to production and makes rollback deterministic.

### Initial staging deployment

1. Make the GitHub repository private if client source should not be public; GitHub Free supports private repositories.
2. Create a client-owned MongoDB Atlas project and staging database.
3. Create a least-privilege database user and appropriate network-access rule.
4. Create a client-owned Cloudinary account and `structurebase/staging` folder.
5. Create a Render **Web Service** from the GitHub repository or use the Blueprint configuration.
6. Use build command `pip install -r requirements.txt`.
7. Use start command `waitress-serve --listen=0.0.0.0:$PORT wsgi:app`.
8. Set health check path `/healthz`.
9. Enter every required secret in Render's Environment settings; never upload the real `.env` file.
10. Set the staging public URL and `STRUCTUREBASE_SEARCH_INDEXING_ENABLED=0`.
11. Understand that free Render blocks common SMTP ports and cannot attach a persistent disk. Email delivery and document-file retention therefore require the paid staging tier or must be marked unverified during free-tier acceptance.
12. Run:

   ```bash
   python -m pytest -q
   python -m py_compile app.py wsgi.py scripts/deploy_smoke_check.py
   python scripts/deploy_smoke_check.py --env-file .env --connections
   python scripts/deploy_smoke_check.py --skip-env --url https://your-staging-url.example
   ```

13. Complete client acceptance using non-production contacts and test records.

### Production promotion

1. Freeze changes during final acceptance.
2. Export and back up staging data that must be retained.
3. Create the production Atlas database/user and Cloudinary folder.
4. Create a separate Render production service on an always-on paid instance.
5. Attach the smallest suitable persistent disk at `/opt/render/project/src/data`; this covers the code's `data/documents` path. Update `render.yaml` or record the dashboard-only disk setting so infrastructure configuration does not drift.
6. Supply new production-only secrets; do not copy staging passwords unnecessarily.
7. Replace all placeholder contacts, owner details, legal copy, inventory, and Mapbox licensing/token information.
8. Set the final HTTPS public base URL.
9. Connect and verify the custom domain and managed TLS.
10. Deploy the approved release tag.
11. Keep indexing off while performing smoke and critical-flow tests.
12. Upload/generate a test document, redeploy once, and confirm the file still downloads from the archive.
13. Enable indexing only after formal launch approval.
14. Monitor logs and business flows closely for the first 24–72 hours.

For production, the effective Render service configuration should include the equivalent of:

```yaml
type: web
runtime: python
plan: starter
buildCommand: pip install -r requirements.txt
startCommand: waitress-serve --listen=0.0.0.0:$PORT wsgi:app
healthCheckPath: /healthz
disk:
  name: structurebase-data
  mountPath: /opt/render/project/src/data
  sizeGB: 1
```

Keep the existing free `render.yaml` for acceptance only, or create a separately reviewed production Blueprint. Do not silently rely on dashboard settings that disagree with the version-controlled deployment contract.

### Continuous deployment policy

- Staging: auto-deploy `main` after checks pass.
- Production: manual deploy/promote from an approved tag or exact commit.
- Database/storage migrations: back up first and run as an explicit release step.
- Rollback: redeploy the previous known-good Render commit, then run `/healthz` and critical-flow checks.
- Secrets: rotate in provider dashboards; never commit them.

## 15. Potential deployment costs

Prices below are current estimates as of 22 August 2026 and may change.

### Client-acceptance / low-cost staging

| Service | Suggested tier | Estimated monthly cost | Notes |
|---|---:|---:|---|
| GitHub | Free | $0 | Unlimited private repositories are available on GitHub Free. |
| Render web service | Free | $0 | Sleeps after 15 minutes; cold start can take about one minute; unsuitable for production. |
| MongoDB Atlas | M0 Free | $0 | 512 MB, one free cluster per project; suitable for acceptance/small proof-of-concept use. |
| Cloudinary | Free | $0 | 25 monthly credits shared across storage, bandwidth, and transformations. |
| Mapbox | Usage tier | Potentially $0 usage, licence to confirm | GL JS lists up to 50,000 monthly map loads free, but Mapbox also states real-estate commercial applications require a Commercial Application License. Confirm directly before launch. |
| SMTP | Existing business mailbox | $0 incremental or mailbox cost | Depends on the client's email provider. |
| Domain | Not required for staging | $0 | Use the temporary `onrender.com` address. |

Estimated staging infrastructure: **$0/month**, with cold starts and free-tier limits. Document files disappear after a spin-down/restart/redeploy, and standard SMTP ports are blocked. It must not store production-only data.

### Recommended small-production baseline

| Service | Suggested tier | Estimated monthly cost | Notes |
|---|---:|---:|---|
| GitHub | Free | $0 | Upgrade only if agency/team governance requires it. |
| Render web service | Starter | about $7 | Always-on entry tier; confirm on [Render pricing](https://render.com/pricing). |
| Render persistent disk | 1 GB starting allocation | about $0.25 | Current documents require `data/documents`; Render lists persistent disks at $0.25/GB/month. A disk prevents multi-instance scaling and zero-downtime deploys. |
| MongoDB Atlas | Flex | $8–$30 | 5 GB and daily snapshots; usage-based. MongoDB positions Flex for prototypes/low-throughput apps; move to Dedicated if stronger production guarantees are required. |
| Cloudinary | Free initially | $0 | Monitor the 25-credit monthly allowance; paid self-service pricing should be checked when usage approaches the limit. |
| Mapbox | Commercial terms | Unknown until confirmed | Usage may remain inside the free request tier, but real-estate licensing can create a separate cost. Obtain written confirmation/quote. |
| SMTP/business email | Existing or paid mailbox | variable | Commonly already covered by Google Workspace/Microsoft 365; not bundled with Render. |
| Domain | Client-selected registrar | commonly about $10–$30/year | Exact `.com`, `.ng`, or `.com.ng` price varies by registrar and renewal year. |

Expected baseline before email/domain/Mapbox licensing: **approximately $15.25–$37.25/month** (`$7 Render + $0.25 disk + $8–$30 Atlas`).

### Stronger production option

MongoDB documents Dedicated clusters as starting around **$56.94/month** and intended for production applications requiring dedicated resources. With Render Starter and a 1 GB persistent disk, this produces an infrastructure baseline of roughly **$64.19/month**, before Cloudinary overage/upgrade, email, domain, Mapbox licensing, monitoring, taxes, and data transfer.

### Cost controls

- Set provider budgets and billing alerts.
- Keep staging on free/low tiers and suspend it when not required.
- Monitor Cloudinary credits and Mapbox map loads.
- Avoid storing uploads on Render's local filesystem.
- Review Atlas operation/storage growth monthly.
- Keep Render and Atlas regions reasonably close to reduce latency and possible transfer costs.
- Recheck provider pricing at each renewal or scaling decision.

## 16. Deployment links

- Render first deploy: <https://render.com/docs/your-first-deploy>
- Render free limitations: <https://render.com/docs/free>
- Render pricing: <https://render.com/pricing>
- Render persistent disks: <https://render.com/docs/disks>
- MongoDB Atlas free cluster: <https://www.mongodb.com/docs/atlas/tutorial/deploy-free-tier-cluster/>
- MongoDB Atlas pricing: <https://www.mongodb.com/pricing>
- MongoDB Atlas Flex costs: <https://www.mongodb.com/docs/atlas/billing/atlas-flex-costs/>
- Cloudinary pricing: <https://cloudinary.com/pricing>
- Cloudinary billing/credits: <https://cloudinary.com/documentation/billing_and_plans>
- Mapbox pricing and licensing note: <https://www.mapbox.com/pricing>
- GitHub pricing: <https://github.com/pricing>
- Existing project repository: <https://github.com/TeflonDon0/STRUCTURE-BASE-WEBSITE>

## 17. Final production requirements

- final client-owned domain and DNS access;
- real business email, phone, WhatsApp, office, coverage, and owner identity;
- unique production secret and initial credentials;
- client-owned Render, Atlas, Cloudinary, Mapbox, and email accounts or formally documented agency ownership;
- Atlas backup/restore policy appropriate to the selected tier;
- Cloudinary retention/backup review;
- confirmed Mapbox commercial real-estate terms;
- final listing inventory and rights-approved imagery;
- approved privacy, terms, marketing, and legal-document wording;
- staff list and approved least-privilege roles;
- monitoring/alert recipients and incident owner;
- acceptance sign-off and agreed maintenance/support arrangement.

## 18. Final deployment and handover checklist

### Release quality

- [ ] Working tree reviewed and intended changes committed.
- [ ] Automated tests, Python compilation, JavaScript syntax, and diff checks pass.
- [ ] Desktop, tablet, and mobile critical routes pass.
- [ ] No console errors or broken links in critical flows.
- [ ] Staging acceptance is signed off.
- [ ] Production release tag exists.

### Data and providers

- [ ] Production Atlas database and least-privilege user configured.
- [ ] Backup policy enabled and a restore tested or documented.
- [ ] Production Cloudinary folder/credentials configured.
- [ ] Render persistent disk is mounted at `/opt/render/project/src/data`, and a document survives a redeploy test.
- [ ] Existing SQLite data migrated only if approved and verified.
- [ ] Real SMTP settings tested end to end.
- [ ] Mapbox commercial use confirmed.

### Security

- [ ] Strong unique `STRUCTUREBASE_SECRET` configured.
- [ ] Secure cookies and strict startup checks enabled.
- [ ] Default/test credentials removed or rotated.
- [ ] Owner and staff use individual accounts.
- [ ] Provider credentials are stored only in secret managers/dashboard variables.
- [ ] Exposure-response and credential-rotation owners are documented.

### Public launch

- [ ] Real contact and company details replace placeholders.
- [ ] Domain and TLS work on both apex and chosen `www` form.
- [ ] Canonical base URL is correct.
- [ ] Privacy/Terms/legal content approved.
- [ ] Live inventory, prices, availability, coordinates, and images approved.
- [ ] Search indexing enabled only after final verification.
- [ ] Sitemap and robots output checked on the live domain.

### Critical-flow verification

- [ ] `/healthz` returns `status: ok`.
- [ ] Staff login and permissions work.
- [ ] Listing create/edit/publish and upload work.
- [ ] Public search, property detail, map marker, enquiry, and inspection work.
- [ ] Maintenance request and receipt work.
- [ ] PDF preview, save, archive, reuse, download, and delete permissions work.
- [ ] Partner application/review/login/share attribution works.
- [ ] Commission rule and controlled state progression work with test data.
- [ ] Email notifications and receipts arrive.
- [ ] Export and provider backups are available.

### Handover

- [ ] Client receives `CLIENT_USER_MANUAL.md` and training.
- [ ] Account ownership and billing responsibility are recorded.
- [ ] Provider access uses named accounts and least privilege.
- [ ] Support hours, response expectations, maintenance scope, and renewal costs are agreed.
- [ ] Rollback, backup, incident, and credential-rotation procedures are handed over.

## 19. Known limitations and risks

- Free Render is acceptance-only because it sleeps and has ephemeral storage.
- Atlas M0 is a development/acceptance tier; Flex remains shared and MongoDB describes Dedicated as the stronger production option.
- Cloudinary Free capacity can be exhausted by image-heavy inventory or traffic.
- Document files currently use local filesystem storage. Production requires a persistent disk; this prevents horizontal scaling and zero-downtime deploys on Render. A Cloudinary raw-file or S3-compatible document adapter is the preferred future route when scaling becomes necessary.
- Mapbox's real-estate commercial licensing statement requires confirmation even when usage is below its technical free threshold.
- SMTP is synchronous; high email volume would benefit from a background queue and retry service.
- The application is a single service and does not currently include horizontally coordinated background jobs.
- PDF templates require continuing legal/content ownership and version review.
- “Paid” commission and finance states record evidence but do not reconcile external banking.
- Provider-level monitoring, automated off-site export, and a tested disaster-recovery schedule remain deployment/operations responsibilities.

## 20. Sensible future enhancements

Prioritise only after real client usage identifies demand:

1. background email queue, delivery webhooks, and retry visibility;
2. automated scheduled backup export and restore drills;
3. error monitoring and uptime alerts;
4. document Draft/Reviewed/Approved workflow and explicit version chains;
5. bulk document actions after archive volume justifies them;
6. calendar integration for inspections;
7. payment-provider integration with proper reconciliation and webhook controls;
8. richer reporting exports with date ranges and role-controlled financial detail;
9. content-managed public editorial pages if ongoing marketing requires them;
10. two-factor authentication or external identity provider for higher-risk operations;
11. dedicated search/geocoding workflow for consistent Nigerian location data;
12. background image processing for larger media volume.

## 21. Business Value Delivered

### Operational efficiency

Listings, enquiries, inspections, maintenance, finance, documents, partners, referrals, and commissions are managed through one coherent workspace. Staff spend less time moving between disconnected forms and records.

### Reduced manual work

Guided document generation, reusable payloads, status workflows, derived dashboard figures, server-side referral attribution, and rule-based commission calculation reduce repeated data entry and manual calculation.

### Centralised business management

The product provides a shared operational record across sales, property management, operations, finance, marketing, and management while role permissions limit unnecessary access.

### Improved customer experience

Prospects can discover suitable properties, understand price and availability, contact the team, and request inspections from responsive public pages. Tenants receive a structured maintenance channel rather than an informal message trail.

### Faster and safer follow-up

Lead owners, stages, notes, inspection links, follow-up dates, maintenance priorities, finance due dates, and dashboard action items make outstanding work visible and accountable.

### Partner-channel control

Approved partners receive consistent property information, trackable links, privacy-limited opportunities, and recorded performance. The business retains server-verified attribution and auditable commission rules rather than relying only on informal claims.

### Professional brand presence

The public experience, property presentation, Nigerian-market terminology, responsive behavior, branded documents, and consistent communication templates create a more credible client-facing operation.

### Better visibility

Operational summaries, analytics, referrals, rule snapshots, payout evidence, and actor-attributed audit records give management a clearer view of activity and exceptions.

### Scalability without premature complexity

The modular Flask architecture can operate inexpensively at current scale, while MongoDB Atlas and Cloudinary remove dependence on one server's disk. The environment-driven design supports separate staging and production services and future provider upgrades.

### Risk reduction

Individual accounts, permissions, hashed credentials, CSRF controls, login throttling, signed attribution, structured validation, explicit commission approvals, document preview, activity logs, and controlled production settings reduce common operational and security mistakes.

---

Document status: pre-production agency specification. Update prices, final provider selections, client-owned account details, and production sign-off data immediately before deployment.
