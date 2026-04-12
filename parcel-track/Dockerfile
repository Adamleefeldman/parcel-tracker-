# syntax=docker/dockerfile:1.7
#
# ParcelTrack backend image.
#
# One image powers three processes — the orchestrator (compose / PaaS) chooses
# the command at runtime:
#   api    : uvicorn app.main:app --host 0.0.0.0 --port 8000
#   worker : celery -A app.background.tasks worker --loglevel=info
#   beat   : celery -A app.background.tasks beat   --loglevel=info
#
# Multi-stage build:
#   builder : installs uv + locked deps into /app/.venv
#   runtime : copies the venv + source, runs as non-root, no dev deps

# ────────────────────────────────────────────────────────────────────────────
# Stage 1: builder
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Build deps for asyncpg / psycopg2 / bcrypt wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install uv from the official distroless image (pinned).
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy only the dep manifests first so layer caching survives source edits.
COPY pyproject.toml uv.lock ./

# Install runtime deps only (no dev group, no project itself yet).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production

# Runtime libs only — no compilers in the final image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
        curl \
 && rm -rf /var/lib/apt/lists/*

# Non-root user.
RUN groupadd --system --gid 1000 app \
 && useradd  --system --uid 1000 --gid app --create-home --home-dir /home/app app

WORKDIR /app

# Copy the prebuilt venv from the builder stage.
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Copy application source. .dockerignore excludes tests/, .env, .venv, caches, git.
COPY --chown=app:app app         ./app
COPY --chown=app:app alembic.ini ./alembic.ini

USER app

EXPOSE 8000

# Liveness probe in standalone runs (compose / PaaS override as needed).
# /health is the cheap liveness endpoint; /ready (added in Task 5) is for readiness.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# No CMD on purpose — the orchestrator picks api / worker / beat.
# Default to api so a bare `docker run` does something useful.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
