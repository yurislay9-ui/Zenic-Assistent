"""
Internal helpers and fallback methods mixin for ReasoningEngine.
"""

import re
from typing import Optional, Dict, Any, List, Tuple

from ._imports import (
    logger, ReasoningStep, ReasoningResult, ReasoningMode,
)


class HelpersMixin:
    """Mixin with internal helper methods and deterministic fallbacks."""

    # ================================================================
    #  INTERNAL HELPERS
    # ================================================================

    def _call_ai(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """Call MiniAIEngine if available."""
        if not self._ai or not self._ai.is_loaded:
            return None
        try:
            return self._ai._call_llm(system_prompt, user_prompt, max_tokens)
        except Exception as e:
            logger.warning(f"ReasoningEngine: AI call failed: {e}")
            return None

    def _get_memory_context(self, query: str) -> str:
        """Get relevant context from SmartMemory."""
        if not self._memory:
            return ""
        parts = []

        # Working memory
        working = self._memory.get_working_context(max_tokens=100)
        if working:
            parts.append(working)

        # Similar past solutions
        if self._semantic and self._semantic.is_loaded:
            similar = self._memory.find_similar_solutions(query, top_k=1)
            for sol in similar:
                parts.append(f"Past: {sol['solution'][:100]}")

        return " | ".join(parts) if parts else ""

    def _save_to_memory(self, query: str, answer: str, mode: str, confidence: float) -> None:
        """Save reasoning result to memory for future use."""
        if not self._memory:
            return
        importance = min(confidence, 0.9)
        if confidence >= 0.6:
            self._memory.save_to_cache(query, answer[:500], mode, "", importance)

    def _build_step_prompt(self, step_num: int, max_steps: int,
                           accumulated: str, problem: str) -> str:
        """Build the prompt for a specific reasoning step."""
        if step_num == 1:
            return f"First, identify the type and key aspects of this problem:\n{accumulated}"
        elif step_num == max_steps:
            return f"Based on all previous analysis, provide the final conclusion:\nPrevious steps: {accumulated}\n\nOriginal problem: {problem}"
        else:
            return f"Based on previous analysis, apply reasoning step {step_num}:\n{accumulated}\n\nWhat is the next logical step?"

    def _extract_conclusion(self, text: str) -> str:
        """Extract the core conclusion from a reasoning step."""
        # Look for conclusion markers
        markers = ["therefore", "thus", "conclusion:", "so,", "hence",
                    "por lo tanto", "en conclusión", "resultado:"]
        text_lower = text.lower()
        for marker in markers:
            idx = text_lower.find(marker)
            if idx >= 0:
                return text[idx + len(marker):].strip()[:200]

        # Fallback: return last meaningful sentence
        sentences = re.split(r'[.!?]\s', text)
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 10]
        return meaningful[-1] if meaningful else text[:200]

    def _estimate_confidence(self, text: str, step_num: int, max_steps: int) -> float:
        """Estimate confidence of a reasoning step."""
        base = 0.5
        # Longer, more detailed answers tend to be better
        if len(text) > 50:
            base += 0.1
        if len(text) > 150:
            base += 0.05
        # Later steps benefit from earlier analysis
        base += (step_num / max_steps) * 0.15
        # Presence of certainty markers
        certainty = ["certainly", "clearly", "definitely", "obviously", "surely"]
        if any(m in text.lower() for m in certainty):
            base += 0.05
        # Presence of hedging
        hedging = ["maybe", "perhaps", "might", "could be", "possibly"]
        if any(m in text.lower() for m in hedging):
            base -= 0.1
        return max(0.1, min(0.95, base))

    def _estimate_complexity(self, problem: str) -> float:
        """Estimate problem complexity for auto mode selection."""
        score = 0.0
        # Longer problems tend to be more complex
        words = problem.split()
        if len(words) > 20:
            score += 0.2
        elif len(words) > 10:
            score += 0.1

        # Multiple concepts indicate complexity
        concept_markers = ["and", "but", "however", "also", "while", "additionally",
                          "y", "pero", "sin embargo", "además", "también"]
        for marker in concept_markers:
            if marker in problem.lower():
                score += 0.1

        # Technical terms increase complexity
        tech_terms = ["api", "database", "auth", "microservice", "pipeline",
                     "webhook", "scheduler", "orm", "cache", "async"]
        for term in tech_terms:
            if term in problem.lower():
                score += 0.1

        # Semantic confidence as complexity indicator
        if self._semantic and self._semantic.is_loaded:
            sem = self._semantic.classify_intent(problem)
            if sem.confidence < 0.3:
                score += 0.2  # Low confidence = complex

        return min(score, 1.0)

    # ================================================================
    #  FALLBACK METHODS (deterministic, no LLM)
    # ================================================================

    def _fallback_step(self, step_num: int, problem: str,
                       previous_steps: List[ReasoningStep]) -> str:
        """Deterministic fallback for a reasoning step."""
        problem_lower = problem.lower()

        if step_num == 1:
            # Classify the problem type
            if any(kw in problem_lower for kw in ["api", "endpoint", "rest"]):
                return "This is an API design problem requiring endpoint definition and data modeling."
            elif any(kw in problem_lower for kw in ["auth", "login", "seguridad"]):
                return "This is an authentication/authorization problem requiring security implementation."
            elif any(kw in problem_lower for kw in ["database", "datos", "schema"]):
                return "This is a data modeling problem requiring schema design and CRUD operations."
            elif any(kw in problem_lower for kw in ["automat", "workflow", "schedule"]):
                return "This is an automation problem requiring workflow design and action chaining."
            else:
                return "This appears to be a general software engineering problem requiring analysis and implementation."

        elif step_num == 2:
            return "Apply standard patterns: validate inputs, process business logic, handle errors gracefully, and return structured results."

        else:
            return "Implementation should follow established patterns with proper error handling and validation."

    def _fallback_generate(self, problem: str, iteration: int) -> str:
        """Deterministic fallback for answer generation."""
        problem_lower = problem.lower()

        # Template-based responses for common problem types
        if any(kw in problem_lower for kw in ["api", "endpoint", "rest"]):
            return "Design a REST API with proper endpoints, request/response schemas, authentication middleware, and error handling. Use FastAPI for the framework and SQLite for persistence."
        elif any(kw in problem_lower for kw in ["auth", "login", "seguridad"]):
            return "Implement JWT-based authentication with token refresh, password hashing (bcrypt/PBKDF2), RBAC for authorization, and API key support for service-to-service communication."
        elif any(kw in problem_lower for kw in ["database", "datos", "schema"]):
            return "Design a normalized database schema with proper foreign keys, indexes for query performance, parameterized queries for security, and migration scripts for schema evolution."
        elif any(kw in problem_lower for kw in ["invoice", "factura", "billing"]):
            return "Build an invoice system with line items, tax calculation, discount support, PDF generation, and payment tracking. Use parameterized SQL for all database operations."
        elif any(kw in problem_lower for kw in ["inventory", "stock", "almacen"]):
            return "Create an inventory management system with stock tracking, low-stock alerts, movement history, and reporting. Implement CRUD operations with validation."
        elif any(kw in problem_lower for kw in ["crm", "cliente", "customer"]):
            return "Develop a CRM with lead pipeline management, contact tracking, sales stage progression, and conversion analytics. Include email notification for stage changes."
        else:
            return f"Based on analysis, this requires a structured implementation with: (1) Data models and validation, (2) Business logic with error handling, (3) API endpoints or automation workflows, (4) Tests for critical paths."

    def _fallback_evaluate(self, answer: str, problem: str) -> Tuple[float, List[str]]:
        """Deterministic evaluation of an answer."""
        issues = []
        score = 0.5

        if len(answer) < 30:
            issues.append("Answer is too short to be complete")
            score -= 0.2
        if "TODO" in answer or "FIXME" in answer:
            issues.append("Answer contains unresolved TODO markers")
            score -= 0.1
        if re.search(r'\bpass\b', answer) and len(answer) < 100:
            issues.append("Answer appears to be a placeholder")
            score -= 0.15
        if any(kw in answer.lower() for kw in ["eval(", "exec(", "os.system("]):
            issues.append("Answer contains security risks")
            score -= 0.2

        # Positive indicators
        if "error" in answer.lower() or "exception" in answer.lower():
            score += 0.1  # Error handling is good
        if "valid" in answer.lower() or "check" in answer.lower():
            score += 0.05  # Validation is good

        return max(0.1, min(0.9, score)), issues

    def _fallback_context_reasoning(self, problem: str, semantic_info: Dict[str, Any]) -> str:
        """Fallback reasoning using semantic info only."""
        op = semantic_info.get("operation", "UNKNOWN")
        goal = semantic_info.get("goal", "UNKNOWN")
        return f"Based on semantic classification as {op}/{goal}, this requires a {op.lower()}-oriented approach focusing on {goal.lower().replace('_', ' ')}."

    def _full_fallback(self, problem: str) -> ReasoningResult:
        """Complete fallback when no AI model is available."""
        answer = self._fallback_generate(problem, 1)
        return ReasoningResult(
            answer=answer,
            confidence=0.25,
            mode=ReasoningMode.FALLBACK,
            steps=[ReasoningStep(
                step_number=1,
                thought="No AI model available, using deterministic fallback",
                conclusion=answer[:200],
                confidence=0.25,
                source="fallback",
            )],
            source="fallback",
        )
