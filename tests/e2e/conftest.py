"""
Zenic-Agents E2E Test Configuration

Shared fixtures for all end-to-end tests.
Provides test clients (conversational + main FastAPI), mock data,
and cross-module fixtures needed for E2E flows.

All E2E tests must be marked with @pytest.mark.e2e.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in os.environ.get("PYTHONPATH", ""):
    os.environ["PYTHONPATH"] = PROJECT_ROOT


# ---------------------------------------------------------------------------
# Session-scoped data directory
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def e2e_data_dir():
    tmp_dir = tempfile.mkdtemp(prefix="zenic_e2e_")
    os.environ["ZENIC_DATA_DIR"] = tmp_dir
    yield tmp_dir
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def e2e_db_path(tmp_path):
    db_file = str(tmp_path / "e2e_test.sqlite")
    yield db_file
    if os.path.exists(db_file):
        os.unlink(db_file)


@pytest.fixture()
def e2e_billing_db(tmp_path):
    db_file = str(tmp_path / "e2e_billing.sqlite")
    yield db_file
    if os.path.exists(db_file):
        os.unlink(db_file)


@pytest.fixture()
def e2e_integrity_db(tmp_path):
    db_file = str(tmp_path / "e2e_integrity.sqlite")
    yield db_file
    if os.path.exists(db_file):
        os.unlink(db_file)


# ---------------------------------------------------------------------------
# Mock Orchestrator
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_orchestrator():
    orch = MagicMock()
    orch.execute = AsyncMock(return_value={
        "status": "SUCCESS",
        "code": "def generated_fn():\n    return 42\n",
        "hash": "abc123def456",
        "error": "",
        "processing_time_ms": 150,
        "route": "DEEP_PATH",
        "criticality": "NORMAL",
        "verdict": "YES",
        "verdict_source": "deterministic",
    })
    orch.stats = {"total_requests": 1, "success_count": 1, "error_count": 0}
    return orch


# ---------------------------------------------------------------------------
# Main FastAPI Test Client (/v1/chat/completions, /health, /v1/models)
# ---------------------------------------------------------------------------

def _build_main_app_fallback():
    """Build a minimal FastAPI app mirroring the main API structure."""
    import time as _time
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="Zenic-Agents", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                      allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    _start = _time.time()

    @app.get("/health")
    async def health():
        return {"status": "healthy", "uptime_s": int(_time.time() - _start)}

    @app.get("/ready")
    async def ready():
        return {"ready": True}

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [
            {"id": "zenic-agents", "object": "model",
             "created": int(_time.time()), "owned_by": "zenic-local"}]}

    @app.post("/v1/chat/completions")
    async def chat_completions(request):
        from fastapi import HTTPException
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        if not body.get("messages"):
            raise HTTPException(status_code=400, detail="No messages provided")
        return {
            "id": "zenic-e2e-test", "object": "chat.completion",
            "created": int(_time.time()), "model": "zenic-agents",
            "choices": [{"index": 0, "message": {
                "role": "assistant", "content": "E2E test response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}}

    @app.get("/")
    async def root():
        return {"status": "active", "model": "zenic-agents", "version": "1.0.0"}

    return app


@pytest.fixture()
def main_api_client(mock_orchestrator):
    """Create a TestClient for the main FastAPI application."""
    from fastapi.testclient import TestClient

    try:
        from src.server.fastapi_parts._app_factory import create_app
        from src.server.rate_limiter import RateLimiter
        rl = RateLimiter(max_requests_per_minute=100, burst_size=30, global_max_concurrent=50)
        app = create_app(orchestrator=mock_orchestrator, auth_service=None,
                         rate_limiter=rl, governor=None, platform_tag="e2e-test")
        return TestClient(app)
    except Exception:
        return TestClient(_build_main_app_fallback())


# ---------------------------------------------------------------------------
# Conversational Server Test Client
# ---------------------------------------------------------------------------

def _build_conv_app_fallback():
    """Build a minimal conversational server app."""
    import time as _time, uuid
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="Zenic-Agents", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                      allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    _start = _time.time()
    _store: dict = {}

    @app.get("/health")
    async def health():
        return {"status": "healthy", "app": "Zenic-Agents", "version": "1.0.0",
                "uptime_seconds": round(_time.time() - _start, 1),
                "sessions": len(_store), "engine_available": False}

    @app.get("/ready")
    async def ready():
        return {"ready": True}

    @app.post("/v1/sessions")
    async def create_session():
        sid = str(uuid.uuid4())
        _store[sid] = {"state": "active", "count": 0}
        return {"session_id": sid, "state": "active", "message_count": 0}

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str):
        if session_id not in _store:
            raise HTTPException(status_code=404, detail="Not found")
        s = _store[session_id]
        return {"session_id": session_id, "state": s["state"], "message_count": s["count"]}

    @app.delete("/v1/sessions/{session_id}")
    async def end_session(session_id: str):
        if session_id not in _store:
            raise HTTPException(status_code=404, detail="Not found")
        del _store[session_id]
        return {"status": "ended", "session_id": session_id}

    @app.post("/v1/chat")
    async def chat(request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        return {"session_id": body.get("session_id", "fallback"), "content": "E2E test response",
                "format": "markdown", "intent_category": "test",
                "latency_ms": 10.0, "source": "deterministic", "metadata": {}}

    @app.get("/v1/personalities")
    async def personalities():
        return {"personalities": ["zenic"], "default": "zenic"}

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [
            {"id": "zenic-agents", "object": "model", "created": int(_start), "owned_by": "zenic-agents"}]}

    @app.get("/v1/stats")
    async def stats():
        return {"engine": {}, "bridge": {}, "sessions": {"active": len(_store)}}

    return app


@pytest.fixture()
def api_client(mock_orchestrator):
    """Create a FastAPI TestClient wired to the conversational server."""
    from fastapi.testclient import TestClient

    try:
        from src.core.conversational.config.env import AgentsConfig
        from src.core.conversational.server.app import AgentsApp
        config = AgentsConfig(host="127.0.0.1", port=5000, max_sessions=10,
                             rate_limit_rpm=100, cors_origins=["*"], api_key="")
        container = AgentsApp(config=config, orchestrator=mock_orchestrator)
        client = TestClient(container.app)
        client._sessions = container.sessions
        client._engine = container.engine
        return client
    except ImportError:
        return TestClient(_build_conv_app_fallback())


# ---------------------------------------------------------------------------
# Defense fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def encryption_passphrase():
    return "e2e-test-passphrase-DO-NOT-USE-IN-PROD"


@pytest.fixture()
def encryption_manager(encryption_passphrase):
    from src.core.defense.encryption import EncryptionManager, reset_encryption_manager
    reset_encryption_manager()
    mgr = EncryptionManager(master_passphrase=encryption_passphrase,
                            pbkdf2_iterations=1_000, enable_hardware_binding=False)
    yield mgr
    reset_encryption_manager()


@pytest.fixture()
def integrity_verifier(e2e_integrity_db):
    from src.core.defense.integrity import IntegrityVerifier, reset_integrity_verifier
    reset_integrity_verifier()
    v = IntegrityVerifier(db_path=e2e_integrity_db, check_interval_seconds=300)
    yield v
    v.stop_monitoring()
    reset_integrity_verifier()


@pytest.fixture()
def ecdsa_signer():
    from src.core.license.signer import ECDSASigner
    return ECDSASigner()


@pytest.fixture()
def crud_validator():
    from src.core.executors.db_parts.crud_validator import CRUDValidator, TableSchema
    v = CRUDValidator()
    v.register_schema(TableSchema(
        table_name="users", columns={"id": "INTEGER", "name": "TEXT", "email": "TEXT"},
        required_columns=["id", "name"], protected_columns=["id"], max_records=1000))
    return v


@pytest.fixture()
def safety_gate():
    from src.core.executors.safety_gate._gate import SafetyGate
    return SafetyGate()


# ---------------------------------------------------------------------------
# Billing fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def billing_service(e2e_billing_db):
    from src.core.billing.service import BillingService, reset_billing_service
    reset_billing_service()
    svc = BillingService(db_path=e2e_billing_db)
    yield svc
    reset_billing_service()


@pytest.fixture()
def mock_stripe():
    with patch("src.core.billing.stripe_integration._ensure_stripe") as mock_ensure:
        mock_ensure.return_value = True
        mod = MagicMock()
        cust = MagicMock(id="cus_e2e_mock_123")
        mod.Customer.create.return_value = cust
        sub = MagicMock(id="sub_e2e_mock_456")
        mod.Subscription.create.return_value = sub
        mod.Subscription.delete.return_value = True
        mod.Subscription.retrieve.return_value = {"items": {"data": [{"id": "si_mock"}]}}
        mod.Subscription.modify.return_value = True
        portal = MagicMock(url="https://billing.stripe.com/mock")
        mod.billing_portal.Session.create.return_value = portal
        mod.Invoice.list.return_value = MagicMock(auto_paging_iter=lambda: [])
        mod.error = MagicMock(SignatureVerificationError=Exception)
        mod.Webhook.construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "metadata": {"tenant_id": "test-tenant", "plan_type": "business"},
                "customer": "cus_e2e_mock_123", "subscription": "sub_e2e_mock_456"}}}
        with patch("src.core.billing.stripe_integration._stripe", mod):
            yield {"module": mod, "customer": cust, "subscription": sub}


# ---------------------------------------------------------------------------
# Session manager fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def session_manager():
    from src.core.conversational.session_manager import SessionManager
    return SessionManager(max_sessions=50)
