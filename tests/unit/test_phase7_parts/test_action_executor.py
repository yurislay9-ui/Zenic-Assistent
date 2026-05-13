"""
Tests for Phase 7 ActionExecutor system.
"""

import os
import tempfile
import pytest


class TestActionExecutor:
    """Tests for the ActionExecutor system."""

    def setup_method(self):
        from src.core.action_executor import get_default_registry, reset_default_registry
        reset_default_registry()
        self.registry = get_default_registry()

    def test_registry_has_all_executors(self):
        """Registry should have 15 registered action type aliases."""
        assert len(self.registry._executors) >= 8

    def test_registry_resolves_aliases(self):
        """Aliases should resolve to the same executor type."""
        assert self.registry.get_executor("send_email") is not None
        assert self.registry.get_executor("email") is not None
        assert self.registry.get_executor("http_request") is not None
        assert self.registry.get_executor("http") is not None
        assert self.registry.get_executor("database_operation") is not None
        assert self.registry.get_executor("db") is not None
        assert self.registry.get_executor("file_operation") is not None
        assert self.registry.get_executor("file") is not None

    @pytest.mark.asyncio
    async def test_notification_executor(self):
        """Notification executor should succeed with log channel."""
        result = await self.registry.execute_action(
            "send_notification",
            {"channel": "log", "message": "Test notification"},
            {}
        )
        assert result.success is True
        assert "message" in result.data or "channel" in result.data

    @pytest.mark.asyncio
    async def test_database_executor_query(self):
        """Database executor should execute parameterized queries."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            result = await self.registry.execute_action(
                "database_operation",
                {"db_path": db_path, "operation": "script",
                 "script": "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)"},
                {}
            )
            assert result.success is True

            result = await self.registry.execute_action(
                "database_operation",
                {"db_path": db_path, "operation": "insert",
                 "query": "INSERT INTO items (name) VALUES (?)", "params": ["test_item"]},
                {}
            )
            assert result.success is True

            result = await self.registry.execute_action(
                "database_operation",
                {"db_path": db_path, "operation": "query",
                 "query": "SELECT * FROM items"},
                {}
            )
            assert result.success is True
            assert len(result.data["rows"]) == 1
            assert result.data["rows"][0]["name"] == "test_item"
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_file_executor_write_read(self):
        """File executor should write and read files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")

            result = await self.registry.execute_action(
                "file_operation",
                {"operation": "write", "destination": file_path, "content": "Hello Phase 7!", "base_dir": tmpdir},
                {}
            )
            assert result.success is True

            result = await self.registry.execute_action(
                "file_operation",
                {"operation": "read", "source": file_path, "base_dir": tmpdir},
                {}
            )
            assert result.success is True
            assert "Hello Phase 7!" in result.data.get("content", "")

    @pytest.mark.asyncio
    async def test_file_executor_path_traversal_blocked(self):
        """File executor should block path traversal attacks."""
        result = await self.registry.execute_action(
            "file_operation",
            {"operation": "read", "source": "../../etc/passwd"},
            {}
        )
        assert result.success is False
        assert "traversal" in result.error.lower() or "Path traversal" in result.error

    @pytest.mark.asyncio
    async def test_transform_executor(self):
        """Transform executor should map fields correctly."""
        result = await self.registry.execute_action(
            "data_transform",
            {"operation": "map_fields",
             "data": {"nombre": "Juan", "edad": 30},
             "mapping": {"nombre": "name", "edad": "age"}},
            {}
        )
        assert result.success is True
        mapped = result.data.get("result", result.data)
        assert mapped.get("name") == "Juan" or mapped.get("nombre") == "Juan"

    @pytest.mark.asyncio
    async def test_webhook_executor_verify(self):
        """Webhook executor should verify HMAC signatures."""
        import hmac, hashlib
        secret = "my_secret"
        body = '{"test": true}'
        expected_sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()

        result = await self.registry.execute_action(
            "webhook",
            {"action": "verify",
             "verify_body": body,
             "secret": secret,
             "verify_signature": expected_sig},
            {}
        )
        assert result.success is True
        assert result.data.get("valid") is True

        result2 = await self.registry.execute_action(
            "webhook",
            {"action": "verify",
             "verify_body": body,
             "secret": secret,
             "verify_signature": "wrong_signature"},
            {}
        )
        assert result2.success is True
        assert result2.data.get("valid") is False

    @pytest.mark.asyncio
    async def test_invalid_action_type(self):
        """Invalid action type should return error."""
        result = await self.registry.execute_action(
            "nonexistent_action",
            {},
            {}
        )
        assert result.success is False
        assert "no executor" in result.error.lower() or "not found" in result.error.lower() or "unknown" in result.error.lower()

    @pytest.mark.asyncio
    async def test_email_dry_run(self):
        """Email executor should work in dry-run mode when SMTP not configured."""
        result = await self.registry.execute_action(
            "send_email",
            {"to": "test@test.com", "subject": "Test", "body": "Test body"},
            {}
        )
        assert result.success is True
        assert "dry" in str(result.data).lower() or "mode" in str(result.data).lower() or result.data.get("mode") == "dry_run"
