"""
compat._runner — AgentRunnerCompat v1→v2 wrapper.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.core.agents.schemas import AgentResult
from src.core.agents.infrastructure import AgentRunner as V2AgentRunner
from src.core.agents.resilience import BaseAgent

logger = logging.getLogger(__name__)


class AgentRunnerCompat:
    """v1-compatible AgentRunner wrapper around v2 infrastructure."""

    def __init__(self, mini_ai=None, semantic_engine=None,
                 smart_memory=None, enable_cache: bool = True,
                 **kwargs) -> None:
        self._mini_ai = mini_ai
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        self._v2_runner = V2AgentRunner()
        self._cache = None
        self._enable_cache = enable_cache
        self._total_calls = 0
        self._cache_hits = 0
        self._llm_calls = 0
        self._fallback_calls = 0

        if enable_cache:
            from .infrastructure.cache import AgentCache
            self._cache = AgentCache()
            if semantic_engine and semantic_engine.is_loaded:
                self._cache.set_semantic_engine(semantic_engine)

    def run(self, agent: Any, input_data: Any) -> AgentResult:
        """Execute an agent."""
        self._total_calls += 1

        # Check cache
        if self._enable_cache and self._cache is not None:
            cached = self._cache.get(agent.name, input_data)
            if cached is not None:
                self._cache_hits += 1
                return AgentResult(
                    success=True, data=cached,
                    source="cache", duration_ms=0, cache_hit=True,
                )

        # v2 BaseAgent
        if isinstance(agent, BaseAgent):
            result_dict = agent.run(input_data)
            success = result_dict.get("success", False)
            data = result_dict.get("data")
            source = result_dict.get("source", "deterministic")
            duration_ms = result_dict.get("duration_ms", 0.0)

            if success and self._enable_cache and self._cache is not None:
                self._cache.put(agent.name, input_data, data)

            return AgentResult(
                success=success, data=data,
                source=source, duration_ms=duration_ms,
            )

        # Legacy v1 agent
        if hasattr(agent, 'build_prompt') and hasattr(agent, 'parse_response'):
            return self._run_legacy_agent(agent, input_data)

        return AgentResult(
            success=False, source="error",
            error=f"Unknown agent type: {type(agent)}",
        )

    def _run_legacy_agent(self, agent: Any, input_data: Any) -> AgentResult:
        """Run a legacy v1 agent (build_prompt/parse_response pattern)."""
        if self._mini_ai and self._mini_ai.is_loaded:
            try:
                system_prompt, user_prompt = agent.build_prompt(input_data)
                raw_response = self._mini_ai._call_llm(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=600,
                )
                if raw_response:
                    parsed = agent.parse_response(raw_response, input_data)
                    if parsed and agent.validate_output(parsed):
                        self._llm_calls += 1
                        if self._enable_cache and self._cache is not None:
                            self._cache.put(agent.name, input_data, parsed)
                        return AgentResult(
                            success=True, data=parsed,
                            source="llm", duration_ms=0,
                        )
            except Exception as e:
                logger.debug(f"AgentRunnerCompat: LLM call failed: {e}")

        # Fallback
        self._fallback_calls += 1
        try:
            fallback_result = agent.fallback(input_data)
            return AgentResult(
                success=True, data=fallback_result,
                source="fallback", duration_ms=0,
            )
        except Exception as e:
            return AgentResult(
                success=False, source="error", error=str(e),
            )

    def clear_cache(self) -> None:
        if self._cache:
            self._cache.clear()

    def update_engines(self, mini_ai=None, semantic_engine=None,
                       smart_memory=None) -> None:
        if mini_ai is not None:
            self._mini_ai = mini_ai
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_calls": self._total_calls,
            "cache_hits": self._cache_hits,
            "llm_calls": self._llm_calls,
            "fallback_calls": self._fallback_calls,
            "cache_hit_rate": self._cache_hits / max(self._total_calls, 1),
            "cache_size": len(self._cache) if self._cache else 0,
        }

    @property
    def cache(self):
        return self._cache

    @property
    def mini_ai(self):
        return self._mini_ai
