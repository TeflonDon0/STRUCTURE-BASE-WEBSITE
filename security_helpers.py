from __future__ import annotations

import time
from urllib.parse import urlsplit

from werkzeug.security import check_password_hash


def is_default_admin_password(app, default_password: str) -> bool:
    return (
        not app.config["ADMIN_PASSWORD_HASH"]
        and app.config["ADMIN_PASSWORD"] == default_password
    )


def check_admin_credentials(
    app,
    username: str,
    password: str,
    default_username: str,
    default_password: str,
) -> bool:
    if (
        app.config["IS_PRODUCTION"]
        and app.config["ADMIN_USERNAME"] == default_username
        and is_default_admin_password(app, default_password)
    ):
        return False

    if username != app.config["ADMIN_USERNAME"]:
        return False

    if app.config["ADMIN_PASSWORD_HASH"]:
        return check_password_hash(app.config["ADMIN_PASSWORD_HASH"], password)

    return password == app.config["ADMIN_PASSWORD"]


def safe_redirect_target(target: str | None, request_host: str, url_for_func) -> str:
    if not target:
        return url_for_func("dashboard")

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        if parsed.netloc and parsed.netloc != request_host:
            return url_for_func("dashboard")
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"

    if not target.startswith("/") or target.startswith("//"):
        return url_for_func("dashboard")

    return target


def admin_return_target(default_endpoint: str, request, url_for_func) -> str:
    target = request.form.get("next") if request.method == "POST" else request.args.get("next")
    if target:
        return safe_redirect_target(target, request.host, url_for_func)
    return url_for_func(default_endpoint)


def client_ip(request) -> str:
    return request.remote_addr or "unknown"


def login_rate_limit_store(app) -> dict[str, list[float]]:
    return app.extensions.setdefault("login_attempts", {})


def login_rate_limit_key(username: str, request) -> str:
    normalized = username.strip().lower() or "anonymous"
    return f"{request.remote_addr or 'unknown'}::{normalized}"


def prune_login_attempts(app, key: str, window_seconds: int, now: float | None = None) -> list[float]:
    cutoff = (now if now is not None else time.time()) - window_seconds
    attempts = [stamp for stamp in login_rate_limit_store(app).get(key, []) if stamp >= cutoff]
    login_rate_limit_store(app)[key] = attempts
    return attempts


def login_is_rate_limited(app, username: str, request, window_seconds: int) -> bool:
    attempts = prune_login_attempts(app, login_rate_limit_key(username, request), window_seconds)
    return len(attempts) >= app.config["LOGIN_MAX_ATTEMPTS"]


def record_failed_login(app, username: str, request, now: float | None = None) -> None:
    key = login_rate_limit_key(username, request)
    attempts = prune_login_attempts(app, key, app.config["LOGIN_WINDOW_SECONDS"], now)
    attempts.append(now if now is not None else time.time())
    login_rate_limit_store(app)[key] = attempts


def reset_failed_login(app, username: str, request) -> None:
    login_rate_limit_store(app).pop(login_rate_limit_key(username, request), None)
