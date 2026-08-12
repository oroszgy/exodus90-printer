# Exodus 90 Printer

Fetches the daily reading from the [Exodus 90](https://exodus90.com) web app and
renders it to Markdown, PDF, and/or your physical printer. Designed to run daily
from a cron job.

## How it works

- The app uses passwordless email OTP login. `exodus90 login` completes that flow
  once and persists the session cookie (in
  `~/.local/share/exodus90-printer/session/cookies.json`).
- Each run resolves the current program (auto-discovered from the today page
  unless `program_id` is pinned), finds the reading for the day, downloads its
  body (served as Markdown), and renders the requested outputs.
- When the session expires (typically after a few weeks), commands fail with a
  clear message; re-run `exodus90 login`.

## Setup

```sh
uv sync --extra dev        # install dependencies
uv run exodus90 login      # complete OTP login (one time, ~monthly)
uv run exodus90 status     # sanity check
```

`uv run exodus90 print` renders today's reading using the configured formats.

## Home Assistant app (formerly add-on)

Run the printer as a Home Assistant app (standalone container, no CLI needed):

1. **Settings → Apps → App Store → ⋮ → Repositories →** add
   `https://github.com/oroszgy/exodus90-printer` and reload.
2. Install **Exodus90 Printer**, configure your Exodus 90 `email`, `timezone`,
   `printer_uri`, etc., and start it.
3. On first start (or after a session expires) open the app's **Web UI**; use
   the **Print today's reading** button and log in via the form there.

See [`addon/DOCS.md`](addon/DOCS.md) for full configuration, printer setup, and
login details. Multi-arch (amd64/arm64) images are published to
`ghcr.io/oroszgy/exodus90-printer` on every tagged release.

## Configuration

Configuration lives in a `config.toml` in the project root (gitignored), or
`~/.config/exodus90-printer/config.toml`, and can be overridden with
`EXODUS90_*` environment variables. A template is committed as
[`config.example.toml`](config.example.toml).

`output_dir` and `formats` are **required** — the tool has no built-in
assumptions about your output location or formats. `program_id` is optional:
when omitted it is **auto-discovered** from the app's today page, so it always
follows your current challenge.

| Setting           | Env var                 | Default                                |
| ----------------- | ----------------------- | -------------------------------------- |
| `base_url`        | `EXODUS90_BASE_URL`     | `https://app.exodus90.com`             |
| `program_id`      | `EXODUS90_PROGRAM_ID`   | auto-discovered (current program)      |
| `output_dir`      | `EXODUS90_OUTPUT_DIR`   | *(required)*                           |
| `formats`         | `EXODUS90_FORMATS`      | *(required)*                           |
| `printer`         | `EXODUS90_PRINTER`      | system default printer                 |
| `pdf_font_dir`    | `EXODUS90_PDF_FONT_DIR` | `/usr/share/fonts/liberation-serif-fonts` |
| `pdf_font_family` | `EXODUS90_PDF_FONT_FAMILY` | `LiberationSerif`                   |

The program URL changes between challenges. By default the tool figures out
which program is currently running automatically; if you need to pin one (e.g.
during the gap between challenges), set `program_id` explicitly to the numeric
part of `https://app.exodus90.com/programs/<id>`.

`exodus90 printers` lists network printers discovered via mDNS (requires
avahi/`ippfind` on the host) so you can copy a URI or set `printer` easily.

## CLI

```sh
exodus90 login                      # log in and persist the session
exodus90 auth                       # is the persisted session still valid?
exodus90 status                     # is the session valid, is there a reading today?
exodus90 fetch [--date 2026-08-10]  # print a reading as Markdown to stdout
exodus90 print [--date ...] [--format markdown] [--format pdf] [--format print]
exodus90 days                       # list the days of the configured program
exodus90 printers                   # list network printers discovered via mDNS
exodus90 discover                   # print one IPP URI for a discovered printer
exodus90 web                        # serve the Web UI (used by the HA app)
```

`print` defaults to today's date and the formats from the config, and never
prompts — safe for cron.

## Install & Cron

Install the `exodus90` command globally so cron can find it without `uv run`:

```sh
uv tool install .              # puts `exodus90` on your PATH
exodus90 login                 # complete OTP login (one time, then ~monthly)
exodus90 status                # sanity check that the session works
```

`uv tool upgrade exodus90-printer` updates the installed command after pulling
changes to this repo.

Then add a cron line that prints each day's reading automatically:

```
# print today's reading at 05:30
30 5 * * *  exodus90 print >> ~/.cache/exodus90-printer/cron.log 2>&1
```

Notes:

- `exodus90 print` never prompts and defaults to today, so it is safe for cron.
- The command exits non-zero on session expiry or a missing reading, which cron
  surfaces via its mail/log output.
- When the session lapses (typically after a few weeks), run `exodus90 login`
  again from a terminal.

## Release process

Releases are tag-driven and fully automated:

```sh
./scripts/release.sh patch   # or: minor / major
```

The script verifies you are on a clean, up-to-date `main`, bumps the version in
`pyproject.toml` and `addon/config.yaml` (and refreshes `uv.lock`) with
`bump-my-version`, then commits, tags `v<version>`, and pushes both.

Pushing a `v*` tag runs the [publish workflow](.github/workflows/publish.yaml),
which builds and pushes the multi-arch app image to
`ghcr.io/oroszgy/exodus90-printer:<version>` (+ `:latest`) and builds and
publishes the `exodus90-printer` package to PyPI. `workflow_dispatch` in the
Actions tab re-publishes the current `main` to PyPI or to a TestPyPI dry-run
target. Plain `main` pushes and pull requests only build and validate; nothing
is published.

## Development

```sh
uv run pytest         # tests
uv run ruff check .   # lint
uv run mypy src tests # type check
```

Test fixtures are real saved copies of the program page, so parser changes are
validated against the actual app markup.
