# Exodus 90 Printer

Fetches the daily reading from the [Exodus 90](https://exodus90.com) web app and
renders it to Markdown, PDF, and/or your physical printer. Designed to run daily
from a cron job.

## How it works

- The app uses passwordless email OTP login. `exodus90 login` completes that flow
  once and persists the session cookie (in
  `~/.local/share/exodus90-printer/session/cookies.json`).
- Each run fetches the configured program page, finds the reading for the day,
  downloads its body (served as Markdown), and renders the requested outputs.
- When the session expires (typically after a few weeks), commands fail with a
  clear message; re-run `exodus90 login`.

## Setup

```sh
uv sync --extra dev        # install dependencies
uv run exodus90 login      # complete OTP login (one time, ~monthly)
uv run exodus90 status     # sanity check
```

`uv run exodus90 print` renders today's reading using the configured formats.

## Configuration

Configuration lives in `~/.config/exodus90-printer/config.toml` and can be
overridden with `EXODUS90_*` environment variables. A template is committed as
[`config.example.toml`](config.example.toml).

| Setting           | Env var                 | Default                                |
| ----------------- | ----------------------- | -------------------------------------- |
| `base_url`        | `EXODUS90_BASE_URL`     | `https://app.exodus90.com`             |
| `program_id`      | `EXODUS90_PROGRAM_ID`   | `208`                                  |
| `output_dir`      | `EXODUS90_OUTPUT_DIR`   | `~/Desktop/exodus90-readings`          |
| `formats`         | `EXODUS90_FORMATS`      | `["pdf", "print"]`                     |
| `printer`         | `EXODUS90_PRINTER`      | system default printer                 |
| `pdf_font_dir`    | `EXODUS90_PDF_FONT_DIR` | `/usr/share/fonts/liberation-serif-fonts` |
| `pdf_font_family` | `EXODUS90_PDF_FONT_FAMILY` | `LiberationSerif`                   |

The program URL changes between challenges, so the **program id is configurable**:
when your challenge changes, update `program_id` (the numeric part of
`https://app.exodus90.com/programs/<id>`).

## CLI

```sh
exodus90 login                      # log in and persist the session
exodus90 status                     # is the session valid, is there a reading today?
exodus90 fetch [--date 2026-08-10]  # print a reading as Markdown to stdout
exodus90 print [--date ...] [--format markdown] [--format pdf] [--format print]
exodus90 days                       # list the days of the configured program
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

## Development

```sh
uv run pytest         # tests
uv run ruff check .   # lint
uv run mypy src tests # type check
```

Test fixtures are real saved copies of the program page, so parser changes are
validated against the actual app markup.
