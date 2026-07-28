FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# libpq-dev is required by psycopg (v3) for the C extension (better perf).
# Also install ca-certificates for outbound TLS (LLM API calls).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create the user BEFORE any content exists in the image. 
RUN useradd --create-home --no-log-init --uid 1000 \
    --shell /usr/sbin/nologin appuser

WORKDIR /app
RUN chown appuser:appuser /app 

# Ownership is set per-file as part of the COPY itself — no second pass
COPY --chown=appuser:appuser pyproject.toml uv.lock ./

USER appuser
RUN uv sync --frozen --no-install-project --no-dev

COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# --loop asyncio forces SelectorEventLoop — required by psycopg on all platforms
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]