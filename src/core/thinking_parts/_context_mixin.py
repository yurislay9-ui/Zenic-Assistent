"""
Context injection mixin for ThinkingEngine.
"""

import time

from ._imports import logger, MAX_THINKING_TOKENS
import logging


class ContextMixin:
    """Context injection — the secret of ThinkingEngine."""

    def _build_context(self, query: str, max_tokens: int = 300) -> str:
        """Construye contexto inteligente inyectando memoria + semántica."""
        context_parts = []

        if self._memory:
            working_ctx = self._memory.get_working_context(max_tokens=150)
            if working_ctx:
                context_parts.append(working_ctx)

        if self._memory and self._semantic and self._semantic.is_loaded:
            similar = self._memory.find_similar_solutions(query, top_k=2)
            for sol in similar:
                context_parts.append(
                    f"Past solution (sim={sol['similarity']:.2f}): {sol['solution'][:150]}"
                )

        if self._semantic and self._semantic.is_loaded:
            sem_result = self._semantic.classify_intent(query)
            if sem_result.source == "embedding" and sem_result.confidence > 0.3:
                context_parts.append(
                    f"Semantic: operation={sem_result.operation}, goal={sem_result.goal}"
                )

        if not context_parts:
            return ""

        combined = " | ".join(context_parts)
        max_chars = max_tokens * 4
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "..."

        return f"Context: {combined}"

    def _call_with_context(self, system_prompt: str, user_prompt: str,
                            max_tokens: int, query: str = ""):
        """Llama a Qwen INYECTANDO contexto de memoria + semántica."""
        if not self._ai or not self._ai.is_loaded:
            return None

        context = self._build_context(query, max_tokens=200)

        enhanced_system = system_prompt
        if context:
            enhanced_system = f"{system_prompt}\n\n{context}"

        self._call_count += 1
        start = time.time()

        try:
            result = self._ai._call_llm(
                system_prompt=enhanced_system,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )
            elapsed = time.time() - start
            self._thinking_time += elapsed
            return result
        except Exception as e:
            logger.warning(f"ThinkingEngine: Thinking call failed: {e}")
            return None
