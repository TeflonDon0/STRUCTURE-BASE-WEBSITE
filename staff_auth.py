from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from werkzeug.security import check_password_hash, generate_password_hash


ROLE_LABELS = {
    "SUPER_ADMIN": "Super admin",
    "ADMIN": "Administrator",
    "PROPERTY_MANAGER": "Property manager",
    "SALES_MANAGER": "Sales manager",
    "MARKETING_MANAGER": "Marketing manager",
    "FINANCE_MANAGER": "Finance manager",
}
ROLE_OPTIONS = tuple(ROLE_LABELS)
STAFF_STATUS_OPTIONS = ("ACTIVE", "DISABLED")

ALL_PERMISSIONS = frozenset(
    {
        "dashboard.view",
        "properties.view",
        "properties.create",
        "properties.edit",
        "properties.delete",
        "leads.view",
        "leads.manage",
        "customers.view",
        "customers.manage",
        "inspections.view",
        "inspections.manage",
        "maintenance.view",
        "maintenance.manage",
        "finance.view",
        "finance.manage",
        "documents.view",
        "documents.manage",
        "partners.view",
        "partners.approve",
        "referrals.view",
        "commissions.view",
        "commissions.manage",
        "commissions.approve",
        "commissions.mark_paid",
        "staff.view",
        "staff.invite",
        "staff.edit",
        "staff.disable",
        "content.manage",
        "analytics.view",
        "settings.manage",
        "audit_logs.view",
        "data.export",
    }
)

ROLE_PERMISSIONS = {
    "SUPER_ADMIN": ALL_PERMISSIONS,
    "ADMIN": frozenset(
        permission
        for permission in ALL_PERMISSIONS
        if permission not in {"staff.invite", "staff.edit", "staff.disable"}
    ),
    "PROPERTY_MANAGER": frozenset(
        {
            "dashboard.view",
            "properties.view",
            "properties.create",
            "properties.edit",
            "inspections.view",
            "inspections.manage",
            "maintenance.view",
            "maintenance.manage",
            "documents.view",
            "documents.manage",
            "analytics.view",
        }
    ),
    "SALES_MANAGER": frozenset(
        {
            "dashboard.view",
            "properties.view",
            "leads.view",
            "leads.manage",
            "customers.view",
            "customers.manage",
            "inspections.view",
            "inspections.manage",
            "partners.view",
            "referrals.view",
            "analytics.view",
        }
    ),
    "MARKETING_MANAGER": frozenset(
        {
            "dashboard.view",
            "properties.view",
            "partners.view",
            "referrals.view",
            "content.manage",
            "analytics.view",
        }
    ),
    "FINANCE_MANAGER": frozenset(
        {
            "dashboard.view",
            "finance.view",
            "finance.manage",
            "documents.view",
            "commissions.view",
            "commissions.manage",
            "commissions.approve",
            "commissions.mark_paid",
            "analytics.view",
        }
    ),
}

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_username(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def role_label(role: str) -> str:
    return ROLE_LABELS.get(str(role or "").strip().upper(), "Staff")


def permissions_for_role(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(str(role or "").strip().upper(), frozenset())


def role_has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for_role(role)


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False
    return check_password_hash(password_hash, password)


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def validate_staff_identity(full_name: str, email: str, username: str = "") -> list[str]:
    errors: list[str] = []
    cleaned_name = " ".join(str(full_name or "").split())
    cleaned_email = normalize_email(email)
    cleaned_username = normalize_username(username)
    if len(cleaned_name) < 2 or len(cleaned_name) > 100:
        errors.append("Enter the staff member's full name.")
    if not EMAIL_PATTERN.fullmatch(cleaned_email) or len(cleaned_email) > 254:
        errors.append("Enter a valid staff email address.")
    if username and not USERNAME_PATTERN.fullmatch(cleaned_username):
        errors.append("Username must be 3 to 40 characters using letters, numbers, dots, dashes, or underscores.")
    return errors


def validate_password(password: str, *, personal_values: Iterable[str] = ()) -> list[str]:
    errors: list[str] = []
    if len(password) < 12:
        errors.append("Password must contain at least 12 characters.")
    if len(password) > 128:
        errors.append("Password must not exceed 128 characters.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errors.append("Password must include at least one letter and one number.")
    lowered = password.lower()
    for value in personal_values:
        candidate = re.sub(r"[^a-z0-9]", "", str(value or "").lower())
        if len(candidate) >= 4 and candidate in re.sub(r"[^a-z0-9]", "", lowered):
            errors.append("Password must not contain your name, email, or username.")
            break
    return errors
