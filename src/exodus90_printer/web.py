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

from exodus90_printer.auth import CodeForm, request_otp, verify_otp
from exodus90_printer.client import ExodusClient
from exodus90_printer.config import Settings
from exodus90_printer.exceptions import AuthError, ExodusError
from exodus90_printer.scraper import discover_program_id, fetch_days, find_day


def run_print(timeout: int = 180) -> tuple[int, str]:
    """Run ``exodus90 print`` and return ``(returncode, combined output)``."""
    try:
        result = subprocess.run(
            ["exodus90", "print"], capture_output=True, text=True, timeout=timeout
        )
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


def _today_status(settings: Settings) -> str:
    """HTML fragment for today's reading title (assumes a valid session)."""
    with ExodusClient(settings) as client:
        program_id = (
            settings.program_id if settings.program_id is not None else discover_program_id(client)
        )
        day = find_day(fetch_days(client, program_id), date.today())
    ref = f" — {escape(day.scripture)}" if day.scripture else ""
    return f"<strong>{escape(day.title)}</strong>{ref}"


class WebUI:
    """Backing logic for the web page; kept separate from HTTP for testability."""

    def __init__(self, settings: Settings, prefill_email: str = "") -> None:
        self.settings = settings
        self.prefill_email = prefill_email
        self._code_form: CodeForm | None = None
        self._lock = threading.Lock()

    def page_html(self) -> str:
        authenticated = _session_ok(self.settings)
        return render_page(
            status_html=self.status(),
            prefill_email=self.prefill_email,
            authenticated=authenticated,
        )

    def status(self) -> str:
        """HTML fragment describing authentication and today's reading."""
        if not _session_ok(self.settings):
            return "<p class='status warn'>Not logged in. Use the login form below.</p>"
        try:
            today = _today_status(self.settings)
        except ExodusError:
            return (
                "<p class='status warn'>Authenticated, but today's reading "
                "could not be determined.</p>"
            )
        return f"<p class='status ok'>Authenticated. Today's reading: {today}</p>"

    def print_reading(self) -> tuple[int, str]:
        return run_print()

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


def render_page(status_html: str, prefill_email: str, authenticated: bool) -> str:
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
  :root {{ --bg:#0f172a; --card:#1e293b; --text:#e2e8f0; --muted:#94a3b8; --accent:#fd5925; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: system-ui, -apple-system, sans-serif;
    background:var(--bg); color:var(--text); }}
  main {{ max-width:720px; margin:0 auto; padding:1.5rem; }}
  h1 {{ font-size:1.4rem; margin:0 0 1rem; }}
  h2 {{ font-size:1rem; margin:0 0 .5rem; }}
  .card {{ background:var(--card); border-radius:.5rem; padding:1rem; margin-bottom:1rem; }}
  .status.ok {{ color:#86efac; }}
  .status.warn {{ color:#fde047; }}
  .result pre {{ white-space:pre-wrap; background:var(--bg); padding:.75rem; border-radius:.25rem;
    font-size:.8rem; max-height:18rem; overflow:auto; }}
  .result.fail pre {{ color:#fca5a5; }}
  button, input {{ font:inherit; }}
  button {{ background:var(--accent); border:0; color:#fff; padding:.5rem 1rem;
    border-radius:.25rem; cursor:pointer; }}
  button:disabled {{ opacity:.6; cursor:wait; }}
  input {{ background:var(--bg); color:var(--text); border:1px solid #334155; padding:.5rem;
    border-radius:.25rem; width:100%; margin-bottom:.5rem; }}
  label {{ display:block; color:var(--muted); font-size:.85rem; margin-bottom:1rem; }}
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


class _Handler(BaseHTTPRequestHandler):
    server: _WebServer

    def log_message(self, format: str, *args: object) -> None:
        if not args or str(args[0]) != "200":
            super().log_message(format, *args)

    def _send(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        return {key: values[-1] for key, values in parse_qs(raw).items()}

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(self.server.ui.page_html())
        elif self.path == "/status":
            self._send(self.server.ui.status())
        else:
            self._send("Not found", status=404)

    def do_POST(self) -> None:
        form = self._form()
        ui = self.server.ui
        if self.path == "/print":
            try:
                code, output = ui.print_reading()
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
