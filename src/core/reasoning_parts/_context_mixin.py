"""
Reason with context mixin for ReasoningEngine.
"""

import time
import logging
from typing import Dict, Any, List

from ._imports import (
    logger, ReasoningStep, ReasoningResult, ReasoningMode,
    MAX_TOKENS_PER_STEP,
)


class ContextMixin:
    """Mixin providing reason_with_context mode."""

    def reason_with_context(self, problem: str, context: str = "") -> ReasoningResult:
        """
        Razonamiento completo con inyección inteligente de contexto.

        Combina:
          1. SemanticEngine: comprensión profunda del problema
          2. SmartMemory: soluciones previas relevantes (RAG)
          3. Working Memory: contexto de la sesión actual
          4. Qwen: razonamiento informado (no a ciegas)

        Este es el modo más inteligente pero requiere todas las capas activas.
        """
        start = time.time()
        self._call_count += 1
        context_parts = []
        memory_hits = 0

        # Layer 1: Semantic understanding
        semantic_info = {}
        if self._semantic and self._semantic.is_loaded:
            sem_result = self._semantic.classify_intent(problem)
            if sem_result.source == "embedding" and sem_result.confidence > 0.3:
                semantic_info = {
                    "operation": sem_result.operation,
                    "goal": sem_result.goal,
                    "confidence": sem_result.confidence,
                }
                context_parts.append(
                    f"Semantic analysis: operation={sem_result.operation}, goal={sem_result.goal} (conf={sem_result.confidence:.2f})"
                )

        # Layer 2: Similar past solutions (RAG)
        if self._memory and self._semantic and self._semantic.is_loaded:
            similar = self._memory.find_similar_solutions(problem, top_k=2)
            for sol in similar:
                context_parts.append(
                    f"Past solution (sim={sol['similarity']:.2f}): {sol['solution'][:150]}"
                )
                memory_hits += 1

        # Layer 3: Working memory context
        if self._memory:
            working_ctx = self._memory.get_working_context(max_tokens=150)
            if working_ctx:
                context_parts.append(working_ctx)

        # Layer 4: Additional context provided by caller
        if context:
            context_parts.append(f"User context: {context[:300]}")

        # Build enriched prompt
        enriched_context = " | ".join(context_parts) if context_parts else ""
        enriched_problem = problem
        if enriched_context:
            enriched_problem = f"{problem}\n\nRelevant context: {enriched_context}"

        # Reason with enriched context
        answer = self._call_ai(
            system_prompt="You are a knowledgeable problem solver with access to past experience and semantic understanding. Use the provided context to give the best possible answer. Be specific and actionable.",
            user_prompt=enriched_problem,
            max_tokens=MAX_TOKENS_PER_STEP + 100,
        )

        # Compute confidence
        if answer and len(answer) > 20:
            confidence = 0.7
            # Boost confidence if semantic + memory agree
            if semantic_info and semantic_info.get("confidence", 0) > 0.5:
                confidence += 0.1
            if memory_hits > 0:
                confidence += 0.05
            confidence = min(confidence, 0.95)
        elif answer:
            confidence = 0.4
        else:
            confidence = 0.1
            # Try fallback with semantic-only reasoning
            if semantic_info:
                answer = self._fallback_context_reasoning(problem, semantic_info)
                confidence = 0.35
            else:
                answer = self._fallback_generate(problem, 1)

        total_ms = (time.time() - start) * 1000

        # Save to memory
        self._save_to_memory(problem, answer[:500], "reason_with_context", confidence)

        # Track in working memory
        if self._memory:
            self._memory.add_working(problem, answer[:500],
                                     semantic_info.get("operation", "UNKNOWN"),
                                     semantic_info.get("goal", "UNKNOWN"),
                                     confidence)

        steps = [ReasoningStep(
            step_number=1,
            thought="Full context reasoning with semantic + memory injection",
            conclusion=answer[:300],
            confidence=confidence,
            duration_ms=total_ms,
            source="llm" if answer and confidence > 0.3 else "fallback",
        )]

        return ReasoningResult(
            answer=answer,
            confidence=confidence,
            mode=ReasoningMode.WITH_CONTEXT,
            steps=steps,
            total_duration_ms=total_ms,
            context_used=len(context_parts) > 0,
            memory_hits=memory_hits,
            source="llm" if confidence > 0.3 else "fallback",
        )
