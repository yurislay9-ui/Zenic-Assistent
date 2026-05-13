"""DeterministicPipeline — Tasks 5-7."""

import re
import logging
from typing import Any, Dict, List, Optional
from ..types import DeterministicResult
from ._types import PATTERN_LIBRARY, VIOLATION_CATALOG, PATTERN_HEURISTICS

logger = logging.getLogger(__name__)


class DeterministicTasks5To7Mixin:
    """Mixin providing tasks 5-7 for DeterministicPipeline."""

    # ================================================================
    #  TASK 5: generate_pattern (reemplaza MiniAIEngine.generate_pattern)
    # ================================================================

    def generate_pattern(self, pattern_desc: str,
                         language: str = "python",
                         context: Optional[Dict[str, Any]] = None) -> DeterministicResult:
        """
        Genera un snippet de código desde la librería de templates.

        Reemplaza: MiniAIEngine.generate_pattern() (que usaba LLM ~20 líneas)
        Mejora: Código siempre correcto, compilable, sin alucinaciones

        NOTA: La IA NUNCA genera código. El código viene de templates
        probados y validados, no de generación probabilística.
        """
        ctx = context or {}
        lang_patterns = PATTERN_LIBRARY.get(language, PATTERN_LIBRARY["python"])

        # Buscar patrón por descripción
        desc_lower = pattern_desc.lower()
        pattern_name = "default"

        for keywords, name in PATTERN_HEURISTICS:
            if any(kw in desc_lower for kw in keywords):
                pattern_name = name
                break

        # Obtener template
        template = lang_patterns.get(pattern_name, lang_patterns.get("default", ""))

        # Rellenar placeholders simples
        name = ctx.get("name", ctx.get("func_name", "generated"))
        class_name = ctx.get("class_name", "GeneratedClass")
        params = ctx.get("params", "data")
        operation = ctx.get("operation", "process")

        result = template.format(
            name=name,
            class_name=class_name,
            params=params,
            operation=operation,
            required_fields=str(ctx.get("required_fields", "['id', 'name']")),
            handler_map=str(ctx.get("handler_map", "{}")),
        )

        confidence = 0.9 if pattern_name != "default" else 0.5

        return DeterministicResult(
            task_name="generate_pattern",
            success=True,
            result=result,
            confidence=confidence,
            source="deterministic",
        )

    # ================================================================
    #  TASK 6: explain_violation (reemplaza MiniAIEngine.explain_violation)
    # ================================================================

    def explain_violation(self, code: str,
                          violations: List[str]) -> DeterministicResult:
        """
        Explica violaciones usando el catálogo de mensajes.

        Reemplaza: MiniAIEngine.explain_violation() (que usaba LLM ~50 tokens)
        Mejora: Explicaciones consistentes, sin variabilidad
        """
        if not violations:
            return DeterministicResult(
                task_name="explain_violation",
                success=True,
                result="No violations detected.",
                confidence=1.0,
                source="deterministic",
            )

        explanations = []
        for v in violations[:5]:  # Max 5 violations
            v_lower = v.lower()
            # Buscar en catálogo
            explanation = None
            for key, msg in VIOLATION_CATALOG.items():
                if key in v_lower or any(kw in v_lower for kw in key.split("_")):
                    explanation = msg
                    break

            if not explanation:
                explanation = f"Code violation detected: {v}"
            explanations.append(explanation)

        result = "; ".join(explanations)

        return DeterministicResult(
            task_name="explain_violation",
            success=True,
            result=result,
            confidence=0.95,
            source="deterministic",
        )

    # ================================================================
    #  TASK 7: describe_subtask (reemplaza MiniAIEngine.describe_subtask)
    # ================================================================

    def describe_subtask(self, target: str, action: str,
                         context: str = "") -> DeterministicResult:
        """
        Genera un nombre descriptivo para un subtask.

        Reemplaza: MiniAIEngine.describe_subtask() (que usaba LLM ~30 tokens)
        Mejora: Nombres consistentes y limpios
        """
        safe_target = re.sub(r'[^a-z0-9_]', '_', target.lower()).strip('_')
        safe_action = re.sub(r'[^a-z0-9_]', '_', action.lower()).strip('_')

        # Limpiar underscores duplicados
        name = re.sub(r'_+', '_', f"{safe_action}_{safe_target}").strip('_')

        if not name or len(name) < 3:
            name = "unnamed_subtask"

        return DeterministicResult(
            task_name="describe_subtask",
            success=True,
            result=name,
            confidence=0.9,
            source="deterministic",
        )

    # ================================================================
    #  UTILITY: Batch execute all 7 tasks
    # ================================================================

    def execute_all(self, text: str, code: str = "",
                    language: str = "python",
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, DeterministicResult]:
        """
        Ejecuta todas las tareas determinísticas en secuencia.

        Returns:
            Diccionario con los resultados de cada tarea
        """
        ctx = context or {}
        results = {}

        results["classify"] = self.classify_intent(text)
        results["extract"] = self.extract_entities(text)

        target = results["extract"].result.get("file", "target")
        results["pattern"] = self.suggest_pattern(target, text)

        template = ctx.get("template", "")
        if template:
            results["fill"] = self.fill_template_gaps(template, ctx)
        else:
            results["fill"] = DeterministicResult(
                task_name="fill_template_gaps", success=True,
                result="", confidence=1.0, source="deterministic",
            )

        if code:
            results["generate"] = self.generate_pattern(
                results["pattern"].result, language, ctx
            )
            violations = ctx.get("violations", [])
            results["explain"] = self.explain_violation(code, violations)
        else:
            results["generate"] = DeterministicResult(
                task_name="generate_pattern", success=True,
                result="", confidence=1.0, source="deterministic",
            )
            results["explain"] = DeterministicResult(
                task_name="explain_violation", success=True,
                result="No code to validate.", confidence=1.0,
                source="deterministic",
            )

        results["subtask"] = self.describe_subtask(target, "process")

        return results
