"""
A40 DeterministicPipeline — SINGLE RESPONSIBILITY: Execute all 7 deterministic tasks without AI.

Deterministic pipeline that replaces ALL MiniAIEngine tasks.
No AI. No LLM calls. Pure algorithmic processing.

7 Deterministic Tasks:
  1. classify_intent()    → Keyword scoring
  2. extract_entities()   → Regex extraction + extension mapping
  3. suggest_pattern()    → Heuristic lookup table
  4. fill_template_gaps() → Context mapping + defaults
  5. generate_pattern()   → Template library composition
  6. explain_violation()  → Violation catalog lookup
  7. describe_subtask()   → Name auto-composition

Ported from:
  - verdict_parts/deterministic_pipeline.py (standalone class)
  - mini_ai_parts/_tasks.py (BoundedTasksMixin)

DEPRECATED: This agent violates the SRP invariant (7 tasks in 1 agent).
Individual A01-A04 agents should be used instead. This module will be
split into separate agents (A40a-A40g) in a future refactoring.
"""

from __future__ import annotations

from typing import Any

from ...resilience import BaseAgent
from ...schemas import PipelineResult
from ._tasks_mixin import DeterministicTasksMixin


class DeterministicPipeline(DeterministicTasksMixin, BaseAgent[PipelineResult]):
    """
    A40: Execute all 7 deterministic tasks without AI.

    Single Responsibility: Deterministic task pipeline ONLY.
    Method: Pure algorithmic processing (no LLM, no AI).
    Fallback: Return empty results with low confidence.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A40_DeterministicPipeline", **kwargs)

    def execute(self, input_data: Any) -> PipelineResult:
        """
        Execute all 7 deterministic tasks.

        input_data can be:
          - dict with 'text', 'code' (optional), 'language' (optional), 'context' (optional)
          - str (raw text, treated as query)
        """
        text, code, language, context = self._parse_input(input_data)

        # Task 1: Classify intent
        classify = self._classify_intent(text)

        # Task 2: Extract entities
        extract = self._extract_entities(text)

        # Task 3: Suggest pattern
        target = extract.get("file", "") if isinstance(extract, dict) else "target"
        pattern = self._suggest_pattern(target, text)

        # Task 4: Fill template gaps (only if template provided)
        template = context.get("template", "") if isinstance(context, dict) else ""
        fill = self._fill_template_gaps(template, context) if template else {
            "result": "", "confidence": 1.0, "source": "deterministic",
        }

        # Task 5: Generate pattern (only if code context provided)
        if code:
            generate = self._generate_pattern(
                pattern.get("result", "default") if isinstance(pattern, dict) else "default",
                language, context,
            )
        else:
            generate = {
                "result": "", "confidence": 1.0, "source": "deterministic",
            }

        # Task 6: Explain violation (only if violations provided)
        violations = context.get("violations", []) if isinstance(context, dict) else []
        explain = self._explain_violation(code, violations)

        # Task 7: Describe subtask
        action = classify.get("operation", "process") if isinstance(classify, dict) else "process"
        subtask = self._describe_subtask(target or "target", action)

        return PipelineResult(
            classify=classify,
            extract=extract,
            pattern=pattern,
            fill=fill,
            generate=generate,
            explain=explain,
            subtask=subtask,
            source="deterministic",
        )

    def _parse_input(self, input_data: Any) -> tuple:
        """Parse input into (text, code, language, context)."""
        if isinstance(input_data, str):
            return input_data, "", "python", {}
        elif isinstance(input_data, dict):
            text = input_data.get("text", input_data.get("query", ""))
            code = input_data.get("code", "")
            language = input_data.get("language", "python")
            context = input_data.get("context", {})
            return text, code, language, context
        return "", "", "python", {}

    def fallback(self, input_data: Any) -> PipelineResult:
        """Fallback: Return empty pipeline result."""
        return PipelineResult(source="fallback")
