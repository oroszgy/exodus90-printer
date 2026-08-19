"""Self-contained Web UI for the Home Assistant app.

Serves a single page with a *Print today's reading* button, a login form for
the passwordless OTP flow, and a command box for debugging. Uses only the
Python standard library so the app image needs no extra web server; it shells
out to the ``exodus90`` CLI for the heavy lifting.
"""

from __future__ import annotations

import subprocess
import threading
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from markdown import markdown as markdown_to_html  # type: ignore[import-untyped]

from exodus90_printer.auth import CodeForm, request_otp, verify_otp
from exodus90_printer.client import ExodusClient
from exodus90_printer.config import Settings
from exodus90_printer.exceptions import AuthError, ExodusError
from exodus90_printer.models import Day, Reading
from exodus90_printer.render.pdf import render_pdf
from exodus90_printer.render.util import output_stem
from exodus90_printer.scraper import discover_program_id, fetch_days, fetch_reading, find_day


def run_print(target_date: str | None = None, timeout: int = 180) -> tuple[int, str]:
    """Run ``exodus90 print`` and return ``(returncode, combined output)``."""
    command = ["exodus90", "print"]
    if target_date:
        command += ["--date", target_date]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ExodusError("`exodus90 print` timed out.") from exc
    return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()


def run_command(command: str, timeout: int = 60) -> tuple[int, str]:
    """Run an arbitrary shell command (debugging) and return ``(code, output)``."""
    try:
        result = subprocess.run(
            ["bash", "-lc", command], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise ExodusError(f"Command timed out: {command}") from exc
    return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()


def _session_ok(settings: Settings) -> bool:
    with ExodusClient(settings) as client:
        return client.is_authenticated()


def _resolve_program_id(client: ExodusClient, settings: Settings) -> int:
    return settings.program_id if settings.program_id is not None else discover_program_id(client)


def render_days_list(days: list[Day]) -> str:
    """HTML fragment for the days list card."""
    today = date.today()
    rows = []
    for day in days:
        if day.date < today:
            row_class = ' class="past"'
        elif day.date == today:
            row_class = ' class="today"'
        else:
            row_class = ""
        ref = f"<span class='scripture'>{escape(day.scripture)}</span>" if day.scripture else ""
        rows.append(
            "<tr" + row_class + ">"
            f"<td class='date'>{escape(day.date.isoformat())}</td>"
            f"<td class='title'>{escape(day.title)}</td>"
            f"<td>{ref}</td>"
            "<td class='actions'>"
            f'<button type="button" class="day-print" data-date="{day.date.isoformat()}">'
            "Print</button> "
            f'<a class="day-pdf" href="pdf/{day.date.isoformat()}">Download PDF</a> '
            f'<a href="reading/{day.date.isoformat()}" target="_blank" rel="noopener">View</a>'
            "</td>"
            "</tr>"
        )
    return "<table class='days'><tbody>" + "".join(rows) + "</tbody></table>"


def render_reading_page(reading: Reading) -> str:
    """A standalone, print-ready HTML page for a reading."""
    header = reading.day.date.isoformat()
    if reading.day.scripture:
        header = f"{header} · {reading.day.scripture}"
    body_html = markdown_to_html(reading.body, extensions=["extra"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(reading.day.title)} — Exodus90</title>
<style>
  :root {{ --text:#111; --muted:#555; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: Georgia, 'Liberation Serif', serif; color:var(--text);
    background:#fff; line-height:1.6; }}
  main {{ max-width:720px; margin:0 auto; padding:2rem 1.5rem; }}
  h1 {{ font-size:1.8rem; margin:0 0 .2rem; }}
  .meta {{ color:var(--muted); margin:0 0 1.5rem; }}
  .reader h1, .reader h2, .reader h3 {{ font-family: system-ui, sans-serif; }}
  .reader blockquote {{ margin-left:1.2em; color:var(--muted); }}
  .reader img, .reader svg {{ max-width:100%; height:auto; }}
  button {{ font:inherit; padding:.4rem .8rem; cursor:pointer; }}
</style>
</head>
<body>
<main>
  <button type="button" onclick="window.print()">Print this page</button>
  <h1>{escape(reading.day.title)}</h1>
  <p class="meta">{escape(header)}</p>
  <div class="reader">
  {body_html}
  </div>
</main>
</body>
</html>
"""


class WebUI:
    """Backing logic for the web page; kept separate from HTTP for testability."""

    def __init__(self, settings: Settings, prefill_email: str = "") -> None:
        self.settings = settings
        self.prefill_email = prefill_email
        self._code_form: CodeForm | None = None
        self._lock = threading.Lock()

    def _program_days(self) -> list[Day] | None:
        """The program's day list, or ``None`` when not authenticated."""
        if not _session_ok(self.settings):
            return None
        with ExodusClient(self.settings) as client:
            program_id = _resolve_program_id(client, self.settings)
            return fetch_days(client, program_id)

    def _status_from_days(self, days: list[Day] | None) -> str:
        if days is None:
            return "<p class='status warn'>Not logged in. Use the login form below.</p>"
        try:
            today = find_day(days, date.today())
        except ExodusError:
            return (
                "<p class='status warn'>Authenticated, but today's reading "
                "could not be determined.</p>"
            )
        ref = f" — {escape(today.scripture)}" if today.scripture else ""
        return (
            f"<p class='status ok'>Authenticated. Today's reading: "
            f"<strong>{escape(today.title)}</strong>{ref}</p>"
        )

    def page_html(self) -> str:
        try:
            days = self._program_days()
            authenticated = days is not None
            status_html = self._status_from_days(days)
        except ExodusError:
            days = None
            authenticated = _session_ok(self.settings)
            status_html = "<p class='status warn'>The reading list could not be fetched.</p>"
        days_html = render_days_list(days) if days else "<p>Log in to see the day list.</p>"
        return render_page(
            status_html=status_html,
            days_html=days_html,
            prefill_email=self.prefill_email,
            authenticated=authenticated,
        )

    def status(self) -> str:
        """HTML fragment describing authentication and today's reading."""
        try:
            days = self._program_days()
        except ExodusError:
            return (
                "<p class='status warn'>Authenticated, but today's reading "
                "could not be determined.</p>"
            )
        return self._status_from_days(days)

    def days_html(self) -> str:
        """HTML fragment for the days list card."""
        try:
            days = self._program_days()
        except ExodusError:
            return "<p class='status warn'>The reading list could not be fetched.</p>"
        if days is None:
            return "<p>Log in to see the day list.</p>"
        return render_days_list(days)

    def reading_html(self, target: str) -> str:
        """A standalone HTML page for the reading of the given date."""
        try:
            target_date = date.fromisoformat(target)
        except ValueError as exc:
            raise ExodusError(f"Invalid date '{target}'; expected YYYY-MM-DD.") from exc
        days = self._program_days()
        if days is None:
            raise AuthError("Not logged in.")
        day = find_day(days, target_date)
        with ExodusClient(self.settings) as client:
            program_id = _resolve_program_id(client, self.settings)
            reading = fetch_reading(client, day, program_id)
        return render_reading_page(reading)

    def pdf_bytes(self, target_date: str) -> tuple[str, bytes]:
        """A freshly generated PDF for the reading of the given date."""
        try:
            target = date.fromisoformat(target_date)
        except ValueError as exc:
            raise ExodusError(f"Invalid date '{target_date}'; expected YYYY-MM-DD.") from exc
        days = self._program_days()
        if days is None:
            raise AuthError("Not logged in.")
        day = find_day(days, target)
        with ExodusClient(self.settings) as client:
            program_id = _resolve_program_id(client, self.settings)
            reading = fetch_reading(client, day, program_id)
        return f"{output_stem(reading)}.pdf", render_pdf(reading, self.settings)

    def print_reading(self, target_date: str | None = None) -> tuple[int, str]:
        return run_print(target_date)

    def command(self, command: str) -> tuple[int, str]:
        return run_command(command)

    def login(self, email: str) -> str:
        """Request a verification code; the code form is kept for ``verify``."""
        with ExodusClient(self.settings) as client:
            code_form = request_otp(client, email)
        with self._lock:
            self._code_form = code_form
        return f"A verification code was emailed to {email}. Enter it below."

    def verify(self, code: str) -> str:
        with self._lock:
            code_form = self._code_form
        if code_form is None:
            raise AuthError("Request a verification code first.")
        with ExodusClient(self.settings) as client:
            verify_otp(client, code_form, code)
            client.save_session()
        return "Authenticated. Session saved."


def render_page(status_html: str, days_html: str, prefill_email: str, authenticated: bool) -> str:
    """Return the full HTML page, with the login card hidden when logged in."""
    hidden = "hidden" if authenticated else ""
    prefill = escape(prefill_email)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exodus90 Printer</title>
<style>
  :root {{
    --app-bg: var(--primary-background-color, #fafafa);
    --app-card: var(--card-background-color, #ffffff);
    --app-text: var(--primary-text-color, #212121);
    --app-muted: var(--secondary-text-color, #727272);
    --app-disabled: var(--disabled-text-color, #bdbdbd);
    --app-accent: var(--primary-color, #03a9f4);
    --app-accent-rgb: var(--rgb-primary-color, 3, 169, 244);
    --app-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
    --app-text-on-accent: var(--text-primary-color, #ffffff);
    --app-success: var(--success-color, #43a047);
    --app-warning: var(--warning-color, #ffa600);
    --app-error: var(--error-color, #db4437);
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: system-ui, -apple-system, sans-serif;
    background:var(--app-bg); color:var(--app-text); }}
  main {{ max-width:720px; margin:0 auto; padding:1.5rem; }}
  h1 {{ font-size:1.4rem; margin:0 0 1rem; }}
  h2 {{ font-size:1rem; margin:0 0 .5rem; }}
  .card {{ background:var(--app-card); border-radius:.5rem; padding:1rem; margin-bottom:1rem; }}
  .status.ok {{ color:var(--app-success); }}
  .status.warn {{ color:var(--app-warning); }}
  table.days {{ width:100%; border-collapse:collapse; }}
  table.days th, table.days td {{ text-align:left; padding:.4rem .5rem;
    border-bottom:1px solid var(--app-divider); vertical-align:top; }}
  table.days tr.today td {{ background:rgba(var(--app-accent-rgb), 0.12); }}
  table.days tr.past td {{ color:var(--app-disabled); }}
  table.days tr.past td.actions {{ color:var(--app-text); }}
  table.days .date {{ white-space:nowrap; color:var(--app-muted); font-size:.85rem; }}
  table.days .scripture {{ color:var(--app-muted); font-size:.85rem; }}
  table.days .actions {{ white-space:nowrap; text-align:right; }}
  table.days a {{ color:var(--app-accent); margin-left:.5rem; }}
  table.days .actions a.day-pdf {{
    display:inline-block; margin-left:.5rem; padding:.3rem .6rem;
    border:1px solid var(--app-accent); border-radius:.25rem;
    color:var(--app-accent); text-decoration:none; font-size:.85rem;
  }}
  table.days .actions a.day-pdf:hover {{
    background:var(--app-accent); color:var(--app-text-on-accent);
  }}
  .result pre {{ white-space:pre-wrap; background:var(--app-bg); padding:.75rem;
    border-radius:.25rem; font-size:.8rem; max-height:18rem; overflow:auto; }}
  .result.fail pre {{ color:var(--app-error); }}
  button, input {{ font:inherit; }}
  button {{ background:var(--app-accent); border:0; color:var(--app-text-on-accent);
    padding:.5rem 1rem; border-radius:.25rem; cursor:pointer; }}
  button:disabled {{ opacity:.6; cursor:wait; }}
  input {{ background:var(--app-card); color:var(--app-text);
    border:1px solid var(--app-divider); padding:.5rem; border-radius:.25rem;
    width:100%; margin-bottom:.5rem; }}
  label {{ display:block; color:var(--app-muted); font-size:.85rem; margin-bottom:1rem; }}
  form {{ margin:0; }}
  [hidden] {{ display:none; }}
</style>
</head>
<body>
<main>
  <h1>Exodus90 Printer</h1>
  <section class="card" id="status">{status_html}</section>

  <section class="card">
    <button id="print-btn" type="button">Print today's reading</button>
    <div class="result" id="print-result"></div>
  </section>

  <section class="card" id="days-card">
    <h2>Days</h2>
    <div id="days">{days_html}</div>
    <div class="result" id="day-print-result"></div>
  </section>

  <section class="card" id="login-card" {hidden}>
    <h2>Login</h2>
    <form id="login-form">
      <label>Email
        <input type="email" name="email" required value="{prefill}" placeholder="you@example.com">
      </label>
      <button type="submit">Send verification code</button>
    </form>
    <form id="code-form" hidden>
      <label>Verification code
        <input type="text" name="code" inputmode="numeric" required autocomplete="one-time-code">
      </label>
      <button type="submit">Verify</button>
    </form>
    <div class="result" id="login-result"></div>
  </section>

  <section class="card">
    <h2>Run a command</h2>
    <form id="cmd-form">
      <input name="command" placeholder="exodus90 days" autocomplete="off">
      <button type="submit">Run</button>
    </form>
    <div class="result" id="cmd-result"></div>
  </section>
</main>
<script>
  function post(path, data) {{
    return fetch(path, {{ method: "POST", body: new URLSearchParams(data) }}).then(r => r.text());
  }}

  var printBtn = document.getElementById("print-btn");
  var printResult = document.getElementById("print-result");
  printBtn.addEventListener("click", function () {{
    printBtn.disabled = true;
    printResult.innerHTML = "<pre>Printing…</pre>";
    post("print", {{}}).then(function (html) {{
      printResult.innerHTML = html;
      printBtn.disabled = false;
    }}).catch(function () {{
      printResult.innerHTML = "<p class='fail'>Request failed.</p>";
      printBtn.disabled = false;
    }});
  }});

  var dayPrintResult = document.getElementById("day-print-result");
  document.querySelectorAll(".day-print").forEach(function (btn) {{
    btn.addEventListener("click", function () {{
      btn.disabled = true;
      post("print", {{ date: btn.dataset.date }}).then(function (html) {{
        dayPrintResult.innerHTML = html;
        btn.disabled = false;
      }}).catch(function () {{
        dayPrintResult.innerHTML = "<p class='fail'>Request failed.</p>";
        btn.disabled = false;
      }});
    }});
  }});

  var loginForm = document.getElementById("login-form");
  var codeForm = document.getElementById("code-form");
  var loginResult = document.getElementById("login-result");
  loginForm.addEventListener("submit", function (e) {{
    e.preventDefault();
    var data = new FormData(loginForm);
    post("login", {{ email: data.get("email") }}).then(function (html) {{
      loginResult.innerHTML = html;
      codeForm.hidden = false;
    }});
  }});
  codeForm.addEventListener("submit", function (e) {{
    e.preventDefault();
    var data = new FormData(codeForm);
    post("verify", {{ code: data.get("code") }}).then(function (html) {{
      loginResult.innerHTML = html;
    }});
  }});

  var cmdForm = document.getElementById("cmd-form");
  var cmdResult = document.getElementById("cmd-result");
  cmdForm.addEventListener("submit", function (e) {{
    e.preventDefault();
    var data = new FormData(cmdForm);
    cmdResult.innerHTML = "<pre>Running…</pre>";
    post("cmd", {{ command: data.get("command") }}).then(function (html) {{
      cmdResult.innerHTML = html;
    }});
  }});
</script>
</body>
</html>
"""


def _result_html(action: str, code: int, output: str) -> str:
    heading = {"print": "Print", "login": "Login", "verify": "Verify", "cmd": "Command"}.get(
        action, action
    )
    label = output or ("Done." if code == 0 else "Failed.")
    css = "ok" if code == 0 else "fail"
    return f"<div class='result {css}'><strong>{heading}</strong><pre>{escape(label)}</pre></div>"


def _error_page(message: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Not found</title>
</head>
<body>
<p>{escape(message)}</p>
<p><a href="../">Back to the main page</a></p>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    server: _WebServer

    def log_message(self, format: str, *args: object) -> None:
        if not args or str(args[0]) != "200":
            super().log_message(format, *args)

    def _send(
        self,
        body: str | bytes,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
        headers: dict[str, str] | None = None,
    ) -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _send_pdf(self, filename: str, data: bytes) -> None:
        self._send(
            data,
            content_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        return {key: values[-1] for key, values in parse_qs(raw).items()}

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(self.server.ui.page_html())
        elif self.path == "/status":
            self._send(self.server.ui.status())
        elif self.path.startswith("/reading/"):
            ui = self.server.ui
            try:
                self._send(ui.reading_html(self.path[len("/reading/") :]))
            except (ExodusError, AuthError) as exc:
                self._send(_error_page(str(exc)), status=404)
        elif self.path.startswith("/pdf/"):
            ui = self.server.ui
            try:
                filename, data = ui.pdf_bytes(self.path[len("/pdf/") :])
            except (ExodusError, AuthError) as exc:
                self._send(_error_page(str(exc)), status=404)
            else:
                self._send_pdf(filename, data)
        else:
            self._send("Not found", status=404)

    def do_POST(self) -> None:
        form = self._form()
        ui = self.server.ui
        if self.path == "/print":
            try:
                code, output = ui.print_reading(form.get("date") or None)
            except ExodusError as exc:
                self._send(_result_html("print", 1, str(exc)))
            else:
                self._send(_result_html("print", code, output))
        elif self.path == "/cmd":
            try:
                code, output = ui.command(form.get("command", ""))
            except ExodusError as exc:
                self._send(_result_html("cmd", 1, str(exc)))
            else:
                self._send(_result_html("cmd", code, output))
        elif self.path == "/login":
            try:
                message = ui.login(form.get("email", ""))
            except ExodusError as exc:
                self._send(_result_html("login", 1, str(exc)))
            else:
                self._send(_result_html("login", 0, message))
        elif self.path == "/verify":
            try:
                message = ui.verify(form.get("code", ""))
            except ExodusError as exc:
                self._send(_result_html("verify", 1, str(exc)))
            else:
                self._send(_result_html("verify", 0, message))
        else:
            self._send("Not found", status=404)


class _WebServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], ui: WebUI) -> None:
        super().__init__(address, _Handler)
        self.ui = ui


def run_server(
    settings: Settings,
    host: str = "0.0.0.0",
    port: int = 8099,
    prefill_email: str = "",
) -> None:
    """Start the Web UI and serve until interrupted."""
    server = _WebServer((host, port), WebUI(settings, prefill_email=prefill_email))
    try:
        server.serve_forever()
    finally:
        server.server_close()
