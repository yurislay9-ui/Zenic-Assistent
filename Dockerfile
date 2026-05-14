# ============================================================
#  ZENIC-AGENTS - Multi-Stage Production Dockerfile
#  Phase 3: VPS Deploy
#
#  Targets:
#    - rust-builder:  Compiles the Rust PyO3 extension via maturin
#    - development:   Hot-reload, debug, SQLite
#    - production:    Gunicorn+Uvicorn workers, PostgreSQL, hardened
#
#  Build:
#    docker build -t zenic-agents:latest .
#    docker build --target production -t zenic-agents:prod .
#
#  Run:
#    docker-compose up -d
# ============================================================

# ── Stage 1: Build Rust PyO3 extension ─────────────────────
FROM python:3.12-slim AS rust-builder

# Rust build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Rust toolchain
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.85.0
ENV PATH="/root/.cargo/bin:${PATH}"

# Install maturin for building Python wheels from Rust
RUN pip install --no-cache-dir maturin>=1.5.0

WORKDIR /build

# Copy Rust workspace source (layer caching — Cargo.toml changes rarely)
COPY zenic-v2/Cargo.toml zenic-v2/Cargo.lock ./zenic-v2/
COPY zenic-v2/.cargo ./zenic-v2/.cargo/
COPY zenic-v2/rust-toolchain.toml ./zenic-v2/

# Copy each crate's Cargo.toml for dependency resolution
COPY zenic-v2/zenic-proto/Cargo.toml ./zenic-v2/zenic-proto/
COPY zenic-v2/zenic-graph/Cargo.toml ./zenic-v2/zenic-graph/
COPY zenic-v2/zenic-runtime/Cargo.toml ./zenic-v2/zenic-runtime/
COPY zenic-v2/zenic-flow/Cargo.toml ./zenic-v2/zenic-flow/
COPY zenic-v2/zenic-policy/Cargo.toml ./zenic-v2/zenic-policy/
COPY zenic-v2/zenic-safety/Cargo.toml ./zenic-v2/zenic-safety/
COPY zenic-v2/zenic-core/Cargo.toml ./zenic-v2/zenic-core/
COPY zenic-v2/zenic-ffi/Cargo.toml ./zenic-v2/zenic-ffi/
COPY zenic-v2/zenic-pybridge/Cargo.toml ./zenic-v2/zenic-pybridge/
COPY zenic-v2/zenic-bench/Cargo.toml ./zenic-v2/zenic-bench/
COPY zenic-v2/zenic-tests/Cargo.toml ./zenic-v2/zenic-tests/

# Create dummy src/lib.rs files so Cargo can resolve the workspace
RUN mkdir -p zenic-v2/zenic-proto/src && echo "" > zenic-v2/zenic-proto/src/lib.rs && \
    mkdir -p zenic-v2/zenic-graph/src && echo "" > zenic-v2/zenic-graph/src/lib.rs && \
    mkdir -p zenic-v2/zenic-runtime/src && echo "" > zenic-v2/zenic-runtime/src/lib.rs && \
    mkdir -p zenic-v2/zenic-flow/src && echo "" > zenic-v2/zenic-flow/src/lib.rs && \
    mkdir -p zenic-v2/zenic-policy/src && echo "" > zenic-v2/zenic-policy/src/lib.rs && \
    mkdir -p zenic-v2/zenic-safety/src && echo "" > zenic-v2/zenic-safety/src/lib.rs && \
    mkdir -p zenic-v2/zenic-core/src && echo "" > zenic-v2/zenic-core/src/lib.rs && \
    mkdir -p zenic-v2/zenic-ffi/src && echo "" > zenic-v2/zenic-ffi/src/lib.rs && \
    mkdir -p zenic-v2/zenic-pybridge/src && echo "" > zenic-v2/zenic-pybridge/src/lib.rs && \
    mkdir -p zenic-v2/zenic-pybridge && echo 'fn main() {}' > zenic-v2/zenic-pybridge/build.rs && \
    mkdir -p zenic-v2/zenic-bench/src && echo "" > zenic-v2/zenic-bench/src/lib.rs && \
    mkdir -p zenic-v2/zenic-tests/src && echo "" > zenic-v2/zenic-tests/src/lib.rs

# Build dependencies only (cached layer)
RUN cd zenic-v2/zenic-pybridge && maturin build --release --interpreter python3.12 2>/dev/null || true

# Now copy the real Rust source code
COPY zenic-v2/ ./zenic-v2/

# Build the actual PyO3 wheel
RUN cd zenic-v2/zenic-pybridge && maturin build --release --interpreter python3.12 --out /wheels

# ── Stage 2: Base with Python + Rust extension ─────────────
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

# Install the compiled Rust extension from the builder stage
COPY --from=rust-builder /wheels/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

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
