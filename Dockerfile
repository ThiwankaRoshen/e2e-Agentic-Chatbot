FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

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
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

CMD ["uvicorn", "app.api_server:app", "--host", "0.0.0.0", "--port", "8000"]