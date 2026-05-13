"""
Mixin: Static extraction helper methods for IntentAgent.
"""

import re
from typing import Any, Dict, Optional, Tuple

from ._imports import EXT_LANG_MAP, FENCE_LANG_MAP, CRITICALITY_KEYWORDS


class ExtractMixin:
    """Static extraction helpers: target, language, code, entities, criticality."""

    @staticmethod
    def _extract_target_and_language(text: str) -> Tuple[str, str]:
        """Extrae el archivo objetivo y el lenguaje del texto."""
        # File extension match
        tgt = re.search(
            r'([\w\.\-]+(?:\.kt|\.py|\.go|\.js|\.ts|\.java|\.rs|\.c|\.cpp|\.h|\.rb))',
            text,
        )
        target = tgt.group(1) if tgt else "unknown"

        # Language from extension
        lang = "python"
        for ext, l in EXT_LANG_MAP.items():
            if ext in target:
                lang = l
                break

        return target, lang

    @staticmethod
    def _extract_code_block(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extrae bloques de código de un mensaje (markdown fences)."""
        pattern = r'```(\w*)\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            lang_hint, code = matches[0]
            lang = FENCE_LANG_MAP.get(lang_hint.lower(), "python")
            return lang, code

        # Detect inline code indicators — only return lines that look like actual code,
        # NOT the entire message (which is often natural language with "import" etc.)
        code_indicators = [
            'def ', 'class ', 'function ', 'fun ', 'func ',
            'import ', 'from ', 'package ',
        ]
        lines = text.strip().split('\n')
        code_lines = [l for l in lines if any(ind in l for ind in code_indicators)]
        if code_lines and len(code_lines) >= 2:
            # Require at least 2 code-like lines to reduce false positives
            # from NL messages like "I need to import a function from my module"
            return 'python', '\n'.join(code_lines)

        return None, None

    @staticmethod
    def _extract_entities(text: str) -> Dict[str, Any]:
        """Extrae entidades nombradas del texto (funciones, clases, archivos)."""
        entities: Dict[str, Any] = {}

        # Function names (EN + ES keywords)
        func_match = re.search(
            r'(?:function|func|def|fun|funci[oó]n)\s+(\w+)', text, re.IGNORECASE
        )
        if func_match:
            entities["function"] = func_match.group(1)

        # Class names (EN + ES keywords)
        class_match = re.search(r'(?:class|clase)\s+(\w+)', text, re.IGNORECASE)
        if class_match:
            entities["class"] = class_match.group(1)

        # File names
        file_match = re.search(
            r'([\w\.\-]+\.(?:py|kt|go|js|ts|java|rs|c|cpp|h|rb))',
            text,
        )
        if file_match:
            entities["file"] = file_match.group(1)

        return entities

    @staticmethod
    def _infer_criticality(message: str) -> str:
        """Infiere la criticidad del mensaje."""
        text_lower = message.lower()
        for kw in CRITICALITY_KEYWORDS["critical"]:
            if kw in text_lower:
                return "critical"
        for kw in CRITICALITY_KEYWORDS["moderate"]:
            if kw in text_lower:
                return "moderate"
        return "standard"

    @staticmethod
    def _infer_template_type(operation: str, target: str) -> str:
        """Infiere el tipo de template basado en la operación y target."""
        target_lower = target.lower()

        if "api" in target_lower or "server" in target_lower or "endpoint" in target_lower:
            return "api"
        if "web" in target_lower or "page" in target_lower or "frontend" in target_lower:
            return "web"
        if "cli" in target_lower or "command" in target_lower:
            return "cli"
        if "data" in target_lower or "model" in target_lower or "schema" in target_lower:
            return "data"
        if "mobile" in target_lower or "app" in target_lower:
            return "mobile"
        if operation == "OPTIMIZE" or operation == "DEBUG":
            return "automation"

        return "generic"
