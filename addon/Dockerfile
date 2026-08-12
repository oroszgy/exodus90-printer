FROM python:3.13-slim

LABEL io.hass.type="app"
LABEL io.hass.arch="aarch64|amd64"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cups \
        cups-client \
        avahi-daemon \
        avahi-utils \
        dbus \
        fonts-liberation \
        jq \
        tmux \
        cron \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN case "$TARGETARCH" in \
        amd64) URL="https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64"; BIN="ttyd.x86_64" ;; \
        arm64) URL="https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.aarch64"; BIN="ttyd.aarch64" ;; \
        *) echo "unsupported arch: $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /usr/local/bin/ttyd "$URL" \
    && chmod +x /usr/local/bin/ttyd

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/uv

ENV PATH="/app/.venv/bin:/uv/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable \
    && rm -rf src pyproject.toml uv.lock README.md

COPY addon/run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]