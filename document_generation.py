from __future__ import annotations

import base64
import copy
import json
import re
from datetime import date
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image as PillowImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

DOCUMENT_TEMPLATE_VERSION = "2026.04.3"
HEX_COLOR_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")
STATIC_DIR = Path(__file__).resolve().parent / "static"
PDF_LOGO_CANDIDATES = (
    STATIC_DIR / "images" / "LOGO2.svg",
    STATIC_DIR / "images" / "structurebase_exact_fullcanvas.svg",
    STATIC_DIR / "images" / "LOGO1.webp",
    STATIC_DIR / "images" / "logo-mark.webp",
)
EMBEDDED_IMAGE_RE = re.compile(r'href="data:image/(?P<format>[A-Za-z0-9.+-]+);base64,(?P<data>[A-Za-z0-9+/=]+)"')


def _pdf_logo_path() -> Path | None:
    for candidate in PDF_LOGO_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def _pdf_logo_image() -> tuple[ImageReader | None, float]:
    logo_path = _pdf_logo_path()
    if logo_path is None:
        return None, 1.0

    if logo_path.suffix.lower() == ".svg":
        match = EMBEDDED_IMAGE_RE.search(logo_path.read_text(encoding="utf-8"))
        if not match:
            return None, 1.0
        image_stream = BytesIO(base64.b64decode(match.group("data")))
        image = PillowImage.open(image_stream)
    else:
        image = PillowImage.open(logo_path)

    with image:
        image = image.convert("RGBA")
        alpha = image.getchannel("A")
        bbox = alpha.getbbox() or image.getbbox()
        if bbox:
            image = image.crop(bbox)

        output = BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        width, height = image.size
        aspect = (width / height) if height else 1.0
        return ImageReader(output), aspect


def _catalog(site_settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    site_name = str(site_settings.get("site_name") or "Structurebase")
    contact_email = str(site_settings.get("contact_email") or "hello@example.com")
    contact_phone = str(site_settings.get("contact_phone_display") or "")
    office_address = str(site_settings.get("office_address") or "Lagos, Nigeria")
    billing_contact = " or ".join(part for part in [contact_email, contact_phone] if part)

    return {
        "letterhead": {
            "label": "Branded Letterhead",
            "document_type": "Letterhead",
            "description": "Formal correspondence with recipient addressing, structured sections, signature blocks, and legal footer support.",
            "template_structure": [
                "Document meta strip",
                "Recipient block",
                "Subject line",
                "Body sections",
                "Callout list",
                "Closing and signatures",
                "Legal footer",
            ],
            "reusable_components": [
                "Meta strip",
                "Section heading",
                "Paragraph block",
                "Bullet callout list",
                "Signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "recipient.name is required",
                "subject is required",
                "body_sections must contain at least one section",
                "issue_date must be YYYY-MM-DD",
            ],
            "acceptance_criteria": [
                "Title and subject fit within first page without collision",
                "All sections respect page margins",
                "Footer and page number render on every page",
            ],
            "sample_payload": {
                "document_number": "LTR-2026-041",
                "issue_date": "2026-04-21",
                "recipient": {
                    "name": "The Facilities Manager",
                    "company": "Marina Crest Residences",
                    "address_lines": ["2B Admiralty Way", "Lekki Phase 1, Lagos"],
                },
                "subject": "Notice of coordinated maintenance review",
                "intro": f"{site_name} is issuing this coordination note to confirm the next on-site review window.",
                "body_sections": [
                    {
                        "heading": "Scope",
                        "body": "The operations desk will review power backup, plumbing access points, and shared-area lighting before the next tenant inspection cycle.",
                    },
                    {
                        "heading": "Required support",
                        "body": "Please make unit access timing, recent vendor notes, and any open snag list available to the review team before arrival.",
                    },
                ],
                "callouts": [
                    "Arrival window: 09:30 to 11:30",
                    "Primary contact must remain reachable on the day",
                    "Escalations should be routed to the operations desk",
                ],
                "closing": "Please acknowledge receipt and confirm the access window so the schedule can be locked in.",
                "signatories": [
                    {"name": "Operations Lead", "role": "Structurebase"},
                ],
                "legal_footer": {
                    "text": f"{site_name} correspondence is confidential and intended only for the named recipient. Contact {contact_email} for verification."
                },
            },
            "field_schema": [
                {"path": "document_number", "type": "string", "required": False, "description": "Internal reference printed in the meta strip."},
                {"path": "issue_date", "type": "date", "required": True, "description": "Issue date shown in ISO format."},
                {"path": "recipient", "type": "object", "required": True, "description": "Recipient name, company, and address lines."},
                {"path": "body_sections[]", "type": "array<object>", "required": True, "description": "Ordered letter sections with heading and body."},
                {"path": "signatories[]", "type": "array<object>", "required": False, "description": "Name and role for signature lines."},
            ],
        },
        "billing": {
            "label": "Billing Document",
            "document_type": "Invoice",
            "description": "Print-safe billing layout with line items, totals, payment instructions, and terms handling.",
            "template_structure": [
                "Invoice header",
                "Bill-to and issuer summary",
                "Line items table",
                "Totals band",
                "Payment instructions",
                "Terms and legal footer",
            ],
            "reusable_components": [
                "Two-column summary table",
                "Overflow-safe line items table",
                "Totals stack",
                "Payment list",
                "Signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "bill_to.name is required",
                "currency must be 3 letters",
                "line_items must contain at least one item",
                "each line item quantity must be greater than zero",
                "due_date must be YYYY-MM-DD",
            ],
            "acceptance_criteria": [
                "Line item header repeats across page breaks",
                "Totals remain right-aligned and legible",
                "Generated PDF opens with valid PDF header and application/pdf mime type",
            ],
            "sample_payload": {
                "document_number": "INV-2026-019",
                "issue_date": "2026-04-21",
                "due_date": "2026-04-28",
                "currency": "NGN",
                "bill_to": {
                    "name": "Mr. Daniel Adeyemi",
                    "company": "Apartment 12B, Harbour Gate",
                    "address_lines": ["Oniru Estate, Victoria Island Extension", "Lagos"],
                },
                "line_items": [
                    {"description": "Service charge - Q2 2026", "quantity": 1, "unit_price": 1850000},
                    {"description": "Diesel contribution - April 2026", "quantity": 1, "unit_price": 325000},
                    {"description": "Water treatment reserve", "quantity": 1, "unit_price": 95000},
                ],
                "payment_instructions": [
                    "Bank: Example Commercial Bank",
                    "Account name: Structurebase Client Account",
                    "Reference: use the invoice number on transfer narration",
                ],
                "notes": [
                    "Please send transfer proof to the finance desk once completed.",
                    "Late payment may affect estate service scheduling.",
                ],
                "terms": "Amounts remain due in full on or before the stated due date unless a written payment arrangement is confirmed.",
                "signatories": [{"name": "Finance Desk", "role": site_name}],
                "legal_footer": {
                    "text": f"For billing questions contact {billing_contact}."
                },
            },
            "field_schema": [
                {"path": "bill_to", "type": "object", "required": True, "description": "Customer or resident being billed."},
                {"path": "line_items[]", "type": "array<object>", "required": True, "description": "Description, quantity, unit_price, optional amount override."},
                {"path": "payment_instructions[]", "type": "array<string>", "required": False, "description": "Rendered as a payment block."},
                {"path": "terms", "type": "string", "required": False, "description": "Optional terms paragraph, moved with page control when present."},
            ],
        },
        "proposal": {
            "label": "Proposal Template",
            "document_type": "Proposal",
            "description": "Client-ready proposal with executive summary, service blocks, commercials, timeline, and approvals.",
            "template_structure": [
                "Client and proposal summary",
                "Executive summary",
                "Service blocks",
                "Timeline",
                "Commercials",
                "Terms and signatures",
            ],
            "reusable_components": [
                "Overview strip",
                "Service card group",
                "Timeline table",
                "Commercials table",
                "Signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "client.name is required",
                "project_title is required",
                "executive_summary is required",
                "service_blocks must contain at least one block",
            ],
            "acceptance_criteria": [
                "Service blocks never split mid-header",
                "Timeline rows wrap without clipping",
                "Commercial totals remain visually separated from narrative text",
            ],
            "sample_payload": {
                "document_number": "PRO-2026-011",
                "issue_date": "2026-04-21",
                "valid_until": "2026-05-05",
                "client": {
                    "name": "Bluecrest Developments",
                    "company": "Bluecrest Developments Ltd",
                    "address_lines": ["Banana Island, Lagos"],
                },
                "project_title": "Premium sales and leasing support for Ikoyi release",
                "executive_summary": f"{site_name} will support launch positioning, enquiry handling, and guided viewings for the next tranche of inventory release.",
                "service_blocks": [
                    {
                        "title": "Listing and launch setup",
                        "items": [
                            "Refine titles, summaries, and public listing structure",
                            "Prepare sales-ready gallery and brochure outputs",
                            "Configure the Lagos map and verification badges",
                        ],
                        "fee_label": "NGN 1,500,000 setup",
                    },
                    {
                        "title": "Lead handling and reporting",
                        "items": [
                            "Qualify inbound enquiries",
                            "Coordinate viewings with the client team",
                            "Provide weekly pipeline and conversion snapshots",
                        ],
                        "fee_label": "NGN 750,000 monthly retainer",
                    },
                ],
                "timeline": [
                    {"phase": "Week 1", "details": "Inventory review, positioning, and collateral setup"},
                    {"phase": "Week 2", "details": "Publish listings and begin outbound lead activation"},
                    {"phase": "Week 3 onward", "details": "Run viewings, reporting, and conversion follow-up"},
                ],
                "commercials": [
                    {"label": "Setup fee", "value": "NGN 1,500,000"},
                    {"label": "Monthly retainer", "value": "NGN 750,000"},
                    {"label": "Success fee", "value": "As agreed in agency schedule"},
                ],
                "terms": [
                    "Commercial terms exclude paid media and third-party creative production.",
                    "Proposal validity is limited to the date shown above.",
                ],
                "signatories": [
                    {"name": "Commercial Lead", "role": site_name},
                    {"name": "Client Approval", "role": "Authorised Signatory"},
                ],
                "legal_footer": {
                    "text": f"This proposal is provided by {site_name} for evaluation only and may not be circulated outside the client decision team without consent."
                },
            },
            "field_schema": [
                {"path": "project_title", "type": "string", "required": True, "description": "Main proposal title."},
                {"path": "service_blocks[]", "type": "array<object>", "required": True, "description": "Title, item list, and fee label per scope block."},
                {"path": "timeline[]", "type": "array<object>", "required": False, "description": "Phase and details entries."},
                {"path": "commercials[]", "type": "array<object>", "required": False, "description": "Commercial line items rendered as a compact table."},
            ],
        },
        "discovery": {
            "label": "Discovery Questionnaire",
            "document_type": "Discovery Questionnaire",
            "description": "Structured questionnaire with grouped prompts, response space, and clear submission guidance.",
            "template_structure": [
                "Questionnaire summary",
                "Response instructions",
                "Sectioned question tables",
                "Contact owner block",
                "Acknowledgement/signature",
            ],
            "reusable_components": [
                "Intro paragraph",
                "Instruction bullets",
                "Question table",
                "Contact block",
                "Footer renderer",
            ],
            "validation_rules": [
                "client.name is required",
                "sections must contain at least one section",
                "each section must contain at least one question",
            ],
            "acceptance_criteria": [
                "Question table rows break cleanly across pages",
                "Blank response areas remain visible in print",
                "Section headings remain attached to the first question row",
            ],
            "sample_payload": {
                "document_number": "DISC-2026-006",
                "issue_date": "2026-04-21",
                "client": {
                    "name": "West Quay Property Holdings",
                    "company": "West Quay Property Holdings",
                    "address_lines": ["Lekki, Lagos"],
                },
                "intro": "Use this questionnaire to align listing, approvals, and operating constraints before launch.",
                "response_instructions": [
                    "Answer each section as completely as possible.",
                    "Where a question is not applicable, mark it clearly.",
                    "Attach supporting references separately if needed.",
                ],
                "sections": [
                    {
                        "title": "Commercial goals",
                        "questions": [
                            "What are the primary sales or leasing objectives for this release?",
                            "Which districts or competitor schemes should influence pricing position?",
                            "What internal approval chain must be completed before public publication?",
                        ],
                    },
                    {
                        "title": "Operations and delivery",
                        "questions": [
                            "Who will own viewing coordination and client response timing?",
                            "Which documents should be available before qualified prospects are invited to viewing?",
                            "What reporting cadence is expected after launch?",
                        ],
                    },
                ],
                "contact_owner": {
                    "name": "Projects Desk",
                    "role": site_name,
                    "email": contact_email,
                },
                "signature_prompt": "Prepared by / reviewed by",
                "legal_footer": {
                    "text": f"Responses to this questionnaire will be used only for project planning and delivery by {site_name}."
                },
            },
            "field_schema": [
                {"path": "sections[]", "type": "array<object>", "required": True, "description": "Each section contains a title and an ordered question list."},
                {"path": "response_instructions[]", "type": "array<string>", "required": False, "description": "Printed above the questionnaire sections."},
                {"path": "contact_owner", "type": "object", "required": False, "description": "Owner block rendered near the close of the document."},
            ],
        },
        "delivery_checklist": {
            "label": "Delivery Checklist",
            "document_type": "Delivery Checklist",
            "description": "Operational handover checklist with status tracking, owners, notes, approvals, and sign-off space.",
            "template_structure": [
                "Delivery summary",
                "Checklist sections",
                "Handover notes",
                "Approval/sign-off blocks",
                "Legal footer",
            ],
            "reusable_components": [
                "Summary strip",
                "Checklist status table",
                "Handover note list",
                "Approval signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "project_title is required",
                "checklist_sections must contain at least one section",
                "each checklist section must contain at least one item",
            ],
            "acceptance_criteria": [
                "Checklist tables repeat headers after page breaks",
                "Status cells remain readable in grayscale print",
                "Approval area remains on the final page with enough signature space",
            ],
            "sample_payload": {
                "document_number": "CHK-2026-022",
                "issue_date": "2026-04-21",
                "project_title": "Ikoyi penthouse launch readiness",
                "delivery_owner": {
                    "name": "Portfolio Operations",
                    "role": site_name,
                    "email": contact_email,
                },
                "checklist_sections": [
                    {
                        "title": "Listing readiness",
                        "items": [
                            {"label": "Copy approved", "status": "Done", "owner": "Marketing", "note": "Final review completed"},
                            {"label": "Gallery compressed and uploaded", "status": "Done", "owner": "Media", "note": ""},
                            {"label": "Map coordinates verified", "status": "Pending", "owner": "Listings", "note": "Awaiting final pin"},
                        ],
                    },
                    {
                        "title": "Commercial readiness",
                        "items": [
                            {"label": "Pricing sign-off received", "status": "Done", "owner": "Commercial", "note": ""},
                            {"label": "Proposal pack approved", "status": "In Review", "owner": "Client", "note": "Final comments due Thursday"},
                        ],
                    },
                ],
                "handover_notes": [
                    "Any pending item must have an accountable owner before publication.",
                    "Operations should confirm the prospect response SLA before launch.",
                ],
                "approvals": [
                    {"label": "Operations sign-off", "name": "Operations Lead", "role": site_name},
                    {"label": "Client sign-off", "name": "Project Sponsor", "role": "Authorised Signatory"},
                ],
                "legal_footer": {
                    "text": f"This checklist is an internal delivery control document for {site_name} and authorised client representatives."
                },
            },
            "field_schema": [
                {"path": "checklist_sections[]", "type": "array<object>", "required": True, "description": "Title with status rows containing label, status, owner, and note."},
                {"path": "handover_notes[]", "type": "array<string>", "required": False, "description": "Rendered below the checklist tables."},
                {"path": "approvals[]", "type": "array<object>", "required": False, "description": "Rendered as final sign-off blocks."},
            ],
        },
        "payment_receipt": {
            "label": "Official Payment Receipt",
            "document_type": "Receipt",
            "description": "Formal receipt for rent, service charge, utility, or project payments with received items, method, and confirmation notes.",
            "template_structure": [
                "Receipt summary",
                "Payer and issuer block",
                "Received items table",
                "Payment details",
                "Confirmation notes",
                "Signature and legal footer",
            ],
            "reusable_components": [
                "Meta strip",
                "Two-column summary table",
                "Overflow-safe received items table",
                "Payment details block",
                "Signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "payer.name is required",
                "currency must be 3 letters",
                "receipt_items must contain at least one item",
                "payment_date must be YYYY-MM-DD",
            ],
            "acceptance_criteria": [
                "Receipt total remains visible and right-aligned",
                "Payment method and reference are visible on the first page",
                "Signature and legal footer remain intact in print output",
            ],
            "sample_payload": {
                "document_number": "RCT-2026-033",
                "issue_date": "2026-04-22",
                "payment_date": "2026-04-22",
                "currency": "NGN",
                "payer": {
                    "name": "Mrs. Tolani Ojo",
                    "company": "Flat 8C, Harbour Gate",
                    "address_lines": ["Oniru Estate, Victoria Island Extension", "Lagos"],
                },
                "receipt_items": [
                    {"label": "Service charge payment", "amount": 1850000},
                    {"label": "Diesel contribution", "amount": 325000},
                ],
                "payment_method": "Bank transfer",
                "payment_reference": "TRF-220426-1182",
                "received_by": "Finance Desk",
                "notes": [
                    "This receipt confirms cleared funds against the listed charges only.",
                    "Keep this receipt with the tenancy or estate records for future reconciliation.",
                ],
                "signatories": [{"name": "Finance Desk", "role": site_name}],
                "legal_footer": {
                    "text": f"For receipt validation contact {contact_email} or {contact_phone}."
                },
            },
            "field_schema": [
                {"path": "payer", "type": "object", "required": True, "description": "Name, company, and address lines for the paying party."},
                {"path": "receipt_items[]", "type": "array<object>", "required": True, "description": "Label and amount rows included in the receipt total."},
                {"path": "payment_method", "type": "string", "required": True, "description": "Transfer, cash, cheque, POS, or other cleared route."},
                {"path": "payment_reference", "type": "string", "required": False, "description": "Bank or internal reference used to reconcile the payment."},
            ],
        },
        "inspection_report": {
            "label": "Property Inspection Report",
            "document_type": "Inspection Report",
            "description": "Structured inspection report for viewings, move-in, routine checks, or move-out reviews with condition rows and recommendations.",
            "template_structure": [
                "Inspection summary",
                "Property and inspection parties",
                "Sectioned observation tables",
                "Recommendations and risk notes",
                "Sign-off block",
                "Legal footer",
            ],
            "reusable_components": [
                "Meta strip",
                "Inspection summary block",
                "Observation table",
                "Recommendation list",
                "Signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "inspection_type is required",
                "property_title is required",
                "inspection_date must be YYYY-MM-DD",
                "sections must contain at least one section",
            ],
            "acceptance_criteria": [
                "Observation headers repeat after page breaks",
                "Condition rows remain legible in grayscale print",
                "Recommendations are clearly separated from raw observations",
            ],
            "sample_payload": {
                "document_number": "INSP-2026-012",
                "issue_date": "2026-04-22",
                "inspection_date": "2026-04-22",
                "inspection_type": "Routine condition review",
                "property_title": "Lekki Phase 1 Detached Villa",
                "property_address": "Adebayo Doherty Road, Lekki Phase 1, Lagos",
                "inspected_by": {"name": "Operations Supervisor", "role": site_name},
                "inspected_for": {"name": "Property Owner", "company": "Private Client"},
                "summary": "The property remains market-ready with minor corrective work required in the guest bathroom and power-backup enclosure.",
                "sections": [
                    {
                        "title": "Interior spaces",
                        "observations": [
                            {"area": "Living room", "condition": "Good", "status": "Serviceable", "note": "Paint finish and lighting points remain in order."},
                            {"area": "Guest bathroom", "condition": "Fair", "status": "Attention required", "note": "Mixer tap looseness observed at sink."},
                        ],
                    },
                    {
                        "title": "External and plant",
                        "observations": [
                            {"area": "Generator enclosure", "condition": "Fair", "status": "Attention required", "note": "Ventilation louvre requires cleaning and panel fasteners need review."},
                        ],
                    },
                ],
                "recommendations": [
                    "Tighten and re-test the guest bathroom mixer assembly before the next viewing cycle.",
                    "Complete generator enclosure cleaning and confirm ventilation airflow.",
                ],
                "signatories": [
                    {"label": "Inspected by", "name": "Operations Supervisor", "role": site_name},
                    {"label": "Acknowledged by", "name": "Property Owner", "role": "Client"},
                ],
                "legal_footer": {
                    "text": f"This inspection report is prepared for operational and commercial coordination by {site_name}."
                },
            },
            "field_schema": [
                {"path": "inspection_type", "type": "string", "required": True, "description": "Viewing, move-in, routine, move-out, or another inspection mode."},
                {"path": "sections[]", "type": "array<object>", "required": True, "description": "Each section contains observations with area, condition, status, and note."},
                {"path": "recommendations[]", "type": "array<string>", "required": False, "description": "Prioritised follow-up actions below the observations."},
            ],
        },
        "maintenance_work_order": {
            "label": "Maintenance Work Order",
            "document_type": "Work Order",
            "description": "Vendor-ready work order with issue summary, scope, site access notes, completion expectations, and sign-off fields.",
            "template_structure": [
                "Work order summary",
                "Vendor and site block",
                "Scope table",
                "Access and site notes",
                "Completion requirements",
                "Approvals and legal footer",
            ],
            "reusable_components": [
                "Meta strip",
                "Scope table",
                "Bullet list",
                "Instruction callout",
                "Signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "vendor.name is required",
                "property_title is required",
                "scope_items must contain at least one item",
                "issue_date must be YYYY-MM-DD",
            ],
            "acceptance_criteria": [
                "Scope items remain grouped and readable across page breaks",
                "Access notes and safety instructions remain visible before the sign-off area",
                "Vendor and internal sign-off lines are available on the final page",
            ],
            "sample_payload": {
                "document_number": "WO-2026-018",
                "issue_date": "2026-04-22",
                "request_reference": "TS-59613405D846",
                "property_title": "Harbour Gate Apartments",
                "unit_reference": "Flat B2",
                "vendor": {
                    "name": "Prime Mechanical Services",
                    "company": "Prime Mechanical Services Ltd",
                    "phone": "+234 800 555 0100",
                },
                "issued_by": {"name": "Operations Desk", "role": site_name, "email": contact_email},
                "issue_summary": "Attend to reported cooling failure and water leakage from the condensate line in Flat B2.",
                "scope_items": [
                    {"task": "Inspect indoor and outdoor AC components", "priority": "High", "materials": "Testing kit and replacement consumables", "note": "Confirm refrigerant balance before recommissioning."},
                    {"task": "Flush and secure condensate line", "priority": "High", "materials": "Line-cleaning kit and clamps", "note": "Test for leakage before handover."},
                ],
                "site_notes": [
                    "Contact the resident before arrival and confirm access timing.",
                    "Work area must be left clean and safe after completion.",
                ],
                "completion_requirements": [
                    "Photograph completed work before departure.",
                    "Report replaced parts and final condition back to the operations desk.",
                ],
                "signatories": [
                    {"label": "Issued by", "name": "Operations Desk", "role": site_name},
                    {"label": "Vendor acknowledgement", "name": "Prime Mechanical Services", "role": "Assigned vendor"},
                ],
                "legal_footer": {
                    "text": f"This work order is issued for the named task only. Confirm completion to {contact_email}."
                },
            },
            "field_schema": [
                {"path": "vendor", "type": "object", "required": True, "description": "Assigned vendor or contractor receiving the work order."},
                {"path": "scope_items[]", "type": "array<object>", "required": True, "description": "Task rows with priority, materials, and execution notes."},
                {"path": "completion_requirements[]", "type": "array<string>", "required": False, "description": "Close-out actions expected before the order can be marked complete."},
            ],
        },
        "lease_notice": {
            "label": "Lease Renewal / Rent Review Notice",
            "document_type": "Lease Renewal Notice",
            "description": "Formal tenant notice covering renewal terms, rent review, response timing, and next-step instructions.",
            "template_structure": [
                "Notice summary",
                "Tenant and premises block",
                "Current and proposed terms",
                "Reason and supporting notes",
                "Response instructions",
                "Sign-off block",
                "Legal footer",
            ],
            "reusable_components": [
                "Meta strip",
                "Notice summary table",
                "Term bullets",
                "Instruction list",
                "Signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "tenant.name is required",
                "property_title is required",
                "current_term_end must be YYYY-MM-DD",
                "response_deadline must be YYYY-MM-DD",
            ],
            "acceptance_criteria": [
                "Current and proposed terms remain easy to compare on the first page",
                "Response deadline is visually distinct",
                "The notice prints as a complete formal communication without clipped dates or amounts",
            ],
            "sample_payload": {
                "document_number": "LRN-2026-007",
                "issue_date": "2026-04-22",
                "tenant": {
                    "name": "Mr. Femi Odukoya",
                    "company": "Apartment 14A, Harbour Gate",
                    "address_lines": ["Victoria Island Extension, Lagos"],
                },
                "property_title": "Harbour Gate Apartments",
                "unit_reference": "Flat 14A",
                "notice_type": "Lease renewal and rent review notice",
                "current_term_end": "2026-06-30",
                "proposed_start": "2026-07-01",
                "current_rent": "NGN 16,500,000 per annum",
                "proposed_rent": "NGN 18,000,000 per annum",
                "notice_reason": "This notice reflects the next lease cycle, updated estate operating costs, and the current market position of comparable stock in the same district.",
                "service_charge_note": "Service charge remains separately payable in line with the estate budget.",
                "response_deadline": "2026-05-15",
                "key_terms": [
                    "Renewal term: 12 months",
                    "Rent to be paid before the commencement date",
                    "Access and service rules remain in force under the current estate handbook",
                ],
                "response_options": [
                    "Accept the proposed renewal in writing before the response deadline.",
                    "Request a clarification meeting if any commercial or operational term needs discussion.",
                ],
                "next_steps": [
                    "Confirm acceptance in writing before the response deadline.",
                    "Contact the team if a clarification meeting is required before execution.",
                ],
                "special_conditions": [
                    "Move-in inventory and meter readings from the current tenancy remain subject to reconciliation where required.",
                    "All estate access procedures and approved-user records must remain current before the renewed term starts.",
                ],
                "signatories": [{"name": "Leasing Desk", "role": site_name}],
                "legal_footer": {
                    "text": f"This notice is issued by {site_name} for tenancy administration and record purposes."
                },
            },
            "field_schema": [
                {"path": "tenant", "type": "object", "required": True, "description": "Tenant name and correspondence address."},
                {"path": "current_rent", "type": "string", "required": False, "description": "Existing rent used for comparison in the notice."},
                {"path": "proposed_rent", "type": "string", "required": True, "description": "Renewal rent or reviewed amount shown prominently in the notice."},
                {"path": "key_terms[]", "type": "array<string>", "required": False, "description": "Term highlights included below the notice summary."},
                {"path": "response_options[]", "type": "array<string>", "required": False, "description": "Clear response routes for the tenant before the deadline."},
            ],
        },
        "management_agreement": {
            "label": "Property Management Agreement",
            "document_type": "Property Management Agreement",
            "description": "Structured management agreement with parties, property scope, service obligations, fee schedule, reporting expectations, and signature blocks.",
            "template_structure": [
                "Agreement summary",
                "Parties and managed property",
                "Scope of services",
                "Fee schedule",
                "Authority and reporting",
                "Service standards and obligations",
                "Termination and special conditions",
                "Signatures and legal footer",
            ],
            "reusable_components": [
                "Meta strip",
                "Party summary block",
                "Scope sections",
                "Fee schedule table",
                "Obligation bullet lists",
                "Signature block",
            ],
            "validation_rules": [
                "owner.name is required",
                "manager.name is required",
                "property_title is required",
                "scope_sections must contain at least one section",
            ],
            "acceptance_criteria": [
                "Scope and fee schedule sections remain distinct and easy to scan",
                "Owner and manager obligations are not mixed together visually",
                "Final signature page retains complete sign-off blocks",
            ],
            "sample_payload": {
                "document_number": "PMA-2026-004",
                "issue_date": "2026-04-22",
                "effective_date": "2026-05-01",
                "owner": {
                    "name": "Cedar Crest Trustees",
                    "company": "Cedar Crest Trustees",
                    "address_lines": ["Banana Island, Lagos"],
                },
                "manager": {
                    "name": site_name,
                    "company": site_name,
                    "address_lines": [office_address, contact_email],
                },
                "property_title": "Cedar Crest Residences",
                "property_address": "Banana Island, Ikoyi, Lagos",
                "term_summary": "Initial management term of 12 months, renewable subject to written review.",
                "scope_sections": [
                    {
                        "title": "Core management scope",
                        "items": [
                            "Coordinate tenant and occupier communication",
                            "Supervise routine maintenance and vendor attendance",
                            "Maintain rent, service charge, and issue registers",
                        ],
                    },
                    {
                        "title": "Reporting",
                        "items": [
                            "Provide monthly operating summary",
                            "Escalate material incidents and urgent approvals promptly",
                        ],
                    },
                ],
                "fee_schedule": [
                    {"label": "Monthly management retainer", "value": "NGN 1,500,000"},
                    {"label": "Emergency coordination surcharge", "value": "At cost plus agreed handling fee"},
                ],
                "reporting_cadence": "A written monthly operations report and an exception-based escalation summary for material incidents.",
                "authority_limits": [
                    "Routine operating expenditure may be approved only within the agreed working budget.",
                    "Non-routine works, capital repairs, and new vendor appointments require owner approval unless there is an immediate safety or asset-protection risk.",
                    "Any tenant concession, waiver, or settlement must be approved by the owner in writing.",
                ],
                "service_standards": [
                    "Routine service requests to be acknowledged within one working day.",
                    "Emergency issues to be escalated immediately through the operations desk.",
                    "Vendor attendance windows and close-out notes must be tracked for each assigned task.",
                ],
                "owner_obligations": [
                    "Provide access, approvals, and operating budgets in a timely manner.",
                    "Approve non-routine expenditure before commitment unless otherwise agreed.",
                    "Keep title, compliance, and occupier authority records current for the managed property.",
                ],
                "manager_obligations": [
                    "Act with reasonable care and maintain accurate operating records.",
                    "Escalate material building, tenant, or safety issues without delay.",
                    "Keep rent, service charge, maintenance, and vendor records available for review.",
                ],
                "termination_events": [
                    "Material breach that remains unremedied after written notice.",
                    "Persistent failure to fund agreed operating requirements after escalation.",
                    "Mutual written agreement to end the engagement at the end of a reporting cycle.",
                ],
                "special_conditions": [
                    "This template should be aligned with the final commercial scope, fee authority, and compliance obligations before execution.",
                    "Any client-specific house rules, approval matrices, or service windows should be attached as a schedule where applicable.",
                ],
                "signatories": [
                    {"label": "For the owner", "name": "Authorised Trustee", "role": "Owner"},
                    {"label": "For the manager", "name": "Operations Director", "role": site_name},
                ],
                "legal_footer": {
                    "text": f"This management agreement template should be reviewed against the commercial brief and legal advice before execution."
                },
            },
            "field_schema": [
                {"path": "owner", "type": "object", "required": True, "description": "Property owner or instructing principal."},
                {"path": "manager", "type": "object", "required": True, "description": "Managing firm or operating desk taking responsibility."},
                {"path": "scope_sections[]", "type": "array<object>", "required": True, "description": "Grouped scope items defining the managed services."},
                {"path": "fee_schedule[]", "type": "array<object>", "required": False, "description": "Commercial line items for the agreement."},
                {"path": "authority_limits[]", "type": "array<string>", "required": False, "description": "Approval and authority boundaries for the manager."},
                {"path": "termination_events[]", "type": "array<string>", "required": False, "description": "Termination triggers and exit conditions."},
            ],
        },
        "tenancy_agreement": {
            "label": "Tenancy / Lease Agreement",
            "document_type": "Tenancy Agreement",
            "description": "Tenant-ready agreement layout covering parties, premises, commercial terms, use conditions, maintenance, access, default, and special conditions.",
            "template_structure": [
                "Agreement summary",
                "Parties and premises",
                "Commercial terms",
                "Use, services, and maintenance",
                "Access, default, and termination",
                "Special conditions",
                "Signatures and legal footer",
            ],
            "reusable_components": [
                "Meta strip",
                "Party summary block",
                "Commercial terms table",
                "Bullet lists",
                "Signature block",
                "Footer renderer",
            ],
            "validation_rules": [
                "landlord.name is required",
                "tenant.name is required",
                "commencement_date must be YYYY-MM-DD",
                "expiry_date must be YYYY-MM-DD",
                "rent_amount is required",
            ],
            "acceptance_criteria": [
                "Parties, premises, and commercial terms are all visible before the detailed conditions begin",
                "House rules remain distinct from negotiated special conditions",
                "Signature areas stay complete on the final page",
            ],
            "sample_payload": {
                "document_number": "TEN-2026-015",
                "issue_date": "2026-04-22",
                "commencement_date": "2026-05-01",
                "expiry_date": "2027-04-30",
                "tenancy_type": "Fixed-term residential tenancy",
                "landlord": {
                    "name": "Marina Crest Holdings",
                    "company": "Marina Crest Holdings",
                    "address_lines": ["Ikoyi, Lagos"],
                },
                "tenant": {
                    "name": "Mrs. Kehinde Ajayi",
                    "company": "",
                    "address_lines": ["Proposed tenant correspondence address to be inserted on execution"],
                },
                "property_title": "Marina Crest Residences",
                "premises_address": "Apartment 7C, Marina Crest Residences, Ikoyi, Lagos",
                "permitted_use": "Private residential occupation only, subject to estate access and conduct rules.",
                "rent_amount": "NGN 24,000,000 per annum",
                "deposit_amount": "NGN 2,000,000 security deposit",
                "payment_schedule": "One year in advance on or before the commencement date.",
                "included_services": [
                    "Estate security and shared-area cleaning",
                    "Waste management and common-area lighting",
                ],
                "utilities_and_outgoings": [
                    "Electricity, diesel contribution, water, data, and unit-specific utility consumption remain payable by the tenant unless otherwise agreed.",
                    "Any meter recharge or usage reconciliation must be completed before vacating the premises.",
                ],
                "landlord_covenants": [
                    "Maintain the tenant's quiet enjoyment of the premises, subject to lawful estate and safety access needs.",
                    "Keep common-area services and landlord-controlled structural elements under routine review.",
                ],
                "tenant_covenants": [
                    "Pay rent and approved charges on or before the due date.",
                    "Keep the premises reasonably clean and avoid nuisance or unauthorised alteration.",
                    "Promptly report defects, leaks, or safety risks that may affect the premises.",
                ],
                "inspection_access": [
                    "The landlord or manager may enter on reasonable notice for inspection, repair, valuation, or viewing, except where urgent safety action is required.",
                    "Move-out inspection, inventory reconciliation, and key return will be completed before final handover.",
                ],
                "default_events": [
                    "Failure to pay rent or agreed charges when due.",
                    "Unauthorised assignment, subletting, or use outside the permitted purpose.",
                    "Material breach of estate rules, safety requirements, or written tenancy conditions.",
                ],
                "house_rules": [
                    "No structural alteration without prior written approval.",
                    "Service and visitor access must comply with estate gate procedures.",
                    "Pets, events, or commercial activity require prior approval where estate policy requires it.",
                ],
                "inventory_schedule": [
                    "Keys, remote controls, and access cards issued at possession.",
                    "Meter readings and visible-condition schedule signed at handover.",
                    "Fixtures, fittings, and built-in appliances acknowledged in the inventory record.",
                ],
                "special_conditions": [
                    "Inventory handover and meter readings will be signed separately at possession.",
                    "Any generator or utility contribution remains payable in line with estate operations.",
                    "This template should be reviewed against the final negotiated terms and any legal advice required for execution.",
                ],
                "signatories": [
                    {"label": "Landlord / authorised signatory", "name": "Authorised Representative", "role": "Landlord"},
                    {"label": "Tenant", "name": "Kehinde Ajayi", "role": "Tenant"},
                ],
                "legal_footer": {
                    "text": "This template supports operational drafting only and should be confirmed against the executed commercial terms and legal review."
                },
            },
            "field_schema": [
                {"path": "landlord", "type": "object", "required": True, "description": "Landlord or instructing lessor details."},
                {"path": "tenant", "type": "object", "required": True, "description": "Tenant or lessee details."},
                {"path": "permitted_use", "type": "string", "required": False, "description": "Short statement of the permitted use and occupancy basis."},
                {"path": "tenant_covenants[]", "type": "array<string>", "required": False, "description": "Core tenant obligations that apply during the term."},
                {"path": "inspection_access[]", "type": "array<string>", "required": False, "description": "Inspection, repair, and handover access arrangements."},
                {"path": "included_services[]", "type": "array<string>", "required": False, "description": "Services included or acknowledged under the tenancy."},
                {"path": "special_conditions[]", "type": "array<string>", "required": False, "description": "Additional negotiated conditions appended near the close."},
            ],
        },
        "sale_agreement": {
            "label": "Sale Agreement / Offer to Purchase Pack",
            "document_type": "Sale Agreement",
            "description": "Buyer-seller agreement pack covering parties, property summary, commercial terms, title references, conditions, completion deliverables, and transaction timetable.",
            "template_structure": [
                "Transaction summary",
                "Buyer and seller block",
                "Property and commercial terms",
                "Title document schedule",
                "Conditions and completion steps",
                "Representations, costs, and remedies",
                "Signatures and legal footer",
            ],
            "reusable_components": [
                "Meta strip",
                "Party summary block",
                "Commercial terms table",
                "Document schedule bullets",
                "Transaction steps table",
                "Signature block",
            ],
            "validation_rules": [
                "seller.name is required",
                "buyer.name is required",
                "property_title is required",
                "purchase_price is required",
                "completion_date must be YYYY-MM-DD",
            ],
            "acceptance_criteria": [
                "Purchase price and completion date remain prominent on page one",
                "Title-document schedule is clearly separated from conditions and steps",
                "Signature page prints with full party blocks and footer intact",
            ],
            "sample_payload": {
                "document_number": "SAL-2026-003",
                "issue_date": "2026-04-22",
                "completion_date": "2026-06-30",
                "seller": {
                    "name": "Primeview Estates Ltd",
                    "company": "Primeview Estates Ltd",
                    "address_lines": ["Abuja, FCT"],
                },
                "buyer": {
                    "name": "Mr. Chinedu Eze",
                    "company": "",
                    "address_lines": ["Port Harcourt, Rivers State"],
                },
                "property_title": "Maitama Residential Plot",
                "property_address": "Maitama District, Abuja",
                "property_interest": "Freehold interest as represented by the seller and subject to title verification.",
                "title_status": "Seller to provide the available root-of-title and transfer history for due diligence review.",
                "purchase_price": "NGN 950,000,000",
                "deposit_amount": "NGN 95,000,000 initial deposit",
                "completion_notes": "Balance payable on or before completion against delivery of agreed title and transfer documents.",
                "title_documents": [
                    "Survey plan",
                    "Certificate of Occupancy copy",
                    "Deed or transfer history available for due diligence review",
                ],
                "conditions_precedent": [
                    "Buyer due diligence and title verification to be completed before balance payment.",
                    "Seller to make agreed title documents available for review and completion.",
                ],
                "completion_deliverables": [
                    "Executed completion and transfer pack as finally agreed by the parties and advisers.",
                    "Original or certified title-support documents available for the agreed completion process.",
                    "Vacant possession or handover arrangement as described in the commercial deal terms.",
                ],
                "representations": [
                    "The seller represents that it has authority to enter the agreed transaction documentation.",
                    "The buyer represents that acquisition funds and required approvals will be available within the agreed transaction period.",
                ],
                "costs_and_taxes": [
                    "Each party bears its own advisory and documentation costs except where specifically agreed otherwise.",
                    "Statutory fees, perfection charges, taxes, and registration costs should be allocated in the final completion documents.",
                ],
                "default_remedies": [
                    "If a condition precedent is not satisfied within the agreed window, the parties may pause or terminate the transaction as finally documented.",
                    "A deposit treatment and refund position should be confirmed in the final binding transaction documents.",
                ],
                "transaction_steps": [
                    {"step": "Initial deposit", "detail": "Buyer pays the agreed initial deposit on execution."},
                    {"step": "Due diligence", "detail": "Buyer and advisers complete title and property review."},
                    {"step": "Completion", "detail": "Balance payment and agreed transfer package are exchanged."},
                ],
                "signatories": [
                    {"label": "For the seller", "name": "Authorised Seller Representative", "role": "Seller"},
                    {"label": "For the buyer", "name": "Chinedu Eze", "role": "Buyer"},
                ],
                "legal_footer": {
                    "text": "This sale pack is a structured business template and should be finalised with transaction-specific legal review before execution."
                },
            },
            "field_schema": [
                {"path": "seller", "type": "object", "required": True, "description": "Seller or transferor details."},
                {"path": "buyer", "type": "object", "required": True, "description": "Buyer or transferee details."},
                {"path": "property_interest", "type": "string", "required": False, "description": "Property interest or estate being sold."},
                {"path": "title_documents[]", "type": "array<string>", "required": False, "description": "Document schedule available for due diligence and completion."},
                {"path": "completion_deliverables[]", "type": "array<string>", "required": False, "description": "Documents, possession items, and completion pack items expected at closing."},
                {"path": "transaction_steps[]", "type": "array<object>", "required": False, "description": "Ordered transaction milestones with short details."},
            ],
        },
    }


def document_generator_catalog(site_settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return copy.deepcopy(_catalog(site_settings))


def generator_spec(site_settings: dict[str, Any]) -> dict[str, Any]:
    catalog = document_generator_catalog(site_settings)
    return {
        "version": DOCUMENT_TEMPLATE_VERSION,
        "render_pipeline": [
            "Load site settings and brand tokens",
            "Choose template and parse payload JSON",
            "Validate common and template-specific fields",
            "Build reusable story components with conditional sections",
            "Render paginated PDF with page header/footer, table controls, and signature blocks",
            "Save the PDF into the document vault and persist payload metadata",
        ],
        "validation_rules": [
            "All payloads must be JSON objects",
            "Dates must use YYYY-MM-DD",
            "Optional brand token colors must be valid 6-digit hex values",
            "Conditional sections render only when the payload contains the required content",
        ],
        "acceptance_criteria": [
            "PDF bytes begin with %PDF and open without repair prompts",
            "First page typography and spacing remain inside print-safe margins",
            "Tables repeat headers and split by row without clipped text",
            "Footer page numbers and legal text render on every page",
            "Stored metadata matches the generated template and payload source",
        ],
        "templates": catalog,
    }


def template_options(site_settings: dict[str, Any]) -> list[tuple[str, str]]:
    catalog = document_generator_catalog(site_settings)
    return [(key, value["label"]) for key, value in catalog.items()]


def template_document_type(template_key: str, site_settings: dict[str, Any]) -> str:
    catalog = document_generator_catalog(site_settings)
    if template_key not in catalog:
        return "Other"
    return str(catalog[template_key]["document_type"])


def sample_payload_json(template_key: str, site_settings: dict[str, Any]) -> str:
    catalog = document_generator_catalog(site_settings)
    payload = catalog.get(template_key, {}).get("sample_payload", {})
    return json.dumps(payload, indent=2)


def _as_string(value: Any) -> str:
    return str(value or "").strip()


def _parse_date(value: str, label: str, errors: list[str]) -> str:
    raw = _as_string(value)
    if not raw:
        errors.append(f"{label} is required.")
        return ""
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        errors.append(f"{label} must use the YYYY-MM-DD format.")
        return ""


def _normalize_signatories(payload: dict[str, Any]) -> list[dict[str, str]]:
    signatories: list[dict[str, str]] = []
    for item in payload.get("signatories") or payload.get("approvals") or []:
        if not isinstance(item, dict):
            continue
        label = _as_string(item.get("label"))
        name = _as_string(item.get("name"))
        role = _as_string(item.get("role"))
        if name or role or label:
            signatories.append({"label": label, "name": name, "role": role})
    return signatories


def _normalize_party_block(value: Any) -> dict[str, Any]:
    block = value if isinstance(value, dict) else {}
    return {
        "name": _as_string(block.get("name")),
        "company": _as_string(block.get("company")),
        "role": _as_string(block.get("role")),
        "email": _as_string(block.get("email")),
        "phone": _as_string(block.get("phone")),
        "address_lines": [_as_string(item) for item in block.get("address_lines") or [] if _as_string(item)],
    }


def _normalize_schedule_rows(
    values: Any,
    *,
    required_keys: tuple[str, ...],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(values, list):
        return rows
    for item in values:
        if not isinstance(item, dict):
            continue
        normalized = {key: _as_string(item.get(key)) for key in required_keys}
        if any(normalized.values()):
            rows.append(normalized)
    return rows


def _normalize_string_sections(values: Any) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    if not isinstance(values, list):
        return sections
    for section in values:
        if not isinstance(section, dict):
            continue
        title = _as_string(section.get("title"))
        items = [_as_string(item) for item in section.get("items") or [] if _as_string(item)]
        if title or items:
            sections.append({"title": title, "items": items})
    return sections


def validate_generator_payload(template_key: str, raw_payload: dict[str, Any], site_settings: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    catalog = document_generator_catalog(site_settings)
    template = catalog.get(template_key)
    if template is None:
        return {}, ["Choose a valid document template."]

    payload = copy.deepcopy(raw_payload)
    errors: list[str] = []
    payload["document_number"] = _as_string(payload.get("document_number"))
    payload["issue_date"] = _parse_date(payload.get("issue_date"), "Issue date", errors)

    legal_footer = payload.get("legal_footer")
    if legal_footer is None:
        payload["legal_footer"] = {}
    elif not isinstance(legal_footer, dict):
        errors.append("legal_footer must be an object when provided.")
        payload["legal_footer"] = {}
    else:
        payload["legal_footer"] = {
            "text": _as_string(legal_footer.get("text")),
        }

    brand_tokens = payload.get("brand_tokens")
    if brand_tokens is None:
        payload["brand_tokens"] = {}
    elif not isinstance(brand_tokens, dict):
        errors.append("brand_tokens must be an object when provided.")
        payload["brand_tokens"] = {}
    else:
        cleaned_tokens: dict[str, str] = {}
        for key in ("primary_color", "accent_color", "text_color"):
            token = _as_string(brand_tokens.get(key))
            if not token:
                continue
            if not HEX_COLOR_RE.match(token):
                errors.append(f"{key.replace('_', ' ').title()} must use a 6-digit hex colour.")
                continue
            cleaned_tokens[key] = token if token.startswith("#") else f"#{token}"
        payload["brand_tokens"] = cleaned_tokens

    if template_key == "letterhead":
        recipient = payload.get("recipient")
        if not isinstance(recipient, dict):
            errors.append("recipient must be an object.")
            recipient = {}
        payload["recipient"] = {
            "name": _as_string(recipient.get("name")),
            "company": _as_string(recipient.get("company")),
            "address_lines": [_as_string(item) for item in recipient.get("address_lines") or [] if _as_string(item)],
        }
        if not payload["recipient"]["name"]:
            errors.append("recipient.name is required.")
        payload["subject"] = _as_string(payload.get("subject"))
        if not payload["subject"]:
            errors.append("subject is required.")
        payload["intro"] = _as_string(payload.get("intro"))
        body_sections = payload.get("body_sections")
        if not isinstance(body_sections, list) or not body_sections:
            errors.append("body_sections must contain at least one section.")
            payload["body_sections"] = []
        else:
            normalized_sections = []
            for section in body_sections:
                if not isinstance(section, dict):
                    continue
                heading = _as_string(section.get("heading"))
                body = _as_string(section.get("body"))
                if heading or body:
                    normalized_sections.append({"heading": heading, "body": body})
            payload["body_sections"] = normalized_sections
            if not normalized_sections:
                errors.append("body_sections must contain at least one valid section.")
        payload["callouts"] = [_as_string(item) for item in payload.get("callouts") or [] if _as_string(item)]
        payload["closing"] = _as_string(payload.get("closing"))
    elif template_key == "billing":
        bill_to = payload.get("bill_to")
        if not isinstance(bill_to, dict):
            errors.append("bill_to must be an object.")
            bill_to = {}
        payload["bill_to"] = {
            "name": _as_string(bill_to.get("name")),
            "company": _as_string(bill_to.get("company")),
            "address_lines": [_as_string(item) for item in bill_to.get("address_lines") or [] if _as_string(item)],
        }
        if not payload["bill_to"]["name"]:
            errors.append("bill_to.name is required.")
        payload["due_date"] = _parse_date(payload.get("due_date"), "Due date", errors)
        payload["currency"] = _as_string(payload.get("currency")).upper()
        if len(payload["currency"]) != 3:
            errors.append("currency must be a 3-letter code.")
        items = payload.get("line_items")
        if not isinstance(items, list) or not items:
            errors.append("line_items must contain at least one item.")
            payload["line_items"] = []
        else:
            normalized_items = []
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                description = _as_string(item.get("description"))
                try:
                    quantity = float(item.get("quantity", 0))
                    unit_price = float(item.get("unit_price", 0))
                except (TypeError, ValueError):
                    errors.append(f"Line item {index} must use numeric quantity and unit_price.")
                    continue
                if not description:
                    errors.append(f"Line item {index} description is required.")
                if quantity <= 0:
                    errors.append(f"Line item {index} quantity must be greater than zero.")
                if unit_price < 0:
                    errors.append(f"Line item {index} unit price cannot be negative.")
                normalized_items.append(
                    {
                        "description": description,
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "amount": float(item.get("amount", quantity * unit_price) or quantity * unit_price),
                    }
                )
            payload["line_items"] = normalized_items
        payload["payment_instructions"] = [_as_string(item) for item in payload.get("payment_instructions") or [] if _as_string(item)]
        payload["notes"] = [_as_string(item) for item in payload.get("notes") or [] if _as_string(item)]
        payload["terms"] = _as_string(payload.get("terms"))
    elif template_key == "proposal":
        client = payload.get("client")
        if not isinstance(client, dict):
            errors.append("client must be an object.")
            client = {}
        payload["client"] = {
            "name": _as_string(client.get("name")),
            "company": _as_string(client.get("company")),
            "address_lines": [_as_string(item) for item in client.get("address_lines") or [] if _as_string(item)],
        }
        if not payload["client"]["name"]:
            errors.append("client.name is required.")
        payload["project_title"] = _as_string(payload.get("project_title"))
        payload["executive_summary"] = _as_string(payload.get("executive_summary"))
        if not payload["project_title"]:
            errors.append("project_title is required.")
        if not payload["executive_summary"]:
            errors.append("executive_summary is required.")
        if payload.get("valid_until"):
            payload["valid_until"] = _parse_date(payload.get("valid_until"), "Valid until", errors)
        service_blocks = payload.get("service_blocks")
        if not isinstance(service_blocks, list) or not service_blocks:
            errors.append("service_blocks must contain at least one block.")
            payload["service_blocks"] = []
        else:
            normalized_blocks = []
            for block in service_blocks:
                if not isinstance(block, dict):
                    continue
                title = _as_string(block.get("title"))
                items = [_as_string(item) for item in block.get("items") or [] if _as_string(item)]
                fee_label = _as_string(block.get("fee_label"))
                if title or items or fee_label:
                    normalized_blocks.append({"title": title, "items": items, "fee_label": fee_label})
            payload["service_blocks"] = normalized_blocks
            if not normalized_blocks:
                errors.append("service_blocks must contain at least one valid block.")
        payload["timeline"] = [
            {"phase": _as_string(item.get("phase")), "details": _as_string(item.get("details"))}
            for item in payload.get("timeline") or []
            if isinstance(item, dict) and (_as_string(item.get("phase")) or _as_string(item.get("details")))
        ]
        payload["commercials"] = [
            {"label": _as_string(item.get("label")), "value": _as_string(item.get("value"))}
            for item in payload.get("commercials") or []
            if isinstance(item, dict) and (_as_string(item.get("label")) or _as_string(item.get("value")))
        ]
        payload["terms"] = [_as_string(item) for item in payload.get("terms") or [] if _as_string(item)]
    elif template_key == "discovery":
        client = payload.get("client")
        if not isinstance(client, dict):
            errors.append("client must be an object.")
            client = {}
        payload["client"] = {
            "name": _as_string(client.get("name")),
            "company": _as_string(client.get("company")),
            "address_lines": [_as_string(item) for item in client.get("address_lines") or [] if _as_string(item)],
        }
        if not payload["client"]["name"]:
            errors.append("client.name is required.")
        payload["intro"] = _as_string(payload.get("intro"))
        payload["response_instructions"] = [_as_string(item) for item in payload.get("response_instructions") or [] if _as_string(item)]
        sections = payload.get("sections")
        if not isinstance(sections, list) or not sections:
            errors.append("sections must contain at least one section.")
            payload["sections"] = []
        else:
            normalized_sections = []
            for index, section in enumerate(sections, start=1):
                if not isinstance(section, dict):
                    continue
                title = _as_string(section.get("title"))
                questions = [_as_string(item) for item in section.get("questions") or [] if _as_string(item)]
                if not questions:
                    errors.append(f"Section {index} must contain at least one question.")
                normalized_sections.append({"title": title, "questions": questions})
            payload["sections"] = normalized_sections
        owner = payload.get("contact_owner")
        if owner and isinstance(owner, dict):
            payload["contact_owner"] = {
                "name": _as_string(owner.get("name")),
                "role": _as_string(owner.get("role")),
                "email": _as_string(owner.get("email")),
            }
        else:
            payload["contact_owner"] = {}
        payload["signature_prompt"] = _as_string(payload.get("signature_prompt"))
    elif template_key == "delivery_checklist":
        payload["project_title"] = _as_string(payload.get("project_title"))
        if not payload["project_title"]:
            errors.append("project_title is required.")
        owner = payload.get("delivery_owner")
        if owner and isinstance(owner, dict):
            payload["delivery_owner"] = {
                "name": _as_string(owner.get("name")),
                "role": _as_string(owner.get("role")),
                "email": _as_string(owner.get("email")),
            }
        else:
            payload["delivery_owner"] = {}
        checklist_sections = payload.get("checklist_sections")
        if not isinstance(checklist_sections, list) or not checklist_sections:
            errors.append("checklist_sections must contain at least one section.")
            payload["checklist_sections"] = []
        else:
            normalized_sections = []
            for index, section in enumerate(checklist_sections, start=1):
                if not isinstance(section, dict):
                    continue
                title = _as_string(section.get("title"))
                items = []
                for item in section.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    label = _as_string(item.get("label"))
                    status = _as_string(item.get("status"))
                    owner_name = _as_string(item.get("owner"))
                    note = _as_string(item.get("note"))
                    if label or status or owner_name or note:
                        items.append({"label": label, "status": status, "owner": owner_name, "note": note})
                if not items:
                    errors.append(f"Checklist section {index} must contain at least one item.")
                normalized_sections.append({"title": title, "items": items})
            payload["checklist_sections"] = normalized_sections
        payload["handover_notes"] = [_as_string(item) for item in payload.get("handover_notes") or [] if _as_string(item)]
    elif template_key == "payment_receipt":
        payload["payer"] = _normalize_party_block(payload.get("payer"))
        if not payload["payer"]["name"]:
            errors.append("payer.name is required.")
        payload["payment_date"] = _parse_date(payload.get("payment_date"), "Payment date", errors)
        payload["currency"] = _as_string(payload.get("currency")).upper()
        if len(payload["currency"]) != 3:
            errors.append("currency must be a 3-letter code.")
        receipt_items = payload.get("receipt_items")
        if not isinstance(receipt_items, list) or not receipt_items:
            errors.append("receipt_items must contain at least one item.")
            payload["receipt_items"] = []
        else:
            normalized_items = []
            for index, item in enumerate(receipt_items, start=1):
                if not isinstance(item, dict):
                    continue
                label = _as_string(item.get("label"))
                try:
                    amount = float(item.get("amount", 0))
                except (TypeError, ValueError):
                    errors.append(f"Receipt item {index} amount must be numeric.")
                    continue
                if not label:
                    errors.append(f"Receipt item {index} label is required.")
                if amount < 0:
                    errors.append(f"Receipt item {index} amount cannot be negative.")
                normalized_items.append({"label": label, "amount": amount})
            payload["receipt_items"] = normalized_items
        payload["payment_method"] = _as_string(payload.get("payment_method"))
        if not payload["payment_method"]:
            errors.append("payment_method is required.")
        payload["payment_reference"] = _as_string(payload.get("payment_reference"))
        payload["received_by"] = _as_string(payload.get("received_by"))
        payload["notes"] = [_as_string(item) for item in payload.get("notes") or [] if _as_string(item)]
    elif template_key == "inspection_report":
        payload["inspection_date"] = _parse_date(payload.get("inspection_date"), "Inspection date", errors)
        payload["inspection_type"] = _as_string(payload.get("inspection_type"))
        payload["property_title"] = _as_string(payload.get("property_title"))
        payload["property_address"] = _as_string(payload.get("property_address"))
        if not payload["inspection_type"]:
            errors.append("inspection_type is required.")
        if not payload["property_title"]:
            errors.append("property_title is required.")
        payload["inspected_by"] = _normalize_party_block(payload.get("inspected_by"))
        payload["inspected_for"] = _normalize_party_block(payload.get("inspected_for"))
        payload["summary"] = _as_string(payload.get("summary"))
        sections = payload.get("sections")
        if not isinstance(sections, list) or not sections:
            errors.append("sections must contain at least one section.")
            payload["sections"] = []
        else:
            normalized_sections = []
            for index, section in enumerate(sections, start=1):
                if not isinstance(section, dict):
                    continue
                title = _as_string(section.get("title"))
                observations = []
                for item in section.get("observations") or []:
                    if not isinstance(item, dict):
                        continue
                    area = _as_string(item.get("area"))
                    condition = _as_string(item.get("condition"))
                    status = _as_string(item.get("status"))
                    note = _as_string(item.get("note"))
                    if area or condition or status or note:
                        observations.append(
                            {
                                "area": area,
                                "condition": condition,
                                "status": status,
                                "note": note,
                            }
                        )
                if not observations:
                    errors.append(f"Inspection section {index} must contain at least one observation.")
                normalized_sections.append({"title": title, "observations": observations})
            payload["sections"] = normalized_sections
        payload["recommendations"] = [_as_string(item) for item in payload.get("recommendations") or [] if _as_string(item)]
    elif template_key == "maintenance_work_order":
        payload["request_reference"] = _as_string(payload.get("request_reference"))
        payload["property_title"] = _as_string(payload.get("property_title"))
        payload["unit_reference"] = _as_string(payload.get("unit_reference"))
        payload["vendor"] = _normalize_party_block(payload.get("vendor"))
        payload["issued_by"] = _normalize_party_block(payload.get("issued_by"))
        payload["issue_summary"] = _as_string(payload.get("issue_summary"))
        if not payload["vendor"]["name"]:
            errors.append("vendor.name is required.")
        if not payload["property_title"]:
            errors.append("property_title is required.")
        if not payload["issue_summary"]:
            errors.append("issue_summary is required.")
        scope_items = payload.get("scope_items")
        if not isinstance(scope_items, list) or not scope_items:
            errors.append("scope_items must contain at least one item.")
            payload["scope_items"] = []
        else:
            normalized_items = []
            for index, item in enumerate(scope_items, start=1):
                if not isinstance(item, dict):
                    continue
                task = _as_string(item.get("task"))
                priority = _as_string(item.get("priority"))
                materials = _as_string(item.get("materials"))
                note = _as_string(item.get("note"))
                if not task:
                    errors.append(f"Scope item {index} task is required.")
                if task or priority or materials or note:
                    normalized_items.append(
                        {
                            "task": task,
                            "priority": priority,
                            "materials": materials,
                            "note": note,
                        }
                    )
            payload["scope_items"] = normalized_items
        payload["site_notes"] = [_as_string(item) for item in payload.get("site_notes") or [] if _as_string(item)]
        payload["completion_requirements"] = [
            _as_string(item) for item in payload.get("completion_requirements") or [] if _as_string(item)
        ]
    elif template_key == "lease_notice":
        payload["tenant"] = _normalize_party_block(payload.get("tenant"))
        if not payload["tenant"]["name"]:
            errors.append("tenant.name is required.")
        payload["property_title"] = _as_string(payload.get("property_title"))
        payload["unit_reference"] = _as_string(payload.get("unit_reference"))
        payload["notice_type"] = _as_string(payload.get("notice_type"))
        payload["current_term_end"] = _parse_date(payload.get("current_term_end"), "Current term end", errors)
        if payload.get("proposed_start"):
            payload["proposed_start"] = _parse_date(payload.get("proposed_start"), "Proposed start", errors)
        else:
            payload["proposed_start"] = ""
        payload["current_rent"] = _as_string(payload.get("current_rent"))
        payload["proposed_rent"] = _as_string(payload.get("proposed_rent"))
        payload["notice_reason"] = _as_string(payload.get("notice_reason"))
        payload["service_charge_note"] = _as_string(payload.get("service_charge_note"))
        payload["response_deadline"] = _parse_date(payload.get("response_deadline"), "Response deadline", errors)
        if not payload["property_title"]:
            errors.append("property_title is required.")
        if not payload["proposed_rent"]:
            errors.append("proposed_rent is required.")
        payload["key_terms"] = [_as_string(item) for item in payload.get("key_terms") or [] if _as_string(item)]
        payload["response_options"] = [_as_string(item) for item in payload.get("response_options") or [] if _as_string(item)]
        payload["next_steps"] = [_as_string(item) for item in payload.get("next_steps") or [] if _as_string(item)]
        payload["special_conditions"] = [_as_string(item) for item in payload.get("special_conditions") or [] if _as_string(item)]
    elif template_key == "management_agreement":
        payload["effective_date"] = _parse_date(payload.get("effective_date"), "Effective date", errors)
        payload["owner"] = _normalize_party_block(payload.get("owner"))
        payload["manager"] = _normalize_party_block(payload.get("manager"))
        payload["property_title"] = _as_string(payload.get("property_title"))
        payload["property_address"] = _as_string(payload.get("property_address"))
        payload["term_summary"] = _as_string(payload.get("term_summary"))
        if not payload["owner"]["name"]:
            errors.append("owner.name is required.")
        if not payload["manager"]["name"]:
            errors.append("manager.name is required.")
        if not payload["property_title"]:
            errors.append("property_title is required.")
        payload["scope_sections"] = _normalize_string_sections(payload.get("scope_sections"))
        if not payload["scope_sections"]:
            errors.append("scope_sections must contain at least one section.")
        payload["fee_schedule"] = _normalize_schedule_rows(payload.get("fee_schedule"), required_keys=("label", "value"))
        payload["reporting_cadence"] = _as_string(payload.get("reporting_cadence"))
        payload["authority_limits"] = [_as_string(item) for item in payload.get("authority_limits") or [] if _as_string(item)]
        payload["service_standards"] = [_as_string(item) for item in payload.get("service_standards") or [] if _as_string(item)]
        payload["owner_obligations"] = [_as_string(item) for item in payload.get("owner_obligations") or [] if _as_string(item)]
        payload["manager_obligations"] = [_as_string(item) for item in payload.get("manager_obligations") or [] if _as_string(item)]
        payload["termination_events"] = [_as_string(item) for item in payload.get("termination_events") or [] if _as_string(item)]
        payload["special_conditions"] = [_as_string(item) for item in payload.get("special_conditions") or [] if _as_string(item)]
    elif template_key == "tenancy_agreement":
        payload["commencement_date"] = _parse_date(payload.get("commencement_date"), "Commencement date", errors)
        payload["expiry_date"] = _parse_date(payload.get("expiry_date"), "Expiry date", errors)
        payload["tenancy_type"] = _as_string(payload.get("tenancy_type"))
        payload["landlord"] = _normalize_party_block(payload.get("landlord"))
        payload["tenant"] = _normalize_party_block(payload.get("tenant"))
        payload["property_title"] = _as_string(payload.get("property_title"))
        payload["premises_address"] = _as_string(payload.get("premises_address"))
        payload["permitted_use"] = _as_string(payload.get("permitted_use"))
        payload["rent_amount"] = _as_string(payload.get("rent_amount"))
        payload["deposit_amount"] = _as_string(payload.get("deposit_amount"))
        payload["payment_schedule"] = _as_string(payload.get("payment_schedule"))
        if not payload["landlord"]["name"]:
            errors.append("landlord.name is required.")
        if not payload["tenant"]["name"]:
            errors.append("tenant.name is required.")
        if not payload["rent_amount"]:
            errors.append("rent_amount is required.")
        payload["included_services"] = [_as_string(item) for item in payload.get("included_services") or [] if _as_string(item)]
        payload["utilities_and_outgoings"] = [_as_string(item) for item in payload.get("utilities_and_outgoings") or [] if _as_string(item)]
        payload["landlord_covenants"] = [_as_string(item) for item in payload.get("landlord_covenants") or [] if _as_string(item)]
        payload["tenant_covenants"] = [_as_string(item) for item in payload.get("tenant_covenants") or [] if _as_string(item)]
        payload["inspection_access"] = [_as_string(item) for item in payload.get("inspection_access") or [] if _as_string(item)]
        payload["default_events"] = [_as_string(item) for item in payload.get("default_events") or [] if _as_string(item)]
        payload["house_rules"] = [_as_string(item) for item in payload.get("house_rules") or [] if _as_string(item)]
        payload["inventory_schedule"] = [_as_string(item) for item in payload.get("inventory_schedule") or [] if _as_string(item)]
        payload["special_conditions"] = [_as_string(item) for item in payload.get("special_conditions") or [] if _as_string(item)]
    elif template_key == "sale_agreement":
        payload["completion_date"] = _parse_date(payload.get("completion_date"), "Completion date", errors)
        payload["seller"] = _normalize_party_block(payload.get("seller"))
        payload["buyer"] = _normalize_party_block(payload.get("buyer"))
        payload["property_title"] = _as_string(payload.get("property_title"))
        payload["property_address"] = _as_string(payload.get("property_address"))
        payload["property_interest"] = _as_string(payload.get("property_interest"))
        payload["title_status"] = _as_string(payload.get("title_status"))
        payload["purchase_price"] = _as_string(payload.get("purchase_price"))
        payload["deposit_amount"] = _as_string(payload.get("deposit_amount"))
        payload["completion_notes"] = _as_string(payload.get("completion_notes"))
        if not payload["seller"]["name"]:
            errors.append("seller.name is required.")
        if not payload["buyer"]["name"]:
            errors.append("buyer.name is required.")
        if not payload["property_title"]:
            errors.append("property_title is required.")
        if not payload["purchase_price"]:
            errors.append("purchase_price is required.")
        payload["title_documents"] = [_as_string(item) for item in payload.get("title_documents") or [] if _as_string(item)]
        payload["conditions_precedent"] = [_as_string(item) for item in payload.get("conditions_precedent") or [] if _as_string(item)]
        payload["completion_deliverables"] = [_as_string(item) for item in payload.get("completion_deliverables") or [] if _as_string(item)]
        payload["representations"] = [_as_string(item) for item in payload.get("representations") or [] if _as_string(item)]
        payload["costs_and_taxes"] = [_as_string(item) for item in payload.get("costs_and_taxes") or [] if _as_string(item)]
        payload["default_remedies"] = [_as_string(item) for item in payload.get("default_remedies") or [] if _as_string(item)]
        payload["transaction_steps"] = _normalize_schedule_rows(payload.get("transaction_steps"), required_keys=("step", "detail"))

    payload["signatories"] = _normalize_signatories(payload)
    return payload, errors


def _currency_label(currency: str, amount: float) -> str:
    return f"{currency} {amount:,.2f}"


class PremiumPdfBuilder:
    def __init__(self, destination: Path, title: str, payload: dict[str, Any], site_settings: dict[str, Any]):
        self.destination = destination
        self.title = title
        self.payload = payload
        self.site_settings = site_settings
        self.brand = self._brand_tokens()
        self.styles = self._build_styles()
        self.logo_reader, self.logo_aspect = _pdf_logo_image()
        self.doc = self._build_doc()

    def _brand_tokens(self) -> dict[str, Any]:
        custom = self.payload.get("brand_tokens") or {}
        return {
            "primary": colors.HexColor(custom.get("primary_color", "#7b3327")),
            "accent": colors.HexColor(custom.get("accent_color", "#a16f36")),
            "text": colors.HexColor(custom.get("text_color", "#182028")),
            "muted": colors.HexColor("#59615f"),
            "line": colors.HexColor("#d9ccbe"),
            "surface": colors.HexColor("#fffdf9"),
            "panel": colors.HexColor("#f8f3ee"),
            "row_alt": colors.HexColor("#fbf8f4"),
        }

    def _build_styles(self) -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "eyebrow": ParagraphStyle(
                "eyebrow",
                parent=base["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=self.brand["muted"],
                spaceAfter=4,
            ),
            "title": ParagraphStyle(
                "title",
                parent=base["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=22,
                leading=26,
                textColor=self.brand["text"],
                spaceAfter=6,
            ),
            "subtitle": ParagraphStyle(
                "subtitle",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=10,
                leading=14,
                textColor=self.brand["muted"],
                spaceAfter=10,
            ),
            "section": ParagraphStyle(
                "section",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=12.5,
                leading=15,
                textColor=self.brand["text"],
                spaceBefore=10,
                spaceAfter=6,
                keepWithNext=True,
            ),
            "body": ParagraphStyle(
                "body",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=9.6,
                leading=14.2,
                textColor=self.brand["text"],
                spaceAfter=6,
                allowWidows=0,
                allowOrphans=0,
            ),
            "list_body": ParagraphStyle(
                "list_body",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=9.4,
                leading=12.8,
                textColor=self.brand["text"],
                spaceAfter=2.5,
                allowWidows=0,
                allowOrphans=0,
            ),
            "small": ParagraphStyle(
                "small",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=8.2,
                leading=11.2,
                textColor=self.brand["muted"],
                spaceAfter=4,
            ),
            "table_head": ParagraphStyle(
                "table_head",
                parent=base["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8.2,
                leading=10,
                textColor=colors.white,
                alignment=TA_LEFT,
            ),
            "table_body": ParagraphStyle(
                "table_body",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=8.7,
                leading=11.4,
                textColor=self.brand["text"],
                allowWidows=0,
                allowOrphans=0,
            ),
            "meta_label": ParagraphStyle(
                "meta_label",
                parent=base["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=7.6,
                leading=10,
                textColor=self.brand["muted"],
            ),
            "meta_value": ParagraphStyle(
                "meta_value",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=9.2,
                leading=12,
                textColor=self.brand["text"],
            ),
            "right_small": ParagraphStyle(
                "right_small",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=8.2,
                leading=10,
                textColor=self.brand["muted"],
                alignment=TA_RIGHT,
            ),
            "center_small": ParagraphStyle(
                "center_small",
                parent=base["BodyText"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
                textColor=self.brand["muted"],
                alignment=TA_CENTER,
            ),
        }

    def _build_doc(self) -> BaseDocTemplate:
        doc = BaseDocTemplate(
            str(self.destination),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=26 * mm,
            bottomMargin=22 * mm,
            title=self.title,
        )
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
        doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=self._draw_chrome)])
        return doc

    def _draw_chrome(self, canvas, doc) -> None:
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(self.brand["primary"])
        canvas.rect(0, height - (12 * mm), width, 12 * mm, stroke=0, fill=1)
        if self.logo_reader is not None:
            try:
                max_logo_width = 32 * mm
                max_logo_height = 14 * mm
                aspect = self.logo_aspect or 1.0
                if aspect >= (max_logo_width / max_logo_height):
                    logo_width = max_logo_width
                    logo_height = logo_width / aspect
                else:
                    logo_height = max_logo_height
                    logo_width = logo_height * aspect

                box_width = logo_width + (6 * mm)
                box_height = max(logo_height + (4 * mm), 12 * mm)
                box_x = doc.leftMargin
                box_y = height - (24 * mm)
                canvas.setFillColor(colors.white)
                canvas.roundRect(box_x, box_y, box_width, box_height, 2 * mm, stroke=0, fill=1)
                logo_x = box_x + ((box_width - logo_width) / 2)
                logo_y = box_y + ((box_height - logo_height) / 2)
                canvas.drawImage(
                    self.logo_reader,
                    logo_x,
                    logo_y,
                    width=logo_width,
                    height=logo_height,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                title_x = box_x + box_width + (4 * mm)
            except Exception:
                title_x = doc.leftMargin
        else:
            title_x = doc.leftMargin
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(title_x, height - 8 * mm, str(self.site_settings.get("site_name") or "Structurebase"))

        footer_primary = str(
            self.payload.get("legal_footer", {}).get("text") or self.site_settings.get("footer_summary") or ""
        ).strip()
        footer_secondary_parts = [
            str(self.site_settings.get("office_address") or "").strip(),
            str(self.site_settings.get("contact_email") or "").strip(),
            str(self.site_settings.get("contact_phone_display") or "").strip(),
        ]
        footer_secondary = " | ".join(part for part in footer_secondary_parts if part)

        canvas.setStrokeColor(self.brand["line"])
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, 18 * mm, width - doc.rightMargin, 18 * mm)

        canvas.setFillColor(self.brand["muted"])
        canvas.setFont("Helvetica", 7.5)
        footer_text_width = doc.width - (22 * mm)
        footer_lines = simpleSplit(footer_primary, "Helvetica", 7.5, footer_text_width)[:2]
        footer_line_y = 14 * mm + ((len(footer_lines) - 1) * 2.8 * mm if footer_lines else 0)
        for line in footer_lines:
            canvas.drawString(doc.leftMargin, footer_line_y, line)
            footer_line_y -= 2.8 * mm

        if footer_secondary:
            canvas.drawString(doc.leftMargin, 9.5 * mm, footer_secondary)

        canvas.setFillColor(self.brand["text"])
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawRightString(width - doc.rightMargin, 9.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def build(self, story: list[Any]) -> None:
        self.doc.build(story)

    def paragraph(self, text: str, style_name: str = "body") -> Paragraph:
        return Paragraph(text.replace("\n", "<br/>"), self.styles[style_name])

    def spacer(self, value_mm: float) -> Spacer:
        return Spacer(1, value_mm * mm)

    def meta_table(self, rows: list[tuple[str, str]]) -> Table:
        data = []
        for label, value in rows:
            data.append(
                [
                    Paragraph(label, self.styles["meta_label"]),
                    Paragraph(str(value or "Not provided"), self.styles["meta_value"]),
                ]
            )
        table = Table(data, colWidths=[36 * mm, self.doc.width - (36 * mm)], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), self.brand["panel"]),
                    ("BOX", (0, 0), (-1, -1), 0.45, self.brand["line"]),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.3, self.brand["line"]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    def info_table(self, rows: list[list[Any]], col_widths: list[float], header: bool = True, align_right_cols: list[int] | None = None) -> Table:
        table = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0, splitByRow=1, hAlign="LEFT")
        styles = [
            ("INNERGRID", (0, 0), (-1, -1), 0.3, self.brand["line"]),
            ("BOX", (0, 0), (-1, -1), 0.6, self.brand["line"]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("WORDWRAP", (0, 0), (-1, -1), "CJK"),
        ]
        if header:
            styles.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), self.brand["primary"]),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ]
            )
        body_start = 1 if header else 0
        for row_index in range(body_start, len(rows)):
            if (row_index - body_start) % 2 == 1:
                styles.append(("BACKGROUND", (0, row_index), (-1, row_index), self.brand["row_alt"]))
        if align_right_cols:
            for column in align_right_cols:
                styles.append(("ALIGN", (column, 0), (column, -1), "RIGHT"))
        table.setStyle(TableStyle(styles))
        return table

    def bullet_list(self, items: list[str]) -> ListFlowable:
        return ListFlowable(
            [ListItem(self.paragraph(item, "list_body"), leftIndent=0) for item in items],
            bulletType="bullet",
            start="circle",
            bulletFontName="Helvetica-Bold",
            bulletFontSize=5,
            bulletColor=self.brand["accent"],
            bulletOffsetY=2,
            leftIndent=10,
            bulletDedent=5,
        )

    def signature_table(self, signatories: list[dict[str, str]]) -> Table:
        columns = []
        for signatory in signatories:
            title_bits = [bit for bit in [signatory.get("label"), signatory.get("name"), signatory.get("role")] if bit]
            text = "<br/>".join(
                [
                    "<font color='#5b615d'>______________________________</font>",
                    *title_bits,
                ]
            )
            columns.append(self.paragraph(text, "body"))
        table = Table([columns], colWidths=[self.doc.width / max(len(columns), 1)] * max(len(columns), 1))
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return table


def _document_header(builder: PremiumPdfBuilder, payload: dict[str, Any], title: str, subtitle: str = "") -> list[Any]:
    meta_rows = [("Reference", payload.get("document_number") or "Reference pending"), ("Issue date", payload.get("issue_date") or "Not provided")]
    if payload.get("due_date"):
        meta_rows.append(("Due date", payload["due_date"]))
    if payload.get("valid_until"):
        meta_rows.append(("Valid until", payload["valid_until"]))
    story: list[Any] = [
        builder.paragraph("Prepared document", "eyebrow"),
        builder.paragraph(title, "title"),
    ]
    if subtitle:
        story.append(builder.paragraph(subtitle, "subtitle"))
    story.extend([builder.meta_table(meta_rows), builder.spacer(3)])
    return story


def _contact_lines(block: dict[str, Any]) -> str:
    lines = [value for value in [block.get("name"), block.get("company"), *block.get("address_lines", [])] if value]
    return "<br/>".join(lines) if lines else "Not provided"


def _render_letterhead(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, str(payload.get("subject") or ""))
    recipient_html = _contact_lines(payload["recipient"])
    story.extend(
        [
            builder.paragraph("Recipient", "section"),
            builder.meta_table([("To", recipient_html)]),
        ]
    )
    if payload.get("intro"):
        story.append(builder.paragraph(payload["intro"]))
    for section in payload.get("body_sections", []):
        story.append(KeepTogether([builder.paragraph(section["heading"] or "Section", "section"), builder.paragraph(section["body"] or "Not provided")]))
    if payload.get("callouts"):
        story.extend([builder.paragraph("Key points", "section"), builder.bullet_list(payload["callouts"])])
    if payload.get("closing"):
        story.extend([builder.spacer(3), builder.paragraph(payload["closing"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_billing(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, "Invoice summary")
    issuer_block = {
        "name": builder.site_settings.get("site_name"),
        "company": builder.site_settings.get("office_address"),
        "address_lines": [builder.site_settings.get("contact_email"), builder.site_settings.get("contact_phone_display")],
    }
    summary = Table(
        [
            [
                builder.paragraph("<b>Bill to</b><br/>" + _contact_lines(payload["bill_to"]), "body"),
                builder.paragraph("<b>Issuer</b><br/>" + _contact_lines(issuer_block), "body"),
            ]
        ],
        colWidths=[builder.doc.width / 2, builder.doc.width / 2],
    )
    summary.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.append(summary)

    rows: list[list[Any]] = [
        [
            Paragraph("Description", builder.styles["table_head"]),
            Paragraph("Qty", builder.styles["table_head"]),
            Paragraph("Unit", builder.styles["table_head"]),
            Paragraph("Amount", builder.styles["table_head"]),
        ]
    ]
    total = 0.0
    for item in payload.get("line_items", []):
        amount = float(item["amount"])
        total += amount
        rows.append(
            [
                builder.paragraph(item["description"], "table_body"),
                builder.paragraph(f"{item['quantity']:,.2f}".rstrip("0").rstrip("."), "table_body"),
                builder.paragraph(_currency_label(payload["currency"], float(item["unit_price"])), "table_body"),
                builder.paragraph(_currency_label(payload["currency"], amount), "table_body"),
            ]
        )
    story.append(builder.info_table(rows, [builder.doc.width * 0.47, builder.doc.width * 0.12, builder.doc.width * 0.19, builder.doc.width * 0.22], align_right_cols=[1, 2, 3]))
    story.append(builder.spacer(4))
    totals = Table(
        [
            [builder.paragraph("Subtotal", "meta_label"), builder.paragraph(_currency_label(payload["currency"], total), "meta_value")],
            [builder.paragraph("Total due", "meta_label"), builder.paragraph(f"<b>{_currency_label(payload['currency'], total)}</b>", "meta_value")],
        ],
        colWidths=[30 * mm, 45 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(totals)
    if payload.get("payment_instructions"):
        story.extend([builder.paragraph("Payment instructions", "section"), builder.bullet_list(payload["payment_instructions"])])
    if payload.get("notes"):
        story.extend([builder.paragraph("Notes", "section"), builder.bullet_list(payload["notes"])])
    if payload.get("terms"):
        story.extend([builder.paragraph("Terms", "section"), builder.paragraph(payload["terms"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_proposal(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, payload.get("project_title") or "")
    story.append(builder.meta_table([("Client", _contact_lines(payload["client"]))]))
    story.extend([builder.paragraph("Executive summary", "section"), builder.paragraph(payload["executive_summary"])])
    for block in payload.get("service_blocks", []):
        section_story = [builder.paragraph(block["title"] or "Service block", "section")]
        if block.get("items"):
            section_story.append(builder.bullet_list(block["items"]))
        if block.get("fee_label"):
            section_story.append(builder.paragraph(f"<b>Commercial:</b> {block['fee_label']}", "body"))
        story.append(KeepTogether(section_story))
    if payload.get("timeline"):
        rows = [[Paragraph("Phase", builder.styles["table_head"]), Paragraph("Details", builder.styles["table_head"])]]
        rows.extend(
            [
                [builder.paragraph(item["phase"], "table_body"), builder.paragraph(item["details"], "table_body")]
                for item in payload["timeline"]
            ]
        )
        story.extend([builder.paragraph("Timeline", "section"), builder.info_table(rows, [builder.doc.width * 0.22, builder.doc.width * 0.78])])
    if payload.get("commercials"):
        rows = [[Paragraph("Commercial item", builder.styles["table_head"]), Paragraph("Value", builder.styles["table_head"])]]
        rows.extend(
            [
                [builder.paragraph(item["label"], "table_body"), builder.paragraph(item["value"], "table_body")]
                for item in payload["commercials"]
            ]
        )
        story.extend([builder.paragraph("Commercials", "section"), builder.info_table(rows, [builder.doc.width * 0.62, builder.doc.width * 0.38], align_right_cols=[1])])
    if payload.get("terms"):
        story.extend([builder.paragraph("Terms", "section"), builder.bullet_list(payload["terms"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_discovery(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, "Discovery questionnaire")
    story.append(builder.meta_table([("Client", _contact_lines(payload["client"]))]))
    if payload.get("intro"):
        story.append(builder.paragraph(payload["intro"]))
    if payload.get("response_instructions"):
        story.extend([builder.paragraph("Response instructions", "section"), builder.bullet_list(payload["response_instructions"])])
    for section in payload.get("sections", []):
        rows = [[Paragraph("Question", builder.styles["table_head"]), Paragraph("Response notes", builder.styles["table_head"])]]
        rows.extend(
            [
                [
                    builder.paragraph(question, "table_body"),
                    builder.paragraph("______________________________________________", "table_body"),
                ]
                for question in section.get("questions", [])
            ]
        )
        story.extend(
            [
                builder.paragraph(section.get("title") or "Question section", "section"),
                builder.info_table(rows, [builder.doc.width * 0.58, builder.doc.width * 0.42]),
            ]
        )
    if payload.get("contact_owner"):
        owner = payload["contact_owner"]
        owner_lines = [value for value in [owner.get("name"), owner.get("role"), owner.get("email")] if value]
        story.extend([builder.paragraph("Return contact", "section"), builder.paragraph("<br/>".join(owner_lines), "body")])
    if payload.get("signature_prompt"):
        story.extend(
            [
                builder.spacer(6),
                builder.paragraph(payload["signature_prompt"], "section"),
                builder.signature_table([{"label": payload["signature_prompt"], "name": "", "role": ""}]),
            ]
        )
    return story


def _render_delivery_checklist(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, payload.get("project_title") or "")
    owner = payload.get("delivery_owner") or {}
    owner_lines = [value for value in [owner.get("name"), owner.get("role"), owner.get("email")] if value]
    if owner_lines:
        story.append(builder.meta_table([("Delivery owner", "<br/>".join(owner_lines))]))
    for section in payload.get("checklist_sections", []):
        rows = [
            [
                Paragraph("Item", builder.styles["table_head"]),
                Paragraph("Status", builder.styles["table_head"]),
                Paragraph("Owner", builder.styles["table_head"]),
                Paragraph("Note", builder.styles["table_head"]),
            ]
        ]
        rows.extend(
            [
                [
                    builder.paragraph(item["label"], "table_body"),
                    builder.paragraph(item["status"], "table_body"),
                    builder.paragraph(item["owner"], "table_body"),
                    builder.paragraph(item["note"], "table_body"),
                ]
                for item in section.get("items", [])
            ]
        )
        story.extend(
            [
                builder.paragraph(section.get("title") or "Checklist section", "section"),
                builder.info_table(rows, [builder.doc.width * 0.36, builder.doc.width * 0.14, builder.doc.width * 0.18, builder.doc.width * 0.32]),
            ]
        )
    if payload.get("handover_notes"):
        story.extend([builder.paragraph("Handover notes", "section"), builder.bullet_list(payload["handover_notes"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.paragraph("Approvals", "section"), builder.signature_table(payload["signatories"])])
    return story


def _render_payment_receipt(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, "Official payment receipt")
    issuer_block = {
        "name": builder.site_settings.get("site_name"),
        "company": builder.site_settings.get("office_address"),
        "address_lines": [builder.site_settings.get("contact_email"), builder.site_settings.get("contact_phone_display")],
    }
    summary = Table(
        [[
            builder.paragraph("<b>Received from</b><br/>" + _contact_lines(payload["payer"]), "body"),
            builder.paragraph("<b>Issued by</b><br/>" + _contact_lines(issuer_block), "body"),
        ]],
        colWidths=[builder.doc.width / 2, builder.doc.width / 2],
    )
    summary.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.append(summary)
    story.append(
        builder.meta_table(
            [
                ("Payment date", payload.get("payment_date") or "Not provided"),
                ("Method", payload.get("payment_method") or "Not provided"),
                ("Reference", payload.get("payment_reference") or "Not provided"),
                ("Received by", payload.get("received_by") or "Not provided"),
            ]
        )
    )
    rows = [[Paragraph("Received item", builder.styles["table_head"]), Paragraph("Amount", builder.styles["table_head"])]]
    total = 0.0
    for item in payload.get("receipt_items", []):
        total += float(item["amount"])
        rows.append(
            [
                builder.paragraph(item["label"], "table_body"),
                builder.paragraph(_currency_label(payload["currency"], float(item["amount"])), "table_body"),
            ]
        )
    story.extend([
        builder.paragraph("Receipt breakdown", "section"),
        builder.info_table(rows, [builder.doc.width * 0.7, builder.doc.width * 0.3], align_right_cols=[1]),
    ])
    totals = Table(
        [[builder.paragraph("Total received", "meta_label"), builder.paragraph(f"<b>{_currency_label(payload['currency'], total)}</b>", "meta_value")]],
        colWidths=[38 * mm, 50 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    story.extend([builder.spacer(3), totals])
    if payload.get("notes"):
        story.extend([builder.paragraph("Confirmation notes", "section"), builder.bullet_list(payload["notes"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_inspection_report(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, payload.get("inspection_type") or "")
    story.append(
        builder.meta_table(
            [
                ("Property", payload.get("property_title") or "Not provided"),
                ("Address", payload.get("property_address") or "Not provided"),
                ("Inspection date", payload.get("inspection_date") or "Not provided"),
                ("Inspected by", _contact_lines(payload.get("inspected_by") or {})),
                ("Inspected for", _contact_lines(payload.get("inspected_for") or {})),
            ]
        )
    )
    if payload.get("summary"):
        story.extend([builder.paragraph("Summary", "section"), builder.paragraph(payload["summary"])])
    for section in payload.get("sections", []):
        rows = [[
            Paragraph("Area", builder.styles["table_head"]),
            Paragraph("Condition", builder.styles["table_head"]),
            Paragraph("Status", builder.styles["table_head"]),
            Paragraph("Note", builder.styles["table_head"]),
        ]]
        rows.extend(
            [
                [
                    builder.paragraph(item["area"], "table_body"),
                    builder.paragraph(item["condition"], "table_body"),
                    builder.paragraph(item["status"], "table_body"),
                    builder.paragraph(item["note"], "table_body"),
                ]
                for item in section.get("observations", [])
            ]
        )
        story.extend([
            builder.paragraph(section.get("title") or "Inspection section", "section"),
            builder.info_table(rows, [builder.doc.width * 0.2, builder.doc.width * 0.18, builder.doc.width * 0.18, builder.doc.width * 0.44]),
        ])
    if payload.get("recommendations"):
        story.extend([builder.paragraph("Recommendations", "section"), builder.bullet_list(payload["recommendations"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_maintenance_work_order(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, "Maintenance work order")
    story.append(
        builder.meta_table(
            [
                ("Reference", payload.get("request_reference") or "Not provided"),
                ("Property", payload.get("property_title") or "Not provided"),
                ("Unit / area", payload.get("unit_reference") or "Not provided"),
                ("Vendor", _contact_lines(payload.get("vendor") or {})),
                ("Issued by", _contact_lines(payload.get("issued_by") or {})),
            ]
        )
    )
    if payload.get("issue_summary"):
        story.extend([builder.paragraph("Issue summary", "section"), builder.paragraph(payload["issue_summary"])])
    rows = [[
        Paragraph("Task", builder.styles["table_head"]),
        Paragraph("Priority", builder.styles["table_head"]),
        Paragraph("Materials", builder.styles["table_head"]),
        Paragraph("Execution note", builder.styles["table_head"]),
    ]]
    rows.extend(
        [
            [
                builder.paragraph(item["task"], "table_body"),
                builder.paragraph(item["priority"], "table_body"),
                builder.paragraph(item["materials"], "table_body"),
                builder.paragraph(item["note"], "table_body"),
            ]
            for item in payload.get("scope_items", [])
        ]
    )
    story.extend([
        builder.paragraph("Assigned scope", "section"),
        builder.info_table(rows, [builder.doc.width * 0.3, builder.doc.width * 0.14, builder.doc.width * 0.22, builder.doc.width * 0.34]),
    ])
    if payload.get("site_notes"):
        story.extend([builder.paragraph("Site access and instructions", "section"), builder.bullet_list(payload["site_notes"])])
    if payload.get("completion_requirements"):
        story.extend([builder.paragraph("Completion requirements", "section"), builder.bullet_list(payload["completion_requirements"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_lease_notice(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, payload.get("notice_type") or "Lease notice")
    story.append(
        builder.meta_table(
            [
                ("Tenant", _contact_lines(payload.get("tenant") or {})),
                ("Property", payload.get("property_title") or "Not provided"),
                ("Unit / area", payload.get("unit_reference") or "Not provided"),
                ("Current term end", payload.get("current_term_end") or "Not provided"),
                ("Proposed start", payload.get("proposed_start") or "Not provided"),
                ("Response deadline", payload.get("response_deadline") or "Not provided"),
            ]
        )
    )
    if payload.get("notice_reason"):
        story.extend(
            [
                builder.paragraph("Notice summary", "section"),
                builder.paragraph(payload["notice_reason"]),
            ]
        )
    story.extend([
        builder.paragraph("Proposed terms", "section"),
        builder.meta_table(
            [
                ("Current rent", payload.get("current_rent") or "Not provided"),
                ("Renewal / reviewed rent", payload.get("proposed_rent") or "Not provided"),
                ("Service charge note", payload.get("service_charge_note") or "Not provided"),
            ]
        ),
    ])
    if payload.get("key_terms"):
        story.extend([builder.paragraph("Key terms", "section"), builder.bullet_list(payload["key_terms"])])
    if payload.get("response_options"):
        story.extend([builder.paragraph("Response options", "section"), builder.bullet_list(payload["response_options"])])
    if payload.get("next_steps"):
        story.extend([builder.paragraph("Response instructions", "section"), builder.bullet_list(payload["next_steps"])])
    if payload.get("special_conditions"):
        story.extend([builder.paragraph("Special conditions", "section"), builder.bullet_list(payload["special_conditions"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_management_agreement(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, payload.get("property_title") or "Property management agreement")
    story.append(
        builder.meta_table(
            [
                ("Effective date", payload.get("effective_date") or "Not provided"),
                ("Owner", _contact_lines(payload.get("owner") or {})),
                ("Manager", _contact_lines(payload.get("manager") or {})),
                ("Property", payload.get("property_title") or "Not provided"),
                ("Property address", payload.get("property_address") or "Not provided"),
                ("Term summary", payload.get("term_summary") or "Not provided"),
            ]
        )
    )
    story.extend(
        [
            builder.paragraph("Agreement intent", "section"),
            builder.paragraph(
                f"This agreement records the appointment of {payload.get('manager', {}).get('name') or 'the manager'} "
                f"to oversee the day-to-day management of {payload.get('property_title') or 'the property'} on behalf of "
                f"{payload.get('owner', {}).get('name') or 'the owner'}, subject to the scope, reporting duties, fee schedule, "
                "authority limits, and termination terms stated below."
            ),
        ]
    )
    for section in payload.get("scope_sections", []):
        section_story = [builder.paragraph(section.get("title") or "Scope section", "section")]
        if section.get("items"):
            section_story.append(builder.bullet_list(section["items"]))
        story.append(KeepTogether(section_story))
    if payload.get("fee_schedule"):
        rows = [[Paragraph("Fee item", builder.styles["table_head"]), Paragraph("Value", builder.styles["table_head"])]]
        rows.extend(
            [
                [builder.paragraph(item["label"], "table_body"), builder.paragraph(item["value"], "table_body")]
                for item in payload["fee_schedule"]
            ]
        )
        story.extend([builder.paragraph("Fee schedule", "section"), builder.info_table(rows, [builder.doc.width * 0.62, builder.doc.width * 0.38], align_right_cols=[1])])
    story.extend(
        [
            builder.paragraph("Authority and reporting", "section"),
            builder.meta_table(
                [
                    ("Reporting cadence", payload.get("reporting_cadence") or "Not provided"),
                    ("Authority scope", "See authority limits below"),
                ]
            ),
        ]
    )
    if payload.get("authority_limits"):
        story.extend([builder.paragraph("Authority limits", "section"), builder.bullet_list(payload["authority_limits"])])
    if payload.get("service_standards"):
        story.extend([builder.paragraph("Service standards", "section"), builder.bullet_list(payload["service_standards"])])
    if payload.get("owner_obligations"):
        story.extend([builder.paragraph("Owner obligations", "section"), builder.bullet_list(payload["owner_obligations"])])
    if payload.get("manager_obligations"):
        story.extend([builder.paragraph("Manager obligations", "section"), builder.bullet_list(payload["manager_obligations"])])
    if payload.get("termination_events"):
        story.extend([builder.paragraph("Termination events", "section"), builder.bullet_list(payload["termination_events"])])
    if payload.get("special_conditions"):
        story.extend([builder.paragraph("Special conditions", "section"), builder.bullet_list(payload["special_conditions"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_tenancy_agreement(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, payload.get("property_title") or "Tenancy agreement")
    story.append(
        builder.meta_table(
            [
                ("Tenancy type", payload.get("tenancy_type") or "Not provided"),
                ("Landlord", _contact_lines(payload.get("landlord") or {})),
                ("Tenant", _contact_lines(payload.get("tenant") or {})),
                ("Property", payload.get("property_title") or "Not provided"),
                ("Premises", payload.get("premises_address") or "Not provided"),
                ("Commencement", payload.get("commencement_date") or "Not provided"),
                ("Expiry", payload.get("expiry_date") or "Not provided"),
            ]
        )
    )
    story.extend(
        [
            builder.paragraph("Agreement intent", "section"),
            builder.paragraph(
                f"This tenancy agreement sets out the occupation terms for {payload.get('property_title') or 'the premises'}, "
                f"including rent, deposit, permitted use, services, access, maintenance responsibilities, default events, and "
                "special conditions binding on both landlord and tenant."
            ),
        ]
    )
    story.extend([
        builder.paragraph("Commercial terms", "section"),
        builder.meta_table(
            [
                ("Rent", payload.get("rent_amount") or "Not provided"),
                ("Deposit", payload.get("deposit_amount") or "Not provided"),
                ("Payment schedule", payload.get("payment_schedule") or "Not provided"),
                ("Permitted use", payload.get("permitted_use") or "Not provided"),
            ]
        ),
    ])
    if payload.get("included_services"):
        story.extend([builder.paragraph("Included services", "section"), builder.bullet_list(payload["included_services"])])
    if payload.get("utilities_and_outgoings"):
        story.extend([builder.paragraph("Utilities and outgoings", "section"), builder.bullet_list(payload["utilities_and_outgoings"])])
    if payload.get("landlord_covenants"):
        story.extend([builder.paragraph("Landlord covenants", "section"), builder.bullet_list(payload["landlord_covenants"])])
    if payload.get("tenant_covenants"):
        story.extend([builder.paragraph("Tenant covenants", "section"), builder.bullet_list(payload["tenant_covenants"])])
    if payload.get("inspection_access"):
        story.extend([builder.paragraph("Inspection and access", "section"), builder.bullet_list(payload["inspection_access"])])
    if payload.get("house_rules"):
        story.extend([builder.paragraph("House rules", "section"), builder.bullet_list(payload["house_rules"])])
    if payload.get("inventory_schedule"):
        story.extend([builder.paragraph("Inventory and handover schedule", "section"), builder.bullet_list(payload["inventory_schedule"])])
    if payload.get("default_events"):
        story.extend([builder.paragraph("Default and remedies", "section"), builder.bullet_list(payload["default_events"])])
    if payload.get("special_conditions"):
        story.extend([builder.paragraph("Special conditions", "section"), builder.bullet_list(payload["special_conditions"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def _render_sale_agreement(builder: PremiumPdfBuilder, payload: dict[str, Any]) -> list[Any]:
    story = _document_header(builder, payload, builder.title, payload.get("property_title") or "Sale agreement")
    story.append(
        builder.meta_table(
            [
                ("Seller", _contact_lines(payload.get("seller") or {})),
                ("Buyer", _contact_lines(payload.get("buyer") or {})),
                ("Property", payload.get("property_title") or "Not provided"),
                ("Property address", payload.get("property_address") or "Not provided"),
                ("Interest being sold", payload.get("property_interest") or "Not provided"),
                ("Title status", payload.get("title_status") or "Not provided"),
                ("Completion date", payload.get("completion_date") or "Not provided"),
            ]
        )
    )
    story.extend(
        [
            builder.paragraph("Transaction intent", "section"),
            builder.paragraph(
                f"This agreement records the sale of {payload.get('property_title') or 'the property'} between the seller and "
                f"buyer, including price, deposit, title review, completion deliverables, transaction steps, tax/cost allocation, "
                "and remedies in the event of default."
            ),
        ]
    )
    story.extend([
        builder.paragraph("Commercial terms", "section"),
        builder.meta_table(
            [
                ("Purchase price", payload.get("purchase_price") or "Not provided"),
                ("Initial deposit", payload.get("deposit_amount") or "Not provided"),
                ("Completion notes", payload.get("completion_notes") or "Not provided"),
            ]
        ),
    ])
    if payload.get("title_documents"):
        story.extend([builder.paragraph("Title documents and due diligence pack", "section"), builder.bullet_list(payload["title_documents"])])
    if payload.get("conditions_precedent"):
        story.extend([builder.paragraph("Conditions precedent", "section"), builder.bullet_list(payload["conditions_precedent"])])
    if payload.get("completion_deliverables"):
        story.extend([builder.paragraph("Completion deliverables", "section"), builder.bullet_list(payload["completion_deliverables"])])
    if payload.get("transaction_steps"):
        rows = [[Paragraph("Step", builder.styles["table_head"]), Paragraph("Detail", builder.styles["table_head"])]]
        rows.extend(
            [
                [builder.paragraph(item["step"], "table_body"), builder.paragraph(item["detail"], "table_body")]
                for item in payload["transaction_steps"]
            ]
        )
        story.extend([builder.paragraph("Transaction steps", "section"), builder.info_table(rows, [builder.doc.width * 0.24, builder.doc.width * 0.76])])
    if payload.get("representations"):
        story.extend([builder.paragraph("Representations and warranties", "section"), builder.bullet_list(payload["representations"])])
    if payload.get("costs_and_taxes"):
        story.extend([builder.paragraph("Costs, taxes, and perfection expenses", "section"), builder.bullet_list(payload["costs_and_taxes"])])
    if payload.get("default_remedies"):
        story.extend([builder.paragraph("Default and remedies", "section"), builder.bullet_list(payload["default_remedies"])])
    if payload.get("signatories"):
        story.extend([builder.spacer(6), builder.signature_table(payload["signatories"])])
    return story


def render_document_pdf(template_key: str, title: str, payload: dict[str, Any], destination: Path, site_settings: dict[str, Any]) -> None:
    builder = PremiumPdfBuilder(destination=destination, title=title, payload=payload, site_settings=site_settings)
    if template_key == "letterhead":
        story = _render_letterhead(builder, payload)
    elif template_key == "billing":
        story = _render_billing(builder, payload)
    elif template_key == "proposal":
        story = _render_proposal(builder, payload)
    elif template_key == "discovery":
        story = _render_discovery(builder, payload)
    elif template_key == "delivery_checklist":
        story = _render_delivery_checklist(builder, payload)
    elif template_key == "payment_receipt":
        story = _render_payment_receipt(builder, payload)
    elif template_key == "inspection_report":
        story = _render_inspection_report(builder, payload)
    elif template_key == "maintenance_work_order":
        story = _render_maintenance_work_order(builder, payload)
    elif template_key == "lease_notice":
        story = _render_lease_notice(builder, payload)
    elif template_key == "management_agreement":
        story = _render_management_agreement(builder, payload)
    elif template_key == "tenancy_agreement":
        story = _render_tenancy_agreement(builder, payload)
    elif template_key == "sale_agreement":
        story = _render_sale_agreement(builder, payload)
    else:
        raise ValueError("Unsupported template key.")
    builder.build(story)
