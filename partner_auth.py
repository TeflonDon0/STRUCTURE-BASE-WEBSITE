from __future__ import annotations

import re
from collections.abc import Mapping

from staff_auth import normalize_email, validate_password


PARTNER_STATUSES = ("PENDING", "APPROVED", "SUSPENDED", "REJECTED")
PARTNER_STATUS_LABELS = {
    "PENDING": "Pending review",
    "APPROVED": "Approved",
    "SUSPENDED": "Suspended",
    "REJECTED": "Rejected",
}
PARTNER_TYPES = ("INDIVIDUAL", "COMPANY")
PARTNER_TYPE_LABELS = {"INDIVIDUAL": "Individual", "COMPANY": "Company"}
PARTNER_SECTIONS = (
    "overview",
    "properties",
    "links",
    "leads",
    "deals",
    "commissions",
    "payouts",
    "materials",
    "profile",
)

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE = re.compile(r"\D+")


def normalize_partner_phone(value: object) -> str:
    digits = _PHONE.sub("", str(value or ""))
    if digits.startswith("0") and len(digits) == 11:
        return "234" + digits[1:]
    return digits


def validate_partner_registration(form: Mapping[str, object]) -> tuple[dict[str, str], list[str]]:
    data = {
        "full_name": " ".join(str(form.get("full_name") or "").split()),
        "email": normalize_email(str(form.get("email") or "")),
        "phone": str(form.get("phone") or "").strip(),
        "whatsapp": str(form.get("whatsapp") or "").strip(),
        "location": " ".join(str(form.get("location") or "").split()),
        "partner_type": str(form.get("partner_type") or "INDIVIDUAL").strip().upper(),
        "company_name": " ".join(str(form.get("company_name") or "").split()),
        "experience_notes": str(form.get("experience_notes") or "").strip(),
        "referral_source": " ".join(str(form.get("referral_source") or "").split()),
    }
    errors: list[str] = []
    if not 2 <= len(data["full_name"]) <= 100:
        errors.append("Enter your full name.")
    if len(data["email"]) > 254 or not _EMAIL.fullmatch(data["email"]):
        errors.append("Enter a valid email address.")
    if not 7 <= len(normalize_partner_phone(data["phone"])) <= 15:
        errors.append("Enter a valid phone number.")
    if data["whatsapp"] and not 7 <= len(normalize_partner_phone(data["whatsapp"])) <= 15:
        errors.append("Enter a valid WhatsApp number.")
    if not 2 <= len(data["location"]) <= 100:
        errors.append("Enter your city or location.")
    if data["partner_type"] not in PARTNER_TYPES:
        errors.append("Choose whether you are registering as an individual or company.")
    if data["partner_type"] == "COMPANY" and not 2 <= len(data["company_name"]) <= 120:
        errors.append("Enter the company name.")
    if len(data["experience_notes"]) > 1500:
        errors.append("Experience notes must not exceed 1,500 characters.")
    if len(data["referral_source"]) > 120:
        errors.append("Referral source must not exceed 120 characters.")
    return data, errors


def validate_partner_password(password: str, confirmation: str, data: Mapping[str, str]) -> list[str]:
    errors = validate_password(
        password,
        personal_values=(data.get("full_name", ""), data.get("email", ""), data.get("company_name", "")),
    )
    if password != confirmation:
        errors.append("Password confirmation does not match.")
    return errors
