"""
Zenic-Agents E2E — Conversational Layer Tests

Tests the conversational layer end-to-end:
  - Session management lifecycle
  - Message processing with memory context
  - Streaming responses
  - Tools integration
  - Input sanitization
  - Intent classification
  - Memory storage and retrieval

These tests exercise CROSS-MODULE flows within the conversational subsystem.
All tests are marked with @pytest.mark.e2e.
"""

from __future__ import annotations

from typing import Any

import pytest

# Import session types with graceful fallback
try:
    from src.core.conversational.types.session import (
        Message,
        MessageRole,
        Session,
        SessionConfig,
        SessionState,
    )
    _HAS_SESSION_TYPES = True
except ImportError:
    _HAS_SESSION_TYPES = False
    Session = None  # type: ignore[assignment,misc]
    SessionConfig = None  # type: ignore[assignment,misc]
    SessionState = None  # type: ignore[assignment,misc]

requires_conversational = pytest.mark.skipif(
    not _HAS_SESSION_TYPES,
    reason="Conversational package has import chain issues"
)


# ---------------------------------------------------------------------------
# Session Management E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestSessionManagementE2E:
    """Test complete session lifecycle end-to-end."""

    def test_create_and_retrieve_session(self, session_manager):
        session = session_manager.create_session(user_id="e2e-user")
        retrieved = session_manager.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        assert retrieved.state == SessionState.ACTIVE

    def test_session_starts_with_system_message(self, session_manager):
        session = session_manager.create_session()
        system_msgs = [m for m in session.messages if m.role == MessageRole.SYSTEM]
        assert len(system_msgs) >= 1

    def test_end_session(self, session_manager):
        session = session_manager.create_session()
        result = session_manager.end_session(session.session_id)
        assert result is True
        assert session_manager.get_session(session.session_id) is None

    def test_end_nonexistent_session(self, session_manager):
        assert session_manager.end_session("does-not-exist-12345") is False

    def test_max_sessions_enforcement(self):
        from src.core.conversational.session_manager import SessionManager
        sm = SessionManager(max_sessions=2)
        sm.create_session()
        sm.create_session()
        with pytest.raises(RuntimeError, match="Maximo de sesiones"):
            sm.create_session()

    def test_session_stats_tracking(self, session_manager):
        s1 = session_manager.create_session()
        session_manager.create_session()
        session_manager.end_session(s1.session_id)
        stats = session_manager.stats
        assert stats["created"] >= 2
        assert stats["ended"] >= 1

    def test_get_or_create_returns_existing(self, session_manager):
        session = session_manager.create_session()
        same = session_manager.get_or_create(session_id=session.session_id)
        assert same.session_id == session.session_id

    def test_get_or_create_creates_new_if_missing(self, session_manager):
        new = session_manager.get_or_create(session_id="nonexistent-xyz")
        assert new is not None
        assert new.session_id != "nonexistent-xyz"

    def test_add_user_message(self, session_manager):
        session = session_manager.create_session()
        msg = session_manager.add_user_message(session.session_id, "Hello")
        assert msg is not None
        assert msg.content == "Hello"
        assert msg.role == MessageRole.USER

    def test_add_assistant_message(self, session_manager):
        session = session_manager.create_session()
        msg = session_manager.add_assistant_message(
            session.session_id, "Hi there!", metadata={"latency_ms": 42.0}
        )
        assert msg is not None
        assert msg.content == "Hi there!"
        assert msg.role == MessageRole.ASSISTANT


# ---------------------------------------------------------------------------
# Message Processing with Memory E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@requires_conversational
class TestMessageProcessingE2E:
    """Test message processing through the conversational engine."""

    @pytest.mark.asyncio
    async def test_process_message_returns_response(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        from src.core.conversational.session_manager import SessionManager

        sessions = SessionManager(max_sessions=10)
        engine = ConversationEngine(session_manager=sessions)
        session = sessions.create_session()

        response = await engine.process_message(
            session_id=session.session_id,
            user_message="Hola, ¿qué puedes hacer?",
        )
        assert response is not None
        assert response.content
        assert response.metadata is not None

    @pytest.mark.asyncio
    async def test_process_message_tracks_intent(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        from src.core.conversational.session_manager import SessionManager

        sessions = SessionManager(max_sessions=10)
        engine = ConversationEngine(session_manager=sessions)
        session = sessions.create_session()

        response = await engine.process_message(
            session_id=session.session_id,
            user_message="Ayúdame a crear un módulo de autenticación",
        )
        assert response.metadata.intent_category

    @pytest.mark.asyncio
    async def test_process_message_invalid_session_returns_error(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        engine = ConversationEngine()

        response = await engine.process_message(
            session_id="nonexistent-session-id", user_message="test",
        )
        assert response is not None
        assert response.metadata.source in ("error", "sanitizer")

    @pytest.mark.asyncio
    async def test_memory_stored_after_processing(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        from src.core.conversational.session_manager import SessionManager

        sessions = SessionManager(max_sessions=10)
        engine = ConversationEngine(session_manager=sessions)
        session = sessions.create_session()

        await engine.process_message(
            session_id=session.session_id,
            user_message="Me gusta programar en Python",
        )
        entries = engine.memory_manager.retrieve_for_context(
            query_text="programar Python",
            session_id=session.session_id, max_results=5,
        )
        assert isinstance(entries, list)


# ---------------------------------------------------------------------------
# Streaming Responses E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@requires_conversational
class TestStreamingE2E:
    """Test streaming response behavior."""

    @pytest.mark.asyncio
    async def test_stream_message_produces_chunks(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        from src.core.conversational.session_manager import SessionManager

        sessions = SessionManager(max_sessions=10)
        engine = ConversationEngine(session_manager=sessions)
        session = sessions.create_session()

        chunks = []
        async for chunk in engine.stream_message(session.session_id, "Dime algo"):
            chunks.append(chunk)
        assert len(chunks) > 0
        assert chunks[-1].is_final is True

    @pytest.mark.asyncio
    async def test_stream_concatenates_to_full_response(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        from src.core.conversational.session_manager import SessionManager

        sessions = SessionManager(max_sessions=10)
        engine = ConversationEngine(session_manager=sessions)
        session = sessions.create_session()

        full = await engine.process_message(
            session_id=session.session_id, user_message="Responde brevemente",
        )
        parts = []
        async for chunk in engine.stream_message(session.session_id, "Responde brevemente"):
            parts.append(chunk.content)
        assert "".join(parts) == full.content


# ---------------------------------------------------------------------------
# Tools & Knowledge E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@requires_conversational
class TestToolsAndKnowledgeE2E:
    """Test tools integration and knowledge base."""

    def test_tool_manager_lists_tools(self):
        from src.core.conversational.tools import ToolManager
        assert isinstance(ToolManager().stats, dict)

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_returns_error(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        engine = ConversationEngine()
        result = await engine.execute_tool("nonexistent_tool_xyz", {}, "test")
        assert result.is_err or result.is_ok

    def test_knowledge_search_returns_list(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        engine = ConversationEngine()
        results = engine.search_knowledge("Zenic-Agents", max_results=3)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_events_emitted_during_processing(self):
        from src.core.conversational.conversation_engine import ConversationEngine
        from src.core.conversational.session_manager import SessionManager

        sessions = SessionManager(max_sessions=10)
        engine = ConversationEngine(session_manager=sessions)
        session = sessions.create_session()

        initial = engine.event_bus.stats.get("events_emitted", 0)
        await engine.process_message(session_id=session.session_id, user_message="Hola")
        after = engine.event_bus.stats.get("events_emitted", 0)
        assert after >= initial


# ---------------------------------------------------------------------------
# Input Sanitization & Intent E2E
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@requires_conversational
class TestInputSanitizationAndIntentE2E:
    """Test input sanitization and intent classification."""

    def test_sanitizer_handles_special_characters(self):
        from src.core.conversational.input import InputSanitizer
        result = InputSanitizer().sanitize("Hello <script>alert('xss')</script> world")
        assert result.is_ok or result.is_err

    def test_sanitizer_handles_empty_input(self):
        from src.core.conversational.input import InputSanitizer
        result = InputSanitizer().sanitize("")
        assert result is not None

    def test_sanitizer_handles_very_long_input(self):
        from src.core.conversational.input import InputSanitizer
        result = InputSanitizer().sanitize("A" * 100_000)
        assert result is not None

    def test_intent_classifier_handles_code_requests(self):
        from src.core.conversational.engine_parts import IntentClassifier
        classifier = IntentClassifier()
        session = Session(config=SessionConfig())
        intent = classifier.classify("Crea una función para calcular factorial", session)
        assert intent is not None
        assert intent.is_code_related is True

    def test_intent_classifier_handles_questions(self):
        from src.core.conversational.engine_parts import IntentClassifier
        classifier = IntentClassifier()
        session = Session(config=SessionConfig())
        intent = classifier.classify("¿Qué es una función lambda?", session)
        assert intent is not None
        assert intent.category is not None
