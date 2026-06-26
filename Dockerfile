FROM python:3.11-slim

# Prevent Python cache files and enable immediate container logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# build-essential supports packages that require compilation
# libgomp1 is commonly required by faiss-cpu
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata and lock file first for Docker build caching
COPY pyproject.toml uv.lock .

# Install uv and sync dependencies from the lock file
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir uv && \
    uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Copy the complete project
COPY . .

EXPOSE 8501


CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]