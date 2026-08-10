"""Tests for the OTP login flow using real saved pages as fixtures."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from exodus90_printer.auth import (
    CodeForm,
    _find_code_form,
    _find_login_form,
    request_otp,
    verify_otp,
)
from exodus90_printer.exceptions import AuthError, SessionExpiredError

FIXTURES = Path(__file__).parent / "fixtures"
LOGIN_PAGE = (FIXTURES / "login_page.html").read_text()
CODE_PAGE = (FIXTURES / "code_page.html").read_text()


class _Response:
    def __init__(
        self,
        text: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = httpx.Headers(headers or {})


class _FakeClient:
    def __init__(self) -> None:
        self.pages: dict[str, _Response] = {}
        self.post_response: _Response | None = None
        self.post_error: Exception | None = None
        self.authenticated = True
        self.posts: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, **_kwargs: object) -> _Response:
        try:
            return self.pages[path]
        except KeyError as exc:
            raise AssertionError(f"Unexpected GET {path}") from exc

    def post(self, path: str, data: dict[str, str] | None = None, **_: object) -> _Response:
        self.posts.append((path, data or {}))
        if self.post_error is not None:
            raise self.post_error
        if self.post_response is not None:
            return self.post_response
        raise AssertionError("No post_response configured")

    def is_authenticated(self) -> bool:
        return self.authenticated


def test_find_login_form_detects_login_form() -> None:
    action, hidden = _find_login_form(LOGIN_PAGE)
    assert action == "/auth/login"
    assert "authenticity_token" in hidden


def test_find_code_form_detects_code_form() -> None:
    code_form = _find_code_form(CODE_PAGE)
    assert code_form.action == "/auth/code"
    assert code_form.code_field == "code"
    assert "authenticity_token" in code_form.fields
    assert "timezone" in code_form.fields


def test_request_otp_follows_redirect_to_code_page() -> None:
    client = _FakeClient()
    client.pages["/auth/login"] = _Response(LOGIN_PAGE)
    client.pages["/auth/code"] = _Response(CODE_PAGE)
    client.post_response = _Response("", status_code=302, headers={"Location": "/auth/code"})
    code_form = request_otp(client, "oroszgy@gmail.com")  # type: ignore[arg-type]
    assert isinstance(code_form, CodeForm)
    assert code_form.code_field == "code"
    assert ("/auth/login", "oroszgy@gmail.com") in [(p, d["email"]) for p, d in client.posts]


def test_request_otp_bad_email_raises_auth_error() -> None:
    client = _FakeClient()
    client.pages["/auth/login"] = _Response(LOGIN_PAGE)
    client.post_error = SessionExpiredError("The Exodus 90 session has expired.")
    with pytest.raises(AuthError):
        request_otp(client, "bad@example.com")  # type: ignore[arg-type]


def test_verify_otp_success() -> None:
    client = _FakeClient()
    client.post_response = _Response("", status_code=302, headers={"Location": "/today"})
    code_form = CodeForm(
        action="/auth/code", fields={"authenticity_token": "tok"}, code_field="code"
    )
    verify_otp(client, code_form, "123-456")  # type: ignore[arg-type]
    assert client.posts[0][1]["code"] == "123-456"


def test_verify_otp_bad_length_raises() -> None:
    code_form = CodeForm(action="/auth/code", fields={}, code_field="code")
    with pytest.raises(AuthError):
        verify_otp(object(), code_form, "123")  # type: ignore[arg-type]


def test_verify_otp_wrong_code_raises_auth_error() -> None:
    client = _FakeClient()
    client.post_error = SessionExpiredError("The Exodus 90 session has expired.")
    code_form = CodeForm(action="/auth/code", fields={}, code_field="code")
    with pytest.raises(AuthError):
        verify_otp(client, code_form, "000-000")  # type: ignore[arg-type]
