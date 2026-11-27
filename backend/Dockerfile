# syntax=docker/dockerfile:1

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    APP_MODE=demo \
    APP_MODULE=app.main:app \
    SHIELD_DB_PATH=/app/var/shield.db \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Unicode TrueType font for Cyrillic/Kazakh PDF export in prod mode
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY data ./data

COPY <<'EOF' /usr/local/bin/entrypoint.sh
#!/bin/sh
set -eu

app_mode=$(printf '%s' "${APP_MODE:-demo}" | tr '[:upper:]' '[:lower:]')
db_path="${SHIELD_DB_PATH:-/app/var/shield.db}"
app_module="${APP_MODULE:-app.main:app}"

if [ "$app_mode" = "prod" ] && [ ! -f "$db_path" ]; then
    echo "[entrypoint] Seeding prod database at ${db_path}..."
    python -m app.prod.seed --reset --with-queue
fi

exec uvicorn "$app_module" --host 0.0.0.0 --port 8000 "$@"
EOF

RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod 0755 /usr/local/bin/entrypoint.sh \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --home-dir /app --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/var \
    && chown -R 10001:10001 /app/var /app/data

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
