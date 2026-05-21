from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from flask import render_template


STATIC_DIR = Path(__file__).resolve().parent / "static"


def _absolute_url(base_url: str, path: str) -> str:
    root = base_url.rstrip("/")
    if not root:
        return path
    return f"{root}{path}"


def _logo_url(base_url: str) -> str:
    logo_path = STATIC_DIR / "images" / "LOGO2-email.png"
    if not logo_path.exists():
        return ""
    return _absolute_url(base_url, "/static/images/LOGO2-email.png")


def _brand_context(site_settings: dict[str, Any], base_url: str) -> dict[str, Any]:
    return {
        "site_name": str(site_settings.get("site_name") or "Structurebase"),
        "office_address": str(site_settings.get("office_address") or "Lagos, Nigeria"),
        "contact_email": str(site_settings.get("contact_email") or ""),
        "contact_phone_display": str(site_settings.get("contact_phone_display") or ""),
        "coverage_area": str(site_settings.get("coverage_area") or ""),
        "footer_summary": str(site_settings.get("footer_summary") or ""),
        "email_sender_name": str(
            site_settings.get("email_sender_name") or site_settings.get("site_name") or "Structurebase"
        ),
        "brand_tagline": str(
            site_settings.get("email_brand_tagline") or "Property sales, rentals, and operations support"
        ),
        "brand_market_line": str(
            site_settings.get("email_brand_market_line") or "Based in Lagos, active across Nigeria"
        ),
        "email_footer_note": str(
            site_settings.get("email_footer_note")
            or site_settings.get("footer_summary")
            or ""
        ),
        "logo_url": _logo_url(base_url),
        "brand": {
            "primary": "#7b3327",
            "accent": "#a16f36",
            "text": "#182028",
            "muted": "#4f5656",
            "line": "#d9ccbe",
            "surface": "#fffdf9",
            "background": "#f4eee6",
            "success": "#2f6b4f",
            "warning": "#8f5b1f",
        },
    }


def communication_template_catalog(site_settings: dict[str, Any], base_url: str = "") -> dict[str, dict[str, Any]]:
    brand = _brand_context(site_settings, base_url)
    site_name = brand["site_name"]
    return {
        "enquiry_receipt": {
            "label": "Enquiry Receipt",
            "description": "Customer-facing acknowledgement for property enquiries with reply expectations and a direct route back to the listing.",
            "sample_payload": {
                "greeting_line": "Hello Amaka,",
                "reference": "ENQ-2026-041",
                "listing_title": "Ikoyi Skyline Penthouse",
                "listing_price": "NGN 850,000,000",
                "preferred_contact": "WhatsApp",
                "reply_line": "+234 800 123 4567",
                "message_excerpt": "Please share viewing availability, service-charge details, and any current negotiation context.",
                "response_window": "A member of the team will review this and respond within one business day.",
                "cta_label": "View listing",
                "cta_url": _absolute_url(base_url, "/properties/ikoyi-skyline-penthouse"),
            },
        },
        "admin_enquiry_notification": {
            "label": "Admin Enquiry Notification",
            "description": "Internal notification for new enquiries with contact details, source context, and a direct queue action.",
            "sample_payload": {
                "reference": "ENQ-2026-041",
                "sender_name": "Amaka Okafor",
                "sender_email": "amaka@example.com",
                "sender_phone": "+234 800 123 4567",
                "preferred_contact": "WhatsApp",
                "listing_title": "Ikoyi Skyline Penthouse",
                "source_label": "Property detail page",
                "message_excerpt": "Please share viewing availability, service-charge details, and any current negotiation context.",
                "cta_label": "Open lead queue",
                "cta_url": _absolute_url(base_url, "/dashboard/enquiries"),
            },
        },
        "maintenance_receipt": {
            "label": "Maintenance Receipt",
            "description": "Customer-facing maintenance acknowledgement with request reference, issue summary, next steps, and escalation guidance.",
            "sample_payload": {
                "recipient_name": "Daniel Aina",
                "ticket_reference": "MNT-2026-014",
                "issue_category": "Power Backup",
                "priority": "High",
                "property_title": "Harbour Gate Apartments",
                "unit_reference": "Flat B2",
                "contact_line": "+234 800 123 4567",
                "response_window": "The operations desk will triage this request and confirm the next action window shortly.",
                "is_emergency": False,
                "cta_label": "Open tenant services",
                "cta_url": _absolute_url(base_url, "/tenant-services"),
                "escalation_url": _absolute_url(base_url, "/tenant-services"),
            },
        },
    }


def communication_template_choices(site_settings: dict[str, Any], base_url: str = "") -> list[tuple[str, str]]:
    return [(key, value["label"]) for key, value in communication_template_catalog(site_settings, base_url).items()]


def communication_sample_payload(template_key: str, site_settings: dict[str, Any], base_url: str = "") -> dict[str, Any]:
    catalog = communication_template_catalog(site_settings, base_url)
    if template_key not in catalog:
        raise KeyError(template_key)
    return copy.deepcopy(catalog[template_key]["sample_payload"])


def _template_subject(template_key: str, payload: dict[str, Any], site_settings: dict[str, Any]) -> str:
    site_name = str(site_settings.get("site_name") or "Structurebase")
    if template_key == "enquiry_receipt":
        return f"We received your enquiry for {payload.get('listing_title') or 'the listing'}"
    if template_key == "admin_enquiry_notification":
        reference = str(payload.get("reference") or "").strip()
        listing_title = payload.get("listing_title") or "listing"
        return (
            f"New enquiry for {listing_title} | {reference}"
            if reference
            else f"New enquiry for {listing_title}"
        )
    if template_key == "maintenance_receipt":
        ticket_reference = str(payload.get("ticket_reference") or "").strip()
        return (
            f"We received your maintenance request {ticket_reference}"
            if ticket_reference
            else "We received your maintenance request"
        )
    return f"{site_name} communication"


def _template_preheader(template_key: str, payload: dict[str, Any]) -> str:
    if template_key == "enquiry_receipt":
        return (
            f"Reference {payload.get('reference') or ''}. "
            f"{payload.get('response_window') or ''}"
        ).strip()
    if template_key == "admin_enquiry_notification":
        return (
            f"{payload.get('sender_name') or 'A client'} sent a new enquiry. "
            f"Reference {payload.get('reference') or ''}. "
            f"Preferred contact: {payload.get('preferred_contact') or 'Not set'}."
        ).strip()
    if template_key == "maintenance_receipt":
        return (
            f"Reference {payload.get('ticket_reference') or ''}. "
            f"Priority: {payload.get('priority') or 'Standard'}."
        ).strip()
    return ""


def _template_support_intro(template_key: str) -> str:
    if template_key == "enquiry_receipt":
        return "Need to add detail before the team replies? Contact"
    if template_key == "maintenance_receipt":
        return "Need to add access details or recent history? Contact"
    if template_key == "admin_enquiry_notification":
        return "Team contact:"
    return ""


def _template_recipient_reason(template_key: str) -> str:
    if template_key == "enquiry_receipt":
        return "You are receiving this email because an enquiry was submitted on Structurebase."
    if template_key == "maintenance_receipt":
        return "You are receiving this email because a maintenance request was submitted on Structurebase."
    if template_key == "admin_enquiry_notification":
        return "This is an internal notification generated from a new website enquiry."
    return ""


def render_communication_template(
    template_key: str,
    payload: dict[str, Any],
    site_settings: dict[str, Any],
    *,
    base_url: str = "",
    logo_cid: str = "",
) -> dict[str, str]:
    catalog = communication_template_catalog(site_settings, base_url)
    if template_key not in catalog:
        raise KeyError(template_key)

    brand_context = _brand_context(site_settings, base_url)
    subject = _template_subject(template_key, payload, site_settings)
    preheader = _template_preheader(template_key, payload)
    context = {
        "payload": payload,
        "subject": subject,
        "preheader": preheader,
        "logo_cid": logo_cid,
        "support_intro": _template_support_intro(template_key),
        "recipient_reason": _template_recipient_reason(template_key),
        "site_settings": site_settings,
        **brand_context,
    }
    body_html = render_template(f"communications/{template_key}.html", **context)
    html = render_template("communications/email_shell.html", body_html=body_html, **context)
    text = render_template(f"communications/{template_key}.txt", **context)
    return {
        "subject": subject,
        "preheader": preheader,
        "body_html": body_html,
        "html": html,
        "text": text,
        "label": catalog[template_key]["label"],
        "description": catalog[template_key]["description"],
    }
