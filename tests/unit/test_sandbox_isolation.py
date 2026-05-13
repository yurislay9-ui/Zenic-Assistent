"""
Unit tests for Sandbox Isolation System

Tests workspace creation, file operations, builtins restriction,
and isolation manager lifecycle.
"""

import pytest
import os
from pathlib import Path
from src.core.shared.sandbox_isolation import (
    SandboxWorkspace, SandboxIsolationManager,
    create_sandbox_builtins, create_sandbox_globals,
    get_isolation_manager, shutdown_isolation
)


class TestSandboxWorkspace:
    """Tests for SandboxWorkspace."""

    def test_create_workspace(self):
        """Should create a workspace with all required directories."""
        ws = SandboxWorkspace(sandbox_id="test_create", auto_cleanup=False)
        try:
            assert ws.code_dir.exists()
            assert ws.projects_dir.exists()
            assert ws.db_dir.exists()
            assert ws.logs_dir.exists()
            assert ws.tmp_dir.exists()
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_workspace_has_id(self):
        """Should have a valid sandbox ID."""
        ws = SandboxWorkspace(auto_cleanup=False)
        try:
            assert ws.sandbox_id is not None
            assert len(ws.sandbox_id) > 0
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_write_and_read_code(self):
        """Should write and read code files."""
        ws = SandboxWorkspace(sandbox_id="test_rw", auto_cleanup=False)
        try:
            ws.write_code("print('hello')", "test.py")
            content = ws.read_code("test.py")
            assert content == "print('hello')"
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_write_and_read_project_file(self):
        """Should write and read project files."""
        ws = SandboxWorkspace(sandbox_id="test_proj", auto_cleanup=False)
        try:
            ws.write_project_file("auth.py", "def login(): pass")
            content = ws.read_project_file("auth.py")
            assert content == "def login(): pass"
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_read_nonexistent_file(self):
        """Should return empty string for nonexistent files."""
        ws = SandboxWorkspace(sandbox_id="test_empty", auto_cleanup=False)
        try:
            content = ws.read_project_file("nonexistent.py")
            assert content == ""
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_snapshot_and_rollback(self):
        """Should snapshot and rollback project files."""
        ws = SandboxWorkspace(sandbox_id="test_snap", auto_cleanup=False)
        try:
            ws.write_project_file("data.py", "version 1")
            ws.snapshot_project_file("data.py", "version 1")

            # Modify the file
            ws.write_project_file("data.py", "version 2")
            assert ws.read_project_file("data.py") == "version 2"

            # Rollback
            success = ws.rollback_project_file("data.py")
            assert success is True
            assert ws.read_project_file("data.py") == "version 1"
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_rollback_nonexistent_backup(self):
        """Should return False when no backup exists."""
        ws = SandboxWorkspace(sandbox_id="test_norollback", auto_cleanup=False)
        try:
            success = ws.rollback_project_file("never_backed_up.py")
            assert success is False
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_get_db_path(self):
        """Should return a path inside the workspace."""
        ws = SandboxWorkspace(sandbox_id="test_db", auto_cleanup=False)
        try:
            db_path = ws.get_db_path("test.sqlite")
            assert "workspace_test_db" in db_path
            assert db_path.endswith("test.sqlite")
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_write_log(self):
        """Should write logs without error."""
        ws = SandboxWorkspace(sandbox_id="test_log", auto_cleanup=False)
        try:
            ws.write_log("Test log entry")
            ws.write_log("Another entry")
            log_path = ws.logs_dir / "execution.log"
            assert log_path.exists()
            content = log_path.read_text()
            assert "Test log entry" in content
            assert "Another entry" in content
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_is_expired(self):
        """Should detect expired workspaces."""
        ws = SandboxWorkspace(sandbox_id="test_ttl", auto_cleanup=False, ttl_seconds=0)
        try:
            # ttl_seconds=0 means already expired
            import time
            time.sleep(0.1)
            assert ws.is_expired()
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_close_cleanup(self):
        """Auto-cleanup should remove workspace directory on close."""
        ws = SandboxWorkspace(sandbox_id="test_cleanup", auto_cleanup=True)
        workspace_dir = ws.workspace_dir
        ws.write_code("test", "test.py")
        assert workspace_dir.exists()
        ws.close()
        assert not workspace_dir.exists()

    def test_context_manager(self):
        """Should work as context manager."""
        with SandboxWorkspace(sandbox_id="test_ctx", auto_cleanup=True) as ws:
            ws.write_code("test", "test.py")
            assert ws.workspace_dir.exists()
        # After exiting, should be cleaned up
        assert not ws.workspace_dir.exists()

    def test_project_file_exists(self):
        """Should check if a project file exists."""
        ws = SandboxWorkspace(sandbox_id="test_exists", auto_cleanup=False)
        try:
            assert ws.project_file_exists("test.py") is False
            ws.write_project_file("test.py", "content")
            assert ws.project_file_exists("test.py") is True
        finally:
            ws.auto_cleanup = True
            ws.close()

    def test_write_code_path_traversal_blocked(self):
        """Should not allow writing outside workspace via path traversal."""
        ws = SandboxWorkspace(sandbox_id="test_traversal", auto_cleanup=True)
        try:
            with pytest.raises((PermissionError, ValueError, OSError)):
                ws.write_code("malicious", "../../etc/shadow")
        finally:
            ws.close()


class TestSandboxBuiltinRestrictions:
    """Tests for sandbox builtins security."""

    @pytest.fixture
    def workspace(self):
        ws = SandboxWorkspace(sandbox_id="test_builtins", auto_cleanup=False)
        yield ws
        ws.auto_cleanup = True
        ws.close()

    def test_safe_modules_importable(self, workspace):
        """Safe modules should be importable."""
        builtins = create_sandbox_builtins(workspace)
        import_fn = builtins["__import__"]
        math_mod = import_fn("math")
        assert hasattr(math_mod, "sqrt")

    def test_unsafe_modules_blocked(self, workspace):
        """Unsafe modules should be blocked."""
        builtins = create_sandbox_builtins(workspace)
        import_fn = builtins["__import__"]
        with pytest.raises(ImportError, match="bloqueada"):
            import_fn("os")

    def test_subprocess_blocked(self, workspace):
        """subprocess should be blocked."""
        builtins = create_sandbox_builtins(workspace)
        import_fn = builtins["__import__"]
        with pytest.raises(ImportError):
            import_fn("subprocess")

    def test_open_restricted_to_workspace(self, workspace):
        """open() should only work within the workspace."""
        builtins = create_sandbox_builtins(workspace)
        open_fn = builtins["open"]
        # Writing within workspace should work
        with open_fn("test_file.txt", "w") as f:
            f.write("hello")

    def test_open_outside_workspace_blocked(self, workspace):
        """open() outside workspace should raise PermissionError."""
        builtins = create_sandbox_builtins(workspace)
        open_fn = builtins["open"]
        with pytest.raises(PermissionError):
            open_fn("/etc/passwd", "r")

    def test_print_is_mocked(self, workspace):
        """print() should be mocked (no side effects)."""
        builtins = create_sandbox_builtins(workspace)
        print_fn = builtins["print"]
        # Should not raise and return None
        result = print_fn("hello")
        assert result is None

    def test_create_sandbox_globals(self, workspace):
        """Should create valid sandbox globals dict."""
        globs = create_sandbox_globals(workspace)
        assert "__builtins__" in globs
        assert "__name__" in globs
        assert globs["__name__"] == "__sandbox__"

    def test_extra_globals_filtered(self, workspace):
        """Dangerous extra globals should be filtered."""
        globs = create_sandbox_globals(workspace, extra_globals={
            "safe_var": 42,
            "os": "should be filtered",
            "sys": "should be filtered",
            "my_data": [1, 2, 3],
        })
        assert globs["safe_var"] == 42
        assert globs["my_data"] == [1, 2, 3]
        assert "os" not in globs
        assert "sys" not in globs


class TestSandboxIsolationManager:
    """Tests for the isolation manager."""

    def test_create_and_release_workspace(self):
        """Should create and release workspaces."""
        manager = SandboxIsolationManager()
        try:
            ws = manager.create_workspace(sandbox_id="mgr_test1")
            assert ws.sandbox_id == "mgr_test1"
            assert ws.workspace_dir.exists()

            manager.release_workspace("mgr_test1")
            # After release, workspace should be cleaned up
            assert "mgr_test1" not in manager._active_workspaces
        finally:
            manager.shutdown()

    def test_list_active_workspaces(self):
        """Should list active workspaces."""
        manager = SandboxIsolationManager()
        try:
            manager.create_workspace(sandbox_id="list_test1")
            active = manager.list_active_workspaces()
            assert len(active) >= 1
            ids = [ws["sandbox_id"] for ws in active]
            assert "list_test1" in ids
        finally:
            manager.shutdown()

    def test_cleanup_forced(self):
        """Forced cleanup should remove all workspaces."""
        manager = SandboxIsolationManager()
        try:
            manager.create_workspace(sandbox_id="forced1")
            manager.create_workspace(sandbox_id="forced2")
            manager.cleanup_forced()
            assert len(manager._active_workspaces) == 0
        finally:
            manager.shutdown()
