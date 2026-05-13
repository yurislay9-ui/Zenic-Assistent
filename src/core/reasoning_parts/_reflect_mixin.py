"""
Self-reflect reasoning mixin for ReasoningEngine.
"""

import re
import json
import time
import logging
from typing import List

from ._imports import (
    logger, ReasoningStep, ReasoningResult, ReasoningMode,
    MAX_TOKENS_PER_STEP, MIN_CONFIDENCE_ACCEPT,
)


class SelfReflectMixin:
    """Mixin providing self_reflect reasoning mode."""

    def self_reflect(self, problem: str, max_iterations: int = 2,
                     context: str = "") -> ReasoningResult:
        """
        Razonamiento con auto-evaluación y corrección.

        Ciclo iterativo:
          1. GENERATE: Producir una respuesta inicial
          2. EVALUATE: Evaluar la calidad de la respuesta
          3. REFINE: Mejorar la respuesta basándose en la evaluación

        Se repite hasta alcanzar confianza aceptable o agotar iteraciones.
        Este es el modo más confiable pero también el más costoso en tokens.
        """
        start = time.time()
        self._call_count += 1
        all_steps: List[ReasoningStep] = []

        # Inject context
        mem_ctx = self._get_memory_context(problem)
        full_problem = problem
        if context:
            full_problem += f"\nContext: {context[:300]}"
        if mem_ctx:
            full_problem += f"\n{mem_ctx}"

        current_answer = ""
        current_confidence = 0.0
        eval_issues = []

        for iteration in range(1, max_iterations + 1):
            # PHASE 1: GENERATE
            gen_start = time.time()
            if iteration == 1:
                gen_answer = self._call_ai(
                    system_prompt="You are a careful problem solver. Give a clear, complete answer. Think about potential issues with your answer.",
                    user_prompt=full_problem,
                    max_tokens=MAX_TOKENS_PER_STEP + 50,
                )
            else:
                # Refine: include previous evaluation
                gen_answer = self._call_ai(
                    system_prompt="You are refining your previous answer based on self-evaluation. Improve it, fix issues, and make it more accurate.",
                    user_prompt=f"Original problem: {problem}\n\nPrevious answer: {current_answer}\n\nIssues found: {eval_issues}\n\nProvide an improved answer:",
                    max_tokens=MAX_TOKENS_PER_STEP + 50,
                )

            gen_duration = (time.time() - gen_start) * 1000

            if not gen_answer:
                # Fallback generation
                gen_answer = self._fallback_generate(problem, iteration)
                current_confidence = 0.3
            else:
                current_confidence = 0.6  # Base confidence for LLM generation

            current_answer = gen_answer

            all_steps.append(ReasoningStep(
                step_number=iteration * 2 - 1,
                thought=f"GENERATE (iteration {iteration})",
                conclusion=gen_answer[:300],
                confidence=current_confidence,
                duration_ms=gen_duration,
                source="llm" if gen_answer else "fallback",
            ))

            # PHASE 2: EVALUATE
            eval_start = time.time()
            eval_answer = self._call_ai(
                system_prompt='Evaluate this answer for correctness, completeness, and potential issues. Reply JSON: {"score":0.8,"issues":["issue1"],"missing":["what is missing"]}',
                user_prompt=f"Problem: {problem}\n\nAnswer: {current_answer[:500]}",
                max_tokens=200,
            )
            eval_duration = (time.time() - eval_start) * 1000

            eval_score = 0.5
            if eval_answer:
                try:
                    match = re.search(r'\{[^}]+\}', eval_answer, re.DOTALL)
                    if match:
                        eval_data = json.loads(match.group())
                        eval_score = float(eval_data.get("score", 0.5))
                        eval_issues = eval_data.get("issues", [])
                except (json.JSONDecodeError, ValueError, TypeError):
                    eval_issues = ["Could not parse evaluation"]
            else:
                # Fallback evaluation: basic heuristic checks
                eval_score, eval_issues = self._fallback_evaluate(current_answer, problem)

            all_steps.append(ReasoningStep(
                step_number=iteration * 2,
                thought=f"EVALUATE (iteration {iteration})",
                conclusion=f"Score: {eval_score:.2f}, Issues: {', '.join(eval_issues[:3]) if eval_issues else 'None'}",
                confidence=eval_score,
                duration_ms=eval_duration,
                source="llm" if eval_answer else "fallback",
            ))

            current_confidence = eval_score

            # If confidence is acceptable, stop refining
            if eval_score >= MIN_CONFIDENCE_ACCEPT + 0.2:  # Higher threshold for self-reflect
                break

        total_ms = (time.time() - start) * 1000

        # Save to memory
        self._save_to_memory(problem, current_answer, "self_reflect", current_confidence)

        return ReasoningResult(
            answer=current_answer,
            confidence=current_confidence,
            mode=ReasoningMode.SELF_REFLECT,
            steps=all_steps,
            total_duration_ms=total_ms,
            refinements=max(0, len(all_steps) // 2 - 1),
            context_used=bool(mem_ctx),
            memory_hits=1 if mem_ctx else 0,
            source="llm" if any(s.source == "llm" for s in all_steps) else "fallback",
        )
