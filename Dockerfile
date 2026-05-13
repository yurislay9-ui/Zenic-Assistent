# ============================================================
#  ZENIC-AGENTS - Multi-Stage Production Dockerfile
#  Phase 3: VPS Deploy
#
#  Targets:
#    - development: Hot-reload, debug, SQLite
#    - production:  Gunicorn+Uvicorn workers, PostgreSQL, hardened
#
#  Build:
#    docker build -t zenic-agents:latest .
#    docker build --target production -t zenic-agents:prod .
#
#  Run:
#    docker-compose up -d
# ============================================================

# ── Base stage: shared system packages ──────────────────────
FROM python:3.12-slim AS base

# Security: no cache, no interactive
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies (minimal for production)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (layer caching — requirements rarely change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir \
       "gunicorn>=21.2.0" \
       "psycopg2-binary>=2.9.9" \
       "asyncpg>=0.29.0"

# Copy source code
COPY . .

# Create non-root user for security
RUN groupadd -r zenic && useradd -r -g zenic -d /app -s /sbin/nologin zenic \
    && mkdir -p /home/zenic/.zenic-agents/data \
    && chown -R zenic:zenic /app /home/zenic

# ── Development stage ───────────────────────────────────────
FROM base AS development

# Install dev tools
RUN pip install --no-cache-dir \
    "watchfiles>=0.21.0" \
    "pytest>=7.4.0" \
    "pytest-asyncio>=0.21.0" \
    "httpx>=0.25.0"

# Development runs as root for convenience (volume mounts)
USER root

EXPOSE 5000

# Hot-reload with uvicorn
CMD ["uvicorn", "src.server.fastapi_app:create_app_from_env", \
     "--host", "0.0.0.0", "--port", "5000", "--reload", \
     "--factory", "--log-level", "debug"]

# ── Production stage ────────────────────────────────────────
FROM base AS production

# Production config
ENV ZENIC_ENV=production \
    ZENIC_DATA_DIR=/home/zenic/.zenic-agents/data \
    ZENIC_SERVER_MODE=fastapi \
    ZENIC_AUTH_ENABLED=true

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

USER zenic

EXPOSE 5000

# Gunicorn with Uvicorn workers — production grade
# - 4 workers: good balance for 2-core VPS
# - uvicorn worker class: async FastAPI support
# - max-requests: prevent memory leaks (recycle workers every 1000 reqs)
# - graceful timeout: 30s for in-flight requests
CMD ["gunicorn", "src.server.fastapi_app:create_app_from_env", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "--factory"]
