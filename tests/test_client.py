"""Tests for HTTP client auth detection and session handling."""

from __future__ import annotations

import httpx
import pytest
import respx

from exodus90_printer.client import ExodusClient
from exodus90_printer.config import Settings
from exodus90_printer.exceptions import SessionExpiredError


def test_redirect_to_login_raises_session_expired(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://app.exodus90.com/today").mock(
        return_value=httpx.Response(302, headers={"location": "/auth/login?src=%2Ftoday"})
    )
    with ExodusClient(Settings()) as client, pytest.raises(SessionExpiredError):
        client.get("/today")


def test_ok_response_is_returned(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://app.exodus90.com/today").mock(
        return_value=httpx.Response(200, text="<html>ok</html>")
    )
    with ExodusClient(Settings()) as client:
        response = client.get("/today")
    assert response.status_code == 200


def test_is_authenticated(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://app.exodus90.com/today").mock(
        return_value=httpx.Response(200, text="ok")
    )
    with ExodusClient(Settings()) as client:
        assert client.is_authenticated() is True


def test_is_authenticated_false_on_redirect(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://app.exodus90.com/today").mock(
        return_value=httpx.Response(302, headers={"location": "/auth/login?src=%2Ftoday"})
    )
    with ExodusClient(Settings()) as client:
        assert client.is_authenticated() is False
