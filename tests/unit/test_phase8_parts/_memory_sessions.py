"""Tests for SmartMemory session management and consolidation (Phase 8.2)."""

import os
import tempfile


class TestSmartMemorySessions:
    """Tests for SmartMemory session management and consolidation (Phase 8.2)."""

    def setup_method(self):
        from src.core.smart_memory import SmartMemory
        # Use temp DB to avoid polluting real data
        self.tmpdir = tempfile.mkdtemp()
        self.original_db_path = None
        import src.core.smart_memory as sm_module
        self.original_db_path = sm_module.DB_PATH
        sm_module.DB_PATH = os.path.join(self.tmpdir, "test_memory.sqlite")
        self.memory = SmartMemory(semantic_engine=None)

    def teardown_method(self):
        import src.core.smart_memory as sm_module
        if self.original_db_path:
            sm_module.DB_PATH = self.original_db_path
        import shutil
        if os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_start_session(self):
        """start_session should create a new session."""
        session_id = self.memory.start_session()
        assert session_id is not None
        assert len(session_id) > 0

    def test_end_session(self):
        """end_session should close the session."""
        self.memory.start_session()
        result = self.memory.end_session()
        assert "session_id" in result

    def test_get_conversation_summary_current(self):
        """Should get summary of current session."""
        self.memory.start_session()
        self.memory.add_working("test query", "test response", "CREATE", "FEATURE_ADD", 0.7)
        summary = self.memory.get_conversation_summary()
        assert len(summary) > 0

    def test_consolidate_memories(self):
        """consolidate_memories should promote important entries."""
        self.memory.start_session()
        # Add important entries
        self.memory.add_working("important query", "important response",
                                "CREATE", "SECURITY_HARDEN", 0.9)
        result = self.memory.consolidate_memories()
        assert isinstance(result, dict)
        assert "promoted_to_long_term" in result

    def test_consolidate_empty_working(self):
        """consolidate_memories should handle empty working memory."""
        self.memory.start_session()
        result = self.memory.consolidate_memories()
        assert result["promoted_to_long_term"] == 0
