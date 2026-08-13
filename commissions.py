from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping


COMMISSION_CALCULATION_TYPES = ("PERCENTAGE", "FIXED")
COMMISSION_CALCULATION_LABELS = {
    "PERCENTAGE": "Percentage",
    "FIXED": "Fixed amount",
}
COMMISSION_SCOPE_TYPES = ("DEFAULT", "PROPERTY", "CAMPAIGN", "PARTNER")
COMMISSION_SCOPE_LABELS = {
    "DEFAULT": "Default",
    "PROPERTY": "Property-specific",
    "CAMPAIGN": "Campaign / special",
    "PARTNER": "Partner override",
}
COMMISSION_STATUSES = (
    "POTENTIAL", "PENDING", "EARNED", "APPROVED", "PAID", "REJECTED", "CANCELLED",
)
COMMISSION_STATUS_LABELS = {
    "POTENTIAL": "Potential",
    "PENDING": "Pending",
    "EARNED": "Earned",
    "APPROVED": "Approved",
    "PAID": "Paid",
    "REJECTED": "Rejected",
    "CANCELLED": "Cancelled",
}
COMMISSION_TRANSITIONS = {
    "POTENTIAL": frozenset({"PENDING", "EARNED", "CANCELLED"}),
    "PENDING": frozenset({"EARNED", "CANCELLED"}),
    "EARNED": frozenset({"APPROVED", "REJECTED", "CANCELLED"}),
    "APPROVED": frozenset({"PAID"}),
    "PAID": frozenset(),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
}

_HUNDRED = Decimal("100")
_TEN_THOUSAND = Decimal("10000")


def decimal_money_to_minor(value: object, *, allow_zero: bool = False) -> int:
    text = str(value or "").strip().replace(",", "")
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid monetary amount.") from None
    if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError("Amount must be greater than zero." if not allow_zero else "Amount cannot be negative.")
    return int((amount * _HUNDRED).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def signed_money_to_minor(value: object) -> int:
    text = str(value or "").strip().replace(",", "")
    try:
        amount = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid adjustment amount.") from None
    if not amount.is_finite():
        raise ValueError("Enter a valid adjustment amount.")
    return int((amount * _HUNDRED).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def minor_to_major(minor: object) -> Decimal:
    return (Decimal(int(minor or 0)) / _HUNDRED).quantize(Decimal("0.01"))


def percentage_to_basis_points(value: object) -> int:
    text = str(value or "").strip().replace("%", "")
    try:
        percentage = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid percentage.") from None
    if not percentage.is_finite() or percentage <= 0 or percentage > 100:
        raise ValueError("Percentage must be greater than 0 and no more than 100.")
    return int((percentage * _HUNDRED).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_commission_minor(
    sale_value_minor: int, *, calculation_type: str, percentage_bps: int = 0, fixed_amount_minor: int = 0
) -> int:
    if int(sale_value_minor) <= 0:
        raise ValueError("Sale value must be greater than zero.")
    if calculation_type == "PERCENTAGE":
        if percentage_bps <= 0 or percentage_bps > 10000:
            raise ValueError("Percentage basis points are outside the allowed range.")
        return int(
            (Decimal(int(sale_value_minor)) * Decimal(int(percentage_bps)) / _TEN_THOUSAND)
            .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    if calculation_type == "FIXED":
        if fixed_amount_minor <= 0:
            raise ValueError("Fixed commission must be greater than zero.")
        return int(fixed_amount_minor)
    raise ValueError("Unsupported commission calculation type.")


def rule_is_effective(rule: Mapping[str, object], on_date: date | None = None) -> bool:
    if not bool(rule.get("active")):
        return False
    target = on_date or datetime.now(UTC).date()
    try:
        valid_from = date.fromisoformat(str(rule.get("valid_from") or "")) if rule.get("valid_from") else None
        valid_until = date.fromisoformat(str(rule.get("valid_until") or "")) if rule.get("valid_until") else None
    except ValueError:
        return False
    return not ((valid_from and target < valid_from) or (valid_until and target > valid_until))


def rule_matches(
    rule: Mapping[str, object], *, property_id: str, partner_id: str, campaign_id: str = "", on_date: date | None = None
) -> bool:
    if not rule_is_effective(rule, on_date):
        return False
    scope = str(rule.get("scope_type") or "DEFAULT")
    if scope == "PROPERTY":
        return bool(property_id and str(rule.get("property_id") or "") == property_id)
    if scope == "PARTNER":
        return bool(partner_id and str(rule.get("partner_id") or "") == partner_id)
    if scope == "CAMPAIGN":
        return bool(campaign_id and str(rule.get("campaign_id") or "") == campaign_id)
    return scope == "DEFAULT"


def rule_sort_key(rule: Mapping[str, object]) -> tuple[int, int, str]:
    specificity = {"PARTNER": 4, "CAMPAIGN": 3, "PROPERTY": 2, "DEFAULT": 1}
    return (
        int(rule.get("priority") or 0),
        specificity.get(str(rule.get("scope_type") or "DEFAULT"), 0),
        str(rule.get("created_at") or ""),
    )


def target_status_for_lead_stage(stage: object) -> str:
    return {
        "NEGOTIATION": "POTENTIAL",
        "DEPOSIT_PAID": "PENDING",
        "CLOSED_WON": "EARNED",
        "CLOSED_LOST": "CANCELLED",
        "ARCHIVED": "CANCELLED",
    }.get(str(stage or "").strip().upper(), "")


def transition_is_allowed(current: object, target: object) -> bool:
    return str(target or "").upper() in COMMISSION_TRANSITIONS.get(str(current or "").upper(), frozenset())
