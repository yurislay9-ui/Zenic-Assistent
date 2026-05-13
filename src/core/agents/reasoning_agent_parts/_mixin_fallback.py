"""
Mixin: Fallback and deterministic reasoning methods.
"""

import time
from typing import Any, Dict, List

from ._imports import (
    ReasoningInput, ReasoningOutput, ReasoningStep,
    PROBLEM_TEMPLATES, PROBLEM_KEYWORDS, logger,
)


class FallbackMixin:
    """Fallback, deterministic reasoning, and helper methods for ReasoningAgent."""

    def fallback(self, input_data: Any) -> ReasoningOutput:
        """
        Fallback determinista: razonamiento por tipo de problema.

        Sin LLM, sin embeddings, 100% determinista.
        Prioriza: SmartMemory cache → SemanticEngine → Template reasoning
        """
        start = time.time()

        if isinstance(input_data, ReasoningInput):
            query = input_data.query
            mode = input_data.mode
            context = input_data.context
            max_steps = input_data.max_steps
        elif isinstance(input_data, str):
            query = input_data
            mode = "step_by_step"
            context = ""
            max_steps = 3
        else:
            query = str(input_data)
            mode = "step_by_step"
            context = ""
            max_steps = 3

        # 1. SmartMemory cache lookup
        if self._smart_memory:
            try:
                cached = self._smart_memory.check_cache(query)
                if cached and cached.get("response"):
                    answer = cached["response"]
                    steps = self._build_fallback_steps(query, max_steps)
                    duration_ms = int((time.time() - start) * 1000)
                    self._update_stats("fallback", duration_ms)
                    return ReasoningOutput(
                        answer=answer[:500],
                        confidence=0.5,
                        mode=mode,
                        steps=steps,
                        source="fallback",
                        total_duration_ms=duration_ms,
                    )
            except Exception as e:
                logger.debug(f"ReasoningAgent: SmartMemory lookup failed: {e}")

        # 2. SemanticEngine-assisted reasoning
        semantic_info = {}
        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                sem_result = self._semantic_engine.classify_intent(query)
                if sem_result and sem_result.confidence > 0.3:
                    semantic_info = {
                        "operation": sem_result.operation,
                        "goal": sem_result.goal,
                        "confidence": sem_result.confidence,
                    }
            except Exception as e:
                logger.debug(f"ReasoningAgent: SemanticEngine failed: {e}")

        # 3. Deterministic fallback reasoning
        answer = self._deterministic_reason(query, semantic_info)
        steps = self._build_fallback_steps(query, max_steps, answer)

        # Build context_used list
        context_used = []
        if semantic_info:
            context_used.append(
                f"semantic:{semantic_info['operation']}/{semantic_info['goal']}"
            )

        # Memory hits
        memory_hits = 0
        if self._smart_memory:
            try:
                if self._semantic_engine and self._semantic_engine.is_loaded:
                    similar = self._smart_memory.find_similar_solutions(query, top_k=2)
                    memory_hits = len(similar)
                    context_used.extend(
                        f"memory:{s.get('similarity', 0):.2f}" for s in similar
                    )
            except Exception:
                pass

        # Save to memory
        self._save_to_memory(query, answer, mode)

        # Estimate confidence
        confidence = 0.3
        if semantic_info and semantic_info.get("confidence", 0) > 0.5:
            confidence = 0.4
        if memory_hits > 0:
            confidence += 0.05

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        return ReasoningOutput(
            answer=answer,
            confidence=min(confidence, 0.5),
            mode=mode,
            steps=steps,
            refinements=0,
            context_used=context_used,
            memory_hits=memory_hits,
            source="fallback",
            total_duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    #  Private helpers
    # ------------------------------------------------------------------

    def _get_memory_context(self, query: str) -> str:
        """Obtiene contexto relevante de SmartMemory."""
        if not self._smart_memory:
            return ""
        parts = []

        try:
            working = self._smart_memory.get_working_context(max_tokens=100)
            if working:
                parts.append(working)
        except Exception:
            pass

        if self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                similar = self._smart_memory.find_similar_solutions(query, top_k=1)
                for sol in similar:
                    parts.append(f"Past: {sol.get('solution', '')[:100]}")
            except Exception:
                pass

        return " | ".join(parts) if parts else ""

    def _save_to_memory(self, query: str, answer: str, mode: str) -> None:
        """Guarda resultado en SmartMemory."""
        if not self._smart_memory:
            return
        try:
            self._smart_memory.save_to_cache(query, answer[:500], mode, "", 0.6)
        except Exception as e:
            logger.debug(f"ReasoningAgent: Memory save failed: {e}")

    def _deterministic_reason(self, problem: str, semantic_info: Dict[str, Any]) -> str:
        """Razonamiento determinista basado en tipo de problema."""
        problem_lower = problem.lower()

        # Detect problem type
        detected_type = None
        best_score = 0
        for ptype, keywords in PROBLEM_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in problem_lower)
            if score > best_score:
                best_score = score
                detected_type = ptype

        # Get template response
        if detected_type and detected_type in PROBLEM_TEMPLATES:
            answer = PROBLEM_TEMPLATES[detected_type]
        else:
            answer = (
                "Based on analysis, this requires a structured implementation with: "
                "(1) Data models and validation, (2) Business logic with error "
                "handling, (3) API endpoints or automation workflows, "
                "(4) Tests for critical paths."
            )

        # Enhance with semantic info if available
        if semantic_info:
            op = semantic_info.get("operation", "UNKNOWN")
            goal = semantic_info.get("goal", "UNKNOWN")
            answer = f"Semantic classification: {op}/{goal}. {answer}"

        return answer

    def _build_fallback_steps(self, problem: str, max_steps: int,
                              final_answer: str = "") -> List[ReasoningStep]:
        """Construye pasos de razonamiento deterministas."""
        steps = []
        problem_lower = problem.lower()

        # Step 1: Identify problem type
        type_desc = "general software engineering"
        for ptype, keywords in PROBLEM_KEYWORDS.items():
            if any(kw in problem_lower for kw in keywords):
                type_desc = ptype
                break

        steps.append(ReasoningStep(
            step_number=1,
            description=f"Identified problem type: {type_desc}",
            conclusion=f"This is a {type_desc} problem requiring structured implementation.",
        ))

        # Step 2: Apply standard patterns
        if max_steps >= 2:
            steps.append(ReasoningStep(
                step_number=2,
                description="Apply standard patterns for this problem type",
                conclusion="Apply: validate inputs, process business logic, "
                           "handle errors gracefully, return structured results.",
            ))

        # Step 3: Final conclusion
        if max_steps >= 3:
            steps.append(ReasoningStep(
                step_number=3,
                description="Synthesize final answer",
                conclusion=final_answer[:200] if final_answer else
                           "Implementation should follow established patterns "
                           "with proper error handling and validation.",
            ))

        return steps[:max_steps]
