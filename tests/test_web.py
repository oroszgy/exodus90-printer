"""Tests for the Web UI (``exodus90_printer.web``)."""

from __future__ import annotations

import http.client
import subprocess
import threading
from collections.abc import Callable
from datetime import date

import pytest

from exodus90_printer import web
from exodus90_printer.auth import CodeForm
from exodus90_printer.config import Settings
from exodus90_printer.exceptions import AuthError, ExodusError
from exodus90_printer.models import Day, Reading
from exodus90_printer.web import WebUI, render_page, run_command, run_print

TODAY = date.today()


class _FakeClient:
    def __init__(self) -> None:
        self.authenticated = True
        self.saved = False

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def is_authenticated(self) -> bool:
        return self.authenticated

    def save_session(self) -> None:
        self.saved = True


class _Result:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _day() -> Day:
    return Day(day_id="program_day_1", date=TODAY, title="Trust and Obey", scripture="Kiv 14,10-20")


def _two_days() -> list[Day]:
    return [
        Day(day_id="program_day_1", date=date(2026, 8, 1), title="Alpha", scripture="Kiv 1,1"),
        Day(day_id="program_day_2", date=date(2026, 8, 2), title="Beta", scripture=None),
    ]


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(web, "ExodusClient", lambda _settings: client)
    return client


def test_render_page_contains_print_button() -> None:
    page = render_page(
        status_html="<p>ok</p>", days_html="<p>days</p>", prefill_email="", authenticated=False
    )
    assert "Print today's reading" in page
    assert 'id="print-btn"' in page
    assert 'id="login-card" ' in page
    assert 'id="days-card"' in page


def test_render_page_hides_login_when_authenticated() -> None:
    page = render_page(status_html="<p>ok</p>", days_html="", prefill_email="", authenticated=True)
    assert 'id="login-card" hidden' in page


def test_render_page_escapes_prefill_email() -> None:
    page = render_page(
        status_html="<p>ok</p>", days_html="", prefill_email='"><script>', authenticated=False
    )
    assert 'value="&quot;&gt;&lt;script&gt;"' in page
    assert 'value=""><script>"' not in page


def test_status_authenticated_shows_reading(
    monkeypatch: pytest.MonkeyPatch, make_settings: Callable[..., Settings]
) -> None:
    ui = WebUI(make_settings())
    monkeypatch.setattr(ui, "_program_days", lambda: [_day()])
    status = ui.status()
    assert "Authenticated" in status
    assert "Trust and Obey" in status


def test_status_not_authenticated(
    monkeypatch: pytest.MonkeyPatch, make_settings: Callable[..., Settings]
) -> None:
    ui = WebUI(make_settings())
    monkeypatch.setattr(ui, "_program_days", lambda: None)
    assert "Not logged in" in ui.status()


def test_status_reading_error_falls_back(
    monkeypatch: pytest.MonkeyPatch, make_settings: Callable[..., Settings]
) -> None:
    def boom() -> list[Day]:
        raise ExodusError("could not determine program")

    ui = WebUI(make_settings())
    monkeypatch.setattr(ui, "_program_days", boom)
    assert "could not be determined" in ui.status()


def test_program_days_uses_pinned_program(
    fake_client: _FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    make_settings: Callable[..., Settings],
) -> None:
    settings = make_settings(program_id=208)
    days = [_day()]
    monkeypatch.setattr(web, "_session_ok", lambda _settings: True)
    monkeypatch.setattr(web, "fetch_days", lambda _client, program_id: days)
    assert WebUI(settings)._program_days() == days


def test_program_days_auto_discovers_program(
    fake_client: _FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    make_settings: Callable[..., Settings],
) -> None:
    settings = make_settings(program_id=None)
    days = [_day()]
    monkeypatch.setattr(web, "_session_ok", lambda _settings: True)
    monkeypatch.setattr(web, "discover_program_id", lambda _client: 198)
    monkeypatch.setattr(web, "fetch_days", lambda _client, program_id: days)
    assert WebUI(settings)._program_days() == days


def test_program_days_none_when_not_authenticated(
    fake_client: _FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    make_settings: Callable[..., Settings],
) -> None:
    monkeypatch.setattr(web, "_session_ok", lambda _settings: False)
    assert WebUI(make_settings())._program_days() is None


def test_days_html_renders_rows(
    monkeypatch: pytest.MonkeyPatch, make_settings: Callable[..., Settings]
) -> None:
    ui = WebUI(make_settings())
    monkeypatch.setattr(ui, "_program_days", lambda: _two_days())
    html = ui.days_html()
    assert "Alpha" in html
    assert "Beta" in html
    assert 'data-date="2026-08-01"' in html
    assert "reading/2026-08-01" in html
    assert 'href="/reading/' not in html


def test_days_html_not_authenticated(
    monkeypatch: pytest.MonkeyPatch, make_settings: Callable[..., Settings]
) -> None:
    ui = WebUI(make_settings())
    monkeypatch.setattr(ui, "_program_days", lambda: None)
    assert "Log in to see the day list" in ui.days_html()


def test_reading_html_renders_markdown(
    fake_client: _FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    make_settings: Callable[..., Settings],
) -> None:
    day = _day()
    reading = Reading(day=day, program_id=208, body="# Title\n\nSome **bold** text.")
    ui = WebUI(make_settings())
    monkeypatch.setattr(ui, "_program_days", lambda: [day])
    monkeypatch.setattr(web, "fetch_reading", lambda _client, d, pid: reading)
    html = ui.reading_html(TODAY.isoformat())
    assert "<h1>Trust and Obey</h1>" in html
    assert "<strong>bold</strong>" in html


def test_reading_html_invalid_date(
    monkeypatch: pytest.MonkeyPatch, make_settings: Callable[..., Settings]
) -> None:
    with pytest.raises(ExodusError, match="Invalid date"):
        WebUI(make_settings()).reading_html("not-a-date")


def test_reading_html_requires_login(
    monkeypatch: pytest.MonkeyPatch, make_settings: Callable[..., Settings]
) -> None:
    ui = WebUI(make_settings())
    monkeypatch.setattr(ui, "_program_days", lambda: None)
    with pytest.raises(AuthError, match="Not logged in"):
        ui.reading_html(TODAY.isoformat())


def test_login_requests_otp_and_keeps_form(
    fake_client: _FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    make_settings: Callable[..., Settings],
) -> None:
    code_form = CodeForm(action="/auth/code", fields={}, code_field="code")
    monkeypatch.setattr(web, "request_otp", lambda _client, _email: code_form)
    ui = WebUI(make_settings())
    message = ui.login("me@example.com")
    assert "me@example.com" in message
    assert ui._code_form is code_form


def test_verify_requires_login_first(
    fake_client: _FakeClient, make_settings: Callable[..., Settings]
) -> None:
    with pytest.raises(AuthError, match="Request a verification code first"):
        WebUI(make_settings()).verify("123-456")


def test_verify_verifies_and_saves_session(
    fake_client: _FakeClient,
    monkeypatch: pytest.MonkeyPatch,
    make_settings: Callable[..., Settings],
) -> None:
    ui = WebUI(make_settings())
    ui._code_form = CodeForm(action="/auth/code", fields={}, code_field="code")
    monkeypatch.setattr(web, "verify_otp", lambda _client, _form, _code: None)
    message = ui.verify("123-456")
    assert "Authenticated" in message
    assert fake_client.saved


def test_run_print_runs_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Result:
        calls.append(cmd)
        return _Result(stdout="print: /tmp/out.pdf")

    monkeypatch.setattr(web.subprocess, "run", fake_run)  # type: ignore[attr-defined]
    code, output = run_print()
    assert code == 0
    assert "print: /tmp/out.pdf" in output
    assert calls[0] == ["exodus90", "print"]


def test_run_print_with_date(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Result:
        calls.append(cmd)
        return _Result(stdout="print: /tmp/out.pdf")

    monkeypatch.setattr(web.subprocess, "run", fake_run)  # type: ignore[attr-defined]
    code, output = run_print("2026-08-10")
    assert code == 0
    assert calls[0] == ["exodus90", "print", "--date", "2026-08-10"]


def test_run_command_runs_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Result:
        calls.append(cmd)
        return _Result(stdout="day list")

    monkeypatch.setattr(web.subprocess, "run", fake_run)  # type: ignore[attr-defined]
    code, output = run_command("exodus90 days")
    assert code == 0
    assert output == "day list"
    assert calls[0] == ["bash", "-lc", "exodus90 days"]


def test_run_print_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> _Result:
        raise subprocess.TimeoutExpired("exodus90", 180)

    monkeypatch.setattr(web.subprocess, "run", boom)  # type: ignore[attr-defined]
    with pytest.raises(ExodusError, match="timed out"):
        run_print()


def test_http_flow(monkeypatch: pytest.MonkeyPatch, make_settings: Callable[..., Settings]) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(web, "ExodusClient", lambda _settings: fake)
    monkeypatch.setattr(web, "_session_ok", lambda _settings: False)
    monkeypatch.setattr(web, "run_print", lambda date=None: (0, "print: ok"))
    code_form = CodeForm(action="/auth/code", fields={}, code_field="code")
    monkeypatch.setattr(web, "request_otp", lambda _client, _email: code_form)
    monkeypatch.setattr(web, "verify_otp", lambda _client, _form, _code: None)

    server = web._WebServer(("127.0.0.1", 0), WebUI(make_settings()))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)

        conn.request("GET", "/")
        response = conn.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "Print today's reading" in body
        assert "Not logged in" in body
        assert "Log in to see the day list" in body

        conn.request("POST", "/print", body="")
        response = conn.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "print: ok" in body
        assert "result ok" in body

        conn.request("POST", "/print", body="date=2026-08-10")
        response = conn.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "print: ok" in body

        conn.request("GET", "/reading/not-a-date")
        response = conn.getresponse()
        body = response.read().decode()
        assert response.status == 404
        assert "Invalid date" in body
        assert 'href="../"' in body

        conn.request("POST", "/login", body="email=me%40example.com")
        response = conn.getresponse()
        body = response.read().decode()
        assert "me@example.com" in body
        assert "result ok" in body

        conn.request("POST", "/verify", body="code=123456")
        response = conn.getresponse()
        body = response.read().decode()
        assert "Authenticated" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
