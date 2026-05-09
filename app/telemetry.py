"""
OpenTelemetry Tracing configuration for the FastAPI service.
Decoupled from main application logic for better code cleanliness.
"""

import os
import structlog

logger = structlog.get_logger("telemetry")

# Global flag for other modules to check
OTEL_ENABLED = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "") != ""
tracer = None

def setup_tracing(app):
    """
    Initialize OpenTelemetry tracing and instrument the FastAPI app.
    Gracefully degrades if libraries are missing or configuration is absent.
    """
    global tracer, OTEL_ENABLED
    
    if not OTEL_ENABLED:
        logger.info("tracing_disabled", reason="endpoint_not_configured")
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Define service resource
        resource = Resource.create({
            "service.name": os.getenv("OTEL_SERVICE_NAME", "fastapi-app"),
            "service.version": "1.0.0",
            "deployment.environment": os.getenv("ENVIRONMENT", "production"),
        })

        # Set up tracer provider and OTLP exporter
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        
        # Instrument the app
        FastAPIInstrumentor.instrument_app(app)
        
        tracer = trace.get_tracer("fastapi_app")
        logger.info("tracing_initialized", service_name=os.getenv("OTEL_SERVICE_NAME", "fastapi-app"))
        return tracer

    except ImportError as e:
        logger.warning("tracing_initialization_failed", error=str(e), reason="missing_libraries")
        OTEL_ENABLED = False
        return None
    except Exception as e:
        logger.error("tracing_initialization_failed", error=str(e))
        OTEL_ENABLED = False
        return None

def get_tracer():
    """Returns the initialized tracer or None."""
    return tracer
