#!/usr/bin/env bash
set -eu

CONFIG_PATH=/data/options.json
VENV_PYTHON=/app/.venv/bin/python

opt() { jq -r "$1" "$CONFIG_PATH"; }

log() { echo "[exodus90] $*"; }

# --- options (Supervisor always writes the full merged set to /data/options.json) ---
SCHEDULE="$(opt '.schedule')"
TIMEZONE="$(opt '.timezone')"
EMAIL="$(opt '.email')"
LOGIN_CODE="$(opt '.login_code')"
PROGRAM_ID="$(opt '.program_id')"
FORMATS="$(jq -c '.formats' "$CONFIG_PATH")"
PRINTER_NAME="$(opt '.printer_name')"
PRINTER_URI="$(opt '.printer_uri')"
OUTPUT_DIR="$(opt '.output_dir')"
PDF_FONT_DIR="$(opt '.pdf_font_dir')"
PDF_RETENTION_DAYS="$(opt '.pdf_retention_days')"
RUN_ON_STARTUP="$(opt '.run_on_startup')"

# --- environment ---
export HOME=/data
export XDG_CONFIG_HOME=/data
export XDG_DATA_HOME=/data
export TZ="$TIMEZONE"
export PATH="/app/.venv/bin:/uv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export EXODUS90_PROGRAM_ID="$PROGRAM_ID"
export EXODUS90_OUTPUT_DIR="$OUTPUT_DIR"
export EXODUS90_PDF_FONT_DIR="$PDF_FONT_DIR"
export EXODUS90_FORMATS="$FORMATS"

mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"

cat > /data/exodus90.env <<EOF
export HOME=/data
export XDG_CONFIG_HOME=/data
export XDG_DATA_HOME=/data
export TZ="$TIMEZONE"
export PATH="/app/.venv/bin:/uv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export EXODUS90_PROGRAM_ID="$PROGRAM_ID"
export EXODUS90_OUTPUT_DIR="$OUTPUT_DIR"
export EXODUS90_PDF_FONT_DIR="$PDF_FONT_DIR"
export EXODUS90_FORMATS='$FORMATS'
EOF
chmod 600 /data/exodus90.env

cat > /etc/profile.d/exodus90-env.sh <<EOF
[ -f /data/exodus90.env ] && . /data/exodus90.env
EOF

log "Configured: program_id=$PROGRAM_ID output_dir=$OUTPUT_DIR formats=$FORMATS tz=$TIMEZONE"

# --- CUPS printer queue ---
if [ -n "$PRINTER_URI" ]; then
    log "Starting CUPS..."
    /usr/sbin/cupsd
    for _ in $(seq 1 30); do
        [ -S /var/run/cups/cups.sock ] && break
        sleep 1
    done
    if [ ! -S /var/run/cups/cups.sock ]; then
        log "ERROR: cupsd did not start; printing will fail."
    elif ! lpstat -p "$PRINTER_NAME" >/dev/null 2>&1; then
        if lpadmin -p "$PRINTER_NAME" -E -v "$PRINTER_URI" -m everywhere; then
            log "Printer queue '$PRINTER_NAME' -> $PRINTER_URI"
        else
            log "ERROR: could not create printer queue '$PRINTER_NAME' for $PRINTER_URI."
        fi
    fi
    export EXODUS90_PRINTER="$PRINTER_NAME"
    echo "export EXODUS90_PRINTER='$PRINTER_NAME'" >> /data/exodus90.env
    lpoptions -d "$PRINTER_NAME" >/dev/null 2>&1 || true
else
    if printf '%s' "$FORMATS" | grep -q '"print"'; then
        log "WARNING: formats include 'print' but printer_uri is empty; printing will fail until configured."
    fi
fi

# --- login bootstrap (HA-native: email + login_code options) ---
SESSION_FILE="$XDG_DATA_HOME/exodus90-printer/session/cookies.json"
if [ -f "$SESSION_FILE" ]; then
    log "Session present; skipping login."
elif [ -n "$EMAIL" ]; then
    if [ -n "$LOGIN_CODE" ]; then
        if exodus90 login --email "$EMAIL" --code "$LOGIN_CODE"; then
            log "Authenticated."
        else
            log "ERROR: login failed with the provided code; check 'login_code' and restart the add-on."
        fi
    else
        if "$VENV_PYTHON" /opt/request_otp.py "$EMAIL"; then
            log "OTP emailed to $EMAIL. Paste the code into the 'login_code' option in the configuration tab and restart the add-on."
        else
            log "ERROR: could not request the login code; check the 'email' option and network connectivity."
        fi
    fi
else
    log "No session and no email configured. Add your email in the configuration tab to start the login flow."
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
    log "Running exodus90 print..."
    if exodus90 print; then
        log "Startup print completed."
    else
        log "Startup print failed (session expired, no reading today, or printer issue); see output above."
    fi
    retention
fi

# --- ingress web terminal (debugging) ---
log "Starting web terminal on port 8099..."
ttyd --writable -p 8099 tmux -u new -A -s exodus90 bash -l &

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
CRON_LINE="$MIN $HOUR * * * find \"$OUTPUT_DIR\" -maxdepth 1 -name '*.pdf' -type f -mtime +$PDF_RETENTION_DAYS -delete; . /data/exodus90.env; exodus90 print >> /proc/1/fd/1 2>&1"
printf '%s\n' "$CRON_LINE" | crontab -
log "Scheduled daily run at $HOUR:$MIN."

exec cron -f