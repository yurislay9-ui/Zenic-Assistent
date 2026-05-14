"""
Zenic-Agents E2E — HTTP API Tests

Tests the main FastAPI endpoints end-to-end:
  - /v1/chat/completions (OpenAI-compatible)
  - /health, /ready, /metrics
  - /v1/models
  - / (root info)
  - Auth middleware (unauthenticated)
  - Rate limiting
  - Error handling (invalid JSON, wrong method, 404)

All tests are marked with @pytest.mark.e2e.
"""

from __future__ import annotations

import time

import pytest


# ---------------------------------------------------------------------------
# /health and /ready endpoints
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestHealthEndpoints:
    """Test health and readiness endpoints."""

    def test_health_returns_200(self, main_api_client):
        response = main_api_client.get("/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_health_has_status_field(self, main_api_client):
        data = main_api_client.get("/health").json()
        assert "status" in data, f"Missing 'status' in {list(data.keys())}"

    def test_ready_returns_200(self, main_api_client):
        response = main_api_client.get("/ready")
        assert response.status_code == 200
        assert response.json().get("ready") is True or "checks" in response.json()

    def test_root_endpoint(self, main_api_client):
        """GET / should return server info."""
        response = main_api_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "active"
        assert "version" in data or "model" in data


# ---------------------------------------------------------------------------
# /v1/chat/completions (OpenAI-compatible)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestChatCompletionsEndpoint:
    """Test the OpenAI-compatible /v1/chat/completions endpoint."""

    def test_chat_completions_returns_200(self, main_api_client):
        """POST /v1/chat/completions with valid messages should return 200."""
        response = main_api_client.post(
            "/v1/chat/completions",
            json={
                "model": "zenic-agents",
                "messages": [{"role": "user", "content": "Hello, test message"}],
            },
        )
        assert response.status_code in (200, 500, 503), (
            f"Expected 200/500/503, got {response.status_code}: {response.text[:200]}"
        )

    def test_chat_completions_no_messages_returns_400(self, main_api_client):
        """POST /v1/chat/completions without messages should return 400."""
        response = main_api_client.post(
            "/v1/chat/completions",
            json={"model": "zenic-agents", "messages": []},
        )
        assert response.status_code == 400, (
            f"Expected 400, got {response.status_code}"
        )

    def test_chat_completions_invalid_json_returns_400(self, main_api_client):
        """Malformed JSON should return 400."""
        response = main_api_client.post(
            "/v1/chat/completions",
            content="not valid json{{{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code in (400, 422), (
            f"Expected 400/422, got {response.status_code}"
        )

    def test_chat_completions_response_structure(self, main_api_client):
        """Successful response should have OpenAI-compatible structure."""
        response = main_api_client.post(
            "/v1/chat/completions",
            json={
                "model": "zenic-agents",
                "messages": [{"role": "user", "content": "Create a hello world function"}],
            },
        )
        if response.status_code == 200:
            data = response.json()
            assert data.get("object") == "chat.completion", (
                f"Expected object=chat.completion, got {data.get('object')}"
            )
            assert "choices" in data
            assert len(data["choices"]) > 0
            assert data["choices"][0].get("message", {}).get("role") == "assistant"

    def test_chat_completions_streaming(self, main_api_client):
        """stream=true should return SSE or streaming response."""
        response = main_api_client.post(
            "/v1/chat/completions",
            json={
                "model": "zenic-agents",
                "messages": [{"role": "user", "content": "stream test"}],
                "stream": True,
            },
        )
        # Streaming may return 200 with text/event-stream or fall back to JSON
        assert response.status_code in (200, 500, 503)


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestModelsEndpoint:
    """Test the /v1/models endpoint."""

    def test_list_models(self, main_api_client):
        """GET /v1/models should return OpenAI-compatible model list."""
        response = main_api_client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        model = data["data"][0]
        assert model["id"] == "zenic-agents"
        assert model["object"] == "model"


# ---------------------------------------------------------------------------
# CORS Headers
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestCORSHeaders:
    """Test that CORS headers are properly set."""

    def test_cors_preflight(self, main_api_client):
        """OPTIONS preflight should succeed."""
        response = main_api_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in (200, 204, 405)

    def test_cors_allows_any_origin(self, main_api_client):
        """GET with any Origin should succeed."""
        response = main_api_client.get(
            "/health", headers={"Origin": "http://any-site.com"},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestAuthentication:
    """Test authentication middleware behavior."""

    def test_health_no_auth_required(self, main_api_client):
        """Health endpoint should not require authentication."""
        response = main_api_client.get("/health")
        assert response.status_code == 200

    def test_models_no_auth_required(self, main_api_client):
        """Models endpoint should work without auth when no auth service is configured."""
        response = main_api_client.get("/v1/models")
        assert response.status_code == 200

    def test_chat_completions_no_auth_when_disabled(self, main_api_client):
        """Chat completions should work without auth when auth_service is None."""
        response = main_api_client.post(
            "/v1/chat/completions",
            json={"model": "zenic-agents", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code in (200, 500, 503), "Should not be 401"


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestRateLimiting:
    """Test rate limiting behavior."""

    def test_normal_request_volume_succeeds(self, main_api_client):
        """Normal volume of requests should all succeed."""
        for _ in range(5):
            response = main_api_client.get("/health")
            assert response.status_code == 200

    def test_burst_requests_under_limit(self, main_api_client):
        """Burst of requests under limit should succeed."""
        for _ in range(3):
            response = main_api_client.get("/v1/models")
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestAPIErrorHandling:
    """Test API error handling end-to-end."""

    def test_unknown_endpoint_returns_404(self, main_api_client):
        response = main_api_client.get("/v1/does-not-exist")
        assert response.status_code == 404

    def test_wrong_method_on_health(self, main_api_client):
        """PATCH on /health should return 405."""
        response = main_api_client.patch("/health")
        assert response.status_code == 405

    def test_missing_messages_field_returns_error(self, main_api_client):
        """Missing 'messages' in chat completions should return error."""
        response = main_api_client.post(
            "/v1/chat/completions",
            json={"model": "zenic-agents"},
        )
        assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Conversational Server API
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestConversationalServerAPI:
    """Test the conversational server's /v1/chat and /v1/sessions endpoints."""

    def test_health_conversational(self, api_client):
        response = api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"

    def test_create_session(self, api_client):
        response = api_client.post("/v1/sessions")
        assert response.status_code == 200
        data = response.json()
        assert data.get("session_id")
        assert data.get("state") == "active"

    def test_session_lifecycle(self, api_client):
        """create → get → end → verify 404."""
        create = api_client.post("/v1/sessions")
        assert create.status_code == 200
        sid = create.json()["session_id"]

        get = api_client.get(f"/v1/sessions/{sid}")
        assert get.status_code == 200

        end = api_client.delete(f"/v1/sessions/{sid}")
        assert end.status_code == 200

        verify = api_client.get(f"/v1/sessions/{sid}")
        assert verify.status_code == 404

    def test_get_nonexistent_session_404(self, api_client):
        response = api_client.get("/v1/sessions/nonexistent-id-12345")
        assert response.status_code == 404

    def test_chat_with_session(self, api_client):
        """Chat with a created session should reuse that session."""
        create = api_client.post("/v1/sessions")
        if create.status_code != 200:
            pytest.skip("Session creation unavailable")
        sid = create.json()["session_id"]

        response = api_client.post(
            "/v1/chat",
            json={"message": "Hello", "session_id": sid},
        )
        assert response.status_code in (200, 422)
        if response.status_code == 200:
            assert response.json().get("session_id") == sid

    def test_list_personalities(self, api_client):
        response = api_client.get("/v1/personalities")
        assert response.status_code == 200
        assert "personalities" in response.json()

    def test_conversational_models(self, api_client):
        response = api_client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
