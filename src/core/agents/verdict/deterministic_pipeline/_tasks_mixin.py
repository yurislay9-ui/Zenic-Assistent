"""
Deterministic Pipeline Tasks Mixin — All 7 deterministic task methods.

Provides mixin class with:
  - _classify_intent() / classify_intent()
  - _extract_entities() / extract_entities()
  - _suggest_pattern() / suggest_pattern()
  - _fill_template_gaps() / fill_template_gaps()
  - _generate_pattern() / generate_pattern()
  - _explain_violation() / explain_violation()
  - _describe_subtask() / describe_subtask()
"""

from __future__ import annotations

import os
import re
from typing import Any

from ._constants import (
    EXT_LANG_MAP, OP_KEYWORDS, GOAL_KEYWORDS,
    PATTERN_HEURISTICS, PATTERN_LIBRARY,
    VIOLATION_CATALOG, GAP_DEFAULTS,
)


class DeterministicTasksMixin:
    """Mixin providing all 7 deterministic task methods."""

    # ──────────────────────────────────────────────────────────
    #  TASK 1: classify_intent
    # ──────────────────────────────────────────────────────────

    def _classify_intent(self, text: str) -> dict[str, Any]:
        """Classify user intent using keyword scoring (EN + ES)."""
        if not text:
            return {"operation": "SEARCH", "goal": "FEATURE_ADD", "confidence": 0.0, "source": "deterministic"}

        text_lower = text.lower()

        # Score operations
        best_op = "SEARCH"
        best_op_score = 0
        for op, keywords in OP_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_op_score:
                best_op_score = score
                best_op = op

        # Score goals
        best_goal = "FEATURE_ADD"
        best_goal_score = 0
        for goal, keywords in GOAL_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_goal_score:
                best_goal_score = score
                best_goal = goal

        # Confidence based on match strength
        total_keywords = len(text_lower.split())
        confidence = min(0.9, (best_op_score + best_goal_score) / max(total_keywords, 1) * 3)
        confidence = max(0.3, confidence)

        return {
            "operation": best_op,
            "goal": best_goal,
            "confidence": round(confidence, 2),
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 2: extract_entities
    # ──────────────────────────────────────────────────────────

    def _extract_entities(self, text: str) -> dict[str, Any]:
        """Extract entities (file, language, function) using regex."""
        if not text:
            return {"file": "", "lang": "unknown", "function": None, "confidence": 0.0, "source": "deterministic"}

        # File extraction
        file_match = re.search(
            r'([\w\.-]+\.(py|kt|go|js|ts|java|rs|rb|cpp|c|h))', text
        )
        file_name = file_match.group(1) if file_match else ""

        # Language from extension
        ext = os.path.splitext(file_name)[1] if file_name else ""
        lang = EXT_LANG_MAP.get(ext, "unknown")

        # Function name extraction
        func_match = re.search(r'(?:function|func|def|fun)\s+(\w+)', text)
        function = func_match.group(1) if func_match else None

        # Language from keywords (fallback)
        if lang == "unknown":
            text_lower = text.lower()
            if "python" in text_lower or "def " in text:
                lang = "python"
            elif "javascript" in text_lower or "function " in text or "const " in text:
                lang = "javascript"
            elif "typescript" in text_lower or ": string" in text or ": number" in text:
                lang = "typescript"
            elif "kotlin" in text_lower or "fun " in text:
                lang = "kotlin"
            elif "golang" in text_lower or "go " in text_lower or "func " in text:
                lang = "go"

        confidence = 0.9 if file_name else (0.6 if lang != "unknown" else 0.2)

        return {
            "file": file_name,
            "lang": lang,
            "function": function,
            "confidence": confidence,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 3: suggest_pattern
    # ──────────────────────────────────────────────────────────

    def _suggest_pattern(self, target: str, description: str) -> dict[str, Any]:
        """Suggest a code pattern using heuristics."""
        desc_lower = description.lower()
        target_lower = target.lower()
        combined = f"{desc_lower} {target_lower}"

        for keywords, pattern_name in PATTERN_HEURISTICS:
            if any(kw in combined for kw in keywords):
                return {
                    "result": f"{pattern_name}_pattern",
                    "confidence": 0.8,
                    "source": "deterministic",
                }

        return {
            "result": "default_pattern",
            "confidence": 0.3,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 4: fill_template_gaps
    # ──────────────────────────────────────────────────────────

    def _fill_template_gaps(
        self, template: str, context: Any
    ) -> dict[str, Any]:
        """Fill template gaps with context and defaults."""
        if not template:
            return {"result": "", "confidence": 1.0, "source": "deterministic"}

        gaps = re.findall(r'__GAP_(\w+)__', template)
        if not gaps:
            return {"result": template, "confidence": 1.0, "source": "deterministic"}

        ctx = context if isinstance(context, dict) else {}
        result = template
        for gap in gaps:
            gap_lower = gap.lower()
            # Try context first (case-insensitive)
            value = None
            if gap_lower in ctx:
                value = ctx[gap_lower]
            elif gap in ctx:
                value = ctx[gap]
            elif gap in GAP_DEFAULTS:
                value = GAP_DEFAULTS[gap]
            else:
                value = f"placeholder_{gap_lower}"

            result = result.replace(f"__GAP_{gap}__", str(value))

        all_filled = not re.search(r'__GAP_\w+__', result)
        confidence = 1.0 if all_filled else 0.5

        return {
            "result": result,
            "confidence": confidence,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 5: generate_pattern
    # ──────────────────────────────────────────────────────────

    def _generate_pattern(
        self, pattern_desc: str, language: str = "python",
        context: Any = None,
    ) -> dict[str, Any]:
        """Generate code snippet from template library."""
        ctx = context if isinstance(context, dict) else {}
        lang_patterns = PATTERN_LIBRARY.get(language, PATTERN_LIBRARY["python"])

        # Find pattern by description
        desc_lower = pattern_desc.lower()
        pattern_name = "default"

        for keywords, name in PATTERN_HEURISTICS:
            if any(kw in desc_lower for kw in keywords):
                pattern_name = name
                break

        # Get template
        template = lang_patterns.get(pattern_name, lang_patterns.get("default", ""))

        # Fill placeholders
        try:
            result = template.format(
                name=ctx.get("name", ctx.get("func_name", "generated")),
                class_name=ctx.get("class_name", "GeneratedClass"),
                params=ctx.get("params", "data"),
                operation=ctx.get("operation", "process"),
                required_fields=str(ctx.get("required_fields", "['id', 'name']")),
                handler_map=str(ctx.get("handler_map", "{}")),
            )
        except (KeyError, IndexError):
            result = template

        confidence = 0.9 if pattern_name != "default" else 0.5

        return {
            "result": result,
            "confidence": confidence,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 6: explain_violation
    # ──────────────────────────────────────────────────────────

    def _explain_violation(
        self, code: str, violations: list[str]
    ) -> dict[str, Any]:
        """Explain violations using catalog."""
        if not violations:
            return {
                "result": "No violations detected." if not code else "No violations detected.",
                "confidence": 1.0,
                "source": "deterministic",
            }

        explanations = []
        for v in violations[:5]:
            v_lower = v.lower()
            explanation = None
            for key, msg in VIOLATION_CATALOG.items():
                if key in v_lower or any(kw in v_lower for kw in key.split("_")):
                    explanation = msg
                    break
            if not explanation:
                explanation = f"Code violation detected: {v}"
            explanations.append(explanation)

        return {
            "result": "; ".join(explanations),
            "confidence": 0.95,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  TASK 7: describe_subtask
    # ──────────────────────────────────────────────────────────

    def _describe_subtask(
        self, target: str, action: str, context: str = ""
    ) -> dict[str, Any]:
        """Generate a descriptive name for a subtask."""
        safe_target = re.sub(r'[^a-z0-9_]', '_', target.lower()).strip('_')
        safe_action = re.sub(r'[^a-z0-9_]', '_', action.lower()).strip('_')

        name = re.sub(r'_+', '_', f"{safe_action}_{safe_target}").strip('_')

        if not name or len(name) < 3:
            name = "unnamed_subtask"

        return {
            "result": name,
            "confidence": 0.9,
            "source": "deterministic",
        }

    # ──────────────────────────────────────────────────────────
    #  INDIVIDUAL TASK ACCESS (for partial execution)
    # ──────────────────────────────────────────────────────────

    def classify_intent(self, text: str) -> dict[str, Any]:
        """Public API: Task 1 — classify intent."""
        return self._classify_intent(text)

    def extract_entities(self, text: str) -> dict[str, Any]:
        """Public API: Task 2 — extract entities."""
        return self._extract_entities(text)

    def suggest_pattern(self, target: str, description: str) -> dict[str, Any]:
        """Public API: Task 3 — suggest pattern."""
        return self._suggest_pattern(target, description)

    def fill_template_gaps(self, template: str, context: Any = None) -> dict[str, Any]:
        """Public API: Task 4 — fill template gaps."""
        return self._fill_template_gaps(template, context or {})

    def generate_pattern(self, pattern_desc: str, language: str = "python",
                         context: Any = None) -> dict[str, Any]:
        """Public API: Task 5 — generate pattern."""
        return self._generate_pattern(pattern_desc, language, context)

    def explain_violation(self, code: str, violations: list[str] = None) -> dict[str, Any]:
        """Public API: Task 6 — explain violation."""
        return self._explain_violation(code, violations or [])

    def describe_subtask(self, target: str, action: str) -> dict[str, Any]:
        """Public API: Task 7 — describe subtask."""
        return self._describe_subtask(target, action)
