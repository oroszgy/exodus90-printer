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
        cron \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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