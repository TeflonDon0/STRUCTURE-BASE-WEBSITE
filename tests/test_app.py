import os

import pytest

from app import app, check_admin_credentials, safe_redirect_target


@pytest.fixture(autouse=True)
def reset_login_attempts() -> None:
    app.extensions.pop("login_attempts", None)
    yield
    app.extensions.pop("login_attempts", None)


@pytest.fixture
def client() -> object:
    return app.test_client()


def test_healthz_returns_ok(client) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"


def test_safe_redirect_target_rejects_external_redirects() -> None:
    with app.test_request_context("/login?next=https://evil.example.com"):
        assert safe_redirect_target("https://evil.example.com") == "/dashboard"


def test_login_success_redirects_to_dashboard(client) -> None:
    with client.session_transaction() as session:
        session["_csrf_token"] = "test-token"

    response = client.post(
        "/login",
        data={
            "username": app.config["ADMIN_USERNAME"],
            "password": app.config["ADMIN_PASSWORD"],
            "csrf_token": "test-token",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"


def test_login_rate_limit_blocks_after_five_failures(client) -> None:
    for _ in range(5):
        with client.session_transaction() as session:
            session["_csrf_token"] = "test-token"

        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": "wrong-password",
                "csrf_token": "test-token",
            },
            follow_redirects=False,
        )

        assert response.status_code in {200, 302}

    response = client.post(
        "/login",
        data={
            "username": "admin",
            "password": "wrong-password",
            "csrf_token": "test-token",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert b"Too many sign-in attempts" in response.data


def test_production_rejects_default_admin_password(monkeypatch) -> None:
    monkeypatch.setitem(app.config, "IS_PRODUCTION", True)
    monkeypatch.setitem(app.config, "ADMIN_USERNAME", "admin")
    monkeypatch.setitem(app.config, "ADMIN_PASSWORD", "change-me-structurebase")
    monkeypatch.setitem(app.config, "ADMIN_PASSWORD_HASH", "")

    assert check_admin_credentials("admin", "change-me-structurebase") is False
