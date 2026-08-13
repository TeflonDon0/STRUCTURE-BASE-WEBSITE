from __future__ import annotations

import re
from datetime import UTC, datetime


REFERRAL_STATUSES = ("VISITED", "LEAD_CREATED", "INSPECTION_REQUESTED", "CONVERTED", "EXPIRED")
REFERRAL_STATUS_LABELS = {
    "VISITED": "Visit captured",
    "LEAD_CREATED": "Lead created",
    "INSPECTION_REQUESTED": "Inspection requested",
    "CONVERTED": "Converted",
    "EXPIRED": "Expired",
}
REFERRAL_CODE_PATTERN = re.compile(r"^SB\d{6}$")


def normalize_referral_code(value: object) -> str:
    code = re.sub(r"\s+", "", str(value or "")).upper()
    return code if REFERRAL_CODE_PATTERN.fullmatch(code) else ""


def referral_scope(listing_id: object) -> str:
    listing = str(listing_id or "").strip()
    return f"property:{listing}" if listing else "general"


def parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def attribution_is_active(expires_at: object, now: datetime | None = None) -> bool:
    expiry = parse_utc(expires_at)
    return bool(expiry and expiry > (now or datetime.now(UTC)))
