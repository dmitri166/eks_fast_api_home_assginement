# =============================================================================
# Multi-stage Dockerfile for FastAPI Production Service
# =============================================================================
# Stage 1: Build — install dependencies into a virtual environment
# Stage 2: Runtime — minimal image with only the venv and app code
# =============================================================================

# ---------------------------------------------------------------------------
# Build stage
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install dependencies into an isolated venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir pip==24.0 && \
    pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# OCI Image Labels
LABEL org.opencontainers.image.title="fastapi-app" \
      org.opencontainers.image.description="Production-ready FastAPI service" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.source="https://github.com/dmitri166/eks_fast_api_home_assginement"

# Security: create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy application code
WORKDIR /app
COPY app.py telemetry.py ./

# Create tmp dir for any temp files (read-only rootfs compatible)
RUN mkdir -p /tmp/app && chown appuser:appuser /tmp/app

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

# Docker-level healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application
ENTRYPOINT ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--access-log"]
CMD ["--workers", "1"]
