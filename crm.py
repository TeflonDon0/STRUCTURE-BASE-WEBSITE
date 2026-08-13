from __future__ import annotations

import re
from datetime import date
from typing import Mapping


LEAD_STAGES = (
    "NEW",
    "CONTACTED",
    "QUALIFIED",
    "INSPECTION_SCHEDULED",
    "INSPECTION_COMPLETED",
    "NEGOTIATION",
    "DEPOSIT_PAID",
    "CLOSED_WON",
    "CLOSED_LOST",
    "ARCHIVED",
)
LEAD_STAGE_LABELS = {
    "NEW": "New",
    "CONTACTED": "Contacted",
    "QUALIFIED": "Qualified",
    "INSPECTION_SCHEDULED": "Inspection scheduled",
    "INSPECTION_COMPLETED": "Inspection completed",
    "NEGOTIATION": "Negotiation",
    "DEPOSIT_PAID": "Deposit paid",
    "CLOSED_WON": "Closed won",
    "CLOSED_LOST": "Closed lost",
    "ARCHIVED": "Archived",
}
LEGACY_LEAD_STAGE_MAP = {
    "New": "NEW",
    "Qualified": "QUALIFIED",
    "Viewing Scheduled": "INSPECTION_SCHEDULED",
    "Negotiating": "NEGOTIATION",
    "Won": "CLOSED_WON",
    "Lost": "CLOSED_LOST",
    "Handled": "ARCHIVED",
}
CLOSED_LEAD_STAGES = frozenset({"CLOSED_WON", "CLOSED_LOST", "ARCHIVED"})

LEAD_SOURCE_LABELS = {
    "WEBSITE": "Website enquiry",
    "WEBSITE_INSPECTION": "Website inspection",
    "WHATSAPP": "WhatsApp",
    "PHONE": "Phone",
    "PARTNER": "Partner",
    "WALK_IN": "Walk-in",
    "SOCIAL": "Social media",
    "OTHER": "Other",
}
LEAD_SOURCES = tuple(LEAD_SOURCE_LABELS)

INSPECTION_STATUSES = (
    "REQUESTED",
    "CONFIRMED",
    "RESCHEDULED",
    "COMPLETED",
    "CANCELLED",
    "NO_SHOW",
)
INSPECTION_STATUS_LABELS = {
    "REQUESTED": "Requested",
    "CONFIRMED": "Confirmed",
    "RESCHEDULED": "Rescheduled",
    "COMPLETED": "Completed",
    "CANCELLED": "Cancelled",
    "NO_SHOW": "No-show",
}

_STAGE_RANK = {stage: index for index, stage in enumerate(LEAD_STAGES)}
_PHONE_DIGITS = re.compile(r"\D+")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def canonical_lead_stage(value: object) -> str:
    text = str(value or "").strip()
    if text in LEAD_STAGES:
        return text
    return LEGACY_LEAD_STAGE_MAP.get(text, "NEW")


def lead_stage_label(value: object) -> str:
    return LEAD_STAGE_LABELS[canonical_lead_stage(value)]


def normalize_contact_email(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_contact_phone(value: object) -> str:
    digits = _PHONE_DIGITS.sub("", str(value or ""))
    if digits.startswith("0") and len(digits) == 11:
        return "234" + digits[1:]
    return digits


def validate_inspection_request(
    form: Mapping[str, object], *, listing_id: str, listing_title: str, today: date | None = None
) -> tuple[dict[str, str], list[str]]:
    data = {
        "listing_id": listing_id,
        "listing_title": listing_title,
        "name": str(form.get("name") or "").strip(),
        "email": str(form.get("email") or "").strip(),
        "phone": str(form.get("phone") or "").strip(),
        "requested_date": str(form.get("requested_date") or "").strip(),
        "requested_time": str(form.get("requested_time") or "").strip(),
        "notes": str(form.get("notes") or "").strip(),
        "source_path": str(form.get("source_path") or "").strip(),
    }
    errors: list[str] = []
    if len(data["name"]) < 2:
        errors.append("Enter your full name.")
    elif len(data["name"]) > 100:
        errors.append("Name must not exceed 100 characters.")
    if not data["email"] and not data["phone"]:
        errors.append("Add an email address or phone number so the team can confirm the inspection.")
    if data["email"] and (len(data["email"]) > 254 or not _EMAIL.fullmatch(data["email"])):
        errors.append("Enter a valid email address.")
    if data["phone"] and len(normalize_contact_phone(data["phone"])) < 7:
        errors.append("Enter a valid phone number.")
    if len(data["notes"]) > 1000:
        errors.append("Inspection notes must not exceed 1,000 characters.")
    try:
        requested = date.fromisoformat(data["requested_date"])
        if requested < (today or date.today()):
            errors.append("Choose today or a future date for the inspection.")
    except ValueError:
        errors.append("Choose a valid inspection date.")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", data["requested_time"]):
        errors.append("Choose a valid inspection time.")
    return data, errors


def advanced_lead_stage(current: object, inspection_status: object) -> str:
    current_stage = canonical_lead_stage(current)
    target = {
        "CONFIRMED": "INSPECTION_SCHEDULED",
        "RESCHEDULED": "INSPECTION_SCHEDULED",
        "COMPLETED": "INSPECTION_COMPLETED",
    }.get(str(inspection_status or "").strip().upper())
    if target and _STAGE_RANK[current_stage] < _STAGE_RANK[target]:
        return target
    return current_stage
