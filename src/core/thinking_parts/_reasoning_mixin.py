"""
Reasoning methods mixin for ThinkingEngine — reason, evaluate_code,
decompose_problem, design_architecture, chain_of_thought.
"""

import re
import json
import time

from ._imports import (
    logger, MAX_THINKING_TOKENS, MAX_PLAN_TOKENS, MAX_DECOMPOSE_TOKENS,
    MAX_EVALUATE_TOKENS, CHAIN_MAX_STEPS, ThinkingResult,
    AUTOMATION_TEMPLATES, APP_TEMPLATES, GenerationPlan,
)


class ReasoningMixin:
    """Reasoning methods for ThinkingEngine."""

    def reason(self, query: str, context: str = "") -> ThinkingResult:
        """Razonamiento general con contexto inyectado."""
        start = time.time()
        full_query = query
        if context:
            full_query = f"{query}\n\nAdditional context: {context[:500]}"

        answer = self._call_with_context(
            system_prompt="You are a code architect. Think step by step. Give a concise, actionable answer.",
            user_prompt=full_query,
            max_tokens=MAX_THINKING_TOKENS,
            query=query,
        )

        elapsed = time.time() - start

        if answer and len(answer) > 10:
            return ThinkingResult(
                answer=answer,
                confidence=0.7,
                source="thinking",
                context_used=True,
                memory_hits=1 if self._memory else 0,
                thinking_time_s=elapsed,
            )

        if self._semantic and self._semantic.is_loaded:
            sem = self._semantic.classify_intent(query)
            return ThinkingResult(
                answer=f"Based on semantic analysis, this is a {sem.operation} request with goal {sem.goal}.",
                confidence=sem.confidence,
                source="semantic_fallback",
                context_used=False,
                thinking_time_s=elapsed,
            )

        return ThinkingResult(
            answer="Unable to reason about this query without AI models.",
            confidence=0.1,
            source="no_model",
            thinking_time_s=elapsed,
        )

    def evaluate_code(self, code: str, language: str = "python") -> dict:
        """Evalúa la calidad del código generado."""
        issues = []
        suggestions = []

        if language == "python":
            if "eval(" in code:
                issues.append("SECURITY: eval() usage detected - potential code injection")
            if "exec(" in code:
                issues.append("SECURITY: exec() usage detected - potential code injection")
            if "os.system(" in code:
                issues.append("SECURITY: os.system() - use subprocess instead")
            if "import pickle" in code:
                issues.append("SECURITY: pickle can deserialize malicious data")
            if "TODO" in code or "FIXME" in code:
                issues.append("QUALITY: Unresolved TODO/FIXME markers")
            if "try:" not in code and "def " in code:
                suggestions.append("ROBUSTNESS: Add error handling (try/except blocks)")
            if '"""' not in code and "'''" not in code:
                suggestions.append("DOCUMENTATION: Add docstrings to functions/classes")
            if "type" not in code and "def " in code:
                suggestions.append("TYPE SAFETY: Add type hints for better code quality")
            func_count = code.count("def ")
            if func_count > 10:
                suggestions.append(f"STRUCTURE: {func_count} functions - consider splitting into modules")

        if self._ai and self._ai.is_loaded:
            code_snippet = code[:500] if len(code) > 500 else code
            answer = self._call_with_context(
                system_prompt='Evaluate this code quality. Reply JSON: {"score":0.8,"issues":["issue1"],"suggestions":["sug1"]}',
                user_prompt=f"Code ({language}):\n{code_snippet}",
                max_tokens=MAX_EVALUATE_TOKENS,
                query="evaluate code quality",
            )
            if answer:
                try:
                    match = re.search(r'\{.*\}', answer, re.DOTALL)
                    if match:
                        eval_result = json.loads(match.group())
                        if "score" in eval_result:
                            ai_score = float(eval_result["score"])
                            if isinstance(eval_result.get("issues"), list):
                                issues.extend(eval_result["issues"][:3])
                            if isinstance(eval_result.get("suggestions"), list):
                                suggestions.extend(eval_result["suggestions"][:3])
                            return {
                                "quality_score": ai_score,
                                "issues": issues,
                                "suggestions": suggestions,
                                "source": "thinking",
                            }
                except (json.JSONDecodeError, ValueError):
                    pass

        base_score = 0.7
        base_score -= len(issues) * 0.1
        base_score += min(len(suggestions) * 0.02, 0.1)
        base_score = max(0.1, min(1.0, base_score))

        return {
            "quality_score": base_score,
            "issues": issues,
            "suggestions": suggestions,
            "source": "static_analysis",
        }

    def decompose_problem(self, problem: str) -> list:
        """Descompone un problema complejo en subproblemas más simples."""
        answer = self._call_with_context(
            system_prompt='Decompose this problem into subproblems. Reply with JSON array: [{"name":"sub1","description":"what to do","priority":"high"}]. Max 5 subproblems.',
            user_prompt=problem,
            max_tokens=MAX_DECOMPOSE_TOKENS,
            query=problem,
        )
        if answer:
            try:
                match = re.search(r'\[.*\]', answer, re.DOTALL)
                if match:
                    subproblems = json.loads(match.group())
                    if isinstance(subproblems, list):
                        return subproblems[:5]
            except (json.JSONDecodeError, ValueError):
                pass
        return self._fallback_decompose(problem)

    def _fallback_decompose(self, problem: str) -> list:
        """Descomposición determinística basada en keywords."""
        subproblems = [
            {"name": "analyze_requirements", "description": "Analyze the requirements and define scope", "priority": "high"},
            {"name": "design_data_model", "description": "Design the data model and database schema", "priority": "high"},
            {"name": "implement_api", "description": "Implement API endpoints and business logic", "priority": "high"},
            {"name": "add_validation", "description": "Add input validation and error handling", "priority": "medium"},
            {"name": "create_tests", "description": "Create test cases for critical paths", "priority": "medium"},
        ]
        problem_lower = problem.lower()
        if any(kw in problem_lower for kw in ["auth", "login", "seguridad"]):
            subproblems.insert(2, {"name": "implement_auth", "description": "Implement authentication and authorization", "priority": "high"})
        if any(kw in problem_lower for kw in ["email", "notificacion", "notification"]):
            subproblems.insert(3, {"name": "setup_notifications", "description": "Setup notification/email system", "priority": "medium"})
        if any(kw in problem_lower for kw in ["reporte", "report", "pdf"]):
            subproblems.insert(3, {"name": "setup_reports", "description": "Setup report generation system", "priority": "medium"})
        return subproblems[:5]

    def design_architecture(self, request: str) -> dict:
        """Diseña una arquitectura completa para una app o automatización."""
        plan = self.plan_generation(request)
        answer = self._call_with_context(
            system_prompt='Design a software architecture. Reply JSON: {"type":"monolith","components":[{"name":"api","tech":"FastAPI","desc":"..."}],"data_flow":"request → api → service → db","tech_stack":["FastAPI","SQLite","Jinja2"]}',
            user_prompt=f"Design architecture for: {request}\nTemplate: {plan.template_type}\nEntities: {[e['name'] for e in plan.entities]}",
            max_tokens=MAX_PLAN_TOKENS,
            query=request,
        )
        if answer:
            try:
                match = re.search(r'\{.*\}', answer, re.DOTALL)
                if match:
                    arch = json.loads(match.group())
                    arch["generation_plan"] = plan
                    arch["source"] = "thinking"
                    return arch
            except (json.JSONDecodeError, ValueError):
                pass
        return self._fallback_architecture(plan)

    def _fallback_architecture(self, plan: GenerationPlan) -> dict:
        """Arquitectura por defecto según template."""
        is_automation = plan.template_type in AUTOMATION_TEMPLATES
        if is_automation:
            return {
                "type": "worker",
                "components": [
                    {"name": "scheduler", "tech": "APScheduler", "desc": "Job scheduling and triggers"},
                    {"name": "workers", "tech": "Python asyncio", "desc": "Background task execution"},
                    {"name": "db", "tech": "SQLite", "desc": "Job state and history"},
                    {"name": "notifications", "tech": "smtplib", "desc": "Email/notification alerts"},
                ],
                "data_flow": "trigger → scheduler → worker → db → notification",
                "tech_stack": ["Python 3.10+", "APScheduler", "SQLite", "smtplib"],
                "generation_plan": plan,
                "source": "fallback",
            }
        return {
            "type": "monolith",
            "components": [
                {"name": "api", "tech": "FastAPI", "desc": "REST API endpoints"},
                {"name": "models", "tech": "dataclasses/SQLite", "desc": "Data models and ORM"},
                {"name": "services", "tech": "Python", "desc": "Business logic layer"},
                {"name": "templates", "tech": "Jinja2", "desc": "HTML templates for dashboard"},
                {"name": "static", "tech": "CSS/JS", "desc": "Frontend assets"},
            ],
            "data_flow": "request → FastAPI → service → SQLite → response/HTML",
            "tech_stack": ["FastAPI", "SQLite", "Jinja2", "uvicorn"],
            "generation_plan": plan,
            "source": "fallback",
        }

    def chain_of_thought(self, problem: str, max_steps: int = CHAIN_MAX_STEPS) -> ThinkingResult:
        """Razonamiento multi-paso (Chain of Thought)."""
        steps = []
        current_context = problem
        start = time.time()

        for step_num in range(max_steps):
            step_result = self._call_with_context(
                system_prompt=f"You are solving a problem step by step. This is step {step_num + 1} of {max_steps}. Think carefully and give your reasoning.",
                user_prompt=current_context,
                max_tokens=MAX_THINKING_TOKENS,
                query=problem,
            )
            if not step_result:
                break
            steps.append(step_result)
            current_context = f"Previous reasoning: {step_result[:200]}\n\nNow continue reasoning about: {problem}"
            conclusion_markers = ["therefore", "in conclusion", "the answer is", "final answer", "por lo tanto", "en conclusión"]
            if any(marker in step_result.lower() for marker in conclusion_markers):
                break

        elapsed = time.time() - start

        if steps:
            return ThinkingResult(
                answer=steps[-1],
                confidence=min(0.5 + len(steps) * 0.15, 0.9),
                source="chain_of_thought",
                context_used=True,
                memory_hits=len(steps),
                thinking_time_s=elapsed,
            )
        return ThinkingResult(
            answer="Chain of thought could not produce reasoning steps.",
            confidence=0.1,
            source="no_model",
            thinking_time_s=elapsed,
        )

    @property
    def stats(self) -> dict:
        """Estadísticas del ThinkingEngine."""
        return {
            "total_calls": self._call_count,
            "total_thinking_time_s": round(self._thinking_time, 2),
            "ai_available": self._ai is not None and self._ai.is_loaded,
            "semantic_available": self._semantic is not None and self._semantic.is_loaded,
            "memory_available": self._memory is not None,
            "app_templates": len(APP_TEMPLATES),
            "automation_templates": len(AUTOMATION_TEMPLATES),
        }
