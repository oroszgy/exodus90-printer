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
| `program_id`         | `208`                           | Numeric id of your challenge (`https://app.exodus90.com/programs/<id>`).    |
| `formats`            | `["pdf","print"]`               | Any of `markdown`, `pdf`, `print`.                                         |
| `printer_name`       | `exodus90`                      | CUPS queue name used for the `print` format.                               |
| `printer_uri`        | *(empty)*                       | Printer device URI, e.g. `ipp://192.168.1.100/ipp/print`. Empty = auto-discover. |
| `output_dir`         | `/share/exodus90-readings`      | Where rendered files are written (visible on the host under `/share`).     |
| `pdf_font_dir`       | `/usr/share/fonts/truetype/liberation` | Font directory for PDF rendering.                              |
| `pdf_retention_days` | `30`                            | Delete rendered PDFs older than this many days.                            |
| `run_on_startup`     | `true`                          | Also fetch/print on container start (catch-up after downtime).             |

### Printer setup

The app bundles a CUPS server (listening on localhost inside the container,
never exposed on your network).

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

The Exodus 90 session cookie expires roughly monthly. Login is interactive and
happens in the app's Web UI terminal — no codes to paste into the config:

1. Set your `email` and start the app.
2. Open the app's **Web UI** (terminal). When no valid session exists, the
   login flow starts automatically there, emails you a fresh code, and prompts
   you to type it in.
3. Enter the code from the email. The log then shows you're authenticated and
   the session is stored persistently (survives restarts and updates).

If the session expires later, restart the app and repeat — the same flow runs
again. You can also log in on demand from the terminal with
`exodus90 login --email <you@x>`.

## Web UI (terminal)

The app exposes an in-app terminal (**Open Web UI**) for debugging and login.
It runs inside the container with the correct environment:

```
exodus90 auth                    # is the session valid?
exodus90 status                  # session + today's reading
exodus90 fetch --date 2026-08-10
exodus90 print --format markdown
exodus90 printers                # list network printers discovered via mDNS
exodus90 discover                # print one IPP URI for a discovered printer
```

You can also log in interactively from the terminal with
`exodus90 login --email <you@x>`.

## Notes

- The app uses **host networking** (`host_network: true`) so the bundled avahi
  responder can discover printers via mDNS on your LAN. As a side effect the
  web terminal listens on port 8099 of the HAOS host; keep it behind a
  firewall if that matters on your network ("Open Web UI" goes through the
  authenticated Home Assistant ingress).
- The app never prompts during scheduled runs; all scheduled runs are
  unattended.
- Session cookies persist in the app's `/data` volume across restarts and
  updates; rendered PDFs go to `/share/exodus90-readings`.
- The app log shows every scheduled run; a failed run (expired session, no
  reading today, printer off) is reported there without stopping the app.
- The `exodus90` CLI is the [exodus90-printer](https://github.com/oroszgy/exodus90-printer)
  package; see its README for details.