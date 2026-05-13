"""
Step-by-step reasoning mixin for ReasoningEngine.
"""

import time
import logging
from typing import List

from ._imports import (
    logger, ReasoningStep, ReasoningResult, ReasoningMode,
    MAX_REASONING_STEPS, MAX_TOKENS_PER_STEP, MIN_CONFIDENCE_ACCEPT,
)


class StepByStepMixin:
    """Mixin providing step_by_step reasoning mode."""

    def step_by_step(self, problem: str, max_steps: int = MAX_REASONING_STEPS,
                     context: str = "") -> ReasoningResult:
        """
        Razonamiento estructurado paso a paso.

        Descompone el problema en pasos explícitos:
          Step 1: Identificar el tipo de problema
          Step 2: Aplicar el razonamiento adecuado
          Step 3: Llegar a una conclusión verificable

        Cada paso produce un resultado estructurado que alimenta el siguiente.
        Si un paso falla o tiene baja confianza, el sistema ajusta su enfoque.
        """
        start = time.time()
        self._call_count += 1
        steps: List[ReasoningStep] = []
        accumulated = f"Problem: {problem}"
        if context:
            accumulated += f"\nAdditional context: {context[:300]}"

        # Inject memory context
        mem_ctx = self._get_memory_context(problem)
        if mem_ctx:
            accumulated += f"\n{mem_ctx}"

        for step_num in range(1, max_steps + 1):
            step_start = time.time()
            step_prompt = self._build_step_prompt(step_num, max_steps, accumulated, problem)
            answer = self._call_ai(
                system_prompt=f"You are solving a problem step by step. Step {step_num} of {max_steps}. Think carefully and give a clear, concise answer for this step only.",
                user_prompt=step_prompt,
                max_tokens=MAX_TOKENS_PER_STEP,
            )
            duration_ms = (time.time() - step_start) * 1000

            if answer:
                # Extract conclusion from step
                conclusion = self._extract_conclusion(answer)
                confidence = self._estimate_confidence(answer, step_num, max_steps)
                step = ReasoningStep(
                    step_number=step_num,
                    thought=answer[:300],
                    conclusion=conclusion,
                    confidence=confidence,
                    duration_ms=duration_ms,
                    source="llm",
                )
                steps.append(step)
                accumulated += f"\nStep {step_num} conclusion: {conclusion}"
            else:
                # LLM failed for this step - use deterministic fallback
                fallback_conclusion = self._fallback_step(step_num, problem, steps)
                step = ReasoningStep(
                    step_number=step_num,
                    thought=fallback_conclusion,
                    conclusion=fallback_conclusion,
                    confidence=0.3,
                    duration_ms=duration_ms,
                    source="fallback",
                )
                steps.append(step)
                accumulated += f"\nStep {step_num} conclusion: {fallback_conclusion}"

        # Build final result
        final_conclusion = steps[-1].conclusion if steps else ""
        avg_confidence = sum(s.confidence for s in steps) / len(steps) if steps else 0.0
        total_ms = (time.time() - start) * 1000

        # If confidence is too low, try to enhance with semantic analysis
        if avg_confidence < MIN_CONFIDENCE_ACCEPT and self._semantic and self._semantic.is_loaded:
            sem = self._semantic.classify_intent(problem)
            if sem.confidence > avg_confidence:
                final_conclusion = f"Based on semantic analysis: {sem.operation}/{sem.goal}. {final_conclusion}"
                avg_confidence = (avg_confidence + sem.confidence) / 2

        # Save to memory
        self._save_to_memory(problem, final_conclusion, "step_by_step", avg_confidence)

        elapsed = time.time() - start
        self._total_time += elapsed

        return ReasoningResult(
            answer=final_conclusion,
            confidence=avg_confidence,
            mode=ReasoningMode.STEP_BY_STEP,
            steps=steps,
            total_duration_ms=total_ms,
            context_used=bool(mem_ctx),
            memory_hits=1 if mem_ctx else 0,
            source="llm" if any(s.source == "llm" for s in steps) else "fallback",
        )
