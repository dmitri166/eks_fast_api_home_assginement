"""
Unit tests for the production FastAPI service.

Tests cover:
- Health and readiness endpoints
- Business-critical /process endpoint (success and failure paths)
- Prometheus metrics exposure
- Correlation ID propagation
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    """Create a test client with lifespan events."""
    with TestClient(app) as c:
        yield c


# -----------------------------------------------------------------------
# Health & Readiness
# -----------------------------------------------------------------------
class TestHealth:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_ready_returns_ready(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}


# -----------------------------------------------------------------------
# /process endpoint
# -----------------------------------------------------------------------
class TestProcess:
    @patch("app.random.uniform", return_value=0.01)
    @patch("app.random.random", return_value=0.5)  # > 0.05, no failure
    def test_process_success(self, mock_rand, mock_uniform, client):
        response = client.get("/process")
        assert response.status_code == 200
        assert response.json() == {"result": "done"}

    @patch("app.random.uniform", return_value=0.01)
    @patch("app.random.random", return_value=0.01)  # < 0.05, triggers failure
    def test_process_failure_returns_500(self, mock_rand, mock_uniform, client):
        response = client.get("/process")
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "processing_failed"
        assert "detail" in data

    @patch("app.random.uniform", return_value=0.01)
    @patch("app.random.random", return_value=0.5)
    def test_process_returns_correlation_id(self, mock_rand, mock_uniform, client):
        response = client.get("/process")
        assert "X-Request-ID" in response.headers

    @patch("app.random.uniform", return_value=0.01)
    @patch("app.random.random", return_value=0.5)
    def test_process_preserves_custom_request_id(self, mock_rand, mock_uniform, client):
        custom_id = "test-correlation-123"
        response = client.get("/process", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id


# -----------------------------------------------------------------------
# Metrics
# -----------------------------------------------------------------------
class TestMetrics:
    def test_metrics_endpoint_exists(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    @patch("app.random.uniform", return_value=0.01)
    @patch("app.random.random", return_value=0.5)
    def test_metrics_contain_process_counters(self, mock_rand, mock_uniform, client):
        # Trigger a request first
        client.get("/process")
        response = client.get("/metrics")
        body = response.text
        assert "process_requests_total" in body
        assert "process_duration_seconds" in body
        assert "http_requests_total" in body

    @patch("app.random.uniform", return_value=0.01)
    @patch("app.random.random", return_value=0.01)  # trigger error
    def test_metrics_increment_error_counter(self, mock_rand, mock_uniform, client):
        client.get("/process")
        response = client.get("/metrics")
        assert "process_errors_total" in response.text
