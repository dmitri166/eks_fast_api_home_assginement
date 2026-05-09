"""
Production-ready FastAPI service — Clean & Hardened Version.

This version features:
- Separated Telemetry logic (telemetry.py)
- Global Unified Error Handling
- Structured JSON logging with Correlation IDs
- Prometheus Metrics (RED method)
- Graceful Shutdown & Lifecycle Management
"""

import logging
import os
import random
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

# Internal module for tracing
import telemetry

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

# Suppress default uvicorn access logs to avoid duplication in JSON logs
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = structlog.get_logger("fastapi_app")

# ---------------------------------------------------------------------------
# Prometheus Metrics (RED Method)
# ---------------------------------------------------------------------------
PROCESS_REQUESTS_TOTAL = Counter(
    "process_requests_total",
    "Total /process requests",
    ["status"],
)

PROCESS_DURATION_SECONDS = Histogram(
    "process_duration_seconds",
    "Duration of /process endpoint in seconds",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 1.0],
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
# Application State & Lifecycle
# ---------------------------------------------------------------------------
_ready = False
GRACEFUL_SHUTDOWN_TIMEOUT = int(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "10"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    global _ready
    # Startup
    telemetry.setup_tracing(app)
    logger.info(
        "application_starting",
        version="1.0.0",
        otel_enabled=telemetry.OTEL_ENABLED,
    )
    _ready = True
    yield
    # Shutdown
    _ready = False
    logger.info("application_shutting_down", timeout=GRACEFUL_SHUTDOWN_TIMEOUT)
    time.sleep(min(GRACEFUL_SHUTDOWN_TIMEOUT, 5))
    if telemetry.OTEL_ENABLED:
        try:
            from opentelemetry import trace as otel_trace

            otel_trace.get_tracer_provider().force_flush()
        except ImportError:
            pass
    logger.info("application_stopped")


def _handle_sigterm(signum, frame):
    """Handle SIGTERM for graceful shutdown in Kubernetes."""
    logger.info("sigterm_received")
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_sigterm)

# ---------------------------------------------------------------------------
# FastAPI Application & Global Error Handling
# ---------------------------------------------------------------------------
class BusinessLogicError(Exception):
    """Custom exception for known business failures."""
    pass


app = FastAPI(
    title="FastAPI Production Service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.exception_handler(BusinessLogicError)
async def business_exception_handler(request: Request, exc: BusinessLogicError):
    """Specifically handle known business failures per API contract."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=500,
        content={
            "error": "processing_failed",
            "detail": str(exc),
            "request_id": request_id, 
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Unified Error Handling (Best Practice).
    Catches all unhandled exceptions, logs them with full context, and
    returns a professional, structured JSON response.
    """
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())
    
    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=request.url.path,
        method=request.method,
        request_id=request_id,
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please contact support.",
            "request_id": request_id,
        },
    )


# ---------------------------------------------------------------------------
# Middleware — Observability (Logs, TraceIDs, Metrics)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Centralized middleware for tracing, logging, and metrics."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id  # Store for error handler

    # Inject TraceID into logs if OTel is active
    trace_id = ""
    if telemetry.OTEL_ENABLED:
        try:
            from opentelemetry import trace as otel_trace
            span = otel_trace.get_current_span()
            if span.get_span_context().is_valid:
                trace_id = format(span.get_span_context().trace_id, "032x")
        except Exception:
            pass

    # Bind structured logging context
    structlog.contextvars.clear_contextvars()
    log_context = {"request_id": request_id, "method": request.method, "path": request.url.path}
    if trace_id:
        log_context["trace_id"] = trace_id
    structlog.contextvars.bind_contextvars(**log_context)

    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    # Record metrics (skip health/metrics)
    if request.url.path not in ("/health", "/ready", "/metrics"):
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method, endpoint=request.url.path
        ).observe(duration)

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )

    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["infra"])
def ready():
    if not _ready:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}


@app.get("/process", tags=["business"])
def process():
    """Business-critical endpoint with OTel integration."""
    start = time.time()
    tracer = telemetry.get_tracer()
    
    # Custom business span if tracing is active
    span = None
    if tracer:
        span = tracer.start_span("business_processing")

    try:
        # Original business logic (simulated)
        time.sleep(random.uniform(0.05, 0.4))
        if random.random() < 0.05:
            raise BusinessLogicError("processing failed")

        PROCESS_REQUESTS_TOTAL.labels(status="success").inc()
        return {"result": "done"}

    except Exception as e:
        PROCESS_REQUESTS_TOTAL.labels(status="error").inc()
        PROCESS_ERRORS_TOTAL.inc()
        if span:
            span.record_exception(e)
            span.set_status(logging.ERROR)
        raise e  # Global exception handler will catch this
    finally:
        PROCESS_DURATION_SECONDS.observe(time.time() - start)
        if span:
            span.end()


@app.get("/metrics", tags=["infra"], include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level=LOG_LEVEL.lower(),
        access_log=False,
    )
