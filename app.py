from __future__ import annotations

import copy
import hashlib
import hmac
import io
import json
import logging
import math
import mimetypes
import os
import re
import secrets
import smtplib
import sqlite3
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from functools import lru_cache, wraps
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from xml.sax.saxutils import escape as xml_escape

# Prevent Cloudinary import failure if CLOUDINARY_URL is set but invalid.
_cloudinary_url_env = os.environ.get("CLOUDINARY_URL", "").strip()
if _cloudinary_url_env and not _cloudinary_url_env.startswith("cloudinary://"):
    os.environ.pop("CLOUDINARY_URL", None)

import cloudinary
import cloudinary.uploader
from analytics import build_business_analytics
from communication_templates import (
    communication_sample_payload,
    communication_template_choices,
    render_communication_template,
)
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from cloudinary.exceptions import Error as CloudinaryError
from cloudinary.utils import cloudinary_url
from commissions import (
    COMMISSION_CALCULATION_LABELS,
    COMMISSION_CALCULATION_TYPES,
    COMMISSION_SCOPE_LABELS,
    COMMISSION_SCOPE_TYPES,
    COMMISSION_STATUS_LABELS,
    COMMISSION_STATUSES,
    calculate_commission_minor,
    decimal_money_to_minor,
    minor_to_major,
    percentage_to_basis_points,
    rule_matches,
    rule_sort_key,
    signed_money_to_minor,
    target_status_for_lead_stage,
    transition_is_allowed,
)
from crm import (
    CLOSED_LEAD_STAGES,
    INSPECTION_STATUSES,
    INSPECTION_STATUS_LABELS,
    LEAD_SOURCES,
    LEAD_SOURCE_LABELS,
    LEAD_STAGES,
    LEAD_STAGE_LABELS,
    advanced_lead_stage,
    canonical_lead_stage,
    lead_stage_label,
    normalize_contact_email,
    normalize_contact_phone,
    validate_inspection_request,
)
from document_generation import (
    DOCUMENT_TEMPLATE_VERSION,
    document_generator_catalog,
    generator_spec,
    render_document_pdf,
    sample_payload_json,
    template_document_type,
    template_options,
    validate_generator_payload,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from partner_auth import (
    PARTNER_SECTIONS,
    PARTNER_STATUSES,
    PARTNER_STATUS_LABELS,
    PARTNER_TYPES,
    PARTNER_TYPE_LABELS,
    normalize_partner_phone,
    validate_partner_password,
    validate_partner_registration,
)
from marketing import (
    MARKETING_ASSET_TYPE_LABELS,
    PARTNER_MARKETING_EVENT_LABELS,
    PARTNER_MARKETING_EVENT_TYPES,
    marketing_share_message,
    normalize_marketing_event_type,
)
from referrals import (
    REFERRAL_STATUSES,
    REFERRAL_STATUS_LABELS,
    attribution_is_active,
    normalize_referral_code,
    referral_scope,
)
from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from itsdangerous import BadSignature, URLSafeSerializer
from security_helpers import (
    admin_return_target as _admin_return_target,
    client_ip as _client_ip,
    is_default_admin_password as _is_default_admin_password,
    safe_redirect_target as _safe_redirect_target,
)
from staff_auth import (
    ALL_PERMISSIONS,
    ROLE_LABELS,
    ROLE_OPTIONS,
    STAFF_STATUS_OPTIONS,
    hash_invitation_token,
    hash_password,
    normalize_email as normalize_staff_email,
    normalize_username,
    permissions_for_role,
    role_has_permission,
    role_label,
    validate_password,
    validate_staff_identity,
    verify_password,
)
from werkzeug.exceptions import NotFound, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "structurebase.db"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = STATIC_DIR / "uploads"
DOCUMENTS_DIR = BASE_DIR / "data" / "documents"
load_dotenv(BASE_DIR / ".env")
EMAIL_LOGO_PATH = STATIC_DIR / "images" / "LOGO2-email.png"

# Prevent Cloudinary initialization errors on startup if CLOUDINARY_URL is missing
# by clearing invalid URLs from environment before Cloudinary config is accessed
_cloudinary_url_env = os.environ.get("CLOUDINARY_URL", "").strip()
if _cloudinary_url_env and not _cloudinary_url_env.startswith("cloudinary://"):
    # Remove invalid CLOUDINARY_URL to prevent import-time errors
    os.environ.pop("CLOUDINARY_URL", None)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp"}
STATUS_OPTIONS = ("For Sale", "For Rent", "For Lease")
AVAILABILITY_OPTIONS = ("Available", "Under Offer", "Sold", "Rented", "Leased", "Off Market")
COMPLETED_AVAILABILITY_OPTIONS = ("Sold", "Rented", "Leased")
SALE_AVAILABILITY_OPTIONS = {"Available", "Under Offer", "Sold", "Off Market"}
RENT_AVAILABILITY_OPTIONS = {"Available", "Under Offer", "Rented", "Off Market"}
LEASE_AVAILABILITY_OPTIONS = {"Available", "Under Offer", "Leased", "Off Market"}
PRICE_SUFFIX_OPTIONS = ("", "/ year", "/ month")
ENQUIRY_CONTACT_OPTIONS = ("Email", "Phone", "WhatsApp")
ENQUIRY_STATUS_OPTIONS = LEAD_STAGES
DISCOVERY_FEATURE_FIELDS = (
    ("is_serviced", "Serviced"),
    ("has_power_24_7", "24/7 Power"),
    ("is_flood_free", "Flood-free zone"),
    ("near_express", "Near express"),
    ("near_schools", "Near schools"),
    ("near_markets", "Near markets"),
)
VERIFICATION_FIELDS = (
    ("verified_property", "Property vetted"),
    ("verified_landlord", "Landlord vetted"),
)
MAINTENANCE_CATEGORY_OPTIONS = (
    "Electrical",
    "Power Backup",
    "Plumbing",
    "Water Supply",
    "Cooling",
    "Security",
    "Gate / Access",
    "Internet / Cable",
    "Cleaning",
    "Common Area",
    "Structural",
    "Other",
)
MAINTENANCE_PRIORITY_OPTIONS = ("Low", "Medium", "High", "Emergency")
MAINTENANCE_STATUS_OPTIONS = ("New", "Assigned", "In Progress", "Resolved")
FINANCIAL_CHARGE_OPTIONS = (
    "Rent",
    "Service Charge",
    "Utility",
    "Diesel Contribution",
    "Prepaid Meter Token",
    "Other",
)
FINANCIAL_STATUS_OPTIONS = ("Due", "Part Paid", "Paid", "Overdue")
CLOSED_ENQUIRY_STATUSES = CLOSED_LEAD_STAGES
OPEN_MAINTENANCE_STATUSES = {"New", "Assigned", "In Progress"}
ACTIONABLE_FINANCE_STATUSES = {"Due", "Overdue", "Part Paid"}
DOCUMENT_TYPE_OPTIONS = (
    "Tenancy Agreement",
    "Receipt",
    "KYC",
    "Invoice",
    "Proposal",
    "Discovery Questionnaire",
    "Delivery Checklist",
    "Letterhead",
    "Inspection Report",
    "Work Order",
    "Lease Renewal Notice",
    "Property Management Agreement",
    "Sale Agreement",
    "Other",
)
DOCUMENT_SOURCE_OPTIONS = ("upload", "generated")
DOCUMENT_STATUS_OPTIONS = ("Final", "Filed")
VIEW_DEDUP_WINDOW_SECONDS = 6 * 60 * 60
SITE_SETTING_FIELDS = (
    "site_name",
    "contact_email",
    "contact_phone_display",
    "contact_phone_raw",
    "whatsapp_phone",
    "office_address",
    "coverage_area",
    "footer_summary",
    "email_sender_name",
    "email_brand_tagline",
    "email_brand_market_line",
    "email_footer_note",
    "homepage_hero_heading",
    "homepage_hero_intro",
    "homepage_primary_cta",
    "homepage_secondary_cta",
    "homepage_trust_signal_1",
    "homepage_trust_signal_2",
    "homepage_trust_signal_3",
)
LISTING_SAVED_VIEWS = (
    ("all", "All inventory"),
    ("drafts", "Drafts"),
    ("published", "Published"),
    ("featured", "Featured"),
    ("under_offer", "Under offer"),
    ("off_market", "Off market"),
    ("most_viewed", "Most viewed"),
    ("verified", "Verified stock"),
)
ENQUIRY_SORT_OPTIONS = (
    ("newest", "Newest first"),
    ("oldest", "Oldest first"),
    ("follow_up", "Follow-up date"),
    ("status", "Status"),
)
MAINTENANCE_SORT_OPTIONS = (
    ("newest", "Newest first"),
    ("updated", "Recently updated"),
    ("priority", "Priority"),
    ("status", "Status"),
)
FINANCIAL_SORT_OPTIONS = (
    ("due_asc", "Due date"),
    ("due_desc", "Latest due date"),
    ("amount_desc", "Highest amount"),
    ("status", "Status"),
)
DOCUMENT_SORT_OPTIONS = (
    ("newest", "Newest first"),
    ("oldest", "Oldest first"),
    ("title", "Title A-Z"),
    ("type", "Document type"),
)
LISTING_BULK_ACTION_OPTIONS = (
    ("publish", "Publish selected"),
    ("unpublish", "Move selected to draft"),
    ("feature", "Mark selected as featured"),
    ("unfeature", "Remove selected from featured"),
    ("availability_available", "Mark selected as available"),
    ("availability_under_offer", "Mark selected as under offer"),
    ("availability_off_market", "Mark selected as off market"),
)

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "change-me-structurebase"
DEFAULT_SECRET_KEY = "change-this-before-deploying"
DEFAULT_CONTACT_EMAIL = "info@structurebase.com"
DEFAULT_PHONE_DISPLAY = "+234 800 123 4567"
DEFAULT_PHONE_RAW = "+2348001234567"
DEFAULT_WHATSAPP_PHONE = "2348001234567"
DEFAULT_SITE_NAME = "Structurebase"
DEFAULT_OFFICE_ADDRESS = "Lagos, Nigeria"
DEFAULT_COVERAGE_AREA = "Lagos, Abuja, Port Harcourt, and selected markets across Nigeria"
DEFAULT_FOOTER_SUMMARY = (
    "Property listings, enquiries, and operations support from a team based in Lagos and active across Nigeria."
)
DEFAULT_EMAIL_SENDER_NAME = DEFAULT_SITE_NAME
DEFAULT_EMAIL_BRAND_TAGLINE = "Property sales, rentals, and operations support"
DEFAULT_EMAIL_BRAND_MARKET_LINE = "Based in Lagos, active across Nigeria"
DEFAULT_EMAIL_FOOTER_NOTE = "Client communications from a Lagos-based team active across Nigeria."
DEFAULT_HOMEPAGE_HERO_HEADING = "Verified property options. Clear next steps."
LEGACY_HOMEPAGE_HERO_HEADING = "Find verified property options. Move with clear guidance."
DEFAULT_HOMEPAGE_HERO_INTRO = (
    "For buyers, renters, landlords, and investors who need current listings, clear pricing, and direct advisor follow-up across Lagos and selected Nigerian markets."
)
LEGACY_HOMEPAGE_HERO_INTRO = (
    "Curated listings and advisor support for buyers, renters, landlords, and investors in Lagos and selected Nigerian markets."
)
DEFAULT_HOMEPAGE_PRIMARY_CTA = "Browse live listings"
DEFAULT_HOMEPAGE_SECONDARY_CTA = "Talk to an advisor"
DEFAULT_HOMEPAGE_TRUST_SIGNAL_1 = "Availability checked"
DEFAULT_HOMEPAGE_TRUST_SIGNAL_2 = "Pricing context included"
DEFAULT_HOMEPAGE_TRUST_SIGNAL_3 = "Advisor follow-up"
LEGACY_HOMEPAGE_TRUST_SIGNAL_1 = "Verified availability checks"
LEGACY_HOMEPAGE_TRUST_SIGNAL_2 = "Clear pricing and district context"
LEGACY_HOMEPAGE_TRUST_SIGNAL_3 = "Direct advisor follow-up"
DEFAULT_MAP_CENTER = (3.3792, 6.5244)
DISTRICT_CENTER_COORDINATES: dict[str, tuple[float, float]] = {
    "ikoyi": (3.4476, 6.4549),
    "banana island": (3.4267, 6.4446),
    "victoria island": (3.4219, 6.4281),
    "lekki phase 1": (3.4739, 6.4477),
    "lekki": (3.5026, 6.4367),
    "ajah": (3.5855, 6.4698),
    "yaba": (3.3797, 6.5158),
    "surulere": (3.3539, 6.5016),
    "ikeja": (3.3420, 6.6018),
    "maryland": (3.3678, 6.5695),
}


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("STRUCTUREBASE_SECRET", DEFAULT_SECRET_KEY),
    DATABASE=str(DATABASE_PATH),
    ENVIRONMENT=(
        os.environ.get("STRUCTUREBASE_ENV", "production" if os.environ.get("RENDER") else "development")
        .strip()
        .lower()
    ),
    DATABASE_BACKEND=os.environ.get("STRUCTUREBASE_DATABASE_BACKEND", "auto").strip().lower(),
    MONGODB_URI=os.environ.get("STRUCTUREBASE_MONGODB_URI", "").strip(),
    MONGODB_DB_NAME=os.environ.get("STRUCTUREBASE_MONGODB_DB_NAME", "structurebase").strip(),
    MONGODB_COLLECTION=os.environ.get("STRUCTUREBASE_MONGODB_COLLECTION", "listings").strip(),
    MONGODB_ENQUIRIES_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_ENQUIRIES_COLLECTION", "enquiries"
    ).strip(),
    MONGODB_CONTACTS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_CONTACTS_COLLECTION", "contacts"
    ).strip(),
    MONGODB_LEAD_NOTES_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_LEAD_NOTES_COLLECTION", "lead_notes"
    ).strip(),
    MONGODB_INSPECTIONS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_INSPECTIONS_COLLECTION", "inspections"
    ).strip(),
    MONGODB_PARTNERS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_PARTNERS_COLLECTION", "partners"
    ).strip(),
    MONGODB_REFERRALS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_REFERRALS_COLLECTION", "referrals"
    ).strip(),
    MONGODB_REFERRAL_EVENTS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_REFERRAL_EVENTS_COLLECTION", "referral_events"
    ).strip(),
    MONGODB_COMMISSION_RULES_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_COMMISSION_RULES_COLLECTION", "commission_rules"
    ).strip(),
    MONGODB_COMMISSIONS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_COMMISSIONS_COLLECTION", "commissions"
    ).strip(),
    MONGODB_MARKETING_ASSETS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_MARKETING_ASSETS_COLLECTION", "marketing_assets"
    ).strip(),
    MONGODB_PARTNER_MARKETING_EVENTS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_PARTNER_MARKETING_EVENTS_COLLECTION", "partner_marketing_events"
    ).strip(),
    REFERRAL_ATTRIBUTION_DAYS=max(1, int(os.environ.get("STRUCTUREBASE_REFERRAL_ATTRIBUTION_DAYS", "30"))),
    MONGODB_ACTIVITY_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_ACTIVITY_COLLECTION", "activity_log"
    ).strip(),
    MONGODB_MAINTENANCE_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_MAINTENANCE_COLLECTION", "maintenance_tickets"
    ).strip(),
    MONGODB_FINANCIAL_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_FINANCIAL_COLLECTION", "financial_records"
    ).strip(),
    MONGODB_DOCUMENT_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_DOCUMENT_COLLECTION", "documents"
    ).strip(),
    MONGODB_SETTINGS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_SETTINGS_COLLECTION", "site_preferences"
    ).strip(),
    MONGODB_STAFF_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_STAFF_COLLECTION", "staff_users"
    ).strip(),
    MONGODB_STAFF_INVITATIONS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_STAFF_INVITATIONS_COLLECTION", "staff_invitations"
    ).strip(),
    MONGODB_LOGIN_ATTEMPTS_COLLECTION=os.environ.get(
        "STRUCTUREBASE_MONGODB_LOGIN_ATTEMPTS_COLLECTION", "staff_login_attempts"
    ).strip(),
    UPLOAD_FOLDER=str(UPLOAD_DIR),
    STORAGE_BACKEND=os.environ.get("STRUCTUREBASE_STORAGE_BACKEND", "auto").strip().lower(),
    CLOUDINARY_URL=os.environ.get("CLOUDINARY_URL", "").strip(),
    CLOUDINARY_CLOUD_NAME=(
        os.environ.get("STRUCTUREBASE_CLOUDINARY_CLOUD_NAME", "")
        or os.environ.get("STRUCTUREBASE_R2_ACCOUNT_ID", "")
    ).strip(),
    CLOUDINARY_API_KEY=(
        os.environ.get("STRUCTUREBASE_CLOUDINARY_API_KEY", "")
        or os.environ.get("STRUCTUREBASE_R2_ACCESS_KEY_ID", "")
    ).strip(),
    CLOUDINARY_API_SECRET=(
        os.environ.get("STRUCTUREBASE_CLOUDINARY_API_SECRET", "")
        or os.environ.get("STRUCTUREBASE_R2_SECRET_ACCESS_KEY", "")
    ).strip(),
    CLOUDINARY_FOLDER=(
        os.environ.get("STRUCTUREBASE_CLOUDINARY_FOLDER", "")
        or os.environ.get("STRUCTUREBASE_R2_BUCKET_NAME", "")
        or "structurebase/listings"
    ).strip().strip("/"),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    ADMIN_USERNAME=os.environ.get("STRUCTUREBASE_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME).strip(),
    ADMIN_PASSWORD=os.environ.get("STRUCTUREBASE_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD).strip(),
    ADMIN_PASSWORD_HASH=os.environ.get("STRUCTUREBASE_ADMIN_PASSWORD_HASH", "").strip(),
    CONTACT_EMAIL=os.environ.get("STRUCTUREBASE_CONTACT_EMAIL", DEFAULT_CONTACT_EMAIL),
    CONTACT_PHONE_DISPLAY=os.environ.get("STRUCTUREBASE_CONTACT_PHONE", DEFAULT_PHONE_DISPLAY),
    CONTACT_PHONE_RAW=os.environ.get("STRUCTUREBASE_CONTACT_PHONE_RAW", DEFAULT_PHONE_RAW),
    WHATSAPP_PHONE=os.environ.get("STRUCTUREBASE_WHATSAPP_PHONE", DEFAULT_WHATSAPP_PHONE),
    SITE_NAME=os.environ.get("STRUCTUREBASE_SITE_NAME", DEFAULT_SITE_NAME),
    PUBLIC_BASE_URL=os.environ.get("STRUCTUREBASE_PUBLIC_BASE_URL", "").strip().rstrip("/"),
    SEARCH_INDEXING_ENABLED=os.environ.get("STRUCTUREBASE_SEARCH_INDEXING_ENABLED", "").strip().lower()
    in {"1", "true", "yes", "on"},
    OFFICE_ADDRESS=os.environ.get("STRUCTUREBASE_OFFICE_ADDRESS", DEFAULT_OFFICE_ADDRESS),
    COVERAGE_AREA=os.environ.get("STRUCTUREBASE_COVERAGE_AREA", DEFAULT_COVERAGE_AREA),
    FOOTER_SUMMARY=os.environ.get("STRUCTUREBASE_FOOTER_SUMMARY", DEFAULT_FOOTER_SUMMARY),
    EMAIL_SENDER_NAME=os.environ.get(
        "STRUCTUREBASE_EMAIL_SENDER_NAME",
        DEFAULT_EMAIL_SENDER_NAME,
    ).strip(),
    EMAIL_BRAND_TAGLINE=os.environ.get(
        "STRUCTUREBASE_EMAIL_BRAND_TAGLINE",
        DEFAULT_EMAIL_BRAND_TAGLINE,
    ).strip(),
    EMAIL_BRAND_MARKET_LINE=os.environ.get(
        "STRUCTUREBASE_EMAIL_BRAND_MARKET_LINE",
        DEFAULT_EMAIL_BRAND_MARKET_LINE,
    ).strip(),
    EMAIL_FOOTER_NOTE=os.environ.get(
        "STRUCTUREBASE_EMAIL_FOOTER_NOTE",
        DEFAULT_EMAIL_FOOTER_NOTE,
    ).strip(),
    HOMEPAGE_HERO_HEADING=os.environ.get(
        "STRUCTUREBASE_HOMEPAGE_HERO_HEADING",
        DEFAULT_HOMEPAGE_HERO_HEADING,
    ).strip(),
    HOMEPAGE_HERO_INTRO=os.environ.get(
        "STRUCTUREBASE_HOMEPAGE_HERO_INTRO",
        DEFAULT_HOMEPAGE_HERO_INTRO,
    ).strip(),
    HOMEPAGE_PRIMARY_CTA=os.environ.get(
        "STRUCTUREBASE_HOMEPAGE_PRIMARY_CTA",
        DEFAULT_HOMEPAGE_PRIMARY_CTA,
    ).strip(),
    HOMEPAGE_SECONDARY_CTA=os.environ.get(
        "STRUCTUREBASE_HOMEPAGE_SECONDARY_CTA",
        DEFAULT_HOMEPAGE_SECONDARY_CTA,
    ).strip(),
    HOMEPAGE_TRUST_SIGNAL_1=os.environ.get(
        "STRUCTUREBASE_HOMEPAGE_TRUST_SIGNAL_1",
        DEFAULT_HOMEPAGE_TRUST_SIGNAL_1,
    ).strip(),
    HOMEPAGE_TRUST_SIGNAL_2=os.environ.get(
        "STRUCTUREBASE_HOMEPAGE_TRUST_SIGNAL_2",
        DEFAULT_HOMEPAGE_TRUST_SIGNAL_2,
    ).strip(),
    HOMEPAGE_TRUST_SIGNAL_3=os.environ.get(
        "STRUCTUREBASE_HOMEPAGE_TRUST_SIGNAL_3",
        DEFAULT_HOMEPAGE_TRUST_SIGNAL_3,
    ).strip(),
    SMTP_HOST=os.environ.get("STRUCTUREBASE_SMTP_HOST", "").strip(),
    SMTP_PORT=max(1, int(os.environ.get("STRUCTUREBASE_SMTP_PORT", "587"))),
    SMTP_USERNAME=os.environ.get("STRUCTUREBASE_SMTP_USERNAME", "").strip(),
    SMTP_PASSWORD=os.environ.get("STRUCTUREBASE_SMTP_PASSWORD", ""),
    SMTP_FROM_EMAIL=os.environ.get("STRUCTUREBASE_SMTP_FROM_EMAIL", "").strip(),
    MAPBOX_TOKEN=os.environ.get("STRUCTUREBASE_MAPBOX_TOKEN", "YOUR_MAPBOX_TOKEN_HERE").strip()
    or "YOUR_MAPBOX_TOKEN_HERE",
    TRUST_PROXY_COUNT=max(
        0,
        int(
            os.environ.get(
                "STRUCTUREBASE_TRUST_PROXY_COUNT",
                "1" if os.environ.get("RENDER") else "0",
            )
        ),
    ),
    LOG_LEVEL=os.environ.get("STRUCTUREBASE_LOG_LEVEL", "INFO").strip().upper() or "INFO",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("STRUCTUREBASE_SESSION_COOKIE_SECURE", "").strip().lower()
    in {"1", "true", "yes", "on"},
    PERMANENT_SESSION_LIFETIME=timedelta(
        hours=max(1, int(os.environ.get("STRUCTUREBASE_SESSION_HOURS", "12")))
    ),
    LOGIN_MAX_ATTEMPTS=max(1, int(os.environ.get("STRUCTUREBASE_LOGIN_MAX_ATTEMPTS", "5"))),
    LOGIN_WINDOW_SECONDS=max(60, int(os.environ.get("STRUCTUREBASE_LOGIN_WINDOW_MINUTES", "15")) * 60),
    STAFF_INVITATION_HOURS=max(
        1,
        int(os.environ.get("STRUCTUREBASE_STAFF_INVITATION_HOURS", "48")),
    ),
)

app.config["IS_PRODUCTION"] = app.config["ENVIRONMENT"] in {"production", "prod"}
app.config["STRICT_STARTUP_CHECKS"] = (
    os.environ.get("STRUCTUREBASE_STRICT_STARTUP_CHECKS", "").strip().lower() in {"1", "true", "yes", "on"}
    or app.config["IS_PRODUCTION"]
)
app.config["PREFERRED_URL_SCHEME"] = "https" if app.config["IS_PRODUCTION"] else "http"
app.config["TEMPLATES_AUTO_RELOAD"] = not app.config["IS_PRODUCTION"]
app.jinja_env.auto_reload = app.config["TEMPLATES_AUTO_RELOAD"]

if app.config["TRUST_PROXY_COUNT"] > 0:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=app.config["TRUST_PROXY_COUNT"],
        x_proto=app.config["TRUST_PROXY_COUNT"],
        x_host=app.config["TRUST_PROXY_COUNT"],
        x_port=app.config["TRUST_PROXY_COUNT"],
        x_prefix=app.config["TRUST_PROXY_COUNT"],
    )


LISTING_SORT = [("featured", DESCENDING), ("updated_at", DESCENDING), ("created_at", DESCENDING)]
PUBLIC_LISTING_SORT_OPTIONS = (
    ("recommended", "Recommended"),
    ("newest", "Recently updated"),
    ("price_asc", "Price: low to high"),
    ("price_desc", "Price: high to low"),
)
PUBLIC_LISTING_SORT_DEFINITIONS = {
    "recommended": LISTING_SORT,
    "newest": [("updated_at", DESCENDING), ("created_at", DESCENDING)],
    "price_asc": [("price", ASCENDING), ("updated_at", DESCENDING)],
    "price_desc": [("price", DESCENDING), ("updated_at", DESCENDING)],
}
PUBLIC_LISTING_SORT_SQL = {
    "recommended": "featured DESC, updated_at DESC, created_at DESC",
    "newest": "updated_at DESC, created_at DESC",
    "price_asc": "price ASC, updated_at DESC",
    "price_desc": "price DESC, updated_at DESC",
}
DASHBOARD_SORT = [("updated_at", DESCENDING), ("created_at", DESCENDING)]
DASHBOARD_SORT_OPTIONS = (
    ("updated_desc", "Recently updated"),
    ("created_desc", "Newest first"),
    ("price_desc", "Highest price"),
    ("price_asc", "Lowest price"),
    ("views_desc", "Most viewed"),
    ("district_asc", "District A-Z"),
)
DASHBOARD_SORT_DEFINITIONS = {
    "updated_desc": [("updated_at", DESCENDING), ("created_at", DESCENDING)],
    "created_desc": [("created_at", DESCENDING)],
    "price_desc": [("price", DESCENDING), ("updated_at", DESCENDING)],
    "price_asc": [("price", ASCENDING), ("updated_at", DESCENDING)],
    "views_desc": [("view_count", DESCENDING), ("updated_at", DESCENDING)],
    "district_asc": [("district", ASCENDING), ("updated_at", DESCENDING)],
}
DASHBOARD_SORT_SQL = {
    "updated_desc": "updated_at DESC, created_at DESC",
    "created_desc": "created_at DESC",
    "price_desc": "price DESC, updated_at DESC",
    "price_asc": "price ASC, updated_at DESC",
    "views_desc": "view_count DESC, updated_at DESC",
    "district_asc": "district ASC, updated_at DESC",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_valid_mongodb_uri(uri: str) -> bool:
    uri = uri.strip()
    return uri.startswith("mongodb://") or uri.startswith("mongodb+srv://")


def is_placeholder_mongodb_uri(uri: str) -> bool:
    lowered = uri.strip().lower()
    placeholder_tokens = (
        "username:password",
        "db_username",
        "db_password",
        "your-cluster.mongodb.net",
        "cluster.mongodb.net",
        "replace-with",
        "<username>",
        "<password>",
    )
    return any(token in lowered for token in placeholder_tokens)


def is_placeholder_cloudinary_value(value: str) -> bool:
    lowered = value.strip().lower()
    placeholder_tokens = (
        "api_key",
        "api-secret",
        "api_secret",
        "cloud_name",
        "cloud-name",
        "cloudinary://api_key:",
        "@cloud_name",
        "@cloud-name",
        "your-cloud-name",
        "your-cloudinary-api-key",
        "your-cloudinary-api-secret",
        "replace-with",
    )
    return any(token in lowered for token in placeholder_tokens)


def database_backend() -> str:
    configured = app.config["DATABASE_BACKEND"]
    if configured == "sqlite":
        return "sqlite"
    if configured == "mongodb":
        return "mongodb"
    return "mongodb" if is_valid_mongodb_uri(app.config["MONGODB_URI"]) else "sqlite"


def cloudinary_is_configured() -> bool:
    if app.config["CLOUDINARY_URL"]:
        return True
    return all(
        [
            app.config["CLOUDINARY_CLOUD_NAME"],
            app.config["CLOUDINARY_API_KEY"],
            app.config["CLOUDINARY_API_SECRET"],
        ]
    )


def storage_backend() -> str:
    configured = app.config["STORAGE_BACKEND"]
    if configured in {"cloudinary", "r2"} and cloudinary_is_configured():
        return "cloudinary"
    if configured == "local":
        return "local"
    return "cloudinary" if cloudinary_is_configured() else "local"


def configure_logging() -> None:
    level_name = str(app.config.get("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    else:
        root_logger.setLevel(level)

    app.logger.setLevel(level)


def sample_listings() -> list[dict[str, object]]:
    now = utc_now_iso()
    listings = [
        {
            "public_id": "ikoyi-skyline-penthouse",
            "title": "Ikoyi Skyline Penthouse",
            "status": "For Sale",
            "availability": "Available",
            "property_type": "Penthouse",
            "district": "Ikoyi",
            "address": "Bourdillon Road, Ikoyi, Lagos",
            "longitude": 3.4476,
            "latitude": 6.4549,
            "gallery_paths": [
                "images/ikoyi-penthouse-sample.webp",
                "images/building1.jpg",
                "images/building2.webp",
            ],
            "virtual_tour_url": "https://my.matterport.com/show/?m=fRGL4VSosLW",
            "is_serviced": 1,
            "has_power_24_7": 1,
            "is_flood_free": 1,
            "near_express": 1,
            "near_schools": 1,
            "near_markets": 0,
            "verified_property": 1,
            "verified_landlord": 1,
            "price": 850000000,
            "price_suffix": "",
            "bedrooms": 4,
            "bathrooms": 5,
            "area_sqm": 480,
            "summary": "Top-floor residence with private terraces, staff quarters, and guarded access in one of Lagos's strongest premium districts.",
            "description": "This penthouse is suited to buyers who want a flagship Lagos residence with privacy, entertaining space, and central reach to Ikoyi and Victoria Island. The floor plan allows for large family living, guest hosting, and executive use without compromising security or circulation.",
            "image_path": "images/ikoyi-penthouse-sample.webp",
            "featured": 1,
            "published": 1,
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        },
        {
            "public_id": "lekki-phase-1-detached-villa",
            "title": "Lekki Phase 1 Detached Villa",
            "status": "For Sale",
            "availability": "Available",
            "property_type": "Detached House",
            "district": "Lekki Phase 1",
            "address": "Freedom Way Axis, Lekki Phase 1, Lagos",
            "longitude": 3.4739,
            "latitude": 6.4477,
            "gallery_paths": [
                "images/lekki-villa-sample.webp",
                "images/building2.webp",
                "images/building1.jpg",
            ],
            "virtual_tour_url": "",
            "is_serviced": 1,
            "has_power_24_7": 1,
            "is_flood_free": 1,
            "near_express": 1,
            "near_schools": 1,
            "near_markets": 1,
            "verified_property": 1,
            "verified_landlord": 0,
            "price": 450000000,
            "price_suffix": "",
            "bedrooms": 5,
            "bathrooms": 5,
            "area_sqm": 620,
            "summary": "Family-scale detached villa positioned for owner-occupiers and investors who want strong demand in Lekki's core residential market.",
            "description": "The property combines ample living space, modern finishes, parking capacity, and reliable neighborhood access. It works well for clients seeking a long-hold Lagos family home or a premium residential investment in a high-demand district.",
            "image_path": "images/lekki-villa-sample.webp",
            "featured": 1,
            "published": 1,
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        },
        {
            "public_id": "victoria-island-office-suite",
            "title": "Victoria Island Office Suite",
            "status": "For Rent",
            "availability": "Available",
            "property_type": "Office",
            "district": "Victoria Island",
            "address": "Ozumba Mbadiwe Corridor, Victoria Island, Lagos",
            "longitude": 3.4219,
            "latitude": 6.4281,
            "gallery_paths": [
                "images/victoria-island-office-sample.webp",
                "images/building1.jpg",
            ],
            "virtual_tour_url": "",
            "is_serviced": 1,
            "has_power_24_7": 1,
            "is_flood_free": 1,
            "near_express": 1,
            "near_schools": 0,
            "near_markets": 1,
            "verified_property": 1,
            "verified_landlord": 1,
            "price": 65000000,
            "price_suffix": "/ year",
            "bedrooms": 0,
            "bathrooms": 4,
            "area_sqm": 740,
            "summary": "Commercial floorplate for firms that need brand visibility, executive access, and predictable business infrastructure.",
            "description": "This office suite suits companies looking for a Lagos address with strong client access and room for structured operations. The layout supports reception, executive offices, meeting rooms, and open work areas across a practical commercial footprint.",
            "image_path": "images/victoria-island-office-sample.webp",
            "featured": 1,
            "published": 1,
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        },
        {
            "public_id": "yaba-income-duplex",
            "title": "Yaba Income Duplex",
            "status": "For Lease",
            "availability": "Available",
            "property_type": "Duplex",
            "district": "Yaba",
            "address": "Commercial Avenue, Yaba, Lagos",
            "longitude": 3.3797,
            "latitude": 6.5158,
            "gallery_paths": [
                "images/yaba-duplex-sample.webp",
                "images/building2.webp",
            ],
            "virtual_tour_url": "",
            "is_serviced": 0,
            "has_power_24_7": 1,
            "is_flood_free": 1,
            "near_express": 1,
            "near_schools": 1,
            "near_markets": 1,
            "verified_property": 0,
            "verified_landlord": 0,
            "price": 18000000,
            "price_suffix": "/ year",
            "bedrooms": 4,
            "bathrooms": 4,
            "area_sqm": 300,
            "summary": "Rental duplex near business and education nodes, positioned for clients who need practical access without moving to the Island.",
            "description": "This Yaba duplex offers a good fit for tenants who want a balanced Lagos location with straightforward access to work, schools, and daily services. The layout supports family living, and the district remains attractive for steady rental demand.",
            "image_path": "images/yaba-duplex-sample.webp",
            "featured": 0,
            "published": 1,
            "view_count": 0,
            "created_at": now,
            "updated_at": now,
        },
    ]
    for listing in listings:
        listing.setdefault("documentation_summary", "")
        listing.setdefault("documentation_verified", 0)
        listing.setdefault("payment_plan_summary", "")
    return listings


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        g.db = connection
    return g.db


def get_mongo_client() -> MongoClient:
    client = app.extensions.get("mongo_client")
    if client is None:
        client = MongoClient(app.config["MONGODB_URI"], serverSelectionTimeoutMS=5000)
        app.extensions["mongo_client"] = client
    return client


def get_mongo_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_COLLECTION"]]


def get_mongo_enquiries_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_ENQUIRIES_COLLECTION"]]


def get_mongo_contacts_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_CONTACTS_COLLECTION"]]


def get_mongo_lead_notes_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_LEAD_NOTES_COLLECTION"]]


def get_mongo_inspections_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_INSPECTIONS_COLLECTION"]]


def get_mongo_partners_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_PARTNERS_COLLECTION"]]


def get_mongo_referrals_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_REFERRALS_COLLECTION"]]


def get_mongo_referral_events_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_REFERRAL_EVENTS_COLLECTION"]]


def get_mongo_commission_rules_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_COMMISSION_RULES_COLLECTION"]]


def get_mongo_commissions_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_COMMISSIONS_COLLECTION"]]


def get_mongo_marketing_assets_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_MARKETING_ASSETS_COLLECTION"]]


def get_mongo_partner_marketing_events_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_PARTNER_MARKETING_EVENTS_COLLECTION"]]


def get_mongo_activity_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_ACTIVITY_COLLECTION"]]


def get_mongo_maintenance_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_MAINTENANCE_COLLECTION"]]


def get_mongo_financial_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_FINANCIAL_COLLECTION"]]


def get_mongo_document_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_DOCUMENT_COLLECTION"]]


def get_mongo_settings_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_SETTINGS_COLLECTION"]]


def get_mongo_staff_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_STAFF_COLLECTION"]]


def get_mongo_staff_invitations_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_STAFF_INVITATIONS_COLLECTION"]]


def get_mongo_login_attempts_collection():
    database = get_mongo_client()[app.config["MONGODB_DB_NAME"]]
    return database[app.config["MONGODB_LOGIN_ATTEMPTS_COLLECTION"]]


def configure_cloudinary() -> None:
    if app.extensions.get("cloudinary_ready"):
        return

    cloudinary.reset_config()
    if app.config["CLOUDINARY_URL"]:
        os.environ["CLOUDINARY_URL"] = app.config["CLOUDINARY_URL"]
        cloudinary.config(secure=True)
    else:
        cloudinary.config(
            cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
            api_key=app.config["CLOUDINARY_API_KEY"],
            api_secret=app.config["CLOUDINARY_API_SECRET"],
            secure=True,
        )
    app.extensions["cloudinary_ready"] = True


def sqlite_table_columns(table_name: str) -> set[str]:
    rows = get_db().execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def ensure_sqlite_column(table_name: str, column_name: str, definition: str) -> None:
    if column_name in sqlite_table_columns(table_name):
        return
    get_db().execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
    get_db().commit()


@app.teardown_appcontext
def close_db(_error: Exception | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def normalize_listing_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    data["featured"] = 1 if data.get("featured") else 0
    data["published"] = 1 if data.get("published") else 0
    data["availability"] = str(data.get("availability") or "Available")
    data["view_count"] = int(data.get("view_count") or 0)
    data["gallery_paths"] = normalize_string_list(data.get("gallery_paths"))
    data["virtual_tour_url"] = str(data.get("virtual_tour_url") or "").strip()
    data["documentation_summary"] = str(data.get("documentation_summary") or "").strip()
    data["documentation_verified"] = 1 if data.get("documentation_verified") else 0
    data["payment_plan_summary"] = str(data.get("payment_plan_summary") or "").strip()
    data["is_completed"] = 1 if data["availability"] in {"Sold", "Rented", "Leased"} else 0
    for key, _label in DISCOVERY_FEATURE_FIELDS + VERIFICATION_FIELDS:
        data[key] = 1 if data.get(key) else 0
    data["longitude"] = normalize_coordinate(data.get("longitude"), minimum=-180, maximum=180)
    data["latitude"] = normalize_coordinate(data.get("latitude"), minimum=-90, maximum=90)
    map_longitude, map_latitude, map_location_mode = resolve_listing_coordinates(data)
    data["map_longitude"] = map_longitude
    data["map_latitude"] = map_latitude
    data["map_location_mode"] = map_location_mode
    data["has_precise_coordinates"] = 1 if map_location_mode == "exact" else 0
    return data


def normalize_enquiry_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    data["status"] = canonical_lead_stage(data.get("status"))
    data["status_label"] = lead_stage_label(data["status"])
    data["source"] = str(data.get("source") or "WEBSITE").strip().upper()
    if data["source"] not in LEAD_SOURCES:
        data["source"] = "OTHER"
    data["source_label"] = LEAD_SOURCE_LABELS[data["source"]]
    data["campaign_id"] = str(data.get("campaign_id") or "").strip()
    data["contact_id"] = str(data.get("contact_id") or "").strip()
    data["assigned_staff_id"] = str(data.get("assigned_staff_id") or "").strip()
    data["assigned_to"] = str(data.get("assigned_to") or "").strip()
    data["estimated_value"] = int(data.get("estimated_value") or 0)
    data["whatsapp"] = str(data.get("whatsapp") or "").strip()
    data["partner_id"] = str(data.get("partner_id") or "").strip()
    data["referral_id"] = str(data.get("referral_id") or "").strip()
    data["last_contacted_at"] = str(data.get("last_contacted_at") or "").strip()
    data["internal_note"] = str(data.get("internal_note") or "").strip()
    data["follow_up_on"] = str(data.get("follow_up_on") or "").strip()
    data["admin_email_recipient"] = str(data.get("admin_email_recipient") or "").strip()
    data["admin_email_sent_at"] = str(data.get("admin_email_sent_at") or "").strip()
    data["admin_email_last_error"] = str(data.get("admin_email_last_error") or "").strip()
    data["receipt_email_recipient"] = str(data.get("receipt_email_recipient") or "").strip()
    data["receipt_email_sent_at"] = str(data.get("receipt_email_sent_at") or "").strip()
    data["receipt_email_last_error"] = str(data.get("receipt_email_last_error") or "").strip()
    if data["admin_email_sent_at"]:
        data["admin_email_status"] = "sent"
    elif data["admin_email_last_error"]:
        data["admin_email_status"] = "failed"
    else:
        data["admin_email_status"] = "pending"
    if data["receipt_email_sent_at"]:
        data["receipt_email_status"] = "sent"
    elif data["receipt_email_last_error"]:
        data["receipt_email_status"] = "failed"
    elif str(data.get("email") or "").strip():
        data["receipt_email_status"] = "pending"
    else:
        data["receipt_email_status"] = "not_requested"
    return data


def normalize_activity_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    raw_metadata = data.get("metadata_json", data.get("metadata", {}))
    if isinstance(raw_metadata, Mapping):
        data["metadata"] = dict(raw_metadata)
    else:
        try:
            data["metadata"] = json.loads(str(raw_metadata or "{}"))
        except json.JSONDecodeError:
            data["metadata"] = {}
    return data


def normalize_contact_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    return data


def normalize_lead_note_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    return data


def normalize_inspection_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    data["status"] = str(data.get("status") or "REQUESTED").upper()
    data["status_label"] = INSPECTION_STATUS_LABELS.get(data["status"], "Requested")
    for key in (
        "lead_id", "contact_id", "assigned_staff_id", "assigned_to", "internal_note",
        "partner_id", "referral_id",
    ):
        data[key] = str(data.get(key) or "").strip()
    return data


def normalize_partner_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    data["status"] = str(data.get("status") or "PENDING").upper()
    data["status_label"] = PARTNER_STATUS_LABELS.get(data["status"], "Pending review")
    data["partner_type"] = str(data.get("partner_type") or "INDIVIDUAL").upper()
    data["partner_type_label"] = PARTNER_TYPE_LABELS.get(data["partner_type"], "Individual")
    for key in (
        "full_name", "email", "phone", "whatsapp", "location", "company_name",
        "experience_notes", "referral_source", "partner_code", "reviewed_by",
        "reviewed_at", "review_note", "last_login_at",
    ):
        data[key] = str(data.get(key) or "").strip()
    return data


def partner_record_for_template(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = normalize_partner_record(record)
    for key in ("password_hash", "email_key", "phone_key"):
        data.pop(key, None)
    return data


def normalize_referral_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    data["status"] = str(data.get("status") or "VISITED").upper()
    data["status_label"] = REFERRAL_STATUS_LABELS.get(data["status"], "Visit captured")
    data["visit_count"] = int(data.get("visit_count") or 0)
    for key in (
        "partner_id", "partner_code", "listing_id", "listing_title", "lead_id", "inspection_id",
        "first_path", "last_path", "first_seen_at", "last_seen_at", "expires_at", "created_at", "updated_at",
    ):
        data[key] = str(data.get(key) or "").strip()
    data.pop("token_hash", None)
    return data


def normalize_referral_event(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    raw = data.get("metadata", data.get("metadata_json", {}))
    if isinstance(raw, Mapping):
        data["metadata"] = dict(raw)
    else:
        try:
            data["metadata"] = json.loads(str(raw or "{}"))
        except json.JSONDecodeError:
            data["metadata"] = {}
    return data


def normalize_commission_rule(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = str(data.get("public_id") or data.get("id") or "")
    data["calculation_type"] = str(data.get("calculation_type") or "PERCENTAGE").upper()
    data["calculation_label"] = COMMISSION_CALCULATION_LABELS.get(data["calculation_type"], "Percentage")
    data["scope_type"] = str(data.get("scope_type") or "DEFAULT").upper()
    data["scope_label"] = COMMISSION_SCOPE_LABELS.get(data["scope_type"], "Default")
    data["percentage_bps"] = int(data.get("percentage_bps") or 0)
    data["percentage"] = str(minor_to_major(data["percentage_bps"]))
    data["fixed_amount_minor"] = int(data.get("fixed_amount_minor") or 0)
    data["fixed_amount"] = int(minor_to_major(data["fixed_amount_minor"]))
    data["priority"] = int(data.get("priority") or 0)
    data["active"] = bool(data.get("active"))
    for key in (
        "name", "property_id", "property_title", "campaign_id", "partner_id", "valid_from",
        "valid_until", "created_by", "created_at", "updated_at",
    ):
        data[key] = str(data.get(key) or "").strip()
    return data


def normalize_commission(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = str(data.get("public_id") or data.get("id") or "")
    data["status"] = str(data.get("status") or "POTENTIAL").upper()
    data["status_label"] = COMMISSION_STATUS_LABELS.get(data["status"], "Potential")
    for key in (
        "sale_value_minor", "calculated_amount_minor", "adjustment_minor", "final_amount_minor",
    ):
        data[key] = int(data.get(key) or 0)
    data["sale_value"] = int(minor_to_major(data["sale_value_minor"]))
    data["calculated_amount"] = int(minor_to_major(data["calculated_amount_minor"]))
    data["adjustment"] = int(minor_to_major(data["adjustment_minor"]))
    data["final_amount"] = int(minor_to_major(data["final_amount_minor"]))
    raw_snapshot = data.get("rule_snapshot", data.get("rule_snapshot_json", {}))
    if isinstance(raw_snapshot, Mapping):
        data["rule_snapshot"] = dict(raw_snapshot)
    else:
        try:
            data["rule_snapshot"] = json.loads(str(raw_snapshot or "{}"))
        except json.JSONDecodeError:
            data["rule_snapshot"] = {}
    for key in (
        "lead_id", "referral_id", "partner_id", "partner_code", "listing_id", "listing_title",
        "customer_reference", "rule_id", "rule_name", "calculation_type", "adjustment_reason",
        "approved_by", "approved_at", "rejected_by", "rejected_at", "rejection_reason",
        "paid_by", "paid_at", "payment_reference", "payment_note", "created_at", "updated_at",
    ):
        data[key] = str(data.get(key) or "").strip()
    data.pop("rule_snapshot_json", None)
    return data


def normalize_marketing_asset(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = str(data.get("public_id") or data.get("id") or "")
    data["asset_type"] = str(data.get("asset_type") or "DOCUMENT").upper()
    data["asset_type_label"] = MARKETING_ASSET_TYPE_LABELS.get(data["asset_type"], "Document")
    data["file_size"] = int(data.get("file_size") or 0)
    data["active"] = bool(data.get("active"))
    data["approved"] = bool(data.get("approved"))
    for key in (
        "listing_id", "title", "storage_kind", "storage_key", "external_url", "mime_type",
        "created_by", "created_at", "updated_at",
    ):
        data[key] = str(data.get(key) or "").strip()
    return data


def normalize_staff_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = str(data.get("public_id") or data.get("id") or "")
    data["username"] = normalize_username(str(data.get("username") or ""))
    data["email"] = normalize_staff_email(str(data.get("email") or ""))
    data["role"] = str(data.get("role") or "").strip().upper()
    data["role_label"] = role_label(str(data["role"]))
    data["status"] = str(data.get("status") or "DISABLED").strip().upper()
    return data


def normalize_staff_invitation_record(
    record: Mapping[str, object] | sqlite3.Row,
) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = str(data.get("public_id") or data.get("id") or "")
    data["email"] = normalize_staff_email(str(data.get("email") or ""))
    data["role"] = str(data.get("role") or "").strip().upper()
    data["role_label"] = role_label(str(data["role"]))
    data["status"] = str(data.get("status") or "PENDING").strip().upper()
    return data


def normalize_maintenance_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    data["status"] = str(data.get("status") or "New")
    data["priority"] = str(data.get("priority") or "Medium")
    data["assigned_manager"] = str(data.get("assigned_manager") or "").strip()
    data["internal_note"] = str(data.get("internal_note") or "").strip()
    return data


def maintenance_form_defaults() -> dict[str, str]:
    return {
        "resident_name": "",
        "email": "",
        "phone": "",
        "unit_reference": "",
        "property_title": "",
        "issue_category": "",
        "priority": "Medium",
        "description": "",
        "assigned_vendor": "",
    }


def maintenance_ticket_reference(ticket_id: str) -> str:
    return f"TS-{str(ticket_id or '').upper()}"


def maintenance_response_window(priority: str) -> str:
    if priority == "Emergency":
        return "Target review: immediate. If there is active risk to safety, access, power, or water, escalate by WhatsApp after submitting."
    if priority == "High":
        return "Target review: same working day."
    if priority == "Low":
        return "Target review: within two working days."
    return "Target review: within one working day."


def normalize_financial_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    data["status"] = str(data.get("status") or "Due")
    data["amount"] = int(data.get("amount") or 0)
    data["assigned_to"] = str(data.get("assigned_to") or "").strip()
    data["note"] = str(data.get("note") or "").strip()
    return data


def normalize_document_record(record: Mapping[str, object] | sqlite3.Row) -> dict[str, object]:
    data = dict(record)
    data.pop("_id", None)
    data["id"] = data.get("public_id") or data.get("id")
    data["file_size"] = int(data.get("file_size") or 0)
    data["note"] = str(data.get("note") or "").strip()
    data["document_status"] = str(
        data.get("document_status")
        or ("Final" if str(data.get("source_kind") or "") == "generated" else "Filed")
    ).strip()
    data["source_kind"] = str(data.get("source_kind") or "upload").strip() or "upload"
    data["template_key"] = str(data.get("template_key") or "").strip()
    data["template_version"] = str(data.get("template_version") or "").strip()
    raw_payload = data.get("payload_json")
    if isinstance(raw_payload, dict):
        data["payload_json"] = json.dumps(raw_payload, indent=2)
        data["payload_data"] = raw_payload
    else:
        payload_text = str(raw_payload or "").strip()
        data["payload_json"] = payload_text
        if payload_text:
            try:
                data["payload_data"] = json.loads(payload_text)
            except json.JSONDecodeError:
                data["payload_data"] = {}
        else:
            data["payload_data"] = {}
    return data


def init_sqlite_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            availability TEXT NOT NULL DEFAULT 'Available',
            property_type TEXT NOT NULL,
            district TEXT NOT NULL,
            address TEXT NOT NULL,
            longitude REAL,
            latitude REAL,
            gallery_paths TEXT NOT NULL DEFAULT '[]',
            virtual_tour_url TEXT NOT NULL DEFAULT '',
            documentation_summary TEXT NOT NULL DEFAULT '',
            documentation_verified INTEGER NOT NULL DEFAULT 0,
            payment_plan_summary TEXT NOT NULL DEFAULT '',
            is_serviced INTEGER NOT NULL DEFAULT 0,
            has_power_24_7 INTEGER NOT NULL DEFAULT 0,
            is_flood_free INTEGER NOT NULL DEFAULT 0,
            near_express INTEGER NOT NULL DEFAULT 0,
            near_schools INTEGER NOT NULL DEFAULT 0,
            near_markets INTEGER NOT NULL DEFAULT 0,
            verified_property INTEGER NOT NULL DEFAULT 0,
            verified_landlord INTEGER NOT NULL DEFAULT 0,
            price INTEGER NOT NULL,
            price_suffix TEXT NOT NULL DEFAULT '',
            bedrooms INTEGER NOT NULL DEFAULT 0,
            bathrooms INTEGER NOT NULL DEFAULT 0,
            area_sqm INTEGER NOT NULL DEFAULT 0,
            summary TEXT NOT NULL,
            description TEXT NOT NULL,
            image_path TEXT,
            featured INTEGER NOT NULL DEFAULT 0,
            published INTEGER NOT NULL DEFAULT 1,
            view_count INTEGER NOT NULL DEFAULT 0,
            last_viewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS enquiries (
            public_id TEXT PRIMARY KEY,
            listing_id TEXT,
            listing_title TEXT,
            status TEXT NOT NULL DEFAULT 'NEW',
            contact_id TEXT,
            source TEXT NOT NULL DEFAULT 'WEBSITE',
            campaign_id TEXT,
            assigned_staff_id TEXT,
            assigned_to TEXT,
            estimated_value INTEGER NOT NULL DEFAULT 0,
            whatsapp TEXT,
            partner_id TEXT,
            referral_id TEXT,
            last_contacted_at TEXT,
            internal_note TEXT,
            follow_up_on TEXT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            preferred_contact TEXT NOT NULL DEFAULT 'Email',
            message TEXT NOT NULL,
            source_path TEXT,
            admin_email_recipient TEXT,
            admin_email_sent_at TEXT,
            admin_email_last_error TEXT,
            receipt_email_recipient TEXT,
            receipt_email_sent_at TEXT,
            receipt_email_last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            public_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            action TEXT NOT NULL,
            actor_label TEXT NOT NULL,
            actor_id TEXT,
            actor_type TEXT NOT NULL DEFAULT 'system',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS staff_users (
            public_id TEXT PRIMARY KEY,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            username_key TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            email_key TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            password_hash TEXT NOT NULL,
            last_login_at TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contacts (
            public_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT,
            email_key TEXT,
            phone TEXT,
            phone_key TEXT,
            whatsapp TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_email_key
        ON contacts (email_key) WHERE email_key != '';

        CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_phone_key
        ON contacts (phone_key) WHERE phone_key != '';

        CREATE TABLE IF NOT EXISTS lead_notes (
            public_id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            body TEXT NOT NULL,
            actor_id TEXT,
            actor_label TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_lead_notes_lead_time
        ON lead_notes (lead_id, created_at);

        CREATE TABLE IF NOT EXISTS inspections (
            public_id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL,
            contact_id TEXT,
            listing_id TEXT,
            listing_title TEXT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            requested_date TEXT NOT NULL,
            requested_time TEXT NOT NULL,
            assigned_staff_id TEXT,
            assigned_to TEXT,
            notes TEXT,
            internal_note TEXT,
            status TEXT NOT NULL DEFAULT 'REQUESTED',
            partner_id TEXT,
            referral_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_inspections_status_date
        ON inspections (status, requested_date, requested_time);

        CREATE INDEX IF NOT EXISTS idx_inspections_lead
        ON inspections (lead_id);

        CREATE TABLE IF NOT EXISTS partners (
            public_id TEXT PRIMARY KEY,
            partner_code TEXT NOT NULL COLLATE NOCASE UNIQUE,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE,
            email_key TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            phone_key TEXT NOT NULL,
            whatsapp TEXT,
            location TEXT NOT NULL,
            partner_type TEXT NOT NULL DEFAULT 'INDIVIDUAL',
            company_name TEXT,
            experience_notes TEXT,
            referral_source TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            password_hash TEXT NOT NULL,
            reviewed_by TEXT,
            reviewed_at TEXT,
            review_note TEXT,
            last_login_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_partners_status_created
        ON partners (status, created_at);

        CREATE TABLE IF NOT EXISTS referrals (
            public_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            partner_id TEXT NOT NULL,
            partner_code TEXT NOT NULL,
            listing_id TEXT,
            listing_title TEXT,
            status TEXT NOT NULL DEFAULT 'VISITED',
            lead_id TEXT,
            inspection_id TEXT,
            first_path TEXT NOT NULL,
            last_path TEXT NOT NULL,
            visit_count INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_referrals_partner_created
        ON referrals (partner_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_referrals_listing_partner
        ON referrals (listing_id, partner_id);

        CREATE INDEX IF NOT EXISTS idx_referrals_lead
        ON referrals (lead_id);

        CREATE TABLE IF NOT EXISTS referral_events (
            public_id TEXT PRIMARY KEY,
            referral_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_referral_events_referral_time
        ON referral_events (referral_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS commission_rules (
            public_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            calculation_type TEXT NOT NULL,
            percentage_bps INTEGER NOT NULL DEFAULT 0,
            fixed_amount_minor INTEGER NOT NULL DEFAULT 0,
            scope_type TEXT NOT NULL DEFAULT 'DEFAULT',
            property_id TEXT,
            property_title TEXT,
            campaign_id TEXT,
            partner_id TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            valid_from TEXT,
            valid_until TEXT,
            priority INTEGER NOT NULL DEFAULT 0,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_commission_rules_active_scope
        ON commission_rules (active, scope_type, priority DESC);

        CREATE INDEX IF NOT EXISTS idx_commission_rules_property
        ON commission_rules (property_id, active);

        CREATE INDEX IF NOT EXISTS idx_commission_rules_partner
        ON commission_rules (partner_id, active);

        CREATE INDEX IF NOT EXISTS idx_commission_rules_campaign
        ON commission_rules (campaign_id, active);

        CREATE TABLE IF NOT EXISTS commissions (
            public_id TEXT PRIMARY KEY,
            lead_id TEXT NOT NULL UNIQUE,
            referral_id TEXT NOT NULL,
            partner_id TEXT NOT NULL,
            partner_code TEXT NOT NULL,
            listing_id TEXT,
            listing_title TEXT,
            customer_reference TEXT NOT NULL,
            sale_value_minor INTEGER NOT NULL,
            rule_id TEXT NOT NULL,
            rule_name TEXT NOT NULL,
            calculation_type TEXT NOT NULL,
            rule_snapshot_json TEXT NOT NULL,
            calculated_amount_minor INTEGER NOT NULL,
            adjustment_minor INTEGER NOT NULL DEFAULT 0,
            final_amount_minor INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'POTENTIAL',
            adjustment_reason TEXT,
            approved_by TEXT,
            approved_at TEXT,
            rejected_by TEXT,
            rejected_at TEXT,
            rejection_reason TEXT,
            paid_by TEXT,
            paid_at TEXT,
            payment_reference TEXT,
            payment_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_commissions_status_created
        ON commissions (status, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_commissions_partner_created
        ON commissions (partner_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_commissions_listing_created
        ON commissions (listing_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS marketing_assets (
            public_id TEXT PRIMARY KEY,
            listing_id TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            title TEXT NOT NULL,
            storage_kind TEXT NOT NULL,
            storage_key TEXT,
            external_url TEXT,
            mime_type TEXT,
            file_size INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            approved INTEGER NOT NULL DEFAULT 0,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_marketing_assets_listing_active
        ON marketing_assets (listing_id, approved, active, created_at DESC);

        CREATE TABLE IF NOT EXISTS partner_marketing_events (
            public_id TEXT PRIMARY KEY,
            partner_id TEXT NOT NULL,
            listing_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_partner_marketing_events_partner_time
        ON partner_marketing_events (partner_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_partner_marketing_events_partner_listing
        ON partner_marketing_events (partner_id, listing_id, event_type);

        CREATE INDEX IF NOT EXISTS idx_partner_marketing_events_partner_type
        ON partner_marketing_events (partner_id, event_type);

        CREATE TABLE IF NOT EXISTS staff_invitations (
            public_id TEXT PRIMARY KEY,
            email TEXT NOT NULL COLLATE NOCASE,
            email_key TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'PENDING',
            invited_by TEXT NOT NULL,
            accepted_by TEXT,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_staff_users_role_status
        ON staff_users (role, status);

        CREATE INDEX IF NOT EXISTS idx_staff_invitations_email_status
        ON staff_invitations (email_key, status);

        CREATE TABLE IF NOT EXISTS staff_login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_key TEXT NOT NULL,
            attempted_at REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_staff_login_attempts_key_time
        ON staff_login_attempts (attempt_key, attempted_at);

        CREATE TABLE IF NOT EXISTS maintenance_tickets (
            public_id TEXT PRIMARY KEY,
            resident_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            unit_reference TEXT NOT NULL,
            property_title TEXT,
            issue_category TEXT NOT NULL,
            priority TEXT NOT NULL,
            description TEXT NOT NULL,
            image_path TEXT,
            assigned_manager TEXT,
            assigned_vendor TEXT,
            internal_note TEXT,
            status TEXT NOT NULL DEFAULT 'New',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS financial_records (
            public_id TEXT PRIMARY KEY,
            resident_name TEXT NOT NULL,
            unit_reference TEXT NOT NULL,
            property_title TEXT,
            charge_type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            assigned_to TEXT,
            status TEXT NOT NULL DEFAULT 'Due',
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS documents (
            public_id TEXT PRIMARY KEY,
            resident_name TEXT NOT NULL,
            unit_reference TEXT NOT NULL,
            property_title TEXT,
            document_type TEXT NOT NULL,
            title TEXT NOT NULL,
            note TEXT,
            document_status TEXT NOT NULL DEFAULT 'Filed',
            source_kind TEXT NOT NULL DEFAULT 'upload',
            template_key TEXT NOT NULL DEFAULT '',
            template_version TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '',
            stored_filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS site_preferences (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    db.commit()

    ensure_sqlite_column("listings", "availability", "TEXT NOT NULL DEFAULT 'Available'")
    ensure_sqlite_column("listings", "view_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "last_viewed_at", "TEXT")
    ensure_sqlite_column("listings", "longitude", "REAL")
    ensure_sqlite_column("listings", "latitude", "REAL")
    ensure_sqlite_column("listings", "gallery_paths", "TEXT NOT NULL DEFAULT '[]'")
    ensure_sqlite_column("listings", "virtual_tour_url", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column("listings", "documentation_summary", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column("listings", "documentation_verified", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "payment_plan_summary", "TEXT NOT NULL DEFAULT ''")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_listings_public_availability_updated "
        "ON listings (published, availability, updated_at DESC)"
    )
    ensure_sqlite_column("listings", "is_serviced", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "has_power_24_7", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "is_flood_free", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "near_express", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "near_schools", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "near_markets", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "verified_property", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "verified_landlord", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("enquiries", "assigned_to", "TEXT")
    ensure_sqlite_column("enquiries", "contact_id", "TEXT")
    ensure_sqlite_column("enquiries", "source", "TEXT NOT NULL DEFAULT 'WEBSITE'")
    ensure_sqlite_column("enquiries", "campaign_id", "TEXT")
    ensure_sqlite_column("enquiries", "assigned_staff_id", "TEXT")
    ensure_sqlite_column("enquiries", "estimated_value", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("enquiries", "whatsapp", "TEXT")
    ensure_sqlite_column("enquiries", "partner_id", "TEXT")
    ensure_sqlite_column("enquiries", "referral_id", "TEXT")
    ensure_sqlite_column("enquiries", "last_contacted_at", "TEXT")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_enquiries_contact_listing_status ON enquiries (contact_id, listing_id, status)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_enquiries_partner_status ON enquiries (partner_id, status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_enquiries_partner_created ON enquiries (partner_id, created_at DESC)")
    ensure_sqlite_column("inspections", "partner_id", "TEXT")
    ensure_sqlite_column("inspections", "referral_id", "TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS idx_inspections_partner_created ON inspections (partner_id, created_at DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_inspections_referral ON inspections (referral_id)")
    ensure_sqlite_column("enquiries", "internal_note", "TEXT")
    ensure_sqlite_column("enquiries", "follow_up_on", "TEXT")
    ensure_sqlite_column("enquiries", "admin_email_recipient", "TEXT")
    ensure_sqlite_column("enquiries", "admin_email_sent_at", "TEXT")
    ensure_sqlite_column("enquiries", "admin_email_last_error", "TEXT")
    ensure_sqlite_column("enquiries", "receipt_email_recipient", "TEXT")
    ensure_sqlite_column("enquiries", "receipt_email_sent_at", "TEXT")
    ensure_sqlite_column("enquiries", "receipt_email_last_error", "TEXT")
    ensure_sqlite_column("activity_log", "actor_id", "TEXT")
    ensure_sqlite_column("activity_log", "actor_type", "TEXT NOT NULL DEFAULT 'system'")
    ensure_sqlite_column("activity_log", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_actor_time ON activity_log (actor_type, actor_id, created_at)"
    )
    ensure_sqlite_column("maintenance_tickets", "assigned_manager", "TEXT")
    ensure_sqlite_column("maintenance_tickets", "internal_note", "TEXT")
    ensure_sqlite_column("financial_records", "assigned_to", "TEXT")
    ensure_sqlite_column("documents", "source_kind", "TEXT NOT NULL DEFAULT 'upload'")
    ensure_sqlite_column("documents", "document_status", "TEXT NOT NULL DEFAULT 'Filed'")
    ensure_sqlite_column("documents", "template_key", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column("documents", "template_version", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column("documents", "payload_json", "TEXT NOT NULL DEFAULT ''")
    db.execute("UPDATE listings SET availability = 'Available' WHERE availability IS NULL OR availability = ''")
    db.execute("UPDATE listings SET view_count = 0 WHERE view_count IS NULL")
    db.execute("UPDATE listings SET gallery_paths = '[]' WHERE gallery_paths IS NULL OR gallery_paths = ''")
    db.execute("UPDATE listings SET virtual_tour_url = '' WHERE virtual_tour_url IS NULL")
    db.execute("UPDATE listings SET documentation_summary = '' WHERE documentation_summary IS NULL")
    db.execute("UPDATE listings SET documentation_verified = 0 WHERE documentation_verified IS NULL")
    db.execute("UPDATE listings SET payment_plan_summary = '' WHERE payment_plan_summary IS NULL")
    db.execute("UPDATE enquiries SET assigned_to = '' WHERE assigned_to IS NULL")
    db.execute("UPDATE enquiries SET contact_id = '' WHERE contact_id IS NULL")
    db.execute("UPDATE enquiries SET source = 'WEBSITE' WHERE source IS NULL OR source = ''")
    db.execute("UPDATE enquiries SET campaign_id = '' WHERE campaign_id IS NULL")
    db.execute("UPDATE enquiries SET assigned_staff_id = '' WHERE assigned_staff_id IS NULL")
    db.execute("UPDATE enquiries SET estimated_value = 0 WHERE estimated_value IS NULL")
    db.execute("UPDATE enquiries SET whatsapp = '' WHERE whatsapp IS NULL")
    db.execute("UPDATE enquiries SET partner_id = '' WHERE partner_id IS NULL")
    db.execute("UPDATE enquiries SET referral_id = '' WHERE referral_id IS NULL")
    for legacy, canonical in {
        "New": "NEW", "Qualified": "QUALIFIED", "Viewing Scheduled": "INSPECTION_SCHEDULED",
        "Negotiating": "NEGOTIATION", "Won": "CLOSED_WON", "Lost": "CLOSED_LOST", "Handled": "ARCHIVED",
    }.items():
        db.execute("UPDATE enquiries SET status = ? WHERE status = ?", (canonical, legacy))
    db.execute("UPDATE enquiries SET internal_note = '' WHERE internal_note IS NULL")
    db.execute("UPDATE enquiries SET admin_email_recipient = '' WHERE admin_email_recipient IS NULL")
    db.execute("UPDATE enquiries SET admin_email_sent_at = '' WHERE admin_email_sent_at IS NULL")
    db.execute("UPDATE enquiries SET admin_email_last_error = '' WHERE admin_email_last_error IS NULL")
    db.execute("UPDATE enquiries SET receipt_email_recipient = '' WHERE receipt_email_recipient IS NULL")
    db.execute("UPDATE enquiries SET receipt_email_sent_at = '' WHERE receipt_email_sent_at IS NULL")
    db.execute("UPDATE enquiries SET receipt_email_last_error = '' WHERE receipt_email_last_error IS NULL")
    db.execute("UPDATE activity_log SET actor_id = '' WHERE actor_id IS NULL")
    db.execute("UPDATE activity_log SET actor_type = 'system' WHERE actor_type IS NULL OR actor_type = ''")
    db.execute("UPDATE activity_log SET metadata_json = '{}' WHERE metadata_json IS NULL OR metadata_json = ''")
    db.execute("UPDATE maintenance_tickets SET assigned_manager = '' WHERE assigned_manager IS NULL")
    db.execute("UPDATE maintenance_tickets SET internal_note = '' WHERE internal_note IS NULL")
    db.execute("UPDATE financial_records SET assigned_to = '' WHERE assigned_to IS NULL")
    db.execute("UPDATE documents SET source_kind = 'upload' WHERE source_kind IS NULL OR source_kind = ''")
    db.execute("UPDATE documents SET document_status = 'Filed' WHERE document_status IS NULL OR document_status = ''")
    db.execute("UPDATE documents SET document_status = 'Final' WHERE source_kind = 'generated' AND document_status = 'Filed'")
    db.execute("UPDATE documents SET template_key = '' WHERE template_key IS NULL")
    db.execute("UPDATE documents SET template_version = '' WHERE template_version IS NULL")
    db.execute("UPDATE documents SET payload_json = '' WHERE payload_json IS NULL")
    db.execute("PRAGMA optimize")
    db.commit()

    current_count = db.execute("SELECT COUNT(*) AS count FROM listings").fetchone()["count"]
    if current_count == 0:
        seed_sqlite_listings()
    bootstrap_staff_admin()


def seed_sqlite_listings() -> None:
    db = get_db()
    payloads = []
    for item in sample_listings():
        payload = dict(item)
        payload["gallery_paths"] = json.dumps(payload.get("gallery_paths", []))
        payloads.append(payload)
    db.executemany(
        """
        INSERT INTO listings (
            title,
            status,
            availability,
            property_type,
            district,
            address,
            longitude,
            latitude,
            gallery_paths,
            virtual_tour_url,
            documentation_summary,
            documentation_verified,
            payment_plan_summary,
            is_serviced,
            has_power_24_7,
            is_flood_free,
            near_express,
            near_schools,
            near_markets,
            verified_property,
            verified_landlord,
            price,
            price_suffix,
            bedrooms,
            bathrooms,
            area_sqm,
            summary,
            description,
            image_path,
            featured,
            published,
            view_count,
            created_at,
            updated_at
        ) VALUES (
            :title,
            :status,
            :availability,
            :property_type,
            :district,
            :address,
            :longitude,
            :latitude,
            :gallery_paths,
            :virtual_tour_url,
            :documentation_summary,
            :documentation_verified,
            :payment_plan_summary,
            :is_serviced,
            :has_power_24_7,
            :is_flood_free,
            :near_express,
            :near_schools,
            :near_markets,
            :verified_property,
            :verified_landlord,
            :price,
            :price_suffix,
            :bedrooms,
            :bathrooms,
            :area_sqm,
            :summary,
            :description,
            :image_path,
            :featured,
            :published,
            :view_count,
            :created_at,
            :updated_at
        )
        """,
        payloads,
    )
    db.commit()


def init_mongodb() -> None:
    collection = get_mongo_collection()
    collection.create_index([("public_id", ASCENDING)], unique=True)
    collection.create_index([("published", ASCENDING), ("featured", DESCENDING), ("updated_at", DESCENDING)])
    collection.create_index([("district", ASCENDING)])
    collection.create_index([("property_type", ASCENDING)])
    collection.create_index([("status", ASCENDING)])
    collection.create_index([("availability", ASCENDING)])
    collection.create_index([("published", ASCENDING), ("availability", ASCENDING), ("updated_at", DESCENDING)])
    collection.create_index([("verified_property", ASCENDING)])
    collection.create_index([("verified_landlord", ASCENDING)])
    collection.create_index([("is_serviced", ASCENDING)])
    collection.create_index([("has_power_24_7", ASCENDING)])
    collection.create_index([("is_flood_free", ASCENDING)])
    collection.create_index([("near_express", ASCENDING)])

    if collection.count_documents({}) == 0:
        collection.insert_many(sample_listings())
    else:
        collection.update_many({"availability": {"$exists": False}}, {"$set": {"availability": "Available"}})
        collection.update_many({"view_count": {"$exists": False}}, {"$set": {"view_count": 0}})
        collection.update_many({"last_viewed_at": {"$exists": False}}, {"$set": {"last_viewed_at": None}})
        collection.update_many({"longitude": {"$exists": False}}, {"$set": {"longitude": None}})
        collection.update_many({"latitude": {"$exists": False}}, {"$set": {"latitude": None}})
        collection.update_many({"gallery_paths": {"$exists": False}}, {"$set": {"gallery_paths": []}})
        collection.update_many({"virtual_tour_url": {"$exists": False}}, {"$set": {"virtual_tour_url": ""}})
        collection.update_many({"documentation_summary": {"$exists": False}}, {"$set": {"documentation_summary": ""}})
        collection.update_many({"documentation_verified": {"$exists": False}}, {"$set": {"documentation_verified": 0}})
        collection.update_many({"payment_plan_summary": {"$exists": False}}, {"$set": {"payment_plan_summary": ""}})
        for key, _label in DISCOVERY_FEATURE_FIELDS + VERIFICATION_FIELDS:
            collection.update_many({key: {"$exists": False}}, {"$set": {key: 0}})

    enquiries = get_mongo_enquiries_collection()
    enquiries.create_index([("public_id", ASCENDING)], unique=True)
    enquiries.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    enquiries.create_index([("listing_id", ASCENDING)])
    enquiries.create_index([("assigned_to", ASCENDING)])
    enquiries.create_index([("contact_id", ASCENDING)])
    enquiries.create_index([("assigned_staff_id", ASCENDING), ("status", ASCENDING)])
    enquiries.create_index([("contact_id", ASCENDING), ("listing_id", ASCENDING), ("status", ASCENDING)])
    enquiries.create_index([("partner_id", ASCENDING), ("status", ASCENDING)])
    enquiries.create_index([("partner_id", ASCENDING), ("created_at", DESCENDING)])
    enquiries.update_many({"assigned_to": {"$exists": False}}, {"$set": {"assigned_to": ""}})
    enquiries.update_many({"contact_id": {"$exists": False}}, {"$set": {"contact_id": ""}})
    enquiries.update_many({"source": {"$exists": False}}, {"$set": {"source": "WEBSITE"}})
    enquiries.update_many({"campaign_id": {"$exists": False}}, {"$set": {"campaign_id": ""}})
    enquiries.update_many({"assigned_staff_id": {"$exists": False}}, {"$set": {"assigned_staff_id": ""}})
    enquiries.update_many({"estimated_value": {"$exists": False}}, {"$set": {"estimated_value": 0}})
    enquiries.update_many({"whatsapp": {"$exists": False}}, {"$set": {"whatsapp": ""}})
    enquiries.update_many({"partner_id": {"$exists": False}}, {"$set": {"partner_id": ""}})
    enquiries.update_many({"referral_id": {"$exists": False}}, {"$set": {"referral_id": ""}})
    enquiries.update_many({"internal_note": {"$exists": False}}, {"$set": {"internal_note": ""}})
    enquiries.update_many({"follow_up_on": {"$exists": False}}, {"$set": {"follow_up_on": ""}})
    for legacy, canonical in {
        "New": "NEW", "Qualified": "QUALIFIED", "Viewing Scheduled": "INSPECTION_SCHEDULED",
        "Negotiating": "NEGOTIATION", "Won": "CLOSED_WON", "Lost": "CLOSED_LOST", "Handled": "ARCHIVED",
    }.items():
        enquiries.update_many({"status": legacy}, {"$set": {"status": canonical}})

    contacts = get_mongo_contacts_collection()
    contacts.create_index([("public_id", ASCENDING)], unique=True)
    contacts.create_index([("email_key", ASCENDING)], unique=True, sparse=True)
    contacts.create_index([("phone_key", ASCENDING)], unique=True, sparse=True)

    lead_notes = get_mongo_lead_notes_collection()
    lead_notes.create_index([("public_id", ASCENDING)], unique=True)
    lead_notes.create_index([("lead_id", ASCENDING), ("created_at", DESCENDING)])

    inspections = get_mongo_inspections_collection()
    inspections.create_index([("public_id", ASCENDING)], unique=True)
    inspections.create_index([("status", ASCENDING), ("requested_date", ASCENDING), ("requested_time", ASCENDING)])
    inspections.create_index([("lead_id", ASCENDING)])
    inspections.create_index([("assigned_staff_id", ASCENDING), ("status", ASCENDING)])
    inspections.create_index([("partner_id", ASCENDING), ("created_at", DESCENDING)])
    inspections.create_index([("referral_id", ASCENDING)])

    partners = get_mongo_partners_collection()
    partners.create_index([("public_id", ASCENDING)], unique=True)
    partners.create_index([("partner_code", ASCENDING)], unique=True)
    partners.create_index([("email_key", ASCENDING)], unique=True)
    partners.create_index([("status", ASCENDING), ("created_at", DESCENDING)])

    referrals = get_mongo_referrals_collection()
    referrals.create_index([("public_id", ASCENDING)], unique=True)
    referrals.create_index([("token_hash", ASCENDING)], unique=True)
    referrals.create_index([("partner_id", ASCENDING), ("created_at", DESCENDING)])
    referrals.create_index([("listing_id", ASCENDING), ("partner_id", ASCENDING)])
    referrals.create_index([("lead_id", ASCENDING)])

    referral_events = get_mongo_referral_events_collection()
    referral_events.create_index([("public_id", ASCENDING)], unique=True)
    referral_events.create_index([("referral_id", ASCENDING), ("created_at", DESCENDING)])

    commission_rules = get_mongo_commission_rules_collection()
    commission_rules.create_index([("public_id", ASCENDING)], unique=True)
    commission_rules.create_index([("active", ASCENDING), ("scope_type", ASCENDING), ("priority", DESCENDING)])
    commission_rules.create_index([("property_id", ASCENDING), ("active", ASCENDING)])
    commission_rules.create_index([("partner_id", ASCENDING), ("active", ASCENDING)])
    commission_rules.create_index([("campaign_id", ASCENDING), ("active", ASCENDING)])

    commissions = get_mongo_commissions_collection()
    commissions.create_index([("public_id", ASCENDING)], unique=True)
    commissions.create_index([("lead_id", ASCENDING)], unique=True)
    commissions.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    commissions.create_index([("partner_id", ASCENDING), ("created_at", DESCENDING)])
    commissions.create_index([("listing_id", ASCENDING), ("created_at", DESCENDING)])

    marketing_assets = get_mongo_marketing_assets_collection()
    marketing_assets.create_index([("public_id", ASCENDING)], unique=True)
    marketing_assets.create_index(
        [("listing_id", ASCENDING), ("approved", ASCENDING), ("active", ASCENDING), ("created_at", DESCENDING)]
    )

    marketing_events = get_mongo_partner_marketing_events_collection()
    marketing_events.create_index([("public_id", ASCENDING)], unique=True)
    marketing_events.create_index([("partner_id", ASCENDING), ("created_at", DESCENDING)])
    marketing_events.create_index(
        [("partner_id", ASCENDING), ("listing_id", ASCENDING), ("event_type", ASCENDING)]
    )
    marketing_events.create_index([("partner_id", ASCENDING), ("event_type", ASCENDING)])

    activity = get_mongo_activity_collection()
    activity.create_index([("created_at", DESCENDING)])
    activity.create_index([("entity_type", ASCENDING), ("entity_id", ASCENDING)])
    activity.create_index([("actor_type", ASCENDING), ("actor_id", ASCENDING), ("created_at", DESCENDING)])

    maintenance = get_mongo_maintenance_collection()
    maintenance.create_index([("public_id", ASCENDING)], unique=True)
    maintenance.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    maintenance.create_index([("assigned_manager", ASCENDING)])
    maintenance.update_many({"assigned_manager": {"$exists": False}}, {"$set": {"assigned_manager": ""}})
    maintenance.update_many({"internal_note": {"$exists": False}}, {"$set": {"internal_note": ""}})

    financial = get_mongo_financial_collection()
    financial.create_index([("public_id", ASCENDING)], unique=True)
    financial.create_index([("status", ASCENDING), ("due_date", ASCENDING)])
    financial.create_index([("assigned_to", ASCENDING)])
    financial.update_many({"assigned_to": {"$exists": False}}, {"$set": {"assigned_to": ""}})

    documents = get_mongo_document_collection()
    documents.create_index([("public_id", ASCENDING)], unique=True)
    documents.create_index([("document_type", ASCENDING), ("created_at", DESCENDING)])
    documents.create_index([("source_kind", ASCENDING), ("template_key", ASCENDING)])
    documents.create_index([("document_status", ASCENDING), ("created_at", DESCENDING)])
    documents.update_many({"source_kind": {"$exists": False}}, {"$set": {"source_kind": "upload"}})
    documents.update_many({"document_status": {"$exists": False}}, {"$set": {"document_status": "Filed"}})
    documents.update_many({"source_kind": "generated", "document_status": "Filed"}, {"$set": {"document_status": "Final"}})
    documents.update_many({"template_key": {"$exists": False}}, {"$set": {"template_key": ""}})
    documents.update_many({"template_version": {"$exists": False}}, {"$set": {"template_version": ""}})
    documents.update_many({"payload_json": {"$exists": False}}, {"$set": {"payload_json": ""}})

    staff = get_mongo_staff_collection()
    staff.create_index([("public_id", ASCENDING)], unique=True)
    staff.create_index([("username_key", ASCENDING)], unique=True)
    staff.create_index([("email_key", ASCENDING)], unique=True)
    staff.create_index([("role", ASCENDING), ("status", ASCENDING)])

    invitations = get_mongo_staff_invitations_collection()
    invitations.create_index([("public_id", ASCENDING)], unique=True)
    invitations.create_index([("token_hash", ASCENDING)], unique=True)
    invitations.create_index([("email_key", ASCENDING), ("status", ASCENDING)])
    invitations.create_index([("expires_at", ASCENDING)])

    login_attempts = get_mongo_login_attempts_collection()
    login_attempts.create_index([("attempt_key", ASCENDING), ("attempted_at", ASCENDING)])
    login_attempts.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)

    get_mongo_settings_collection()
    bootstrap_staff_admin()


def init_data_store() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    if database_backend() == "mongodb":
        mongodb_uri = app.config["MONGODB_URI"]
        if not is_valid_mongodb_uri(mongodb_uri):
            raise RuntimeError(
                "Invalid or missing STRUCTUREBASE_MONGODB_URI. "
                "Set it to a valid MongoDB URI like mongodb+srv://... or mongodb://..."
            )
        app.logger.info("Initializing MongoDB data store.")
        get_mongo_client().admin.command("ping")
        init_mongodb()
    else:
        app.logger.info("Initializing SQLite data store.")
        init_sqlite_db()
    backfill_lead_contacts()


def staff_record_for_template(record: Mapping[str, object]) -> dict[str, object]:
    data = normalize_staff_record(record)
    for key in ("password_hash", "username_key", "email_key"):
        data.pop(key, None)
    return data


def staff_user_count() -> int:
    if database_backend() == "mongodb":
        return int(get_mongo_staff_collection().count_documents({}))
    row = get_db().execute("SELECT COUNT(*) AS count FROM staff_users").fetchone()
    return int(row["count"] or 0)


def fetch_staff_user(user_id: str) -> dict[str, object] | None:
    identifier = str(user_id or "").strip()
    if not identifier:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_staff_collection().find_one({"public_id": identifier})
    else:
        row = get_db().execute(
            "SELECT * FROM staff_users WHERE public_id = ?",
            (identifier,),
        ).fetchone()
    return normalize_staff_record(row) if row is not None else None


def fetch_staff_by_identifier(identifier: str) -> dict[str, object] | None:
    key = str(identifier or "").strip().lower()
    if not key:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_staff_collection().find_one(
            {"$or": [{"username_key": key}, {"email_key": key}]}
        )
    else:
        row = get_db().execute(
            "SELECT * FROM staff_users WHERE username_key = ? OR email_key = ?",
            (key, key),
        ).fetchone()
    return normalize_staff_record(row) if row is not None else None


def staff_identity_exists(*, username: str = "", email: str = "") -> bool:
    username_key = normalize_username(username)
    email_key = normalize_staff_email(email)
    conditions = [value for value in (username_key, email_key) if value]
    if not conditions:
        return False
    if database_backend() == "mongodb":
        query_parts = []
        if username_key:
            query_parts.append({"username_key": username_key})
        if email_key:
            query_parts.append({"email_key": email_key})
        return get_mongo_staff_collection().count_documents({"$or": query_parts}, limit=1) > 0
    clauses = []
    params: list[str] = []
    if username_key:
        clauses.append("username_key = ?")
        params.append(username_key)
    if email_key:
        clauses.append("email_key = ?")
        params.append(email_key)
    row = get_db().execute(
        f"SELECT 1 FROM staff_users WHERE {' OR '.join(clauses)} LIMIT 1",
        params,
    ).fetchone()
    return row is not None


def create_staff_user(
    *,
    full_name: str,
    email: str,
    username: str,
    role: str,
    password_hash: str,
    created_by: str,
) -> str:
    now = utc_now_iso()
    payload = {
        "public_id": uuid.uuid4().hex[:16],
        "username": normalize_username(username),
        "username_key": normalize_username(username),
        "email": normalize_staff_email(email),
        "email_key": normalize_staff_email(email),
        "full_name": " ".join(str(full_name or "").split()),
        "role": str(role or "").strip().upper(),
        "status": "ACTIVE",
        "password_hash": password_hash,
        "last_login_at": "",
        "created_by": str(created_by or "").strip(),
        "created_at": now,
        "updated_at": now,
    }
    if payload["role"] not in ROLE_OPTIONS:
        raise ValueError("Choose a valid staff role.")
    try:
        if database_backend() == "mongodb":
            get_mongo_staff_collection().insert_one(payload)
        else:
            get_db().execute(
                """
                INSERT INTO staff_users (
                    public_id, username, username_key, email, email_key, full_name,
                    role, status, password_hash, last_login_at, created_by,
                    created_at, updated_at
                ) VALUES (
                    :public_id, :username, :username_key, :email, :email_key, :full_name,
                    :role, :status, :password_hash, :last_login_at, :created_by,
                    :created_at, :updated_at
                )
                """,
                payload,
            )
            get_db().commit()
    except (sqlite3.IntegrityError, DuplicateKeyError) as exc:
        raise ValueError("That username or email address is already in use.") from exc
    return str(payload["public_id"])


def bootstrap_staff_admin() -> None:
    if staff_user_count() > 0:
        return
    username = normalize_username(app.config["ADMIN_USERNAME"]) or "admin"
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,39}", username):
        username = "owner"
    configured_email = normalize_staff_email(
        os.environ.get("STRUCTUREBASE_INITIAL_ADMIN_EMAIL", "")
        or (app.config["ADMIN_USERNAME"] if "@" in app.config["ADMIN_USERNAME"] else "")
        or app.config["CONTACT_EMAIL"]
    )
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", configured_email):
        configured_email = f"{username}@local.invalid"
    full_name = " ".join(
        os.environ.get("STRUCTUREBASE_INITIAL_ADMIN_NAME", "Structurebase Owner").split()
    )
    password_hash = app.config["ADMIN_PASSWORD_HASH"] or hash_password(app.config["ADMIN_PASSWORD"])
    try:
        user_id = create_staff_user(
            full_name=full_name,
            email=configured_email,
            username=username,
            role="SUPER_ADMIN",
            password_hash=password_hash,
            created_by="bootstrap",
        )
    except ValueError:
        if staff_user_count() > 0:
            return
        raise
    app.logger.info("Bootstrapped the initial super-admin staff identity: %s", user_id)


def authenticate_staff(identifier: str, password: str) -> dict[str, object] | None:
    if (
        app.config["IS_PRODUCTION"]
        and normalize_username(identifier) == normalize_username(DEFAULT_ADMIN_USERNAME)
        and password == DEFAULT_ADMIN_PASSWORD
        and admin_password_is_default()
    ):
        return None
    staff = fetch_staff_by_identifier(identifier)
    if staff is None or staff.get("status") != "ACTIVE":
        return None
    if not verify_password(str(staff.get("password_hash") or ""), password):
        return None
    return staff


def update_staff_last_login(user_id: str) -> None:
    now = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_staff_collection().update_one(
            {"public_id": user_id},
            {"$set": {"last_login_at": now, "updated_at": now}},
        )
        return
    get_db().execute(
        "UPDATE staff_users SET last_login_at = ?, updated_at = ? WHERE public_id = ?",
        (now, now, user_id),
    )
    get_db().commit()


def all_staff_users() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_staff_collection().find({}).sort(
            [("status", ASCENDING), ("full_name", ASCENDING)]
        )
    else:
        rows = get_db().execute(
            "SELECT * FROM staff_users ORDER BY status ASC, full_name COLLATE NOCASE ASC"
        ).fetchall()
    return [staff_record_for_template(row) for row in rows]


def partner_code_exists(partner_code: str) -> bool:
    if database_backend() == "mongodb":
        return get_mongo_partners_collection().find_one({"partner_code": partner_code}, {"_id": 1}) is not None
    return get_db().execute(
        "SELECT 1 FROM partners WHERE partner_code = ? COLLATE NOCASE", (partner_code,)
    ).fetchone() is not None


def generate_partner_code() -> str:
    for _ in range(20):
        code = f"SB{secrets.randbelow(1_000_000):06d}"
        if not partner_code_exists(code):
            return code
    raise RuntimeError("Could not allocate a unique partner code.")


def fetch_partner(partner_id: str) -> dict[str, object] | None:
    if not partner_id:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_partners_collection().find_one({"public_id": partner_id})
    else:
        row = get_db().execute("SELECT * FROM partners WHERE public_id = ?", (partner_id,)).fetchone()
    return normalize_partner_record(row) if row is not None else None


def fetch_partner_by_email(email: str) -> dict[str, object] | None:
    email_key = normalize_staff_email(email)
    if not email_key:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_partners_collection().find_one({"email_key": email_key})
    else:
        row = get_db().execute("SELECT * FROM partners WHERE email_key = ?", (email_key,)).fetchone()
    return normalize_partner_record(row) if row is not None else None


def fetch_partner_by_code(partner_code: str, *, approved_only: bool = False) -> dict[str, object] | None:
    code = normalize_referral_code(partner_code)
    if not code:
        return None
    if database_backend() == "mongodb":
        query: dict[str, object] = {"partner_code": code}
        if approved_only:
            query["status"] = "APPROVED"
        row = get_mongo_partners_collection().find_one(query)
    else:
        sql = "SELECT * FROM partners WHERE partner_code = ? COLLATE NOCASE"
        params: tuple[object, ...] = (code,)
        if approved_only:
            sql += " AND status = ?"
            params += ("APPROVED",)
        row = get_db().execute(sql, params).fetchone()
    return normalize_partner_record(row) if row is not None else None


def create_partner(data: Mapping[str, str], password_hash: str) -> str:
    now = utc_now_iso()
    payload = {
        "public_id": uuid.uuid4().hex[:12], "partner_code": generate_partner_code(),
        "full_name": data["full_name"], "email": data["email"], "email_key": normalize_staff_email(data["email"]),
        "phone": data["phone"], "phone_key": normalize_partner_phone(data["phone"]),
        "whatsapp": data.get("whatsapp") or data["phone"], "location": data["location"],
        "partner_type": data["partner_type"], "company_name": data.get("company_name", ""),
        "experience_notes": data.get("experience_notes", ""), "referral_source": data.get("referral_source", ""),
        "status": "PENDING", "password_hash": password_hash, "reviewed_by": "", "reviewed_at": "",
        "review_note": "", "last_login_at": "", "created_at": now, "updated_at": now,
    }
    try:
        if database_backend() == "mongodb":
            get_mongo_partners_collection().insert_one(payload)
        else:
            get_db().execute(
                """INSERT INTO partners (
                    public_id, partner_code, full_name, email, email_key, phone, phone_key, whatsapp,
                    location, partner_type, company_name, experience_notes, referral_source, status,
                    password_hash, reviewed_by, reviewed_at, review_note, last_login_at, created_at, updated_at
                ) VALUES (
                    :public_id, :partner_code, :full_name, :email, :email_key, :phone, :phone_key, :whatsapp,
                    :location, :partner_type, :company_name, :experience_notes, :referral_source, :status,
                    :password_hash, :reviewed_by, :reviewed_at, :review_note, :last_login_at, :created_at, :updated_at
                )""",
                payload,
            )
            get_db().commit()
    except (sqlite3.IntegrityError, DuplicateKeyError) as exc:
        raise ValueError("A partner account already exists for that email address.") from exc
    return str(payload["public_id"])


def authenticate_partner(email: str, password: str) -> dict[str, object] | None:
    partner = fetch_partner_by_email(email)
    if partner is None or not verify_password(str(partner.get("password_hash") or ""), password):
        return None
    return partner


def all_partners() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_partners_collection().find({}).sort([("status", ASCENDING), ("created_at", DESCENDING)])
    else:
        rows = get_db().execute("SELECT * FROM partners ORDER BY status ASC, created_at DESC").fetchall()
    return [partner_record_for_template(row) for row in rows]


def update_partner_status(partner_id: str, *, status: str, review_note: str, reviewed_by: str) -> None:
    now = utc_now_iso()
    payload = {"status": status, "review_note": review_note, "reviewed_by": reviewed_by, "reviewed_at": now, "updated_at": now}
    if database_backend() == "mongodb":
        result = get_mongo_partners_collection().update_one({"public_id": partner_id}, {"$set": payload})
        if not result.matched_count:
            abort(404)
    else:
        cursor = get_db().execute(
            "UPDATE partners SET status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ? WHERE public_id = ?",
            (status, review_note, reviewed_by, now, now, partner_id),
        )
        get_db().commit()
        if not cursor.rowcount:
            abort(404)


def update_partner_last_login(partner_id: str) -> None:
    now = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_partners_collection().update_one({"public_id": partner_id}, {"$set": {"last_login_at": now, "updated_at": now}})
    else:
        get_db().execute("UPDATE partners SET last_login_at = ?, updated_at = ? WHERE public_id = ?", (now, now, partner_id))
        get_db().commit()


def update_partner_profile(partner_id: str, data: Mapping[str, str]) -> None:
    payload = {
        "full_name": data["full_name"], "phone": data["phone"], "phone_key": normalize_partner_phone(data["phone"]),
        "whatsapp": data.get("whatsapp") or data["phone"], "location": data["location"],
        "partner_type": data["partner_type"], "company_name": data.get("company_name", ""),
        "experience_notes": data.get("experience_notes", ""), "referral_source": data.get("referral_source", ""),
        "updated_at": utc_now_iso(),
    }
    if database_backend() == "mongodb":
        get_mongo_partners_collection().update_one({"public_id": partner_id}, {"$set": payload})
    else:
        get_db().execute(
            """UPDATE partners SET full_name = :full_name, phone = :phone, phone_key = :phone_key,
               whatsapp = :whatsapp, location = :location, partner_type = :partner_type,
               company_name = :company_name, experience_notes = :experience_notes,
               referral_source = :referral_source, updated_at = :updated_at WHERE public_id = :partner_id""",
            {**payload, "partner_id": partner_id},
        )
        get_db().commit()


def update_staff_access(user_id: str, *, role: str, status: str, full_name: str) -> None:
    now = utc_now_iso()
    payload = {
        "role": role,
        "status": status,
        "full_name": " ".join(full_name.split()),
        "updated_at": now,
    }
    if database_backend() == "mongodb":
        result = get_mongo_staff_collection().update_one({"public_id": user_id}, {"$set": payload})
        if not result.matched_count:
            abort(404)
        return
    cursor = get_db().execute(
        "UPDATE staff_users SET role = ?, status = ?, full_name = ?, updated_at = ? WHERE public_id = ?",
        (role, status, payload["full_name"], now, user_id),
    )
    get_db().commit()
    if not cursor.rowcount:
        abort(404)


def active_super_admin_count() -> int:
    query = {"role": "SUPER_ADMIN", "status": "ACTIVE"}
    if database_backend() == "mongodb":
        return int(get_mongo_staff_collection().count_documents(query))
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM staff_users WHERE role = 'SUPER_ADMIN' AND status = 'ACTIVE'"
    ).fetchone()
    return int(row["count"] or 0)


def create_staff_invitation(
    *, full_name: str, email: str, role: str, invited_by: str
) -> tuple[str, str]:
    now = utc_now_iso()
    token = secrets.token_urlsafe(32)
    payload = {
        "public_id": uuid.uuid4().hex[:16],
        "email": normalize_staff_email(email),
        "email_key": normalize_staff_email(email),
        "full_name": " ".join(full_name.split()),
        "role": role,
        "token_hash": hash_invitation_token(token),
        "status": "PENDING",
        "invited_by": invited_by,
        "accepted_by": "",
        "expires_at": (datetime.now(UTC) + timedelta(hours=app.config["STAFF_INVITATION_HOURS"])).isoformat(),
        "created_at": now,
        "updated_at": now,
    }
    if database_backend() == "mongodb":
        get_mongo_staff_invitations_collection().update_many(
            {"email_key": payload["email_key"], "status": "PENDING"},
            {"$set": {"status": "REVOKED", "updated_at": now}},
        )
        get_mongo_staff_invitations_collection().insert_one(payload)
    else:
        get_db().execute(
            "UPDATE staff_invitations SET status = 'REVOKED', updated_at = ? WHERE email_key = ? AND status = 'PENDING'",
            (now, payload["email_key"]),
        )
        get_db().execute(
            """
            INSERT INTO staff_invitations (
                public_id, email, email_key, full_name, role, token_hash, status,
                invited_by, accepted_by, expires_at, created_at, updated_at
            ) VALUES (
                :public_id, :email, :email_key, :full_name, :role, :token_hash, :status,
                :invited_by, :accepted_by, :expires_at, :created_at, :updated_at
            )
            """,
            payload,
        )
        get_db().commit()
    return str(payload["public_id"]), token


def fetch_staff_invitation_by_token(token: str) -> dict[str, object] | None:
    token_hash = hash_invitation_token(token)
    if database_backend() == "mongodb":
        row = get_mongo_staff_invitations_collection().find_one({"token_hash": token_hash})
    else:
        row = get_db().execute(
            "SELECT * FROM staff_invitations WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
    return normalize_staff_invitation_record(row) if row is not None else None


def fetch_staff_invitation(invitation_id: str) -> dict[str, object] | None:
    identifier = str(invitation_id or "").strip()
    if not identifier:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_staff_invitations_collection().find_one({"public_id": identifier})
    else:
        row = get_db().execute(
            "SELECT * FROM staff_invitations WHERE public_id = ?",
            (identifier,),
        ).fetchone()
    return normalize_staff_invitation_record(row) if row is not None else None


def invitation_is_active(invitation: Mapping[str, object]) -> bool:
    if invitation.get("status") != "PENDING":
        return False
    try:
        expires_at = datetime.fromisoformat(str(invitation.get("expires_at") or ""))
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > datetime.now(UTC)


def pending_staff_invitations() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_staff_invitations_collection().find({"status": "PENDING"}).sort(
            "created_at", DESCENDING
        )
    else:
        rows = get_db().execute(
            "SELECT * FROM staff_invitations WHERE status = 'PENDING' ORDER BY created_at DESC"
        ).fetchall()
    invitations = [normalize_staff_invitation_record(row) for row in rows]
    for invitation in invitations:
        invitation["is_expired"] = not invitation_is_active(invitation)
    return invitations


def update_staff_invitation_status(
    invitation_id: str, status: str, *, accepted_by: str = ""
) -> None:
    now = utc_now_iso()
    if database_backend() == "mongodb":
        result = get_mongo_staff_invitations_collection().update_one(
            {"public_id": invitation_id},
            {"$set": {"status": status, "accepted_by": accepted_by, "updated_at": now}},
        )
        if not result.matched_count:
            abort(404)
        return
    cursor = get_db().execute(
        "UPDATE staff_invitations SET status = ?, accepted_by = ?, updated_at = ? WHERE public_id = ?",
        (status, accepted_by, now, invitation_id),
    )
    get_db().commit()
    if not cursor.rowcount:
        abort(404)


def listing_defaults() -> dict[str, object]:
    return {
        "title": "",
        "status": "For Sale",
        "availability": "Available",
        "property_type": "",
        "district": "",
        "address": "",
        "longitude": "",
        "latitude": "",
        "gallery_paths": [],
        "virtual_tour_url": "",
        "documentation_summary": "",
        "documentation_verified": 0,
        "payment_plan_summary": "",
        "is_serviced": 0,
        "has_power_24_7": 0,
        "is_flood_free": 0,
        "near_express": 0,
        "near_schools": 0,
        "near_markets": 0,
        "verified_property": 0,
        "verified_landlord": 0,
        "price": "",
        "price_suffix": "",
        "bedrooms": 0,
        "bathrooms": 0,
        "area_sqm": 0,
        "summary": "",
        "description": "",
        "featured": 0,
        "published": 1,
        "image_path": "",
    }


def row_to_form_data(row: sqlite3.Row) -> dict[str, object]:
    data = listing_defaults()
    for key in data:
        if key in row.keys():
            data[key] = row[key]
    return data


def normalize_digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def normalized_email_address(value: str) -> str:
    return parseaddr(str(value or "").strip())[1].strip().lower()


def is_placeholder_email(value: str) -> bool:
    email = normalized_email_address(value)
    if not email:
        return True
    if email == DEFAULT_CONTACT_EMAIL.strip().lower():
        return True
    local, _separator, domain = email.partition("@")
    if domain in {"example.com", "example.org", "example.net"}:
        return True
    if email in {"yourgmail@gmail.com", "you@gmail.com"}:
        return True
    if local.startswith("your") and domain == "gmail.com":
        return True
    return False


def effective_contact_email(value: str) -> str:
    email = normalized_email_address(value)
    if email and not is_placeholder_email(email):
        return email
    smtp_from = normalized_email_address(app.config.get("SMTP_FROM_EMAIL", ""))
    if smtp_from:
        return smtp_from
    smtp_username = normalized_email_address(app.config.get("SMTP_USERNAME", ""))
    if smtp_username:
        return smtp_username
    return email


def site_settings_defaults() -> dict[str, str]:
    return {
        "site_name": app.config["SITE_NAME"],
        "contact_email": app.config["CONTACT_EMAIL"],
        "contact_phone_display": app.config["CONTACT_PHONE_DISPLAY"],
        "contact_phone_raw": app.config["CONTACT_PHONE_RAW"],
        "contact_phone_configured": app.config["CONTACT_PHONE_DISPLAY"] != DEFAULT_PHONE_DISPLAY,
        "whatsapp_phone": app.config["WHATSAPP_PHONE"],
        "office_address": app.config["OFFICE_ADDRESS"],
        "coverage_area": app.config["COVERAGE_AREA"],
        "footer_summary": app.config["FOOTER_SUMMARY"],
        "email_sender_name": app.config["EMAIL_SENDER_NAME"],
        "email_brand_tagline": app.config["EMAIL_BRAND_TAGLINE"],
        "email_brand_market_line": app.config["EMAIL_BRAND_MARKET_LINE"],
        "email_footer_note": app.config["EMAIL_FOOTER_NOTE"],
        "homepage_hero_heading": app.config["HOMEPAGE_HERO_HEADING"],
        "homepage_hero_intro": app.config["HOMEPAGE_HERO_INTRO"],
        "homepage_primary_cta": app.config["HOMEPAGE_PRIMARY_CTA"],
        "homepage_secondary_cta": app.config["HOMEPAGE_SECONDARY_CTA"],
        "homepage_trust_signal_1": app.config["HOMEPAGE_TRUST_SIGNAL_1"],
        "homepage_trust_signal_2": app.config["HOMEPAGE_TRUST_SIGNAL_2"],
        "homepage_trust_signal_3": app.config["HOMEPAGE_TRUST_SIGNAL_3"],
    }


def persisted_site_settings() -> dict[str, str]:
    if database_backend() == "mongodb":
        document = get_mongo_settings_collection().find_one({"_id": "site_preferences"}) or {}
        return {
            key: str(document.get(key) or "").strip()
            for key in SITE_SETTING_FIELDS
            if str(document.get(key) or "").strip()
        }

    rows = get_db().execute(
        "SELECT setting_key, setting_value FROM site_preferences WHERE setting_key IN ({})".format(
            ", ".join("?" for _ in SITE_SETTING_FIELDS)
        ),
        SITE_SETTING_FIELDS,
    ).fetchall()
    return {
        str(row["setting_key"]): str(row["setting_value"] or "").strip()
        for row in rows
        if str(row["setting_value"] or "").strip()
    }


def update_site_settings(data: Mapping[str, str]) -> None:
    payload = {key: str(data.get(key) or "").strip() for key in SITE_SETTING_FIELDS}
    now = utc_now_iso()

    if database_backend() == "mongodb":
        document = {"_id": "site_preferences", **payload, "updated_at": now}
        get_mongo_settings_collection().update_one(
            {"_id": "site_preferences"},
            {"$set": document},
            upsert=True,
        )
        return

    db = get_db()
    db.executemany(
        """
        INSERT INTO site_preferences (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        [(key, value, now) for key, value in payload.items()],
    )
    db.commit()


def normalize_string_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
        if not isinstance(parsed, list):
            return []
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def normalize_coordinate(
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    if value in {None, ""}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < minimum or parsed > maximum:
        return None
    return round(parsed, 6)


def fallback_listing_coordinates(listing: Mapping[str, object]) -> tuple[float, float] | None:
    district = str(listing.get("district") or "").strip().lower()
    address = str(listing.get("address") or "").strip().lower()
    haystack = " ".join(part for part in (district, address) if part)
    if not haystack:
        return None
    for key, coordinates in DISTRICT_CENTER_COORDINATES.items():
        if key in haystack:
            return coordinates
    return None


def resolve_listing_coordinates(listing: Mapping[str, object]) -> tuple[float | None, float | None, str]:
    longitude = normalize_coordinate(listing.get("longitude"), minimum=-180, maximum=180)
    latitude = normalize_coordinate(listing.get("latitude"), minimum=-90, maximum=90)
    if longitude is not None and latitude is not None:
        return longitude, latitude, "exact"
    fallback = fallback_listing_coordinates(listing)
    if fallback is not None:
        return fallback[0], fallback[1], "approximate"
    return None, None, "missing"


def site_settings() -> dict[str, str | bool]:
    merged = site_settings_defaults()
    merged.update(persisted_site_settings())
    whatsapp_digits = normalize_digits(merged["whatsapp_phone"])
    phone_digits = normalize_digits(merged["contact_phone_raw"]) or whatsapp_digits
    contact_email = effective_contact_email(merged["contact_email"])
    contact_email_configured = bool(contact_email) and not is_placeholder_email(contact_email)
    contact_phone_configured = (
        10 <= len(phone_digits) <= 15
        and phone_digits != normalize_digits(DEFAULT_PHONE_RAW)
        and str(merged.get("contact_phone_display") or "").strip() != DEFAULT_PHONE_DISPLAY
    )
    whatsapp_configured = (
        10 <= len(whatsapp_digits) <= 15
        and whatsapp_digits != normalize_digits(DEFAULT_WHATSAPP_PHONE)
    )
    email_sender_name = str(merged.get("email_sender_name") or "").strip() or merged["site_name"]
    email_brand_tagline = (
        str(merged.get("email_brand_tagline") or "").strip() or DEFAULT_EMAIL_BRAND_TAGLINE
    )
    email_brand_market_line = (
        str(merged.get("email_brand_market_line") or "").strip() or DEFAULT_EMAIL_BRAND_MARKET_LINE
    )
    email_footer_note = str(merged.get("email_footer_note") or "").strip() or merged["footer_summary"]
    homepage_hero_heading = (
        str(merged.get("homepage_hero_heading") or "").strip() or DEFAULT_HOMEPAGE_HERO_HEADING
    )
    homepage_hero_intro = (
        str(merged.get("homepage_hero_intro") or "").strip() or DEFAULT_HOMEPAGE_HERO_INTRO
    )
    homepage_primary_cta = (
        str(merged.get("homepage_primary_cta") or "").strip() or DEFAULT_HOMEPAGE_PRIMARY_CTA
    )
    homepage_secondary_cta = (
        str(merged.get("homepage_secondary_cta") or "").strip() or DEFAULT_HOMEPAGE_SECONDARY_CTA
    )
    homepage_trust_signals = [
        str(merged.get("homepage_trust_signal_1") or "").strip() or DEFAULT_HOMEPAGE_TRUST_SIGNAL_1,
        str(merged.get("homepage_trust_signal_2") or "").strip() or DEFAULT_HOMEPAGE_TRUST_SIGNAL_2,
        str(merged.get("homepage_trust_signal_3") or "").strip() or DEFAULT_HOMEPAGE_TRUST_SIGNAL_3,
    ]
    if homepage_hero_heading == LEGACY_HOMEPAGE_HERO_HEADING:
        homepage_hero_heading = DEFAULT_HOMEPAGE_HERO_HEADING
    if homepage_hero_intro == LEGACY_HOMEPAGE_HERO_INTRO:
        homepage_hero_intro = DEFAULT_HOMEPAGE_HERO_INTRO
    homepage_trust_signals = [
        DEFAULT_HOMEPAGE_TRUST_SIGNAL_1 if homepage_trust_signals[0] == LEGACY_HOMEPAGE_TRUST_SIGNAL_1 else homepage_trust_signals[0],
        DEFAULT_HOMEPAGE_TRUST_SIGNAL_2 if homepage_trust_signals[1] == LEGACY_HOMEPAGE_TRUST_SIGNAL_2 else homepage_trust_signals[1],
        DEFAULT_HOMEPAGE_TRUST_SIGNAL_3 if homepage_trust_signals[2] == LEGACY_HOMEPAGE_TRUST_SIGNAL_3 else homepage_trust_signals[2],
    ]
    using_default_credentials = (
        app.config["ADMIN_USERNAME"] == DEFAULT_ADMIN_USERNAME
        and admin_password_is_default()
    )
    return {
        "site_name": merged["site_name"],
        "contact_email": contact_email,
        "contact_email_configured": contact_email_configured,
        "contact_phone_display": merged["contact_phone_display"],
        "contact_phone_raw": phone_digits,
        "contact_phone_configured": contact_phone_configured,
        "whatsapp_phone": whatsapp_digits,
        "whatsapp_configured": whatsapp_configured,
        "office_address": merged["office_address"],
        "coverage_area": merged["coverage_area"],
        "footer_summary": merged["footer_summary"],
        "email_sender_name": email_sender_name,
        "email_brand_tagline": email_brand_tagline,
        "email_brand_market_line": email_brand_market_line,
        "email_footer_note": email_footer_note,
        "homepage_hero_heading": homepage_hero_heading,
        "homepage_hero_intro": homepage_hero_intro,
        "homepage_primary_cta": homepage_primary_cta,
        "homepage_secondary_cta": homepage_secondary_cta,
        "homepage_trust_signal_1": homepage_trust_signals[0],
        "homepage_trust_signal_2": homepage_trust_signals[1],
        "homepage_trust_signal_3": homepage_trust_signals[2],
        "homepage_trust_signals": homepage_trust_signals,
        "using_default_credentials": using_default_credentials,
    }


def smtp_is_configured() -> bool:
    return all(
        [
            app.config["SMTP_HOST"],
            app.config["SMTP_USERNAME"],
            app.config["SMTP_PASSWORD"],
            app.config["SMTP_FROM_EMAIL"],
        ]
    )


def startup_validation_issues() -> tuple[list[str], list[str]]:
    blocking_errors: list[str] = []
    warnings: list[str] = []

    if app.config["DATABASE_BACKEND"] == "mongodb" and not app.config["MONGODB_URI"]:
        blocking_errors.append(
            "MongoDB backend is selected but STRUCTUREBASE_MONGODB_URI is empty."
        )
    elif app.config["DATABASE_BACKEND"] == "mongodb" and not is_valid_mongodb_uri(app.config["MONGODB_URI"]):
        blocking_errors.append(
            "MongoDB backend is selected but STRUCTUREBASE_MONGODB_URI is not a valid MongoDB URI."
        )
    elif app.config["DATABASE_BACKEND"] == "mongodb" and is_placeholder_mongodb_uri(app.config["MONGODB_URI"]):
        blocking_errors.append(
            "STRUCTUREBASE_MONGODB_URI still contains placeholder text. "
            "Paste the real MongoDB Atlas connection string from Atlas > Connect > Drivers."
        )

    if app.config["STORAGE_BACKEND"] in {"cloudinary", "r2"} and not cloudinary_is_configured():
        blocking_errors.append(
            "Cloud storage is selected but Cloudinary credentials are incomplete."
        )
    elif app.config["STORAGE_BACKEND"] in {"cloudinary", "r2"} and any(
        is_placeholder_cloudinary_value(value)
        for value in (
            app.config["CLOUDINARY_URL"],
            app.config["CLOUDINARY_CLOUD_NAME"],
            app.config["CLOUDINARY_API_KEY"],
            app.config["CLOUDINARY_API_SECRET"],
        )
        if value
    ):
        blocking_errors.append(
            "Cloudinary configuration still contains placeholder text. "
            "Paste real Cloudinary credentials or set STRUCTUREBASE_STORAGE_BACKEND=local."
        )

    smtp_values = [
        app.config["SMTP_HOST"],
        app.config["SMTP_USERNAME"],
        app.config["SMTP_PASSWORD"],
        app.config["SMTP_FROM_EMAIL"],
    ]
    if any(smtp_values) and not smtp_is_configured():
        blocking_errors.append(
            "SMTP settings are partially configured. Set all SMTP fields or clear them."
        )

    if app.config["IS_PRODUCTION"] and app.config["SECRET_KEY"] == DEFAULT_SECRET_KEY:
        blocking_errors.append(
            "STRUCTUREBASE_SECRET is still using the default placeholder value."
        )

    if (
        app.config["IS_PRODUCTION"]
        and not app.config["ADMIN_PASSWORD_HASH"]
        and app.config["ADMIN_PASSWORD"] == DEFAULT_ADMIN_PASSWORD
    ):
        blocking_errors.append(
            "Admin credentials are still using the default password."
        )

    if app.config["IS_PRODUCTION"] and not app.config["SESSION_COOKIE_SECURE"]:
        blocking_errors.append(
            "Secure session cookies must be enabled in production."
        )

    if app.config["IS_PRODUCTION"] and database_backend() == "sqlite":
        warnings.append(
            "SQLite is active in production mode; concurrency and recovery guarantees are limited."
        )

    if app.config["IS_PRODUCTION"] and app.config["TRUST_PROXY_COUNT"] < 1:
        warnings.append(
            "Trusted proxy count is zero in production; client IP and scheme detection may be inaccurate."
        )

    public_base_url = str(app.config.get("PUBLIC_BASE_URL") or "").strip()
    if public_base_url:
        parsed_public_url = urlsplit(public_base_url)
        if (
            parsed_public_url.scheme not in {"http", "https"}
            or not parsed_public_url.netloc
            or parsed_public_url.path not in {"", "/"}
            or parsed_public_url.query
            or parsed_public_url.fragment
        ):
            blocking_errors.append(
                "STRUCTUREBASE_PUBLIC_BASE_URL must be an http(s) origin without a path, query, or fragment."
            )
    elif app.config["SEARCH_INDEXING_ENABLED"]:
        warnings.append(
            "Search indexing is enabled without STRUCTUREBASE_PUBLIC_BASE_URL; canonical URLs will use the request host."
        )

    if app.config["IS_PRODUCTION"] and not app.config["SEARCH_INDEXING_ENABLED"]:
        warnings.append(
            "Search indexing is disabled. Keep this for client acceptance and enable it only on the final public domain."
        )

    if is_placeholder_email(str(app.config["CONTACT_EMAIL"] or "")):
        warnings.append(
            "Contact email still uses a placeholder or fallback value."
        )

    if app.config["MAPBOX_TOKEN"] == "YOUR_MAPBOX_TOKEN_HERE":
        warnings.append("Mapbox token is still using the placeholder value.")

    return blocking_errors, warnings


def enforce_startup_checks() -> None:
    blocking_errors, warnings = startup_validation_issues()
    startup_event = {
        "event": "startup.config",
        "environment": app.config["ENVIRONMENT"],
        "strict_checks": bool(app.config["STRICT_STARTUP_CHECKS"]),
        "database_backend": database_backend(),
        "storage_backend": storage_backend(),
        "smtp_configured": smtp_is_configured(),
        "trust_proxy_count": int(app.config["TRUST_PROXY_COUNT"]),
    }
    app.logger.info(json.dumps(startup_event, separators=(",", ":")))

    for warning in warnings:
        app.logger.warning("Startup warning: %s", warning)

    if blocking_errors:
        for error in blocking_errors:
            app.logger.error("Startup check failed: %s", error)
        if app.config["STRICT_STARTUP_CHECKS"]:
            raise RuntimeError("Startup checks failed. Review logs for the blocking configuration issues.")
        app.logger.warning("Startup checks found blocking issues, but strict checks are disabled.")


def email_logo_asset() -> tuple[str, bytes] | None:
    if not EMAIL_LOGO_PATH.exists():
        return None
    return "png", EMAIL_LOGO_PATH.read_bytes()


def email_sender_display_name() -> str:
    settings = site_settings()
    return str(settings.get("email_sender_name") or settings.get("site_name") or "").strip()


def delivery_error_summary(exc: Exception) -> str:
    message = " ".join(str(exc).split()).strip()
    if not message:
        message = exc.__class__.__name__
    return message[:180]


def enquiry_sender_display_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    cleaned = re.sub(r"[^\w\s'’.-]", "", cleaned).strip(" .,-")
    return cleaned or "A client"


def enquiry_greeting_line(value: str) -> str:
    candidate = enquiry_sender_display_name(value)
    if candidate == "A client":
        return "Hello there,"
    first_name = re.split(r"\s+", candidate, maxsplit=1)[0]
    if len(first_name) < 2 or first_name.lower() in {"test", "admin", "unknown", "none"}:
        return "Hello there,"
    if first_name.isupper() and len(first_name) <= 20:
        first_name = first_name.title()
    return f"Hello {first_name},"


def send_email_message(
    *,
    to_address: str,
    subject: str,
    text_body: str,
    html_body: str = "",
    reply_to: str = "",
    embedded_logo_cid: str = "",
) -> None:
    if not smtp_is_configured():
        raise RuntimeError("SMTP is not configured.")

    message = EmailMessage()
    message["Subject"] = subject
    sender_name = email_sender_display_name()
    message["From"] = (
        formataddr((sender_name, app.config["SMTP_FROM_EMAIL"]))
        if sender_name
        else app.config["SMTP_FROM_EMAIL"]
    )
    message["To"] = to_address
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
        if embedded_logo_cid:
            logo_asset = email_logo_asset()
            if logo_asset is not None:
                subtype, logo_bytes = logo_asset
                html_part = message.get_payload()[-1]
                html_part.add_related(
                    logo_bytes,
                    maintype="image",
                    subtype=subtype,
                    cid=f"<{embedded_logo_cid}>",
                    filename=f"logo.{subtype}",
                    disposition="inline",
                )

    host = app.config["SMTP_HOST"]
    port = int(app.config["SMTP_PORT"])
    username = app.config["SMTP_USERNAME"]
    password = app.config["SMTP_PASSWORD"]

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)


def send_staff_invitation_email(
    *, full_name: str, email: str, role: str, invitation_url: str
) -> dict[str, str | bool]:
    result: dict[str, str | bool] = {"sent": False, "error": ""}
    settings = site_settings()
    site_name = str(settings.get("site_name") or "Structurebase")
    text_body = (
        f"Hello {full_name},\n\n"
        f"You have been invited to join the {site_name} staff workspace as "
        f"{role_label(role)}.\n\n"
        f"Create your account using this secure link:\n{invitation_url}\n\n"
        f"The link expires in {app.config['STAFF_INVITATION_HOURS']} hours and can only be used once. "
        "If you were not expecting this invitation, you can ignore this email.\n"
    )
    try:
        send_email_message(
            to_address=email,
            subject=f"Join the {site_name} staff workspace",
            text_body=text_body,
        )
        result["sent"] = True
    except Exception as exc:
        app.logger.exception("Failed to send staff invitation email.")
        result["error"] = delivery_error_summary(exc)
    return result


def send_inspection_update_email(inspection: Mapping[str, object], *, event: str) -> dict[str, object]:
    """Send best-effort inspection notifications without blocking the booking workflow."""
    result: dict[str, object] = {"admin_sent": False, "client_sent": False, "errors": []}
    if not smtp_is_configured():
        return result
    settings = site_settings()
    site_name = str(settings.get("site_name") or "Structurebase")
    reference = f"INSP-{str(inspection.get('id') or inspection.get('public_id') or '').upper()}"
    status_label = INSPECTION_STATUS_LABELS.get(str(inspection.get("status") or "REQUESTED"), "Requested")
    schedule = f"{inspection.get('requested_date')} at {inspection.get('requested_time')}"
    subject = f"{site_name} inspection {event}: {inspection.get('listing_title')}"
    body = (
        f"Inspection reference: {reference}\n"
        f"Property: {inspection.get('listing_title')}\n"
        f"Client: {inspection.get('name')}\n"
        f"Schedule: {schedule}\n"
        f"Status: {status_label}\n\n"
        "A team member will contact you if any further coordination is needed."
    )
    recipients = (
        ("admin_sent", normalized_email_address(str(settings.get("contact_email") or ""))),
        ("client_sent", normalized_email_address(str(inspection.get("email") or ""))),
    )
    for key, recipient in recipients:
        if not recipient:
            continue
        try:
            send_email_message(to_address=recipient, subject=subject, text_body=body)
            result[key] = True
        except Exception as exc:
            app.logger.exception("Failed to send %s inspection notification for %s", key, reference)
            result["errors"].append(delivery_error_summary(exc))
    return result


def send_partner_notification(partner: Mapping[str, object], *, audience: str, event: str) -> bool:
    if not smtp_is_configured():
        return False
    settings = site_settings()
    site_name = str(settings.get("site_name") or "Structurebase")
    if audience == "admin":
        recipient = normalized_email_address(str(settings.get("contact_email") or ""))
        subject = f"New {site_name} partner application"
        body = (
            f"A partner application requires review.\n\n"
            f"Applicant: {partner.get('full_name')}\nEmail: {partner.get('email')}\n"
            f"Location: {partner.get('location')}\nPartner code: {partner.get('partner_code')}\n"
        )
    else:
        recipient = normalized_email_address(str(partner.get("email") or ""))
        subject = f"Your {site_name} partner application is {event}"
        body = (
            f"Hello {partner.get('full_name')},\n\n"
            f"Your partner application ({partner.get('partner_code')}) is now {event}.\n"
            f"{str(partner.get('review_note') or '').strip()}\n\n"
            f"Sign in at {url_for('partner_login', _external=True)}"
        )
    if not recipient:
        return False
    try:
        send_email_message(to_address=recipient, subject=subject, text_body=body)
        return True
    except Exception:
        app.logger.exception("Failed to send partner %s notification for %s", audience, partner.get("partner_code"))
        return False


REFERRAL_COOKIE_NAME = "sb_referral"


def referral_token_hash(token: str) -> str:
    return hmac.new(
        str(app.config["SECRET_KEY"]).encode("utf-8"),
        str(token or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def referral_cookie_data() -> dict[str, dict[str, str]]:
    if hasattr(g, "referral_cookie_data"):
        return g.referral_cookie_data
    raw_cookie = request.cookies.get(REFERRAL_COOKIE_NAME, "")
    data: dict[str, dict[str, str]] = {}
    if raw_cookie:
        try:
            loaded = URLSafeSerializer(app.config["SECRET_KEY"], salt="structurebase-referral-v1").loads(raw_cookie)
            if isinstance(loaded, Mapping):
                for scope, entry in loaded.items():
                    if isinstance(scope, str) and isinstance(entry, Mapping):
                        token = str(entry.get("token") or "")
                        expires_at = str(entry.get("expires_at") or "")
                        if token and attribution_is_active(expires_at):
                            data[scope] = {"token": token, "expires_at": expires_at}
        except BadSignature:
            data = {}
    g.referral_cookie_data = data
    return data


def mark_referral_cookie_changed() -> None:
    g.referral_cookie_changed = True


def persist_referral_cookie(response):
    if not getattr(g, "referral_cookie_changed", False):
        return response
    data = getattr(g, "referral_cookie_data", {})
    if data:
        signed = URLSafeSerializer(app.config["SECRET_KEY"], salt="structurebase-referral-v1").dumps(data)
        response.set_cookie(
            REFERRAL_COOKIE_NAME, signed,
            max_age=int(app.config["REFERRAL_ATTRIBUTION_DAYS"]) * 86400,
            secure=bool(app.config["SESSION_COOKIE_SECURE"]), httponly=True, samesite="Lax", path="/",
        )
    else:
        response.delete_cookie(
            REFERRAL_COOKIE_NAME, secure=bool(app.config["SESSION_COOKIE_SECURE"]), httponly=True,
            samesite="Lax", path="/",
        )
    return response


def create_referral_event(referral_id: str, event_type: str, metadata: Mapping[str, object] | None = None) -> None:
    payload = {
        "public_id": uuid.uuid4().hex[:12], "referral_id": referral_id, "event_type": event_type,
        "metadata": dict(metadata or {}), "created_at": utc_now_iso(),
    }
    if database_backend() == "mongodb":
        get_mongo_referral_events_collection().insert_one(payload)
    else:
        get_db().execute(
            "INSERT INTO referral_events (public_id, referral_id, event_type, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (payload["public_id"], referral_id, event_type, json.dumps(payload["metadata"], separators=(",", ":")), payload["created_at"]),
        )
        get_db().commit()


def fetch_referral(referral_id: str) -> dict[str, object] | None:
    if not referral_id:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_referrals_collection().find_one({"public_id": referral_id})
    else:
        row = get_db().execute("SELECT * FROM referrals WHERE public_id = ?", (referral_id,)).fetchone()
    return normalize_referral_record(row) if row is not None else None


def fetch_referral_by_token(token: str) -> dict[str, object] | None:
    token_digest = referral_token_hash(token)
    if database_backend() == "mongodb":
        row = get_mongo_referrals_collection().find_one({"token_hash": token_digest})
    else:
        row = get_db().execute("SELECT * FROM referrals WHERE token_hash = ?", (token_digest,)).fetchone()
    return normalize_referral_record(row) if row is not None else None


def create_referral_record(
    *, token: str, partner: Mapping[str, object], listing_id: str, listing_title: str, path: str
) -> dict[str, object]:
    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    expires_at = (now_dt + timedelta(days=int(app.config["REFERRAL_ATTRIBUTION_DAYS"]))).isoformat()
    payload = {
        "public_id": uuid.uuid4().hex[:12], "token_hash": referral_token_hash(token),
        "partner_id": str(partner["id"]), "partner_code": str(partner["partner_code"]),
        "listing_id": listing_id, "listing_title": listing_title, "status": "VISITED",
        "lead_id": "", "inspection_id": "", "first_path": path[:500], "last_path": path[:500],
        "visit_count": 1, "first_seen_at": now, "last_seen_at": now, "expires_at": expires_at,
        "created_at": now, "updated_at": now,
    }
    if database_backend() == "mongodb":
        get_mongo_referrals_collection().insert_one(payload)
    else:
        get_db().execute(
            """INSERT INTO referrals (
                public_id, token_hash, partner_id, partner_code, listing_id, listing_title, status,
                lead_id, inspection_id, first_path, last_path, visit_count, first_seen_at,
                last_seen_at, expires_at, created_at, updated_at
            ) VALUES (
                :public_id, :token_hash, :partner_id, :partner_code, :listing_id, :listing_title, :status,
                :lead_id, :inspection_id, :first_path, :last_path, :visit_count, :first_seen_at,
                :last_seen_at, :expires_at, :created_at, :updated_at
            )""",
            payload,
        )
        get_db().commit()
    create_referral_event(str(payload["public_id"]), "CAPTURED", {"listing_id": listing_id})
    return normalize_referral_record(payload)


def touch_referral(referral: Mapping[str, object], path: str) -> dict[str, object]:
    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    expires_at = (now_dt + timedelta(days=int(app.config["REFERRAL_ATTRIBUTION_DAYS"]))).isoformat()
    if database_backend() == "mongodb":
        get_mongo_referrals_collection().update_one(
            {"public_id": referral["id"]},
            {"$set": {"last_path": path[:500], "last_seen_at": now, "expires_at": expires_at, "updated_at": now}, "$inc": {"visit_count": 1}},
        )
    else:
        get_db().execute(
            "UPDATE referrals SET last_path = ?, last_seen_at = ?, expires_at = ?, updated_at = ?, visit_count = visit_count + 1 WHERE public_id = ?",
            (path[:500], now, expires_at, now, referral["id"]),
        )
        get_db().commit()
    create_referral_event(str(referral["id"]), "RETURN_VISIT", {"path": path[:500]})
    refreshed = fetch_referral(str(referral["id"]))
    assert refreshed is not None
    return refreshed


def capture_referral(partner_code: str, *, listing_id: str = "", listing_title: str = "") -> dict[str, object] | None:
    partner = fetch_partner_by_code(partner_code, approved_only=True)
    if partner is None:
        return None
    scope = referral_scope(listing_id)
    cookie_data = referral_cookie_data()
    existing_entry = cookie_data.get(scope)
    if existing_entry:
        existing = fetch_referral_by_token(existing_entry["token"])
        if existing and attribution_is_active(existing.get("expires_at")):
            if existing.get("partner_id") != partner.get("id"):
                create_referral_event(
                    str(existing["id"]), "COMPETING_CODE_IGNORED",
                    {"attempted_partner_code": str(partner["partner_code"]), "listing_id": listing_id},
                )
                return existing
            refreshed = touch_referral(existing, request.path)
            cookie_data[scope] = {"token": existing_entry["token"], "expires_at": str(refreshed["expires_at"])}
            mark_referral_cookie_changed()
            return refreshed
        cookie_data.pop(scope, None)

    token = secrets.token_urlsafe(32)
    referral = create_referral_record(
        token=token, partner=partner, listing_id=listing_id, listing_title=listing_title, path=request.path,
    )
    cookie_data[scope] = {"token": token, "expires_at": str(referral["expires_at"])}
    while len(cookie_data) > 8:
        cookie_data.pop(next(iter(cookie_data)))
    mark_referral_cookie_changed()
    return referral


def resolve_referral_attribution(listing_id: str = "") -> dict[str, object] | None:
    cookie_data = referral_cookie_data()
    scopes = [referral_scope(listing_id)]
    if listing_id:
        scopes.append("general")
    for scope in scopes:
        entry = cookie_data.get(scope)
        if not entry:
            continue
        referral = fetch_referral_by_token(entry["token"])
        partner = fetch_partner(str(referral.get("partner_id") or "")) if referral else None
        expected_listing = str(referral.get("listing_id") or "") if referral else ""
        if (
            referral and attribution_is_active(referral.get("expires_at"))
            and partner and partner.get("status") == "APPROVED"
            and (not expected_listing or expected_listing == str(listing_id or ""))
        ):
            return referral
        cookie_data.pop(scope, None)
        mark_referral_cookie_changed()
        if referral and referral.get("status") == "VISITED" and not attribution_is_active(referral.get("expires_at")):
            update_referral_record(str(referral["id"]), status="EXPIRED")
    return None


def update_referral_record(referral_id: str, **updates: object) -> None:
    allowed = {"status", "lead_id", "inspection_id", "last_path", "last_seen_at", "expires_at"}
    payload = {key: value for key, value in updates.items() if key in allowed}
    if not payload:
        return
    payload["updated_at"] = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_referrals_collection().update_one({"public_id": referral_id}, {"$set": payload})
    else:
        assignments = ", ".join(f"{key} = ?" for key in payload)
        get_db().execute(
            f"UPDATE referrals SET {assignments} WHERE public_id = ?", (*payload.values(), referral_id)
        )
        get_db().commit()


def attach_referral_to_lead(lead_id: str, listing_id: str = "") -> dict[str, object] | None:
    lead = fetch_enquiry(lead_id)
    if lead.get("referral_id"):
        return fetch_referral(str(lead["referral_id"]))
    attribution = resolve_referral_attribution(listing_id)
    if attribution is None:
        return None
    if lead.get("partner_id") and lead.get("partner_id") != attribution.get("partner_id"):
        create_referral_event(str(attribution["id"]), "ATTRIBUTION_CONFLICT_IGNORED", {"lead_id": lead_id})
        return None
    values = {"partner_id": str(attribution["partner_id"]), "referral_id": str(attribution["id"]), "updated_at": utc_now_iso()}
    if database_backend() == "mongodb":
        get_mongo_enquiries_collection().update_one({"public_id": lead_id}, {"$set": values})
    else:
        get_db().execute(
            "UPDATE enquiries SET partner_id = ?, referral_id = ?, updated_at = ? WHERE public_id = ?",
            (values["partner_id"], values["referral_id"], values["updated_at"], lead_id),
        )
        get_db().commit()
    update_referral_record(str(attribution["id"]), status="LEAD_CREATED", lead_id=lead_id)
    create_referral_event(str(attribution["id"]), "LEAD_ATTRIBUTED", {"lead_id": lead_id})
    return fetch_referral(str(attribution["id"]))


def attach_inspection_to_referral(referral_id: str, inspection_id: str, lead_id: str) -> None:
    referral = fetch_referral(referral_id)
    if referral is None:
        return
    update_referral_record(referral_id, status="INSPECTION_REQUESTED", inspection_id=inspection_id, lead_id=lead_id)
    create_referral_event(referral_id, "INSPECTION_ATTRIBUTED", {"inspection_id": inspection_id, "lead_id": lead_id})


def record_referral_lead_lifecycle(
    referral_id: str, lead_id: str, previous_status: str, next_status: str
) -> None:
    if not referral_id or previous_status == next_status:
        return
    referral = fetch_referral(referral_id)
    if referral is None or str(referral.get("lead_id") or "") != lead_id:
        return
    create_referral_event(
        referral_id,
        "LEAD_STATUS_CHANGED",
        {"lead_id": lead_id, "previous_status": previous_status, "status": next_status},
    )
    if next_status == "CLOSED_WON" and referral.get("status") != "CONVERTED":
        update_referral_record(referral_id, status="CONVERTED")
        create_referral_event(referral_id, "CONVERTED", {"lead_id": lead_id})


def all_referrals() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_referrals_collection().find({}).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute("SELECT * FROM referrals ORDER BY created_at DESC").fetchall()
    return [normalize_referral_record(row) for row in rows]


def referrals_for_partner(partner_id: str) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_referrals_collection().find({"partner_id": partner_id}).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute(
            "SELECT * FROM referrals WHERE partner_id = ? ORDER BY created_at DESC", (partner_id,)
        ).fetchall()
    return [normalize_referral_record(row) for row in rows]


def referral_events(referral_id: str) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_referral_events_collection().find({"referral_id": referral_id}).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute(
            "SELECT * FROM referral_events WHERE referral_id = ? ORDER BY created_at DESC", (referral_id,)
        ).fetchall()
    return [normalize_referral_event(row) for row in rows]


def all_commission_rules() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_commission_rules_collection().find({}).sort(
            [("priority", DESCENDING), ("created_at", DESCENDING)]
        )
    else:
        rows = get_db().execute(
            "SELECT * FROM commission_rules ORDER BY priority DESC, created_at DESC"
        ).fetchall()
    return [normalize_commission_rule(row) for row in rows]


def fetch_commission_rule(rule_id: str) -> dict[str, object] | None:
    if not rule_id:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_commission_rules_collection().find_one({"public_id": rule_id})
    else:
        row = get_db().execute(
            "SELECT * FROM commission_rules WHERE public_id = ?", (rule_id,)
        ).fetchone()
    return normalize_commission_rule(row) if row is not None else None


def validate_commission_rule_form(form: Mapping[str, object]) -> tuple[dict[str, object], list[str]]:
    calculation_type = str(form.get("calculation_type") or "").strip().upper()
    scope_type = str(form.get("scope_type") or "").strip().upper()
    data: dict[str, object] = {
        "name": " ".join(str(form.get("name") or "").split()),
        "calculation_type": calculation_type,
        "percentage_bps": 0,
        "fixed_amount_minor": 0,
        "scope_type": scope_type,
        "property_id": str(form.get("property_id") or "").strip(),
        "property_title": "",
        "campaign_id": str(form.get("campaign_id") or "").strip(),
        "partner_id": str(form.get("partner_id") or "").strip(),
        "active": 1 if str(form.get("active") or "").lower() in {"1", "true", "on", "yes"} else 0,
        "valid_from": str(form.get("valid_from") or "").strip(),
        "valid_until": str(form.get("valid_until") or "").strip(),
        "priority": 0,
    }
    errors: list[str] = []
    if len(str(data["name"])) < 3 or len(str(data["name"])) > 100:
        errors.append("Rule name must be between 3 and 100 characters.")
    if calculation_type not in COMMISSION_CALCULATION_TYPES:
        errors.append("Choose a valid calculation type.")
    elif calculation_type == "PERCENTAGE":
        try:
            data["percentage_bps"] = percentage_to_basis_points(form.get("percentage"))
        except ValueError as exc:
            errors.append(str(exc))
    else:
        try:
            data["fixed_amount_minor"] = decimal_money_to_minor(form.get("fixed_amount"))
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if int(data["fixed_amount_minor"]) > 100_000_000_000_000_000:
                errors.append("Fixed commission exceeds the supported monetary limit.")
    if scope_type not in COMMISSION_SCOPE_TYPES:
        errors.append("Choose a valid rule scope.")
    elif scope_type == "PROPERTY":
        try:
            listing = fetch_listing(str(data["property_id"]))
            data["property_title"] = str(listing["title"])
        except NotFound:
            errors.append("Choose a valid property for this rule.")
    elif scope_type == "PARTNER":
        if fetch_partner(str(data["partner_id"])) is None:
            errors.append("Choose a valid partner for this override.")
    elif scope_type == "CAMPAIGN" and not str(data["campaign_id"]):
        errors.append("Campaign identifier is required for a campaign rule.")
    for key, label in (("valid_from", "Valid from"), ("valid_until", "Valid until")):
        if data[key]:
            try:
                date.fromisoformat(str(data[key]))
            except ValueError:
                errors.append(f"{label} must be a valid date.")
    if data["valid_from"] and data["valid_until"] and str(data["valid_until"]) < str(data["valid_from"]):
        errors.append("Valid until cannot be earlier than valid from.")
    priority, priority_error = safe_int(form.get("priority", "0"), "Priority", minimum=0)
    if priority_error:
        errors.append(priority_error)
    elif int(priority or 0) > 1000:
        errors.append("Priority cannot exceed 1,000.")
    else:
        data["priority"] = int(priority or 0)
    return data, errors


def save_commission_rule(data: Mapping[str, object], *, created_by: str, rule_id: str = "") -> str:
    now = utc_now_iso()
    payload = {**data, "updated_at": now}
    if rule_id:
        if database_backend() == "mongodb":
            result = get_mongo_commission_rules_collection().update_one(
                {"public_id": rule_id}, {"$set": payload}
            )
            if not result.matched_count:
                abort(404)
        else:
            assignments = ", ".join(f"{key} = :{key}" for key in payload)
            cursor = get_db().execute(
                f"UPDATE commission_rules SET {assignments} WHERE public_id = :rule_id",
                {**payload, "rule_id": rule_id},
            )
            get_db().commit()
            if not cursor.rowcount:
                abort(404)
        return rule_id
    public_id = uuid.uuid4().hex[:12]
    payload.update({"public_id": public_id, "created_by": created_by, "created_at": now})
    if database_backend() == "mongodb":
        get_mongo_commission_rules_collection().insert_one(dict(payload))
    else:
        get_db().execute(
            """INSERT INTO commission_rules (
                public_id, name, calculation_type, percentage_bps, fixed_amount_minor, scope_type,
                property_id, property_title, campaign_id, partner_id, active, valid_from, valid_until,
                priority, created_by, created_at, updated_at
            ) VALUES (
                :public_id, :name, :calculation_type, :percentage_bps, :fixed_amount_minor, :scope_type,
                :property_id, :property_title, :campaign_id, :partner_id, :active, :valid_from, :valid_until,
                :priority, :created_by, :created_at, :updated_at
            )""",
            payload,
        )
        get_db().commit()
    return public_id


def select_commission_rule(
    *, property_id: str, partner_id: str, campaign_id: str = ""
) -> dict[str, object] | None:
    if database_backend() == "mongodb":
        scope_filters: list[dict[str, object]] = [{"scope_type": "DEFAULT"}]
        if property_id:
            scope_filters.append({"scope_type": "PROPERTY", "property_id": property_id})
        if partner_id:
            scope_filters.append({"scope_type": "PARTNER", "partner_id": partner_id})
        if campaign_id:
            scope_filters.append({"scope_type": "CAMPAIGN", "campaign_id": campaign_id})
        candidates = [
            normalize_commission_rule(row)
            for row in get_mongo_commission_rules_collection().find({"active": 1, "$or": scope_filters})
        ]
    else:
        candidates = [
            normalize_commission_rule(row)
            for row in get_db().execute(
                """SELECT * FROM commission_rules
                   WHERE active = 1 AND (
                       scope_type = 'DEFAULT'
                       OR (scope_type = 'PROPERTY' AND property_id = ?)
                       OR (scope_type = 'PARTNER' AND partner_id = ?)
                       OR (scope_type = 'CAMPAIGN' AND campaign_id = ?)
                   )""",
                (property_id, partner_id, campaign_id),
            ).fetchall()
        ]
    matches = [
        rule for rule in candidates
        if rule_matches(
            rule, property_id=property_id, partner_id=partner_id, campaign_id=campaign_id,
        )
    ]
    return max(matches, key=rule_sort_key) if matches else None


def fetch_commission(commission_id: str) -> dict[str, object] | None:
    if not commission_id:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_commissions_collection().find_one({"public_id": commission_id})
    else:
        row = get_db().execute(
            "SELECT * FROM commissions WHERE public_id = ?", (commission_id,)
        ).fetchone()
    return normalize_commission(row) if row is not None else None


def fetch_commission_for_lead(lead_id: str) -> dict[str, object] | None:
    if database_backend() == "mongodb":
        row = get_mongo_commissions_collection().find_one({"lead_id": lead_id})
    else:
        row = get_db().execute("SELECT * FROM commissions WHERE lead_id = ?", (lead_id,)).fetchone()
    return normalize_commission(row) if row is not None else None


def all_commissions() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_commissions_collection().find({}).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute("SELECT * FROM commissions ORDER BY created_at DESC").fetchall()
    return [normalize_commission(row) for row in rows]


def query_commissions(
    *, status: str = "", partner_id: str = "", listing_id: str = "", date_from: str = "", date_to: str = ""
) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        query: dict[str, object] = {}
        if status:
            query["status"] = status
        if partner_id:
            query["partner_id"] = partner_id
        if listing_id:
            query["listing_id"] = listing_id
        if date_from or date_to:
            created_filter: dict[str, str] = {}
            if date_from:
                created_filter["$gte"] = f"{date_from}T00:00:00+00:00"
            if date_to:
                created_filter["$lte"] = f"{date_to}T23:59:59.999999+00:00"
            query["created_at"] = created_filter
        rows = get_mongo_commissions_collection().find(query).sort("created_at", DESCENDING)
    else:
        clauses: list[str] = []
        values: list[str] = []
        for column, value in (("status", status), ("partner_id", partner_id), ("listing_id", listing_id)):
            if value:
                clauses.append(f"{column} = ?")
                values.append(value)
        if date_from:
            clauses.append("created_at >= ?")
            values.append(f"{date_from}T00:00:00+00:00")
        if date_to:
            clauses.append("created_at <= ?")
            values.append(f"{date_to}T23:59:59.999999+00:00")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = get_db().execute(
            f"SELECT * FROM commissions{where} ORDER BY created_at DESC", values
        ).fetchall()
    return [normalize_commission(row) for row in rows]


def commissions_for_partner(partner_id: str) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_commissions_collection().find({"partner_id": partner_id}).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute(
            "SELECT * FROM commissions WHERE partner_id = ? ORDER BY created_at DESC", (partner_id,)
        ).fetchall()
    return [normalize_commission(row) for row in rows]


def stored_marketing_assets_for_listing(listing_id: str) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_marketing_assets_collection().find(
            {"listing_id": listing_id, "approved": 1, "active": 1}
        ).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute(
            """SELECT * FROM marketing_assets
               WHERE listing_id = ? AND approved = 1 AND active = 1
               ORDER BY created_at DESC""",
            (listing_id,),
        ).fetchall()
    return [normalize_marketing_asset(row) for row in rows]


def fetch_marketing_asset(asset_id: str) -> dict[str, object] | None:
    if database_backend() == "mongodb":
        row = get_mongo_marketing_assets_collection().find_one(
            {"public_id": asset_id, "approved": 1, "active": 1}
        )
    else:
        row = get_db().execute(
            "SELECT * FROM marketing_assets WHERE public_id = ? AND approved = 1 AND active = 1",
            (asset_id,),
        ).fetchone()
    return normalize_marketing_asset(row) if row is not None else None


def create_partner_marketing_event(
    *, partner_id: str, listing_id: str, event_type: str, metadata: Mapping[str, object] | None = None
) -> str:
    normalized_type = normalize_marketing_event_type(event_type)
    if not normalized_type:
        raise ValueError("Unsupported partner marketing event.")
    public_id = uuid.uuid4().hex[:12]
    payload = {
        "public_id": public_id, "partner_id": partner_id, "listing_id": listing_id,
        "event_type": normalized_type, "metadata": dict(metadata or {}), "created_at": utc_now_iso(),
    }
    if database_backend() == "mongodb":
        get_mongo_partner_marketing_events_collection().insert_one(payload)
    else:
        get_db().execute(
            """INSERT INTO partner_marketing_events (
                public_id, partner_id, listing_id, event_type, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                public_id, partner_id, listing_id, normalized_type,
                json.dumps(payload["metadata"], separators=(",", ":")), payload["created_at"],
            ),
        )
        get_db().commit()
    return public_id


def partner_marketing_event_counts(partner_id: str) -> dict[str, int]:
    counts = {event_type: 0 for event_type in PARTNER_MARKETING_EVENT_TYPES}
    if database_backend() == "mongodb":
        rows = get_mongo_partner_marketing_events_collection().aggregate([
            {"$match": {"partner_id": partner_id}},
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
        ])
        for row in rows:
            event_type = str(row.get("_id") or "")
            if event_type in counts:
                counts[event_type] = int(row.get("count") or 0)
    else:
        rows = get_db().execute(
            """SELECT event_type, COUNT(*) AS count FROM partner_marketing_events
               WHERE partner_id = ? GROUP BY event_type""",
            (partner_id,),
        ).fetchall()
        for row in rows:
            if row["event_type"] in counts:
                counts[row["event_type"]] = int(row["count"] or 0)
    return counts


def partner_performance_metrics(partner_id: str) -> dict[str, int]:
    event_counts = partner_marketing_event_counts(partner_id)
    if database_backend() == "mongodb":
        referral_summary = next(iter(get_mongo_referrals_collection().aggregate([
            {"$match": {"partner_id": partner_id}},
            {"$group": {"_id": None, "referrals": {"$sum": 1}, "visits": {"$sum": "$visit_count"}}},
        ])), {})
        lead_summary = next(iter(get_mongo_enquiries_collection().aggregate([
            {"$match": {"partner_id": partner_id}},
            {"$group": {
                "_id": None, "leads": {"$sum": 1},
                "conversions": {"$sum": {"$cond": [{"$eq": ["$status", "CLOSED_WON"]}, 1, 0]}},
            }},
        ])), {})
        inspections = int(get_mongo_inspections_collection().count_documents({"partner_id": partner_id}))
    else:
        referral_summary = get_db().execute(
            "SELECT COUNT(*) AS referrals, COALESCE(SUM(visit_count), 0) AS visits FROM referrals WHERE partner_id = ?",
            (partner_id,),
        ).fetchone()
        lead_summary = get_db().execute(
            """SELECT COUNT(*) AS leads,
               SUM(CASE WHEN status = 'CLOSED_WON' THEN 1 ELSE 0 END) AS conversions
               FROM enquiries WHERE partner_id = ?""",
            (partner_id,),
        ).fetchone()
        inspection_row = get_db().execute(
            "SELECT COUNT(*) AS count FROM inspections WHERE partner_id = ?", (partner_id,)
        ).fetchone()
        inspections = int(inspection_row["count"] or 0)
    return {
        "referral_links_opened": int(referral_summary.get("referrals", 0) if isinstance(referral_summary, Mapping) else referral_summary["referrals"] or 0),
        "referral_property_views": int(referral_summary.get("visits", 0) if isinstance(referral_summary, Mapping) else referral_summary["visits"] or 0),
        "leads_generated": int(lead_summary.get("leads", 0) if isinstance(lead_summary, Mapping) else lead_summary["leads"] or 0),
        "inspections_generated": inspections,
        "successful_deals": int(lead_summary.get("conversions", 0) if isinstance(lead_summary, Mapping) else lead_summary["conversions"] or 0),
        "links_copied": event_counts["LINK_COPIED"],
        "shares_initiated": event_counts["SHARE_INITIATED"] + event_counts["WHATSAPP_SHARE"],
        "media_downloads": event_counts["MEDIA_DOWNLOADED"],
    }


def partner_marketing_listing(listing: Mapping[str, object], partner: Mapping[str, object]) -> dict[str, object]:
    item = dict(listing)
    referral_url = url_for(
        "property_detail", listing_id=item["id"], ref=partner["partner_code"], _external=True,
    )
    price_label = listing_price_label(item)
    share_text = marketing_share_message(item, referral_url, price_label)
    rule = select_commission_rule(property_id=str(item["id"]), partner_id=str(partner["id"]))
    if rule and rule["calculation_type"] == "PERCENTAGE":
        commission_opportunity = f"{rule['percentage']}% of an eligible verified sale"
    elif rule:
        commission_opportunity = f"{format_naira(rule['fixed_amount'])} on an eligible verified sale"
    else:
        commission_opportunity = "No active commission rule is currently attached"
    item.update({
        "referral_url": referral_url,
        "share_text": share_text,
        "whatsapp_share_url": f"https://wa.me/?text={quote(share_text)}",
        "commission_opportunity": commission_opportunity,
        "marketing_assets": [
            {
                "id": f"primary:{item['id']}", "asset_type": "IMAGE", "asset_type_label": "Image",
                "title": "Primary property image", "file_size": 0,
                "download_url": url_for("download_partner_marketing_asset", asset_id=f"primary:{item['id']}"),
            },
            *[
                {**asset, "download_url": url_for("download_partner_marketing_asset", asset_id=asset["id"])}
                for asset in stored_marketing_assets_for_listing(str(item["id"]))
            ],
        ],
    })
    return item


def create_commission_for_lead(
    lead: Mapping[str, object], rule: Mapping[str, object], status: str
) -> dict[str, object]:
    sale_value_minor = int(lead.get("estimated_value") or 0) * 100
    calculated = calculate_commission_minor(
        sale_value_minor,
        calculation_type=str(rule["calculation_type"]),
        percentage_bps=int(rule.get("percentage_bps") or 0),
        fixed_amount_minor=int(rule.get("fixed_amount_minor") or 0),
    )
    if calculated > sale_value_minor:
        raise ValueError("Commission cannot exceed the recorded sale value.")
    partner = fetch_partner(str(lead.get("partner_id") or ""))
    if partner is None:
        raise ValueError("Attributed partner no longer exists.")
    now = utc_now_iso()
    snapshot = {
        "rule_id": rule["id"], "name": rule["name"], "scope_type": rule["scope_type"],
        "calculation_type": rule["calculation_type"], "percentage_bps": rule["percentage_bps"],
        "fixed_amount_minor": rule["fixed_amount_minor"], "priority": rule["priority"],
    }
    payload = {
        "public_id": uuid.uuid4().hex[:12], "lead_id": str(lead["id"]),
        "referral_id": str(lead.get("referral_id") or ""), "partner_id": str(partner["id"]),
        "partner_code": str(partner["partner_code"]), "listing_id": str(lead.get("listing_id") or ""),
        "listing_title": str(lead.get("listing_title") or ""), "customer_reference": str(lead["id"]).upper(),
        "sale_value_minor": sale_value_minor, "rule_id": str(rule["id"]), "rule_name": str(rule["name"]),
        "calculation_type": str(rule["calculation_type"]), "rule_snapshot": snapshot,
        "calculated_amount_minor": calculated, "adjustment_minor": 0, "final_amount_minor": calculated,
        "status": status, "adjustment_reason": "", "approved_by": "", "approved_at": "",
        "rejected_by": "", "rejected_at": "", "rejection_reason": "", "paid_by": "", "paid_at": "",
        "payment_reference": "", "payment_note": "", "created_at": now, "updated_at": now,
    }
    if database_backend() == "mongodb":
        try:
            get_mongo_commissions_collection().insert_one(dict(payload))
        except DuplicateKeyError:
            existing = fetch_commission_for_lead(str(lead["id"]))
            if existing is not None:
                return existing
            raise
    else:
        try:
            get_db().execute(
                """INSERT INTO commissions (
                public_id, lead_id, referral_id, partner_id, partner_code, listing_id, listing_title,
                customer_reference, sale_value_minor, rule_id, rule_name, calculation_type,
                rule_snapshot_json, calculated_amount_minor, adjustment_minor, final_amount_minor, status,
                adjustment_reason, approved_by, approved_at, rejected_by, rejected_at, rejection_reason,
                paid_by, paid_at, payment_reference, payment_note, created_at, updated_at
            ) VALUES (
                :public_id, :lead_id, :referral_id, :partner_id, :partner_code, :listing_id, :listing_title,
                :customer_reference, :sale_value_minor, :rule_id, :rule_name, :calculation_type,
                :rule_snapshot_json, :calculated_amount_minor, :adjustment_minor, :final_amount_minor, :status,
                :adjustment_reason, :approved_by, :approved_at, :rejected_by, :rejected_at, :rejection_reason,
                :paid_by, :paid_at, :payment_reference, :payment_note, :created_at, :updated_at
            )""",
                {**payload, "rule_snapshot_json": json.dumps(snapshot, separators=(",", ":"))},
            )
            get_db().commit()
        except sqlite3.IntegrityError:
            existing = fetch_commission_for_lead(str(lead["id"]))
            if existing is not None:
                return existing
            raise
    create_activity_record(
        entity_type="commission", entity_id=str(payload["public_id"]), action="created",
        summary=f"Commission created for deal {payload['customer_reference']} at {COMMISSION_STATUS_LABELS[status].lower()}.",
        metadata={"lead_id": lead["id"], "rule_id": rule["id"], "amount_minor": calculated, "status": status},
    )
    return normalize_commission(payload)


def update_commission_fields(commission_id: str, **updates: object) -> None:
    allowed = {
        "sale_value_minor", "calculated_amount_minor", "adjustment_minor", "final_amount_minor", "status",
        "adjustment_reason", "approved_by", "approved_at", "rejected_by", "rejected_at", "rejection_reason",
        "paid_by", "paid_at", "payment_reference", "payment_note",
    }
    payload = {key: value for key, value in updates.items() if key in allowed}
    if not payload:
        return
    payload["updated_at"] = utc_now_iso()
    if database_backend() == "mongodb":
        result = get_mongo_commissions_collection().update_one({"public_id": commission_id}, {"$set": payload})
        if not result.matched_count:
            abort(404)
    else:
        assignments = ", ".join(f"{key} = ?" for key in payload)
        cursor = get_db().execute(
            f"UPDATE commissions SET {assignments} WHERE public_id = ?", (*payload.values(), commission_id)
        )
        get_db().commit()
        if not cursor.rowcount:
            abort(404)


def sync_commission_for_lead(lead_id: str) -> dict[str, object] | None:
    lead = fetch_enquiry(lead_id)
    target = target_status_for_lead_stage(lead.get("status"))
    existing = fetch_commission_for_lead(lead_id)
    if not target:
        return existing
    if target == "CANCELLED":
        if existing and existing["status"] in {"POTENTIAL", "PENDING", "EARNED"}:
            update_commission_fields(str(existing["id"]), status="CANCELLED")
            create_activity_record(
                entity_type="commission", entity_id=str(existing["id"]), action="cancelled",
                summary=f"Commission cancelled after deal {lead_id.upper()} closed without a sale.",
                metadata={"lead_id": lead_id, "previous_status": existing["status"], "status": "CANCELLED"},
            )
            return fetch_commission(str(existing["id"]))
        return existing
    if not lead.get("partner_id") or not lead.get("referral_id") or int(lead.get("estimated_value") or 0) <= 0:
        return existing
    referral = fetch_referral(str(lead["referral_id"]))
    if referral is None or referral.get("partner_id") != lead.get("partner_id") or referral.get("lead_id") != lead_id:
        return existing
    if existing is None:
        rule = select_commission_rule(
            property_id=str(lead.get("listing_id") or ""), partner_id=str(lead["partner_id"]),
            campaign_id=str(lead.get("campaign_id") or ""),
        )
        if rule is None:
            return None
        try:
            return create_commission_for_lead(lead, rule, target)
        except ValueError:
            app.logger.warning(
                "Commission creation rejected for lead %s because the matched rule produced an invalid amount.",
                lead_id,
            )
            return None
    if existing["status"] in {"POTENTIAL", "PENDING", "EARNED"}:
        snapshot = existing["rule_snapshot"]
        sale_value_minor = int(lead.get("estimated_value") or 0) * 100
        calculated = calculate_commission_minor(
            sale_value_minor,
            calculation_type=str(existing["calculation_type"]),
            percentage_bps=int(snapshot.get("percentage_bps") or 0),
            fixed_amount_minor=int(snapshot.get("fixed_amount_minor") or 0),
        )
        final_amount = calculated + int(existing["adjustment_minor"])
        if final_amount <= 0:
            return existing
        changes: dict[str, object] = {
            "sale_value_minor": sale_value_minor,
            "calculated_amount_minor": calculated,
            "final_amount_minor": final_amount,
        }
        if existing["status"] != target and transition_is_allowed(existing["status"], target):
            changes["status"] = target
        update_commission_fields(str(existing["id"]), **changes)
        if existing["status"] != changes.get("status", existing["status"]):
            create_activity_record(
                entity_type="commission", entity_id=str(existing["id"]), action="status_changed",
                summary=f"Commission moved to {COMMISSION_STATUS_LABELS[target].lower()} with deal {lead_id.upper()}.",
                metadata={"previous_status": existing["status"], "status": target, "lead_id": lead_id},
            )
        return fetch_commission(str(existing["id"]))
    return existing


def enquiry_reference(enquiry_id: str) -> str:
    return f"ENQ-{str(enquiry_id or '').upper()}"


def enquiry_source_label(source_path: str) -> str:
    source = str(source_path or "").strip()
    if source.startswith("/properties/"):
        return "Property detail page"
    if source.startswith("/properties"):
        return "Listings page"
    if source.startswith("/tenant-services"):
        return "Tenant services page"
    if source in {"", "/"}:
        return "Homepage"
    return "Website enquiry"


def enquiry_reply_line(preferred_contact: str, settings: Mapping[str, object]) -> str:
    if preferred_contact == "Email":
        return str(settings.get("contact_email") or "")
    return str(settings.get("contact_phone_display") or "")


def enquiry_email_context(
    enquiry_id: str,
    enquiry_data: Mapping[str, str],
    listing: Mapping[str, object] | None,
) -> dict[str, object]:
    settings = site_settings()
    listing_title = str(enquiry_data.get("listing_title") or "Property enquiry")
    reply_to = normalized_email_address(str(enquiry_data.get("email") or "").strip())
    return {
        "settings": settings,
        "base_url": request.url_root.rstrip("/"),
        "logo_cid": "structurebase-logo",
        "reference": enquiry_reference(enquiry_id),
        "listing_title": listing_title,
        "has_listing": listing is not None,
        "listing_price": listing_price_label(listing) if listing is not None else "Pricing shared on request",
        "reply_to": reply_to,
        "phone": str(enquiry_data.get("phone") or "").strip(),
        "message_excerpt": str(enquiry_data.get("message") or "").strip(),
        "preferred_contact": str(enquiry_data.get("preferred_contact") or "Email"),
        "detail_url": (
            url_for("property_detail", listing_id=str(listing["id"]), _external=True)
            if listing is not None
            else url_for("properties", _external=True)
        ),
        "source_label": enquiry_source_label(str(enquiry_data.get("source_path") or "").strip()),
        "sender_name": enquiry_sender_display_name(str(enquiry_data.get("name") or "").strip()),
        "greeting_line": enquiry_greeting_line(str(enquiry_data.get("name") or "").strip()),
    }


def send_admin_enquiry_notification(
    enquiry_context: Mapping[str, object],
) -> dict[str, str | bool]:
    settings = enquiry_context["settings"]
    recipient = normalized_email_address(str(settings.get("contact_email") or ""))
    result: dict[str, str | bool] = {
        "sent": False,
        "recipient": recipient,
        "sent_at": "",
        "error": "",
    }
    if not recipient:
        result["error"] = "No admin recipient is configured."
        return result

    payload = {
        "reference": enquiry_context["reference"],
        "sender_name": enquiry_context["sender_name"],
        "sender_email": enquiry_context["reply_to"],
        "sender_phone": str(enquiry_context.get("phone") or ""),
        "preferred_contact": enquiry_context["preferred_contact"],
        "listing_title": enquiry_context["listing_title"],
        "source_label": enquiry_context["source_label"],
        "message_excerpt": enquiry_context["message_excerpt"],
        "cta_label": "Open lead queue",
        "cta_url": url_for("admin_enquiries", _external=True),
    }
    rendered = render_communication_template(
        "admin_enquiry_notification",
        payload,
        settings,
        base_url=str(enquiry_context["base_url"]),
        logo_cid=str(enquiry_context["logo_cid"]),
    )
    try:
        send_email_message(
            to_address=recipient,
            subject=rendered["subject"],
            text_body=rendered["text"],
            html_body=rendered["html"],
            reply_to=str(enquiry_context["reply_to"] or ""),
            embedded_logo_cid=str(enquiry_context["logo_cid"]),
        )
        result["sent"] = True
        result["sent_at"] = utc_now_iso()
    except Exception as exc:
        app.logger.exception(
            "Failed to send admin enquiry notification for %s",
            enquiry_context["reference"],
        )
        result["error"] = delivery_error_summary(exc)
    return result


def send_enquiry_receipt(
    enquiry_context: Mapping[str, object],
) -> dict[str, str | bool]:
    recipient = normalized_email_address(str(enquiry_context["reply_to"] or ""))
    result: dict[str, str | bool] = {
        "sent": False,
        "recipient": recipient,
        "sent_at": "",
        "error": "",
    }
    if not recipient:
        return result

    settings = enquiry_context["settings"]
    payload = {
        "greeting_line": enquiry_context["greeting_line"],
        "reference": enquiry_context["reference"],
        "listing_title": enquiry_context["listing_title"],
        "listing_price": enquiry_context["listing_price"],
        "preferred_contact": enquiry_context["preferred_contact"],
        "reply_line": enquiry_reply_line(str(enquiry_context["preferred_contact"]), settings),
        "message_excerpt": enquiry_context["message_excerpt"],
        "response_window": "A member of the team will review this and respond within one business day.",
        "cta_label": "View listing" if enquiry_context.get("has_listing") else "Browse listings",
        "cta_url": enquiry_context["detail_url"],
    }
    rendered = render_communication_template(
        "enquiry_receipt",
        payload,
        settings,
        base_url=str(enquiry_context["base_url"]),
        logo_cid=str(enquiry_context["logo_cid"]),
    )
    try:
        send_email_message(
            to_address=recipient,
            subject=rendered["subject"],
            text_body=rendered["text"],
            html_body=rendered["html"],
            reply_to=str(settings["contact_email"]),
            embedded_logo_cid=str(enquiry_context["logo_cid"]),
        )
        result["sent"] = True
        result["sent_at"] = utc_now_iso()
    except Exception as exc:
        app.logger.exception(
            "Failed to send enquiry receipt for %s",
            enquiry_context["reference"],
        )
        result["error"] = delivery_error_summary(exc)
    return result


def persist_enquiry_delivery(
    enquiry_id: str,
    *,
    admin_result: Mapping[str, object] | None = None,
    receipt_result: Mapping[str, object] | None = None,
) -> None:
    updates: dict[str, str] = {}
    if admin_result is not None:
        updates["admin_email_recipient"] = str(admin_result.get("recipient") or "").strip()
        updates["admin_email_last_error"] = str(admin_result.get("error") or "").strip()
        if admin_result.get("sent"):
            updates["admin_email_sent_at"] = str(admin_result.get("sent_at") or "").strip()
            updates["admin_email_last_error"] = ""
    if receipt_result is not None:
        updates["receipt_email_recipient"] = str(receipt_result.get("recipient") or "").strip()
        updates["receipt_email_last_error"] = str(receipt_result.get("error") or "").strip()
        if receipt_result.get("sent"):
            updates["receipt_email_sent_at"] = str(receipt_result.get("sent_at") or "").strip()
            updates["receipt_email_last_error"] = ""
    update_enquiry_delivery_status(enquiry_id, **updates)


def send_enquiry_emails(
    enquiry_id: str,
    enquiry_data: Mapping[str, str],
    listing: Mapping[str, object] | None,
) -> dict[str, str | bool]:
    if not smtp_is_configured():
        return {"admin_sent": False, "receipt_sent": False, "admin_error": "SMTP is not configured."}

    enquiry_context = enquiry_email_context(enquiry_id, enquiry_data, listing)
    admin_result = send_admin_enquiry_notification(enquiry_context)
    receipt_result = send_enquiry_receipt(enquiry_context)
    persist_enquiry_delivery(
        enquiry_id,
        admin_result=admin_result,
        receipt_result=receipt_result,
    )
    return {
        "admin_sent": bool(admin_result.get("sent")),
        "receipt_sent": bool(receipt_result.get("sent")),
        "admin_error": str(admin_result.get("error") or ""),
        "receipt_error": str(receipt_result.get("error") or ""),
    }


def is_local_request_host() -> bool:
    host = request.host.split(":", 1)[0].strip("[]").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def is_authenticated() -> bool:
    return current_staff() is not None


def current_staff() -> dict[str, object] | None:
    if not has_request_context():
        return None
    if hasattr(g, "current_staff"):
        return g.current_staff
    user_id = str(session.get("staff_user_id") or "").strip()
    staff = fetch_staff_user(user_id) if user_id else None
    if staff is None or staff.get("status") != "ACTIVE":
        if user_id:
            for key in ("staff_user_id", "staff_role", "staff_name"):
                session.pop(key, None)
        g.current_staff = None
        return None
    g.current_staff = staff
    return staff


def current_partner() -> dict[str, object] | None:
    if not has_request_context():
        return None
    if hasattr(g, "current_partner"):
        return g.current_partner
    partner_id = str(session.get("partner_user_id") or "").strip()
    partner = fetch_partner(partner_id) if partner_id else None
    if partner is None:
        if partner_id:
            session.pop("partner_user_id", None)
        g.current_partner = None
        return None
    g.current_partner = partner
    return partner


def is_partner_authenticated(*, require_approved: bool = True) -> bool:
    partner = current_partner()
    return bool(partner and (not require_approved or partner.get("status") == "APPROVED"))


def has_permission(permission: str) -> bool:
    staff = current_staff()
    return bool(staff and role_has_permission(str(staff.get("role") or ""), permission))


def current_staff_label() -> str:
    staff = current_staff()
    if staff is None:
        return "System"
    return str(staff.get("full_name") or staff.get("username") or "Staff")


def admin_password_is_default() -> bool:
    return _is_default_admin_password(app, DEFAULT_ADMIN_PASSWORD)


def check_admin_credentials(username: str, password: str) -> bool:
    return authenticate_staff(username, password) is not None


def safe_redirect_target(target: str | None) -> str:
    return _safe_redirect_target(target, request.host, url_for)


def admin_return_target(default_endpoint: str) -> str:
    return _admin_return_target(default_endpoint, request, url_for)


def client_ip() -> str:
    return _client_ip(request)


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def login_rate_limit_key(username: str, realm: str = "staff") -> str:
    raw_key = f"{realm}::{client_ip()}::{normalize_username(username) or 'anonymous'}".encode("utf-8")
    return hmac.new(
        str(app.config["SECRET_KEY"]).encode("utf-8"),
        raw_key,
        hashlib.sha256,
    ).hexdigest()


def prune_login_attempts(key: str) -> list[float]:
    cutoff = time.time() - app.config["LOGIN_WINDOW_SECONDS"]
    if database_backend() == "mongodb":
        collection = get_mongo_login_attempts_collection()
        collection.delete_many({"attempted_at": {"$lt": cutoff}})
        return [
            float(row.get("attempted_at") or 0)
            for row in collection.find({"attempt_key": key, "attempted_at": {"$gte": cutoff}})
        ]
    db = get_db()
    db.execute("DELETE FROM staff_login_attempts WHERE attempted_at < ?", (cutoff,))
    rows = db.execute(
        "SELECT attempted_at FROM staff_login_attempts WHERE attempt_key = ? AND attempted_at >= ?",
        (key, cutoff),
    ).fetchall()
    db.commit()
    return [float(row["attempted_at"]) for row in rows]


def login_is_rate_limited(username: str, realm: str = "staff") -> bool:
    return len(prune_login_attempts(login_rate_limit_key(username, realm))) >= app.config["LOGIN_MAX_ATTEMPTS"]


def record_failed_login(username: str, realm: str = "staff") -> None:
    attempt_key = login_rate_limit_key(username, realm)
    attempted_at = time.time()
    if database_backend() == "mongodb":
        get_mongo_login_attempts_collection().insert_one(
            {
                "attempt_key": attempt_key,
                "attempted_at": attempted_at,
                "expires_at": datetime.now(UTC) + timedelta(seconds=app.config["LOGIN_WINDOW_SECONDS"]),
            }
        )
        return
    get_db().execute(
        "INSERT INTO staff_login_attempts (attempt_key, attempted_at) VALUES (?, ?)",
        (attempt_key, attempted_at),
    )
    get_db().commit()


def reset_failed_login(username: str, realm: str = "staff") -> None:
    attempt_key = login_rate_limit_key(username, realm)
    if database_backend() == "mongodb":
        get_mongo_login_attempts_collection().delete_many({"attempt_key": attempt_key})
        return
    get_db().execute("DELETE FROM staff_login_attempts WHERE attempt_key = ?", (attempt_key,))
    get_db().commit()


def build_content_security_policy(nonce: str) -> str:
    directives = {
        "default-src": ["'self'"],
        "base-uri": ["'self'"],
        "object-src": ["'none'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'self'"],
        "worker-src": ["'self'", "blob:"],
        "child-src": ["'self'", "blob:"],
        "img-src": ["'self'", "data:", "blob:", "https:"],
        "script-src": ["'self'", "https://api.mapbox.com", f"'nonce-{nonce}'"],
        "style-src": [
            "'self'",
            "'unsafe-inline'",
            "https://fonts.googleapis.com",
            "https://api.mapbox.com",
        ],
        "font-src": ["'self'", "data:", "https://fonts.gstatic.com"],
        "connect-src": [
            "'self'",
            "https://api.mapbox.com",
            "https://events.mapbox.com",
            "https://*.mapbox.com",
            "https://res.cloudinary.com",
        ],
        "frame-src": ["'self'", "https:"],
        "manifest-src": ["'self'"],
    }

    policy = "; ".join(
        f"{directive} {' '.join(values)}" for directive, values in directives.items()
    )
    if app.config["IS_PRODUCTION"]:
        policy = f"{policy}; upgrade-insecure-requests"
    return policy


@app.before_request
def protect_form_posts():
    g.request_started_at = time.perf_counter()
    incoming_request_id = re.sub(
        r"[^A-Za-z0-9._-]",
        "",
        str(request.headers.get("X-Request-ID", "")).strip(),
    )[:80]
    g.request_id = incoming_request_id or uuid.uuid4().hex
    g.csp_nonce = secrets.token_urlsafe(16)
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    expected = session.get("_csrf_token", "")
    provided = request.form.get("csrf_token", "")
    if expected and provided and hmac.compare_digest(expected, provided):
        return None
    flash("Your form session expired. Refresh the page and try again.", "error")
    if request.path.startswith("/dashboard"):
        return redirect(request.referrer or url_for("dashboard"))
    if request.endpoint == "login":
        return redirect(url_for("login", next=request.form.get("next") or request.args.get("next") or ""))
    if request.endpoint == "partner_login":
        return redirect(url_for("partner_login", next=request.form.get("next") or request.args.get("next") or ""))
    return redirect(request.referrer or url_for("home"))


@app.after_request
def apply_response_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
    response.headers.setdefault("X-Request-ID", getattr(g, "request_id", ""))
    if getattr(g, "csp_nonce", ""):
        response.headers.setdefault(
            "Content-Security-Policy",
            build_content_security_policy(g.csp_nonce),
        )
    if app.config["IS_PRODUCTION"] and request.is_secure:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    if app.config["IS_PRODUCTION"] and request.endpoint == "static" and request.args.get("v"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

    started = getattr(g, "request_started_at", None)
    duration_ms = round((time.perf_counter() - started) * 1000, 2) if started else None
    if not request.path.startswith("/static/") or response.status_code >= 400:
        logged_path = (
            "/staff/accept/[redacted]"
            if request.endpoint == "accept_staff_invitation"
            else request.path
        )
        log_payload = {
            "event": "http.request",
            "request_id": getattr(g, "request_id", ""),
            "method": request.method,
            "path": logged_path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "ip": client_ip(),
            "endpoint": request.endpoint or "",
            "scheme": request.scheme,
        }
        level = logging.INFO
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        app.logger.log(level, json.dumps(log_payload, separators=(",", ":")))
    return persist_referral_cookie(response)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def permission_required(permission: str):
    if permission not in ALL_PERMISSIONS:
        raise ValueError(f"Unknown permission: {permission}")

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not is_authenticated():
                return redirect(url_for("login", next=request.path))
            if not has_permission(permission):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def partner_login_required(*, approved: bool = True):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            partner = current_partner()
            if partner is None:
                return redirect(url_for("partner_login", next=request.path))
            if approved and partner.get("status") != "APPROVED":
                return redirect(url_for("partner_application_status"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def safe_int(value: str, field_name: str, minimum: int = 0) -> tuple[int | None, str | None]:
    raw = (value or "").strip()
    if not raw:
        return minimum, None
    try:
        parsed = int(raw)
    except ValueError:
        return None, f"{field_name} must be a whole number."
    if parsed < minimum:
        return None, f"{field_name} must be at least {minimum}."
    return parsed, None


def safe_float(
    value: str,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> tuple[float | None, str | None]:
    raw = (value or "").strip()
    if not raw:
        return None, None
    try:
        parsed = float(raw)
    except ValueError:
        return None, f"{field_name} must be a number."
    if not math.isfinite(parsed):
        return None, f"{field_name} must be a finite number."
    if parsed < minimum or parsed > maximum:
        return None, f"{field_name} must be between {minimum} and {maximum}."
    return round(parsed, 6), None


def validate_listing_form(form) -> tuple[dict[str, object], list[str]]:
    data = {
        "title": form.get("title", "").strip(),
        "status": form.get("status", "").strip(),
        "availability": form.get("availability", "").strip(),
        "property_type": form.get("property_type", "").strip(),
        "district": form.get("district", "").strip(),
        "address": form.get("address", "").strip(),
        "longitude": form.get("longitude", "").strip(),
        "latitude": form.get("latitude", "").strip(),
        "virtual_tour_url": form.get("virtual_tour_url", "").strip(),
        "documentation_summary": form.get("documentation_summary", "").strip(),
        "documentation_verified": 1 if form.get("documentation_verified") else 0,
        "payment_plan_summary": form.get("payment_plan_summary", "").strip(),
        "price": form.get("price", "").strip(),
        "price_suffix": form.get("price_suffix", "").strip(),
        "bedrooms": form.get("bedrooms", "").strip(),
        "bathrooms": form.get("bathrooms", "").strip(),
        "area_sqm": form.get("area_sqm", "").strip(),
        "summary": form.get("summary", "").strip(),
        "description": form.get("description", "").strip(),
        "featured": 1 if form.get("featured") else 0,
        "published": 1 if form.get("published") else 0,
        "image_path": form.get("existing_image_path", "").strip(),
        "gallery_paths": normalize_string_list(form.get("existing_gallery_paths", "")),
    }
    for key, _label in DISCOVERY_FEATURE_FIELDS + VERIFICATION_FIELDS:
        data[key] = 1 if form.get(key) else 0

    errors: list[str] = []

    for key, label in (
        ("title", "Title"),
        ("property_type", "Property type"),
        ("district", "District"),
        ("address", "Address"),
        ("summary", "Summary"),
        ("description", "Description"),
    ):
        if not data[key]:
            errors.append(f"{label} is required.")

    if data["status"] not in STATUS_OPTIONS:
        errors.append("Choose whether the listing is for sale, rent, or lease.")

    if data["availability"] not in AVAILABILITY_OPTIONS:
        errors.append("Choose a valid availability state.")
    elif data["status"] == "For Sale" and data["availability"] not in SALE_AVAILABILITY_OPTIONS:
        errors.append("Sale listings can be available, under offer, sold, or off market.")
    elif data["status"] == "For Rent" and data["availability"] not in RENT_AVAILABILITY_OPTIONS:
        errors.append("Rent listings can be available, under offer, rented, or off market.")
    elif data["status"] == "For Lease" and data["availability"] not in LEASE_AVAILABILITY_OPTIONS:
        errors.append("Lease listings can be available, under offer, leased, or off market.")

    if data["price_suffix"] not in PRICE_SUFFIX_OPTIONS:
        errors.append("Choose a valid price suffix.")

    if data["virtual_tour_url"] and not re.match(r"^https?://", data["virtual_tour_url"], re.I):
        errors.append("Virtual tour URL must start with http:// or https://.")

    if len(str(data["documentation_summary"])) > 1200:
        errors.append("Documentation summary must not exceed 1,200 characters.")
    if data["documentation_verified"] and not data["documentation_summary"]:
        errors.append("Add a documentation summary before marking it verified for public display.")
    if len(str(data["payment_plan_summary"])) > 1200:
        errors.append("Payment plan summary must not exceed 1,200 characters.")

    price, price_error = safe_int(str(data["price"]), "Price", minimum=1)
    bedrooms, bedrooms_error = safe_int(str(data["bedrooms"]), "Bedrooms", minimum=0)
    bathrooms, bathrooms_error = safe_int(str(data["bathrooms"]), "Bathrooms", minimum=0)
    area_sqm, area_error = safe_int(str(data["area_sqm"]), "Area", minimum=0)
    longitude, longitude_error = safe_float(
        str(data["longitude"]), "Longitude", minimum=-180, maximum=180
    )
    latitude, latitude_error = safe_float(
        str(data["latitude"]), "Latitude", minimum=-90, maximum=90
    )

    for message in (
        price_error,
        bedrooms_error,
        bathrooms_error,
        area_error,
        longitude_error,
        latitude_error,
    ):
        if message:
            errors.append(message)

    if bool(data["longitude"]) != bool(data["latitude"]):
        errors.append("Add both latitude and longitude, or leave both blank.")

    data["price"] = price if price is not None else data["price"]
    data["bedrooms"] = bedrooms if bedrooms is not None else data["bedrooms"]
    data["bathrooms"] = bathrooms if bathrooms is not None else data["bathrooms"]
    data["area_sqm"] = area_sqm if area_sqm is not None else data["area_sqm"]
    if data["longitude"] and longitude is not None:
        data["longitude"] = longitude
    elif not data["longitude"]:
        data["longitude"] = ""
    if data["latitude"] and latitude is not None:
        data["latitude"] = latitude
    elif not data["latitude"]:
        data["latitude"] = ""

    return data, errors


def validate_enquiry_form(form, listing: Mapping[str, object] | None = None) -> tuple[dict[str, str], list[str]]:
    data = {
        "listing_id": form.get("listing_id", "").strip(),
        "listing_title": form.get("listing_title", "").strip(),
        "name": form.get("name", "").strip(),
        "email": form.get("email", "").strip(),
        "phone": form.get("phone", "").strip(),
        "preferred_contact": form.get("preferred_contact", "Email").strip(),
        "message": form.get("message", "").strip(),
        "source_path": form.get("source_path", "").strip(),
    }
    errors: list[str] = []

    if listing is not None:
        data["listing_id"] = str(listing["id"])
        data["listing_title"] = str(listing["title"])

    if not data["name"]:
        errors.append("Your name is required.")
    if not data["email"] and not data["phone"]:
        errors.append("Add an email address or phone number so the team can reply.")
    if data["preferred_contact"] not in ENQUIRY_CONTACT_OPTIONS:
        errors.append("Choose a valid contact preference.")
    if not data["message"]:
        errors.append("Tell the team what you need help with.")

    return data, errors


def validate_maintenance_form(form) -> tuple[dict[str, str], dict[str, list[str]]]:
    data = maintenance_form_defaults()
    data.update(
        {
            "resident_name": form.get("resident_name", "").strip(),
            "email": form.get("email", "").strip(),
            "phone": form.get("phone", "").strip(),
            "unit_reference": form.get("unit_reference", "").strip(),
            "property_title": form.get("property_title", "").strip(),
            "issue_category": form.get("issue_category", "").strip(),
            "priority": form.get("priority", "").strip() or "Medium",
            "description": form.get("description", "").strip(),
            "assigned_vendor": form.get("assigned_vendor", "").strip(),
        }
    )
    errors: dict[str, list[str]] = {}

    def add_error(field: str, message: str) -> None:
        errors.setdefault(field, []).append(message)

    for key, label in (
        ("resident_name", "Resident name"),
        ("unit_reference", "Unit reference"),
        ("description", "Issue description"),
    ):
        if not data[key]:
            add_error(key, f"{label} is required.")

    if not data["email"] and not data["phone"]:
        message = "Add at least one contact method for follow-up."
        add_error("email", message)
        add_error("phone", message)
    if data["issue_category"] not in MAINTENANCE_CATEGORY_OPTIONS:
        add_error("issue_category", "Choose a valid maintenance category.")
    if data["priority"] not in MAINTENANCE_PRIORITY_OPTIONS:
        add_error("priority", "Choose a valid maintenance priority.")

    return data, errors


def validate_financial_record_form(form) -> tuple[dict[str, object], list[str]]:
    data = {
        "resident_name": form.get("resident_name", "").strip(),
        "unit_reference": form.get("unit_reference", "").strip(),
        "property_title": form.get("property_title", "").strip(),
        "charge_type": form.get("charge_type", "").strip(),
        "amount": form.get("amount", "").strip(),
        "due_date": form.get("due_date", "").strip(),
        "assigned_to": form.get("assigned_to", "").strip(),
        "status": form.get("status", "").strip(),
        "note": form.get("note", "").strip(),
    }
    errors: list[str] = []

    for key, label in (
        ("resident_name", "Resident name"),
        ("unit_reference", "Unit reference"),
        ("due_date", "Due date"),
    ):
        if not data[key]:
            errors.append(f"{label} is required.")

    if data["charge_type"] not in FINANCIAL_CHARGE_OPTIONS:
        errors.append("Choose a valid charge type.")
    if data["status"] not in FINANCIAL_STATUS_OPTIONS:
        errors.append("Choose a valid financial status.")

    amount, amount_error = safe_int(str(data["amount"]), "Amount", minimum=1)
    if amount_error:
        errors.append(amount_error)
    else:
        data["amount"] = amount

    if data["due_date"]:
        try:
            data["due_date"] = date.fromisoformat(data["due_date"]).isoformat()
        except ValueError:
            errors.append("Due date must use the YYYY-MM-DD format.")

    return data, errors


def validate_document_form(form) -> tuple[dict[str, str], list[str]]:
    data = {
        "resident_name": form.get("resident_name", "").strip(),
        "unit_reference": form.get("unit_reference", "").strip(),
        "property_title": form.get("property_title", "").strip(),
        "document_type": form.get("document_type", "").strip(),
        "title": form.get("title", "").strip(),
        "note": form.get("note", "").strip(),
    }
    errors: list[str] = []

    for key, label in (
        ("resident_name", "Resident name"),
        ("unit_reference", "Unit reference"),
        ("title", "Document title"),
    ):
        if not data[key]:
            errors.append(f"{label} is required.")

    if data["document_type"] not in DOCUMENT_TYPE_OPTIONS:
        errors.append("Choose a valid document type.")

    return data, errors


GUIDED_DOCUMENT_GENERATOR_BLUEPRINTS = {
    "billing": {
        "label": "Guided invoice fields",
        "description": "Use the normal form for operational billing details. The JSON payload is still generated and stored underneath.",
        "sections": [
            {
                "kicker": "Summary",
                "title": "Invoice details",
                "layout": "compact",
                "fields": [
                    {"name": "issue_date", "label": "Issue date", "kind": "date"},
                    {"name": "document_number", "label": "Invoice number", "kind": "text"},
                    {"name": "due_date", "label": "Due date", "kind": "date"},
                    {"name": "currency", "label": "Currency", "kind": "text", "placeholder": "NGN"},
                ],
            },
            {
                "kicker": "Bill to",
                "title": "Recipient details",
                "fields": [
                    {"name": "bill_to_name", "label": "Recipient name", "kind": "text"},
                    {"name": "bill_to_company", "label": "Company or unit", "kind": "text"},
                    {
                        "name": "bill_to_address_lines",
                        "label": "Address lines",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one line per address line.",
                    },
                ],
            },
            {
                "kicker": "Charges",
                "title": "Line items and payment terms",
                "fields": [
                    {
                        "name": "line_items",
                        "label": "Line items",
                        "kind": "textarea",
                        "rows": 6,
                        "help": "Use one line per item in this format: Description | Quantity | Unit price",
                    },
                    {
                        "name": "payment_instructions",
                        "label": "Payment instructions",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one instruction per line.",
                    },
                    {
                        "name": "notes",
                        "label": "Billing notes",
                        "kind": "textarea",
                        "rows": 3,
                        "help": "Optional notes shown below the totals.",
                    },
                    {
                        "name": "terms",
                        "label": "Terms",
                        "kind": "textarea",
                        "rows": 3,
                    },
                ],
            },
        ],
    },
    "payment_receipt": {
        "label": "Guided receipt fields",
        "description": "Capture the payer, receipt breakdown, and confirmation notes without editing raw JSON.",
        "sections": [
            {
                "kicker": "Summary",
                "title": "Receipt details",
                "layout": "compact",
                "fields": [
                    {"name": "issue_date", "label": "Issue date", "kind": "date"},
                    {"name": "document_number", "label": "Receipt number", "kind": "text"},
                    {"name": "payment_date", "label": "Payment date", "kind": "date"},
                    {"name": "currency", "label": "Currency", "kind": "text", "placeholder": "NGN"},
                    {"name": "payment_method", "label": "Payment method", "kind": "text"},
                    {"name": "payment_reference", "label": "Payment reference", "kind": "text"},
                    {"name": "received_by", "label": "Received by", "kind": "text"},
                ],
            },
            {
                "kicker": "Payer",
                "title": "Received from",
                "fields": [
                    {"name": "payer_name", "label": "Payer name", "kind": "text"},
                    {"name": "payer_company", "label": "Company or unit", "kind": "text"},
                    {
                        "name": "payer_address_lines",
                        "label": "Address lines",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one line per address line.",
                    },
                ],
            },
            {
                "kicker": "Breakdown",
                "title": "Receipt items and notes",
                "fields": [
                    {
                        "name": "receipt_items",
                        "label": "Receipt items",
                        "kind": "textarea",
                        "rows": 6,
                        "help": "Use one line per item in this format: Label | Amount",
                    },
                    {
                        "name": "notes",
                        "label": "Confirmation notes",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one note per line.",
                    },
                ],
            },
        ],
    },
    "maintenance_work_order": {
        "label": "Guided work-order fields",
        "description": "Use the structured form for the most common work-order data. Scope lines are turned into the assigned task table automatically.",
        "sections": [
            {
                "kicker": "Summary",
                "title": "Work-order details",
                "layout": "compact",
                "fields": [
                    {"name": "issue_date", "label": "Issue date", "kind": "date"},
                    {"name": "document_number", "label": "Document number", "kind": "text"},
                    {"name": "request_reference", "label": "Request reference", "kind": "text"},
                    {"name": "property_title", "label": "Property title", "kind": "text"},
                    {"name": "unit_reference", "label": "Unit or area", "kind": "text"},
                ],
            },
            {
                "kicker": "Vendor",
                "title": "Assigned parties",
                "fields": [
                    {"name": "vendor_name", "label": "Vendor name", "kind": "text"},
                    {"name": "vendor_company", "label": "Vendor company", "kind": "text"},
                    {"name": "vendor_phone", "label": "Vendor phone", "kind": "text"},
                    {"name": "vendor_email", "label": "Vendor email", "kind": "email"},
                    {
                        "name": "vendor_address_lines",
                        "label": "Vendor address lines",
                        "kind": "textarea",
                        "rows": 3,
                        "help": "Use one line per address line.",
                    },
                    {"name": "issued_by_name", "label": "Issued by", "kind": "text"},
                    {"name": "issued_by_role", "label": "Issuer role", "kind": "text"},
                    {"name": "issued_by_phone", "label": "Issuer phone", "kind": "text"},
                    {"name": "issued_by_email", "label": "Issuer email", "kind": "email"},
                ],
            },
            {
                "kicker": "Scope",
                "title": "Issue and execution details",
                "fields": [
                    {
                        "name": "issue_summary",
                        "label": "Issue summary",
                        "kind": "textarea",
                        "rows": 4,
                    },
                    {
                        "name": "scope_items",
                        "label": "Assigned scope",
                        "kind": "textarea",
                        "rows": 7,
                        "help": "Use one line per item in this format: Task | Priority | Materials | Execution note",
                    },
                    {
                        "name": "site_notes",
                        "label": "Site access and instructions",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one note per line.",
                    },
                    {
                        "name": "completion_requirements",
                        "label": "Completion requirements",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one requirement per line.",
                    },
                ],
            },
        ],
    },
    "lease_notice": {
        "label": "Guided lease-notice fields",
        "description": "Handle the main lease-renewal and rent-review content from a normal form, while the system keeps the formal notice payload intact.",
        "sections": [
            {
                "kicker": "Summary",
                "title": "Notice details",
                "layout": "compact",
                "fields": [
                    {"name": "issue_date", "label": "Issue date", "kind": "date"},
                    {"name": "document_number", "label": "Notice number", "kind": "text"},
                    {"name": "notice_type", "label": "Notice type", "kind": "text"},
                    {"name": "current_term_end", "label": "Current term end", "kind": "date"},
                    {"name": "proposed_start", "label": "Proposed start", "kind": "date"},
                    {"name": "response_deadline", "label": "Response deadline", "kind": "date"},
                ],
            },
            {
                "kicker": "Tenant",
                "title": "Tenant and premises",
                "fields": [
                    {"name": "tenant_name", "label": "Tenant name", "kind": "text"},
                    {"name": "tenant_company", "label": "Company or unit", "kind": "text"},
                    {
                        "name": "tenant_address_lines",
                        "label": "Tenant address lines",
                        "kind": "textarea",
                        "rows": 3,
                        "help": "Use one line per address line.",
                    },
                    {"name": "property_title", "label": "Property title", "kind": "text"},
                    {"name": "unit_reference", "label": "Unit or area", "kind": "text"},
                ],
            },
            {
                "kicker": "Terms",
                "title": "Commercial terms and response guidance",
                "fields": [
                    {"name": "current_rent", "label": "Current rent", "kind": "text"},
                    {"name": "proposed_rent", "label": "Proposed rent", "kind": "text"},
                    {"name": "service_charge_note", "label": "Service-charge note", "kind": "textarea", "rows": 3},
                    {"name": "notice_reason", "label": "Notice reason", "kind": "textarea", "rows": 4},
                    {
                        "name": "key_terms",
                        "label": "Key terms",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one term per line.",
                    },
                    {
                        "name": "response_options",
                        "label": "Response options",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one option per line.",
                    },
                    {
                        "name": "next_steps",
                        "label": "Next steps",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one step per line.",
                    },
                    {
                        "name": "special_conditions",
                        "label": "Special conditions",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one condition per line.",
                    },
                ],
            },
        ],
    },
    "tenancy_agreement": {
        "label": "Guided tenancy fields",
        "description": "The guided editor covers the core party, rent, use, covenant, and house-rule sections. The full payload remains available under the advanced panel.",
        "sections": [
            {
                "kicker": "Summary",
                "title": "Agreement details",
                "layout": "compact",
                "fields": [
                    {"name": "issue_date", "label": "Issue date", "kind": "date"},
                    {"name": "document_number", "label": "Agreement number", "kind": "text"},
                    {"name": "commencement_date", "label": "Commencement date", "kind": "date"},
                    {"name": "expiry_date", "label": "Expiry date", "kind": "date"},
                    {"name": "tenancy_type", "label": "Tenancy type", "kind": "text"},
                ],
            },
            {
                "kicker": "Parties",
                "title": "Landlord, tenant, and premises",
                "fields": [
                    {"name": "landlord_name", "label": "Landlord name", "kind": "text"},
                    {"name": "landlord_company", "label": "Landlord company", "kind": "text"},
                    {
                        "name": "landlord_address_lines",
                        "label": "Landlord address lines",
                        "kind": "textarea",
                        "rows": 3,
                        "help": "Use one line per address line.",
                    },
                    {"name": "tenant_name", "label": "Tenant name", "kind": "text"},
                    {"name": "tenant_company", "label": "Tenant company", "kind": "text"},
                    {
                        "name": "tenant_address_lines",
                        "label": "Tenant address lines",
                        "kind": "textarea",
                        "rows": 3,
                        "help": "Use one line per address line.",
                    },
                    {"name": "property_title", "label": "Property title", "kind": "text"},
                    {
                        "name": "premises_address",
                        "label": "Premises address",
                        "kind": "textarea",
                        "rows": 3,
                    },
                ],
            },
            {
                "kicker": "Commercial",
                "title": "Rent, use, and core terms",
                "fields": [
                    {"name": "permitted_use", "label": "Permitted use", "kind": "textarea", "rows": 3},
                    {"name": "rent_amount", "label": "Rent amount", "kind": "text"},
                    {"name": "deposit_amount", "label": "Deposit amount", "kind": "text"},
                    {"name": "payment_schedule", "label": "Payment schedule", "kind": "textarea", "rows": 3},
                    {
                        "name": "included_services",
                        "label": "Included services",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one service per line.",
                    },
                    {
                        "name": "utilities_and_outgoings",
                        "label": "Utilities and outgoings",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one item per line.",
                    },
                ],
            },
            {
                "kicker": "Conditions",
                "title": "Covenants, access, defaults, and house rules",
                "fields": [
                    {
                        "name": "landlord_covenants",
                        "label": "Landlord covenants",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one covenant per line.",
                    },
                    {
                        "name": "tenant_covenants",
                        "label": "Tenant covenants",
                        "kind": "textarea",
                        "rows": 5,
                        "help": "Use one covenant per line.",
                    },
                    {
                        "name": "inspection_access",
                        "label": "Inspection and access",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one access condition per line.",
                    },
                    {
                        "name": "default_events",
                        "label": "Default events",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one default event per line.",
                    },
                    {
                        "name": "house_rules",
                        "label": "House rules",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one rule per line.",
                    },
                    {
                        "name": "inventory_schedule",
                        "label": "Inventory and handover schedule",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one item per line.",
                    },
                    {
                        "name": "special_conditions",
                        "label": "Special conditions",
                        "kind": "textarea",
                        "rows": 4,
                        "help": "Use one condition per line.",
                    },
                ],
            },
        ],
    },
}


def guided_document_blueprint(template_key: str) -> dict[str, object] | None:
    blueprint = GUIDED_DOCUMENT_GENERATOR_BLUEPRINTS.get(template_key)
    return copy.deepcopy(blueprint) if blueprint else None


def guided_document_field_names(template_key: str) -> list[str]:
    blueprint = GUIDED_DOCUMENT_GENERATOR_BLUEPRINTS.get(template_key)
    if not blueprint:
        return []
    names: list[str] = []
    for section in blueprint["sections"]:
        for field in section["fields"]:
            names.append(str(field["name"]))
    return names


def split_multiline_field(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def lines_to_multiline(values: object) -> str:
    if not isinstance(values, list):
        return ""
    return "\n".join(str(item or "").strip() for item in values if str(item or "").strip())


def rows_to_pipe_text(rows: object, keys: tuple[str, ...]) -> str:
    if not isinstance(rows, list):
        return ""
    rendered_rows: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parts = [str(row.get(key) or "").strip() for key in keys]
        if any(parts):
            rendered_rows.append(" | ".join(parts))
    return "\n".join(rendered_rows)


def parse_pipe_rows(value: str, keys: tuple[str, ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        while len(parts) < len(keys):
            parts.append("")
        rows.append({key: parts[index] for index, key in enumerate(keys)})
    return rows


def sample_generator_payload_data(template_key: str, current_site_settings: dict[str, str]) -> dict[str, object]:
    catalog = document_generator_catalog(current_site_settings)
    return copy.deepcopy(catalog.get(template_key, {}).get("sample_payload", {}))


def party_block_from_guided(guided_data: dict[str, str], prefix: str) -> dict[str, object]:
    return {
        "name": guided_data.get(f"{prefix}_name", ""),
        "company": guided_data.get(f"{prefix}_company", ""),
        "role": guided_data.get(f"{prefix}_role", ""),
        "email": guided_data.get(f"{prefix}_email", ""),
        "phone": guided_data.get(f"{prefix}_phone", ""),
        "address_lines": split_multiline_field(guided_data.get(f"{prefix}_address_lines", "")),
    }


def apply_party_block_to_guided(guided_data: dict[str, str], prefix: str, block: object) -> None:
    if not isinstance(block, Mapping):
        block = {}
    guided_data[f"{prefix}_name"] = str(block.get("name") or "").strip()
    guided_data[f"{prefix}_company"] = str(block.get("company") or "").strip()
    guided_data[f"{prefix}_role"] = str(block.get("role") or "").strip()
    guided_data[f"{prefix}_email"] = str(block.get("email") or "").strip()
    guided_data[f"{prefix}_phone"] = str(block.get("phone") or "").strip()
    guided_data[f"{prefix}_address_lines"] = lines_to_multiline(block.get("address_lines"))


def collect_guided_form_data(template_key: str, form) -> dict[str, str]:
    return {
        field_name: form.get(f"guided_{field_name}", "").strip()
        for field_name in guided_document_field_names(template_key)
    }


def guided_form_data_from_payload(
    template_key: str,
    payload: dict[str, object] | None,
    current_site_settings: dict[str, str],
) -> dict[str, str]:
    if not guided_document_blueprint(template_key):
        return {}

    source = copy.deepcopy(payload or sample_generator_payload_data(template_key, current_site_settings))
    guided_data = {field_name: "" for field_name in guided_document_field_names(template_key)}
    guided_data["issue_date"] = str(source.get("issue_date") or "").strip()
    guided_data["document_number"] = str(source.get("document_number") or "").strip()

    if template_key == "billing":
        guided_data["due_date"] = str(source.get("due_date") or "").strip()
        guided_data["currency"] = str(source.get("currency") or "").strip()
        apply_party_block_to_guided(guided_data, "bill_to", source.get("bill_to"))
        guided_data["line_items"] = rows_to_pipe_text(source.get("line_items"), ("description", "quantity", "unit_price"))
        guided_data["payment_instructions"] = lines_to_multiline(source.get("payment_instructions"))
        guided_data["notes"] = lines_to_multiline(source.get("notes"))
        guided_data["terms"] = str(source.get("terms") or "").strip()
    elif template_key == "payment_receipt":
        guided_data["payment_date"] = str(source.get("payment_date") or "").strip()
        guided_data["currency"] = str(source.get("currency") or "").strip()
        guided_data["payment_method"] = str(source.get("payment_method") or "").strip()
        guided_data["payment_reference"] = str(source.get("payment_reference") or "").strip()
        guided_data["received_by"] = str(source.get("received_by") or "").strip()
        apply_party_block_to_guided(guided_data, "payer", source.get("payer"))
        guided_data["receipt_items"] = rows_to_pipe_text(source.get("receipt_items"), ("label", "amount"))
        guided_data["notes"] = lines_to_multiline(source.get("notes"))
    elif template_key == "maintenance_work_order":
        guided_data["request_reference"] = str(source.get("request_reference") or "").strip()
        guided_data["property_title"] = str(source.get("property_title") or "").strip()
        guided_data["unit_reference"] = str(source.get("unit_reference") or "").strip()
        guided_data["issue_summary"] = str(source.get("issue_summary") or "").strip()
        apply_party_block_to_guided(guided_data, "vendor", source.get("vendor"))
        apply_party_block_to_guided(guided_data, "issued_by", source.get("issued_by"))
        guided_data["scope_items"] = rows_to_pipe_text(source.get("scope_items"), ("task", "priority", "materials", "note"))
        guided_data["site_notes"] = lines_to_multiline(source.get("site_notes"))
        guided_data["completion_requirements"] = lines_to_multiline(source.get("completion_requirements"))
    elif template_key == "lease_notice":
        guided_data["notice_type"] = str(source.get("notice_type") or "").strip()
        guided_data["current_term_end"] = str(source.get("current_term_end") or "").strip()
        guided_data["proposed_start"] = str(source.get("proposed_start") or "").strip()
        guided_data["response_deadline"] = str(source.get("response_deadline") or "").strip()
        guided_data["property_title"] = str(source.get("property_title") or "").strip()
        guided_data["unit_reference"] = str(source.get("unit_reference") or "").strip()
        guided_data["current_rent"] = str(source.get("current_rent") or "").strip()
        guided_data["proposed_rent"] = str(source.get("proposed_rent") or "").strip()
        guided_data["service_charge_note"] = str(source.get("service_charge_note") or "").strip()
        guided_data["notice_reason"] = str(source.get("notice_reason") or "").strip()
        apply_party_block_to_guided(guided_data, "tenant", source.get("tenant"))
        guided_data["key_terms"] = lines_to_multiline(source.get("key_terms"))
        guided_data["response_options"] = lines_to_multiline(source.get("response_options"))
        guided_data["next_steps"] = lines_to_multiline(source.get("next_steps"))
        guided_data["special_conditions"] = lines_to_multiline(source.get("special_conditions"))
    elif template_key == "tenancy_agreement":
        guided_data["commencement_date"] = str(source.get("commencement_date") or "").strip()
        guided_data["expiry_date"] = str(source.get("expiry_date") or "").strip()
        guided_data["tenancy_type"] = str(source.get("tenancy_type") or "").strip()
        guided_data["property_title"] = str(source.get("property_title") or "").strip()
        guided_data["premises_address"] = str(source.get("premises_address") or "").strip()
        guided_data["permitted_use"] = str(source.get("permitted_use") or "").strip()
        guided_data["rent_amount"] = str(source.get("rent_amount") or "").strip()
        guided_data["deposit_amount"] = str(source.get("deposit_amount") or "").strip()
        guided_data["payment_schedule"] = str(source.get("payment_schedule") or "").strip()
        apply_party_block_to_guided(guided_data, "landlord", source.get("landlord"))
        apply_party_block_to_guided(guided_data, "tenant", source.get("tenant"))
        guided_data["included_services"] = lines_to_multiline(source.get("included_services"))
        guided_data["utilities_and_outgoings"] = lines_to_multiline(source.get("utilities_and_outgoings"))
        guided_data["landlord_covenants"] = lines_to_multiline(source.get("landlord_covenants"))
        guided_data["tenant_covenants"] = lines_to_multiline(source.get("tenant_covenants"))
        guided_data["inspection_access"] = lines_to_multiline(source.get("inspection_access"))
        guided_data["default_events"] = lines_to_multiline(source.get("default_events"))
        guided_data["house_rules"] = lines_to_multiline(source.get("house_rules"))
        guided_data["inventory_schedule"] = lines_to_multiline(source.get("inventory_schedule"))
        guided_data["special_conditions"] = lines_to_multiline(source.get("special_conditions"))

    return guided_data


def build_guided_generator_payload(
    template_key: str,
    guided_data: dict[str, str],
    current_site_settings: dict[str, str],
) -> dict[str, object]:
    payload = sample_generator_payload_data(template_key, current_site_settings)
    payload["issue_date"] = guided_data.get("issue_date", "")
    payload["document_number"] = guided_data.get("document_number", "")

    if template_key == "billing":
        payload["due_date"] = guided_data.get("due_date", "")
        payload["currency"] = guided_data.get("currency", "")
        payload["bill_to"] = party_block_from_guided(guided_data, "bill_to")
        payload["line_items"] = parse_pipe_rows(guided_data.get("line_items", ""), ("description", "quantity", "unit_price"))
        payload["payment_instructions"] = split_multiline_field(guided_data.get("payment_instructions", ""))
        payload["notes"] = split_multiline_field(guided_data.get("notes", ""))
        payload["terms"] = guided_data.get("terms", "")
    elif template_key == "payment_receipt":
        payload["payment_date"] = guided_data.get("payment_date", "")
        payload["currency"] = guided_data.get("currency", "")
        payload["payment_method"] = guided_data.get("payment_method", "")
        payload["payment_reference"] = guided_data.get("payment_reference", "")
        payload["received_by"] = guided_data.get("received_by", "")
        payload["payer"] = party_block_from_guided(guided_data, "payer")
        payload["receipt_items"] = parse_pipe_rows(guided_data.get("receipt_items", ""), ("label", "amount"))
        payload["notes"] = split_multiline_field(guided_data.get("notes", ""))
    elif template_key == "maintenance_work_order":
        payload["request_reference"] = guided_data.get("request_reference", "")
        payload["property_title"] = guided_data.get("property_title", "")
        payload["unit_reference"] = guided_data.get("unit_reference", "")
        payload["vendor"] = party_block_from_guided(guided_data, "vendor")
        payload["issued_by"] = party_block_from_guided(guided_data, "issued_by")
        payload["issue_summary"] = guided_data.get("issue_summary", "")
        payload["scope_items"] = parse_pipe_rows(guided_data.get("scope_items", ""), ("task", "priority", "materials", "note"))
        payload["site_notes"] = split_multiline_field(guided_data.get("site_notes", ""))
        payload["completion_requirements"] = split_multiline_field(guided_data.get("completion_requirements", ""))
    elif template_key == "lease_notice":
        payload["tenant"] = party_block_from_guided(guided_data, "tenant")
        payload["property_title"] = guided_data.get("property_title", "")
        payload["unit_reference"] = guided_data.get("unit_reference", "")
        payload["notice_type"] = guided_data.get("notice_type", "")
        payload["current_term_end"] = guided_data.get("current_term_end", "")
        payload["proposed_start"] = guided_data.get("proposed_start", "")
        payload["current_rent"] = guided_data.get("current_rent", "")
        payload["proposed_rent"] = guided_data.get("proposed_rent", "")
        payload["notice_reason"] = guided_data.get("notice_reason", "")
        payload["service_charge_note"] = guided_data.get("service_charge_note", "")
        payload["response_deadline"] = guided_data.get("response_deadline", "")
        payload["key_terms"] = split_multiline_field(guided_data.get("key_terms", ""))
        payload["response_options"] = split_multiline_field(guided_data.get("response_options", ""))
        payload["next_steps"] = split_multiline_field(guided_data.get("next_steps", ""))
        payload["special_conditions"] = split_multiline_field(guided_data.get("special_conditions", ""))
    elif template_key == "tenancy_agreement":
        payload["commencement_date"] = guided_data.get("commencement_date", "")
        payload["expiry_date"] = guided_data.get("expiry_date", "")
        payload["tenancy_type"] = guided_data.get("tenancy_type", "")
        payload["landlord"] = party_block_from_guided(guided_data, "landlord")
        payload["tenant"] = party_block_from_guided(guided_data, "tenant")
        payload["property_title"] = guided_data.get("property_title", "")
        payload["premises_address"] = guided_data.get("premises_address", "")
        payload["permitted_use"] = guided_data.get("permitted_use", "")
        payload["rent_amount"] = guided_data.get("rent_amount", "")
        payload["deposit_amount"] = guided_data.get("deposit_amount", "")
        payload["payment_schedule"] = guided_data.get("payment_schedule", "")
        payload["included_services"] = split_multiline_field(guided_data.get("included_services", ""))
        payload["utilities_and_outgoings"] = split_multiline_field(guided_data.get("utilities_and_outgoings", ""))
        payload["landlord_covenants"] = split_multiline_field(guided_data.get("landlord_covenants", ""))
        payload["tenant_covenants"] = split_multiline_field(guided_data.get("tenant_covenants", ""))
        payload["inspection_access"] = split_multiline_field(guided_data.get("inspection_access", ""))
        payload["default_events"] = split_multiline_field(guided_data.get("default_events", ""))
        payload["house_rules"] = split_multiline_field(guided_data.get("house_rules", ""))
        payload["inventory_schedule"] = split_multiline_field(guided_data.get("inventory_schedule", ""))
        payload["special_conditions"] = split_multiline_field(guided_data.get("special_conditions", ""))

    return payload


def validate_document_generation_form(
    form,
    current_site_settings: dict[str, str],
) -> tuple[dict[str, str], dict[str, object], list[str], dict[str, str]]:
    data = {
        "template_key": form.get("template_key", "").strip(),
        "title": form.get("title", "").strip(),
        "resident_name": form.get("resident_name", "").strip(),
        "unit_reference": form.get("unit_reference", "").strip(),
        "property_title": form.get("property_title", "").strip(),
        "note": form.get("note", "").strip(),
        "payload_json": form.get("payload_json", "").strip(),
        "use_advanced_payload": "1" if form.get("use_advanced_payload", "").strip() else "",
    }
    guided_form_data = collect_guided_form_data(data["template_key"], form)
    errors: list[str] = []

    for key, label in (
        ("template_key", "Template"),
        ("title", "Document title"),
        ("resident_name", "Client or record owner"),
        ("unit_reference", "Reference"),
    ):
        if not data[key]:
            errors.append(f"{label} is required.")

    guided_supported = guided_document_blueprint(data["template_key"]) is not None
    use_advanced_payload = data["use_advanced_payload"] == "1" or not guided_supported

    payload_data: dict[str, object] = {}
    if use_advanced_payload:
        if not data["payload_json"]:
            errors.append("Advanced data is required.")
        elif data["payload_json"]:
            try:
                parsed = json.loads(data["payload_json"])
            except json.JSONDecodeError as error:
                errors.append(f"Advanced data is invalid: {error.msg}.")
            else:
                if not isinstance(parsed, dict):
                    errors.append("Advanced data must be an object at the top level.")
                else:
                    payload_data = parsed
    elif guided_supported:
        payload_data = build_guided_generator_payload(data["template_key"], guided_form_data, current_site_settings)
        data["payload_json"] = json.dumps(payload_data, indent=2)

    if errors:
        return data, payload_data, errors, guided_form_data

    validated_payload, payload_errors = validate_generator_payload(
        data["template_key"],
        payload_data,
        current_site_settings,
    )
    if payload_errors:
        errors.extend(payload_errors)
    else:
        data["payload_json"] = json.dumps(validated_payload, indent=2)
        payload_data = validated_payload
        if guided_supported and not use_advanced_payload:
            guided_form_data = guided_form_data_from_payload(data["template_key"], validated_payload, current_site_settings)

    return data, payload_data, errors, guided_form_data


def validate_site_settings_form(form) -> tuple[dict[str, str], list[str]]:
    data = {key: form.get(key, "").strip() for key in SITE_SETTING_FIELDS}
    errors: list[str] = []

    for key, label in (
        ("site_name", "Site name"),
        ("contact_email", "Contact email"),
        ("contact_phone_display", "Contact phone display"),
        ("whatsapp_phone", "WhatsApp phone"),
        ("coverage_area", "Coverage area"),
        ("footer_summary", "Footer summary"),
        ("homepage_hero_heading", "Homepage hero heading"),
        ("homepage_hero_intro", "Homepage hero intro"),
        ("homepage_primary_cta", "Homepage primary CTA"),
        ("homepage_secondary_cta", "Homepage secondary CTA"),
    ):
        if not data[key]:
            errors.append(f"{label} is required.")

    if data["contact_email"] and "@" not in data["contact_email"]:
        errors.append("Contact email must be a valid email address.")

    if not data["contact_phone_raw"]:
        data["contact_phone_raw"] = data["contact_phone_display"]

    if not normalize_digits(data["contact_phone_raw"]):
        errors.append("Contact phone must include digits.")
    if not normalize_digits(data["whatsapp_phone"]):
        errors.append("WhatsApp phone must include digits.")

    return data, errors


def normalize_optional_date(value: str, field_name: str) -> tuple[str, str | None]:
    raw = (value or "").strip()
    if not raw:
        return "", None
    try:
        return date.fromisoformat(raw).isoformat(), None
    except ValueError:
        return "", f"{field_name} must use the YYYY-MM-DD format."


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_cloudinary_asset(image_path: str | None) -> bool:
    return bool(image_path and image_path.startswith("cloudinary:"))


def cloudinary_public_id(image_path: str) -> str:
    if not is_cloudinary_asset(image_path):
        return ""
    return image_path.split(":", 1)[1].strip()


def cloudinary_asset_path(public_id: str) -> str:
    return f"cloudinary:{public_id}"


def uploaded_asset_exists(image_path: str) -> bool:
    if is_cloudinary_asset(image_path):
        return True
    if not image_path.startswith("uploads/"):
        return False
    return (STATIC_DIR / image_path).exists()


def save_uploaded_asset(image_path: str, payload: bytes) -> None:
    if storage_backend() == "cloudinary":
        public_id = cloudinary_public_id(image_path)
        if not public_id:
            raise ValueError("The image could not be prepared for cloud upload.")
        try:
            configure_cloudinary()
            cloudinary.uploader.upload(
                io.BytesIO(payload),
                public_id=public_id,
                overwrite=True,
                invalidate=True,
                resource_type="image",
                format="webp",
            )
        except CloudinaryError as error:
            raise ValueError("The image could not be uploaded to cloud storage.") from error
        return

    destination = STATIC_DIR / image_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def delete_uploaded_image(image_path: str | None) -> None:
    if not image_path:
        return
    if is_cloudinary_asset(image_path):
        try:
            configure_cloudinary()
            cloudinary.uploader.destroy(
                cloudinary_public_id(image_path),
                invalidate=True,
                resource_type="image",
            )
        except CloudinaryError:
            return
        return

    if not image_path.startswith("uploads/"):
        return

    file_path = STATIC_DIR / image_path
    if file_path.exists():
        file_path.unlink()


def normalize_uploaded_image(file_storage, current_image_path: str | None = None) -> str | None:
    if not file_storage or not file_storage.filename:
        return current_image_path

    filename = secure_filename(file_storage.filename)
    if not allowed_file(filename):
        raise ValueError("Upload a JPG, PNG, or WEBP image.")

    if storage_backend() == "cloudinary":
        folder = app.config["CLOUDINARY_FOLDER"] or "structurebase/listings"
        stored_path = cloudinary_asset_path(f"{folder}/{uuid.uuid4().hex}")
    else:
        stored_path = f"uploads/{uuid.uuid4().hex}.webp"

    try:
        with Image.open(file_storage.stream) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1800, 1800))
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, "WEBP", quality=82, method=6)
    except UnidentifiedImageError as error:
        raise ValueError("The uploaded file is not a valid image.") from error

    save_uploaded_asset(stored_path, buffer.getvalue())
    delete_uploaded_image(current_image_path)
    return stored_path


def normalize_uploaded_gallery(files, current_gallery_paths: list[str] | None = None) -> list[str]:
    gallery_paths = [path for path in (current_gallery_paths or []) if path]
    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue
        stored_path = normalize_uploaded_image(file_storage, current_image_path=None)
        if stored_path:
            gallery_paths.append(stored_path)
    return gallery_paths


def allowed_document(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS


def save_document_upload(file_storage) -> dict[str, object]:
    if not file_storage or not file_storage.filename:
        raise ValueError("Upload a document file before saving.")

    filename = secure_filename(file_storage.filename)
    if not allowed_document(filename):
        raise ValueError("Upload PDF, JPG, PNG, or WEBP files for documents.")

    extension = filename.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    destination = DOCUMENTS_DIR / stored_name
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    file_storage.save(destination)

    mime_type = file_storage.mimetype or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return {
        "stored_filename": stored_name,
        "original_filename": filename,
        "mime_type": mime_type,
        "file_size": destination.stat().st_size,
    }


def save_generated_document_pdf(title: str, pdf_path: Path) -> dict[str, object]:
    filename = secure_filename(title) or f"generated-document-{uuid.uuid4().hex[:8]}"
    original_filename = f"{filename}.pdf"
    stored_name = f"{uuid.uuid4().hex}.pdf"
    destination = DOCUMENTS_DIR / stored_name
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pdf_path.read_bytes())
    return {
        "stored_filename": stored_name,
        "original_filename": original_filename,
        "mime_type": "application/pdf",
        "file_size": destination.stat().st_size,
    }


def delete_document_file(stored_filename: str | None) -> None:
    if not stored_filename:
        return
    file_path = DOCUMENTS_DIR / stored_filename
    if not file_path.exists():
        return

    for attempt in range(3):
        try:
            file_path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 2:
                app.logger.warning("Document file could not be deleted immediately: %s", file_path)
                return
            time.sleep(0.15)


def sqlite_listing_id(listing_id: str) -> int:
    try:
        return int(listing_id)
    except (TypeError, ValueError):
        abort(404)


def fetch_enquiry(enquiry_id: str) -> dict[str, object]:
    if database_backend() == "mongodb":
        row = get_mongo_enquiries_collection().find_one({"public_id": enquiry_id})
        if row is None:
            abort(404)
        return normalize_enquiry_record(row)

    row = get_db().execute("SELECT * FROM enquiries WHERE public_id = ?", (enquiry_id,)).fetchone()
    if row is None:
        abort(404)
    return normalize_enquiry_record(row)


def get_or_create_contact(*, name: str, email: str = "", phone: str = "", whatsapp: str = "") -> str:
    email_key = normalize_contact_email(email)
    phone_key = normalize_contact_phone(phone)
    query_parts = []
    if email_key:
        query_parts.append({"email_key": email_key})
    if phone_key:
        query_parts.append({"phone_key": phone_key})
    now = utc_now_iso()

    if database_backend() == "mongodb":
        contacts = get_mongo_contacts_collection()
        existing = contacts.find_one({"$or": query_parts}) if query_parts else None
        if existing:
            contact_id = str(existing["public_id"])
            contacts.update_one(
                {"public_id": contact_id},
                {"$set": {"full_name": name, "email": email, "phone": phone, "whatsapp": whatsapp, "updated_at": now}},
            )
            return contact_id
        payload = {
            "public_id": uuid.uuid4().hex[:12], "full_name": name, "email": email, "phone": phone,
            "whatsapp": whatsapp, "created_at": now, "updated_at": now,
        }
        if email_key:
            payload["email_key"] = email_key
        if phone_key:
            payload["phone_key"] = phone_key
        try:
            contacts.insert_one(payload)
            return str(payload["public_id"])
        except DuplicateKeyError:
            existing = contacts.find_one({"$or": query_parts}) if query_parts else None
            if existing:
                return str(existing["public_id"])
            raise

    db = get_db()
    existing = None
    if email_key:
        existing = db.execute("SELECT * FROM contacts WHERE email_key = ?", (email_key,)).fetchone()
    if existing is None and phone_key:
        existing = db.execute("SELECT * FROM contacts WHERE phone_key = ?", (phone_key,)).fetchone()
    if existing is not None:
        contact_id = str(existing["public_id"])
        db.execute(
            "UPDATE contacts SET full_name = ?, email = ?, phone = ?, whatsapp = ?, updated_at = ? WHERE public_id = ?",
            (name, email, phone, whatsapp, now, contact_id),
        )
        db.commit()
        return contact_id
    contact_id = uuid.uuid4().hex[:12]
    db.execute(
        """INSERT INTO contacts (public_id, full_name, email, email_key, phone, phone_key, whatsapp, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (contact_id, name, email, email_key, phone, phone_key, whatsapp, now, now),
    )
    db.commit()
    return contact_id


def backfill_lead_contacts() -> None:
    """Attach legacy enquiries to canonical contacts without changing their public IDs."""
    for lead in all_enquiries():
        if str(lead.get("contact_id") or ""):
            continue
        contact_id = get_or_create_contact(
            name=str(lead.get("name") or "Lead contact"), email=str(lead.get("email") or ""),
            phone=str(lead.get("phone") or ""), whatsapp=str(lead.get("whatsapp") or ""),
        )
        if database_backend() == "mongodb":
            get_mongo_enquiries_collection().update_one(
                {"public_id": lead["id"]}, {"$set": {"contact_id": contact_id}}
            )
        else:
            get_db().execute(
                "UPDATE enquiries SET contact_id = ? WHERE public_id = ?", (contact_id, lead["id"])
            )
            get_db().commit()


def fetch_contact(contact_id: str) -> dict[str, object] | None:
    if not contact_id:
        return None
    if database_backend() == "mongodb":
        row = get_mongo_contacts_collection().find_one({"public_id": contact_id})
    else:
        row = get_db().execute("SELECT * FROM contacts WHERE public_id = ?", (contact_id,)).fetchone()
    return normalize_contact_record(row) if row is not None else None


def lead_notes(lead_id: str) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_lead_notes_collection().find({"lead_id": lead_id}).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute(
            "SELECT * FROM lead_notes WHERE lead_id = ? ORDER BY created_at DESC", (lead_id,)
        ).fetchall()
    return [normalize_lead_note_record(row) for row in rows]


def create_lead_note(lead_id: str, body: str) -> str:
    staff = current_staff()
    if staff is None:
        abort(401)
    payload = {
        "public_id": uuid.uuid4().hex[:12], "lead_id": lead_id, "body": body,
        "actor_id": str(staff["id"]), "actor_label": str(staff["full_name"]), "created_at": utc_now_iso(),
    }
    if database_backend() == "mongodb":
        get_mongo_lead_notes_collection().insert_one(payload)
    else:
        get_db().execute(
            "INSERT INTO lead_notes (public_id, lead_id, body, actor_id, actor_label, created_at) VALUES (:public_id, :lead_id, :body, :actor_id, :actor_label, :created_at)",
            payload,
        )
        get_db().commit()
    return str(payload["public_id"])


def activity_for_entity(entity_type: str, entity_id: str) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_activity_collection().find(
            {"entity_type": entity_type, "entity_id": entity_id}
        ).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute(
            "SELECT * FROM activity_log WHERE entity_type = ? AND entity_id = ? ORDER BY created_at DESC",
            (entity_type, entity_id),
        ).fetchall()
    return [normalize_activity_record(row) for row in rows]


def related_listing_for_enquiry(enquiry: Mapping[str, object]) -> dict[str, object] | None:
    listing_id = str(enquiry.get("listing_id") or "").strip()
    if not listing_id:
        return None
    try:
        return fetch_listing(listing_id, include_unpublished=True)
    except NotFound:
        return None


def create_activity_record(
    *,
    entity_type: str,
    entity_id: str | None,
    action: str,
    summary: str,
    actor_label: str = "",
    actor_id: str = "",
    actor_type: str = "system",
    metadata: Mapping[str, object] | None = None,
) -> None:
    staff = current_staff() if has_request_context() else None
    if staff is not None and actor_label in {"", "Admin"}:
        actor_label = str(staff.get("full_name") or staff.get("username") or "Staff")
        actor_id = str(staff.get("id") or "")
        actor_type = "staff"
    elif actor_label in {"Tenant", "Public enquiry"}:
        actor_type = "public"
    metadata_payload = dict(metadata or {})
    payload = {
        "public_id": uuid.uuid4().hex[:12],
        "entity_type": entity_type,
        "entity_id": entity_id or "",
        "action": action,
        "actor_label": actor_label or "System",
        "actor_id": actor_id,
        "actor_type": actor_type,
        "metadata_json": json.dumps(metadata_payload, separators=(",", ":"), default=str),
        "summary": summary,
        "created_at": utc_now_iso(),
    }
    if database_backend() == "mongodb":
        mongo_payload = dict(payload)
        mongo_payload["metadata"] = metadata_payload
        mongo_payload.pop("metadata_json", None)
        get_mongo_activity_collection().insert_one(mongo_payload)
        return

    get_db().execute(
        """
        INSERT INTO activity_log (
            public_id,
            entity_type,
            entity_id,
            action,
            actor_label,
            actor_id,
            actor_type,
            metadata_json,
            summary,
            created_at
        ) VALUES (
            :public_id,
            :entity_type,
            :entity_id,
            :action,
            :actor_label,
            :actor_id,
            :actor_type,
            :metadata_json,
            :summary,
            :created_at
        )
        """,
        payload,
    )
    get_db().commit()


def recent_activity(limit: int = 10) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_activity_collection().find({}).sort("created_at", DESCENDING).limit(limit)
        return [normalize_activity_record(item) for item in cursor]

    rows = get_db().execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [normalize_activity_record(row) for row in rows]


def query_activity_records(
    *, query: str = "", entity_type: str = "", actor_type: str = "", limit: int = 200
) -> list[dict[str, object]]:
    query = str(query or "").strip()
    entity_type = str(entity_type or "").strip()
    actor_type = str(actor_type or "").strip()
    if database_backend() == "mongodb":
        mongo_query: dict[str, object] = {}
        if query:
            escaped = re.escape(query)
            mongo_query["$or"] = [
                {"actor_label": {"$regex": escaped, "$options": "i"}},
                {"summary": {"$regex": escaped, "$options": "i"}},
                {"action": {"$regex": escaped, "$options": "i"}},
            ]
        if entity_type:
            mongo_query["entity_type"] = entity_type
        if actor_type:
            mongo_query["actor_type"] = actor_type
        rows = get_mongo_activity_collection().find(mongo_query).sort("created_at", DESCENDING).limit(limit)
        return [normalize_activity_record(row) for row in rows]

    clauses: list[str] = []
    params: list[object] = []
    if query:
        like_query = f"%{query}%"
        clauses.append("(actor_label LIKE ? OR summary LIKE ? OR action LIKE ?)")
        params.extend([like_query, like_query, like_query])
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if actor_type:
        clauses.append("actor_type = ?")
        params.append(actor_type)
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = get_db().execute(
        f"SELECT * FROM activity_log {where_clause} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [normalize_activity_record(row) for row in rows]


def create_maintenance_ticket_record(data: dict[str, object]) -> str:
    payload = dict(data)
    payload["public_id"] = uuid.uuid4().hex[:12]
    payload["assigned_manager"] = str(payload.get("assigned_manager") or "").strip()
    payload["internal_note"] = str(payload.get("internal_note") or "").strip()
    if database_backend() == "mongodb":
        get_mongo_maintenance_collection().insert_one(payload)
        return str(payload["public_id"])

    get_db().execute(
        """
        INSERT INTO maintenance_tickets (
            public_id,
            resident_name,
            email,
            phone,
            unit_reference,
            property_title,
            issue_category,
            priority,
            description,
            image_path,
            assigned_manager,
            assigned_vendor,
            internal_note,
            status,
            created_at,
            updated_at
        ) VALUES (
            :public_id,
            :resident_name,
            :email,
            :phone,
            :unit_reference,
            :property_title,
            :issue_category,
            :priority,
            :description,
            :image_path,
            :assigned_manager,
            :assigned_vendor,
            :internal_note,
            :status,
            :created_at,
            :updated_at
        )
        """,
        payload,
    )
    get_db().commit()
    return str(payload["public_id"])


def recent_maintenance_tickets(limit: int = 8) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_maintenance_collection().find({}).sort("created_at", DESCENDING).limit(limit)
        return [normalize_maintenance_record(item) for item in cursor]

    rows = get_db().execute(
        "SELECT * FROM maintenance_tickets ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [normalize_maintenance_record(row) for row in rows]


def maintenance_stats() -> dict[str, int]:
    if database_backend() == "mongodb":
        total = get_mongo_maintenance_collection().count_documents({})
        open_count = get_mongo_maintenance_collection().count_documents({"status": {"$in": ["New", "Assigned", "In Progress"]}})
        return {"maintenance_total": total, "maintenance_open": open_count}

    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status IN ('New', 'Assigned', 'In Progress') THEN 1 ELSE 0 END) AS open_count
        FROM maintenance_tickets
        """
    ).fetchone()
    return {
        "maintenance_total": int(row["total"] or 0),
        "maintenance_open": int(row["open_count"] or 0),
    }


def fetch_maintenance_ticket(ticket_id: str) -> dict[str, object]:
    if database_backend() == "mongodb":
        row = get_mongo_maintenance_collection().find_one({"public_id": ticket_id})
        if row is None:
            abort(404)
        return normalize_maintenance_record(row)

    row = get_db().execute(
        "SELECT * FROM maintenance_tickets WHERE public_id = ?",
        (ticket_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return normalize_maintenance_record(row)


def update_maintenance_ticket(
    ticket_id: str,
    *,
    status: str,
    assigned_vendor: str,
    assigned_manager: str = "",
    internal_note: str = "",
) -> None:
    now = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_maintenance_collection().update_one(
            {"public_id": ticket_id},
            {
                "$set": {
                    "status": status,
                    "assigned_vendor": assigned_vendor,
                    "assigned_manager": assigned_manager,
                    "internal_note": internal_note,
                    "updated_at": now,
                }
            },
        )
        return

    get_db().execute(
        """
        UPDATE maintenance_tickets
        SET status = ?, assigned_vendor = ?, assigned_manager = ?, internal_note = ?, updated_at = ?
        WHERE public_id = ?
        """,
        (status, assigned_vendor, assigned_manager, internal_note, now, ticket_id),
    )
    get_db().commit()


def create_financial_record(data: dict[str, object]) -> str:
    payload = dict(data)
    payload["public_id"] = uuid.uuid4().hex[:12]
    payload["assigned_to"] = str(payload.get("assigned_to") or "").strip()
    if database_backend() == "mongodb":
        get_mongo_financial_collection().insert_one(payload)
        return str(payload["public_id"])

    get_db().execute(
        """
        INSERT INTO financial_records (
            public_id,
            resident_name,
            unit_reference,
            property_title,
            charge_type,
            amount,
            due_date,
            assigned_to,
            status,
            note,
            created_at,
            updated_at
        ) VALUES (
            :public_id,
            :resident_name,
            :unit_reference,
            :property_title,
            :charge_type,
            :amount,
            :due_date,
            :assigned_to,
            :status,
            :note,
            :created_at,
            :updated_at
        )
        """,
        payload,
    )
    get_db().commit()
    return str(payload["public_id"])


def recent_financial_records(limit: int = 8) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_financial_collection().find({}).sort([("due_date", ASCENDING), ("created_at", DESCENDING)]).limit(limit)
        return [normalize_financial_record(item) for item in cursor]

    rows = get_db().execute(
        "SELECT * FROM financial_records ORDER BY due_date ASC, created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [normalize_financial_record(row) for row in rows]


def financial_stats() -> dict[str, int]:
    if database_backend() == "mongodb":
        due_count = get_mongo_financial_collection().count_documents({"status": {"$in": ["Due", "Overdue", "Part Paid"]}})
        total_due = next(
            iter(
                get_mongo_financial_collection().aggregate(
                    [
                        {"$match": {"status": {"$in": ["Due", "Overdue", "Part Paid"]}}},
                        {"$group": {"_id": None, "amount": {"$sum": "$amount"}}},
                    ]
                )
            ),
            None,
        )
        return {
            "financial_due_count": due_count,
            "financial_due_amount": int((total_due or {}).get("amount", 0)),
        }

    row = get_db().execute(
        """
        SELECT
            SUM(CASE WHEN status IN ('Due', 'Overdue', 'Part Paid') THEN 1 ELSE 0 END) AS due_count,
            SUM(CASE WHEN status IN ('Due', 'Overdue', 'Part Paid') THEN amount ELSE 0 END) AS due_amount
        FROM financial_records
        """
    ).fetchone()
    return {
        "financial_due_count": int(row["due_count"] or 0),
        "financial_due_amount": int(row["due_amount"] or 0),
    }


def fetch_financial_record(record_id: str) -> dict[str, object]:
    if database_backend() == "mongodb":
        row = get_mongo_financial_collection().find_one({"public_id": record_id})
        if row is None:
            abort(404)
        return normalize_financial_record(row)

    row = get_db().execute(
        "SELECT * FROM financial_records WHERE public_id = ?",
        (record_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return normalize_financial_record(row)


def update_financial_record(record_id: str, *, status: str, assigned_to: str = "", note: str = "") -> None:
    now = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_financial_collection().update_one(
            {"public_id": record_id},
            {"$set": {"status": status, "assigned_to": assigned_to, "note": note, "updated_at": now}},
        )
        return

    get_db().execute(
        "UPDATE financial_records SET status = ?, assigned_to = ?, note = ?, updated_at = ? WHERE public_id = ?",
        (status, assigned_to, note, now, record_id),
    )
    get_db().commit()


def create_document_record(data: dict[str, object]) -> str:
    payload = dict(data)
    payload["public_id"] = uuid.uuid4().hex[:12]
    payload["source_kind"] = str(payload.get("source_kind") or "upload").strip() or "upload"
    payload["document_status"] = str(
        payload.get("document_status") or ("Final" if payload["source_kind"] == "generated" else "Filed")
    ).strip()
    payload["template_key"] = str(payload.get("template_key") or "").strip()
    payload["template_version"] = str(payload.get("template_version") or "").strip()
    payload["payload_json"] = (
        json.dumps(payload.get("payload_json"), ensure_ascii=False)
        if isinstance(payload.get("payload_json"), dict)
        else str(payload.get("payload_json") or "")
    )
    if database_backend() == "mongodb":
        get_mongo_document_collection().insert_one(payload)
        return str(payload["public_id"])

    get_db().execute(
        """
        INSERT INTO documents (
            public_id,
            resident_name,
            unit_reference,
            property_title,
            document_type,
            title,
            note,
            document_status,
            source_kind,
            template_key,
            template_version,
            payload_json,
            stored_filename,
            original_filename,
            mime_type,
            file_size,
            created_at,
            updated_at
        ) VALUES (
            :public_id,
            :resident_name,
            :unit_reference,
            :property_title,
            :document_type,
            :title,
            :note,
            :document_status,
            :source_kind,
            :template_key,
            :template_version,
            :payload_json,
            :stored_filename,
            :original_filename,
            :mime_type,
            :file_size,
            :created_at,
            :updated_at
        )
        """,
        payload,
    )
    get_db().commit()
    return str(payload["public_id"])


def recent_documents(limit: int = 8) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_document_collection().find({}).sort("created_at", DESCENDING).limit(limit)
        return [normalize_document_record(item) for item in cursor]

    rows = get_db().execute(
        "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [normalize_document_record(row) for row in rows]


def document_stats() -> dict[str, int]:
    if database_backend() == "mongodb":
        total = get_mongo_document_collection().count_documents({})
        return {"document_total": total}

    row = get_db().execute("SELECT COUNT(*) AS total FROM documents").fetchone()
    return {"document_total": int(row["total"] or 0)}


def fetch_document_record(document_id: str) -> dict[str, object]:
    if database_backend() == "mongodb":
        row = get_mongo_document_collection().find_one({"public_id": document_id})
        if row is None:
            abort(404)
        return normalize_document_record(row)

    row = get_db().execute(
        "SELECT * FROM documents WHERE public_id = ?",
        (document_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return normalize_document_record(row)


def delete_document_record(document_id: str) -> dict[str, object]:
    document = fetch_document_record(document_id)
    if database_backend() == "mongodb":
        get_mongo_document_collection().delete_one({"public_id": document_id})
    else:
        get_db().execute("DELETE FROM documents WHERE public_id = ?", (document_id,))
        get_db().commit()
    return document


def update_document_metadata(document_id: str, *, title: str, document_type: str, note: str) -> None:
    now = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_document_collection().update_one(
            {"public_id": document_id},
            {"$set": {"title": title, "document_type": document_type, "note": note, "updated_at": now}},
        )
        return

    get_db().execute(
        """
        UPDATE documents
        SET title = ?, document_type = ?, note = ?, updated_at = ?
        WHERE public_id = ?
        """,
        (title, document_type, note, now, document_id),
    )
    get_db().commit()


def create_enquiry_record(data: dict[str, str]) -> str:
    now = utc_now_iso()
    contact_id = str(data.get("contact_id") or "") or get_or_create_contact(
        name=data["name"], email=data.get("email", ""), phone=data.get("phone", ""),
        whatsapp=data.get("whatsapp", ""),
    )
    payload = {
        "public_id": uuid.uuid4().hex[:12],
        "listing_id": data["listing_id"],
        "listing_title": data["listing_title"],
        "status": canonical_lead_stage(data.get("status") or "NEW"),
        "contact_id": contact_id,
        "source": str(data.get("source") or "WEBSITE").upper(),
        "campaign_id": str(data.get("campaign_id") or ""),
        "assigned_staff_id": str(data.get("assigned_staff_id") or ""),
        "assigned_to": "",
        "estimated_value": int(data.get("estimated_value") or 0),
        "whatsapp": str(data.get("whatsapp") or ""),
        "partner_id": str(data.get("partner_id") or ""),
        "referral_id": str(data.get("referral_id") or ""),
        "last_contacted_at": "",
        "internal_note": "",
        "follow_up_on": "",
        "name": data["name"],
        "email": data["email"],
        "phone": data["phone"],
        "preferred_contact": data["preferred_contact"],
        "message": data["message"],
        "source_path": data["source_path"],
        "admin_email_recipient": "",
        "admin_email_sent_at": "",
        "admin_email_last_error": "",
        "receipt_email_recipient": "",
        "receipt_email_sent_at": "",
        "receipt_email_last_error": "",
        "created_at": now,
        "updated_at": now,
    }

    if database_backend() == "mongodb":
        get_mongo_enquiries_collection().insert_one(payload)
    else:
        get_db().execute(
            """
            INSERT INTO enquiries (
                public_id,
                listing_id,
                listing_title,
                status,
                contact_id,
                source,
                campaign_id,
                assigned_staff_id,
                assigned_to,
                estimated_value,
                whatsapp,
                partner_id,
                referral_id,
                last_contacted_at,
                internal_note,
                follow_up_on,
                name,
                email,
                phone,
                preferred_contact,
                message,
                source_path,
                admin_email_recipient,
                admin_email_sent_at,
                admin_email_last_error,
                receipt_email_recipient,
                receipt_email_sent_at,
                receipt_email_last_error,
                created_at,
                updated_at
            ) VALUES (
                :public_id,
                :listing_id,
                :listing_title,
                :status,
                :contact_id,
                :source,
                :campaign_id,
                :assigned_staff_id,
                :assigned_to,
                :estimated_value,
                :whatsapp,
                :partner_id,
                :referral_id,
                :last_contacted_at,
                :internal_note,
                :follow_up_on,
                :name,
                :email,
                :phone,
                :preferred_contact,
                :message,
                :source_path,
                :admin_email_recipient,
                :admin_email_sent_at,
                :admin_email_last_error,
                :receipt_email_recipient,
                :receipt_email_sent_at,
                :receipt_email_last_error,
                :created_at,
                :updated_at
            )
            """,
            payload,
        )
        get_db().commit()

    return payload["public_id"]


def dashboard_enquiries(limit: int = 8) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_enquiries_collection().find({}).sort("created_at", DESCENDING).limit(limit)
        return [normalize_enquiry_record(item) for item in cursor]

    rows = get_db().execute(
        "SELECT * FROM enquiries ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [normalize_enquiry_record(row) for row in rows]


def enquiry_stats() -> dict[str, int]:
    if database_backend() == "mongodb":
        total = get_mongo_enquiries_collection().count_documents({})
        new_count = get_mongo_enquiries_collection().count_documents({"status": "NEW"})
        return {"enquiry_total": total, "new_count": new_count}

    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'NEW' THEN 1 ELSE 0 END) AS new_count
        FROM enquiries
        """
    ).fetchone()
    return {"enquiry_total": int(row["total"] or 0), "new_count": int(row["new_count"] or 0)}


def update_enquiry_record(
    enquiry_id: str,
    *,
    status: str,
    assigned_to: str = "",
    assigned_staff_id: str = "",
    source: str = "WEBSITE",
    campaign_id: str = "",
    estimated_value: int = 0,
    internal_note: str = "",
    follow_up_on: str = "",
) -> None:
    now = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_enquiries_collection().update_one(
            {"public_id": enquiry_id},
            {
                "$set": {
                    "status": status,
                    "assigned_to": assigned_to,
                    "assigned_staff_id": assigned_staff_id,
                    "source": source,
                    "campaign_id": campaign_id,
                    "estimated_value": estimated_value,
                    "internal_note": internal_note,
                    "follow_up_on": follow_up_on,
                    "updated_at": now,
                }
            },
        )
        return

    get_db().execute(
        "UPDATE enquiries SET status = ?, assigned_to = ?, assigned_staff_id = ?, source = ?, campaign_id = ?, estimated_value = ?, internal_note = ?, follow_up_on = ?, updated_at = ? WHERE public_id = ?",
        (status, assigned_to, assigned_staff_id, source, campaign_id, estimated_value, internal_note, follow_up_on, now, enquiry_id),
    )
    get_db().commit()


def update_enquiry_delivery_status(
    enquiry_id: str,
    **updates: str,
) -> None:
    payload = {key: str(value).strip() for key, value in updates.items()}
    if not payload:
        return

    payload["updated_at"] = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_enquiries_collection().update_one(
            {"public_id": enquiry_id},
            {"$set": payload},
        )
        return

    assignments = ", ".join(f"{field} = ?" for field in payload)
    values = list(payload.values())
    values.append(enquiry_id)
    get_db().execute(
        f"UPDATE enquiries SET {assignments} WHERE public_id = ?",
        values,
    )
    get_db().commit()


def should_track_listing_view(listing_id: str) -> bool:
    seen = session.get("viewed_listings", {})
    now = time.time()
    last_seen = float(seen.get(listing_id, 0))
    if now - last_seen < VIEW_DEDUP_WINDOW_SECONDS:
        return False

    seen[listing_id] = now
    if len(seen) > 60:
        ordered = sorted(seen.items(), key=lambda item: item[1], reverse=True)[:30]
        seen = {key: stamp for key, stamp in ordered}
    session["viewed_listings"] = seen
    session.modified = True
    return True


def increment_listing_view(listing_id: str) -> None:
    now = utc_now_iso()
    if database_backend() == "mongodb":
        get_mongo_collection().update_one(
            {"public_id": listing_id},
            {"$inc": {"view_count": 1}, "$set": {"last_viewed_at": now}},
        )
        return

    get_db().execute(
        "UPDATE listings SET view_count = COALESCE(view_count, 0) + 1, last_viewed_at = ? WHERE id = ?",
        (now, sqlite_listing_id(listing_id)),
    )
    get_db().commit()


def fetch_listing(listing_id: str, include_unpublished: bool = False) -> dict[str, object]:
    if database_backend() == "mongodb":
        query: dict[str, object] = {"public_id": listing_id}
        if not include_unpublished:
            query["published"] = 1
        row = get_mongo_collection().find_one(query)
        if row is None:
            abort(404)
        return normalize_listing_record(row)

    db = get_db()
    sql = "SELECT * FROM listings WHERE id = ?"
    params: list[object] = [sqlite_listing_id(listing_id)]
    if not include_unpublished:
        sql += " AND published = 1"
    row = db.execute(sql, params).fetchone()
    if row is None:
        abort(404)
    return normalize_listing_record(row)


def query_public_listings(filters: dict[str, str]) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        query: dict[str, object] = {"published": 1}
        if filters["status"]:
            query["status"] = filters["status"]
        if filters.get("availability"):
            query["availability"] = filters["availability"]
        if filters["district"]:
            query["district"] = filters["district"]
        if filters["property_type"]:
            query["property_type"] = filters["property_type"]
        if filters.get("verified_only"):
            query["verified_property"] = 1
        price_query: dict[str, int] = {}
        if filters.get("min_price"):
            price_query["$gte"] = int(filters["min_price"])
        if filters.get("max_price"):
            price_query["$lte"] = int(filters["max_price"])
        if price_query:
            query["price"] = price_query
        if filters.get("min_bedrooms"):
            query["bedrooms"] = {"$gte": int(filters["min_bedrooms"])}
        for key, _label in DISCOVERY_FEATURE_FIELDS:
            if filters.get(key):
                query[key] = 1
        if filters["q"]:
            pattern = re.escape(filters["q"])
            query["$or"] = [
                {"title": {"$regex": pattern, "$options": "i"}},
                {"summary": {"$regex": pattern, "$options": "i"}},
                {"district": {"$regex": pattern, "$options": "i"}},
                {"address": {"$regex": pattern, "$options": "i"}},
            ]
        cursor = get_mongo_collection().find(query).sort(
            PUBLIC_LISTING_SORT_DEFINITIONS.get(filters.get("sort", "recommended"), LISTING_SORT)
        )
        return [normalize_listing_record(document) for document in cursor]

    db = get_db()
    sql = "SELECT * FROM listings WHERE published = 1"
    params: list[object] = []

    if filters["status"]:
        sql += " AND status = ?"
        params.append(filters["status"])
    if filters.get("availability"):
        sql += " AND availability = ?"
        params.append(filters["availability"])
    if filters["district"]:
        sql += " AND district = ?"
        params.append(filters["district"])
    if filters["property_type"]:
        sql += " AND property_type = ?"
        params.append(filters["property_type"])
    if filters.get("verified_only"):
        sql += " AND verified_property = 1"
    if filters.get("min_price"):
        sql += " AND price >= ?"
        params.append(int(filters["min_price"]))
    if filters.get("max_price"):
        sql += " AND price <= ?"
        params.append(int(filters["max_price"]))
    if filters.get("min_bedrooms"):
        sql += " AND bedrooms >= ?"
        params.append(int(filters["min_bedrooms"]))
    for key, _label in DISCOVERY_FEATURE_FIELDS:
        if filters.get(key):
            sql += f" AND {key} = 1"
    if filters["q"]:
        pattern = f"%{filters['q']}%"
        sql += " AND (title LIKE ? OR summary LIKE ? OR district LIKE ? OR address LIKE ?)"
        params.extend([pattern, pattern, pattern, pattern])

    sql += f" ORDER BY {PUBLIC_LISTING_SORT_SQL.get(filters.get('sort', 'recommended'), PUBLIC_LISTING_SORT_SQL['recommended'])}"
    rows = db.execute(sql, params).fetchall()
    return [normalize_listing_record(row) for row in rows]


def home_featured_listings(limit: int = 3) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = (
            get_mongo_collection()
            .find({"published": 1, "availability": {"$nin": list(COMPLETED_AVAILABILITY_OPTIONS)}})
            .sort(LISTING_SORT)
            .limit(limit)
        )
        return [normalize_listing_record(document) for document in cursor]

    rows = get_db().execute(
        """
        SELECT * FROM listings
        WHERE published = 1 AND availability NOT IN ('Sold', 'Rented', 'Leased')
        ORDER BY featured DESC, updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [normalize_listing_record(row) for row in rows]


def home_completed_listings(limit: int = 3) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = (
            get_mongo_collection()
            .find({"published": 1, "availability": {"$in": list(COMPLETED_AVAILABILITY_OPTIONS)}})
            .sort([("updated_at", DESCENDING), ("created_at", DESCENDING)])
            .limit(limit)
        )
        return [normalize_listing_record(document) for document in cursor]

    rows = get_db().execute(
        """
        SELECT * FROM listings
        WHERE published = 1 AND availability IN ('Sold', 'Rented', 'Leased')
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [normalize_listing_record(row) for row in rows]


def public_stats(include_district_count: bool = True) -> dict[str, int]:
    if database_backend() == "mongodb":
        result = next(
            iter(
                get_mongo_collection().aggregate(
                    [
                        {"$match": {"published": 1}},
                        {
                            "$group": {
                                "_id": None,
                                "total": {"$sum": 1},
                                "sale_count": {
                                    "$sum": {"$cond": [{"$eq": ["$status", "For Sale"]}, 1, 0]}
                                },
                                "rent_count": {
                                    "$sum": {"$cond": [{"$eq": ["$status", "For Rent"]}, 1, 0]}
                                },
                                "lease_count": {
                                    "$sum": {"$cond": [{"$eq": ["$status", "For Lease"]}, 1, 0]}
                                },
                                "verified_count": {
                                    "$sum": {
                                        "$cond": [
                                            {
                                                "$or": [
                                                    {"$eq": ["$verified_property", 1]},
                                                    {"$eq": ["$verified_landlord", 1]},
                                                ]
                                            },
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "districts": {"$addToSet": "$district"},
                            }
                        },
                    ]
                )
            ),
            None,
        )
        if result is None:
            return {
                "total": 0,
                "sale_count": 0,
                "rent_count": 0,
                "lease_count": 0,
                "verified_count": 0,
                "district_count": 0,
            }
        return {
            "total": int(result.get("total", 0)),
            "sale_count": int(result.get("sale_count", 0)),
            "rent_count": int(result.get("rent_count", 0)),
            "lease_count": int(result.get("lease_count", 0)),
            "verified_count": int(result.get("verified_count", 0)),
            "district_count": len(result.get("districts", [])) if include_district_count else 0,
        }

    query = """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'For Sale' THEN 1 ELSE 0 END) AS sale_count,
            SUM(CASE WHEN status = 'For Rent' THEN 1 ELSE 0 END) AS rent_count,
            SUM(CASE WHEN status = 'For Lease' THEN 1 ELSE 0 END) AS lease_count,
            SUM(CASE WHEN verified_property = 1 OR verified_landlord = 1 THEN 1 ELSE 0 END) AS verified_count
        FROM listings
        WHERE published = 1
    """
    row = get_db().execute(query).fetchone()
    stats = {
        "total": int(row["total"] or 0),
        "sale_count": int(row["sale_count"] or 0),
        "rent_count": int(row["rent_count"] or 0),
        "lease_count": int(row["lease_count"] or 0),
        "verified_count": int(row["verified_count"] or 0),
        "district_count": 0,
    }
    if include_district_count:
        district_row = get_db().execute(
            "SELECT COUNT(DISTINCT district) AS district_count FROM listings WHERE published = 1"
        ).fetchone()
        stats["district_count"] = int(district_row["district_count"] or 0)
    return stats


def top_districts(limit: int = 4) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_collection().aggregate(
            [
                {"$match": {"published": 1}},
                {"$group": {"_id": "$district", "total": {"$sum": 1}}},
                {"$sort": {"total": -1, "_id": 1}},
                {"$limit": limit},
            ]
        )
        return [{"district": item["_id"], "total": int(item["total"])} for item in cursor]

    rows = get_db().execute(
        """
        SELECT district, COUNT(*) AS total
        FROM listings
        WHERE published = 1
        GROUP BY district
        ORDER BY total DESC, district ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [{"district": row["district"], "total": int(row["total"])} for row in rows]


def distinct_public_values(field_name: str) -> list[dict[str, str]]:
    allowed_fields = {"district", "property_type", "availability"}
    if field_name not in allowed_fields:
        raise ValueError(f"Unsupported public distinct field: {field_name}")

    if database_backend() == "mongodb":
        values = sorted(
            [value for value in get_mongo_collection().distinct(field_name, {"published": 1}) if value]
        )
        return [{field_name: value} for value in values]

    rows = get_db().execute(
        f"SELECT DISTINCT {field_name} FROM listings WHERE published = 1 ORDER BY {field_name} ASC"
    ).fetchall()
    return [{field_name: row[field_name]} for row in rows]


def dashboard_listing_filter_defaults() -> dict[str, str]:
    return {
        "q": "",
        "status": "",
        "availability": "",
        "district": "",
        "property_type": "",
        "publication": "",
        "sort": "updated_desc",
        "featured_only": "",
        "verified_property_only": "",
        "verified_landlord_only": "",
    }


def dashboard_listing_filters_from_request() -> dict[str, str]:
    filters = dashboard_listing_filter_defaults()
    filters.update(
        {
            "q": request.args.get("q", "").strip(),
            "status": request.args.get("status", "").strip(),
            "availability": request.args.get("availability", "").strip(),
            "district": request.args.get("district", "").strip(),
            "property_type": request.args.get("property_type", "").strip(),
            "publication": request.args.get("publication", "").strip(),
            "sort": request.args.get("sort", filters["sort"]).strip(),
            "featured_only": "1" if request.args.get("featured_only") else "",
            "verified_property_only": "1" if request.args.get("verified_property_only") else "",
            "verified_landlord_only": "1" if request.args.get("verified_landlord_only") else "",
        }
    )

    if filters["status"] not in STATUS_OPTIONS:
        filters["status"] = ""
    if filters["availability"] not in AVAILABILITY_OPTIONS:
        filters["availability"] = ""
    if filters["publication"] not in {"", "published", "draft"}:
        filters["publication"] = ""
    if filters["sort"] not in DASHBOARD_SORT_DEFINITIONS:
        filters["sort"] = "updated_desc"
    return filters


def distinct_dashboard_values(field_name: str) -> list[dict[str, str]]:
    allowed_fields = {"district", "property_type", "availability"}
    if field_name not in allowed_fields:
        raise ValueError(f"Unsupported dashboard distinct field: {field_name}")

    if database_backend() == "mongodb":
        values = sorted([value for value in get_mongo_collection().distinct(field_name) if value])
        return [{field_name: value} for value in values]

    rows = get_db().execute(
        f"SELECT DISTINCT {field_name} FROM listings WHERE {field_name} IS NOT NULL AND TRIM({field_name}) != '' ORDER BY {field_name} ASC"
    ).fetchall()
    return [{field_name: row[field_name]} for row in rows]


def dashboard_active_filter_labels(filters: Mapping[str, str]) -> list[str]:
    labels: list[str] = []
    if filters.get("q"):
        labels.append(f'Search: "{filters["q"]}"')
    if filters.get("status"):
        labels.append(str(filters["status"]))
    if filters.get("availability"):
        labels.append(str(filters["availability"]))
    if filters.get("district"):
        labels.append(str(filters["district"]))
    if filters.get("property_type"):
        labels.append(str(filters["property_type"]))
    if filters.get("publication") == "published":
        labels.append("Published only")
    elif filters.get("publication") == "draft":
        labels.append("Drafts only")
    if filters.get("featured_only"):
        labels.append("Featured only")
    if filters.get("verified_property_only"):
        labels.append("Property vetted")
    if filters.get("verified_landlord_only"):
        labels.append("Landlord vetted")
    return labels


def related_listings(listing: Mapping[str, object], limit: int = 3) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = (
            get_mongo_collection()
            .find(
                {
                    "published": 1,
                    "public_id": {"$ne": listing["id"]},
                    "district": listing["district"],
                    "availability": {"$nin": list(COMPLETED_AVAILABILITY_OPTIONS)},
                }
            )
            .sort(LISTING_SORT)
            .limit(limit)
        )
        return [normalize_listing_record(document) for document in cursor]

    rows = get_db().execute(
        """
        SELECT * FROM listings
        WHERE published = 1 AND id != ? AND district = ?
          AND availability NOT IN ('Sold', 'Rented', 'Leased')
        ORDER BY featured DESC, updated_at DESC
        LIMIT ?
        """,
        (sqlite_listing_id(str(listing["id"])), listing["district"], limit),
    ).fetchall()
    return [normalize_listing_record(row) for row in rows]


def dashboard_listings(filters: Mapping[str, str] | None = None) -> list[dict[str, object]]:
    active_filters = dashboard_listing_filter_defaults()
    if filters:
        active_filters.update({key: str(value) for key, value in filters.items()})

    if database_backend() == "mongodb":
        query: dict[str, object] = {}
        if active_filters["status"]:
            query["status"] = active_filters["status"]
        if active_filters["availability"]:
            query["availability"] = active_filters["availability"]
        if active_filters["district"]:
            query["district"] = active_filters["district"]
        if active_filters["property_type"]:
            query["property_type"] = active_filters["property_type"]
        if active_filters["publication"] == "published":
            query["published"] = 1
        elif active_filters["publication"] == "draft":
            query["published"] = 0
        if active_filters["featured_only"]:
            query["featured"] = 1
        if active_filters["verified_property_only"]:
            query["verified_property"] = 1
        if active_filters["verified_landlord_only"]:
            query["verified_landlord"] = 1
        if active_filters["q"]:
            pattern = re.escape(active_filters["q"])
            query["$or"] = [
                {"title": {"$regex": pattern, "$options": "i"}},
                {"summary": {"$regex": pattern, "$options": "i"}},
                {"district": {"$regex": pattern, "$options": "i"}},
                {"address": {"$regex": pattern, "$options": "i"}},
            ]
        cursor = get_mongo_collection().find(query).sort(
            DASHBOARD_SORT_DEFINITIONS.get(active_filters["sort"], DASHBOARD_SORT)
        )
        return [normalize_listing_record(document) for document in cursor]

    sql = "SELECT * FROM listings WHERE 1 = 1"
    params: list[object] = []

    if active_filters["status"]:
        sql += " AND status = ?"
        params.append(active_filters["status"])
    if active_filters["availability"]:
        sql += " AND availability = ?"
        params.append(active_filters["availability"])
    if active_filters["district"]:
        sql += " AND district = ?"
        params.append(active_filters["district"])
    if active_filters["property_type"]:
        sql += " AND property_type = ?"
        params.append(active_filters["property_type"])
    if active_filters["publication"] == "published":
        sql += " AND published = 1"
    elif active_filters["publication"] == "draft":
        sql += " AND published = 0"
    if active_filters["featured_only"]:
        sql += " AND featured = 1"
    if active_filters["verified_property_only"]:
        sql += " AND verified_property = 1"
    if active_filters["verified_landlord_only"]:
        sql += " AND verified_landlord = 1"
    if active_filters["q"]:
        pattern = f"%{active_filters['q']}%"
        sql += " AND (title LIKE ? OR summary LIKE ? OR district LIKE ? OR address LIKE ?)"
        params.extend([pattern, pattern, pattern, pattern])

    sql += f" ORDER BY {DASHBOARD_SORT_SQL.get(active_filters['sort'], DASHBOARD_SORT_SQL['updated_desc'])}"
    rows = get_db().execute(sql, params).fetchall()
    return [normalize_listing_record(row) for row in rows]


def dashboard_stats() -> dict[str, int]:
    if database_backend() == "mongodb":
        result = next(
            iter(
                get_mongo_collection().aggregate(
                    [
                        {
                            "$group": {
                                "_id": None,
                                "total": {"$sum": 1},
                                "published_count": {
                                    "$sum": {"$cond": [{"$eq": ["$published", 1]}, 1, 0]}
                                },
                                "featured_count": {
                                    "$sum": {"$cond": [{"$eq": ["$featured", 1]}, 1, 0]}
                                },
                                "total_views": {"$sum": {"$ifNull": ["$view_count", 0]}},
                            }
                        }
                    ]
                )
            ),
            None,
        )
        if result is None:
            stats = {"total": 0, "published_count": 0, "featured_count": 0, "total_views": 0}
        else:
            stats = {
                "total": int(result.get("total", 0)),
                "published_count": int(result.get("published_count", 0)),
                "featured_count": int(result.get("featured_count", 0)),
                "total_views": int(result.get("total_views", 0)),
            }
        stats.update(enquiry_stats())
        stats.update(maintenance_stats())
        stats.update(financial_stats())
        stats.update(document_stats())
        return stats

    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN published = 1 THEN 1 ELSE 0 END) AS published_count,
            SUM(CASE WHEN featured = 1 THEN 1 ELSE 0 END) AS featured_count,
            SUM(COALESCE(view_count, 0)) AS total_views
        FROM listings
        """
    ).fetchone()
    stats = {
        "total": int(row["total"] or 0),
        "published_count": int(row["published_count"] or 0),
        "featured_count": int(row["featured_count"] or 0),
        "total_views": int(row["total_views"] or 0),
    }
    stats.update(enquiry_stats())
    stats.update(maintenance_stats())
    stats.update(financial_stats())
    stats.update(document_stats())
    return stats


def all_enquiries() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_enquiries_collection().find({}).sort("created_at", DESCENDING)
        return [normalize_enquiry_record(item) for item in cursor]

    rows = get_db().execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall()
    return [normalize_enquiry_record(row) for row in rows]


def active_staff_with_permission(permission: str) -> list[dict[str, object]]:
    return [
        staff for staff in all_staff_users()
        if staff.get("status") == "ACTIVE" and role_has_permission(str(staff.get("role") or ""), permission)
    ]


def find_open_lead(contact_id: str, listing_id: str) -> dict[str, object] | None:
    if database_backend() == "mongodb":
        row = get_mongo_enquiries_collection().find_one(
            {"contact_id": contact_id, "listing_id": listing_id, "status": {"$nin": list(CLOSED_LEAD_STAGES)}},
            sort=[("created_at", DESCENDING)],
        )
    else:
        placeholders = ", ".join("?" for _ in CLOSED_LEAD_STAGES)
        row = get_db().execute(
            f"""SELECT * FROM enquiries
                WHERE contact_id = ? AND listing_id = ? AND status NOT IN ({placeholders})
                ORDER BY created_at DESC LIMIT 1""",
            (contact_id, listing_id, *sorted(CLOSED_LEAD_STAGES)),
        ).fetchone()
    return normalize_enquiry_record(row) if row is not None else None


def create_inspection_record(data: Mapping[str, object]) -> str:
    now = utc_now_iso()
    payload = {
        "public_id": uuid.uuid4().hex[:12], "lead_id": str(data["lead_id"]),
        "contact_id": str(data.get("contact_id") or ""), "listing_id": str(data.get("listing_id") or ""),
        "listing_title": str(data.get("listing_title") or ""), "name": str(data["name"]),
        "email": str(data.get("email") or ""), "phone": str(data.get("phone") or ""),
        "requested_date": str(data["requested_date"]), "requested_time": str(data["requested_time"]),
        "assigned_staff_id": "", "assigned_to": "", "notes": str(data.get("notes") or ""),
        "internal_note": "", "status": "REQUESTED", "partner_id": str(data.get("partner_id") or ""),
        "referral_id": str(data.get("referral_id") or ""), "created_at": now, "updated_at": now,
    }
    if database_backend() == "mongodb":
        get_mongo_inspections_collection().insert_one(payload)
    else:
        get_db().execute(
            """INSERT INTO inspections (
                public_id, lead_id, contact_id, listing_id, listing_title, name, email, phone,
                requested_date, requested_time, assigned_staff_id, assigned_to, notes, internal_note,
                status, partner_id, referral_id, created_at, updated_at
            ) VALUES (
                :public_id, :lead_id, :contact_id, :listing_id, :listing_title, :name, :email, :phone,
                :requested_date, :requested_time, :assigned_staff_id, :assigned_to, :notes, :internal_note,
                :status, :partner_id, :referral_id, :created_at, :updated_at
            )""",
            payload,
        )
        get_db().commit()
    return str(payload["public_id"])


def fetch_inspection(inspection_id: str) -> dict[str, object]:
    if database_backend() == "mongodb":
        row = get_mongo_inspections_collection().find_one({"public_id": inspection_id})
    else:
        row = get_db().execute("SELECT * FROM inspections WHERE public_id = ?", (inspection_id,)).fetchone()
    if row is None:
        abort(404)
    return normalize_inspection_record(row)


def all_inspections() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_inspections_collection().find({}).sort(
            [("requested_date", ASCENDING), ("requested_time", ASCENDING)]
        )
    else:
        rows = get_db().execute(
            "SELECT * FROM inspections ORDER BY requested_date ASC, requested_time ASC"
        ).fetchall()
    return [normalize_inspection_record(row) for row in rows]


def inspections_for_lead(lead_id: str) -> list[dict[str, object]]:
    return [inspection for inspection in all_inspections() if inspection.get("lead_id") == lead_id]


def update_inspection_record(
    inspection_id: str, *, status: str, requested_date: str, requested_time: str,
    assigned_staff_id: str, assigned_to: str, internal_note: str,
) -> None:
    payload = {
        "status": status, "requested_date": requested_date, "requested_time": requested_time,
        "assigned_staff_id": assigned_staff_id, "assigned_to": assigned_to,
        "internal_note": internal_note, "updated_at": utc_now_iso(),
    }
    if database_backend() == "mongodb":
        get_mongo_inspections_collection().update_one({"public_id": inspection_id}, {"$set": payload})
    else:
        get_db().execute(
            """UPDATE inspections SET status = :status, requested_date = :requested_date,
               requested_time = :requested_time, assigned_staff_id = :assigned_staff_id,
               assigned_to = :assigned_to, internal_note = :internal_note, updated_at = :updated_at
               WHERE public_id = :inspection_id""",
            {**payload, "inspection_id": inspection_id},
        )
        get_db().commit()


def advance_lead_for_inspection(lead_id: str, inspection_status: str) -> None:
    lead = fetch_enquiry(lead_id)
    next_stage = advanced_lead_stage(lead.get("status"), inspection_status)
    if next_stage == lead.get("status"):
        return
    update_enquiry_record(
        lead_id, status=next_stage, assigned_to=str(lead.get("assigned_to") or ""),
        assigned_staff_id=str(lead.get("assigned_staff_id") or ""), source=str(lead.get("source") or "WEBSITE"),
        estimated_value=int(lead.get("estimated_value") or 0), internal_note=str(lead.get("internal_note") or ""),
        follow_up_on=str(lead.get("follow_up_on") or ""),
    )
    create_activity_record(
        entity_type="enquiry", entity_id=lead_id, action="stage_advanced",
        summary=f"Lead advanced to {lead_stage_label(next_stage).lower()} from its inspection status.",
        metadata={"inspection_status": inspection_status, "status": next_stage},
    )


def all_maintenance_tickets() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_maintenance_collection().find({}).sort("created_at", DESCENDING)
        return [normalize_maintenance_record(item) for item in cursor]

    rows = get_db().execute("SELECT * FROM maintenance_tickets ORDER BY created_at DESC").fetchall()
    return [normalize_maintenance_record(row) for row in rows]


def all_financial_records() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_financial_collection().find({}).sort([("due_date", ASCENDING), ("created_at", DESCENDING)])
        return [normalize_financial_record(item) for item in cursor]

    rows = get_db().execute(
        "SELECT * FROM financial_records ORDER BY due_date ASC, created_at DESC"
    ).fetchall()
    return [normalize_financial_record(row) for row in rows]


def all_documents() -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_document_collection().find({}).sort("created_at", DESCENDING)
        return [normalize_document_record(item) for item in cursor]

    rows = get_db().execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [normalize_document_record(row) for row in rows]


def record_matches_query(query: str, *values: object) -> bool:
    needle = (query or "").strip().lower()
    if not needle:
        return True
    return any(needle in str(value or "").lower() for value in values)


def distinct_record_values(records: list[Mapping[str, object]], field_name: str) -> list[str]:
    return sorted({str(record.get(field_name) or "").strip() for record in records if str(record.get(field_name) or "").strip()})


def find_listing_optional(listing_id: str) -> dict[str, object] | None:
    if not listing_id:
        return None

    if database_backend() == "mongodb":
        row = get_mongo_collection().find_one({"public_id": listing_id})
        return normalize_listing_record(row) if row else None

    try:
        numeric_id = int(listing_id)
    except (TypeError, ValueError):
        return None

    row = get_db().execute("SELECT * FROM listings WHERE id = ?", (numeric_id,)).fetchone()
    return normalize_listing_record(row) if row else None


def resolve_related_listing(
    *, listing_id: str = "", listing_title: str = "", property_title: str = ""
) -> dict[str, object] | None:
    related = find_listing_optional(str(listing_id or "").strip())
    if related is not None:
        return related

    title_candidates = [
        str(value or "").strip().lower()
        for value in (listing_title, property_title)
        if str(value or "").strip()
    ]
    if not title_candidates:
        return None

    for listing in dashboard_listings():
        listing_title_value = str(listing.get("title") or "").strip().lower()
        if listing_title_value and listing_title_value in title_candidates:
            return listing
    return None


def attach_related_listing_links(record: Mapping[str, object]) -> dict[str, object]:
    data = dict(record)
    related = resolve_related_listing(
        listing_id=str(data.get("listing_id") or "").strip(),
        listing_title=str(data.get("listing_title") or "").strip(),
        property_title=str(data.get("property_title") or "").strip(),
    )
    data["related_listing_id"] = str(related.get("id") or "") if related else ""
    data["related_listing_edit_url"] = url_for("admin_listings", q=str(related["title"])) if related else ""
    data["related_listing_public_url"] = (
        url_for("property_detail", listing_id=str(related["id"])) if related and related.get("published") else ""
    )
    return data


def annotate_records_with_listing_links(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [attach_related_listing_links(record) for record in records]


def admin_listing_filters_from_request() -> dict[str, str]:
    filters = dashboard_listing_filters_from_request()
    filters["view"] = request.args.get("view", "all").strip().lower() or "all"
    allowed_views = {value for value, _label in LISTING_SAVED_VIEWS}
    if filters["view"] not in allowed_views:
        filters["view"] = "all"

    view = filters["view"]
    if view == "drafts":
        filters["publication"] = "draft"
    elif view == "published":
        filters["publication"] = "published"
    elif view == "featured":
        filters["featured_only"] = "1"
    elif view == "under_offer":
        filters["availability"] = "Under Offer"
    elif view == "off_market":
        filters["availability"] = "Off Market"
    elif view == "most_viewed":
        filters["sort"] = "views_desc"
    elif view == "verified":
        filters["verified_property_only"] = "1"
    return filters


def listing_saved_view_label(view_key: str) -> str:
    return next((label for value, label in LISTING_SAVED_VIEWS if value == view_key), "All inventory")


def apply_listing_bulk_action(listing_ids: list[str], action: str) -> int:
    handled = 0
    unique_ids = [listing_id for listing_id in dict.fromkeys(listing_ids) if listing_id]
    for listing_id in unique_ids:
        listing = fetch_listing(listing_id, include_unpublished=True)
        payload = row_to_form_data(listing)

        if action == "publish":
            payload["published"] = 1
        elif action == "unpublish":
            payload["published"] = 0
        elif action == "feature":
            payload["featured"] = 1
        elif action == "unfeature":
            payload["featured"] = 0
        elif action == "availability_available":
            payload["availability"] = "Available"
        elif action == "availability_under_offer":
            payload["availability"] = "Under Offer"
        elif action == "availability_off_market":
            payload["availability"] = "Off Market"
        else:
            continue

        payload["updated_at"] = utc_now_iso()
        update_listing_record(listing_id, payload)
        create_activity_record(
            entity_type="listing",
            entity_id=str(listing["id"]),
            action="bulk_updated",
            summary=f"Bulk action on listing: {listing['title']} ({action.replace('_', ' ')}).",
            actor_label="Admin",
        )
        handled += 1
    return handled


def enquiry_filter_defaults() -> dict[str, str]:
    return {"q": "", "status": "", "source": "", "assigned_to": "", "sort": "newest"}


def enquiry_filters_from_request() -> dict[str, str]:
    filters = enquiry_filter_defaults()
    filters.update(
        {
            "q": request.args.get("q", "").strip(),
            "status": request.args.get("status", "").strip(),
            "source": request.args.get("source", "").strip().upper(),
            "assigned_to": request.args.get("assigned_to", "").strip(),
            "sort": request.args.get("sort", "newest").strip(),
        }
    )
    if filters["status"] not in ENQUIRY_STATUS_OPTIONS:
        filters["status"] = ""
    if filters["source"] not in LEAD_SOURCES:
        filters["source"] = ""
    if filters["sort"] not in {value for value, _label in ENQUIRY_SORT_OPTIONS}:
        filters["sort"] = "newest"
    return filters


def query_admin_enquiries(filters: Mapping[str, str]) -> list[dict[str, object]]:
    records = all_enquiries()
    filtered = [
        record
        for record in records
        if record_matches_query(
            filters.get("q", ""),
            record.get("name"),
            record.get("email"),
            record.get("phone"),
            record.get("message"),
            record.get("listing_title"),
            record.get("internal_note"),
        )
        and (not filters.get("status") or record.get("status") == filters.get("status"))
        and (not filters.get("source") or record.get("source") == filters.get("source"))
        and (
            not filters.get("assigned_to")
            or str(record.get("assigned_to") or "").strip().lower() == filters.get("assigned_to", "").strip().lower()
        )
    ]

    if filters.get("sort") == "oldest":
        filtered.sort(key=lambda record: str(record.get("created_at") or ""))
    elif filters.get("sort") == "follow_up":
        filtered.sort(
            key=lambda record: (
                1 if not str(record.get("follow_up_on") or "").strip() else 0,
                str(record.get("follow_up_on") or ""),
                str(record.get("created_at") or ""),
            )
        )
    elif filters.get("sort") == "status":
        order = {value: index for index, value in enumerate(ENQUIRY_STATUS_OPTIONS)}
        filtered.sort(
            key=lambda record: (
                order.get(str(record.get("status") or ""), len(order)),
                str(record.get("created_at") or ""),
            )
        )
    else:
        filtered.sort(key=lambda record: str(record.get("created_at") or ""), reverse=True)

    return annotate_records_with_listing_links(filtered)


def maintenance_filter_defaults() -> dict[str, str]:
    return {"q": "", "status": "", "priority": "", "assigned_manager": "", "sort": "newest"}


def maintenance_filters_from_request() -> dict[str, str]:
    filters = maintenance_filter_defaults()
    filters.update(
        {
            "q": request.args.get("q", "").strip(),
            "status": request.args.get("status", "").strip(),
            "priority": request.args.get("priority", "").strip(),
            "assigned_manager": request.args.get("assigned_manager", "").strip(),
            "sort": request.args.get("sort", "newest").strip(),
        }
    )
    if filters["status"] not in MAINTENANCE_STATUS_OPTIONS:
        filters["status"] = ""
    if filters["priority"] not in MAINTENANCE_PRIORITY_OPTIONS:
        filters["priority"] = ""
    if filters["sort"] not in {value for value, _label in MAINTENANCE_SORT_OPTIONS}:
        filters["sort"] = "newest"
    return filters


def query_admin_maintenance(filters: Mapping[str, str]) -> list[dict[str, object]]:
    records = all_maintenance_tickets()
    filtered = [
        record
        for record in records
        if record_matches_query(
            filters.get("q", ""),
            record.get("resident_name"),
            record.get("unit_reference"),
            record.get("property_title"),
            record.get("description"),
            record.get("assigned_vendor"),
            record.get("internal_note"),
        )
        and (not filters.get("status") or record.get("status") == filters.get("status"))
        and (not filters.get("priority") or record.get("priority") == filters.get("priority"))
        and (
            not filters.get("assigned_manager")
            or str(record.get("assigned_manager") or "").strip().lower()
            == filters.get("assigned_manager", "").strip().lower()
        )
    ]

    priority_order = {value: index for index, value in enumerate(MAINTENANCE_PRIORITY_OPTIONS)}
    status_order = {value: index for index, value in enumerate(MAINTENANCE_STATUS_OPTIONS)}

    if filters.get("sort") == "updated":
        filtered.sort(key=lambda record: str(record.get("updated_at") or ""), reverse=True)
    elif filters.get("sort") == "priority":
        filtered.sort(
            key=lambda record: (
                priority_order.get(str(record.get("priority") or ""), len(priority_order)),
                str(record.get("created_at") or ""),
            )
        )
    elif filters.get("sort") == "status":
        filtered.sort(
            key=lambda record: (
                status_order.get(str(record.get("status") or ""), len(status_order)),
                str(record.get("created_at") or ""),
            )
        )
    else:
        filtered.sort(key=lambda record: str(record.get("created_at") or ""), reverse=True)

    return annotate_records_with_listing_links(filtered)


def finance_filter_defaults() -> dict[str, str]:
    return {"q": "", "status": "", "charge_type": "", "assigned_to": "", "sort": "due_asc"}


def finance_filters_from_request() -> dict[str, str]:
    filters = finance_filter_defaults()
    filters.update(
        {
            "q": request.args.get("q", "").strip(),
            "status": request.args.get("status", "").strip(),
            "charge_type": request.args.get("charge_type", "").strip(),
            "assigned_to": request.args.get("assigned_to", "").strip(),
            "sort": request.args.get("sort", "due_asc").strip(),
        }
    )
    if filters["status"] not in FINANCIAL_STATUS_OPTIONS:
        filters["status"] = ""
    if filters["charge_type"] not in FINANCIAL_CHARGE_OPTIONS:
        filters["charge_type"] = ""
    if filters["sort"] not in {value for value, _label in FINANCIAL_SORT_OPTIONS}:
        filters["sort"] = "due_asc"
    return filters


def query_admin_financial_records(filters: Mapping[str, str]) -> list[dict[str, object]]:
    records = all_financial_records()
    filtered = [
        record
        for record in records
        if record_matches_query(
            filters.get("q", ""),
            record.get("resident_name"),
            record.get("unit_reference"),
            record.get("property_title"),
            record.get("note"),
        )
        and (not filters.get("status") or record.get("status") == filters.get("status"))
        and (not filters.get("charge_type") or record.get("charge_type") == filters.get("charge_type"))
        and (
            not filters.get("assigned_to")
            or str(record.get("assigned_to") or "").strip().lower() == filters.get("assigned_to", "").strip().lower()
        )
    ]

    if filters.get("sort") == "due_desc":
        filtered.sort(key=lambda record: str(record.get("due_date") or ""), reverse=True)
    elif filters.get("sort") == "amount_desc":
        filtered.sort(key=lambda record: int(record.get("amount") or 0), reverse=True)
    elif filters.get("sort") == "status":
        order = {value: index for index, value in enumerate(FINANCIAL_STATUS_OPTIONS)}
        filtered.sort(
            key=lambda record: (
                order.get(str(record.get("status") or ""), len(order)),
                str(record.get("due_date") or ""),
            )
        )
    else:
        filtered.sort(key=lambda record: str(record.get("due_date") or ""))

    return annotate_records_with_listing_links(filtered)


def document_filter_defaults() -> dict[str, str]:
    return {"q": "", "document_type": "", "source_kind": "", "document_status": "", "sort": "newest"}


def document_filters_from_request() -> dict[str, str]:
    filters = document_filter_defaults()
    filters.update(
        {
            "q": request.args.get("q", "").strip(),
            "document_type": request.args.get("document_type", "").strip(),
            "source_kind": request.args.get("source_kind", "").strip(),
            "document_status": request.args.get("document_status", "").strip(),
            "sort": request.args.get("sort", "newest").strip(),
        }
    )
    if filters["document_type"] not in DOCUMENT_TYPE_OPTIONS:
        filters["document_type"] = ""
    if filters["source_kind"] not in DOCUMENT_SOURCE_OPTIONS:
        filters["source_kind"] = ""
    if filters["document_status"] not in DOCUMENT_STATUS_OPTIONS:
        filters["document_status"] = ""
    if filters["sort"] not in {value for value, _label in DOCUMENT_SORT_OPTIONS}:
        filters["sort"] = "newest"
    return filters


def query_admin_documents(filters: Mapping[str, str]) -> list[dict[str, object]]:
    records = all_documents()
    filtered = [
        record
        for record in records
        if record_matches_query(
            filters.get("q", ""),
            record.get("title"),
            record.get("resident_name"),
            record.get("unit_reference"),
            record.get("property_title"),
            record.get("original_filename"),
            record.get("note"),
            record.get("template_key"),
            record.get("source_kind"),
        )
        and (
            not filters.get("document_type")
            or record.get("document_type") == filters.get("document_type")
        )
        and (not filters.get("source_kind") or record.get("source_kind") == filters.get("source_kind"))
        and (
            not filters.get("document_status")
            or record.get("document_status") == filters.get("document_status")
        )
    ]

    if filters.get("sort") == "oldest":
        filtered.sort(key=lambda record: str(record.get("created_at") or ""))
    elif filters.get("sort") == "title":
        filtered.sort(key=lambda record: str(record.get("title") or "").lower())
    elif filters.get("sort") == "type":
        filtered.sort(
            key=lambda record: (
                str(record.get("document_type") or "").lower(),
                str(record.get("created_at") or ""),
            )
        )
    else:
        filtered.sort(key=lambda record: str(record.get("created_at") or ""), reverse=True)

    return annotate_records_with_listing_links(filtered)


def parse_optional_iso_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def dashboard_overview_metrics(
    enquiries: list[Mapping[str, object]],
    maintenance_tickets: list[Mapping[str, object]],
    financial_records: list[Mapping[str, object]],
    documents: list[Mapping[str, object]],
) -> dict[str, int]:
    today = date.today()
    lead_attention = 0
    due_follow_ups = 0
    unassigned_leads = 0

    for record in enquiries:
        status = str(record.get("status") or "")
        if status in CLOSED_ENQUIRY_STATUSES:
            continue
        assigned_to = str(record.get("assigned_to") or "").strip()
        follow_up_on = parse_optional_iso_date(record.get("follow_up_on"))
        follow_up_due = bool(follow_up_on and follow_up_on <= today)
        if follow_up_due:
            due_follow_ups += 1
        if not assigned_to:
            unassigned_leads += 1
        if status == "NEW" or follow_up_due or not assigned_to:
            lead_attention += 1

    urgent_tickets = 0
    emergency_tickets = 0
    unassigned_tickets = 0
    vendor_gaps = 0
    for ticket in maintenance_tickets:
        if str(ticket.get("status") or "") not in OPEN_MAINTENANCE_STATUSES:
            continue
        priority = str(ticket.get("priority") or "")
        if priority in {"Emergency", "High"}:
            urgent_tickets += 1
        if priority == "Emergency":
            emergency_tickets += 1
        if not str(ticket.get("assigned_manager") or "").strip():
            unassigned_tickets += 1
        if not str(ticket.get("assigned_vendor") or "").strip():
            vendor_gaps += 1

    overdue_finance = 0
    overdue_finance_amount = 0
    finance_owner_gaps = 0
    for record in financial_records:
        status = str(record.get("status") or "")
        if status == "Overdue":
            overdue_finance += 1
            overdue_finance_amount += int(record.get("amount") or 0)
        if status in ACTIONABLE_FINANCE_STATUSES and not str(record.get("assigned_to") or "").strip():
            finance_owner_gaps += 1

    generated_documents = sum(1 for record in documents if str(record.get("source_kind") or "") == "generated")

    return {
        "lead_attention_count": lead_attention,
        "due_follow_up_count": due_follow_ups,
        "unassigned_leads_count": unassigned_leads,
        "urgent_ticket_count": urgent_tickets,
        "emergency_ticket_count": emergency_tickets,
        "unassigned_ticket_count": unassigned_tickets,
        "vendor_gap_count": vendor_gaps,
        "overdue_finance_count": overdue_finance,
        "overdue_finance_amount": overdue_finance_amount,
        "finance_owner_gap_count": finance_owner_gaps,
        "generated_document_count": generated_documents,
    }


def dashboard_enquiry_preview(records: list[Mapping[str, object]], limit: int = 6) -> list[dict[str, object]]:
    today = date.today()

    def sort_key(record: Mapping[str, object]) -> tuple[int, int, int, int, date, str]:
        status = str(record.get("status") or "")
        follow_up_on = parse_optional_iso_date(record.get("follow_up_on"))
        return (
            0 if status not in CLOSED_ENQUIRY_STATUSES else 1,
            0 if follow_up_on and follow_up_on <= today else 1,
            0 if status == "NEW" else 1,
            0 if not str(record.get("assigned_to") or "").strip() else 1,
            follow_up_on or date.max,
            str(record.get("created_at") or ""),
        )

    preview: list[dict[str, object]] = []
    for record in sorted(records, key=sort_key)[:limit]:
        item = dict(record)
        follow_up_on = parse_optional_iso_date(item.get("follow_up_on"))
        detail_bits: list[str] = []
        if follow_up_on and follow_up_on <= today:
            item["triage_label"] = "Follow-up due"
            detail_bits.append(f"Follow up {follow_up_on.isoformat()}")
        elif str(item.get("status") or "") == "NEW":
            item["triage_label"] = "New lead"
            detail_bits.append("Awaiting first response")
        elif not str(item.get("assigned_to") or "").strip():
            item["triage_label"] = "Assign owner"
            detail_bits.append("No owner assigned yet")
        else:
            item["triage_label"] = "Active"

        if str(item.get("assigned_to") or "").strip():
            detail_bits.append(f"Owner: {item['assigned_to']}")
        else:
            detail_bits.append("Owner missing")
        item["triage_detail"] = " · ".join(detail_bits)
        preview.append(item)
    return preview


def dashboard_maintenance_preview(records: list[Mapping[str, object]], limit: int = 6) -> list[dict[str, object]]:
    priority_order = {"Emergency": 0, "High": 1, "Medium": 2, "Low": 3}

    def sort_key(record: Mapping[str, object]) -> tuple[int, int, int, int, str]:
        status = str(record.get("status") or "")
        priority = str(record.get("priority") or "")
        return (
            0 if status in OPEN_MAINTENANCE_STATUSES else 1,
            priority_order.get(priority, len(priority_order)),
            0 if not str(record.get("assigned_manager") or "").strip() else 1,
            0 if not str(record.get("assigned_vendor") or "").strip() else 1,
            str(record.get("updated_at") or record.get("created_at") or ""),
        )

    preview: list[dict[str, object]] = []
    for record in sorted(records, key=sort_key)[:limit]:
        item = dict(record)
        detail_bits: list[str] = []
        if str(item.get("priority") or "") == "Emergency":
            item["triage_label"] = "Emergency"
        elif not str(item.get("assigned_manager") or "").strip():
            item["triage_label"] = "Assign owner"
        elif not str(item.get("assigned_vendor") or "").strip():
            item["triage_label"] = "Vendor missing"
        elif str(item.get("status") or "") == "New":
            item["triage_label"] = "New ticket"
        else:
            item["triage_label"] = str(item.get("status") or "Open")

        assigned_manager = str(item.get("assigned_manager") or "").strip()
        assigned_vendor = str(item.get("assigned_vendor") or "").strip()
        detail_bits.append(f"Owner: {assigned_manager}" if assigned_manager else "Owner missing")
        detail_bits.append(f"Vendor: {assigned_vendor}" if assigned_vendor else "Vendor missing")
        item["triage_detail"] = " · ".join(detail_bits)
        preview.append(item)
    return preview


def dashboard_finance_preview(records: list[Mapping[str, object]], limit: int = 6) -> list[dict[str, object]]:
    today = date.today()
    status_order = {"Overdue": 0, "Due": 1, "Part Paid": 2, "Paid": 3}

    def sort_key(record: Mapping[str, object]) -> tuple[int, date, int, str]:
        due_date = parse_optional_iso_date(record.get("due_date"))
        return (
            status_order.get(str(record.get("status") or ""), len(status_order)),
            due_date or date.max,
            0 if not str(record.get("assigned_to") or "").strip() else 1,
            str(record.get("created_at") or ""),
        )

    preview: list[dict[str, object]] = []
    for record in sorted(records, key=sort_key)[:limit]:
        item = dict(record)
        due_date = parse_optional_iso_date(item.get("due_date"))
        detail_bits: list[str] = []
        if str(item.get("status") or "") == "Overdue":
            item["triage_label"] = "Overdue"
        elif due_date and due_date <= today:
            item["triage_label"] = "Due now"
        elif not str(item.get("assigned_to") or "").strip():
            item["triage_label"] = "Assign owner"
        else:
            item["triage_label"] = str(item.get("status") or "Due")

        if due_date:
            detail_bits.append(f"Due {due_date.isoformat()}")
        assigned_to = str(item.get("assigned_to") or "").strip()
        detail_bits.append(f"Owner: {assigned_to}" if assigned_to else "Owner missing")
        item["triage_detail"] = " · ".join(detail_bits)
        preview.append(item)
    return preview


def dashboard_document_preview(records: list[Mapping[str, object]], limit: int = 6) -> list[dict[str, object]]:
    preview: list[dict[str, object]] = []
    for record in records[:limit]:
        item = dict(record)
        item["triage_label"] = "Generated" if str(item.get("source_kind") or "") == "generated" else "Uploaded"
        if item["triage_label"] == "Generated" and str(item.get("template_key") or "").strip():
            item["triage_detail"] = str(item["template_key"]).replace("_", " ")
        else:
            item["triage_detail"] = str(item.get("original_filename") or "").strip()
        preview.append(item)
    return preview


def dashboard_action_items(
    overview_metrics: Mapping[str, int],
    inventory_overview: Mapping[str, int],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    def add(count: int, title: str, detail: str, href: str, label: str, tone: str = "attention") -> None:
        if count <= 0:
            return
        actions.append(
            {
                "count": str(count),
                "title": title,
                "detail": detail,
                "href": href,
                "label": label,
                "tone": tone,
            }
        )

    add(
        int(overview_metrics.get("due_follow_up_count") or 0),
        "Follow-ups due now",
        "Lead owners need to make the next contact before opportunities cool off.",
        url_for("admin_enquiries", sort="follow_up"),
        "Open leads",
    )
    add(
        int(overview_metrics.get("unassigned_leads_count") or 0),
        "Unassigned leads",
        "Assign an owner so every enquiry has a clear next step.",
        url_for("admin_enquiries", sort="follow_up"),
        "Assign owners",
    )
    add(
        int(overview_metrics.get("emergency_ticket_count") or 0),
        "Emergency tickets",
        "Operational issues marked emergency should be handled before routine tickets.",
        url_for("admin_maintenance", priority="Emergency", sort="priority"),
        "Review operations",
        "critical",
    )
    add(
        int(overview_metrics.get("vendor_gap_count") or 0),
        "Tickets without vendors",
        "Vendor gaps slow resolution and make support harder to track.",
        url_for("admin_maintenance", sort="priority"),
        "Assign vendors",
    )
    add(
        int(overview_metrics.get("overdue_finance_count") or 0),
        "Overdue finance",
        "Outstanding charges need owner follow-up and payment status updates.",
        url_for("admin_finance", status="Overdue"),
        "Open finance",
        "critical",
    )
    add(
        int(inventory_overview.get("draft_count") or 0),
        "Draft listings",
        "Unpublished inventory should be completed, published, or intentionally archived.",
        url_for("admin_listings", view="drafts"),
        "Review drafts",
        "neutral",
    )
    return actions[:6]


def listing_management_summary(records: list[Mapping[str, object]]) -> dict[str, int]:
    return {
        "published_count": sum(1 for item in records if item.get("published")),
        "draft_count": sum(1 for item in records if not item.get("published")),
        "featured_count": sum(1 for item in records if item.get("featured")),
        "unverified_count": sum(
            1
            for item in records
            if not int(item.get("verified_property") or 0) and not int(item.get("verified_landlord") or 0)
        ),
        "off_market_count": sum(1 for item in records if item.get("availability") == "Off Market"),
        "under_offer_count": sum(1 for item in records if item.get("availability") == "Under Offer"),
    }


def enquiry_management_summary(records: list[Mapping[str, object]]) -> dict[str, object]:
    today = date.today()
    status_counts = {status: 0 for status in ENQUIRY_STATUS_OPTIONS}
    due_follow_up = 0
    unassigned = 0
    for record in records:
        status = canonical_lead_stage(record.get("status"))
        if status in status_counts:
            status_counts[status] += 1
        follow_up_on = parse_optional_iso_date(record.get("follow_up_on"))
        if follow_up_on and follow_up_on <= today and status not in CLOSED_ENQUIRY_STATUSES:
            due_follow_up += 1
        if status not in CLOSED_ENQUIRY_STATUSES and not str(record.get("assigned_to") or "").strip():
            unassigned += 1
    return {
        "status_counts": status_counts,
        "open_count": sum(count for status, count in status_counts.items() if status not in CLOSED_ENQUIRY_STATUSES),
        "due_follow_up_count": due_follow_up,
        "unassigned_count": unassigned,
    }


def maintenance_management_summary(records: list[Mapping[str, object]]) -> dict[str, int]:
    return {
        "open_count": sum(1 for item in records if str(item.get("status") or "") in OPEN_MAINTENANCE_STATUSES),
        "emergency_count": sum(1 for item in records if item.get("priority") == "Emergency"),
        "high_priority_count": sum(1 for item in records if item.get("priority") in {"High", "Emergency"}),
        "owner_gap_count": sum(
            1
            for item in records
            if str(item.get("status") or "") in OPEN_MAINTENANCE_STATUSES
            and not str(item.get("assigned_manager") or "").strip()
        ),
        "vendor_gap_count": sum(
            1
            for item in records
            if str(item.get("status") or "") in OPEN_MAINTENANCE_STATUSES
            and not str(item.get("assigned_vendor") or "").strip()
        ),
    }


def finance_management_summary(records: list[Mapping[str, object]]) -> dict[str, int]:
    open_records = [item for item in records if str(item.get("status") or "") in ACTIONABLE_FINANCE_STATUSES]
    overdue_records = [item for item in records if str(item.get("status") or "") == "Overdue"]
    paid_records = [item for item in records if str(item.get("status") or "") == "Paid"]
    return {
        "open_count": len(open_records),
        "open_amount": sum(int(item.get("amount") or 0) for item in open_records),
        "overdue_count": len(overdue_records),
        "overdue_amount": sum(int(item.get("amount") or 0) for item in overdue_records),
        "paid_count": len(paid_records),
        "paid_amount": sum(int(item.get("amount") or 0) for item in paid_records),
        "owner_gap_count": sum(1 for item in open_records if not str(item.get("assigned_to") or "").strip()),
    }


def document_management_summary(records: list[Mapping[str, object]]) -> dict[str, int]:
    generated = sum(1 for item in records if str(item.get("source_kind") or "") == "generated")
    linked = sum(1 for item in records if str(item.get("related_listing_edit_url") or "").strip())
    return {
        "generated_count": generated,
        "uploaded_count": max(0, len(records) - generated),
        "linked_count": linked,
        "unlinked_count": max(0, len(records) - linked),
    }


def create_listing_record(data: dict[str, object]) -> str:
    payload = dict(data)
    payload["public_id"] = uuid.uuid4().hex[:12]
    payload["view_count"] = int(payload.get("view_count") or 0)
    payload["last_viewed_at"] = payload.get("last_viewed_at")
    payload["longitude"] = normalize_coordinate(payload.get("longitude"), minimum=-180, maximum=180)
    payload["latitude"] = normalize_coordinate(payload.get("latitude"), minimum=-90, maximum=90)
    payload["gallery_paths"] = normalize_string_list(payload.get("gallery_paths"))

    if database_backend() == "mongodb":
        get_mongo_collection().insert_one(payload)
        return str(payload["public_id"])

    sqlite_payload = {key: value for key, value in payload.items() if key != "public_id"}
    sqlite_payload["gallery_paths"] = json.dumps(sqlite_payload.get("gallery_paths", []))
    cursor = get_db().execute(
        """
        INSERT INTO listings (
            title,
            status,
            availability,
            property_type,
            district,
            address,
            longitude,
            latitude,
            gallery_paths,
            virtual_tour_url,
            documentation_summary,
            documentation_verified,
            payment_plan_summary,
            is_serviced,
            has_power_24_7,
            is_flood_free,
            near_express,
            near_schools,
            near_markets,
            verified_property,
            verified_landlord,
            price,
            price_suffix,
            bedrooms,
            bathrooms,
            area_sqm,
            summary,
            description,
            image_path,
            featured,
            published,
            view_count,
            last_viewed_at,
            created_at,
            updated_at
        ) VALUES (
            :title,
            :status,
            :availability,
            :property_type,
            :district,
            :address,
            :longitude,
            :latitude,
            :gallery_paths,
            :virtual_tour_url,
            :documentation_summary,
            :documentation_verified,
            :payment_plan_summary,
            :is_serviced,
            :has_power_24_7,
            :is_flood_free,
            :near_express,
            :near_schools,
            :near_markets,
            :verified_property,
            :verified_landlord,
            :price,
            :price_suffix,
            :bedrooms,
            :bathrooms,
            :area_sqm,
            :summary,
            :description,
            :image_path,
            :featured,
            :published,
            :view_count,
            :last_viewed_at,
            :created_at,
            :updated_at
        )
        """,
        sqlite_payload,
    )
    get_db().commit()
    return str(cursor.lastrowid)


def update_listing_record(listing_id: str, data: dict[str, object]) -> None:
    payload = dict(data)
    payload["longitude"] = normalize_coordinate(payload.get("longitude"), minimum=-180, maximum=180)
    payload["latitude"] = normalize_coordinate(payload.get("latitude"), minimum=-90, maximum=90)
    payload["gallery_paths"] = normalize_string_list(payload.get("gallery_paths"))
    if database_backend() == "mongodb":
        get_mongo_collection().update_one({"public_id": listing_id}, {"$set": payload})
        return

    payload["id"] = sqlite_listing_id(listing_id)
    payload["gallery_paths"] = json.dumps(payload.get("gallery_paths", []))
    get_db().execute(
        """
        UPDATE listings
        SET
            title = :title,
            status = :status,
            availability = :availability,
            property_type = :property_type,
            district = :district,
            address = :address,
            longitude = :longitude,
            latitude = :latitude,
            gallery_paths = :gallery_paths,
            virtual_tour_url = :virtual_tour_url,
            documentation_summary = :documentation_summary,
            documentation_verified = :documentation_verified,
            payment_plan_summary = :payment_plan_summary,
            is_serviced = :is_serviced,
            has_power_24_7 = :has_power_24_7,
            is_flood_free = :is_flood_free,
            near_express = :near_express,
            near_schools = :near_schools,
            near_markets = :near_markets,
            verified_property = :verified_property,
            verified_landlord = :verified_landlord,
            price = :price,
            price_suffix = :price_suffix,
            bedrooms = :bedrooms,
            bathrooms = :bathrooms,
            area_sqm = :area_sqm,
            summary = :summary,
            description = :description,
            image_path = :image_path,
            featured = :featured,
            published = :published,
            updated_at = :updated_at
        WHERE id = :id
        """,
        payload,
    )
    get_db().commit()


def delete_listing_record(listing_id: str) -> None:
    if database_backend() == "mongodb":
        get_mongo_collection().delete_one({"public_id": listing_id})
        return

    get_db().execute("DELETE FROM listings WHERE id = ?", (sqlite_listing_id(listing_id),))
    get_db().commit()


def build_whatsapp_url(message: str) -> str:
    settings = site_settings()
    return f"https://wa.me/{settings['whatsapp_phone']}?text={quote(message)}"


def listing_whatsapp_message(listing: Mapping[str, object]) -> str:
    settings = site_settings()
    price = format_naira(int(listing["price"]) if listing["price"] is not None else None)
    return (
        f"Hello {settings['site_name']}, I am interested in {listing['title']} in {listing['district']} "
        f"listed at {price}{listing['price_suffix']}. Please share more details and viewing availability."
    )


def general_whatsapp_message() -> str:
    settings = site_settings()
    return f"Hello {settings['site_name']}, I need help with a property search, enquiry, or support request."


def listing_field(listing: sqlite3.Row | dict[str, object], key: str) -> object:
    if isinstance(listing, sqlite3.Row):
        return listing[key]
    return listing.get(key, "")


def representative_listing_image_path(listing: sqlite3.Row | dict[str, object]) -> str:
    property_type = str(listing_field(listing, "property_type") or "").lower()
    district = str(listing_field(listing, "district") or "").lower()

    if any(token in property_type for token in ("office", "commercial", "workspace", "suite", "shop")):
        return "images/victoria-island-office-sample.webp"
    if "yaba" in district or any(token in property_type for token in ("duplex",)):
        return "images/yaba-duplex-sample.webp"
    if any(token in property_type for token in ("penthouse", "apartment", "flat")):
        return "images/ikoyi-penthouse-sample.webp"
    if any(token in property_type for token in ("detached", "house", "villa", "terrace")):
        return "images/lekki-villa-sample.webp"
    if any(token in district for token in ("ikoyi", "victoria island", "banana island")):
        return "images/ikoyi-penthouse-sample.webp"
    if any(token in district for token in ("lekki", "ajah", "epe")):
        return "images/lekki-villa-sample.webp"
    return "images/lekki-villa-sample.webp"


def listing_has_uploaded_image(listing: sqlite3.Row | dict[str, object]) -> bool:
    image_path = str(listing_field(listing, "image_path") or "").strip()
    if not image_path:
        return False
    if image_path.startswith(("http://", "https://")):
        return True
    if image_path.startswith("uploads/") or is_cloudinary_asset(image_path):
        return uploaded_asset_exists(image_path)
    return (STATIC_DIR / image_path).exists()


def resolved_listing_image_path(listing: sqlite3.Row | dict[str, object]) -> str:
    if listing_has_uploaded_image(listing):
        return str(listing_field(listing, "image_path")).strip()
    gallery_paths = normalize_string_list(listing_field(listing, "gallery_paths"))
    for path in gallery_paths:
        if path:
            return path
    return representative_listing_image_path(listing)


def listing_media_gallery(listing: Mapping[str, object]) -> list[str]:
    gallery_paths = normalize_string_list(listing.get("gallery_paths"))
    ordered: list[str] = []
    primary = resolved_listing_image_path(listing)
    if primary:
        ordered.append(primary)
    for path in gallery_paths:
        if path and path not in ordered:
            ordered.append(path)
    return ordered


def listing_feature_labels(listing: Mapping[str, object]) -> list[str]:
    return [label for key, label in DISCOVERY_FEATURE_FIELDS if listing.get(key)]


def listing_verification_labels(listing: Mapping[str, object]) -> list[str]:
    return [label for key, label in VERIFICATION_FIELDS if listing.get(key)]


def asset_url(asset_path: str | None) -> str:
    path = (asset_path or "").strip()
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    if is_cloudinary_asset(path):
        configure_cloudinary()
        return cloudinary_url(
            cloudinary_public_id(path),
            secure=True,
            resource_type="image",
            format="webp",
        )[0]
    return static_asset_url(path)


def absolute_asset_url(asset_path: str | None) -> str:
    url = asset_url(asset_path)
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        origin = configured_public_origin() or request.url_root.rstrip("/")
        url = origin + "/" + url.lstrip("/")
    return canonical_external_url(url)


def canonical_external_url(url: str) -> str:
    if app.config["IS_PRODUCTION"] and url.startswith("http://"):
        return "https://" + url.removeprefix("http://")
    return url


def configured_public_origin() -> str:
    value = str(app.config.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def canonical_request_url() -> str:
    origin = configured_public_origin()
    if origin:
        return origin + (request.path if request.path.startswith("/") else f"/{request.path}")
    return canonical_external_url(request.base_url)


def organization_structured_data() -> dict[str, object]:
    settings = site_settings()
    data: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "RealEstateAgent",
        "name": str(settings["site_name"]),
        "url": canonical_external_url((configured_public_origin() or request.url_root.rstrip("/")) + "/"),
        "logo": absolute_asset_url("images/logo-mark.webp"),
        "address": {
            "@type": "PostalAddress",
            "streetAddress": str(settings["office_address"]),
            "addressCountry": "NG",
        },
        "areaServed": str(settings["coverage_area"]),
    }
    contact_points: list[dict[str, str]] = []
    if settings["contact_phone_configured"]:
        contact_points.append(
            {
                "@type": "ContactPoint",
                "telephone": str(settings["contact_phone_raw"]),
                "contactType": "sales",
                "areaServed": "NG",
            }
        )
    if settings["contact_email_configured"]:
        contact_points.append(
            {
                "@type": "ContactPoint",
                "email": str(settings["contact_email"]),
                "contactType": "customer service",
                "areaServed": "NG",
            }
        )
    if contact_points:
        data["contactPoint"] = contact_points
    return data


def _compute_static_asset_version(filename: str) -> str:
    file_path = STATIC_DIR / filename
    try:
        return hashlib.blake2s(file_path.read_bytes(), digest_size=6).hexdigest()
    except OSError:
        return "0"


@lru_cache(maxsize=256)
def _cached_static_asset_version(filename: str) -> str:
    return _compute_static_asset_version(filename)


def static_asset_version(filename: str) -> str:
    if app.config["IS_PRODUCTION"]:
        return _cached_static_asset_version(filename)
    return _compute_static_asset_version(filename)


def static_asset_url(filename: str) -> str:
    return url_for("static", filename=filename, v=static_asset_version(filename))


def service_worker_url() -> str:
    return url_for("service_worker", v=static_asset_version("service-worker.js"))


def listing_schema_availability(listing: Mapping[str, object]) -> str:
    availability = str(listing.get("availability") or "Available")
    if availability in {"Sold", "Rented", "Leased", "Off Market"}:
        return "https://schema.org/SoldOut"
    if availability == "Under Offer":
        return "https://schema.org/LimitedAvailability"
    return "https://schema.org/InStock"


def property_structured_data(listing: Mapping[str, object]) -> dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@type": "Offer",
        "name": str(listing["title"]),
        "description": str(listing["summary"]),
        "url": canonical_request_url(),
        "image": absolute_asset_url(resolved_listing_image_path(listing)),
        "priceCurrency": "NGN",
        "price": int(listing["price"]) if listing.get("price") is not None else None,
        "availability": listing_schema_availability(listing),
        "seller": {"@type": "Organization", "name": app.config["SITE_NAME"]},
        "itemOffered": {
            "@type": "Residence" if str(listing.get("property_type") or "").lower() != "office" else "Product",
            "name": str(listing["title"]),
            "address": str(listing["address"]),
        },
    }


@app.template_filter("naira")
def format_naira(value: int | None) -> str:
    if value is None:
        return "Price on request"
    return f"NGN {value:,.0f}"


@app.template_filter("grouped_number")
def format_grouped_number(value: object) -> str:
    raw = str(value or "").strip().replace(",", "")
    return f"{int(raw):,}" if raw.isdigit() else ""


@app.template_filter("filesize")
def format_filesize(value: int | None) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return "0 B"


def listing_price_label(listing: Mapping[str, object]) -> str:
    return f"{format_naira(int(listing['price']) if listing.get('price') is not None else None)}{listing.get('price_suffix') or ''}"


def listing_map_feature(listing: Mapping[str, object]) -> dict[str, object] | None:
    longitude = listing.get("map_longitude")
    latitude = listing.get("map_latitude")
    if longitude is None or latitude is None:
        return None

    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        "properties": {
            "id": str(listing["id"]),
            "title": str(listing["title"]),
            "district": str(listing["district"]),
            "address": str(listing["address"]),
            "property_type": str(listing["property_type"]),
            "status": str(listing["status"]),
            "availability": str(listing["availability"]),
            "price_label": listing_price_label(listing),
            "detail_url": url_for("property_detail", listing_id=str(listing["id"])),
            "results_anchor": f"#listing-{listing['id']}",
            "image_url": asset_url(resolved_listing_image_path(listing)),
            "map_location_mode": str(listing.get("map_location_mode") or "missing"),
            "verified_property": 1 if listing.get("verified_property") else 0,
            "verified_landlord": 1 if listing.get("verified_landlord") else 0,
        },
    }


def listing_map_payload(listings: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, int]]:
    features = [feature for listing in listings if (feature := listing_map_feature(listing))]
    exact_count = sum(1 for listing in listings if listing.get("map_location_mode") == "exact")
    mapped_count = len(features)
    return (
        {"type": "FeatureCollection", "features": features},
        {
            "mapped_count": mapped_count,
            "exact_count": exact_count,
            "approximate_count": max(0, mapped_count - exact_count),
        },
    )


@app.context_processor
def inject_globals() -> dict[str, object]:
    settings = site_settings()
    partner = current_partner()
    return {
        "current_year": datetime.now().year,
        "site_settings": settings,
        "is_authenticated": is_authenticated(),
        "current_staff": staff_record_for_template(current_staff()) if current_staff() else None,
        "is_partner_authenticated": is_partner_authenticated(),
        "has_partner_account": partner is not None,
        "current_partner": partner_record_for_template(partner) if partner else None,
        "can": has_permission,
        "role_labels": ROLE_LABELS,
        "general_whatsapp_url": build_whatsapp_url(general_whatsapp_message()),
        "listing_whatsapp_url": lambda listing: build_whatsapp_url(listing_whatsapp_message(listing)),
        "listing_image_path": resolved_listing_image_path,
        "listing_media_gallery": listing_media_gallery,
        "listing_feature_labels": listing_feature_labels,
        "listing_verification_labels": listing_verification_labels,
        "listing_has_uploaded_image": listing_has_uploaded_image,
        "asset_url": asset_url,
        "absolute_asset_url": absolute_asset_url,
        "canonical_request_url": canonical_request_url,
        "organization_structured_data": organization_structured_data,
        "static_asset_url": static_asset_url,
        "service_worker_url": service_worker_url(),
        "database_backend": database_backend(),
        "storage_backend": storage_backend(),
        "is_production": app.config["IS_PRODUCTION"],
        "search_indexing_enabled": bool(app.config["SEARCH_INDEXING_ENABLED"]),
        "csrf_token": csrf_token,
        "csp_nonce": lambda: getattr(g, "csp_nonce", ""),
        "availability_options": AVAILABILITY_OPTIONS,
        "enquiry_contact_options": ENQUIRY_CONTACT_OPTIONS,
        "status_options": STATUS_OPTIONS,
        "discovery_feature_fields": DISCOVERY_FEATURE_FIELDS,
        "verification_fields": VERIFICATION_FIELDS,
        "maintenance_category_options": MAINTENANCE_CATEGORY_OPTIONS,
        "maintenance_priority_options": MAINTENANCE_PRIORITY_OPTIONS,
        "maintenance_status_options": MAINTENANCE_STATUS_OPTIONS,
        "financial_charge_options": FINANCIAL_CHARGE_OPTIONS,
        "financial_status_options": FINANCIAL_STATUS_OPTIONS,
        "document_type_options": DOCUMENT_TYPE_OPTIONS,
        "mapbox_token": app.config["MAPBOX_TOKEN"],
    }


@app.route("/")
def home():
    if request.args.get("ref"):
        capture_referral(request.args.get("ref", ""))
    featured = home_featured_listings(limit=3)
    completed = home_completed_listings(limit=3)
    stats = public_stats(include_district_count=True)
    districts = top_districts(limit=4)
    return render_template(
        "index.html",
        featured=featured,
        completed=completed,
        stats=stats,
        districts=districts,
        search_districts=distinct_public_values("district"),
        search_property_types=distinct_public_values("property_type"),
    )


@app.route("/properties")
def properties():
    if request.args.get("ref"):
        capture_referral(request.args.get("ref", ""))
    raw_min_price = request.args.get("min_price", "").strip().replace(",", "")
    raw_max_price = request.args.get("max_price", "").strip().replace(",", "")
    raw_min_bedrooms = request.args.get("min_bedrooms", "").strip()
    min_price = raw_min_price if raw_min_price.isdigit() and 0 < int(raw_min_price) <= 10_000_000_000_000 else ""
    max_price = raw_max_price if raw_max_price.isdigit() and 0 < int(raw_max_price) <= 10_000_000_000_000 else ""
    min_bedrooms = raw_min_bedrooms if raw_min_bedrooms.isdigit() and 0 < int(raw_min_bedrooms) <= 20 else ""
    sort = request.args.get("sort", "recommended").strip()
    if sort not in PUBLIC_LISTING_SORT_DEFINITIONS:
        sort = "recommended"
    filters = {
        "status": request.args.get("status", "").strip(),
        "availability": request.args.get("availability", "").strip(),
        "district": request.args.get("district", "").strip(),
        "property_type": request.args.get("property_type", "").strip(),
        "q": request.args.get("q", "").strip(),
        "min_price": min_price,
        "max_price": max_price,
        "min_bedrooms": min_bedrooms,
        "sort": sort,
        "verified_only": "1" if request.args.get("verified_only") else "",
    }
    for key, _label in DISCOVERY_FEATURE_FIELDS:
        filters[key] = "1" if request.args.get(key) else ""
    listings = query_public_listings(filters)
    active_filter_count = sum(
        bool(filters.get(key))
        for key in (
            "status", "availability", "district", "property_type", "q",
            "min_price", "max_price", "min_bedrooms", "verified_only",
            *(key for key, _label in DISCOVERY_FEATURE_FIELDS),
        )
    )

    districts = distinct_public_values("district")
    property_types = distinct_public_values("property_type")
    availabilities = distinct_public_values("availability")
    map_feature_collection, map_summary = listing_map_payload(listings)

    return render_template(
        "properties.html",
        listings=listings,
        filters=filters,
        districts=districts,
        property_types=property_types,
        availabilities=availabilities,
        map_feature_collection=map_feature_collection,
        map_summary=map_summary,
        feature_filter_fields=DISCOVERY_FEATURE_FIELDS,
        public_sort_options=PUBLIC_LISTING_SORT_OPTIONS,
        active_filter_count=active_filter_count,
    )


@app.route("/properties/<listing_id>")
def property_detail(listing_id: str):
    listing = fetch_listing(listing_id)
    if request.args.get("ref"):
        capture_referral(
            request.args.get("ref", ""),
            listing_id=str(listing["id"]),
            listing_title=str(listing["title"]),
        )
    if should_track_listing_view(str(listing["id"])):
        increment_listing_view(str(listing["id"]))
        listing["view_count"] = int(listing.get("view_count", 0)) + 1
    related = related_listings(listing, limit=3)
    return render_template(
        "property_detail.html",
        listing=listing,
        related=related,
        today_iso=date.today().isoformat(),
        structured_data=property_structured_data(listing),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if is_authenticated():
        return redirect(url_for("dashboard"))

    next_url = safe_redirect_target(request.args.get("next") or request.form.get("next"))
    login_error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if login_is_rate_limited(username):
            login_error = "Too many sign-in attempts. Wait a few minutes before trying again."
            return render_template(
                "login.html",
                next_url=next_url,
                using_default_credentials=site_settings()["using_default_credentials"],
                admin_username=username or app.config["ADMIN_USERNAME"],
                show_local_default_credentials=is_local_request_host(),
                default_admin_username=DEFAULT_ADMIN_USERNAME,
                default_admin_password=DEFAULT_ADMIN_PASSWORD,
                login_error=login_error,
            )

        staff = authenticate_staff(username, password)
        if staff is not None:
            session.clear()
            session["staff_user_id"] = str(staff["id"])
            session["staff_role"] = str(staff["role"])
            session["staff_name"] = str(staff["full_name"])
            session.permanent = True
            reset_failed_login(username)
            update_staff_last_login(str(staff["id"]))
            create_activity_record(
                entity_type="staff_user",
                entity_id=str(staff["id"]),
                action="signed_in",
                summary=f"{staff['full_name']} signed in.",
                actor_label=str(staff["full_name"]),
                actor_id=str(staff["id"]),
                actor_type="staff",
            )
            flash(f"Welcome back, {staff['full_name']}.", "success")
            return redirect(next_url)

        record_failed_login(username)
        login_error = "Incorrect username or password."

    return render_template(
        "login.html",
        next_url=next_url,
        using_default_credentials=site_settings()["using_default_credentials"],
        admin_username=request.form.get("username", "").strip() if request.method == "POST" else "",
        show_local_default_credentials=is_local_request_host(),
        default_admin_username=DEFAULT_ADMIN_USERNAME,
        default_admin_password=DEFAULT_ADMIN_PASSWORD,
        login_error=login_error,
    )


@app.post("/logout")
def logout():
    staff = current_staff()
    if staff is not None:
        create_activity_record(
            entity_type="staff_user",
            entity_id=str(staff["id"]),
            action="signed_out",
            summary=f"{staff['full_name']} signed out.",
        )
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


@app.post("/enquiries")
def submit_enquiry():
    next_url = safe_redirect_target(request.form.get("source_path") or request.referrer or url_for("properties"))
    listing_id = request.form.get("listing_id", "").strip()
    listing = fetch_listing(listing_id) if listing_id else None
    enquiry_data, errors = validate_enquiry_form(request.form, listing)

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(next_url)

    enquiry_id = create_enquiry_record(enquiry_data)
    referral = attach_referral_to_lead(enquiry_id, str(enquiry_data.get("listing_id") or ""))
    create_activity_record(
        entity_type="enquiry",
        entity_id=enquiry_id,
        action="created",
        summary=f"New enquiry from {enquiry_data['name']} for {enquiry_data['listing_title'] or 'general assistance'}.",
        actor_label="Public enquiry",
        metadata={
            "referral_id": str(referral.get("id") or "") if referral else "",
            "partner_id": str(referral.get("partner_id") or "") if referral else "",
        },
    )
    delivery = send_enquiry_emails(enquiry_id, enquiry_data, listing)
    if enquiry_data.get("email") and delivery["receipt_sent"]:
        flash(
            "Enquiry received. A confirmation email is on the way, and the team will follow up soon.",
            "success",
        )
    else:
        flash("Enquiry received. The team will follow up using your preferred contact details.", "success")
    return redirect(next_url)


@app.route("/dashboard")
@permission_required("dashboard.view")
def dashboard():
    stats = dashboard_stats()
    inventory = dashboard_listings() if has_permission("properties.view") else []
    enquiry_records = all_enquiries() if has_permission("leads.view") else []
    maintenance_records = all_maintenance_tickets() if has_permission("maintenance.view") else []
    finance_records = all_financial_records() if has_permission("finance.view") else []
    document_records = all_documents() if has_permission("documents.view") else []
    partner_records = all_partners() if has_permission("partners.view") else []
    overview_metrics = dashboard_overview_metrics(
        enquiry_records,
        maintenance_records,
        finance_records,
        document_records,
    )
    inventory_overview = {
        "draft_count": sum(1 for listing in inventory if not listing.get("published")),
        "under_offer_count": sum(1 for listing in inventory if listing.get("availability") == "Under Offer"),
        "off_market_count": sum(1 for listing in inventory if listing.get("availability") == "Off Market"),
        "verified_count": sum(
            1
            for listing in inventory
            if int(listing.get("verified_property") or 0) or int(listing.get("verified_landlord") or 0)
        ),
    }
    action_items = dashboard_action_items(overview_metrics, inventory_overview)
    pending_partner_count = sum(1 for item in partner_records if item.get("status") == "PENDING")
    if pending_partner_count:
        action_items.insert(0, {
            "count": str(pending_partner_count), "title": "Partner applications awaiting review",
            "detail": "Review identity and business information before granting external portal access.",
            "href": url_for("admin_partners", status="PENDING"), "label": "Review partners", "tone": "attention",
        })
    action_items = [
        item
        for item in action_items
        if not (
            (item["href"].startswith(url_for("admin_enquiries")) and not has_permission("leads.view"))
            or (item["href"].startswith(url_for("admin_maintenance")) and not has_permission("maintenance.view"))
            or (item["href"].startswith(url_for("admin_finance")) and not has_permission("finance.view"))
            or (item["href"].startswith(url_for("admin_listings")) and not has_permission("properties.view"))
        )
    ]
    enquiry_preview_filters = enquiry_filter_defaults()
    enquiry_preview_filters["sort"] = "follow_up"
    return render_template(
        "dashboard.html",
        stats=stats,
        overview_metrics=overview_metrics,
        inventory_overview=inventory_overview,
        action_items=action_items,
        recent_listings=inventory[:6],
        recent_enquiries=dashboard_enquiry_preview(query_admin_enquiries(enquiry_preview_filters), limit=6),
        recent_maintenance=dashboard_maintenance_preview(query_admin_maintenance(maintenance_filter_defaults()), limit=6),
        upcoming_finance=dashboard_finance_preview(query_admin_financial_records(finance_filter_defaults()), limit=6),
        recent_documents=dashboard_document_preview(query_admin_documents(document_filter_defaults()), limit=6),
        activity=recent_activity(limit=10) if has_permission("audit_logs.view") else [],
        partner_summary={
            "total": len(partner_records),
            "pending": sum(1 for item in partner_records if item.get("status") == "PENDING"),
            "approved": sum(1 for item in partner_records if item.get("status") == "APPROVED"),
        },
    )


@app.get("/dashboard/analytics")
@permission_required("analytics.view")
def admin_analytics():
    show_properties = has_permission("properties.view")
    show_leads = has_permission("leads.view")
    show_inspections = has_permission("inspections.view")
    show_partners = has_permission("partners.view")
    show_referrals = has_permission("referrals.view")
    show_commissions = has_permission("commissions.view")

    analytics = build_business_analytics(
        listings=dashboard_listings() if show_properties else [],
        leads=all_enquiries() if show_leads else [],
        inspections=all_inspections() if show_inspections else [],
        partners=all_partners() if show_partners else [],
        referrals=all_referrals() if show_referrals else [],
        commissions=all_commissions() if show_commissions else [],
    )
    return render_template(
        "admin_analytics.html",
        analytics=analytics,
        show_properties=show_properties,
        show_leads=show_leads,
        show_inspections=show_inspections,
        show_partners=show_partners,
        show_referrals=show_referrals,
        show_commissions=show_commissions,
    )


@app.route("/dashboard/listings")
@permission_required("properties.view")
def admin_listings():
    filters = admin_listing_filters_from_request()
    listings = dashboard_listings(filters)
    all_inventory = dashboard_listings()
    active_filter_labels = dashboard_active_filter_labels(filters)
    if filters.get("view") and filters["view"] != "all":
        active_filter_labels.insert(0, f"View: {listing_saved_view_label(filters['view'])}")

    saved_view_counts = {
        "all": len(all_inventory),
        "drafts": sum(1 for listing in all_inventory if not listing.get("published")),
        "published": sum(1 for listing in all_inventory if listing.get("published")),
        "featured": sum(1 for listing in all_inventory if listing.get("featured")),
        "under_offer": sum(1 for listing in all_inventory if listing.get("availability") == "Under Offer"),
        "off_market": sum(1 for listing in all_inventory if listing.get("availability") == "Off Market"),
        "most_viewed": len(all_inventory),
        "verified": sum(
            1
            for listing in all_inventory
            if int(listing.get("verified_property") or 0) or int(listing.get("verified_landlord") or 0)
        ),
    }
    return render_template(
        "admin_listings.html",
        listings=listings,
        stats=dashboard_stats(),
        inventory_total=len(all_inventory),
        status_options=STATUS_OPTIONS,
        listing_filters=filters,
        listing_saved_views=LISTING_SAVED_VIEWS,
        listing_saved_view_counts=saved_view_counts,
        listing_summary=listing_management_summary(all_inventory),
        listing_bulk_action_options=LISTING_BULK_ACTION_OPTIONS,
        dashboard_sort_options=DASHBOARD_SORT_OPTIONS,
        dashboard_districts=distinct_dashboard_values("district"),
        dashboard_property_types=distinct_dashboard_values("property_type"),
        dashboard_availabilities=distinct_dashboard_values("availability"),
        dashboard_active_filter_labels=active_filter_labels,
    )


@app.post("/dashboard/listings/bulk")
@permission_required("properties.edit")
def bulk_update_listings():
    next_url = admin_return_target("admin_listings")
    action = request.form.get("action", "").strip()
    listing_ids = [listing_id.strip() for listing_id in request.form.getlist("listing_ids") if listing_id.strip()]
    allowed_actions = {value for value, _label in LISTING_BULK_ACTION_OPTIONS}

    if action not in allowed_actions:
        flash("Choose a valid bulk action.", "error")
        return redirect(next_url)
    if not listing_ids:
        flash("Select at least one listing before applying a bulk action.", "error")
        return redirect(next_url)

    updated_count = apply_listing_bulk_action(listing_ids, action)
    if updated_count:
        flash(
            f"Bulk action applied to {updated_count} listing{'s' if updated_count != 1 else ''}.",
            "success",
        )
    else:
        flash("No listings were updated.", "error")
    return redirect(next_url)


@app.route("/dashboard/enquiries")
@permission_required("leads.view")
def admin_enquiries():
    filters = enquiry_filters_from_request()
    all_records = all_enquiries()
    records = query_admin_enquiries(filters)
    active_filter_labels: list[str] = []
    if filters.get("q"):
        active_filter_labels.append(f'Search: "{filters["q"]}"')
    if filters.get("status"):
        active_filter_labels.append(lead_stage_label(filters["status"]))
    if filters.get("source"):
        active_filter_labels.append(LEAD_SOURCE_LABELS[filters["source"]])
    if filters.get("assigned_to"):
        active_filter_labels.append(f"Owner: {filters['assigned_to']}")
    return render_template(
        "admin_enquiries.html",
        enquiries=records,
        enquiry_filters=filters,
        enquiry_status_options=ENQUIRY_STATUS_OPTIONS,
        lead_stage_labels=LEAD_STAGE_LABELS,
        lead_sources=LEAD_SOURCES,
        lead_source_labels=LEAD_SOURCE_LABELS,
        enquiry_sort_options=ENQUIRY_SORT_OPTIONS,
        enquiry_total=len(all_records),
        enquiry_summary=enquiry_management_summary(all_records),
        enquiry_assignees=distinct_record_values(all_records, "assigned_to"),
        assignable_staff=active_staff_with_permission("leads.manage"),
        active_filter_labels=active_filter_labels,
    )


@app.route("/dashboard/leads/<lead_id>")
@permission_required("leads.view")
def admin_lead_detail(lead_id: str):
    lead = fetch_enquiry(lead_id)
    source_partner = fetch_partner(str(lead.get("partner_id") or ""))
    source_referral = fetch_referral(str(lead.get("referral_id") or ""))
    return render_template(
        "admin_lead_detail.html",
        lead=lead,
        contact=fetch_contact(str(lead.get("contact_id") or "")),
        notes=lead_notes(lead_id),
        lead_activity=activity_for_entity("enquiry", lead_id),
        inspections=inspections_for_lead(lead_id) if has_permission("inspections.view") else [],
        enquiry_status_options=ENQUIRY_STATUS_OPTIONS,
        lead_stage_labels=LEAD_STAGE_LABELS,
        lead_sources=LEAD_SOURCES,
        lead_source_labels=LEAD_SOURCE_LABELS,
        assignable_staff=active_staff_with_permission("leads.manage"),
        source_partner=source_partner,
        source_referral=source_referral,
        commission=fetch_commission_for_lead(lead_id) if has_permission("commissions.view") else None,
    )


@app.route("/dashboard/inspections")
@permission_required("inspections.view")
def admin_inspections():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip().upper()
    if status not in INSPECTION_STATUSES:
        status = ""
    records = [
        item for item in all_inspections()
        if (not status or item["status"] == status)
        and record_matches_query(
            query, item.get("name"), item.get("email"), item.get("phone"),
            item.get("listing_title"), item.get("assigned_to"), item.get("notes"),
        )
    ]
    return render_template(
        "admin_inspections.html", inspections=records, inspection_total=len(all_inspections()),
        inspection_statuses=INSPECTION_STATUSES, inspection_status_labels=INSPECTION_STATUS_LABELS,
        filters={"q": query, "status": status},
        assignable_staff=active_staff_with_permission("inspections.manage"),
    )


@app.get("/dashboard/referrals")
@permission_required("referrals.view")
def admin_referrals():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip().upper()
    partner_id = request.args.get("partner_id", "").strip()
    if status not in REFERRAL_STATUSES:
        status = ""
    all_records = all_referrals()
    partner_lookup = {str(item["id"]): partner_record_for_template(item) for item in all_partners()}
    records = [
        {**item, "partner": partner_lookup.get(str(item.get("partner_id") or ""))}
        for item in all_records
        if (not status or item.get("status") == status)
        and (not partner_id or item.get("partner_id") == partner_id)
        and record_matches_query(
            query, item.get("partner_code"), item.get("listing_title"), item.get("listing_id"),
            item.get("lead_id"), item.get("inspection_id"),
        )
    ]
    return render_template(
        "admin_referrals.html",
        referrals=records,
        referral_total=len(all_records),
        referral_statuses=REFERRAL_STATUSES,
        referral_status_labels=REFERRAL_STATUS_LABELS,
        partners=sorted(partner_lookup.values(), key=lambda item: str(item.get("full_name") or "").casefold()),
        filters={"q": query, "status": status, "partner_id": partner_id},
    )


@app.get("/dashboard/referrals/<referral_id>")
@permission_required("referrals.view")
def admin_referral_detail(referral_id: str):
    referral = fetch_referral(referral_id)
    if referral is None:
        abort(404)
    return render_template(
        "admin_referral_detail.html",
        referral=referral,
        partner=fetch_partner(str(referral.get("partner_id") or "")),
        lead=fetch_enquiry(str(referral["lead_id"])) if referral.get("lead_id") else None,
        events=referral_events(referral_id),
    )


@app.get("/dashboard/commissions")
@permission_required("commissions.view")
def admin_commissions():
    status = request.args.get("status", "").strip().upper()
    partner_id = request.args.get("partner_id", "").strip()
    listing_id = request.args.get("listing_id", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    if status not in COMMISSION_STATUSES:
        status = ""
    for value in (date_from, date_to):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                abort(400)
    all_records = all_commissions()
    records = query_commissions(
        status=status, partner_id=partner_id, listing_id=listing_id,
        date_from=date_from, date_to=date_to,
    )
    summary = {
        key.lower(): sum(item["final_amount"] for item in all_records if item["status"] == key)
        for key in COMMISSION_STATUSES
    }
    return render_template(
        "admin_commissions.html", commissions=records, commission_total=len(all_records),
        commission_statuses=COMMISSION_STATUSES, commission_status_labels=COMMISSION_STATUS_LABELS,
        partners=sorted(all_partners(), key=lambda item: str(item.get("full_name") or "").casefold()),
        properties=dashboard_listings(), filters={
            "status": status, "partner_id": partner_id, "listing_id": listing_id,
            "date_from": date_from, "date_to": date_to,
        }, summary=summary,
    )


@app.get("/dashboard/commissions/<commission_id>")
@permission_required("commissions.view")
def admin_commission_detail(commission_id: str):
    commission = fetch_commission(commission_id)
    if commission is None:
        abort(404)
    return render_template(
        "admin_commission_detail.html", commission=commission,
        partner=fetch_partner(str(commission["partner_id"])),
        lead=fetch_enquiry(str(commission["lead_id"])),
        rule=fetch_commission_rule(str(commission["rule_id"])),
        approver=fetch_staff_user(str(commission.get("approved_by") or "")),
        rejector=fetch_staff_user(str(commission.get("rejected_by") or "")),
        payer=fetch_staff_user(str(commission.get("paid_by") or "")),
        commission_activity=activity_for_entity("commission", commission_id),
    )


@app.route("/dashboard/commission-rules", methods=["GET", "POST"])
@permission_required("commissions.manage")
def admin_commission_rules():
    form_data: Mapping[str, object] = request.form if request.method == "POST" else {}
    errors: list[str] = []
    if request.method == "POST":
        data, errors = validate_commission_rule_form(request.form)
        if not errors:
            staff = current_staff()
            assert staff is not None
            rule_id = save_commission_rule(data, created_by=str(staff["id"]))
            create_activity_record(
                entity_type="commission_rule", entity_id=rule_id, action="created",
                summary=f"Commission rule created: {data['name']}.",
                metadata={"scope_type": data["scope_type"], "calculation_type": data["calculation_type"]},
            )
            flash("Commission rule created.", "success")
            return redirect(url_for("admin_commission_rules"))
    return render_template(
        "admin_commission_rules.html", rules=all_commission_rules(), form_data=form_data, errors=errors,
        calculation_types=COMMISSION_CALCULATION_TYPES, calculation_labels=COMMISSION_CALCULATION_LABELS,
        scope_types=COMMISSION_SCOPE_TYPES, scope_labels=COMMISSION_SCOPE_LABELS,
        partners=sorted(all_partners(), key=lambda item: str(item.get("full_name") or "").casefold()),
        properties=dashboard_listings(),
    ), (400 if errors else 200)


@app.post("/dashboard/commission-rules/<rule_id>/status")
@permission_required("commissions.manage")
def update_commission_rule_status(rule_id: str):
    rule = fetch_commission_rule(rule_id)
    if rule is None:
        abort(404)
    active = request.form.get("active", "") == "1"
    save_commission_rule(
        {
            key: rule[key] for key in (
                "name", "calculation_type", "percentage_bps", "fixed_amount_minor", "scope_type",
                "property_id", "property_title", "campaign_id", "partner_id", "valid_from", "valid_until", "priority",
            )
        } | {"active": 1 if active else 0},
        created_by=str(rule.get("created_by") or ""), rule_id=rule_id,
    )
    create_activity_record(
        entity_type="commission_rule", entity_id=rule_id, action="activated" if active else "deactivated",
        summary=f"Commission rule {rule['name']} was {'activated' if active else 'deactivated'}.",
    )
    flash(f"Rule {'activated' if active else 'deactivated'}.", "success")
    return redirect(url_for("admin_commission_rules"))


@app.post("/dashboard/commissions/<commission_id>/adjust")
@permission_required("commissions.manage")
def adjust_commission(commission_id: str):
    commission = fetch_commission(commission_id)
    if commission is None:
        abort(404)
    if commission["status"] not in {"POTENTIAL", "PENDING", "EARNED"}:
        flash("Only potential, pending, or earned commissions can be adjusted.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    reason = request.form.get("reason", "").strip()
    if len(reason) < 5 or len(reason) > 500:
        flash("Provide an adjustment reason between 5 and 500 characters.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    try:
        adjustment_minor = signed_money_to_minor(request.form.get("adjustment"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    final_amount = int(commission["calculated_amount_minor"]) + adjustment_minor
    if final_amount <= 0 or final_amount > int(commission["sale_value_minor"]):
        flash("Adjusted commission must remain above zero and cannot exceed the sale value.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    update_commission_fields(
        commission_id, adjustment_minor=adjustment_minor, final_amount_minor=final_amount,
        adjustment_reason=reason,
    )
    create_activity_record(
        entity_type="commission", entity_id=commission_id, action="adjusted",
        summary=f"Commission adjusted for deal {commission['customer_reference']}.",
        metadata={
            "previous_adjustment_minor": commission["adjustment_minor"], "adjustment_minor": adjustment_minor,
            "previous_amount_minor": commission["final_amount_minor"], "amount_minor": final_amount, "reason": reason,
        },
    )
    flash("Commission adjustment recorded.", "success")
    return redirect(url_for("admin_commission_detail", commission_id=commission_id))


@app.post("/dashboard/commissions/<commission_id>/decision")
@permission_required("commissions.approve")
def decide_commission(commission_id: str):
    commission = fetch_commission(commission_id)
    if commission is None:
        abort(404)
    decision = request.form.get("decision", "").strip().upper()
    reason = request.form.get("reason", "").strip()
    if commission["status"] != "EARNED" or decision not in {"APPROVED", "REJECTED"}:
        flash("Only an earned commission can be approved or rejected.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    if decision == "REJECTED" and (len(reason) < 5 or len(reason) > 500):
        flash("Provide a rejection reason between 5 and 500 characters.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    staff = current_staff()
    assert staff is not None
    now = utc_now_iso()
    if decision == "APPROVED":
        update_commission_fields(commission_id, status="APPROVED", approved_by=str(staff["id"]), approved_at=now)
    else:
        update_commission_fields(
            commission_id, status="REJECTED", rejected_by=str(staff["id"]), rejected_at=now,
            rejection_reason=reason,
        )
    create_activity_record(
        entity_type="commission", entity_id=commission_id,
        action="approved" if decision == "APPROVED" else "rejected",
        summary=f"Commission {decision.lower()} for deal {commission['customer_reference']}.",
        metadata={"previous_status": "EARNED", "status": decision, "reason": reason},
    )
    flash(f"Commission {decision.lower()}.", "success")
    return redirect(url_for("admin_commission_detail", commission_id=commission_id))


@app.post("/dashboard/commissions/<commission_id>/paid")
@permission_required("commissions.mark_paid")
def mark_commission_paid(commission_id: str):
    commission = fetch_commission(commission_id)
    if commission is None:
        abort(404)
    if commission["status"] != "APPROVED":
        flash("Only an approved commission can be marked paid.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    payment_reference = request.form.get("payment_reference", "").strip()
    payment_note = request.form.get("payment_note", "").strip()
    paid_on = request.form.get("paid_on", "").strip()
    try:
        paid_date = date.fromisoformat(paid_on)
    except ValueError:
        paid_date = None
    if not payment_reference or len(payment_reference) > 100:
        flash("Provide a payment reference of no more than 100 characters.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    if paid_date is None or paid_date > date.today():
        flash("Payment date must be today or an earlier valid date.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    if len(payment_note) > 500:
        flash("Payment note must not exceed 500 characters.", "error")
        return redirect(url_for("admin_commission_detail", commission_id=commission_id))
    staff = current_staff()
    assert staff is not None
    update_commission_fields(
        commission_id, status="PAID", paid_by=str(staff["id"]), paid_at=paid_on,
        payment_reference=payment_reference, payment_note=payment_note,
    )
    create_activity_record(
        entity_type="commission", entity_id=commission_id, action="paid",
        summary=f"Commission payout recorded for deal {commission['customer_reference']}.",
        metadata={"previous_status": "APPROVED", "status": "PAID", "payment_reference": payment_reference},
    )
    flash("Payout record saved. No bank transfer was initiated by this system.", "success")
    return redirect(url_for("admin_commission_detail", commission_id=commission_id))


@app.get("/dashboard/partners")
@permission_required("partners.view")
def admin_partners():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip().upper()
    if status not in PARTNER_STATUSES:
        status = ""
    all_records = all_partners()
    records = [
        partner for partner in all_records
        if (not status or partner["status"] == status)
        and record_matches_query(
            query, partner.get("full_name"), partner.get("email"), partner.get("phone"),
            partner.get("whatsapp"), partner.get("location"), partner.get("company_name"), partner.get("partner_code"),
        )
    ]
    counts = {option: sum(1 for partner in all_records if partner["status"] == option) for option in PARTNER_STATUSES}
    return render_template(
        "admin_partners.html", partners=records, partner_total=len(all_records), partner_counts=counts,
        partner_statuses=PARTNER_STATUSES, partner_status_labels=PARTNER_STATUS_LABELS,
        filters={"q": query, "status": status},
    )


@app.get("/dashboard/partners/<partner_id>")
@permission_required("partners.view")
def admin_partner_detail(partner_id: str):
    partner = fetch_partner(partner_id)
    if partner is None:
        abort(404)
    attributed_leads = leads_for_partner(partner_id)
    return render_template(
        "admin_partner_detail.html", partner=partner_record_for_template(partner),
        partner_leads=attributed_leads, partner_referrals=referrals_for_partner(partner_id),
        partner_activity=activity_for_entity("partner", partner_id),
        partner_statuses=PARTNER_STATUSES, partner_status_labels=PARTNER_STATUS_LABELS,
    )


@app.post("/dashboard/partners/<partner_id>/status")
@permission_required("partners.approve")
def review_partner(partner_id: str):
    partner = fetch_partner(partner_id)
    if partner is None:
        abort(404)
    next_status = request.form.get("status", "").strip().upper()
    review_note = request.form.get("review_note", "").strip()
    allowed_transitions = {
        "PENDING": {"APPROVED", "REJECTED"},
        "APPROVED": {"SUSPENDED"},
        "SUSPENDED": {"APPROVED", "REJECTED"},
        "REJECTED": {"PENDING", "APPROVED"},
    }
    if next_status not in allowed_transitions.get(str(partner["status"]), set()):
        flash("That partner status transition is not allowed.", "error")
        return redirect(url_for("admin_partner_detail", partner_id=partner_id))
    if len(review_note) > 1000:
        flash("Review notes must not exceed 1,000 characters.", "error")
        return redirect(url_for("admin_partner_detail", partner_id=partner_id))
    reviewer = current_staff()
    assert reviewer is not None
    update_partner_status(partner_id, status=next_status, review_note=review_note, reviewed_by=str(reviewer["id"]))
    create_activity_record(
        entity_type="partner", entity_id=partner_id, action="status_changed",
        summary=f"Partner {partner['full_name']} moved from {partner['status_label'].lower()} to {PARTNER_STATUS_LABELS[next_status].lower()}.",
        metadata={"previous_status": partner["status"], "status": next_status, "review_note": review_note},
    )
    updated_partner = fetch_partner(partner_id)
    if updated_partner:
        send_partner_notification(updated_partner, audience="partner", event=PARTNER_STATUS_LABELS[next_status].lower())
    flash(f"Partner status updated to {PARTNER_STATUS_LABELS[next_status].lower()}.", "success")
    return redirect(url_for("admin_partner_detail", partner_id=partner_id))


@app.post("/dashboard/inspections/<inspection_id>/update")
@permission_required("inspections.manage")
def update_inspection(inspection_id: str):
    inspection = fetch_inspection(inspection_id)
    status = request.form.get("status", "").strip().upper()
    requested_date = request.form.get("requested_date", "").strip()
    requested_time = request.form.get("requested_time", "").strip()
    assigned_staff_id = request.form.get("assigned_staff_id", "").strip()
    internal_note = request.form.get("internal_note", "").strip()
    if status not in INSPECTION_STATUSES:
        flash("Choose a valid inspection status.", "error")
        return redirect(url_for("admin_inspections"))
    try:
        date.fromisoformat(requested_date)
    except ValueError:
        flash("Choose a valid inspection date.", "error")
        return redirect(url_for("admin_inspections"))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", requested_time):
        flash("Choose a valid inspection time.", "error")
        return redirect(url_for("admin_inspections"))
    assignable = {str(staff["id"]): staff for staff in active_staff_with_permission("inspections.manage")}
    assigned_staff = assignable.get(assigned_staff_id) if assigned_staff_id else None
    if assigned_staff_id and assigned_staff is None:
        flash("Choose an active inspection owner.", "error")
        return redirect(url_for("admin_inspections"))
    assigned_to = str(assigned_staff["full_name"]) if assigned_staff else ""
    update_inspection_record(
        inspection_id, status=status, requested_date=requested_date, requested_time=requested_time,
        assigned_staff_id=assigned_staff_id, assigned_to=assigned_to, internal_note=internal_note,
    )
    advance_lead_for_inspection(str(inspection["lead_id"]), status)
    create_activity_record(
        entity_type="inspection", entity_id=inspection_id, action="updated",
        summary=f"Inspection for {inspection['listing_title']} moved to {INSPECTION_STATUS_LABELS[status].lower()}.",
        metadata={"previous_status": inspection["status"], "status": status, "lead_id": inspection["lead_id"]},
    )
    if status in {"CONFIRMED", "RESCHEDULED", "COMPLETED", "CANCELLED"}:
        send_inspection_update_email(fetch_inspection(inspection_id), event=INSPECTION_STATUS_LABELS[status].lower())
    flash("Inspection updated.", "success")
    return redirect(url_for("admin_inspections"))


@app.route("/dashboard/maintenance")
@permission_required("maintenance.view")
def admin_maintenance():
    filters = maintenance_filters_from_request()
    all_records = all_maintenance_tickets()
    records = query_admin_maintenance(filters)
    active_filter_labels: list[str] = []
    if filters.get("q"):
        active_filter_labels.append(f'Search: "{filters["q"]}"')
    if filters.get("status"):
        active_filter_labels.append(str(filters["status"]))
    if filters.get("priority"):
        active_filter_labels.append(str(filters["priority"]))
    if filters.get("assigned_manager"):
        active_filter_labels.append(f"Owner: {filters['assigned_manager']}")
    return render_template(
        "admin_maintenance.html",
        maintenance_tickets=records,
        maintenance_filters=filters,
        maintenance_status_options=MAINTENANCE_STATUS_OPTIONS,
        maintenance_priority_options=MAINTENANCE_PRIORITY_OPTIONS,
        maintenance_sort_options=MAINTENANCE_SORT_OPTIONS,
        maintenance_total=len(all_records),
        maintenance_summary=maintenance_management_summary(all_records),
        maintenance_managers=distinct_record_values(all_records, "assigned_manager"),
        active_filter_labels=active_filter_labels,
    )


@app.route("/dashboard/finance")
@permission_required("finance.view")
def admin_finance():
    filters = finance_filters_from_request()
    all_records = all_financial_records()
    records = query_admin_financial_records(filters)
    active_filter_labels: list[str] = []
    if filters.get("q"):
        active_filter_labels.append(f'Search: "{filters["q"]}"')
    if filters.get("status"):
        active_filter_labels.append(str(filters["status"]))
    if filters.get("charge_type"):
        active_filter_labels.append(str(filters["charge_type"]))
    if filters.get("assigned_to"):
        active_filter_labels.append(f"Owner: {filters['assigned_to']}")
    return render_template(
        "admin_finance.html",
        financial_records=records,
        finance_filters=filters,
        financial_status_options=FINANCIAL_STATUS_OPTIONS,
        financial_charge_options=FINANCIAL_CHARGE_OPTIONS,
        financial_sort_options=FINANCIAL_SORT_OPTIONS,
        finance_total=len(all_records),
        finance_summary=finance_management_summary(all_records),
        finance_assignees=distinct_record_values(all_records, "assigned_to"),
        active_filter_labels=active_filter_labels,
    )


@app.route("/dashboard/documents")
@permission_required("documents.view")
def admin_documents():
    filters = document_filters_from_request()
    all_records = all_documents()
    records = query_admin_documents(filters)
    active_filter_labels: list[str] = []
    if filters.get("q"):
        active_filter_labels.append(f'Search: "{filters["q"]}"')
    if filters.get("document_type"):
        active_filter_labels.append(str(filters["document_type"]))
    if filters.get("source_kind"):
        active_filter_labels.append("Generated" if filters["source_kind"] == "generated" else "Uploaded")
    if filters.get("document_status"):
        active_filter_labels.append(f"Status: {filters['document_status']}")
    return render_template(
        "admin_documents.html",
        documents=records,
        document_filters=filters,
        document_type_options=DOCUMENT_TYPE_OPTIONS,
        document_source_options=DOCUMENT_SOURCE_OPTIONS,
        document_status_options=DOCUMENT_STATUS_OPTIONS,
        document_sort_options=DOCUMENT_SORT_OPTIONS,
        document_total=len(all_records),
        document_summary=document_management_summary(all_records),
        active_filter_labels=active_filter_labels,
    )


@app.get("/dashboard/documents/generator-spec.json")
@permission_required("documents.manage")
def document_generator_spec():
    return jsonify(generator_spec(site_settings()))


@app.post("/dashboard/documents/preview")
@permission_required("documents.manage")
def preview_generated_document_pdf():
    settings = site_settings()
    form_data, payload_data, errors, _guided_form_data = validate_document_generation_form(request.form, settings)
    selected_template = form_data.get("template_key", "")
    if errors:
        return jsonify({"errors": errors}), 400

    temp_path = DOCUMENTS_DIR / f"preview-{uuid.uuid4().hex}.pdf"
    try:
        preview_payload = dict(payload_data)
        preview_payload["document_status"] = "Preview"
        preview_payload["generated_at"] = utc_now_iso()
        render_document_pdf(selected_template, form_data["title"], preview_payload, temp_path, settings)
        pdf_bytes = temp_path.read_bytes()
    finally:
        if temp_path.exists():
            temp_path.unlink()

    download_name = f"{secure_filename(form_data['title']) or 'document-preview'}-preview.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=download_name,
        max_age=0,
    )


@app.route("/dashboard/documents/generate", methods=["GET", "POST"])
@permission_required("documents.manage")
def generate_document_pdf():
    settings = site_settings()
    template_library = document_generator_catalog(settings)
    template_choices = template_options(settings)
    source_document = None
    source_payload: dict[str, object] | None = None
    if request.method == "GET" and request.args.get("source_document_id", "").strip():
        source_document = fetch_document_record(request.args["source_document_id"].strip())
        source_template = str(source_document.get("template_key") or "").strip()
        candidate_payload = source_document.get("payload_data")
        if source_document.get("source_kind") != "generated" or source_template not in template_library or not isinstance(candidate_payload, dict):
            abort(400, description="This document cannot be reused from the generator.")
        selected_template = source_template
        source_payload = candidate_payload
    else:
        selected_template = (
            request.form.get("template_key", "").strip()
            if request.method == "POST"
            else request.args.get("template_key", "").strip()
        )
    if selected_template not in template_library:
        selected_template = "billing" if "billing" in template_library else template_choices[0][0]
    guided_template = guided_document_blueprint(selected_template)
    guided_form_data = guided_form_data_from_payload(
        selected_template,
        source_payload or template_library[selected_template].get("sample_payload", {}),
        settings,
    )

    form_data = {
        "template_key": selected_template,
        "title": f"Copy of {source_document['title']}" if source_document else f"{template_library[selected_template]['label']} - {settings['site_name']}",
        "resident_name": source_document.get("resident_name", "") if source_document else "",
        "unit_reference": source_document.get("unit_reference", "") if source_document else "",
        "property_title": source_document.get("property_title", "") if source_document else "",
        "note": source_document.get("note", "") if source_document else "",
        "payload_json": json.dumps(source_payload, indent=2, ensure_ascii=False) if source_payload else sample_payload_json(selected_template, settings),
        "use_advanced_payload": "1" if source_document and not guided_template else "",
    }

    if request.method == "POST":
        form_data, payload_data, errors, guided_form_data = validate_document_generation_form(request.form, settings)
        selected_template = form_data.get("template_key") or selected_template
        guided_template = guided_document_blueprint(selected_template)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            temp_path = DOCUMENTS_DIR / f"tmp-{uuid.uuid4().hex}.pdf"
            try:
                payload_data["document_status"] = "Final"
                payload_data["generated_at"] = utc_now_iso()
                render_document_pdf(selected_template, form_data["title"], payload_data, temp_path, settings)
                upload_meta = save_generated_document_pdf(form_data["title"], temp_path)
            finally:
                if temp_path.exists():
                    temp_path.unlink()

            now = utc_now_iso()
            record_form_data = {
                key: value
                for key, value in form_data.items()
                if key not in {"payload_json", "use_advanced_payload"}
            }
            record_payload: dict[str, object] = {
                **record_form_data,
                **upload_meta,
                "document_type": template_document_type(selected_template, settings),
                "document_status": "Final",
                "source_kind": "generated",
                "template_key": selected_template,
                "template_version": DOCUMENT_TEMPLATE_VERSION,
                "payload_json": payload_data,
                "created_at": now,
                "updated_at": now,
            }
            document_id = create_document_record(record_payload)
            create_activity_record(
                entity_type="document",
                entity_id=document_id,
                action="generated",
                summary=f"Created {template_library[selected_template]['label'].lower()}: {form_data['title']}.",
                actor_label="Admin",
            )
            flash("PDF created and saved to documents.", "success")
            return redirect(url_for("admin_documents"))

    return render_template(
        "document_generator.html",
        page_title="Generate PDF Document",
        form_data=form_data,
        template_choices=template_choices,
        selected_template=selected_template,
        guided_template=guided_template,
        guided_form_data=guided_form_data,
        show_advanced_payload=bool(form_data.get("use_advanced_payload")),
        active_template=template_library[selected_template],
        generator_spec=generator_spec(settings),
        source_document=source_document,
        back_url=url_for("admin_documents"),
    )


@app.route("/dashboard/settings", methods=["GET", "POST"])
@permission_required("settings.manage")
def admin_settings():
    form_data = site_settings_defaults()
    form_data.update(persisted_site_settings())

    if request.method == "POST":
        form_data, errors = validate_site_settings_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            update_site_settings(form_data)
            create_activity_record(
                entity_type="site_settings",
                entity_id="site_preferences",
                action="updated",
                summary="Site settings updated from the admin workspace.",
                actor_label="Admin",
            )
            flash("Site settings updated.", "success")
            return redirect(url_for("admin_settings"))

    return render_template("admin_settings.html", form_data=form_data)


@app.get("/dashboard/settings/communications")
@permission_required("settings.manage")
def communication_preview():
    settings = site_settings()
    base_url = request.url_root.rstrip("/")
    template_choices = communication_template_choices(settings, base_url)
    selected_template = request.args.get("template_key", "").strip()
    valid_keys = {value for value, _label in template_choices}
    if selected_template not in valid_keys:
        selected_template = template_choices[0][0]

    payload = communication_sample_payload(selected_template, settings, base_url)
    rendered = render_communication_template(selected_template, payload, settings, base_url=base_url)
    return render_template(
        "communication_preview.html",
        page_title="Communication Preview",
        template_choices=template_choices,
        selected_template=selected_template,
        rendered=rendered,
        payload_json=json.dumps(payload, indent=2),
    )


@app.get("/dashboard/settings/communications/frame/<template_key>")
@permission_required("settings.manage")
def communication_preview_frame(template_key: str):
    settings = site_settings()
    base_url = request.url_root.rstrip("/")
    try:
        payload = communication_sample_payload(template_key, settings, base_url)
        rendered = render_communication_template(template_key, payload, settings, base_url=base_url)
    except KeyError:
        abort(404)

    response = app.response_class(rendered["html"], mimetype="text/html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/dashboard/team")
@permission_required("staff.view")
def admin_team():
    return render_template(
        "admin_team.html",
        staff_members=all_staff_users(),
        invitations=pending_staff_invitations(),
        role_options=ROLE_OPTIONS,
        staff_status_options=STAFF_STATUS_OPTIONS,
        permission_matrix={role: sorted(permissions_for_role(role)) for role in ROLE_OPTIONS},
        new_invitation_url=session.pop("staff_invitation_url", ""),
    )


@app.get("/dashboard/audit")
@permission_required("audit_logs.view")
def admin_audit_log():
    filters = {
        "q": request.args.get("q", "").strip(),
        "entity_type": request.args.get("entity_type", "").strip(),
        "actor_type": request.args.get("actor_type", "").strip(),
    }
    records = query_activity_records(
        query=filters["q"],
        entity_type=filters["entity_type"],
        actor_type=filters["actor_type"],
        limit=200,
    )
    return render_template("admin_audit.html", records=records, filters=filters)


@app.post("/dashboard/team/invite")
@permission_required("staff.invite")
def invite_staff():
    full_name = " ".join(request.form.get("full_name", "").split())
    email = normalize_staff_email(request.form.get("email", ""))
    role = request.form.get("role", "").strip().upper()
    errors = validate_staff_identity(full_name, email)
    if role not in ROLE_OPTIONS:
        errors.append("Choose a valid staff role.")
    if staff_identity_exists(email=email):
        errors.append("A staff account already uses that email address.")
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("admin_team"))

    inviter = current_staff()
    invitation_id, token = create_staff_invitation(
        full_name=full_name,
        email=email,
        role=role,
        invited_by=str(inviter["id"]),
    )
    invitation_url = url_for("accept_staff_invitation", token=token, _external=True)
    delivery = send_staff_invitation_email(
        full_name=full_name,
        email=email,
        role=role,
        invitation_url=invitation_url,
    )
    session["staff_invitation_url"] = invitation_url
    create_activity_record(
        entity_type="staff_invitation",
        entity_id=invitation_id,
        action="created",
        summary=f"Invited {full_name} as {role_label(role)}.",
        metadata={"email": email, "role": role, "email_sent": bool(delivery.get("sent"))},
    )
    if delivery.get("sent"):
        flash(f"Invitation sent to {email}.", "success")
    else:
        flash(
            "The invitation was created, but email delivery failed. Copy the one-time link shown below.",
            "error",
        )
    return redirect(url_for("admin_team"))


@app.post("/dashboard/team/<user_id>/update")
@permission_required("staff.edit")
def update_staff_member(user_id: str):
    target = fetch_staff_user(user_id)
    if target is None:
        abort(404)
    actor = current_staff()
    full_name = " ".join(request.form.get("full_name", "").split())
    role = request.form.get("role", "").strip().upper()
    status = request.form.get("status", "").strip().upper()
    errors = validate_staff_identity(full_name, str(target["email"]), str(target["username"]))
    if role not in ROLE_OPTIONS:
        errors.append("Choose a valid staff role.")
    if status not in STAFF_STATUS_OPTIONS:
        errors.append("Choose a valid staff status.")
    if status != target["status"] and not has_permission("staff.disable"):
        abort(403)
    if actor and actor["id"] == target["id"] and (
        role != target["role"] or status != target["status"]
    ):
        errors.append("You cannot change your own role or disable your own account.")
    removing_last_super_admin = (
        target["role"] == "SUPER_ADMIN"
        and target["status"] == "ACTIVE"
        and (role != "SUPER_ADMIN" or status != "ACTIVE")
        and active_super_admin_count() <= 1
    )
    if removing_last_super_admin:
        errors.append("At least one active super admin must remain.")
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("admin_team"))

    before = {"full_name": target["full_name"], "role": target["role"], "status": target["status"]}
    update_staff_access(user_id, role=role, status=status, full_name=full_name)
    create_activity_record(
        entity_type="staff_user",
        entity_id=user_id,
        action="access_updated",
        summary=f"Updated access for {full_name}: {role_label(role)}, {status.lower()}.",
        metadata={"before": before, "after": {"full_name": full_name, "role": role, "status": status}},
    )
    flash("Staff access updated.", "success")
    return redirect(url_for("admin_team"))


@app.post("/dashboard/team/invitations/<invitation_id>/revoke")
@permission_required("staff.invite")
def revoke_staff_invitation(invitation_id: str):
    invitation = fetch_staff_invitation(invitation_id)
    if invitation is None:
        abort(404)
    if invitation["status"] == "PENDING":
        update_staff_invitation_status(invitation_id, "REVOKED")
        create_activity_record(
            entity_type="staff_invitation",
            entity_id=invitation_id,
            action="revoked",
            summary=f"Revoked the staff invitation for {invitation['email']}.",
            metadata={"email": invitation["email"], "role": invitation["role"]},
        )
    flash("Invitation revoked.", "success")
    return redirect(url_for("admin_team"))


@app.route("/staff/accept/<token>", methods=["GET", "POST"])
def accept_staff_invitation(token: str):
    invitation = fetch_staff_invitation_by_token(token)
    if invitation is None or not invitation_is_active(invitation):
        return render_template("staff_accept_invitation.html", invitation=None, form_data={}), 410

    default_username = re.sub(r"[^a-z0-9._-]", "", invitation["email"].split("@", 1)[0].lower())
    if len(default_username) < 3:
        default_username = "staff"
    form_data = {"username": default_username}
    errors: list[str] = []
    if request.method == "POST":
        form_data["username"] = normalize_username(request.form.get("username", ""))
        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")
        errors.extend(
            validate_staff_identity(
                str(invitation["full_name"]),
                str(invitation["email"]),
                form_data["username"],
            )
        )
        errors.extend(
            validate_password(
                password,
                personal_values=(
                    str(invitation["full_name"]),
                    str(invitation["email"]),
                    form_data["username"],
                ),
            )
        )
        if password != password_confirmation:
            errors.append("Password confirmation does not match.")
        if staff_identity_exists(username=form_data["username"], email=str(invitation["email"])):
            errors.append("That username or email address is already in use.")

        if not errors:
            try:
                user_id = create_staff_user(
                    full_name=str(invitation["full_name"]),
                    email=str(invitation["email"]),
                    username=form_data["username"],
                    role=str(invitation["role"]),
                    password_hash=hash_password(password),
                    created_by=str(invitation["invited_by"]),
                )
            except ValueError as exc:
                errors.append(str(exc))
            else:
                update_staff_invitation_status(str(invitation["id"]), "ACCEPTED", accepted_by=user_id)
                session.clear()
                session["staff_user_id"] = user_id
                session["staff_role"] = str(invitation["role"])
                session["staff_name"] = str(invitation["full_name"])
                session.permanent = True
                update_staff_last_login(user_id)
                create_activity_record(
                    entity_type="staff_user",
                    entity_id=user_id,
                    action="invitation_accepted",
                    summary=f"{invitation['full_name']} activated their staff account.",
                )
                flash("Your staff account is ready.", "success")
                return redirect(url_for("dashboard"))

    return render_template(
        "staff_accept_invitation.html",
        invitation=invitation,
        form_data=form_data,
        errors=errors,
    ), (400 if errors else 200)


@app.route("/tenant-services", methods=["GET", "POST"])
def tenant_services():
    form_data = maintenance_form_defaults()
    field_errors: dict[str, list[str]] = {}
    submission_receipt = session.pop("tenant_service_receipt", None)

    if request.method == "POST":
        form_data, field_errors = validate_maintenance_form(request.form)

        if not field_errors:
            try:
                issue_image = normalize_uploaded_image(request.files.get("issue_image"))
                form_data["image_path"] = issue_image or ""
            except ValueError as error:
                field_errors.setdefault("issue_image", []).append(str(error))

        if field_errors:
            flash("Check the highlighted fields and try again.", "error")
        else:
            now = utc_now_iso()
            form_data["status"] = "New"
            form_data["created_at"] = now
            form_data["updated_at"] = now
            form_data["assigned_vendor"] = ""
            ticket_id = create_maintenance_ticket_record(form_data)
            ticket_reference = maintenance_ticket_reference(ticket_id)
            contact_lines = [value for value in [form_data["phone"], form_data["email"]] if value]
            session["tenant_service_receipt"] = {
                "ticket_reference": ticket_reference,
                "issue_category": form_data["issue_category"],
                "priority": form_data["priority"],
                "unit_reference": form_data["unit_reference"],
                "property_title": form_data["property_title"],
                "contact_line": " / ".join(contact_lines),
                "response_window": maintenance_response_window(form_data["priority"]),
                "is_emergency": form_data["priority"] == "Emergency",
            }
            create_activity_record(
                entity_type="maintenance_ticket",
                entity_id=ticket_id,
                action="created",
                summary=f"Maintenance ticket logged for {form_data['unit_reference']}.",
                actor_label="Tenant",
            )
            flash(
                f"Maintenance request {ticket_reference} submitted. The operations team will review it shortly.",
                "success",
            )
            return redirect(url_for("tenant_services"))

    return render_template(
        "tenant_services.html",
        form_data=form_data,
        field_errors=field_errors,
        submission_receipt=submission_receipt,
    )


@app.post("/dashboard/enquiries/<enquiry_id>/status")
@permission_required("leads.manage")
def update_enquiry(enquiry_id: str):
    enquiry = fetch_enquiry(enquiry_id)
    next_url = admin_return_target("admin_enquiries")
    next_status = request.form.get("status", "").strip()
    assigned_staff_id = request.form.get("assigned_staff_id", "").strip()
    source = request.form.get("source", str(enquiry.get("source") or "WEBSITE")).strip().upper()
    campaign_id = request.form.get("campaign_id", str(enquiry.get("campaign_id") or "")).strip()
    estimated_value, estimated_value_error = safe_int(
        request.form.get("estimated_value", ""), "Estimated value", minimum=0
    )
    assignable = {str(staff["id"]): staff for staff in active_staff_with_permission("leads.manage")}
    assigned_staff = assignable.get(assigned_staff_id) if assigned_staff_id else None
    assigned_to = str(assigned_staff["full_name"]) if assigned_staff else ""
    internal_note = request.form.get("internal_note", "").strip()
    follow_up_on, follow_up_error = normalize_optional_date(
        request.form.get("follow_up_on", ""),
        "Follow-up date",
    )
    if next_status not in ENQUIRY_STATUS_OPTIONS:
        flash("Choose a valid lead stage.", "error")
        return redirect(next_url)
    if assigned_staff_id and assigned_staff is None:
        flash("Choose an active sales owner.", "error")
        return redirect(next_url)
    if source not in LEAD_SOURCES:
        flash("Choose a valid lead source.", "error")
        return redirect(next_url)
    if campaign_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", campaign_id):
        flash("Campaign identifier may use letters, numbers, dots, underscores, and hyphens.", "error")
        return redirect(next_url)
    if estimated_value_error:
        flash(estimated_value_error, "error")
        return redirect(next_url)
    if int(estimated_value or 0) > 1_000_000_000_000_000:
        flash("Estimated value exceeds the supported monetary limit.", "error")
        return redirect(next_url)
    if follow_up_error:
        flash(follow_up_error, "error")
        return redirect(next_url)

    update_enquiry_record(
        enquiry_id,
        status=next_status,
        assigned_to=assigned_to,
        assigned_staff_id=assigned_staff_id,
        source=source,
        campaign_id=campaign_id,
        estimated_value=int(estimated_value or 0),
        internal_note=internal_note,
        follow_up_on=follow_up_on,
    )
    record_referral_lead_lifecycle(
        str(enquiry.get("referral_id") or ""),
        enquiry_id,
        str(enquiry.get("status") or ""),
        next_status,
    )
    commission = sync_commission_for_lead(enquiry_id)
    if (
        target_status_for_lead_stage(next_status) in {"POTENTIAL", "PENDING", "EARNED"}
        and enquiry.get("partner_id") and enquiry.get("referral_id") and commission is None
    ):
        flash(
            "This attributed deal has no commission yet. Add a positive estimated value and an active matching rule.",
            "warning",
        )
    create_activity_record(
        entity_type="enquiry",
        entity_id=enquiry_id,
        action="updated",
        summary=f"Lead from {enquiry['name']} moved to {lead_stage_label(next_status).lower()}.",
        actor_label="Admin",
        metadata={
            "previous_status": enquiry["status"], "status": next_status,
            "assigned_staff_id": assigned_staff_id, "source": source,
        },
    )
    flash("Lead updated.", "success")
    return redirect(next_url)


@app.post("/inspections")
def submit_inspection():
    next_url = safe_redirect_target(request.form.get("source_path") or request.referrer or url_for("properties"))
    listing_id = request.form.get("listing_id", "").strip()
    listing = fetch_listing(listing_id) if listing_id else None
    if listing is None:
        abort(404)
    inspection_data, errors = validate_inspection_request(
        request.form, listing_id=str(listing["id"]), listing_title=str(listing["title"])
    )
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(f"{next_url}#property-inspection")

    contact_id = get_or_create_contact(
        name=inspection_data["name"], email=inspection_data["email"], phone=inspection_data["phone"],
        whatsapp=inspection_data["phone"],
    )
    lead = find_open_lead(contact_id, str(listing["id"]))
    if lead is None:
        lead_id = create_enquiry_record({
            "listing_id": str(listing["id"]), "listing_title": str(listing["title"]),
            "name": inspection_data["name"], "email": inspection_data["email"],
            "phone": inspection_data["phone"], "whatsapp": inspection_data["phone"],
            "preferred_contact": "Phone" if inspection_data["phone"] else "Email",
            "message": inspection_data["notes"] or "Requested a property inspection.",
            "source_path": inspection_data["source_path"], "source": "WEBSITE_INSPECTION",
            "contact_id": contact_id,
        })
        create_activity_record(
            entity_type="enquiry", entity_id=lead_id, action="created",
            summary=f"Inspection request created a lead for {inspection_data['name']}.", actor_label="Public inspection",
        )
    else:
        lead_id = str(lead["id"])

    attach_referral_to_lead(lead_id, str(listing["id"]))
    attributed_lead = fetch_enquiry(lead_id)
    referral_id = str(attributed_lead.get("referral_id") or "")
    partner_id = str(attributed_lead.get("partner_id") or "")
    inspection_id = create_inspection_record({
        **inspection_data,
        "lead_id": lead_id,
        "contact_id": contact_id,
        "partner_id": partner_id,
        "referral_id": referral_id,
    })
    if referral_id:
        attach_inspection_to_referral(referral_id, inspection_id, lead_id)
    create_activity_record(
        entity_type="inspection", entity_id=inspection_id, action="requested",
        summary=f"Inspection requested for {listing['title']} on {inspection_data['requested_date']} at {inspection_data['requested_time']}.",
        actor_label="Public inspection",
        metadata={"lead_id": lead_id, "referral_id": referral_id, "partner_id": partner_id},
    )
    create_activity_record(
        entity_type="enquiry", entity_id=lead_id, action="inspection_requested",
        summary=f"Inspection requested for {inspection_data['requested_date']} at {inspection_data['requested_time']}.",
        actor_label="Public inspection", metadata={"inspection_id": inspection_id},
    )
    send_inspection_update_email(fetch_inspection(inspection_id), event="request received")
    flash("Inspection request received. The team will confirm the date and time with you.", "success")
    return redirect(f"{next_url}#property-inspection")


def partner_safe_next(target: str | None) -> str:
    cleaned = safe_redirect_target(target)
    return cleaned if cleaned == "/partner" or cleaned.startswith("/partner/") else url_for("partner_dashboard")


@app.route("/partners/register", methods=["GET", "POST"])
def partner_register():
    if current_partner() is not None:
        return redirect(url_for("partner_dashboard") if is_partner_authenticated() else url_for("partner_application_status"))
    form_data = {
        "full_name": "", "email": "", "phone": "", "whatsapp": "", "location": "",
        "partner_type": "INDIVIDUAL", "company_name": "", "experience_notes": "", "referral_source": "",
    }
    errors: list[str] = []
    if request.method == "POST":
        if login_is_rate_limited("application", "partner-registration"):
            errors.append("Too many applications were submitted from this connection. Wait a few minutes before trying again.")
            return render_template(
                "partner_register.html", form_data=form_data, errors=errors,
                partner_types=PARTNER_TYPES, partner_type_labels=PARTNER_TYPE_LABELS,
            ), 429
        record_failed_login("application", "partner-registration")
        form_data, errors = validate_partner_registration(request.form)
        password = request.form.get("password", "")
        errors.extend(validate_partner_password(password, request.form.get("password_confirmation", ""), form_data))
        if fetch_partner_by_email(form_data["email"]):
            errors.append("A partner application already exists for that email address.")
        if not errors:
            try:
                partner_id = create_partner(form_data, hash_password(password))
            except ValueError as exc:
                errors.append(str(exc))
            else:
                session.clear()
                session["partner_user_id"] = partner_id
                session.permanent = True
                partner = fetch_partner(partner_id)
                create_activity_record(
                    entity_type="partner", entity_id=partner_id, action="application_submitted",
                    summary=f"Partner application submitted by {form_data['full_name']}.",
                    actor_label=form_data["full_name"], actor_id=partner_id, actor_type="partner",
                    metadata={"partner_code": partner["partner_code"] if partner else ""},
                )
                if partner:
                    send_partner_notification(partner, audience="admin", event="submitted")
                flash("Application received. The team will review your details before activating partner access.", "success")
                return redirect(url_for("partner_application_status"))
        flash("Check the form and correct the highlighted information.", "error")
    return render_template(
        "partner_register.html", form_data=form_data, errors=errors,
        partner_types=PARTNER_TYPES, partner_type_labels=PARTNER_TYPE_LABELS,
    ), (400 if errors else 200)


@app.route("/partners/login", methods=["GET", "POST"])
def partner_login():
    if current_partner() is not None:
        return redirect(url_for("partner_dashboard") if is_partner_authenticated() else url_for("partner_application_status"))
    next_url = partner_safe_next(request.args.get("next") or request.form.get("next"))
    login_error = ""
    email = request.form.get("email", "").strip() if request.method == "POST" else ""
    if request.method == "POST":
        if login_is_rate_limited(email, "partner"):
            login_error = "Too many sign-in attempts. Wait a few minutes before trying again."
        else:
            partner = authenticate_partner(email, request.form.get("password", ""))
            if partner is None:
                record_failed_login(email, "partner")
                login_error = "Incorrect email or password."
            else:
                reset_failed_login(email, "partner")
                session.clear()
                session["partner_user_id"] = str(partner["id"])
                session.permanent = True
                update_partner_last_login(str(partner["id"]))
                create_activity_record(
                    entity_type="partner", entity_id=str(partner["id"]), action="signed_in",
                    summary=f"{partner['full_name']} signed in to the partner portal.",
                    actor_label=str(partner["full_name"]), actor_id=str(partner["id"]), actor_type="partner",
                )
                if partner["status"] != "APPROVED":
                    return redirect(url_for("partner_application_status"))
                flash(f"Welcome back, {partner['full_name']}.", "success")
                return redirect(next_url)
    return render_template("partner_login.html", email=email, next_url=next_url, login_error=login_error), (400 if login_error else 200)


@app.post("/partners/logout")
def partner_logout():
    partner = current_partner()
    if partner:
        create_activity_record(
            entity_type="partner", entity_id=str(partner["id"]), action="signed_out",
            summary=f"{partner['full_name']} signed out of the partner portal.",
            actor_label=str(partner["full_name"]), actor_id=str(partner["id"]), actor_type="partner",
        )
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("partner_login"))


@app.get("/partner/status")
@partner_login_required(approved=False)
def partner_application_status():
    partner = current_partner()
    if partner and partner["status"] == "APPROVED":
        return redirect(url_for("partner_dashboard"))
    return render_template("partner_status.html", partner=partner_record_for_template(partner))


def masked_partner_lead(lead: Mapping[str, object]) -> dict[str, object]:
    name_parts = str(lead.get("name") or "Client").split()
    email = str(lead.get("email") or "")
    phone = normalize_partner_phone(lead.get("phone"))
    return {
        "id": str(lead.get("id") or ""),
        "listing_id": str(lead.get("listing_id") or ""),
        "listing_title": str(lead.get("listing_title") or "Property opportunity"),
        "status": canonical_lead_stage(lead.get("status")),
        "status_label": lead_stage_label(lead.get("status")),
        "name": " ".join(f"{part[0]}***" if part else "" for part in name_parts),
        "email": f"{email[:1]}***@{email.split('@', 1)[1]}" if "@" in email else "",
        "phone": f"***{phone[-4:]}" if phone else "",
        "created_at": str(lead.get("created_at") or ""),
        "updated_at": str(lead.get("updated_at") or ""),
    }


def leads_for_partner(partner_id: str, *, masked: bool = False) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        rows = get_mongo_enquiries_collection().find({"partner_id": partner_id}).sort("created_at", DESCENDING)
    else:
        rows = get_db().execute(
            "SELECT * FROM enquiries WHERE partner_id = ? ORDER BY created_at DESC", (partner_id,)
        ).fetchall()
    records = [normalize_enquiry_record(row) for row in rows]
    return [masked_partner_lead(item) for item in records] if masked else records


def partner_dashboard_context(partner: Mapping[str, object], section: str) -> dict[str, object]:
    partner_id = str(partner["id"])
    needs_leads = section in {"overview", "leads", "deals"}
    needs_properties = section in {"overview", "properties", "links", "materials"}
    needs_referrals = section in {"overview", "links"}
    needs_commissions = section in {"overview", "commissions", "payouts"}
    leads = leads_for_partner(partner_id, masked=True) if needs_leads else []
    referrals = referrals_for_partner(partner_id) if needs_referrals else []
    partner_commissions = commissions_for_partner(partner_id) if needs_commissions else []
    active_deal_stages = {"NEGOTIATION", "DEPOSIT_PAID"}
    published = query_public_listings({
        "status": "", "availability": "", "district": "", "property_type": "", "q": "", "verified_only": "",
        **{key: "" for key, _label in DISCOVERY_FEATURE_FIELDS},
    }) if needs_properties else []
    published = [partner_marketing_listing(listing, partner) for listing in published]
    performance = partner_performance_metrics(partner_id) if section in {"overview", "materials"} else {}
    return {
        "partner": partner_record_for_template(partner), "available_properties": published,
        "partner_leads": leads, "partner_referrals": referrals,
        "partner_commissions": partner_commissions,
        "partner_payouts": [item for item in partner_commissions if item["status"] == "PAID"],
        "performance": performance,
        "partner_deals": [item for item in leads if item.get("status") in active_deal_stages],
        "summary": {
            "available_properties": len(published), "lead_count": len(leads),
            "referral_count": len(referrals),
            "active_deals": sum(1 for item in leads if item.get("status") in active_deal_stages),
            **{
                f"{status.lower()}_commission": sum(
                    item["final_amount"] for item in partner_commissions if item["status"] == status
                )
                for status in ("POTENTIAL", "PENDING", "EARNED", "APPROVED", "PAID")
            },
        },
    }


@app.route("/partner", defaults={"section": "overview"})
@app.route("/partner/<section>", methods=["GET", "POST"])
@partner_login_required()
def partner_dashboard(section: str):
    if section not in PARTNER_SECTIONS:
        abort(404)
    partner = current_partner()
    assert partner is not None
    if request.method == "POST":
        if section != "profile":
            abort(405)
        form_data, errors = validate_partner_registration({**request.form, "email": partner["email"]})
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            update_partner_profile(str(partner["id"]), form_data)
            create_activity_record(
                entity_type="partner", entity_id=str(partner["id"]), action="profile_updated",
                summary=f"{partner['full_name']} updated their partner profile.",
                actor_label=str(partner["full_name"]), actor_id=str(partner["id"]), actor_type="partner",
            )
            flash("Profile updated.", "success")
            return redirect(url_for("partner_dashboard", section="profile"))
    context = partner_dashboard_context(partner, section)
    context.update({"section": section, "partner_sections": PARTNER_SECTIONS, "partner_type_labels": PARTNER_TYPE_LABELS})
    return render_template("partner_dashboard.html", **context)


@app.get("/partner/marketing/<listing_id>")
@partner_login_required()
def partner_marketing_property(listing_id: str):
    partner = current_partner()
    assert partner is not None
    listing = fetch_listing(listing_id)
    if not listing.get("published"):
        abort(404)
    return render_template(
        "partner_marketing_property.html",
        partner=partner_record_for_template(partner),
        listing=partner_marketing_listing(listing, partner),
    )


@app.post("/partner/marketing-events")
@partner_login_required()
def record_partner_marketing_event():
    partner = current_partner()
    assert partner is not None
    listing_id = request.form.get("listing_id", "").strip()
    event_type = normalize_marketing_event_type(request.form.get("event_type"))
    if not event_type:
        return jsonify({"ok": False, "error": "invalid_event"}), 400
    listing = fetch_listing(listing_id)
    if not listing.get("published"):
        abort(404)
    create_partner_marketing_event(
        partner_id=str(partner["id"]), listing_id=str(listing["id"]), event_type=event_type,
    )
    return jsonify({"ok": True, "event": PARTNER_MARKETING_EVENT_LABELS[event_type]}), 201


@app.get("/partner/marketing-assets/<path:asset_id>/download")
@partner_login_required()
def download_partner_marketing_asset(asset_id: str):
    partner = current_partner()
    assert partner is not None
    if asset_id.startswith("primary:"):
        listing_id = asset_id.split(":", 1)[1]
        listing = fetch_listing(listing_id)
        if not listing.get("published"):
            abort(404)
        asset_path = resolved_listing_image_path(listing)
        title = f"{listing['title']} primary image"
        asset_type = "IMAGE"
    else:
        asset = fetch_marketing_asset(asset_id)
        if asset is None:
            abort(404)
        listing = fetch_listing(str(asset["listing_id"]))
        if not listing.get("published"):
            abort(404)
        asset_path = str(asset.get("storage_key") or asset.get("external_url") or "")
        title = str(asset["title"])
        asset_type = str(asset["asset_type"])
    create_partner_marketing_event(
        partner_id=str(partner["id"]), listing_id=str(listing["id"]), event_type="MEDIA_DOWNLOADED",
        metadata={"asset_type": asset_type, "asset_title": title[:120]},
    )
    download_stem = secure_filename(f"{listing['title']}-{title}") or "structurebase-marketing-asset"
    if asset_path.startswith(("https://", "http://")):
        if not asset_path.startswith("https://"):
            abort(404)
        return redirect(asset_path)
    if is_cloudinary_asset(asset_path):
        configure_cloudinary()
        cloud_url = cloudinary_url(
            cloudinary_public_id(asset_path), secure=True, resource_type="image", format="webp",
            flags="attachment",
        )[0]
        return redirect(cloud_url)
    candidate = (STATIC_DIR / asset_path).resolve()
    try:
        candidate.relative_to(STATIC_DIR.resolve())
    except ValueError:
        abort(404)
    if not candidate.is_file():
        abort(404)
    suffix = candidate.suffix.lower() or ".bin"
    return send_file(candidate, as_attachment=True, download_name=f"{download_stem}{suffix}", conditional=True)


@app.post("/dashboard/leads/<lead_id>/notes")
@permission_required("leads.manage")
def add_lead_note(lead_id: str):
    lead = fetch_enquiry(lead_id)
    body = " ".join(request.form.get("body", "").split())
    if len(body) < 2:
        flash("Add a note before saving.", "error")
        return redirect(url_for("admin_lead_detail", lead_id=lead_id))
    if len(body) > 2000:
        flash("Lead notes must not exceed 2,000 characters.", "error")
        return redirect(url_for("admin_lead_detail", lead_id=lead_id))
    create_lead_note(lead_id, body)
    create_activity_record(
        entity_type="enquiry", entity_id=lead_id, action="note_added",
        summary=f"A note was added to {lead['name']}'s lead.",
    )
    flash("Note added.", "success")
    return redirect(url_for("admin_lead_detail", lead_id=lead_id))


@app.post("/dashboard/enquiries/<enquiry_id>/resend-admin-email")
@permission_required("leads.manage")
def resend_enquiry_admin_email(enquiry_id: str):
    next_url = admin_return_target("admin_enquiries")
    enquiry = fetch_enquiry(enquiry_id)
    if not smtp_is_configured():
        flash("SMTP is not configured yet.", "error")
        return redirect(next_url)

    result = send_admin_enquiry_notification(
        enquiry_email_context(enquiry_id, enquiry, related_listing_for_enquiry(enquiry))
    )
    persist_enquiry_delivery(enquiry_id, admin_result=result)
    if result.get("sent"):
        create_activity_record(
            entity_type="enquiry",
            entity_id=enquiry_id,
            action="admin_email_resent",
            summary=f"Admin enquiry notification resent for {enquiry_reference(enquiry_id)}.",
            actor_label="Admin",
        )
        flash("Admin notification email sent again.", "success")
    else:
        flash(
            str(result.get("error") or "The admin notification could not be sent."),
            "error",
        )
    return redirect(next_url)


@app.post("/dashboard/enquiries/<enquiry_id>/resend-receipt-email")
@permission_required("leads.manage")
def resend_enquiry_receipt_email(enquiry_id: str):
    next_url = admin_return_target("admin_enquiries")
    enquiry = fetch_enquiry(enquiry_id)
    if not smtp_is_configured():
        flash("SMTP is not configured yet.", "error")
        return redirect(next_url)
    if not normalized_email_address(str(enquiry.get("email") or "")):
        flash("This enquiry does not include a visitor email address.", "error")
        return redirect(next_url)

    result = send_enquiry_receipt(
        enquiry_email_context(enquiry_id, enquiry, related_listing_for_enquiry(enquiry))
    )
    persist_enquiry_delivery(enquiry_id, receipt_result=result)
    if result.get("sent"):
        create_activity_record(
            entity_type="enquiry",
            entity_id=enquiry_id,
            action="receipt_email_resent",
            summary=f"Visitor receipt email resent for {enquiry_reference(enquiry_id)}.",
            actor_label="Admin",
        )
        flash("Client receipt email sent again.", "success")
    else:
        flash(
            str(result.get("error") or "The visitor receipt could not be sent."),
            "error",
        )
    return redirect(next_url)


@app.post("/dashboard/maintenance/<ticket_id>/update")
@permission_required("maintenance.manage")
def update_maintenance(ticket_id: str):
    ticket = fetch_maintenance_ticket(ticket_id)
    next_url = admin_return_target("admin_maintenance")
    status = request.form.get("status", "").strip()
    assigned_vendor = request.form.get("assigned_vendor", "").strip()
    assigned_manager = request.form.get("assigned_manager", "").strip()
    internal_note = request.form.get("internal_note", "").strip()
    if status not in MAINTENANCE_STATUS_OPTIONS:
        flash("Choose a valid maintenance status.", "error")
        return redirect(next_url)

    update_maintenance_ticket(
        ticket_id,
        status=status,
        assigned_vendor=assigned_vendor,
        assigned_manager=assigned_manager,
        internal_note=internal_note,
    )
    create_activity_record(
        entity_type="maintenance_ticket",
        entity_id=ticket_id,
        action="updated",
        summary=f"Maintenance ticket for {ticket['unit_reference']} moved to {status.lower()}.",
        actor_label="Admin",
    )
    flash("Maintenance ticket updated.", "success")
    return redirect(next_url)


@app.route("/dashboard/finance/new", methods=["GET", "POST"])
@permission_required("finance.manage")
def create_finance_record():
    back_url = admin_return_target("admin_finance")
    form_data = {
        "resident_name": "",
        "unit_reference": "",
        "property_title": "",
        "charge_type": FINANCIAL_CHARGE_OPTIONS[0],
        "amount": "",
        "due_date": "",
        "status": FINANCIAL_STATUS_OPTIONS[0],
        "assigned_to": "",
        "note": "",
    }

    if request.method == "POST":
        form_data, errors = validate_financial_record_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            now = utc_now_iso()
            form_data["created_at"] = now
            form_data["updated_at"] = now
            record_id = create_financial_record(form_data)
            create_activity_record(
                entity_type="financial_record",
                entity_id=record_id,
                action="created",
                summary=f"Financial record created for {form_data['unit_reference']} ({form_data['charge_type']}).",
                actor_label="Admin",
            )
            flash("Financial record saved.", "success")
            return redirect(back_url)

    return render_template(
        "finance_form.html",
        page_title="Add Financial Record",
        submit_label="Save financial record",
        form_data=form_data,
        back_url=back_url,
    )


@app.post("/dashboard/finance/<record_id>/status")
@permission_required("finance.manage")
def update_finance(record_id: str):
    record = fetch_financial_record(record_id)
    next_url = admin_return_target("admin_finance")
    status = request.form.get("status", "").strip()
    assigned_to = request.form.get("assigned_to", "").strip()
    note = request.form.get("note", "").strip()
    if status not in FINANCIAL_STATUS_OPTIONS:
        flash("Choose a valid financial status.", "error")
        return redirect(next_url)

    update_financial_record(record_id, status=status, assigned_to=assigned_to, note=note)
    create_activity_record(
        entity_type="financial_record",
        entity_id=record_id,
        action="updated",
        summary=f"{record['charge_type']} for {record['unit_reference']} marked {status.lower()}.",
        actor_label="Admin",
    )
    flash("Financial status updated.", "success")
    return redirect(next_url)


@app.route("/dashboard/documents/new", methods=["GET", "POST"])
@permission_required("documents.manage")
def create_document():
    back_url = admin_return_target("admin_documents")
    form_data = {
        "resident_name": "",
        "unit_reference": "",
        "property_title": "",
        "document_type": DOCUMENT_TYPE_OPTIONS[0],
        "title": "",
        "note": "",
    }

    if request.method == "POST":
        form_data, errors = validate_document_form(request.form)

        if not errors:
            try:
                upload_meta = save_document_upload(request.files.get("document_file"))
                form_data.update(upload_meta)
            except ValueError as error:
                errors.append(str(error))

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            now = utc_now_iso()
            form_data["created_at"] = now
            form_data["updated_at"] = now
            document_id = create_document_record(form_data)
            create_activity_record(
                entity_type="document",
                entity_id=document_id,
                action="created",
                summary=f"Document uploaded for {form_data['unit_reference']}: {form_data['title']}.",
                actor_label="Admin",
            )
            flash("Document saved to documents.", "success")
            return redirect(back_url)

    return render_template(
        "document_form.html",
        page_title="Upload Document",
        submit_label="Upload document",
        form_data=form_data,
        back_url=back_url,
    )


@app.post("/dashboard/documents/<document_id>/update")
@permission_required("documents.manage")
def update_document(document_id: str):
    document = fetch_document_record(document_id)
    next_url = admin_return_target("admin_documents")
    title = request.form.get("title", "").strip()
    document_type = request.form.get("document_type", "").strip()
    note = request.form.get("note", "").strip()

    errors: list[str] = []
    if not title:
        errors.append("Document title is required.")
    if document_type not in DOCUMENT_TYPE_OPTIONS:
        errors.append("Choose a valid document type.")

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(next_url)

    update_document_metadata(document_id, title=title, document_type=document_type, note=note)
    create_activity_record(
        entity_type="document",
        entity_id=document_id,
        action="updated",
        summary=f"Document details updated: {document['title']}.",
        actor_label="Admin",
    )
    flash("Document details updated.", "success")
    return redirect(next_url)


@app.get("/dashboard/documents/<document_id>/download")
@permission_required("documents.view")
def download_document(document_id: str):
    document = fetch_document_record(document_id)
    return send_file(
        DOCUMENTS_DIR / document["stored_filename"],
        mimetype=document["mime_type"],
        as_attachment=True,
        download_name=document["original_filename"],
    )


@app.post("/dashboard/documents/<document_id>/delete")
@permission_required("documents.manage")
def delete_document(document_id: str):
    next_url = admin_return_target("admin_documents")
    document = delete_document_record(document_id)
    delete_document_file(document["stored_filename"])
    create_activity_record(
        entity_type="document",
        entity_id=document_id,
        action="deleted",
        summary=f"Document removed: {document['title']}.",
        actor_label="Admin",
    )
    flash("Document deleted.", "success")
    return redirect(next_url)


@app.get("/dashboard/export.json")
@permission_required("data.export")
def export_dashboard_data():
    if database_backend() == "mongodb":
        listings = [normalize_listing_record(item) for item in get_mongo_collection().find({}).sort(DASHBOARD_SORT)]
        enquiries = [normalize_enquiry_record(item) for item in get_mongo_enquiries_collection().find({}).sort("created_at", DESCENDING)]
        activity = [normalize_activity_record(item) for item in get_mongo_activity_collection().find({}).sort("created_at", DESCENDING)]
        maintenance_tickets = [normalize_maintenance_record(item) for item in get_mongo_maintenance_collection().find({}).sort("created_at", DESCENDING)]
        financial_records = [normalize_financial_record(item) for item in get_mongo_financial_collection().find({}).sort([("due_date", ASCENDING), ("created_at", DESCENDING)])]
        documents = [normalize_document_record(item) for item in get_mongo_document_collection().find({}).sort("created_at", DESCENDING)]
        contacts = [normalize_contact_record(item) for item in get_mongo_contacts_collection().find({}).sort("created_at", DESCENDING)]
        lead_note_records = [normalize_lead_note_record(item) for item in get_mongo_lead_notes_collection().find({}).sort("created_at", DESCENDING)]
        inspections = [normalize_inspection_record(item) for item in get_mongo_inspections_collection().find({}).sort("created_at", DESCENDING)]
        partners = [partner_record_for_template(item) for item in get_mongo_partners_collection().find({}).sort("created_at", DESCENDING)]
        referrals = [normalize_referral_record(item) for item in get_mongo_referrals_collection().find({}).sort("created_at", DESCENDING)]
        referral_event_records = [normalize_referral_event(item) for item in get_mongo_referral_events_collection().find({}).sort("created_at", DESCENDING)]
        commission_rules = [normalize_commission_rule(item) for item in get_mongo_commission_rules_collection().find({}).sort("created_at", DESCENDING)]
        commissions = [normalize_commission(item) for item in get_mongo_commissions_collection().find({}).sort("created_at", DESCENDING)]
    else:
        listings = [normalize_listing_record(row) for row in get_db().execute("SELECT * FROM listings ORDER BY updated_at DESC, created_at DESC").fetchall()]
        enquiries = [normalize_enquiry_record(row) for row in get_db().execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall()]
        activity = [normalize_activity_record(row) for row in get_db().execute("SELECT * FROM activity_log ORDER BY created_at DESC").fetchall()]
        maintenance_tickets = [normalize_maintenance_record(row) for row in get_db().execute("SELECT * FROM maintenance_tickets ORDER BY created_at DESC").fetchall()]
        financial_records = [normalize_financial_record(row) for row in get_db().execute("SELECT * FROM financial_records ORDER BY due_date ASC, created_at DESC").fetchall()]
        documents = [normalize_document_record(row) for row in get_db().execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()]
        contacts = [normalize_contact_record(row) for row in get_db().execute("SELECT * FROM contacts ORDER BY created_at DESC").fetchall()]
        lead_note_records = [normalize_lead_note_record(row) for row in get_db().execute("SELECT * FROM lead_notes ORDER BY created_at DESC").fetchall()]
        inspections = [normalize_inspection_record(row) for row in get_db().execute("SELECT * FROM inspections ORDER BY created_at DESC").fetchall()]
        partners = [partner_record_for_template(row) for row in get_db().execute("SELECT * FROM partners ORDER BY created_at DESC").fetchall()]
        referrals = [normalize_referral_record(row) for row in get_db().execute("SELECT * FROM referrals ORDER BY created_at DESC").fetchall()]
        referral_event_records = [normalize_referral_event(row) for row in get_db().execute("SELECT * FROM referral_events ORDER BY created_at DESC").fetchall()]
        commission_rules = [normalize_commission_rule(row) for row in get_db().execute("SELECT * FROM commission_rules ORDER BY created_at DESC").fetchall()]
        commissions = [normalize_commission(row) for row in get_db().execute("SELECT * FROM commissions ORDER BY created_at DESC").fetchall()]

    return jsonify(
        {
            "generated_at": utc_now_iso(),
            "database_backend": database_backend(),
            "site_preferences": site_settings(),
            "listings": listings,
            "enquiries": enquiries,
            "contacts": contacts,
            "lead_notes": lead_note_records,
            "inspections": inspections,
            "partners": partners,
            "referrals": referrals,
            "referral_events": referral_event_records,
            "commission_rules": commission_rules,
            "commissions": commissions,
            "activity": activity,
            "maintenance_tickets": maintenance_tickets,
            "financial_records": financial_records,
            "documents": documents,
        }
    )


@app.route("/dashboard/listings/new", methods=["GET", "POST"])
@permission_required("properties.create")
def create_listing():
    back_url = admin_return_target("admin_listings")
    form_data = listing_defaults()

    if request.method == "POST":
        form_data, errors = validate_listing_form(request.form)

        if not errors:
            try:
                image_path = normalize_uploaded_image(request.files.get("image"))
                form_data["image_path"] = image_path or ""
                form_data["gallery_paths"] = normalize_uploaded_gallery(
                    request.files.getlist("gallery_images"),
                    form_data.get("gallery_paths", []),
                )
            except ValueError as error:
                errors.append(str(error))

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            now = utc_now_iso()
            form_data["created_at"] = now
            form_data["updated_at"] = now
            form_data["view_count"] = 0
            form_data["last_viewed_at"] = None
            created_listing_id = create_listing_record(form_data)
            create_activity_record(
                entity_type="listing",
                entity_id=created_listing_id,
                action="created",
                summary=f"Created listing: {form_data['title']} in {form_data['district']}.",
                actor_label="Admin",
            )
            flash("Listing created successfully.", "success")
            return redirect(back_url)

    return render_template(
        "listing_form.html",
        page_title="Add Listing",
        submit_label="Create listing",
        form_data=form_data,
        back_url=back_url,
    )


@app.route("/dashboard/listings/<listing_id>/edit", methods=["GET", "POST"])
@permission_required("properties.edit")
def edit_listing(listing_id: str):
    back_url = admin_return_target("admin_listings")
    listing = fetch_listing(listing_id, include_unpublished=True)
    form_data = row_to_form_data(listing)

    if request.method == "POST":
        form_data, errors = validate_listing_form(request.form)
        current_gallery = normalize_string_list(listing.get("gallery_paths"))
        removed_gallery = set(request.form.getlist("remove_gallery_paths"))
        retained_gallery = [path for path in current_gallery if path not in removed_gallery]

        if not errors:
            try:
                form_data["image_path"] = (
                    normalize_uploaded_image(request.files.get("image"), listing["image_path"]) or ""
                )
                form_data["gallery_paths"] = normalize_uploaded_gallery(
                    request.files.getlist("gallery_images"),
                    retained_gallery,
                )
            except ValueError as error:
                errors.append(str(error))

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            for path in removed_gallery:
                if path and path not in form_data["gallery_paths"]:
                    delete_uploaded_image(path)
            form_data["updated_at"] = utc_now_iso()
            update_listing_record(listing_id, form_data)
            create_activity_record(
                entity_type="listing",
                entity_id=listing_id,
                action="updated",
                summary=f"Updated listing: {form_data['title']} ({form_data['availability'].lower()}).",
                actor_label="Admin",
            )
            flash("Listing updated successfully.", "success")
            return redirect(back_url)

    return render_template(
        "listing_form.html",
        page_title="Edit Listing",
        submit_label="Save changes",
        form_data=form_data,
        back_url=back_url,
    )


@app.post("/dashboard/listings/<listing_id>/delete")
@permission_required("properties.delete")
def delete_listing(listing_id: str):
    next_url = admin_return_target("admin_listings")
    listing = fetch_listing(listing_id, include_unpublished=True)
    delete_uploaded_image(listing["image_path"])
    for path in normalize_string_list(listing.get("gallery_paths")):
        if path != listing.get("image_path"):
            delete_uploaded_image(path)
    delete_listing_record(listing_id)
    create_activity_record(
        entity_type="listing",
        entity_id=str(listing["id"]),
        action="deleted",
        summary=f"Deleted listing: {listing['title']}.",
        actor_label="Admin",
    )
    flash("Listing deleted.", "success")
    return redirect(next_url)


@app.route("/about")
def about():
    stats = public_stats(include_district_count=True)
    return render_template("about.html", stats=stats)


@app.get("/offline")
def offline():
    return render_template("offline.html")


@app.get("/service-worker.js")
def service_worker():
    response = send_file(
        STATIC_DIR / "service-worker.js",
        mimetype="application/javascript",
        conditional=True,
        max_age=0,
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/favicon.ico")
def favicon():
    return send_file(
        STATIC_DIR / "images" / "icon-192.png",
        mimetype="image/png",
        max_age=86400,
    )


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.get("/robots.txt")
def robots_txt():
    if not app.config["SEARCH_INDEXING_ENABLED"]:
        return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")

    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /dashboard",
        "Disallow: /login",
        "Disallow: /partners/login",
        "Disallow: /partner",
        "Disallow: /staff",
        f"Sitemap: {canonical_external_url((configured_public_origin() or request.url_root.rstrip('/')) + url_for('sitemap_xml'))}",
        "",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    filters = {
        "status": "",
        "availability": "",
        "district": "",
        "property_type": "",
        "q": "",
        "min_price": "",
        "max_price": "",
        "min_bedrooms": "",
        "sort": "recommended",
        "verified_only": "",
    }
    for key, _label in DISCOVERY_FEATURE_FIELDS:
        filters[key] = ""
    listings = query_public_listings(filters)
    paths = [
        url_for("home"),
        url_for("properties"),
        url_for("about"),
        url_for("tenant_services"),
        url_for("partner_register"),
        url_for("privacy"),
        url_for("terms"),
        *(url_for("property_detail", listing_id=str(listing["id"])) for listing in listings),
    ]
    origin = configured_public_origin() or request.url_root.rstrip("/")
    entries = "".join(
        f"<url><loc>{xml_escape(canonical_external_url(origin + path))}</loc></url>"
        for path in dict.fromkeys(paths)
    )
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    )
    return Response(payload, mimetype="application/xml")


@app.get("/healthz")
def healthcheck():
    payload = {
        "status": "ok",
        "environment": app.config["ENVIRONMENT"],
        "database_backend": database_backend(),
        "storage_backend": storage_backend(),
        "smtp_configured": smtp_is_configured(),
        "proxy_trust_count": app.config["TRUST_PROXY_COUNT"],
        "mapbox_configured": app.config["MAPBOX_TOKEN"] != "YOUR_MAPBOX_TOKEN_HERE",
        "admin_username_configured": app.config["ADMIN_USERNAME"] != DEFAULT_ADMIN_USERNAME,
        "admin_password_configured": bool(app.config["ADMIN_PASSWORD_HASH"])
        or app.config["ADMIN_PASSWORD"] != DEFAULT_ADMIN_PASSWORD,
        "using_default_credentials": site_settings()["using_default_credentials"],
    }
    if database_backend() == "mongodb":
        try:
            get_mongo_client().admin.command("ping")
        except PyMongoError:
            payload["status"] = "degraded"
            if app.config["IS_PRODUCTION"]:
                return jsonify({"status": payload["status"]}), 503
            return jsonify(payload), 503
    if app.config["IS_PRODUCTION"]:
        return jsonify({"status": payload["status"]})
    return jsonify(payload)


@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(_error):
    flash("Image upload is too large. Keep files under 10MB.", "error")
    if request.path.startswith("/dashboard"):
        return redirect(url_for("dashboard"))
    return redirect(request.referrer or url_for("home"))


@app.errorhandler(403)
def handle_forbidden(_error):
    return (
        render_template(
            "error_page.html",
            error_code="403",
            error_label="Access restricted",
            error_heading="Your staff role does not allow this action.",
            error_message="Return to the workspace and choose a section available to your account, or ask a super admin if your responsibilities have changed.",
        ),
        403,
    )


@app.errorhandler(404)
def handle_not_found(_error):
    return (
        render_template(
            "error_page.html",
            error_code="404",
            error_label="Page not found",
            error_heading="This address does not lead to a current page.",
            error_message="The listing or page may have moved, expired, or been entered incorrectly. Return to the live catalogue or ask the team for guidance.",
        ),
        404,
    )


@app.errorhandler(500)
def handle_server_error(_error):
    app.logger.exception("Unhandled server error")
    return (
        render_template(
            "error_page.html",
            error_code="500",
            error_label="Temporary issue",
            error_heading="We could not complete that request.",
            error_message="Nothing has been submitted twice. Try again, return to the catalogue, or contact the team if the issue continues.",
        ),
        500,
    )


configure_logging()

with app.app_context():
    enforce_startup_checks()
    try:
        init_data_store()
    except PyMongoError as exc:
        app.logger.exception(
            "Startup data store initialization failed. Check MongoDB URI, "
            "Atlas network access, database user credentials, and allowed IPs."
        )
        raise RuntimeError("Startup data store initialization failed.") from exc
    except Exception:
        app.logger.exception("Startup data store initialization failed.")
        raise


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1").strip() or "127.0.0.1"
    app.run(host=host, port=port, debug=False)
