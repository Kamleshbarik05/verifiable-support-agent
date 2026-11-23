# ==============================================================================
# Stage 1: Build & Dependency Wheel Compilation
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build-essential for compiling C-extensions (psycopg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# ==============================================================================
# Stage 2: Hardened Runtime Container
# ==============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime libpq for PostgreSQL connectivity
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pre-built wheels from builder stage
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Create dedicated non-root user for security isolation
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1001 -m appuser

# Copy application code and evaluation datasets
COPY app/ app/
COPY eval/ eval/

# Set ownership to unprivileged user
RUN chown -R appuser:appgroup /app

# Switch to non-root security context
USER 1001

# Cloud Run injects $PORT (default 8080)
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV OTEL_EXPORTER=gcp

EXPOSE 8080

# Health check probe for local docker testing
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Production server entrypoint
CMD exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT} --workers 1