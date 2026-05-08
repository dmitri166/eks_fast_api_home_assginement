"""
Production-ready FastAPI service.

Hardened version of the original app with:
- Structured JSON logging with correlation IDs
- Prometheus metrics instrumentation
- OpenTelemetry distributed tracing (Tempo-compatible)
- Proper error handling and graceful shutdown
- Separate health/readiness probes
"""

import logging
import os
import signal
import sys
import time
import random
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import structlog
import uvicorn

# ---------------------------------------------------------------------------
# OpenTelemetry Tracing (optional — gracefully degrades if not configured)
# ---------------------------------------------------------------------------
OTEL_ENABLED = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "") != ""
tracer = None

if OTEL_ENABLED:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        resource = Resource.create({
            "service.name": os.getenv("OTEL_SERVICE_NAME", "fastapi-app"),
            "service.version": "1.0.0",
            "deployment.environment": os.getenv("ENVIRONMENT", "production"),
        })
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter())
        )
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer("fastapi_app")
    except ImportError:
        OTEL_ENABLED = False


# ---------------------------------------------------------------------------
# Structured Logging Configuration
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Suppress default uvicorn access logs to avoid duplication
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

logger = structlog.get_logger("fastapi_app")

# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------
PROCESS_REQUESTS_TOTAL = Counter(
    "process_requests_total",
    "Total /process requests",
    ["status"],  # "success" or "error"
)

PROCESS_DURATION_SECONDS = Histogram(
    "process_duration_seconds",
    "Duration of /process endpoint in seconds",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 1.0],
)

PROCESS_ERRORS_TOTAL = Counter(
    "process_errors_total",
    "Total /process errors (business-critical)",
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

# ---------------------------------------------------------------------------
# Application State
# ---------------------------------------------------------------------------
_ready = False
GRACEFUL_SHUTDOWN_TIMEOUT = int(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "10"))


# ---------------------------------------------------------------------------
# Lifecycle & Graceful Shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    global _ready
    logger.info("application_starting", version="1.0.0", otel_enabled=OTEL_ENABLED)
    _ready = True
    logger.info("application_ready")
    yield
    # Shutdown
    logger.info("application_shutting_down", timeout=GRACEFUL_SHUTDOWN_TIMEOUT)
    _ready = False
    # Give in-flight requests time to complete
    time.sleep(min(GRACEFUL_SHUTDOWN_TIMEOUT, 5))
    # Flush tracing spans before exit
    if OTEL_ENABLED:
        try:
            from opentelemetry import trace
            trace.get_tracer_provider().force_flush()
        except Exception:
            pass
    logger.info("application_stopped")


def _handle_sigterm(signum, frame):
    """Handle SIGTERM for graceful shutdown in Kubernetes."""
    logger.info("sigterm_received")
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_sigterm)

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FastAPI Production Service",
    version="1.0.0",
    docs_url=None,       # Disable Swagger UI in production
    redoc_url=None,       # Disable ReDoc in production
    lifespan=lifespan,
)

# Auto-instrument FastAPI with OpenTelemetry (if enabled)
if OTEL_ENABLED:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Middleware — Request Logging & Metrics
# ---------------------------------------------------------------------------
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Add correlation ID, structured logging, and metrics to every request."""
    # Correlation ID: use incoming header or generate one
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Extract trace ID from OpenTelemetry span if available
    trace_id = ""
    if OTEL_ENABLED:
        try:
            from opentelemetry import trace as otel_trace
            span = otel_trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.is_valid:
                trace_id = format(ctx.trace_id, "032x")
        except Exception:
            pass

    # Bind context for structured logging
    structlog.contextvars.clear_contextvars()
    log_context = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "client_ip": request.client.host if request.client else "unknown",
    }
    if trace_id:
        log_context["trace_id"] = trace_id
    structlog.contextvars.bind_contextvars(**log_context)

    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_request_error")
        response = JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "request_id": request_id},
        )

    duration = time.time() - start_time

    # Add correlation ID to response headers
    response.headers["X-Request-ID"] = request_id
    if trace_id:
        response.headers["X-Trace-ID"] = trace_id

    # Skip metrics for /health, /ready, /metrics to reduce noise
    if request.url.path not in ("/health", "/ready", "/metrics"):
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            endpoint=request.url.path,
        ).observe(duration)

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )

    return response


# ---------------------------------------------------------------------------
# Health & Readiness Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["infrastructure"])
def health():
    """Liveness probe — is the process alive and responsive?"""
    return {"status": "ok"}


@app.get("/ready", tags=["infrastructure"])
def ready():
    """Readiness probe — is the app ready to serve traffic?"""
    if not _ready:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Business Endpoint
# ---------------------------------------------------------------------------
@app.get("/process", tags=["business"])
def process():
    """
    Business-critical processing endpoint.

    Original behavior preserved:
    - Simulates processing with random latency (50-400ms)
    - 5% chance of failure

    Enhancements:
    - Metrics: duration histogram + error counter
    - OpenTelemetry span with custom attributes
    - Structured error logging with correlation ID
    - Returns HTTP 500 instead of unhandled exception
    """
    # Create a custom span for business logic tracing
    span_ctx = None
    if OTEL_ENABLED and tracer:
        span_ctx = tracer.start_span("process_business_logic")
        span_ctx.set_attribute("endpoint", "/process")

    start = time.time()
    try:
        # Original business logic — untouched
        time.sleep(random.uniform(0.05, 0.4))
        if random.random() < 0.05:
            raise Exception("processing failed")

        duration = time.time() - start
        PROCESS_DURATION_SECONDS.observe(duration)
        PROCESS_REQUESTS_TOTAL.labels(status="success").inc()

        if span_ctx:
            span_ctx.set_attribute("process.status", "success")
            span_ctx.set_attribute("process.duration_ms", round(duration * 1000, 2))
            span_ctx.end()

        return {"result": "done"}

    except Exception as exc:
        duration = time.time() - start
        PROCESS_DURATION_SECONDS.observe(duration)
        PROCESS_REQUESTS_TOTAL.labels(status="error").inc()
        PROCESS_ERRORS_TOTAL.inc()

        if span_ctx:
            span_ctx.set_attribute("process.status", "error")
            span_ctx.set_attribute("process.error", str(exc))
            span_ctx.record_exception(exc)
            span_ctx.end()

        logger.error(
            "process_failed",
            error=str(exc),
            duration_ms=round(duration * 1000, 2),
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": "processing_failed",
                "detail": str(exc),
            },
        )


# ---------------------------------------------------------------------------
# Prometheus Metrics Endpoint
# ---------------------------------------------------------------------------
@app.get("/metrics", tags=["infrastructure"], include_in_schema=False)
def metrics():
    """Expose Prometheus metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level=LOG_LEVEL.lower(),
        access_log=False,  # We handle access logging via middleware
    )
