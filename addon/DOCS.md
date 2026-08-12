# Exodus90 Printer app (formerly add-on)

Fetches the daily [Exodus 90](https://exodus90.com) reading and renders it as
PDF and/or prints it via CUPS. Designed to run unattended every day from the
app's own cron schedule. Also auto-discovers network printers so you usually
don't need to fill in a printer URI at all.

## Installation

1. Add this repository to Home Assistant:

   **Settings → Apps → App Store → ⋮ → Repositories →** add
   `https://github.com/oroszgy/exodus90-printer` and reload.

   (Home Assistant 2026.2 renamed *add-ons* to *apps*; on older versions the
   path is **Settings → Add-ons → Add-on Store**.)
2. Install **Exodus90 Printer**.
3. Configure and start (see below).

Updates appear in the app store automatically when a new tagged release is
published.

## Configuration

| Option               | Default                         | Description                                                               |
| -------------------- | ------------------------------- | ------------------------------------------------------------------------- |
| `email`              | *(empty)*                       | Your Exodus 90 account email. Empty = login is never attempted.            |
| `schedule`           | `05:30`                         | Daily print time (`HH:MM`, local time per `timezone`).                      |
| `timezone`           | `UTC`                           | [IANA](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) name. |
| `program_id`         | *(auto)*                      | Numeric id of your challenge (`https://app.exodus90.com/programs/<id>`). Leave empty to auto-discover the currently running challenge. |
| `formats`            | `["pdf","print"]`               | Any of `markdown`, `pdf`, `print`.                                         |
| `printer_uri`        | *(empty)*                       | Printer device URI, e.g. `ipp://192.168.1.100/ipp/print`. Empty = auto-discover. |
| `output_dir`         | `/share/exodus90-readings`      | Where rendered files are written (visible on the host under `/share`).     |
| `pdf_font_dir`       | `/usr/share/fonts/truetype/liberation` | Font directory for PDF rendering.                              |
| `pdf_retention_days` | `30`                            | Delete rendered PDFs older than this many days.                            |
| `run_on_startup`     | `true`                          | Also fetch/print on container start (catch-up after downtime).             |

### Printer setup

The app bundles a CUPS server (listening on localhost inside the container,
never exposed on your network). The printer queue is created with a fixed
internal name (`exodus90`) — no queue name needs to be configured.

**If you leave `printer_uri` empty**, the app auto-discovers network printers
advertising IPP via mDNS/DNS-SD (`ippfind`/avahi) on startup and sets up the
first one found automatically. This works for most modern printers, including
AirPrint/IPP Everywhere ones. The log shows which printer was selected.

To pick a specific printer (or if discovery finds nothing — mDNS can be
blocked between networks), set `printer_uri` explicitly:

```
ipp://<printer-ip>/ipp/print
```

Other supported URI schemes: `socket://<ip>:9100`, `lpd://<ip>/<queue>`,
`ipp://<cups-server>:631/printers/<queue>` for an existing CUPS server.
Printing to a USB printer attached to the HAOS host is not supported.

If no printer is configured or discovered, keep `formats` set to only
`markdown` and `pdf`; the `print` format will fail until a printer is
available.

## Login (OTP)

The Exodus 90 session cookie expires roughly monthly. Login happens from the
app's Web UI — no codes to paste into the config:

1. Set your `email` (used to prefill the form) and start the app.
2. Open the app's **Web UI**. When no valid session exists, the page shows a
   **Login** card.
3. Enter your email and click **Send verification code** — a code is emailed to
   you — then type the code and click **Verify**.

The session is stored persistently and survives restarts and updates. If it
expires later, reopen the Web UI and log in again. You can also log in from a
shell with `exodus90 login --email <you@x>`.

## Web UI

The app's **Open Web UI** page has everything you need day to day:

- **Print today's reading** — one click, fetches and prints the current day.
- **Status** — whether the session is valid and today's reading title.
- **Login** — the OTP flow above.
- **Run a command** — a small shell box for debugging, e.g.
  `exodus90 days`, `exodus90 fetch --date 2026-08-10`, `exodus90 status`.

## Notes

- The app uses **host networking** (`host_network: true`) so the bundled avahi
  responder can discover printers via mDNS on your LAN. As a side effect the
  Web UI listens on port 8099 of the HAOS host; keep it behind a firewall if
  that matters on your network ("Open Web UI" goes through the authenticated
  Home Assistant ingress).
- The app never prompts during scheduled runs; all scheduled runs are
  unattended.
- Session cookies persist in the app's `/data` volume across restarts and
  updates; rendered PDFs go to `/share/exodus90-readings`.
- The app log shows every scheduled run; a failed run (expired session, no
  reading today, printer off) is reported there without stopping the app.
- The `exodus90` CLI is the [exodus90-printer](https://github.com/oroszgy/exodus90-printer)
  package; see its README for details.