"""
Unit tests for Structured Logging

Tests StructuredFormatter, PlainFormatter, setup_logging, and log_pipeline_step.
"""

import json
import logging
import pytest
from unittest.mock import patch, MagicMock

from src.core.shared.structured_logging import (
    StructuredFormatter,
    PlainFormatter,
    setup_logging,
    log_pipeline_step,
)


class TestStructuredFormatter:
    """Tests for the StructuredFormatter class."""

    def _make_record(self, msg="test message", level=logging.INFO,
                     logger_name="test.logger", **extra):
        """Helper: create a LogRecord with optional extra fields."""
        record = logging.LogRecord(
            name=logger_name,
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_format_produces_valid_json(self):
        """Should produce valid JSON with required fields."""
        fmt = StructuredFormatter(service_name="test-svc")
        record = self._make_record("hello world")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["message"] == "hello world"
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["service"] == "test-svc"
        assert "timestamp" in data

    def test_format_includes_extra_fields(self):
        """Should include extra fields like request_id, pipeline_level."""
        fmt = StructuredFormatter()
        record = self._make_record(
            "msg", request_id="req-123", pipeline_level=3, operation="search"
        )
        output = fmt.format(record)
        data = json.loads(output)
        assert data["request_id"] == "req-123"
        assert data["pipeline_level"] == 3
        assert data["operation"] == "search"

    def test_format_exception_info(self):
        """Should include exception details when exc_info is present."""
        fmt = StructuredFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="t.py",
            lineno=1, msg="error", args=(), exc_info=exc_info,
        )
        output = fmt.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert data["exception"]["type"] == "ValueError"
        assert "boom" in data["exception"]["message"]

    def test_format_omits_none_extra_fields(self):
        """Should not include extra fields that are None."""
        fmt = StructuredFormatter()
        record = self._make_record("msg")
        output = fmt.format(record)
        data = json.loads(output)
        assert "request_id" not in data
        assert "pipeline_level" not in data

    def test_format_fallback_on_failure(self):
        """Should fall back to plain formatting if JSON serialization fails."""
        fmt = StructuredFormatter()
        record = self._make_record("test")
        # Force JSON serialization to fail by patching json.dumps
        with patch("src.core.shared.structured_logging.json.dumps", side_effect=TypeError("fail")):
            output = fmt.format(record)
            # Should fall back to the parent class format, which is a plain string
            assert isinstance(output, str)
            assert "test" in output

    def test_custom_service_name(self):
        """Should use the custom service name in output."""
        fmt = StructuredFormatter(service_name="custom-svc")
        record = self._make_record("msg")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["service"] == "custom-svc"


class TestPlainFormatter:
    """Tests for the PlainFormatter class."""

    def _make_record(self, msg="test message", level=logging.INFO,
                     logger_name="my.module.logger", **extra):
        """Helper: create a LogRecord with optional extra fields."""
        record = logging.LogRecord(
            name=logger_name,
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_format_with_color(self):
        """Should include ANSI color codes when use_color=True."""
        fmt = PlainFormatter(use_color=True)
        record = self._make_record("hello", level=logging.INFO)
        output = fmt.format(record)
        assert "\033[32m" in output  # Green for INFO
        assert "\033[0m" in output  # Reset
        assert "hello" in output

    def test_format_without_color(self):
        """Should not include ANSI codes when use_color=False."""
        fmt = PlainFormatter(use_color=False)
        record = self._make_record("hello", level=logging.INFO)
        output = fmt.format(record)
        assert "\033[" not in output
        assert "hello" in output

    def test_format_shows_last_logger_component(self):
        """Should show only the last component of the logger name."""
        fmt = PlainFormatter(use_color=False)
        record = self._make_record("msg", logger_name="a.b.c")
        output = fmt.format(record)
        assert "c:" in output
        assert "a.b.c" not in output

    def test_format_includes_extra_fields(self):
        """Should include compact extra fields when present."""
        fmt = PlainFormatter(use_color=False)
        record = self._make_record("msg", request_id="r1", status="ok")
        output = fmt.format(record)
        assert "request_id=r1" in output
        assert "status=ok" in output

    def test_format_exception_info(self):
        """Should append traceback when exc_info is present."""
        fmt = PlainFormatter(use_color=False)
        try:
            raise RuntimeError("ouch")
        except RuntimeError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="t.py",
            lineno=1, msg="err", args=(), exc_info=exc_info,
        )
        output = fmt.format(record)
        assert "RuntimeError" in output
        assert "ouch" in output

    def test_color_mapping_all_levels(self):
        """Should have color codes for all standard levels."""
        colors = PlainFormatter.COLORS
        assert "DEBUG" in colors
        assert "INFO" in colors
        assert "WARNING" in colors
        assert "ERROR" in colors
        assert "CRITICAL" in colors


class TestSetupLogging:
    """Tests for the setup_logging function."""

    @pytest.fixture(autouse=True)
    def clean_root_logger(self):
        """Remove our handlers before and after each test."""
        root = logging.getLogger()
        # Remove existing StreamHandlers with our formatters
        for h in list(root.handlers):
            if isinstance(h, logging.StreamHandler):
                f = getattr(h, 'formatter', None)
                if isinstance(f, (StructuredFormatter, PlainFormatter)):
                    root.removeHandler(h)
        yield
        # Cleanup after test
        for h in list(root.handlers):
            if isinstance(h, logging.StreamHandler):
                f = getattr(h, 'formatter', None)
                if isinstance(f, (StructuredFormatter, PlainFormatter)):
                    root.removeHandler(h)

    def test_setup_adds_plain_handler_by_default(self):
        """Should add a PlainFormatter handler when structured=False."""
        setup_logging(level=logging.DEBUG, structured=False)
        root = logging.getLogger()
        found = any(
            isinstance(getattr(h, 'formatter', None), PlainFormatter)
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
        )
        assert found

    def test_setup_adds_structured_handler(self):
        """Should add a StructuredFormatter handler when structured=True."""
        setup_logging(level=logging.INFO, structured=True, service_name="test")
        root = logging.getLogger()
        found = any(
            isinstance(getattr(h, 'formatter', None), StructuredFormatter)
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
        )
        assert found

    def test_setup_does_not_duplicate_handlers(self):
        """Should not add duplicate handlers on repeated calls."""
        setup_logging(structured=False)
        setup_logging(structured=False)
        root = logging.getLogger()
        count = sum(
            1 for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and isinstance(getattr(h, 'formatter', None), (StructuredFormatter, PlainFormatter))
        )
        assert count == 1

    def test_setup_sets_log_level(self):
        """Should set the root logger to the specified level."""
        setup_logging(level=logging.WARNING)
        root = logging.getLogger()
        assert root.level == logging.WARNING


class TestLogPipelineStep:
    """Tests for the log_pipeline_step helper."""

    def test_logs_with_pipeline_level(self):
        """Should pass pipeline_level in the extra dict."""
        mock_logger = MagicMock()
        log_pipeline_step(
            mock_logger, logging.INFO, "step done",
            pipeline_level=3, request_id="req-1",
        )
        mock_logger.log.assert_called_once()
        call_args = mock_logger.log.call_args
        assert call_args[0][0] == logging.INFO
        assert call_args[0][1] == "step done"
        extra = call_args[1]["extra"]
        assert extra["pipeline_level"] == 3
        assert extra["request_id"] == "req-1"

    def test_logs_without_optional_fields(self):
        """Should work without pipeline_level or request_id."""
        mock_logger = MagicMock()
        log_pipeline_step(mock_logger, logging.WARNING, "warning msg")
        mock_logger.log.assert_called_once()
        extra = mock_logger.log.call_args[1]["extra"]
        assert "pipeline_level" not in extra
        assert "request_id" not in extra

    def test_logs_with_kwargs(self):
        """Should pass extra kwargs into the extra dict."""
        mock_logger = MagicMock()
        log_pipeline_step(
            mock_logger, logging.DEBUG, "debug msg",
            operation="search", target="main.py",
        )
        extra = mock_logger.log.call_args[1]["extra"]
        assert extra["operation"] == "search"
        assert extra["target"] == "main.py"
