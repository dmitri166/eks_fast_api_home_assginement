# ADR-002: Structured JSON Logging with Correlation IDs

## Status
Accepted

## Context
The original app has no logging. For production, we need to choose between:
1. **Plain text logging** (`print()` or basic `logging`)
2. **Structured JSON logging** with metadata enrichment

## Decision
Use **structlog** for structured JSON logging with automatic correlation IDs.

## Rationale
- **Machine-parseable**: JSON logs can be queried in CloudWatch Insights, Loki, or Elasticsearch without custom parsing
- **Correlation IDs**: Every request gets a UUID (`X-Request-ID` header), making it possible to trace a request across logs
- **Context enrichment**: Each log line includes method, path, status code, duration, and client IP without boilerplate
- **OpenTelemetry integration**: Trace IDs from the OTEL context are injected into log lines, linking logs to traces in Tempo
- **Zero tolerance compliance**: When `/process` fails, the error log includes the correlation ID, error message, and processing duration — no information is lost

## Example Output
```json
{
  "event": "process_failed",
  "request_id": "a1b2c3d4-e5f6-7890",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "method": "GET",
  "path": "/process",
  "error": "processing failed",
  "duration_ms": 123.45,
  "level": "error",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

## Consequences
- Additional dependency (`structlog`)
- Team must understand structured logging patterns
- Log volume increases slightly (JSON is more verbose than plain text)
