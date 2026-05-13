"""
Tests for EmailExecutor, HttpExecutor, DatabaseExecutor, and FileExecutor.
"""

import os
import tempfile
import pytest

from src.core.action_executor import (
    EmailExecutor,
    HttpExecutor,
    DatabaseExecutor,
    FileExecutor,
)

from .conftest import run_async


class TestEmailExecutor:
    """Tests for EmailExecutor (dry-run mode)."""

    def setup_method(self):
        self.executor = EmailExecutor()

    def test_dry_run_without_smtp(self):
        """EmailExecutor should run in dry-run mode without SMTP config."""
        config = {
            "to": ["test@example.com"],
            "subject": "Test",
            "body": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data.get("mode") == "dry_run"

    def test_invalid_email_rejected(self):
        """Invalid recipient email should be rejected."""
        config = {
            "to": ["not-an-email"],
            "subject": "Test",
            "body": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid email" in result.error

    def test_no_recipients_rejected(self):
        """Missing recipients should be rejected."""
        config = {
            "to": [],
            "subject": "Test",
            "body": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No recipient" in result.error

    def test_string_to_normalized(self):
        """String 'to' should be normalized to list."""
        config = {
            "to": "single@example.com",
            "subject": "Test",
            "body": "Hello",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True


class TestHttpExecutor:
    """Tests for HttpExecutor (validation only, no real HTTP calls)."""

    def setup_method(self):
        self.executor = HttpExecutor()

    def test_no_url_rejected(self):
        """Missing URL should be rejected."""
        config = {"url": ""}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No URL" in result.error

    def test_invalid_url_rejected(self):
        """Invalid URL should be rejected."""
        config = {"url": "not-a-url"}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid URL" in result.error

    def test_invalid_method_rejected(self):
        """Invalid HTTP method should be rejected."""
        config = {"url": "https://example.com", "method": "PATCHX"}
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid HTTP method" in result.error


class TestDatabaseExecutor:
    """Tests for DatabaseExecutor (using :memory: DB)."""

    def setup_method(self):
        self.executor = DatabaseExecutor()

    def test_query_operation(self):
        """Query operation on in-memory DB should work."""
        config = {
            "db_path": ":memory:",
            "operation": "script",
            "script": "CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT); INSERT INTO test VALUES (1, 'hello');",
        }
        run_async(self.executor.execute(config, {}))

        query_config = {
            "db_path": ":memory:",
            "operation": "query",
            "query": "SELECT 1 as val",
        }
        result = run_async(self.executor.execute(query_config, {}))
        assert result.success is True

    def test_invalid_operation_rejected(self):
        """Invalid DB operation should be rejected."""
        config = {
            "db_path": ":memory:",
            "operation": "invalid_op",
            "query": "SELECT 1",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid DB operation" in result.error

    def test_empty_query_rejected(self):
        """Empty query should be rejected."""
        config = {
            "db_path": ":memory:",
            "operation": "query",
            "query": "",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No SQL query" in result.error

    def test_backup_in_memory_rejected(self):
        """Backup of in-memory DB should be rejected."""
        config = {
            "db_path": ":memory:",
            "operation": "backup",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Cannot backup in-memory" in result.error

    def test_script_execution(self):
        """Script execution should work on in-memory DB."""
        config = {
            "db_path": ":memory:",
            "operation": "script",
            "script": "CREATE TABLE t(x INT); INSERT INTO t VALUES(42);",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["script_lines"] >= 2

    def test_empty_script_rejected(self):
        """Empty script should be rejected."""
        config = {
            "db_path": ":memory:",
            "operation": "script",
            "script": "",
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "No SQL script" in result.error


class TestFileExecutor:
    """Tests for FileExecutor (using temp directories)."""

    def setup_method(self):
        self.executor = FileExecutor()
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_and_read(self):
        """Write then read should return the same content."""
        write_config = {
            "operation": "write",
            "source": os.path.join(self.tmpdir, "test.txt"),
            "content": "Hello World",
            "base_dir": self.tmpdir,
        }
        write_result = run_async(self.executor.execute(write_config, {}))
        assert write_result.success is True

        read_config = {
            "operation": "read",
            "source": "test.txt",
            "base_dir": self.tmpdir,
        }
        read_result = run_async(self.executor.execute(read_config, {}))
        assert read_result.success is True
        assert read_result.data["content"] == "Hello World"

    def test_mkdir_operation(self):
        """mkdir should create a directory."""
        config = {
            "operation": "mkdir",
            "source": "new_dir",
            "base_dir": self.tmpdir,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert os.path.isdir(os.path.join(self.tmpdir, "new_dir"))

    def test_exists_operation(self):
        """exists should report file existence."""
        config = {
            "operation": "exists",
            "source": "nonexistent.txt",
            "base_dir": self.tmpdir,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is True
        assert result.data["exists"] is False

    def test_invalid_operation_rejected(self):
        """Invalid file operation should be rejected."""
        config = {
            "operation": "chmod",
            "source": "file.txt",
            "base_dir": self.tmpdir,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
        assert "Invalid file operation" in result.error

    def test_path_traversal_blocked(self):
        """Path traversal in file operations should be blocked."""
        config = {
            "operation": "read",
            "source": "../../../etc/passwd",
            "base_dir": self.tmpdir,
        }
        result = run_async(self.executor.execute(config, {}))
        assert result.success is False
