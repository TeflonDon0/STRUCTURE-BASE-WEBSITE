# Structurebase Client User Manual

## About this manual

This manual explains how to operate the Structurebase website and admin workspace. It is written for normal day-to-day users, not developers.

The exact pages you can see depend on your assigned staff role. If a menu item described here is missing, your account probably does not have permission to use it. Ask the Super admin rather than sharing another person's account.

## 1. What Structurebase does

Structurebase combines a public Nigerian property website with an internal business workspace.

The public website allows visitors to:

- browse and filter available properties;
- review property details, pricing, location, verification, documentation, and payment information;
- inspect available properties on the catalogue map;
- send an enquiry;
- request a property inspection;
- submit a tenant maintenance request;
- contact the team by the configured phone or WhatsApp details;
- apply for the Partner Programme.

The admin workspace allows authorised staff to:

- manage property listings and publication status;
- receive, assign, and progress leads;
- schedule and update inspections;
- manage maintenance requests and vendor follow-up;
- record charges and payment status;
- upload and generate documents;
- review partners, referrals, commissions, analytics, staff access, and audit history;
- update approved website and communication settings.

The approved partner portal gives each partner access only to their own approved marketing activity, referral links, attributed opportunities, commission records, and marketing materials.

## 2. Before you begin

The developer must provide:

- the live or client-testing website address;
- your personal staff username;
- your temporary password or staff invitation link;
- confirmation of your role and responsibilities.

Do not use placeholder contact information for a public launch. The final business email, phone number, WhatsApp number, office address, domain, and owner details must be supplied before production goes live.

## 3. Quick start

1. Open the website address supplied by the developer.
2. Add `/login` to the address, for example `https://example.com/login`.
3. Enter your username and password.
4. Select **Sign in**.
5. Review **Overview** for action items and work queues.
6. Open the module you need from the navigation.
7. Sign out with **Logout** when using a shared device.

### First sign-in from an invitation

1. Open the invitation link sent to your email.
2. Choose a username using letters, numbers, dots, dashes, or underscores.
3. Create a password of at least 12 characters containing letters and numbers.
4. Do not include your name, email, or username in the password.
5. Confirm the password and complete account activation.

Invitation links are single-use and normally expire after 48 hours. Ask the Super admin to revoke and replace an expired invitation.

## 4. Understanding the admin navigation

The main navigation keeps daily operational areas visible:

- **Overview** — priorities, totals, action items, and recent work.
- **Listings** — property inventory and publication controls.
- **Leads** — enquiries and the sales pipeline.
- **Inspections** — requested and scheduled property visits.
- **Operations** — tenant maintenance and vendor follow-up.
- **Finance** — charges, amounts due, and payment status.
- **Documents** — uploaded files and generated PDFs.
- **More** — Team, Partners, Referrals, Commissions, Analytics, Audit, and Settings, depending on your permissions.

On a phone, select the menu button, then select the required module. Open **More** for the less frequently used administration modules.

The Structurebase logo returns to **Overview** from the admin workspace. **View site** opens the public website.

## 5. Using the Overview dashboard

Use **Overview** at the start of each working day.

1. Review the action items for work that needs attention.
2. Check operational totals and pipeline summaries.
3. Review recent listings, enquiries, maintenance requests, finance items, and documents.
4. Follow links from each queue to the relevant record.
5. Assign owners and follow-up dates instead of relying on memory or private notes.

Dashboard figures are calculated from stored records. They are not estimates. If a figure appears wrong, first check the status, owner, date, and value recorded on the underlying item.

## 6. Property listings

### Find and filter listings

1. Open **Listings**.
2. Use **Search** for a title, district, reference, or other visible listing information.
3. Use the saved views and filters for drafts, published listings, featured listings, availability, verification, and other inventory states.
4. Select **Apply** after changing filters.
5. Select **Reset** to clear them.

### Create a listing

1. Open **Listings**.
2. Select **New listing**.
3. Complete the property identity, location, purpose, type, price, summary, and description.
4. Add bedrooms, bathrooms, area, service information, amenities, verification details, documentation, and payment-plan information where known.
5. Enter coordinates only when they are accurate. Incorrect coordinates place the property in the wrong position on the map.
6. Upload a clear primary image and supporting gallery images.
7. Use alternative text that briefly describes the image for accessibility.
8. Keep the listing as a draft until the information and images have been checked.
9. Publish only approved inventory.

### Edit a listing

1. Find the listing under **Listings**.
2. Select its edit action.
3. Change only the required fields.
4. Confirm price, availability, documentation, coordinates, images, and publication state.
5. Save the listing.
6. Use **View site** or the public listing link to inspect the result.

### Bulk listing actions

Where checkboxes are available:

1. Select the required listings.
2. Confirm the number shown as selected.
3. Choose the bulk action, such as publish, move to draft, feature, remove featured status, or update availability.
4. Apply the action and verify the affected records.

Do not use bulk actions until the selected count and intended action are correct.

### Delete a listing

Deletion is restricted to roles with deletion permission and requires confirmation. Prefer moving an unavailable property to draft or an appropriate availability state when the record may still be needed for reporting, enquiries, referrals, or audit history.

## 7. Leads and enquiries

Public property enquiries and inspection requests create or update customer and lead information. The system reduces duplicate active leads for the same contact and property.

### Work a lead

1. Open **Leads**.
2. Search or filter by stage, owner, source, follow-up status, or date.
3. Open the person's lead record.
4. Review the enquiry, property, contact details, source, partner attribution, inspections, and activity.
5. Set **Owner**.
6. Set a realistic **Follow-up** date.
7. Update **Stage**.
8. Record **Source** and optional **Campaign identifier** when appropriate. Do not replace a verified partner source.
9. Add **Estimated value (NGN)** when the opportunity becomes commercially meaningful.
10. Add a concise **Internal summary** and select **Save lead**.
11. Use **Add note** for dated conversation history.

### Lead stages

- **New** — received but not yet worked.
- **Contacted** — the team has made contact.
- **Qualified** — the person and requirement appear genuine and suitable.
- **Inspection scheduled** — a viewing appointment is arranged.
- **Inspection completed** — the viewing took place.
- **Negotiation** — commercial terms are being discussed.
- **Deposit paid** — the recorded deal reached the deposit milestone.
- **Closed won** — the transaction succeeded.
- **Closed lost** — the opportunity ended unsuccessfully.
- **Archived** — closed operationally without deleting history.

Stage changes can affect referral and commission workflows. Only record real business events.

### Email delivery controls

If email is configured, authorised staff can resend the admin notification or customer receipt from the lead record. A resend creates another email attempt; use it only after confirming the email address and delivery status.

## 8. Inspections

### Process an inspection request

1. Open **Inspections**.
2. Filter or review upcoming requests.
3. Open or locate the inspection.
4. Confirm the requested date and time with the customer.
5. Assign a staff member.
6. Update the status and internal note.
7. Save the update.
8. Update the linked lead stage when appropriate.

Inspection statuses are **Requested**, **Confirmed**, **Rescheduled**, **Completed**, **Cancelled**, and **No-show**.

Never mark an inspection **Completed** before it takes place. If the appointment changes, use **Rescheduled** and record the new date/time.

## 9. Operations and maintenance

Visitors or tenants submit maintenance requests through **Tenant Services**. Emergency wording on the form does not replace local emergency services.

### Process a ticket

1. Open **Operations**.
2. Search by resident, unit, property, issue, or vendor.
3. Filter by status, priority, owner, or sorting option.
4. Review the description and uploaded image, if present.
5. Assign an internal owner.
6. Enter the assigned vendor when applicable.
7. Update the internal note.
8. Move the status through **New**, **Assigned**, **In Progress**, and **Resolved**.
9. Save the ticket.

Treat **Emergency** and **High** priority items first. Do not mark a ticket **Resolved** until the outcome has been confirmed.

## 10. Finance records

The Finance module records operational charges; it is not a bank account or payment gateway.

### Create a charge

1. Open **Finance**.
2. Select the new-record action.
3. Enter the resident, unit, property, charge type, amount, due date, owner, and note.
4. Save the record.

Charge types include Rent, Service Charge, Utility, Diesel Contribution, Prepaid Meter Token, and Other.

### Update payment status

Use:

- **Due** — no payment recorded and the due date has not passed;
- **Part Paid** — only part of the amount has been received;
- **Paid** — the full payment has been independently confirmed;
- **Overdue** — an unpaid balance is past its due date.

Recording **Paid** does not move money. Keep the bank receipt or other evidence according to the company's finance process.

## 11. Documents

The document archive contains uploaded files and PDFs generated by Structurebase.

### Search the archive

1. Open **Documents**.
2. Search by title, resident, unit, property, filename, or note.
3. Filter by **Document type**, **Source**, or **Status**.
4. Sort the results and select **Apply**.

**Generated** files were created by the PDF generator. **Uploaded** files came from an external source. Generated files normally show **Final**; uploaded files show **Filed**.

### Upload a document

1. Select **Upload document**.
2. Enter the resident/client, unit reference, property, document type, title, and internal note.
3. Choose the file.
4. Save it and confirm it appears in the archive.

### Generate a PDF

1. Select **Generate PDF**.
2. Choose a template. The generator opens with a guided billing template by default.
3. Complete **File title**, **Client or record owner**, and **Reference**.
4. Add the property/project title and internal note where useful.
5. Complete the guided fields for the selected template.
6. Select **Preview PDF**.
7. Review the PDF in the new tab. Previewing does not save a document.
8. Return to the generator and correct any issue.
9. Select **Save final PDF** only after review, then confirm the action.

Available templates include billing/invoice documents, payment receipts, inspection reports, maintenance work orders, lease notices, tenancy agreements, sale agreements, management agreements, proposals, discovery questionnaires, delivery checklists, and letterhead documents.

Legal and transaction templates are drafting aids. Confirm current Nigerian law, parties, title facts, payment terms, notices, schedules, and execution requirements with a qualified property lawyer before formal use.

### Reuse a generated document

1. Find a generated document in **Documents**.
2. Select **Use as new**.
3. Confirm that the title begins with “Copy of”.
4. Update dates, references, parties, amounts, and all transaction-specific content.
5. Preview the PDF.
6. Save only after review.

This creates a new archive record and leaves the original unchanged.

### Edit archive details

Open **Edit archive details** to change the archive title, type, or note. These changes help organise the archive but do not alter the PDF itself.

### Delete a document

Open **Edit archive details**, then **More**, and use **Delete document**. Deletion removes the archive record and stored file and cannot be undone through the website. Download or back up anything that must be retained first.

## 12. Partners and referrals

### Review a partner application

1. Open **More** → **Partners**.
2. Filter by application status if required.
3. Open the partner record.
4. Review identity, contact, location, organisation, experience, and application notes.
5. Add an internal review note.
6. Choose an allowed status: **Pending review**, **Approved**, **Suspended**, or **Rejected**.
7. Save the decision.

Only approved partners can enter the portal. Suspending a partner stops portal access without deleting their history.

### Referral attribution

Approved partners receive property-specific links. The first valid partner touch for that property is retained for the configured attribution period, normally 30 days. Enquiries and inspection requests resolve the source on the server; staff and public users should not try to alter attribution manually.

Open **More** → **Referrals** to review visits, lead creation, inspection requests, conversions, and expired attribution records.

## 13. Commissions

The commission system calculates and records internal entitlement. It does not send money.

### Configure a rule

1. Open **More** → **Commissions**.
2. Select **Manage rules**.
3. Enter the rule name.
4. Choose **Percentage** or **Fixed amount**.
5. Choose the scope: Default, Property-specific, Campaign/special, or Partner override.
6. Set priority and optional validity dates.
7. Confirm **Active immediately** only when the rule is ready.
8. Select **Create rule**.

Higher priority wins. At equal priority, the more specific matching rule is preferred. Existing commissions keep their original rule snapshot when rules later change.

### Commission status

- **Potential** — an eligible attributed opportunity exists.
- **Pending** — the deal has reached the configured pending milestone.
- **Earned** — the deal reached the earned milestone.
- **Approved** — an authorised person approved payment.
- **Paid** — finance recorded independent payment evidence.
- **Rejected** or **Cancelled** — the commission will not proceed.

Adjustments require a reason. Approval and payment recording require separate permissions. Never use **Paid** until the actual transfer has been independently confirmed; the website does not make the transfer.

## 14. Team and permissions

Open **More** → **Team**.

### Invite staff

1. Select the invitation action.
2. Enter the person's full name and email.
3. Choose the least powerful role that covers their work.
4. Send or copy the invitation link through an approved channel.
5. Revoke unused invitations when they are no longer needed.

### Roles

- **Super admin** — all permissions, including staff control and data export.
- **Administrator** — broad operational access but cannot invite, edit, or disable staff.
- **Property manager** — listings, inspections, maintenance, documents, and analytics.
- **Sales manager** — leads, customers, inspections, partner/referral visibility, and analytics.
- **Marketing manager** — listings visibility, partners, referrals, content, and analytics.
- **Finance manager** — finance, documents visibility, commission controls, payout recording, and analytics.

Disable an account immediately when a staff member should no longer have access. Never recycle one person's account for another person.

## 15. Analytics, Audit, Settings, and export

### Analytics

Open **More** → **Analytics** to review business activity derived from stored listings, leads, inspections, partners, referrals, and commissions. Correct the source records when figures are inaccurate.

### Audit

Open **More** → **Audit** to search recorded administrative activity by text, record type, or actor type. Audit history helps identify who performed an action and when.

### Settings

Open **More** → **Settings** to manage approved site identity, contact information, coverage wording, footer content, homepage wording, and communication presentation available through the interface. Select **Preview communications** before relying on changed email presentation.

Server credentials, deployment variables, database configuration, storage credentials, domain records, and security secrets are not normal website settings. Ask the developer to change them.

### Export backup

The available **Export backup** action downloads structured application data for authorised users. Treat the file as confidential because it can contain customer and operational information. It does not replace provider-level database and media backups.

## 16. Public and partner journeys to test

Before publishing major changes, test:

1. Homepage → Listings → filters → property details.
2. Property details → enquiry submission.
3. Property details → inspection request.
4. Tenant Services → maintenance request and receipt.
5. Partner application → staff review → approved partner login.
6. Partner property link → private browser visit → enquiry → verified attribution.
7. Admin listing update → public listing result.
8. Document preview → final save → archive download.

## 17. Common mistakes to avoid

- Publishing a listing before price, availability, coordinates, and images are verified.
- Marking a lead, inspection, maintenance ticket, payment, or commission complete before the real event occurs.
- Replacing verified partner attribution manually.
- Saving a final PDF without first opening its preview.
- Assuming archive title edits change an existing PDF.
- Deleting records that should be retained for reporting or audit history.
- Sharing accounts or passwords.
- Uploading files containing unnecessary sensitive information.
- Entering live credentials into public forms, notes, or source-code files.
- Enabling search-engine indexing on a temporary testing address.

## 18. Troubleshooting

### I cannot sign in

- Check that you are using the staff login, not Partner sign in.
- Confirm the username and password carefully.
- Wait 15 minutes after repeated failed attempts.
- Ask the Super admin whether your account is active.
- Ask the developer for help if the application reports a server or database problem.

### A menu item is missing

Your role probably lacks permission. Ask the Super admin to review your role; do not use another account.

### An uploaded image or document is missing

- Confirm the upload completed successfully.
- Refresh the archive or listing.
- Check storage usage and provider status with the developer.
- Do not repeatedly upload duplicates while a storage incident is being investigated.

### The PDF preview does not open

- Allow pop-ups for the Structurebase website.
- Read the inline validation message and correct the identified fields.
- Keep the page open; your entries remain available after a failed preview.
- Contact the developer if the preview service remains unavailable.

### An email did not arrive

- Confirm the recipient address.
- Check spam/junk folders.
- Use the resend action once where available.
- Ask the developer to inspect SMTP configuration and delivery logs.

### The map is blank or inaccurate

- Confirm internet access.
- Verify the listing's coordinates.
- Ask the developer to check the Mapbox token, usage, and commercial licence.

### The site is slow to open

A free testing service may sleep after inactivity and take about a minute to wake. Production should use an always-on service. Report continuing slowness to the developer.

## 19. Contact the developer for

- domain, DNS, SSL, hosting, or deployment changes;
- environment variables, secrets, credentials, or API keys;
- database migration, restoration, or provider-level backups;
- storage, email, or Mapbox configuration;
- new roles, permission changes beyond the existing role choices, or security incidents;
- data repair or deletion that cannot safely be performed in the interface;
- unexpected errors, missing files, failed deployments, or performance incidents;
- structural changes to PDF templates or legal document wording;
- new integrations, automation, reports, or website features.

## 20. Operating checklist

### Daily

- Review **Overview** action items.
- Assign new leads and set follow-up dates.
- Confirm upcoming inspections.
- Triage emergency and high-priority maintenance.
- Review overdue or newly paid finance records.
- Check pending partner or commission actions relevant to your role.
- Confirm important public listings remain accurate and available.

### Weekly

- Review stale leads and overdue follow-ups.
- Confirm published inventory, pricing, availability, and primary images.
- Review unassigned inspections and maintenance tickets.
- Review overdue balances and payment evidence.
- Review unlinked or poorly named documents.
- Review partner/referral performance and commission exceptions.
- Review Analytics and Audit for unusual activity.
- Confirm a recent application-data export and provider backups exist.
- Revoke unused invitations and disable access that is no longer required.

---

Document status: client-handoff draft. Replace placeholder business contact details and the final website address before issuing the production copy.
