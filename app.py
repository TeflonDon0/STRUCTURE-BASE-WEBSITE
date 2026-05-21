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
from functools import wraps
from pathlib import Path
from urllib.parse import quote, urlsplit

import cloudinary
import cloudinary.uploader
from communication_templates import (
    communication_sample_payload,
    communication_template_choices,
    render_communication_template,
)
from flask import (
    Flask,
    abort,
    flash,
    g,
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
from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError
from werkzeug.exceptions import NotFound, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "structurebase.db"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = STATIC_DIR / "uploads"
DOCUMENTS_DIR = BASE_DIR / "data" / "documents"
load_dotenv(BASE_DIR / ".env")
EMAIL_LOGO_PATH = STATIC_DIR / "images" / "LOGO2-email.png"

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp"}
STATUS_OPTIONS = ("For Sale", "For Rent", "For Lease")
AVAILABILITY_OPTIONS = ("Available", "Under Offer", "Sold", "Rented", "Leased", "Off Market")
SALE_AVAILABILITY_OPTIONS = {"Available", "Under Offer", "Sold", "Off Market"}
RENT_AVAILABILITY_OPTIONS = {"Available", "Under Offer", "Rented", "Off Market"}
LEASE_AVAILABILITY_OPTIONS = {"Available", "Under Offer", "Leased", "Off Market"}
PRICE_SUFFIX_OPTIONS = ("", "/ year", "/ month")
ENQUIRY_CONTACT_OPTIONS = ("Email", "Phone", "WhatsApp")
ENQUIRY_STATUS_OPTIONS = (
    "New",
    "Qualified",
    "Viewing Scheduled",
    "Negotiating",
    "Won",
    "Lost",
    "Handled",
)
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
CLOSED_ENQUIRY_STATUSES = {"Won", "Lost", "Handled"}
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


def database_backend() -> str:
    configured = app.config["DATABASE_BACKEND"]
    if configured in {"sqlite", "mongodb"}:
        return configured
    return "mongodb" if app.config["MONGODB_URI"] else "sqlite"


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
    return [
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
    data["status"] = str(data.get("status") or "New")
    data["assigned_to"] = str(data.get("assigned_to") or "").strip()
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
            status TEXT NOT NULL DEFAULT 'New',
            assigned_to TEXT,
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
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

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
    ensure_sqlite_column("listings", "is_serviced", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "has_power_24_7", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "is_flood_free", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "near_express", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "near_schools", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "near_markets", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "verified_property", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("listings", "verified_landlord", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column("enquiries", "assigned_to", "TEXT")
    ensure_sqlite_column("enquiries", "internal_note", "TEXT")
    ensure_sqlite_column("enquiries", "follow_up_on", "TEXT")
    ensure_sqlite_column("enquiries", "admin_email_recipient", "TEXT")
    ensure_sqlite_column("enquiries", "admin_email_sent_at", "TEXT")
    ensure_sqlite_column("enquiries", "admin_email_last_error", "TEXT")
    ensure_sqlite_column("enquiries", "receipt_email_recipient", "TEXT")
    ensure_sqlite_column("enquiries", "receipt_email_sent_at", "TEXT")
    ensure_sqlite_column("enquiries", "receipt_email_last_error", "TEXT")
    ensure_sqlite_column("maintenance_tickets", "assigned_manager", "TEXT")
    ensure_sqlite_column("maintenance_tickets", "internal_note", "TEXT")
    ensure_sqlite_column("financial_records", "assigned_to", "TEXT")
    ensure_sqlite_column("documents", "source_kind", "TEXT NOT NULL DEFAULT 'upload'")
    ensure_sqlite_column("documents", "template_key", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column("documents", "template_version", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column("documents", "payload_json", "TEXT NOT NULL DEFAULT ''")
    db.execute("UPDATE listings SET availability = 'Available' WHERE availability IS NULL OR availability = ''")
    db.execute("UPDATE listings SET view_count = 0 WHERE view_count IS NULL")
    db.execute("UPDATE listings SET gallery_paths = '[]' WHERE gallery_paths IS NULL OR gallery_paths = ''")
    db.execute("UPDATE listings SET virtual_tour_url = '' WHERE virtual_tour_url IS NULL")
    db.execute("UPDATE enquiries SET assigned_to = '' WHERE assigned_to IS NULL")
    db.execute("UPDATE enquiries SET internal_note = '' WHERE internal_note IS NULL")
    db.execute("UPDATE enquiries SET admin_email_recipient = '' WHERE admin_email_recipient IS NULL")
    db.execute("UPDATE enquiries SET admin_email_sent_at = '' WHERE admin_email_sent_at IS NULL")
    db.execute("UPDATE enquiries SET admin_email_last_error = '' WHERE admin_email_last_error IS NULL")
    db.execute("UPDATE enquiries SET receipt_email_recipient = '' WHERE receipt_email_recipient IS NULL")
    db.execute("UPDATE enquiries SET receipt_email_sent_at = '' WHERE receipt_email_sent_at IS NULL")
    db.execute("UPDATE enquiries SET receipt_email_last_error = '' WHERE receipt_email_last_error IS NULL")
    db.execute("UPDATE maintenance_tickets SET assigned_manager = '' WHERE assigned_manager IS NULL")
    db.execute("UPDATE maintenance_tickets SET internal_note = '' WHERE internal_note IS NULL")
    db.execute("UPDATE financial_records SET assigned_to = '' WHERE assigned_to IS NULL")
    db.execute("UPDATE documents SET source_kind = 'upload' WHERE source_kind IS NULL OR source_kind = ''")
    db.execute("UPDATE documents SET template_key = '' WHERE template_key IS NULL")
    db.execute("UPDATE documents SET template_version = '' WHERE template_version IS NULL")
    db.execute("UPDATE documents SET payload_json = '' WHERE payload_json IS NULL")
    db.commit()

    current_count = db.execute("SELECT COUNT(*) AS count FROM listings").fetchone()["count"]
    if current_count == 0:
        seed_sqlite_listings()


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
        for key, _label in DISCOVERY_FEATURE_FIELDS + VERIFICATION_FIELDS:
            collection.update_many({key: {"$exists": False}}, {"$set": {key: 0}})

    enquiries = get_mongo_enquiries_collection()
    enquiries.create_index([("public_id", ASCENDING)], unique=True)
    enquiries.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    enquiries.create_index([("listing_id", ASCENDING)])
    enquiries.create_index([("assigned_to", ASCENDING)])
    enquiries.update_many({"assigned_to": {"$exists": False}}, {"$set": {"assigned_to": ""}})
    enquiries.update_many({"internal_note": {"$exists": False}}, {"$set": {"internal_note": ""}})
    enquiries.update_many({"follow_up_on": {"$exists": False}}, {"$set": {"follow_up_on": ""}})

    activity = get_mongo_activity_collection()
    activity.create_index([("created_at", DESCENDING)])
    activity.create_index([("entity_type", ASCENDING), ("entity_id", ASCENDING)])

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
    documents.update_many({"source_kind": {"$exists": False}}, {"$set": {"source_kind": "upload"}})
    documents.update_many({"template_key": {"$exists": False}}, {"$set": {"template_key": ""}})
    documents.update_many({"template_version": {"$exists": False}}, {"$set": {"template_version": ""}})
    documents.update_many({"payload_json": {"$exists": False}}, {"$set": {"payload_json": ""}})

    get_mongo_settings_collection()


def init_data_store() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    if database_backend() == "mongodb":
        get_mongo_client().admin.command("ping")
        init_mongodb()
        return
    init_sqlite_db()


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
        and not app.config["ADMIN_PASSWORD_HASH"]
        and app.config["ADMIN_PASSWORD"] == DEFAULT_ADMIN_PASSWORD
    )
    return {
        "site_name": merged["site_name"],
        "contact_email": contact_email,
        "contact_phone_display": merged["contact_phone_display"],
        "contact_phone_raw": phone_digits,
        "whatsapp_phone": whatsapp_digits,
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

    if app.config["STORAGE_BACKEND"] in {"cloudinary", "r2"} and not cloudinary_is_configured():
        blocking_errors.append(
            "Cloud storage is selected but Cloudinary credentials are incomplete."
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

    if is_placeholder_email(str(site_settings().get("contact_email") or "")):
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
        raise RuntimeError("Startup checks failed. Review logs for the blocking configuration issues.")


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
    return bool(session.get("is_admin"))


def check_admin_credentials(username: str, password: str) -> bool:
    if username != app.config["ADMIN_USERNAME"]:
        return False
    if app.config["ADMIN_PASSWORD_HASH"]:
        return check_password_hash(app.config["ADMIN_PASSWORD_HASH"], password)
    return password == app.config["ADMIN_PASSWORD"]


def safe_redirect_target(target: str | None) -> str:
    if not target:
        return url_for("dashboard")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        if parsed.netloc and parsed.netloc != request.host:
            return url_for("dashboard")
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
    if not target.startswith("/") or target.startswith("//"):
        return url_for("dashboard")
    return target


def admin_return_target(default_endpoint: str) -> str:
    target = request.form.get("next") if request.method == "POST" else request.args.get("next")
    if target:
        return safe_redirect_target(target)
    return url_for(default_endpoint)


def client_ip() -> str:
    return request.remote_addr or "unknown"


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def login_rate_limit_store() -> dict[str, list[float]]:
    return app.extensions.setdefault("login_attempts", {})


def login_rate_limit_key(username: str) -> str:
    normalized = username.strip().lower() or "anonymous"
    return f"{client_ip()}::{normalized}"


def prune_login_attempts(key: str) -> list[float]:
    cutoff = time.time() - app.config["LOGIN_WINDOW_SECONDS"]
    attempts = [stamp for stamp in login_rate_limit_store().get(key, []) if stamp >= cutoff]
    login_rate_limit_store()[key] = attempts
    return attempts


def login_is_rate_limited(username: str) -> bool:
    attempts = prune_login_attempts(login_rate_limit_key(username))
    return len(attempts) >= app.config["LOGIN_MAX_ATTEMPTS"]


def record_failed_login(username: str) -> None:
    key = login_rate_limit_key(username)
    attempts = prune_login_attempts(key)
    attempts.append(time.time())
    login_rate_limit_store()[key] = attempts


def reset_failed_login(username: str) -> None:
    login_rate_limit_store().pop(login_rate_limit_key(username), None)


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

    started = getattr(g, "request_started_at", None)
    duration_ms = round((time.perf_counter() - started) * 1000, 2) if started else None
    if not request.path.startswith("/static/") or response.status_code >= 400:
        log_payload = {
            "event": "http.request",
            "request_id": getattr(g, "request_id", ""),
            "method": request.method,
            "path": request.path,
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
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


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
    actor_label: str,
) -> None:
    payload = {
        "public_id": uuid.uuid4().hex[:12],
        "entity_type": entity_type,
        "entity_id": entity_id or "",
        "action": action,
        "actor_label": actor_label,
        "summary": summary,
        "created_at": utc_now_iso(),
    }
    if database_backend() == "mongodb":
        get_mongo_activity_collection().insert_one(payload)
        return

    get_db().execute(
        """
        INSERT INTO activity_log (
            public_id,
            entity_type,
            entity_id,
            action,
            actor_label,
            summary,
            created_at
        ) VALUES (
            :public_id,
            :entity_type,
            :entity_id,
            :action,
            :actor_label,
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
    payload = {
        "public_id": uuid.uuid4().hex[:12],
        "listing_id": data["listing_id"],
        "listing_title": data["listing_title"],
        "status": "New",
        "assigned_to": "",
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
            assigned_to,
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
            :assigned_to,
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
        new_count = get_mongo_enquiries_collection().count_documents({"status": "New"})
        return {"enquiry_total": total, "new_count": new_count}

    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status = 'New' THEN 1 ELSE 0 END) AS new_count
        FROM enquiries
        """
    ).fetchone()
    return {"enquiry_total": int(row["total"] or 0), "new_count": int(row["new_count"] or 0)}


def update_enquiry_record(
    enquiry_id: str,
    *,
    status: str,
    assigned_to: str = "",
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
                    "internal_note": internal_note,
                    "follow_up_on": follow_up_on,
                    "updated_at": now,
                }
            },
        )
        return

    get_db().execute(
        "UPDATE enquiries SET status = ?, assigned_to = ?, internal_note = ?, follow_up_on = ?, updated_at = ? WHERE public_id = ?",
        (status, assigned_to, internal_note, follow_up_on, now, enquiry_id),
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
        cursor = get_mongo_collection().find(query).sort(LISTING_SORT)
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
    for key, _label in DISCOVERY_FEATURE_FIELDS:
        if filters.get(key):
            sql += f" AND {key} = 1"
    if filters["q"]:
        pattern = f"%{filters['q']}%"
        sql += " AND (title LIKE ? OR summary LIKE ? OR district LIKE ? OR address LIKE ?)"
        params.extend([pattern, pattern, pattern, pattern])

    sql += " ORDER BY featured DESC, updated_at DESC, created_at DESC"
    rows = db.execute(sql, params).fetchall()
    return [normalize_listing_record(row) for row in rows]


def home_featured_listings(limit: int = 3) -> list[dict[str, object]]:
    if database_backend() == "mongodb":
        cursor = get_mongo_collection().find({"published": 1}).sort(LISTING_SORT).limit(limit)
        return [normalize_listing_record(document) for document in cursor]

    rows = get_db().execute(
        """
        SELECT * FROM listings
        WHERE published = 1
        ORDER BY featured DESC, updated_at DESC
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
    return {"q": "", "status": "", "assigned_to": "", "sort": "newest"}


def enquiry_filters_from_request() -> dict[str, str]:
    filters = enquiry_filter_defaults()
    filters.update(
        {
            "q": request.args.get("q", "").strip(),
            "status": request.args.get("status", "").strip(),
            "assigned_to": request.args.get("assigned_to", "").strip(),
            "sort": request.args.get("sort", "newest").strip(),
        }
    )
    if filters["status"] not in ENQUIRY_STATUS_OPTIONS:
        filters["status"] = ""
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
    return {"q": "", "document_type": "", "sort": "newest"}


def document_filters_from_request() -> dict[str, str]:
    filters = document_filter_defaults()
    filters.update(
        {
            "q": request.args.get("q", "").strip(),
            "document_type": request.args.get("document_type", "").strip(),
            "sort": request.args.get("sort", "newest").strip(),
        }
    )
    if filters["document_type"] not in DOCUMENT_TYPE_OPTIONS:
        filters["document_type"] = ""
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
        if status == "New" or follow_up_due or not assigned_to:
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
            0 if status == "New" else 1,
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
        elif str(item.get("status") or "") == "New":
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
        status = str(record.get("status") or "New")
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
    return url_for("static", filename=path)


def absolute_asset_url(asset_path: str | None) -> str:
    url = asset_url(asset_path)
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return request.url_root.rstrip("/") + url


def static_asset_version(filename: str) -> str:
    file_path = STATIC_DIR / filename
    try:
        return hashlib.blake2s(file_path.read_bytes(), digest_size=6).hexdigest()
    except OSError:
        return "0"


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
        "url": request.base_url,
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
    return {
        "current_year": datetime.now().year,
        "site_settings": settings,
        "is_authenticated": is_authenticated(),
        "general_whatsapp_url": build_whatsapp_url(general_whatsapp_message()),
        "listing_whatsapp_url": lambda listing: build_whatsapp_url(listing_whatsapp_message(listing)),
        "listing_image_path": resolved_listing_image_path,
        "listing_media_gallery": listing_media_gallery,
        "listing_feature_labels": listing_feature_labels,
        "listing_verification_labels": listing_verification_labels,
        "listing_has_uploaded_image": listing_has_uploaded_image,
        "asset_url": asset_url,
        "absolute_asset_url": absolute_asset_url,
        "static_asset_url": static_asset_url,
        "service_worker_url": service_worker_url(),
        "database_backend": database_backend(),
        "storage_backend": storage_backend(),
        "is_production": app.config["IS_PRODUCTION"],
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
    featured = home_featured_listings(limit=3)
    stats = public_stats(include_district_count=True)
    districts = top_districts(limit=4)
    return render_template("index.html", featured=featured, stats=stats, districts=districts)


@app.route("/properties")
def properties():
    filters = {
        "status": request.args.get("status", "").strip(),
        "availability": request.args.get("availability", "").strip(),
        "district": request.args.get("district", "").strip(),
        "property_type": request.args.get("property_type", "").strip(),
        "q": request.args.get("q", "").strip(),
        "verified_only": "1" if request.args.get("verified_only") else "",
    }
    for key, _label in DISCOVERY_FEATURE_FIELDS:
        filters[key] = "1" if request.args.get(key) else ""
    listings = query_public_listings(filters)

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
    )


@app.route("/properties/<listing_id>")
def property_detail(listing_id: str):
    listing = fetch_listing(listing_id)
    if should_track_listing_view(str(listing["id"])):
        increment_listing_view(str(listing["id"]))
        listing["view_count"] = int(listing.get("view_count", 0)) + 1
    related = related_listings(listing, limit=3)
    return render_template(
        "property_detail.html",
        listing=listing,
        related=related,
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

        if check_admin_credentials(username, password):
            session.clear()
            session["is_admin"] = True
            session["admin_username"] = app.config["ADMIN_USERNAME"]
            session.permanent = True
            reset_failed_login(username)
            flash("Dashboard access granted.", "success")
            return redirect(next_url)

        record_failed_login(username)
        login_error = "Incorrect username or password."

    return render_template(
        "login.html",
        next_url=next_url,
        using_default_credentials=site_settings()["using_default_credentials"],
        admin_username=request.form.get("username", "").strip() or app.config["ADMIN_USERNAME"],
        show_local_default_credentials=is_local_request_host(),
        default_admin_username=DEFAULT_ADMIN_USERNAME,
        default_admin_password=DEFAULT_ADMIN_PASSWORD,
        login_error=login_error,
    )


@app.post("/logout")
def logout():
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
    create_activity_record(
        entity_type="enquiry",
        entity_id=enquiry_id,
        action="created",
        summary=f"New enquiry from {enquiry_data['name']} for {enquiry_data['listing_title'] or 'general assistance'}.",
        actor_label="Public enquiry",
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
@login_required
def dashboard():
    stats = dashboard_stats()
    inventory = dashboard_listings()
    enquiry_records = all_enquiries()
    maintenance_records = all_maintenance_tickets()
    finance_records = all_financial_records()
    document_records = all_documents()
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
        activity=recent_activity(limit=10),
    )


@app.route("/dashboard/listings")
@login_required
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
@login_required
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
@login_required
def admin_enquiries():
    filters = enquiry_filters_from_request()
    all_records = all_enquiries()
    records = query_admin_enquiries(filters)
    active_filter_labels: list[str] = []
    if filters.get("q"):
        active_filter_labels.append(f'Search: "{filters["q"]}"')
    if filters.get("status"):
        active_filter_labels.append(str(filters["status"]))
    if filters.get("assigned_to"):
        active_filter_labels.append(f"Owner: {filters['assigned_to']}")
    return render_template(
        "admin_enquiries.html",
        enquiries=records,
        enquiry_filters=filters,
        enquiry_status_options=ENQUIRY_STATUS_OPTIONS,
        enquiry_sort_options=ENQUIRY_SORT_OPTIONS,
        enquiry_total=len(all_records),
        enquiry_summary=enquiry_management_summary(all_records),
        enquiry_assignees=distinct_record_values(all_records, "assigned_to"),
        active_filter_labels=active_filter_labels,
    )


@app.route("/dashboard/maintenance")
@login_required
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
@login_required
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
@login_required
def admin_documents():
    filters = document_filters_from_request()
    all_records = all_documents()
    records = query_admin_documents(filters)
    active_filter_labels: list[str] = []
    if filters.get("q"):
        active_filter_labels.append(f'Search: "{filters["q"]}"')
    if filters.get("document_type"):
        active_filter_labels.append(str(filters["document_type"]))
    return render_template(
        "admin_documents.html",
        documents=records,
        document_filters=filters,
        document_type_options=DOCUMENT_TYPE_OPTIONS,
        document_sort_options=DOCUMENT_SORT_OPTIONS,
        document_total=len(all_records),
        document_summary=document_management_summary(all_records),
        active_filter_labels=active_filter_labels,
    )


@app.get("/dashboard/documents/generator-spec.json")
@login_required
def document_generator_spec():
    return jsonify(generator_spec(site_settings()))


@app.route("/dashboard/documents/generate", methods=["GET", "POST"])
@login_required
def generate_document_pdf():
    settings = site_settings()
    template_library = document_generator_catalog(settings)
    template_choices = template_options(settings)
    selected_template = (
        request.form.get("template_key", "").strip()
        if request.method == "POST"
        else request.args.get("template_key", "").strip()
    )
    if selected_template not in template_library:
        selected_template = template_choices[0][0]
    guided_template = guided_document_blueprint(selected_template)
    guided_form_data = guided_form_data_from_payload(
        selected_template,
        template_library[selected_template].get("sample_payload", {}),
        settings,
    )

    form_data = {
        "template_key": selected_template,
        "title": f"{template_library[selected_template]['label']} - {settings['site_name']}",
        "resident_name": "",
        "unit_reference": "",
        "property_title": "",
        "note": "",
        "payload_json": sample_payload_json(selected_template, settings),
        "use_advanced_payload": "",
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
        back_url=url_for("admin_documents"),
    )


@app.route("/dashboard/settings", methods=["GET", "POST"])
@login_required
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
@login_required
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
@login_required
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
@login_required
def update_enquiry(enquiry_id: str):
    enquiry = fetch_enquiry(enquiry_id)
    next_url = admin_return_target("admin_enquiries")
    next_status = request.form.get("status", "").strip()
    assigned_to = request.form.get("assigned_to", "").strip()
    internal_note = request.form.get("internal_note", "").strip()
    follow_up_on, follow_up_error = normalize_optional_date(
        request.form.get("follow_up_on", ""),
        "Follow-up date",
    )
    if next_status not in ENQUIRY_STATUS_OPTIONS:
        flash("Choose a valid enquiry state.", "error")
        return redirect(next_url)
    if follow_up_error:
        flash(follow_up_error, "error")
        return redirect(next_url)

    update_enquiry_record(
        enquiry_id,
        status=next_status,
        assigned_to=assigned_to,
        internal_note=internal_note,
        follow_up_on=follow_up_on,
    )
    create_activity_record(
        entity_type="enquiry",
        entity_id=enquiry_id,
        action="status_changed",
        summary=f"Enquiry from {enquiry['name']} marked as {next_status.lower()}.",
        actor_label="Admin",
    )
    flash("Enquiry status updated.", "success")
    return redirect(next_url)


@app.post("/dashboard/enquiries/<enquiry_id>/resend-admin-email")
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
def download_document(document_id: str):
    document = fetch_document_record(document_id)
    return send_file(
        DOCUMENTS_DIR / document["stored_filename"],
        mimetype=document["mime_type"],
        as_attachment=True,
        download_name=document["original_filename"],
    )


@app.post("/dashboard/documents/<document_id>/delete")
@login_required
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
@login_required
def export_dashboard_data():
    if database_backend() == "mongodb":
        listings = [normalize_listing_record(item) for item in get_mongo_collection().find({}).sort(DASHBOARD_SORT)]
        enquiries = [normalize_enquiry_record(item) for item in get_mongo_enquiries_collection().find({}).sort("created_at", DESCENDING)]
        activity = [normalize_activity_record(item) for item in get_mongo_activity_collection().find({}).sort("created_at", DESCENDING)]
        maintenance_tickets = [normalize_maintenance_record(item) for item in get_mongo_maintenance_collection().find({}).sort("created_at", DESCENDING)]
        financial_records = [normalize_financial_record(item) for item in get_mongo_financial_collection().find({}).sort([("due_date", ASCENDING), ("created_at", DESCENDING)])]
        documents = [normalize_document_record(item) for item in get_mongo_document_collection().find({}).sort("created_at", DESCENDING)]
    else:
        listings = [normalize_listing_record(row) for row in get_db().execute("SELECT * FROM listings ORDER BY updated_at DESC, created_at DESC").fetchall()]
        enquiries = [normalize_enquiry_record(row) for row in get_db().execute("SELECT * FROM enquiries ORDER BY created_at DESC").fetchall()]
        activity = [normalize_activity_record(row) for row in get_db().execute("SELECT * FROM activity_log ORDER BY created_at DESC").fetchall()]
        maintenance_tickets = [normalize_maintenance_record(row) for row in get_db().execute("SELECT * FROM maintenance_tickets ORDER BY created_at DESC").fetchall()]
        financial_records = [normalize_financial_record(row) for row in get_db().execute("SELECT * FROM financial_records ORDER BY due_date ASC, created_at DESC").fetchall()]
        documents = [normalize_document_record(row) for row in get_db().execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()]

    return jsonify(
        {
            "generated_at": utc_now_iso(),
            "database_backend": database_backend(),
            "site_preferences": site_settings(),
            "listings": listings,
            "enquiries": enquiries,
            "activity": activity,
            "maintenance_tickets": maintenance_tickets,
            "financial_records": financial_records,
            "documents": documents,
        }
    )


@app.route("/dashboard/listings/new", methods=["GET", "POST"])
@login_required
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
@login_required
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
@login_required
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
    }
    if database_backend() == "mongodb":
        try:
            get_mongo_client().admin.command("ping")
        except PyMongoError:
            payload["status"] = "degraded"
            return jsonify(payload), 503
    return jsonify(payload)


@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(_error):
    flash("Image upload is too large. Keep files under 10MB.", "error")
    if request.path.startswith("/dashboard"):
        return redirect(url_for("dashboard"))
    return redirect(request.referrer or url_for("home"))


configure_logging()

with app.app_context():
    init_data_store()
    enforce_startup_checks()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
