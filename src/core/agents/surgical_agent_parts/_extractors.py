"""
SurgicalAgent compact extractors and parsing helpers mixin.
"""

import re
import logging
from typing import Any, Dict, Optional, Tuple

from ._imports import (
    IntentOutput, VALID_OPERATIONS, VALID_GOALS, VALID_LANGUAGES,
    EXT_LANG, FENCE_LANG, CRIT_KW, logger,
)


class ExtractorsMixin:
    """Compact regex extractors and parsing helpers for SurgicalAgent."""

    # ============================================================
    #  EXTRACTORES COMPACTOS (regex quirúrgico)
    # ============================================================

    @staticmethod
    def _extract_target_and_lang(text: str) -> Tuple[str, str]:
        """Extrae archivo objetivo y lenguaje del texto."""
        tgt = re.search(r'([\w\.\-]+\.(?:kt|py|go|js|ts|java|rs|c|cpp|h|rb))', text)
        target = tgt.group(1) if tgt else "unknown"
        lang = "python"
        for ext, l in EXT_LANG.items():
            if ext in target:
                lang = l
                break
        return target, lang

    @staticmethod
    def _extract_code_block(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extrae bloques de código (markdown fences + inline detection)."""
        matches = re.findall(r'```(\w*)\n(.*?)```', text, re.DOTALL)
        if matches:
            lang_hint, code = matches[0]
            return FENCE_LANG.get(lang_hint.lower(), "python"), code
        # Inline code detection — only return lines that look like actual code,
        # NOT the entire message (which is often natural language with "import" etc.)
        indicators = ['def ', 'class ', 'function ', 'fun ', 'func ', 'import ', 'from ']
        lines = text.strip().split('\n')
        code_lines = [l for l in lines if any(ind in l for ind in indicators)]
        if code_lines and len(code_lines) >= 2:
            # Require at least 2 code-like lines to reduce false positives
            # from NL messages like "I need to import a function from my module"
            return 'python', '\n'.join(code_lines)
        return None, None

    @staticmethod
    def _extract_entities(text: str) -> Dict[str, Any]:
        """Extrae entidades nombradas (funciones, clases, archivos)."""
        entities: Dict[str, Any] = {}
        func_m = re.search(r'(?:function|func|def|fun)\s+(\w+)', text, re.IGNORECASE)
        if func_m:
            entities["function"] = func_m.group(1)
        class_m = re.search(r'(?:class)\s+(\w+)', text, re.IGNORECASE)
        if class_m:
            entities["class"] = class_m.group(1)
        file_m = re.search(r'([\w\.\-]+\.(?:py|kt|go|js|ts|java|rs|c|cpp|h|rb))', text)
        if file_m:
            entities["file"] = file_m.group(1)
        return entities

    @staticmethod
    def _infer_criticality(message: str) -> str:
        """Infiere criticidad del mensaje."""
        text_lower = message.lower()
        for kw in CRIT_KW["critical"]:
            if kw in text_lower:
                return "critical"
        for kw in CRIT_KW["moderate"]:
            if kw in text_lower:
                return "moderate"
        return "standard"

    @staticmethod
    def _infer_template(operation: str, target: str) -> str:
        """Infiere template type según operation + target."""
        t = target.lower()
        if any(x in t for x in ("api", "server", "endpoint")):
            return "api"
        if any(x in t for x in ("web", "page", "frontend")):
            return "web"
        if any(x in t for x in ("cli", "command")):
            return "cli"
        if any(x in t for x in ("data", "model", "schema")):
            return "data"
        if any(x in t for x in ("mobile", "app")):
            return "mobile"
        if operation in ("OPTIMIZE", "DEBUG"):
            return "automation"
        return "generic"

    # ============================================================
    #  PARSING HELPERS
    # ============================================================

    def _dict_to_output(self, data: Dict[str, Any], source: str = "llm") -> Optional[IntentOutput]:
        """Convierte dict JSON a IntentOutput validado."""
        operation = data.get("operation", "").upper()
        goal = data.get("goal", "").upper()
        if operation not in VALID_OPERATIONS:
            operation = "SEARCH"
        if goal not in VALID_GOALS:
            goal = "FEATURE_ADD"

        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
        except (ValueError, TypeError):
            confidence = 0.5

        language = data.get("language", "python").lower()
        if language not in VALID_LANGUAGES:
            language = "python"

        criticality = str(data.get("criticality", "standard")).strip()
        if criticality not in ("standard", "moderate", "critical"):
            criticality = "standard"

        entities = data.get("entities", {})
        if not isinstance(entities, dict):
            entities = {"raw": str(entities)}

        return IntentOutput(
            operation=operation, goal=goal,
            target=str(data.get("target", "")).strip(),
            language=language,
            entities=entities,
            template_type=str(data.get("template_type", "generic")).strip(),
            criticality=criticality,
            confidence=confidence,
            source=source,
        )

    def _parse_freetext(self, text: str, source: str = "llm") -> Optional[IntentOutput]:
        """Parsea texto libre del LLM cuando no hay JSON."""
        text_upper = text.upper().strip()
        operation = "SEARCH"
        for op in VALID_OPERATIONS:
            if op in text_upper:
                operation = op
                break
        goal = "FEATURE_ADD"
        for g in VALID_GOALS:
            if g in text_upper:
                goal = g
                break
        return IntentOutput(
            operation=operation, goal=goal,
            confidence=0.35, source=source,
        )

    def _cache_result(self, message: str, output: IntentOutput) -> None:
        """Cachea resultado en SmartMemory si disponible."""
        if not self._smart_memory:
            return
        try:
            self._smart_memory.save_to_cache(
                query=message,
                response=f"op={output.operation},goal={output.goal}",
                operation=output.operation,
                goal=output.goal,
                importance=output.confidence,
            )
        except Exception as e:
            logger.debug(f"SurgicalAgent: Cache save failed: {e}")
