from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_ROUTES = ("/", "/properties", "/tenant-services", "/login")
AUTH_SHELL_ROUTES = {"/login", "/partners/login"}


@dataclass(frozen=True)
class RouteAudit:
    route: str
    status: str
    issues: list[str]
    metrics: dict[str, Any]


def fetch_text(url: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Structurebase UI audit"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return int(response.status), response.read().decode(charset, errors="replace")


def audit_html(route: str, html: str, status_code: int) -> RouteAudit:
    lower = html.lower()
    issues: list[str] = []
    if status_code != 200:
        issues.append(f"Unexpected status code {status_code}.")
    if "<main" not in lower:
        issues.append("Missing main landmark.")
    if "skip to main content" not in lower:
        issues.append("Missing skip link.")
    if "<title>" not in lower:
        issues.append("Missing page title.")
    if "document generator" in lower or "internal issue" in lower:
        issues.append("Client-visible internal wording detected.")
    if "todo" in lower:
        issues.append("TODO wording detected.")
    if "aria-label=\"open navigation\"" not in lower and route not in AUTH_SHELL_ROUTES:
        issues.append("Navigation toggle label not found.")

    metrics = {
        "bytes": len(html.encode("utf-8")),
        "forms": lower.count("<form"),
        "buttons": lower.count("<button"),
        "images": lower.count("<img"),
        "links": lower.count("<a "),
    }
    return RouteAudit(route=route, status="pass" if not issues else "fail", issues=issues, metrics=metrics)


def run(base_url: str, routes: tuple[str, ...], timeout: float) -> list[RouteAudit]:
    audits: list[RouteAudit] = []
    for route in routes:
        url = base_url.rstrip("/") + route
        try:
            status_code, html = fetch_text(url, timeout)
            audits.append(audit_html(route, html, status_code))
        except Exception as exc:  # pragma: no cover - CLI guardrail
            audits.append(RouteAudit(route=route, status="fail", issues=[str(exc)], metrics={}))
        time.sleep(0.05)
    return audits


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a lightweight HTML-level UI audit for key Structurebase routes.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Running local site URL.")
    parser.add_argument("--route", action="append", dest="routes", help="Route to audit. Can be passed multiple times.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Request timeout in seconds.")
    args = parser.parse_args()

    routes = tuple(args.routes or DEFAULT_ROUTES)
    audits = run(args.base_url, routes, args.timeout)
    print(json.dumps([audit.__dict__ for audit in audits], indent=2))
    return 1 if any(audit.status == "fail" for audit in audits) else 0


if __name__ == "__main__":
    sys.exit(main())
