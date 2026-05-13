"""
Tests for TransformExecutor, WebhookExecutor, and NotificationExecutor.
"""

import hashlib
import hmac
import os
import pytest
from unittest.mock import patch

from src.core.action_executor import (
    TransformExecutor,
    WebhookExecutor,
    NotificationExecutor,
)

from .conftest import run_async


class TestTransformExecutor:
    """Tests for TransformExecutor (pure data operations)."""

    def setup_method(self):
        self.executor = TransformExecutor()

    def test_map_fields_dict(self):
        """map_fields should rename dict keys according to mapping."""
        config = {
            "operation": "map_fields",
            "data": {"old_key": "value"},
            "mapping": {"old_key": "new_key"},
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["result"]["new_key"] == "value"

    def test_filter_data(self):
        """filter should filter list items by key/value."""
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        config = {
            "operation": "filter",
            "data": data,
            "key": "age",
            "operator": "gt",
            "value": 26,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert len(result.data["result"]) == 1
        assert result.data["result"][0]["name"] == "Alice"

    def test_sort_data(self):
        """sort should sort list items by key."""
        data = [
            {"name": "Charlie", "age": 35},
            {"name": "Alice", "age": 25},
            {"name": "Bob", "age": 30},
        ]
        config = {
            "operation": "sort",
            "data": data,
            "key": "age",
            "ascending": True,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["result"][0]["name"] == "Alice"

    def test_aggregate_count(self):
        """aggregate count should return list length."""
        config = {
            "operation": "aggregate",
            "data": [{"x": 1}, {"x": 2}, {"x": 3}],
            "aggregation": "count",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["result"]["count"] == 3

    def test_no_data_rejected(self):
        """Missing data should be rejected."""
        config = {"operation": "map_fields", "mapping": {}}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No input data" in result.error

    def test_invalid_operation_rejected(self):
        """Invalid transform operation should be rejected."""
        config = {"operation": "explode", "data": [1, 2, 3]}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid transform operation" in result.error


class TestWebhookExecutor:
    """Tests for WebhookExecutor (verify signature only)."""

    def setup_method(self):
        self.executor = WebhookExecutor()

    def test_verify_valid_signature(self):
        """verify should accept a valid HMAC-SHA256 signature."""
        secret = "my_secret"
        body = '{"event": "test"}'
        expected_sig = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()

        config = {
            "action": "verify",
            "secret": secret,
            "verify_signature": expected_sig,
            "verify_body": body,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["valid"] is True

    def test_verify_invalid_signature(self):
        """verify should reject an invalid HMAC-SHA256 signature."""
        config = {
            "action": "verify",
            "secret": "my_secret",
            "verify_signature": "invalid_hex_signature",
            "verify_body": '{"event": "test"}',
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["valid"] is False

    def test_verify_sha256_prefix(self):
        """verify should handle sha256= prefix in signature."""
        secret = "secret"
        body = "payload"
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        config = {
            "action": "verify",
            "secret": secret,
            "verify_signature": f"sha256={sig}",
            "verify_body": body,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.data["valid"] is True

    def test_verify_missing_secret(self):
        """verify without secret should return error."""
        config = {
            "action": "verify",
            "verify_signature": "abc",
            "verify_body": "data",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Secret is required" in result.error

    def test_send_missing_url(self):
        """send without URL should return error."""
        config = {
            "action": "send",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False

    def test_invalid_action_rejected(self):
        """Invalid webhook action should be rejected."""
        config = {"action": "delete"}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid webhook action" in result.error


class TestNotificationExecutor:
    """Tests for NotificationExecutor."""

    def setup_method(self):
        self.executor = NotificationExecutor(
            email_executor=None,
            webhook_executor=None,
        )

    def test_log_channel(self):
        """log channel should succeed and deliver."""
        config = {
            "channel": "log",
            "message": "Test notification",
            "subject": "Test",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["channel"] == "log"
        assert result.data["delivered"] is True

    def test_email_channel_fallback(self):
        """email channel should fallback to log without EmailExecutor."""
        config = {
            "channel": "email",
            "recipient": "test@example.com",
            "message": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["fallback"] is True

    def test_telegram_channel_fallback(self):
        """telegram channel should fallback to log without bot token."""
        config = {
            "channel": "telegram",
            "recipient": "12345",
            "message": "Hello",
        }
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data.get("fallback") is True

    def test_webhook_channel_no_url_fallback(self):
        """webhook channel should fallback to log without URL."""
        config = {
            "channel": "webhook",
            "recipient": "",
            "message": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data.get("fallback") is True

    def test_unknown_channel_falls_back(self):
        """Unknown channel should fallback to log."""
        config = {
            "channel": "slack",
            "message": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["fallback"] is True
        assert result.data["original_channel"] == "slack"
