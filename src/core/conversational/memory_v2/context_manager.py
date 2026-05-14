from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, List, Optional

from .engine import get_memory_engine_v2
from .types import MemoryQuery, MemoryRecord, MemoryTier, MemoryType

logger = logging.getLogger(__name__)

_FACT_PATTERNS = [
    re.compile(r"(?:my name is|i am|i'm called)\s+(\w+)", re.I),
    re.compile(r"(?:i (?:live|work) (?:in|at|for))\s+(.+?)(?:\.|$)", re.I),
    re.compile(r"(?:i (?:like|prefer|love|hate|dislike))\s+(.+?)(?:\.|$)", re.I),
    re.compile(r"(?:my (?:email|phone|address) is)\s+(.+?)(?:\.|$)", re.I),
    re.compile(r"(?:i (?:need|want|have))\s+(.+?)(?:\.|$)", re.I),
]


def _extract_facts(text: str) -> List[str]:
    facts: List[str] = []
    for pattern in _FACT_PATTERNS:
        for match in pattern.finditer(text):
            facts.append(match.group(0).strip())
    return facts


class ContextManager:
    """Builds and manages conversation context using MemoryEngineV2."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def _engine(self) -> Any:
        return get_memory_engine_v2()

    def build_system_context(
        self,
        session_id: str,
        user_preferences: Optional[Dict[str, Any]] = None,
    ) -> str:
        engine = self._engine()
        context_window = engine.build_context_window(session_id, max_tokens=2048)
        parts: List[str] = ["You are Zenic, an enterprise assistant."]

        if context_window.summary:
            parts.append(f"Session context: {context_window.summary}")

        pref_query = MemoryQuery(
            query_text="",
            types={MemoryType.PREFERENCE},
            tiers={MemoryTier.LONG_TERM, MemoryTier.PERMANENT},
            max_results=10,
        )
        pref_result = engine.search(pref_query)
        if pref_result.records:
            pref_lines = [r.content for r in pref_result.records[:5]]
            parts.append("User preferences: " + "; ".join(pref_lines))

        if user_preferences:
            for key, val in user_preferences.items():
                parts.append(f"User {key}: {val}")

        return "\n".join(parts)

    def build_conversation_context(
        self,
        session_id: str,
        max_tokens: int = 4096,
    ) -> List[Dict[str, str]]:
        engine = self._engine()
        context_window = engine.build_context_window(session_id, max_tokens=max_tokens)
        messages: List[Dict[str, str]] = []

        if context_window.summary:
            messages.append({
                "role": "system",
                "content": f"Previous context: {context_window.summary}",
            })

        for record in context_window.records:
            if record.mem_type == MemoryType.CONVERSATION:
                meta = record.metadata
                role = meta.get("role", "user")
                messages.append({"role": role, "content": record.content})

        return messages

    def inject_memory_context(self, query: str, session_id: str) -> str:
        engine = self._engine()
        facts = self.get_relevant_facts(query, session_id, max_facts=5)
        if not facts:
            return query

        context_block = "Relevant context:\n" + "\n".join(f"- {f}" for f in facts)
        return f"{context_block}\n\nUser query: {query}"

    def update_after_turn(
        self,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        engine = self._engine()

        engine.store(
            content=user_msg,
            tier=MemoryTier.SHORT_TERM,
            mem_type=MemoryType.CONVERSATION,
            session_id=session_id,
            importance=0.4,
            metadata={"role": "user"},
        )
        engine.store(
            content=assistant_msg,
            tier=MemoryTier.SHORT_TERM,
            mem_type=MemoryType.CONVERSATION,
            session_id=session_id,
            importance=0.3,
            metadata={"role": "assistant"},
        )

        facts = _extract_facts(user_msg)
        for fact in facts:
            engine.store(
                content=fact,
                tier=MemoryTier.LONG_TERM,
                mem_type=MemoryType.FACT,
                session_id=session_id,
                importance=0.8,
            )

        if any(w in user_msg.lower() for w in ("always", "never", "prefer", "don't like")):
            engine.store(
                content=user_msg,
                tier=MemoryTier.LONG_TERM,
                mem_type=MemoryType.PREFERENCE,
                session_id=session_id,
                importance=0.9,
            )

    def get_relevant_facts(
        self, query: str, session_id: str, max_facts: int = 5
    ) -> List[str]:
        engine = self._engine()
        query_obj = MemoryQuery(
            query_text=query,
            types={MemoryType.FACT, MemoryType.PREFERENCE},
            tiers={MemoryTier.LONG_TERM, MemoryTier.PERMANENT},
            session_id=session_id,
            min_importance=0.5,
            max_results=max_facts,
        )
        result = engine.search(query_obj)
        if not result.records:
            query_obj.session_id = None
            result = engine.search(query_obj)

        return [r.content for r in result.records[:max_facts]]


# ── Singleton ──────────────────────────────────────────────────

_instance: Optional[ContextManager] = None
_instance_lock = threading.Lock()


def get_context_manager() -> ContextManager:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ContextManager()
    return _instance


def reset_context_manager() -> None:
    global _instance
    with _instance_lock:
        _instance = None
