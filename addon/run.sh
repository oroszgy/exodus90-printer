#!/usr/bin/env bash
set -eu

CONFIG_PATH=/data/options.json

opt() { jq -r "$1" "$CONFIG_PATH"; }

log() { echo "[exodus90] $*"; }

# --- options (Supervisor always writes the full merged set to /data/options.json) ---
SCHEDULE="$(opt '.schedule')"
TIMEZONE="$(opt '.timezone')"
EMAIL="$(opt '.email')"
PROGRAM_ID="$(opt '.program_id')"
FORMATS="$(jq -c '.formats' "$CONFIG_PATH")"
PRINTER_URI="$(opt '.printer_uri')"
OUTPUT_DIR="$(opt '.output_dir')"
PDF_FONT_DIR="$(opt '.pdf_font_dir')"
PDF_RETENTION_DAYS="$(opt '.pdf_retention_days')"
DOUBLE_SIDED="$(opt '.double_sided')"
RUN_ON_STARTUP="$(opt '.run_on_startup')"

# --- environment ---
export HOME=/data
export XDG_CONFIG_HOME=/data
export XDG_DATA_HOME=/data
export TZ="$TIMEZONE"
export PATH="/app/.venv/bin:/uv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export EXODUS90_OUTPUT_DIR="$OUTPUT_DIR"
export EXODUS90_PDF_FONT_DIR="$PDF_FONT_DIR"
export EXODUS90_FORMATS="$FORMATS"
export EXODUS90_DOUBLE_SIDED="$DOUBLE_SIDED"
if [ -n "$PROGRAM_ID" ] && [ "$PROGRAM_ID" != "null" ]; then
    export EXODUS90_PROGRAM_ID="$PROGRAM_ID"
fi

mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"

cat > /data/exodus90.env <<EOF
export HOME=/data
export XDG_CONFIG_HOME=/data
export XDG_DATA_HOME=/data
export TZ="$TIMEZONE"
export PATH="/app/.venv/bin:/uv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export EXODUS90_OUTPUT_DIR="$OUTPUT_DIR"
export EXODUS90_PDF_FONT_DIR="$PDF_FONT_DIR"
export EXODUS90_FORMATS='$FORMATS'
export EXODUS90_DOUBLE_SIDED='$DOUBLE_SIDED'
EOF
if [ -n "$PROGRAM_ID" ] && [ "$PROGRAM_ID" != "null" ]; then
    echo "export EXODUS90_PROGRAM_ID='$PROGRAM_ID'" >> /data/exodus90.env
fi
chmod 600 /data/exodus90.env

cat > /etc/profile.d/exodus90-env.sh <<EOF
[ -f /data/exodus90.env ] && . /data/exodus90.env
EOF

if [ -n "$PROGRAM_ID" ] && [ "$PROGRAM_ID" != "null" ]; then
    log "Configured: program_id=$PROGRAM_ID"
else
    log "Configured: program_id=auto (discovered from today page)"
fi
log "output_dir=$OUTPUT_DIR formats=$FORMATS tz=$TIMEZONE"

# --- dbus + avahi-daemon (needed for mDNS printer discovery) ---
log "Starting dbus and avahi-daemon..."
mkdir -p /run/dbus /var/run/dbus
dbus-daemon --system --nofork &
sleep 1
avahi-daemon --no-drop-root --no-chroot &
sleep 2

# --- CUPS printer queue ---
# The queue name is purely an internal label; no user input needed.
PRINTER_NAME="exodus90"

setup_printer() {
    local uri="$1"
    log "Starting CUPS..."
    /usr/sbin/cupsd
    for _ in $(seq 1 30); do
        [ -S /var/run/cups/cups.sock ] && break
        sleep 1
    done
    if [ ! -S /var/run/cups/cups.sock ]; then
        log "ERROR: cupsd did not start; printing will fail."
        return 1
    fi
    if ! lpstat -p "$PRINTER_NAME" >/dev/null 2>&1; then
        if lpadmin -p "$PRINTER_NAME" -E -v "$uri" -m everywhere; then
            log "Printer queue '$PRINTER_NAME' -> $uri"
        else
            log "ERROR: could not create printer queue '$PRINTER_NAME' for $uri."
        fi
    fi
    export EXODUS90_PRINTER="$PRINTER_NAME"
    echo "export EXODUS90_PRINTER='$PRINTER_NAME'" >> /data/exodus90.env
    lpoptions -d "$PRINTER_NAME" >/dev/null 2>&1 || true
}

if [ -n "$PRINTER_URI" ]; then
    setup_printer "$PRINTER_URI"
else
    log "printer_uri empty; auto-discovering network printers via mDNS/DNS-SD..."
    DISCOVERED="$(timeout 30 exodus90 discover 2>/dev/null || true)"
    if [ -n "$DISCOVERED" ]; then
        log "Auto-discovered printer: $DISCOVERED"
        setup_printer "$DISCOVERED"
    else
        if printf '%s' "$FORMATS" | grep -q '"print"'; then
            log "WARNING: formats include 'print' but no printer_uri is set and no network printer was discovered; printing will fail until configured."
        else
            log "No printer configured (formats do not include 'print'); skipping printer setup."
        fi
    fi
fi

# --- session status (login happens from the Web UI form) ---
if ! exodus90 auth >/dev/null 2>&1; then
    log "No valid session. Open the app's Web UI and log in with the form (a code is emailed to you)."
else
    log "Session present and valid; skipping login."
fi

# --- PDF retention ---
retention() {
    if [ -d "$OUTPUT_DIR" ]; then
        find "$OUTPUT_DIR" -maxdepth 1 -name '*.pdf' -type f -mtime "+$PDF_RETENTION_DAYS" -delete
    fi
}
retention

# --- startup print (catch-up after reboot / missed cron runs) ---
if [ "$RUN_ON_STARTUP" = "true" ]; then
    if exodus90 auth >/dev/null 2>&1; then
        log "Running exodus90 print..."
        if exodus90 print; then
            log "Startup print completed."
        else
            log "Startup print failed (no reading today or printer issue); see output above."
        fi
    else
        log "Not logged in yet; skipping startup print. Complete login from the Web UI."
    fi
    retention
fi

# --- ingress Web UI (print button + login form + command box) ---
log "Starting Web UI on port 8099..."
if [ -n "$EMAIL" ]; then
    exodus90 web --port 8099 --email "$EMAIL" &
else
    exodus90 web --port 8099 &
fi

# --- daily schedule via cron ---
HOUR="${SCHEDULE%%:*}"
MIN="${SCHEDULE#*:}"
if ! [[ "$HOUR" =~ ^[0-9]+$ ]] || ! [[ "$MIN" =~ ^[0-9]+$ ]] || [ "$HOUR" -gt 23 ] || [ "$MIN" -gt 59 ]; then
    log "ERROR: invalid schedule '$SCHEDULE'; expected HH:MM. Falling back to 05:30."
    HOUR=5
    MIN=30
fi
HOUR=$((10#$HOUR))
MIN=$((10#$MIN))
CRON_LINE="$MIN $HOUR * * * find \"$OUTPUT_DIR\" -maxdepth 1 -name '*.pdf' -type f -mtime +$PDF_RETENTION_DAYS -delete; . /data/exodus90.env; exodus90 print >> /proc/1/fd/1 2>&1; exodus90 print-night-vigil >> /proc/1/fd/1 2>&1"
printf '%s\n' "$CRON_LINE" | crontab -
log "Scheduled daily run at $HOUR:$MIN."

exec cron -f