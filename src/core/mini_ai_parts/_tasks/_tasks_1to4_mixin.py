"""
MiniAIEngine bounded task methods (tasks 1-7) — PURELY DETERMINISTIC.

CAMBIO FUNDAMENTAL (v17.1):
  ANTES: Las 7 tareas llamaban _call_llm() primero, luego fallback.
  AHORA: Las 7 tareas son 100% determinísticas. NUNCA llaman al LLM.

  La IA SOLO se usa para veredictos binarios (SÍ/NO) vía VerdictMixin.
  Esto elimina:
    - Latencia de 3-8s por tarea
    - Alucinaciones en clasificación/extracción/generación
    - Parsing errors del output del LLM
    - Uso innecesario del modelo Qwen3-0.6B

  Las 7 tareas ahora delegan al DeterministicPipeline cuando está
  disponible, o usan métodos fallback propios cuando no.
"""

import re
import os
import json
import logging
from typing import Optional, Any
from .._imports import IntentResult
from src.core.shared.constants import VALID_INTENT_OPERATIONS, VALID_INTENT_GOALS, EXT_LANG_MAP

class BoundedTasks1To4Mixin:
    """
    7 Bounded Task methods — 100% deterministic, NO LLM calls.

    CRITICAL DESIGN PRINCIPLE:
      These methods NEVER call _call_llm(). They are purely algorithmic.
      The LLM is reserved exclusively for VerdictMixin.verdict().

    Each method has a deterministic implementation that:
      - Returns consistent results (same input → same output)
      - Has zero latency from LLM calls
      - Cannot hallucinate or produce unpredictable output
      - Works even when the model is not loaded
    """

    # ================================================================
    #  BOUNDED TASK 1: classify_intent (deterministic keyword scoring)
    # ================================================================

    # ── Imported from canonical constants.py ──
    VALID_OPERATIONS = VALID_INTENT_OPERATIONS
    VALID_GOALS = VALID_INTENT_GOALS

    # Keyword maps with weighted scoring
    OP_KEYWORDS = {
        "CREATE": ["create", "new", "add", "implement", "crear", "nuevo", "agregar", "generar", "build", "make", "escribir", "write"],
        "REFACTOR": ["refactor", "restructure", "reorganize", "refactorizar", "reestructurar", "clean", "simplify", "mejorar", "limpiar"],
        "DELETE": ["delete", "remove", "eliminate", "eliminar", "borrar", "quitar", "drop", "remover"],
        "SEARCH": ["search", "find", "where", "locate", "buscar", "encontrar", "donde", "localizar"],
        "ANALYZE": ["analyze", "review", "check", "analizar", "revisar", "verificar", "examine", "inspeccionar"],
        "EXPLAIN": ["explain", "describe", "what does", "explicar", "describir", "como funciona", "que hace"],
        "DEBUG": ["debug", "fix", "correct", "bug", "error", "corregir", "arreglar", "depurar", "reparar"],
        "OPTIMIZE": ["optimize", "improve", "faster", "optimizar", "mejorar", "acelerar", "performance", "rendimiento"],
    }

    GOAL_KEYWORDS = {
        "BUG_FIX": ["bug", "fix", "error", "corregir", "arreglar", "wrong", "broken", "falla", "defecto"],
        "FEATURE_ADD": ["add", "new", "feature", "agregar", "nueva", "implement", "crear", "nueva funcionalidad"],
        "SECURITY_HARDEN": ["security", "auth", "login", "token", "crypto", "vulnerability", "seguridad", "autenticar"],
        "PERFORMANCE": ["optimize", "fast", "slow", "performance", "optimizar", "rapido", "lento", "velocidad"],
        "MODERN_PATTERN": ["modern", "update", "upgrade", "moderno", "actualizar", "migrate", "migrar"],
        "COMPLEXITY_REDUCTION": ["simplify", "reduce", "complex", "simplificar", "reducir", "complejo"],
        "READABILITY": ["readable", "clean", "comment", "legible", "limpio", "documentar", "claro"],
    }

    def classify_intent(self, text: str) -> IntentResult:
        """
        Clasifica la intención del usuario usando keyword scoring ponderado.

        100% determinístico. NUNCA llama al LLM.
        Mejora sobre versión anterior:
          - 0ms de latencia (antes 3-8s con 2 llamadas LLM)
          - 0% de errores de parsing
          - Resultados consistentes y reproducibles
        """
        text_lower = text.lower()
        words = text_lower.split()

        # Score each operation
        best_op, best_score = "SEARCH", 0
        for op, keywords in self.OP_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw in words:
                    score += 2  # Word match is stronger
                elif kw in text_lower:
                    score += 1  # Substring match
            if score > best_score:
                best_score, best_op = score, op

        # Classify goal
        goal = self._deterministic_goal(text_lower)

        confidence = min(best_score / 10.0, 0.9) if best_score > 0 else 0.1

        logger.debug(
            f"BoundedTasks.classify_intent: op={best_op}, goal={goal}, "
            f"confidence={confidence:.2f}, score={best_score} (deterministic)"
        )

        return IntentResult(
            operation=best_op,
            goal=goal,
            confidence=confidence,
            source="deterministic",
        )

    # ================================================================
    #  BOUNDED TASK 2: extract_entities (regex + patterns)
    # ================================================================

    # Extension-to-language map (imported from constants.py)
    EXT_LANG_MAP = EXT_LANG_MAP

    def extract_entities(self, text: str) -> dict[str, Any]:
        """
        Extrae entidades: archivo, lenguaje, función objetivo.

        100% determinístico. NUNCA llama al LLM.
        Mejora: 0ms de latencia, 0% de JSON parse errors.
        """
        # File extraction
        file_match = re.search(r'([\w\.-]+\.(py|kt|go|js|ts|java|rs|rb|cpp|c|h|swift|scala))', text)
        file_name = file_match.group(1) if file_match else ""

        # Language from extension
        ext = os.path.splitext(file_name)[1] if file_name else ""
        lang = self.EXT_LANG_MAP.get(ext, "unknown")

        # Language from keywords (if no file extension)
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
            elif "golang" in text_lower or "func " in text:
                lang = "go"
            elif "rust" in text_lower or "fn " in text or "let mut" in text:
                lang = "rust"
            elif "ruby" in text_lower or "def " in text and "end" in text:
                lang = "ruby"

        # Function name extraction
        func_match = re.search(r'(?:function|func|def|fun)\s+(\w+)', text)
        function = func_match.group(1) if func_match else None

        confidence = 0.9 if file_name else (0.6 if lang != "unknown" else 0.2)

        logger.debug(
            f"BoundedTasks.extract_entities: file={file_name}, lang={lang}, "
            f"func={function}, confidence={confidence:.2f} (deterministic)"
        )

        return {
            "file": file_name,
            "lang": lang,
            "function": function,
            "source": "deterministic",
        }

    # ================================================================
    #  BOUNDED TASK 3: suggest_pattern (heuristic lookup)
    # ================================================================

    PATTERN_HEURISTICS = [
        (["async", "await", "coroutine", "asincrono"], "async_await"),
        (["validate", "validar", "check", "verify", "verificar"], "validator"),
        (["repository", "repo", "database", "db", "base de datos"], "repository"),
        (["factory", "create", "creator", "fabrica"], "factory"),
        (["middleware", "interceptor", "pipeline"], "middleware"),
        (["observer", "subscribe", "event", "listen", "escuchar"], "observer"),
        (["security", "auth", "login", "token", "seguridad"], "security"),
        (["cache", "memoize", "store", "cachear"], "cache"),
        (["singleton", "single", "unique", "unico"], "singleton"),
        (["test", "testing", "prueba", "spec"], "default"),
    ]

    def suggest_pattern(self, target: str, description: str) -> str:
        """
        Sugiere un patrón de código usando heurísticas.

        100% determinístico. NUNCA llama al LLM.
        Mejora: Siempre devuelve un patrón válido, 0% de respuestas basura.
        """
        desc_lower = description.lower()
        target_lower = target.lower()
        combined = f"{desc_lower} {target_lower}"

        for keywords, pattern_name in self.PATTERN_HEURISTICS:
            if any(kw in combined for kw in keywords):
                result = f"{pattern_name}_pattern"
                logger.debug(f"BoundedTasks.suggest_pattern: {result} (deterministic)")
                return result

        logger.debug("BoundedTasks.suggest_pattern: default_pattern (deterministic)")
        return "default_pattern"

    # ================================================================
    #  BOUNDED TASK 4: fill_template_gaps (context + defaults)
    # ================================================================

    def fill_template_gaps(self, template: str, context: dict[str, Any]) -> str:
        """
        Rellena los huecos __GAP_N__ en un template con información contextual.

        100% determinístico. NUNCA llama al LLM.
        Mejora: Siempre rellena todos los huecos, 0% de JSON parse errors.
        """
        gaps = re.findall(r'__GAP_(\w+)__', template)
        if not gaps:
            return template

        defaults = {
            "NAME": context.get("name", "generated"),
            "CLASS_NAME": context.get("class_name", "GeneratedClass"),
            "FUNC_NAME": context.get("func_name", "generated_function"),
            "RETURN_TYPE": context.get("return_type", "Any"),
            "PARAMS": context.get("params", "self"),
            "BODY": context.get("body", "pass"),
            "DOCSTRING": context.get("docstring", "Generated by ZENIC-AGENTS v1"),
            "IMPORT": context.get("import_", "import os"),
            "VAR_NAME": context.get("var_name", "result"),
            "TYPE": context.get("type", "str"),
            "OPERATION": context.get("operation", "process"),
            "REQUIRED_FIELDS": str(context.get("required_fields", "['id', 'name']")),
            "HANDLER_MAP": str(context.get("handler_map", "{}")),
        }

        result = template
        filled_count = 0
        for gap in gaps:
            gap_lower = gap.lower()
            # Try context first (case-insensitive)
            value = None
            if gap_lower in context:
                value = context[gap_lower]
            elif gap in context:
                value = context[gap]
            elif gap in defaults:
                value = defaults[gap]
            else:
                value = f"placeholder_{gap_lower}"

            result = result.replace(f"__GAP_{gap}__", str(value))
            filled_count += 1

        logger.debug(
            f"BoundedTasks.fill_template_gaps: filled {filled_count} gaps (deterministic)"
        )
        return result
