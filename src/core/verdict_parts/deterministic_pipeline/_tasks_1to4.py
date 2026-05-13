"""
DeterministicPipeline - Pipeline que hace TODAS las tareas sin IA.

Reemplaza las 7 tareas bounded de MiniAIEngine con versiones
puramente determinísticas que son más rápidas y más confiables.

Tareas reemplazadas:
  1. classify_intent()    → Keyword scoring + evidencia
  2. extract_entities()   → Regex extraction + patrones
  3. suggest_pattern()    → Lookup table + heuristicas
  4. fill_template_gaps() → Context mapping + defaults
  5. generate_pattern()   → Template library + composición
  6. explain_violation()  → Formateo automático + catálogo
  7. describe_subtask()   → Composición automática de nombre

Ventajas sobre la versión con IA:
  - 0ms de latencia LLM (antes 3-8s por llamada)
  - 0% de alucinaciones
  - 0% de parsing errors (no depende de output de IA)
  - Determinístico: mismo input → mismo output, siempre
  - Funciona sin GPU, sin modelo, sin dependencias externas
"""

import re
import os
import json
import logging
from typing import Dict, Any, List, Optional
from ..types import DeterministicResult, Evidence, EvidenceType, Verdict
from ..evidence_collector import EvidenceCollector, OP_KEYWORDS, GOAL_KEYWORDS
from ._types import EXT_LANG_MAP, PATTERN_LIBRARY, VIOLATION_CATALOG, PATTERN_HEURISTICS

class DeterministicTasks1To4Mixin:
    """
    Pipeline determinístico que reemplaza las 7 tareas de MiniAIEngine.

    Todas las operaciones son puramente algorítmicas:
    - No usan el modelo LLM
    - Son determinísticas (mismo input → mismo output)
    - Son más rápidas que las versiones con IA
    - Son más confiables (no alucinan)

    Cuando el resultado no es suficientemente confiable,
    devuelve confidence baja para que el ConsensusResolver
    decida si necesita arbitraje de IA.
    """

    def __init__(self):
        self._evidence_collector = EvidenceCollector()

    # ================================================================
    #  TASK 1: classify_intent (reemplaza MiniAIEngine.classify_intent)
    # ================================================================

    def classify_intent(self, text: str) -> DeterministicResult:
        """
        Clasifica la intención del usuario usando keyword scoring.

        Reemplaza: MiniAIEngine.classify_intent() (que usaba 2 llamadas LLM)
        Mejora: 0ms de latencia, 0% de errores de parsing, determinístico
        """
        evidence = self._evidence_collector.collect_intent_evidence(text)
        result = self._evidence_collector.collect_goal_evidence(text)
        all_evidence = evidence + result

        from ..consensus_resolver import ConsensusResolver
        resolver = ConsensusResolver()
        return resolver.resolve_classification(text, all_evidence)

    # ================================================================
    #  TASK 2: extract_entities (reemplaza MiniAIEngine.extract_entities)
    # ================================================================

    def extract_entities(self, text: str) -> DeterministicResult:
        """
        Extrae entidades (archivo, lenguaje, función) usando regex.

        Reemplaza: MiniAIEngine.extract_entities() (que usaba LLM con JSON)
        Mejora: 0ms de latencia, 0% de JSON parse errors
        """
        # File extraction
        file_match = re.search(r'([\w\.-]+\.(py|kt|go|js|ts|java|rs|rb|cpp|c|h))', text)
        file_name = file_match.group(1) if file_match else ""

        # Language from extension
        ext = os.path.splitext(file_name)[1] if file_name else ""
        lang = EXT_LANG_MAP.get(ext, "unknown")

        # Function name extraction
        func_match = re.search(r'(?:function|func|def|fun)\s+(\w+)', text)
        function = func_match.group(1) if func_match else None

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
            elif "golang" in text_lower or "go " in text_lower or "func " in text:
                lang = "go"

        confidence = 0.9 if file_name else (0.6 if lang != "unknown" else 0.2)

        return DeterministicResult(
            task_name="extract_entities",
            success=True,
            result={
                "file": file_name,
                "lang": lang,
                "function": function,
            },
            confidence=confidence,
            source="deterministic",
        )

    # ================================================================
    #  TASK 3: suggest_pattern (reemplaza MiniAIEngine.suggest_pattern)
    # ================================================================

    def suggest_pattern(self, target: str, description: str) -> DeterministicResult:
        """
        Sugiere un patrón de código usando heurísticas.

        Reemplaza: MiniAIEngine.suggest_pattern() (que usaba LLM)
        Mejora: Siempre devuelve un patrón válido, 0% de respuestas basura
        """
        desc_lower = description.lower()
        target_lower = target.lower()
        combined = f"{desc_lower} {target_lower}"

        for keywords, pattern_name in PATTERN_HEURISTICS:
            if any(kw in combined for kw in keywords):
                return DeterministicResult(
                    task_name="suggest_pattern",
                    success=True,
                    result=f"{pattern_name}_pattern",
                    confidence=0.8,
                    source="deterministic",
                )

        return DeterministicResult(
            task_name="suggest_pattern",
            success=True,
            result="default_pattern",
            confidence=0.3,
            source="deterministic",
        )

    # ================================================================
    #  TASK 4: fill_template_gaps (reemplaza MiniAIEngine.fill_template_gaps)
    # ================================================================

    def fill_template_gaps(self, template: str,
                           context: Dict[str, Any]) -> DeterministicResult:
        """
        Rellena huecos de template con contexto y defaults.

        Reemplaza: MiniAIEngine.fill_template_gaps() (que usaba LLM para JSON)
        Mejora: Siempre rellena todos los huecos, 0% de JSON parse errors
        """
        gaps = re.findall(r'__GAP_(\w+)__', template)
        if not gaps:
            return DeterministicResult(
                task_name="fill_template_gaps",
                success=True,
                result=template,
                confidence=1.0,
                source="deterministic",
            )

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

        all_filled = not re.search(r'__GAP_\w+__', result)
        confidence = 1.0 if all_filled else 0.5

        return DeterministicResult(
            task_name="fill_template_gaps",
            success=True,
            result=result,
            confidence=confidence,
            source="deterministic",
        )
