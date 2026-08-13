from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence

from crm import LEAD_SOURCE_LABELS, LEAD_SOURCES, LEAD_STAGE_LABELS, LEAD_STAGES


ACTIVE_DEAL_STAGES = frozenset(
    {
        "QUALIFIED",
        "INSPECTION_SCHEDULED",
        "INSPECTION_COMPLETED",
        "NEGOTIATION",
        "DEPOSIT_PAID",
    }
)
CLOSED_LEAD_STAGES = frozenset({"CLOSED_WON", "CLOSED_LOST", "ARCHIVED"})
PENDING_COMMISSION_STATUSES = frozenset({"POTENTIAL", "PENDING", "EARNED", "APPROVED"})
EARNED_COMMISSION_STATUSES = frozenset({"EARNED", "APPROVED", "PAID"})
COMPLETED_PROPERTY_STATUSES = frozenset({"Sold", "Rented", "Leased"})


def _text(record: Mapping[str, object], key: str) -> str:
    return str(record.get(key) or "").strip()


def _integer(record: Mapping[str, object], key: str) -> int:
    try:
        return int(record.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def build_business_analytics(
    *,
    listings: Sequence[Mapping[str, object]] = (),
    leads: Sequence[Mapping[str, object]] = (),
    inspections: Sequence[Mapping[str, object]] = (),
    partners: Sequence[Mapping[str, object]] = (),
    referrals: Sequence[Mapping[str, object]] = (),
    commissions: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Create a read-only analytics projection from normalized application records.

    The caller controls which record groups are supplied, so permission checks stay
    at the route boundary and no unauthorized domain is queried or exposed.
    """

    lead_counts = Counter(_text(item, "status") or "NEW" for item in leads)
    source_counts = Counter(_text(item, "source") or "OTHER" for item in leads)
    inspection_counts = Counter(_text(item, "status") or "REQUESTED" for item in inspections)
    partner_counts = Counter(_text(item, "status") or "PENDING" for item in partners)
    commission_counts = Counter(_text(item, "status") or "POTENTIAL" for item in commissions)

    leads_by_listing: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    inspections_by_listing: Counter[str] = Counter()
    referrals_by_listing: Counter[str] = Counter()
    referral_visits_by_listing: Counter[str] = Counter()
    for lead in leads:
        listing_id = _text(lead, "listing_id")
        if listing_id:
            leads_by_listing[listing_id].append(lead)
    for inspection in inspections:
        listing_id = _text(inspection, "listing_id")
        if listing_id:
            inspections_by_listing[listing_id] += 1
    for referral in referrals:
        listing_id = _text(referral, "listing_id")
        if listing_id:
            referrals_by_listing[listing_id] += 1
            referral_visits_by_listing[listing_id] += _integer(referral, "visit_count")

    property_performance: list[dict[str, object]] = []
    for listing in listings:
        listing_id = _text(listing, "id") or _text(listing, "public_id")
        listing_leads = leads_by_listing.get(listing_id, [])
        enquiries = len(listing_leads)
        successful_deals = sum(1 for item in listing_leads if _text(item, "status") == "CLOSED_WON")
        referral_leads = sum(1 for item in listing_leads if _text(item, "partner_id"))
        views = _integer(listing, "view_count")
        inspection_total = inspections_by_listing[listing_id]
        property_performance.append(
            {
                "id": listing_id,
                "title": _text(listing, "title") or "Untitled property",
                "district": _text(listing, "district") or "Location not set",
                "availability": _text(listing, "availability") or "Available",
                "published": bool(listing.get("published")),
                "views": views,
                "enquiries": enquiries,
                "inspections": inspection_total,
                "referral_leads": referral_leads,
                "referral_visits": referral_visits_by_listing[listing_id],
                "successful_deals": successful_deals,
                "engagement": enquiries + inspection_total + referral_leads,
            }
        )
    property_performance.sort(
        key=lambda item: (
            int(item["successful_deals"]),
            int(item["inspections"]),
            int(item["enquiries"]),
            int(item["views"]),
        ),
        reverse=True,
    )

    leads_by_partner: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    inspections_by_partner: Counter[str] = Counter()
    referral_links_by_partner: Counter[str] = Counter()
    referral_visits_by_partner: Counter[str] = Counter()
    commissions_by_partner: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for lead in leads:
        partner_id = _text(lead, "partner_id")
        if partner_id:
            leads_by_partner[partner_id].append(lead)
    for inspection in inspections:
        partner_id = _text(inspection, "partner_id")
        if partner_id:
            inspections_by_partner[partner_id] += 1
    for referral in referrals:
        partner_id = _text(referral, "partner_id")
        if partner_id:
            referral_links_by_partner[partner_id] += 1
            referral_visits_by_partner[partner_id] += _integer(referral, "visit_count")
    for commission in commissions:
        partner_id = _text(commission, "partner_id")
        if partner_id:
            commissions_by_partner[partner_id].append(commission)

    partner_performance: list[dict[str, object]] = []
    for partner in partners:
        partner_id = _text(partner, "id") or _text(partner, "public_id")
        partner_leads = leads_by_partner.get(partner_id, [])
        partner_commissions = commissions_by_partner.get(partner_id, [])
        partner_performance.append(
            {
                "id": partner_id,
                "name": _text(partner, "full_name") or "Unnamed partner",
                "code": _text(partner, "partner_code"),
                "status": _text(partner, "status") or "PENDING",
                "referral_links": referral_links_by_partner[partner_id],
                "referral_visits": referral_visits_by_partner[partner_id],
                "leads": len(partner_leads),
                "inspections": inspections_by_partner[partner_id],
                "active_deals": sum(
                    1 for item in partner_leads if _text(item, "status") in ACTIVE_DEAL_STAGES
                ),
                "closed_deals": sum(
                    1 for item in partner_leads if _text(item, "status") == "CLOSED_WON"
                ),
                "earned_commission": sum(
                    _integer(item, "final_amount")
                    for item in partner_commissions
                    if _text(item, "status") in EARNED_COMMISSION_STATUSES
                ),
                "paid_commission": sum(
                    _integer(item, "final_amount")
                    for item in partner_commissions
                    if _text(item, "status") == "PAID"
                ),
            }
        )
    partner_performance.sort(
        key=lambda item: (
            int(item["closed_deals"]),
            int(item["active_deals"]),
            int(item["leads"]),
            int(item["referral_visits"]),
        ),
        reverse=True,
    )

    pipeline = [
        {
            "status": stage,
            "label": LEAD_STAGE_LABELS[stage],
            "count": lead_counts[stage],
            "share": round((lead_counts[stage] / len(leads)) * 100) if leads else 0,
        }
        for stage in LEAD_STAGES
        if lead_counts[stage]
    ]
    sources = [
        {
            "source": source,
            "label": LEAD_SOURCE_LABELS[source],
            "count": source_counts[source],
            "closed_deals": sum(
                1
                for lead in leads
                if _text(lead, "source") == source and _text(lead, "status") == "CLOSED_WON"
            ),
        }
        for source in LEAD_SOURCES
        if source_counts[source]
    ]
    sources.sort(key=lambda item: (int(item["closed_deals"]), int(item["count"])), reverse=True)

    pending_commissions = [
        item for item in commissions if _text(item, "status") in PENDING_COMMISSION_STATUSES
    ]
    paid_commissions = [item for item in commissions if _text(item, "status") == "PAID"]
    completed_inspections = inspection_counts["COMPLETED"]

    return {
        "summary": {
            "total_properties": len(listings),
            "available_properties": sum(
                1 for item in listings if _text(item, "availability") == "Available"
            ),
            "reserved_properties": sum(
                1 for item in listings if _text(item, "availability") == "Under Offer"
            ),
            "completed_properties": sum(
                1 for item in listings if _text(item, "availability") in COMPLETED_PROPERTY_STATUSES
            ),
            "new_leads": lead_counts["NEW"],
            "active_leads": sum(
                count for status, count in lead_counts.items() if status not in CLOSED_LEAD_STAGES
            ),
            "inspection_requests": len(inspections),
            "completed_inspections": completed_inspections,
            "pending_partners": partner_counts["PENDING"],
            "approved_partners": partner_counts["APPROVED"],
            "active_deals": sum(lead_counts[status] for status in ACTIVE_DEAL_STAGES),
            "closed_sales": lead_counts["CLOSED_WON"],
            "pending_commissions": len(pending_commissions),
            "pending_commission_value": sum(_integer(item, "final_amount") for item in pending_commissions),
            "paid_commissions": len(paid_commissions),
            "paid_commission_value": sum(_integer(item, "final_amount") for item in paid_commissions),
        },
        "pipeline": pipeline,
        "sources": sources,
        "property_performance": property_performance,
        "partner_performance": partner_performance,
        "commission_counts": dict(commission_counts),
    }
