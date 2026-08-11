# AGENTS.md

uv-managed Python 3.13 CLI (`uv_build` backend) that fetches the daily Exodus 90
reading from https://app.exodus90.com (Rails + Hotwire) and renders it as
Markdown/PDF/print. Runs daily from cron; `print` never prompts.

## Commands

```sh
uv sync --extra dev          # install deps
uv run pytest                # tests
uv run mypy src tests        # strict typing (must pass)
uv run ruff check .          # lint
uv run ruff format --check . # formatting
```

Run `format --check` → `check` → `mypy` → `pytest` before finishing. `uv run
exodus90 <cmd>` runs the CLI from source.

## Scraping protocol (easy to get wrong)

The app lazy-loads content via Turbo frames; `ExodusClient` has
`follow_redirects=False` and treats any 302 to `/auth/login` as
`SessionExpiredError`.

- **Days list**: GET `/programs/{program_id}/days` with header
  `Turbo-Frame: program_days_frame`. `/programs/{program_id}` itself returns no
  day buttons. Parse `button[data-reading-date]`; day id = `data-modal`,
  title = `p.text-left.grow`, scripture ref = `#{day_id} h2`.
- **Reading body**: GET `/readings/{day_id}` with header
  `Turbo-Frame: {day_id}_frame`; the Markdown lives in the
  `data-content` attribute of `div[data-reader-target=body]`.
- **lxml quirk**: on the live `/days` page, `get_text()` returns `""` for the
  modal h1/h2 (button titles are fine). Use `_element_text` (falls back to
  `Tag.string`) in `scraper.py`; don't "fix" it with another parser.

## Auth (auth.py)

- Passwordless OTP: POST `/auth/login` (fields `authenticity_token` hidden +
  `email`) → 302 to `/auth/code`; client doesn't auto-follow, so
  `request_otp` follows the Location header manually.
- Code form: hidden `authenticity_token` + `timezone`, code input named `code`;
  codes are submitted as `123-456` (3-3 split).
- Form detection heuristics live in `_find_login_form`/`_find_code_form`
  (`_LOGIN_TEXT_FIELDS`, `_CODE_INPUT_TYPES`). Changing the app layout
  (Turbo/Rails versions) is the main breakage risk; re-capture fixtures and
  verify live.

## Tests & fixtures

- `tests/fixtures/` are real saved app pages: `days_page.html`,
  `program_page.html`, `reading_page.html`, `login_page.html`, `code_page.html`.
  Parser tests parse these, so fixture updates = intended markup changes.
- Fake clients in tests must emulate httpx semantics: use `httpx.Headers` for
  response headers (case-insensitive `.get("location")`), and `status_code` +
  `.text` on responses. Passing fakes to typed functions needs
  `# type: ignore[arg-type]` (mypy strict).
- Re-capturing `code_page.html` requires POSTing `/auth/login` (sends a real
  OTP email to the account owner; the code is not consumed). **Sanitize the
  account email out of any captured auth fixture** before committing
  (`code_page.html` currently uses `user@example.com`).

## Live verification

With a valid session, `uv run exodus90 status` / `days` / `fetch` / `print`
are the fastest way to confirm scraper changes against real markup. Sessions
live at `~/.local/share/exodus90-printer/session/cookies.json` (JSON cookie
jar) and expire roughly monthly; re-auth is interactive
(`exodus90 login`, OTP email).

## Config & output quirks

- Config is deliberately a **flat** TOML (`~/.config/exodus90-printer/config.toml`,
  see `config.example.toml`) because pydantic-settings
  `TomlConfigSettingsSource` doesn't flatten nested tables. Add new settings
  as top-level fields; `EXODUS90_*` env vars override.
- `program_id` changes when the challenge/program changes — it's configurable,
  not hardcoded to 208.
- PDF uses **xhtml2pdf** (WeasyPrint was ruled out: no pango on the system);
  fonts are Liberation Serif from `/usr/share/fonts/liberation-serif-fonts`.
  Print goes through CUPS `lp` (`render/printer.py`).

## Conventions

- No code comments unless asked (project style). Keep commits small and
  focused; the user commits as you go (`git commit` when a coherent change
  lands).
- `cli.py` uses Typer callable defaults; `B008` is ignored per-file there —
  keep it scoped to that file only.

## Releases

`scripts/release.sh [--dry-run] (major|minor|patch)` bumps the version via
`uvx bump-my-version bump` (config in `[tool.bumpversion]`), refreshes
`uv.lock`, and pushes main + `v<version>`; the `publish.yaml` workflow publishes
the GHCR add-on image and the PyPI package on `v*` tags /
`workflow_dispatch`. Never edit `version` / `current_version` by hand.
