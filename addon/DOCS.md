# Exodus90 Printer add-on

Fetches the daily [Exodus 90](https://exodus90.com) reading and renders it as
PDF and/or prints it via CUPS. Designed to run unattended every day from the
add-on's own cron schedule.

## Installation

1. Add this repository to Home Assistant:

   **Settings → Add-ons → Add-on Store → ⋮ → Repositories →** add
   `https://github.com/oroszgy/exodus90-printer#ha-addon` and reload.
2. Install **Exodus90 Printer**.
3. Configure and start (see below).

## Configuration

| Option               | Default                         | Description                                                               |
| -------------------- | ------------------------------- | ------------------------------------------------------------------------- |
| `email`              | *(empty)*                       | Your Exodus 90 account email. Empty = login is never attempted.            |
| `login_code`         | *(empty)*                       | OTP code emailed to you; set it (then restart) to finish login.            |
| `schedule`           | `05:30`                         | Daily print time (`HH:MM`, local time per `timezone`).                      |
| `timezone`           | `UTC`                           | [IANA](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) name. |
| `program_id`         | `208`                           | Numeric id of your challenge (`https://app.exodus90.com/programs/<id>`).    |
| `formats`            | `["pdf","print"]`               | Any of `markdown`, `pdf`, `print`.                                         |
| `printer_name`       | `exodus90`                      | CUPS queue name used for the `print` format.                               |
| `printer_uri`        | *(empty)*                       | Printer device URI, e.g. `ipp://192.168.1.100/ipp/print`. Empty = no queue.|
| `output_dir`         | `/share/exodus90-readings`      | Where rendered files are written (visible on the host under `/share`).     |
| `pdf_font_dir`       | `/usr/share/fonts/truetype/liberation` | Font directory for PDF rendering.                              |
| `pdf_retention_days` | `30`                            | Delete rendered PDFs older than this many days.                            |
| `run_on_startup`     | `true`                          | Also fetch/print on container start (catch-up after downtime).             |

### Printer setup

The add-on bundles a CUPS server (listening on localhost inside the
container, never exposed on your network). Point `printer_uri` at a
**network printer** using a driverless IPP URI (most modern printers,
including AirPrint-capable ones):

```
ipp://<printer-ip>/ipp/print
```

Other supported URI schemes: `socket://<ip>:9100`, `lpd://<ip>/<queue>`,
`ipp://<cups-server>:631/printers/<queue>` for an existing CUPS server.
Printing to a USB printer attached to the HAOS host is not supported.

If you leave `printer_uri` empty, keep `formats` set to only `markdown` and
`pdf`; the `print` format will fail until a printer is configured.

## Login (OTP)

The Exodus 90 session cookie expires roughly monthly. The add-on handles this
from the UI:

1. Set your `email` and start the add-on.
2. The add-on **emails you a login code automatically** (log shows
   "OTP emailed …"). No code is consumed until you use it.
3. Open the add-on **Configuration** tab, paste the code into `login_code`,
   save, and **restart**.
4. The log shows "Authenticated." and the session is stored persistently.

If the session later expires, clear `login_code`, restart to receive a fresh
code, and repeat step 3.

## Web UI (terminal)

The add-on exposes an in-app terminal (**Open Web UI**) for debugging. It
runs inside the container with the correct environment:

```
exodus90 status                 # session + today's reading
exodus90 fetch --date 2026-08-10
exodus90 print --format markdown
```

Login is normally handled by the `email`/`login_code` options; you can also
run `exodus90 login --email you@x --code 123-456` from the terminal.

## Notes

- The add-on never prompts; all scheduled runs are unattended.
- Session cookies persist in the add-on's `/data` volume across restarts and
  updates; rendered PDFs go to `/share/exodus90-readings`.
- Add-on log shows every scheduled run; a failed run (expired session, no
  reading today, printer off) is reported there without stopping the add-on.
- The `exodus90` CLI is the [exodus90-printer](https://github.com/oroszgy/exodus90-printer)
  package; see its README for details.
