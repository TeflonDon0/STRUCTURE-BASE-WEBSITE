from __future__ import annotations

from typing import Mapping


PARTNER_MARKETING_EVENT_TYPES = (
    "LINK_COPIED",
    "SHARE_INITIATED",
    "WHATSAPP_SHARE",
    "MEDIA_DOWNLOADED",
)
PARTNER_MARKETING_EVENT_LABELS = {
    "LINK_COPIED": "Referral link copied",
    "SHARE_INITIATED": "Share initiated",
    "WHATSAPP_SHARE": "WhatsApp share initiated",
    "MEDIA_DOWNLOADED": "Marketing media downloaded",
}
MARKETING_ASSET_TYPES = ("IMAGE", "BROCHURE", "DOCUMENT", "VIDEO")
MARKETING_ASSET_TYPE_LABELS = {
    "IMAGE": "Image",
    "BROCHURE": "Brochure",
    "DOCUMENT": "Document",
    "VIDEO": "Video",
}


def marketing_share_message(listing: Mapping[str, object], referral_url: str, formatted_price: str) -> str:
    title = str(listing.get("title") or "Property opportunity").strip()
    district = str(listing.get("district") or "Nigeria").strip()
    selling_point = str(listing.get("summary") or "").strip()
    if len(selling_point) > 180:
        selling_point = f"{selling_point[:177].rstrip()}..."
    lines = [title, district, formatted_price]
    if selling_point:
        lines.append(selling_point)
    lines.extend(("View full details and enquire:", referral_url))
    return "\n".join(lines)


def normalize_marketing_event_type(value: object) -> str:
    event_type = str(value or "").strip().upper()
    return event_type if event_type in PARTNER_MARKETING_EVENT_TYPES else ""
