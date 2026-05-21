from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

import cloudinary
import cloudinary.api
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def env_value(key: str) -> str:
    return os.environ.get(key, "").strip()


def result(name: str, status: str, detail: str) -> CheckResult:
    return CheckResult(name=name, status=status, detail=detail)


def is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return not value or lowered.startswith("replace-with") or "your-" in lowered or "change-me" in lowered


def check_required_env() -> list[CheckResult]:
    checks: list[CheckResult] = []
    required = [
        "STRUCTUREBASE_ENV",
        "STRUCTUREBASE_SECRET",
        "STRUCTUREBASE_ADMIN_USERNAME",
        "STRUCTUREBASE_ADMIN_PASSWORD",
        "STRUCTUREBASE_SESSION_COOKIE_SECURE",
        "STRUCTUREBASE_DATABASE_BACKEND",
        "STRUCTUREBASE_STORAGE_BACKEND",
        "STRUCTUREBASE_SITE_NAME",
        "STRUCTUREBASE_CONTACT_EMAIL",
        "STRUCTUREBASE_CONTACT_PHONE",
        "STRUCTUREBASE_CONTACT_PHONE_RAW",
        "STRUCTUREBASE_WHATSAPP_PHONE",
    ]
    missing = [key for key in required if not env_value(key)]
    placeholder = [key for key in required if is_placeholder(env_value(key))]
    if missing:
        checks.append(result("required_env", "fail", f"Missing: {', '.join(missing)}"))
    elif placeholder:
        checks.append(result("required_env", "fail", f"Placeholder values: {', '.join(placeholder)}"))
    else:
        checks.append(result("required_env", "pass", "Required deployment env vars are present."))

    if env_value("STRUCTUREBASE_ENV") != "production":
        checks.append(result("environment", "warn", "STRUCTUREBASE_ENV is not production."))
    else:
        checks.append(result("environment", "pass", "Production environment selected."))

    if env_value("STRUCTUREBASE_SESSION_COOKIE_SECURE") not in {"1", "true", "True", "yes", "on"}:
        checks.append(result("secure_cookie", "fail", "STRUCTUREBASE_SESSION_COOKIE_SECURE must be 1/true in production."))
    else:
        checks.append(result("secure_cookie", "pass", "Secure session cookies enabled."))

    if env_value("STRUCTUREBASE_ADMIN_PASSWORD_HASH"):
        checks.append(result("admin_password", "warn", "STRUCTUREBASE_ADMIN_PASSWORD_HASH is set and overrides STRUCTUREBASE_ADMIN_PASSWORD."))
    elif is_placeholder(env_value("STRUCTUREBASE_ADMIN_PASSWORD")):
        checks.append(result("admin_password", "fail", "Admin password is missing or placeholder."))
    else:
        checks.append(result("admin_password", "pass", "Admin password is configured."))

    return checks


def check_mongodb(connect: bool) -> list[CheckResult]:
    backend = env_value("STRUCTUREBASE_DATABASE_BACKEND")
    uri = env_value("STRUCTUREBASE_MONGODB_URI")
    if backend != "mongodb":
        return [result("mongodb", "warn", f"Database backend is {backend or 'unset'}; MongoDB is not active.")]
    if not (uri.startswith("mongodb://") or uri.startswith("mongodb+srv://")):
        return [result("mongodb", "fail", "STRUCTUREBASE_MONGODB_URI must start with mongodb:// or mongodb+srv://.")]
    if not connect:
        return [result("mongodb", "pass", "MongoDB URI shape is valid. Use --connections to ping Atlas.")]
    try:
        MongoClient(uri, serverSelectionTimeoutMS=8000).admin.command("ping")
    except PyMongoError as exc:
        return [result("mongodb", "fail", f"MongoDB ping failed: {exc.__class__.__name__}: {exc}")]
    return [result("mongodb", "pass", "MongoDB ping succeeded.")]


def check_cloudinary(connect: bool) -> list[CheckResult]:
    backend = env_value("STRUCTUREBASE_STORAGE_BACKEND")
    cloudinary_url = env_value("CLOUDINARY_URL")
    explicit = [
        env_value("STRUCTUREBASE_CLOUDINARY_CLOUD_NAME"),
        env_value("STRUCTUREBASE_CLOUDINARY_API_KEY"),
        env_value("STRUCTUREBASE_CLOUDINARY_API_SECRET"),
    ]
    if backend != "cloudinary":
        return [result("cloudinary", "warn", f"Storage backend is {backend or 'unset'}; Cloudinary is not active.")]
    if not cloudinary_url and not all(explicit):
        return [result("cloudinary", "fail", "Set CLOUDINARY_URL or all explicit Cloudinary credentials.")]
    if cloudinary_url and not cloudinary_url.startswith("cloudinary://"):
        return [result("cloudinary", "fail", "CLOUDINARY_URL must start with cloudinary://.")]
    if not connect:
        return [result("cloudinary", "pass", "Cloudinary credential shape is valid. Use --connections to call API ping.")]
    if cloudinary_url:
        os.environ["CLOUDINARY_URL"] = cloudinary_url
        cloudinary.config(secure=True)
    else:
        cloudinary.config(
            cloud_name=explicit[0],
            api_key=explicit[1],
            api_secret=explicit[2],
            secure=True,
        )
    try:
        cloudinary.api.ping()
    except Exception as exc:
        return [result("cloudinary", "fail", f"Cloudinary ping failed: {exc.__class__.__name__}: {exc}")]
    return [result("cloudinary", "pass", "Cloudinary API ping succeeded.")]


def check_smtp(connect: bool) -> list[CheckResult]:
    keys = [
        "STRUCTUREBASE_SMTP_HOST",
        "STRUCTUREBASE_SMTP_PORT",
        "STRUCTUREBASE_SMTP_USERNAME",
        "STRUCTUREBASE_SMTP_PASSWORD",
        "STRUCTUREBASE_SMTP_FROM_EMAIL",
    ]
    values = {key: env_value(key) for key in keys}
    configured = [key for key, value in values.items() if value]
    if not configured:
        return [result("smtp", "warn", "SMTP is not configured; email sending will be disabled.")]
    if len(configured) != len(keys):
        missing = [key for key in keys if not values[key]]
        return [result("smtp", "fail", f"Partial SMTP config. Missing: {', '.join(missing)}")]
    if not connect:
        return [result("smtp", "pass", "SMTP env vars are complete. Use --connections to authenticate.")]
    try:
        port = int(values["STRUCTUREBASE_SMTP_PORT"])
        with smtplib.SMTP(values["STRUCTUREBASE_SMTP_HOST"], port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(values["STRUCTUREBASE_SMTP_USERNAME"], values["STRUCTUREBASE_SMTP_PASSWORD"])
    except Exception as exc:
        return [result("smtp", "fail", f"SMTP login failed: {exc.__class__.__name__}: {exc}")]
    return [result("smtp", "pass", "SMTP login succeeded.")]


def check_url(base_url: str) -> list[CheckResult]:
    if not base_url:
        return []
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return [result("url", "fail", "Deployment URL must include http(s)://host.")]
    health_url = urljoin(base_url.rstrip("/") + "/", "healthz")
    try:
        with urlopen(health_url, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body)
            status = payload.get("status")
            if status != "ok":
                return [result("url_health", "fail", f"{health_url} returned status={status}: {body[:500]}")]
            return [result("url_health", "pass", f"{health_url} returned status=ok.")]
    except HTTPError as exc:
        return [result("url_health", "fail", f"{health_url} returned HTTP {exc.code}.")]
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [result("url_health", "fail", f"{health_url} failed: {exc.__class__.__name__}: {exc}")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Structurebase deployment environment and connections.")
    parser.add_argument("--env-file", default=".env", help="Optional env file to load before checks.")
    parser.add_argument("--skip-env", action="store_true", help="Only run live URL checks; skip local env validation.")
    parser.add_argument("--connections", action="store_true", help="Ping external services when credentials are configured.")
    parser.add_argument("--url", default="", help="Optional deployed base URL to health-check.")
    args = parser.parse_args()

    if not args.skip_env:
        load_dotenv(args.env_file)

    checks: list[CheckResult] = []
    if not args.skip_env:
        checks.extend(check_required_env())
        checks.extend(check_mongodb(args.connections))
        checks.extend(check_cloudinary(args.connections))
        checks.extend(check_smtp(args.connections))
    checks.extend(check_url(args.url))

    failed = False
    for check in checks:
        print(f"[{check.status.upper()}] {check.name}: {check.detail}")
        failed = failed or check.status == "fail"
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
